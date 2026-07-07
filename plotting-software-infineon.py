"""
MNST Lab Live Plotter  –  AML Terminal Log format (3-Column Data)
══════════════════════════════════════════════════════════════════
Log format (AML terminal logger, CRLF):
  Data rows: col-0 = H2 Vol%  e.g. "-0.11"
             col-1 = Raw ADC  e.g. "+0030.000"
             col-2 = Temp     e.g. "25"
  Sampling : 224 ms / sample (configurable)

Performance design for 48-hour continuous runs
───────────────────────────────────────────────
• data_x / data_y stored as array.array('d') – ~2× more memory-efficient
• Renderer decimates points automatically to maintain 60 FPS
• 3 Independent Plot Tabs (H2 Vol, Raw, Temp) updated dynamically
"""

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import time
import os
import csv
import random
import array as arr
from queue import Queue, Empty
from datetime import datetime

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter, FormatStrFormatter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import numpy as np

# ───────────────────────── CONFIG ────────────────────────────
LOG_FILE_DEFAULT = r"C:\Users\Aniket\OneDrive\Desktop\Terminal log\terminal.log"
READ_POLL_SEC    = 0.05
PLOT_REFRESH_MS  = 224          # MCU rate is approx 224ms
MAX_OVERLAYS     = 10

MAX_RENDER_PTS   = 8_000        # max points rendered to matplotlib at once
SCATTER_LIMIT    = 200_000      # hide scatter dots above this many points

# Simulator knobs
USE_SIMULATOR    = False
SIM_PERIOD_SEC   = 0.224

# ─── Parser ──────────────────────────────────────────────────
def _parse_line(line: str):
    """Parses 3 columns: H2 Vol%, Raw ADC, Temp. Returns tuple of floats or None."""
    parts = line.strip().split()
    if len(parts) >= 3:
        try:
            return float(parts[0]), float(parts[1]), float(parts[2])
        except ValueError:
            return None
    return None

def fmt_mmss(x, pos):
    """Axis tick: hh:mm:ss for long runs, mm:ss for short ones."""
    x = max(0.0, float(x))
    h  = int(x // 3600)
    m  = int((x % 3600) // 60)
    s  = int(x % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def sec_to_mmss(sec: float) -> str:
    sec = max(0.0, float(sec))
    h   = int(sec // 3600)
    m   = int((sec % 3600) // 60)
    s   = int(sec % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def _decimate(xs, ys, max_pts):
    """Return (xs_d, ys_d) downsampled to max_pts using min-max decimation."""
    n = len(xs)
    if n <= max_pts:
        return xs, ys

    x_np = np.frombuffer(xs, dtype=np.float64) if isinstance(xs, arr.array) else np.asarray(xs, dtype=np.float64)
    y_np = np.frombuffer(ys, dtype=np.float64) if isinstance(ys, arr.array) else np.asarray(ys, dtype=np.float64)

    stride  = max(1, n // (max_pts // 2))
    indices = []
    for i in range(0, n - stride + 1, stride):
        block = y_np[i:i + stride]
        base  = i + np.argmin(block)
        peak  = i + np.argmax(block)
        if base < peak:
            indices.extend([base, peak])
        else:
            indices.extend([peak, base])

    if indices and indices[-1] != n - 1:
        indices.append(n - 1)

    idx = np.array(indices, dtype=np.intp)
    return x_np[idx], y_np[idx]


# ─────────────────────────────────────────────────────────────
#  FileMonitor
# ─────────────────────────────────────────────────────────────
class FileMonitor:
    def __init__(self):
        self.file_path   = None
        self.running     = False
        self.sample_sec  = 0.224

        self.data_x   = arr.array('d')
        self.data_y1  = arr.array('d') # H2 Vol%
        self.data_y2  = arr.array('d') # Raw ADC
        self.data_y3  = arr.array('d') # Temp

        self.file_pos  = 0
        self.t0        = None
        self._seq      = 0
        self._line_buf = ""

        self.queue   = Queue()          
        self.event_q = Queue()          

    def start(self):
        if (not USE_SIMULATOR) and (not self.file_path):
            return

        self.running   = True
        self.file_pos  = 0
        self._seq      = 0
        self._line_buf = ""
        self.data_x    = arr.array('d')
        self.data_y1   = arr.array('d')
        self.data_y2   = arr.array('d')
        self.data_y3   = arr.array('d')
        self.queue     = Queue()
        self.event_q   = Queue()
        self.t0        = time.time()

        target = self.sim_loop if USE_SIMULATOR else self.read_loop
        threading.Thread(target=target, daemon=True).start()

    def stop(self):
        self.running = False

    def reset_buffers(self):
        self._seq      = 0
        self._line_buf = ""
        self.data_x    = arr.array('d')
        self.data_y1   = arr.array('d')
        self.data_y2   = arr.array('d')
        self.data_y3   = arr.array('d')
        self.queue     = Queue()
        self.t0        = time.time()

    def sim_loop(self):
        v1, v2, v3 = 1.25, 1090.0, 25.0
        while self.running:
            v1 += random.uniform(-0.02, 0.02)
            v2 += random.uniform(-1.5, 1.5)
            v3 += random.uniform(-0.1, 0.1)
            t = self._seq * self.sample_sec
            self._seq += 1
            self.queue.put((t, round(v1, 2), round(v2, 2), round(v3, 1)))
            time.sleep(self.sample_sec)

    def read_loop(self):
        while self.running and self.file_path and not os.path.exists(self.file_path):
            time.sleep(READ_POLL_SEC)

        last_size = 0

        while self.running and self.file_path:
            try:
                try:
                    size = os.path.getsize(self.file_path)
                except FileNotFoundError:
                    time.sleep(READ_POLL_SEC)
                    continue

                if (size < self.file_pos) or (size < last_size):
                    self.file_pos  = 0
                    self._seq      = 0
                    self._line_buf = ""
                    self.event_q.put(("RESET", "File truncated/cleared by logger"))
                last_size = size

                with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(self.file_pos)
                    chunk = f.read()
                    self.file_pos = f.tell()

                if chunk:
                    chunk          = self._line_buf + chunk
                    parts          = chunk.split("\n")
                    self._line_buf = parts[-1]          

                    for raw_line in parts[:-1]:
                        line = raw_line.rstrip("\r") + "\n"
                        vals = _parse_line(line)
                        if vals is not None:
                            t = self._seq * self.sample_sec
                            self._seq += 1
                            self.queue.put((t, vals[0], vals[1], vals[2]))

            except Exception as ex:
                print("FileMonitor error:", ex)

            time.sleep(READ_POLL_SEC)


# ─────────────────────────────────────────────────────────────
#  LivePlotterApp
# ─────────────────────────────────────────────────────────────
class LivePlotterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MNST Lab  –  AML Live Plotter")
        self.root.geometry("1350x860")
        self.root.configure(bg="#1A2535")
        self.root.minsize(1000, 650)

        self.monitor  = FileMonitor()
        self.overlays = []
        self._last_n  = 0               

        self._setup_styles()
        self._build_ui()
        self.update_plot()

    def _setup_styles(self):
        s = ttk.Style()
        try:
            s.theme_use("clam")
        except Exception:
            pass

        BG   = "#1A2535"
        CARD = "#1A2535"
        FG   = "#D0D8E8"
        ACC  = "#5BA3D9"
        BTN  = "#243348"

        s.configure("Top.TFrame",      background=BG)
        s.configure("Card.TLabelframe", background=CARD, foreground="#7A9CBF", bordercolor="#2A3F5A", relief="groove")
        s.configure("Card.TLabelframe.Label", background=CARD, foreground=ACC, font=("Segoe UI Semibold", 8))
        s.configure("Top.TLabel", background=BG, foreground=FG, font=("Segoe UI", 9))
        s.configure("Accent.TLabel", background=BG, foreground=ACC, font=("Consolas", 10, "bold"))
        s.configure("Top.TButton", padding=(10, 5), background=BTN, foreground="#E8EEF8", font=("Segoe UI", 9))
        s.map("Top.TButton", background=[("active", "#2563EB")], foreground=[("active", "#FFFFFF")])
        s.configure("Sm.TButton", padding=(6, 4), background=BTN, foreground="#E8EEF8", font=("Segoe UI", 8))
        s.map("Sm.TButton", background=[("active", "#2563EB")], foreground=[("active", "#FFFFFF")])
        s.configure("Top.TEntry", padding=(5, 3), fieldbackground="#0F1A2A", foreground="#E8EEF8", insertcolor=ACC)
        s.configure("Top.TCheckbutton", background=BG, foreground=FG, font=("Segoe UI", 9))
        s.map("Top.TCheckbutton", background=[("active", BG)])
        
        # Notebook (Tabs) Styling to match dark aesthetic
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=BTN, foreground=FG, padding=(15, 6), font=("Segoe UI Semibold", 10))
        s.map("TNotebook.Tab", background=[("selected", ACC)], foreground=[("selected", "#1A2535")])

    def _build_ui(self):
        self._build_topbar()
        self._build_opts_row()
        self._build_plot()
        self._build_statsbar()

    def _build_topbar(self):
        top = ttk.Frame(self.root, style="Top.TFrame", padding=(10, 8, 10, 4))
        top.pack(fill=tk.X)

        fb = ttk.LabelFrame(top, text="Log File", style="Card.TLabelframe", padding=(8, 5))
        fb.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(fb, text="📂 Load…",  style="Top.TButton", command=self.load_file).pack(side=tk.LEFT, padx=3)
        ttk.Button(fb, text="Default",   style="Top.TButton", command=self.use_default).pack(side=tk.LEFT, padx=3)
        self.file_var = tk.StringVar(value="(no file selected)")
        ttk.Label(fb, textvariable=self.file_var, style="Top.TLabel", width=52).pack(side=tk.LEFT, padx=8)

        cb = ttk.LabelFrame(top, text="Controls", style="Card.TLabelframe", padding=(8, 5))
        cb.pack(side=tk.LEFT, padx=(0, 6))
        self.status_var = tk.StringVar(value="idle")
        ttk.Button(cb, text="▶ Start", style="Top.TButton", command=self.start).pack(side=tk.LEFT, padx=3)
        ttk.Button(cb, text="⏹ Stop",  style="Top.TButton", command=self.stop).pack(side=tk.LEFT, padx=3)
        ttk.Button(cb, text="⟳ Reset", style="Top.TButton", command=self.manual_reset).pack(side=tk.LEFT, padx=3)
        ttk.Label(cb, text="Status:", style="Top.TLabel").pack(side=tk.LEFT, padx=(8, 3))
        ttk.Label(cb, textvariable=self.status_var, style="Accent.TLabel").pack(side=tk.LEFT)

        sb = ttk.LabelFrame(top, text="Sample Interval", style="Card.TLabelframe", padding=(8, 5))
        sb.pack(side=tk.LEFT, padx=(0, 6))
        self.sample_var = tk.StringVar(value="224")
        ttk.Entry(sb, textvariable=self.sample_var, width=6, style="Top.TEntry").pack(side=tk.LEFT, padx=3)
        ttk.Label(sb, text="ms", style="Top.TLabel").pack(side=tk.LEFT)
        ttk.Button(sb, text="Apply", style="Top.TButton", command=self.apply_sample_interval).pack(side=tk.LEFT, padx=(5, 0))

        tb = ttk.LabelFrame(top, text="Graph Title", style="Card.TLabelframe", padding=(8, 5))
        tb.pack(side=tk.LEFT, padx=(0, 6))
        self.title_var = tk.StringVar(value="TCI Sensor Live Data")
        ttk.Entry(tb, textvariable=self.title_var, width=18, style="Top.TEntry").pack(side=tk.LEFT, padx=3)
        ttk.Button(tb, text="Apply", style="Top.TButton", command=self.apply_title).pack(side=tk.LEFT, padx=3)

        eb = ttk.LabelFrame(top, text="Export / Overlay", style="Card.TLabelframe", padding=(6, 5))
        eb.pack(side=tk.LEFT)
        for txt, cmd in [("CSV", self.export_csv), ("Graph", self.save_graph), 
                         ("+Overlay", self.overlay_csv), ("−Remove", self.remove_last_overlay), ("✕Clear", self.clear_overlays)]:
            ttk.Button(eb, text=txt, style="Sm.TButton", command=cmd).pack(side=tk.LEFT, padx=2)

    def _build_opts_row(self):
        opts = ttk.Frame(self.root, style="Top.TFrame", padding=(12, 2, 12, 4))
        opts.pack(fill=tk.X)

        self.autoscale_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opts, text="Auto-scale Y", variable=self.autoscale_var, style="Top.TCheckbutton").pack(side=tk.LEFT)

        ttk.Label(opts, text="  Plot mode:", style="Top.TLabel").pack(side=tk.LEFT, padx=(14, 4))
        self.plot_mode_var = tk.StringVar(value="line+dots")
        for label, val in [("Line+Dots", "line+dots"), ("Line only", "line"), ("Dots only", "dots")]:
            ttk.Radiobutton(opts, text=label, value=val, variable=self.plot_mode_var, style="Top.TCheckbutton", command=self._apply_plot_mode).pack(side=tk.LEFT, padx=3)

        ttk.Label(opts, text="  Window (pts):", style="Top.TLabel").pack(side=tk.LEFT, padx=(12, 3))
        self.window_var = tk.StringVar(value="all")
        ttk.Entry(opts, textvariable=self.window_var, width=7, style="Top.TEntry").pack(side=tk.LEFT)
        ttk.Label(opts, text="(blank=all)", style="Top.TLabel").pack(side=tk.LEFT, padx=(3, 0))

        self.note_var   = tk.StringVar(value="")
        self.latest_var = tk.StringVar(value="Latest: --.-")
        ttk.Label(opts, textvariable=self.note_var, style="Top.TLabel").pack(side=tk.RIGHT, padx=(0, 20))
        ttk.Label(opts, textvariable=self.latest_var, style="Accent.TLabel").pack(side=tk.RIGHT, padx=(0, 6))

    def _build_plot(self):
        plot_frame = tk.Frame(self.root, bg="#1A2535")
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(4, 0))

        self.notebook = ttk.Notebook(plot_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.figs, self.axs, self.lines, self.points = [], [], [], []
        self.canvases, self.toolbars, self.legs = [], [], []

        titles = ["H2 Volume (%)", "Raw ADC Value", "Temperature (°C)"]
        colors = ["#1565C0", "#E65100", "#2E7D32"]

        for i in range(3):
            f = tk.Frame(self.notebook, bg="#1A2535")
            self.notebook.add(f, text=f"  {titles[i]}  ")

            fig, ax = plt.subplots(figsize=(12.0, 6.0))
            fig.patch.set_facecolor("#FFFFFF")
            ax.set_facecolor("#F8F8F4")

            for spine in ax.spines.values():
                spine.set_edgecolor("#BBBBAA")
                spine.set_linewidth(0.8)

            ax.grid(True, color="#DDDDD0", linestyle="--", linewidth=0.6, alpha=0.9)
            ax.set_axisbelow(True)
            ax.tick_params(colors="#333333", labelsize=9)
            ax.yaxis.set_major_formatter(FormatStrFormatter("%.2f"))

            ax.set_xlabel("Time (hh:mm:ss / mm:ss)", fontsize=10, color="#444444")
            ax.set_ylabel(titles[i], fontsize=10, color="#444444")
            ax.set_title(self.title_var.get(), fontsize=12, fontweight="bold", color="#222222")
            ax.xaxis.set_major_formatter(FuncFormatter(fmt_mmss))

            (line,) = ax.plot([], [], lw=1.6, color=colors[i], label=titles[i], solid_capstyle="round")
            pts = ax.scatter([], [], s=16, color=colors[i], zorder=4, label="_nolegend_")

            canvas = FigureCanvasTkAgg(fig, master=f)
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            tb_frame = tk.Frame(f, bg="#131D2A")
            tb_frame.pack(fill=tk.X, pady=(0, 4))
            toolbar = NavigationToolbar2Tk(canvas, tb_frame)
            toolbar.config(background="#131D2A")
            for child in toolbar.winfo_children():
                try:
                    child.config(background="#DFE8F3", foreground="#05379A", activebackground="#2A4060", activeforeground="#FFFFFF", relief="flat", bd=0)
                except Exception: pass
            toolbar.update()

            self.figs.append(fig)
            self.axs.append(ax)
            self.lines.append(line)
            self.points.append(pts)
            self.canvases.append(canvas)
            self.toolbars.append(toolbar)
            self._refresh_legend(i)

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

    def _build_statsbar(self):
        bar = tk.Frame(self.root, bg="#0F1820", height=24)
        bar.pack(fill=tk.X, side=tk.BOTTOM)
        bar.pack_propagate(False)

        self._stat_n   = tk.StringVar(value="n=0")
        self._stat_min = tk.StringVar(value="min=--")
        self._stat_max = tk.StringVar(value="max=--")
        self._stat_avg = tk.StringVar(value="avg=--")
        self._stat_std = tk.StringVar(value="σ=--")
        self._stat_dur = tk.StringVar(value="dur=--")

        for var, color in [
            (self._stat_n,   "#CBEE1E"), (self._stat_dur, "#74AEFF"),
            (self._stat_min, "#22C55E"), (self._stat_max, "#EF4444"),
            (self._stat_avg, "#60A5FA"), (self._stat_std, "#A78BFA"),
        ]:
            tk.Label(bar, textvariable=var, bg="#0F1820", fg=color, font=("Consolas", 9)).pack(side=tk.LEFT, padx=10)

        self._sim_lbl = tk.Label(bar, text="", bg="#0F1820", fg="#FBBF24", font=("Consolas", 9, "bold"))
        self._sim_lbl.pack(side=tk.RIGHT, padx=10)

        self._render_lbl = tk.Label(bar, text="", bg="#DAEEFE", fg="#0F4085", font=("Consolas", 8))
        self._render_lbl.pack(side=tk.RIGHT, padx=10)

    def _refresh_legend(self, idx, draggable=True):
        leg = self.axs[idx].legend(loc="best", facecolor="#FFFFFF", edgecolor="#AAAAAA", labelcolor="#222222", fontsize=9, framealpha=0.9)
        if leg and draggable:
            leg.set_draggable(True)

    def _apply_plot_mode(self):
        self._redraw_live(force_all=True)

    def _on_tab_changed(self, event):
        self._redraw_live(force_all=False)
        self._update_latest_label()

    def _get_window(self, tab_idx):
        xs = self.monitor.data_x
        if tab_idx == 0: ys = self.monitor.data_y1
        elif tab_idx == 1: ys = self.monitor.data_y2
        else: ys = self.monitor.data_y3

        n = len(xs)
        raw = self.window_var.get().strip()
        if raw and raw.lower() != "all":
            try:
                w = int(raw)
                if 0 < w < n:
                    xs = arr.array('d', xs[-w:])
                    ys = arr.array('d', ys[-w:])
            except ValueError:
                pass
        return xs, ys

    def _update_stats(self, ys):
        n = len(ys)
        if n == 0:
            for v, t in [(self._stat_n, "n=0"), (self._stat_dur, "dur=0s"), (self._stat_min, "min=--"),
                         (self._stat_max, "max=--"), (self._stat_avg, "avg=--"), (self._stat_std, "σ=--")]:
                v.set(t)
            return

        y_np = np.frombuffer(ys, dtype=np.float64) if isinstance(ys, arr.array) else np.asarray(ys, dtype=np.float64)

        mn, mx, avg, std = float(y_np.min()), float(y_np.max()), float(y_np.mean()), float(y_np.std())
        dur_str = sec_to_mmss(n * self.monitor.sample_sec)

        self._stat_n.set(f"n={n:,}")
        self._stat_dur.set(f"dur={dur_str}")
        self._stat_min.set(f"min={mn:.2f}")
        self._stat_max.set(f"max={mx:.2f}")
        self._stat_avg.set(f"avg={avg:.2f}")
        self._stat_std.set(f"σ={std:.4f}")

    def _update_latest_label(self):
        if not self.monitor.data_x:
            return
        curr_tab = self.notebook.index(self.notebook.select())
        units = ["%", "Raw", "°C"]
        if curr_tab == 0 and len(self.monitor.data_y1): val = self.monitor.data_y1[-1]
        elif curr_tab == 1 and len(self.monitor.data_y2): val = self.monitor.data_y2[-1]
        elif len(self.monitor.data_y3): val = self.monitor.data_y3[-1]
        else: return
        self.latest_var.set(f"Latest: {val:.2f} {units[curr_tab]}")

    def clear_overlays(self):
        for item in self.overlays:
            try: item["line"].remove()
            except Exception: pass
        self.overlays.clear()
        curr_tab = self.notebook.index(self.notebook.select())
        self._refresh_legend(curr_tab)
        self.canvases[curr_tab].draw_idle()
        self.note_var.set("All overlays cleared")

    def remove_last_overlay(self):
        if not self.overlays: return
        item = self.overlays.pop()
        try: item["line"].remove()
        except Exception: pass
        curr_tab = self.notebook.index(self.notebook.select())
        self._refresh_legend(curr_tab)
        self.canvases[curr_tab].draw_idle()
        self.note_var.set(f"Removed: {item['label']}")

    def overlay_csv(self):
        curr_tab = self.notebook.index(self.notebook.select())
        if len(self.overlays) >= MAX_OVERLAYS: return
        path = filedialog.askopenfilename(title="Select CSV exported by this app", filetypes=[("CSV files", "*.csv"), ("All files", "*.*")])
        if not path: return
        try:
            xs, ys = [], []
            col_target = "h2_vol" if curr_tab == 0 else "raw_adc" if curr_tab == 1 else "temp_c"
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        xs.append(float(row["time_sec"]))
                        ys.append(float(row[col_target]))
                    except Exception: continue
            if not xs: raise ValueError(f"No valid data rows found for '{col_target}'.")
            label = os.path.basename(path)
            colors = ["#10B981","#F59E0B","#A855F7","#EF4444","#06B6D4","#84CC16","#E65100","#3B82F6","#EC4899","#64748B"]
            color = colors[len(self.overlays) % len(colors)]
            (ln,) = self.axs[curr_tab].plot(xs, ys, lw=1.6, ls="--", color=color, label=f"Overlay: {label}")
            self.overlays.append({"line": ln, "label": label, "path": path})
            self._refresh_legend(curr_tab)
            self.canvases[curr_tab].draw_idle()
        except Exception as ex:
            messagebox.showerror("Overlay failed", str(ex))

    def apply_title(self):
        t = self.title_var.get().strip() or "TCI Sensor Live Data"
        for ax in self.axs:
            ax.set_title(t, fontsize=12, fontweight="bold", color="#222222")
        curr_tab = self.notebook.index(self.notebook.select())
        self.canvases[curr_tab].draw_idle()

    def apply_sample_interval(self):
        try:
            ms = float(self.sample_var.get())
            if ms <= 0: raise ValueError
        except ValueError:
            self.sample_var.set(str(int(self.monitor.sample_sec * 1000)))
            return
        self.monitor.sample_sec = ms / 1000.0
        self.note_var.set(f"Sample interval → {ms:.0f} ms")
        if self.monitor.data_x:
            n = len(self.monitor.data_x)
            self.monitor.data_x = arr.array('d', (i * self.monitor.sample_sec for i in range(n)))
            self._redraw_live(force_all=True)

    def use_default(self):
        self.monitor.file_path = LOG_FILE_DEFAULT
        self.file_var.set(self.monitor.file_path)

    def load_file(self):
        path = filedialog.askopenfilename(title="Select AML terminal log", filetypes=[("Log/Text files", "*.log *.txt"), ("All files", "*.*")])
        if path:
            self.monitor.file_path = path
            self.file_var.set(path)

    def start(self):
        if (not USE_SIMULATOR) and (not self.monitor.file_path):
            messagebox.showwarning("No file", "Select a log file first (Load… or Default).")
            return
        try:
            ms = float(self.sample_var.get())
            if ms > 0: self.monitor.sample_sec = ms / 1000.0
        except Exception: pass
        self.monitor.start()
        self.status_var.set("● running")
        if USE_SIMULATOR: self._sim_lbl.config(text="[SIMULATOR]")

    def stop(self):
        self.monitor.stop()
        self.status_var.set("⏹ stopped")
        self._sim_lbl.config(text="")

    def manual_reset(self):
        self.monitor.reset_buffers()
        self._last_n = 0
        for i in range(3):
            self.lines[i].set_data([], [])
            self.points[i].set_offsets(np.empty((0, 2)))
            self.axs[i].relim()
            self.axs[i].autoscale_view()
            self.canvases[i].draw_idle()
        self.latest_var.set("Latest: --.-")
        self.note_var.set("Reset: Manual")
        self._update_stats(arr.array('d'))
        self._render_lbl.config(text="")

    def export_csv(self):
        if not self.monitor.data_x: return
        default = f"sensor_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path = filedialog.asksaveasfilename(title="Save CSV", defaultextension=".csv", initialfile=default, filetypes=[("CSV (Excel)", "*.csv")])
        if not path: return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["time_sec", "time_mmss", "h2_vol", "raw_adc", "temp_c"])
                for t, y1, y2, y3 in zip(self.monitor.data_x, self.monitor.data_y1, self.monitor.data_y2, self.monitor.data_y3):
                    w.writerow([f"{t:.3f}", sec_to_mmss(t), f"{y1:.2f}", f"{y2:.2f}", f"{y3:.1f}"])
            self.note_var.set(f"Saved: {os.path.basename(path)}")
        except Exception as ex:
            messagebox.showerror("Export failed", str(ex))

    def save_graph(self):
        curr_tab = self.notebook.index(self.notebook.select())
        names = ["h2vol", "raw_adc", "temp"]
        default = f"plot_{names[curr_tab]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = filedialog.asksaveasfilename(title="Save graph", defaultextension=".png", initialfile=default, filetypes=[("PNG image", "*.png"), ("PDF", "*.pdf")])
        if not path: return
        try:
            self.figs[curr_tab].savefig(path, dpi=300, bbox_inches="tight", facecolor="#FFFFFF")
            self.note_var.set(f"Graph saved: {os.path.basename(path)}")
        except Exception as ex:
            messagebox.showerror("Save failed", str(ex))

    def _handle_monitor_events(self):
        while True:
            try: ev, reason = self.monitor.event_q.get_nowait()
            except Empty: break
            if ev == "RESET": self.manual_reset()

    def _redraw_live(self, force_all=False):
        curr_tab = self.notebook.index(self.notebook.select())
        tabs_to_draw = range(3) if force_all else [curr_tab]
        mode = self.plot_mode_var.get()

        for i in tabs_to_draw:
            xs, ys = self._get_window(i)
            n = len(xs)
            if n == 0: continue

            xd, yd = _decimate(xs, ys, MAX_RENDER_PTS)
            nd = len(xd)

            if mode in ("line+dots", "line"):
                self.lines[i].set_data(xd, yd)
                self.lines[i].set_visible(True)
            else:
                self.lines[i].set_visible(False)

            want_dots = mode in ("line+dots", "dots")
            if want_dots and n <= SCATTER_LIMIT:
                self.points[i].set_visible(True)
                self.points[i].set_offsets(np.column_stack([np.asarray(xd), np.asarray(yd)]))
            else:
                self.points[i].set_visible(False)

            if self.autoscale_var.get():
                y_min, y_max = np.min(yd), np.max(yd)
                margin = max((y_max - y_min) * 0.08, 0.05)
                new_lo, new_hi = y_min - margin, y_max + margin
                cur_lo, cur_hi = self.axs[i].get_ylim()

                if abs(new_lo - cur_lo) > 0.005 or abs(new_hi - cur_hi) > 0.005:
                    self.axs[i].set_ylim(new_lo, new_hi)

                x_max = np.max(xd)
                cur_xl, cur_xr = self.axs[i].get_xlim()
                if x_max > cur_xr * 0.98 or x_max < cur_xl:
                    self.axs[i].set_xlim(0, x_max * 1.04)

            self.canvases[i].draw_idle()

        # Update stats bar only for visible tab
        _, curr_ys = self._get_window(curr_tab)
        self._update_stats(curr_ys)

        total_n = len(self.monitor.data_x)
        self._render_lbl.config(text=f"By Ishan. (rendering {total_n:,} pts)")

    def update_plot(self):
        self._handle_monitor_events()

        got = 0
        while True:
            try:
                t, y1, y2, y3 = self.monitor.queue.get_nowait()
            except Empty:
                break
            self.monitor.data_x.append(t)
            self.monitor.data_y1.append(y1)
            self.monitor.data_y2.append(y2)
            self.monitor.data_y3.append(y3)
            got += 1

        if got > 0:
            self._redraw_live(force_all=False)
            self._update_latest_label()
            self._last_n += got

        self.root.after(PLOT_REFRESH_MS, self.update_plot)


if __name__ == "__main__":
    root = tk.Tk()
    app  = LivePlotterApp(root)
    root.mainloop()