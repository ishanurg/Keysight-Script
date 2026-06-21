import sys
import os
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import math
import csv
import pyvisa
import queue
import numpy as np
import pandas as pd

# PyQtGraph with OpenGL Hardware Acceleration
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore

pg.setConfigOptions(useOpenGL=True, antialias=True)

# ==============================================================================
# 1. UI THEME ARCHITECTURE
# ==============================================================================
class Theme:
    BG    = '#0f172a'
    PNL   = '#1e293b'
    PNL2  = '#334155'
    ACC   = '#3b82f6'
    ACC_H = '#2563eb'
    ERR   = '#ef4444'
    FG    = '#f8fafc'
    DIM   = '#94a3b8'

def set_hd_resolution():
    """Forces Windows to render Tkinter in crisp High-DPI."""
    if sys.platform == 'win32':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

# ==============================================================================
# 2. MAIN APPLICATION CLASS
# ==============================================================================
class B2910CL_MasterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Keysight B2910CL HD Master Controller")
        self.root.geometry("1400x850")
        self.root.configure(bg=Theme.BG)
        
        self.rm = pyvisa.ResourceManager()
        self.smu = None
        self.is_running = False
        self.data_queue = queue.Queue()

        self.apply_styles()
        self.build_gui()
        self.scan_ports()

    def apply_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=Theme.BG)
        style.configure('Panel.TFrame', background=Theme.PNL)
        style.configure('TLabel', background=Theme.PNL, foreground=Theme.FG, font=('Segoe UI', 11))
        style.configure('Header.TLabel', font=('Segoe UI', 14, 'bold'))
        
        style.configure('TNotebook', background=Theme.BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=Theme.PNL2, foreground=Theme.FG, 
                        padding=[20, 10], font=('Segoe UI', 11, 'bold'))
        style.map('TNotebook.Tab', background=[('selected', Theme.ACC)])
        
        style.configure('TButton', background=Theme.PNL2, foreground=Theme.FG, font=('Segoe UI', 11, 'bold'))
        style.map('TButton', background=[('active', Theme.ACC)])
        style.configure('Action.TButton', background=Theme.ACC, padding=10)

    def build_gui(self):
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        # --- LEFT SIDEBAR (Connection & Execution) ---
        sidebar = ttk.Frame(self.root, style='Panel.TFrame', padding=20)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ttk.Label(sidebar, text="HARDWARE SETUP", style='Header.TLabel').pack(anchor="w", pady=(0, 10))
        self.visa_combo = ttk.Combobox(sidebar, width=30, font=('Segoe UI', 10))
        self.visa_combo.pack(fill="x", pady=5)
        
        btn_frame = ttk.Frame(sidebar, style='Panel.TFrame')
        btn_frame.pack(fill="x", pady=10)
        ttk.Button(btn_frame, text="Scan USB", command=self.scan_ports).pack(side="left", expand=True, fill="x", padx=(0,5))
        self.btn_conn = ttk.Button(btn_frame, text="Connect", command=self.connect_smu)
        self.btn_conn.pack(side="left", expand=True, fill="x", padx=(5,0))

        self.lbl_status = ttk.Label(sidebar, text="Status: Offline", foreground=Theme.ERR)
        self.lbl_status.pack(anchor="w", pady=10)

        ttk.Label(sidebar, text="EXECUTION ENGINE", style='Header.TLabel').pack(anchor="w", pady=(40, 10))
        self.btn_start = ttk.Button(sidebar, text="START TEST", style='Action.TButton', command=self.start_test)
        self.btn_start.pack(fill="x", pady=10)
        self.btn_stop = ttk.Button(sidebar, text="EMERGENCY STOP", command=self.stop_test)
        self.btn_stop.pack(fill="x", pady=5)

        # --- RIGHT PANEL (Tabs) ---
        self.tabs = ttk.Notebook(self.root)
        self.tabs.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)

        self.tab_config = ttk.Frame(self.tabs, style='Panel.TFrame')
        self.tab_live = ttk.Frame(self.tabs, style='Panel.TFrame')
        self.tab_viewer = ttk.Frame(self.tabs, style='Panel.TFrame')

        self.tabs.add(self.tab_config, text="⚙️ Test Configuration")
        self.tabs.add(self.tab_live, text="📈 Live Hardware Plot")
        self.tabs.add(self.tab_viewer, text="📂 Offline CSV Viewer")

        self.build_config_tab()
        self.build_plot_tabs()

    def browse_save_location(self):
        """Opens a file dialog to choose where the CSV will be saved."""
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV Data Files", "*.csv"), ("All Files", "*.*")],
            title="Choose Save Location",
            initialfile="B2910CL_Data.csv"
        )
        if path:  # If the user didn't click Cancel
            self.save_var.set(path)

    def build_config_tab(self):
        grid_frame = ttk.Frame(self.tab_config, style='Panel.TFrame', padding=30)
        grid_frame.pack(fill="both", expand=True)

        # Variables
        self.src_mode_var = tk.StringVar(value="Current (A)")
        self.shape_var    = tk.StringVar(value="Sine Wave")
        self.min_val_var  = tk.StringVar(value="0.005")
        self.max_val_var  = tk.StringVar(value="0.040")
        self.comp_var     = tk.StringVar(value="10.0")
        
        self.period_var   = tk.StringVar(value="4.0")
        self.points_var   = tk.StringVar(value="360")
        self.total_t_var  = tk.StringVar(value="12.0")
        
        self.aperture_var = tk.StringVar(value="Auto")
        self.wire_var     = tk.BooleanVar(value=False)
        
        # Default save path inside the running folder
        default_save = os.path.join(os.path.dirname(os.path.abspath(__file__)), "B2910CL_Data.csv")
        self.save_var = tk.StringVar(value=default_save)

        # File browse frame setup
        save_frame = ttk.Frame(grid_frame, style='Panel.TFrame')
        ttk.Entry(save_frame, textvariable=self.save_var, width=50).pack(side="left", fill="x", expand=True)
        ttk.Button(save_frame, text="Browse...", command=self.browse_save_location, width=10).pack(side="left", padx=(10, 0))

        # Layout Design
        params = [
            ("Output Force Mode:", ttk.Combobox(grid_frame, textvariable=self.src_mode_var, values=["Current (A)", "Voltage (V)", "DC Hold"])),
            ("Waveform Shape:", ttk.Combobox(grid_frame, textvariable=self.shape_var, values=["Sine Wave", "Cosine Wave", "Square (Pulse)", "Triangle", "Staircase", "DC Hold"])),
            ("Base/Min Level:", ttk.Entry(grid_frame, textvariable=self.min_val_var)),
            ("Peak/Max Level:", ttk.Entry(grid_frame, textvariable=self.max_val_var)),
            ("Compliance Limit:", ttk.Entry(grid_frame, textvariable=self.comp_var)),
            ("---", None),
            ("Cycle Period (s):", ttk.Entry(grid_frame, textvariable=self.period_var)),
            ("Resolution (Points/Cycle):", ttk.Entry(grid_frame, textvariable=self.points_var)),
            ("Total Test Duration (s):", ttk.Entry(grid_frame, textvariable=self.total_t_var)),
            ("---", None),
            ("Aperture (Integration) Time:", ttk.Combobox(grid_frame, textvariable=self.aperture_var, values=["Auto", "1e-5 (10 µs Limit)"])),
            ("4-Wire Kelvin Sensing:", ttk.Checkbutton(grid_frame, text="Enable Remote Sensing", variable=self.wire_var)),
            ("Save File Path (.csv):", save_frame),
        ]

        for i, (label, widget) in enumerate(params):
            if widget is None:
                ttk.Separator(grid_frame, orient="horizontal").grid(row=i, column=0, columnspan=2, sticky="ew", pady=15)
            else:
                ttk.Label(grid_frame, text=label, font=('Segoe UI', 11, 'bold')).grid(row=i, column=0, sticky="e", padx=20, pady=8)
                widget.grid(row=i, column=1, sticky="w", pady=8)

    def build_plot_tabs(self):
        # 1. Live Plot Setup (Tkinter Frame housing PyQtGraph)
        self.live_tk_frame = tk.Frame(self.tab_live, bg=Theme.PNL)
        self.live_tk_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.live_glw = pg.GraphicsLayoutWidget()
        self.live_glw.setBackground(Theme.PNL)
        self.p_src = self.live_glw.addPlot(row=0, col=0, title="Sourced Signal")
        self.p_msr = self.live_glw.addPlot(row=1, col=0, title="Measured Response")
        
        for p in [self.p_src, self.p_msr]:
            p.showGrid(x=True, y=True, alpha=0.3)
            p.getAxis('left').setPen(Theme.FG)
            p.getAxis('bottom').setPen(Theme.FG)

        self.curve_src = self.p_src.plot(pen=pg.mkPen(Theme.ACC, width=2))
        self.curve_msr = self.p_msr.plot(pen=pg.mkPen(Theme.ERR, width=2))

        # 2. Offline Viewer Setup
        ttk.Button(self.tab_viewer, text="📂 Load CSV Data", command=self.load_csv).pack(pady=10)
        self.view_tk_frame = tk.Frame(self.tab_viewer, bg=Theme.PNL)
        self.view_tk_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self.view_glw = pg.GraphicsLayoutWidget()
        self.view_glw.setBackground(Theme.PNL)
        self.vp_src = self.view_glw.addPlot(row=0, col=0, title="Historical Source")
        self.vp_msr = self.view_glw.addPlot(row=1, col=0, title="Historical Measure")
        
        for p in [self.vp_src, self.vp_msr]:
            p.showGrid(x=True, y=True, alpha=0.3)
            p.getAxis('left').setPen(Theme.FG)
            p.getAxis('bottom').setPen(Theme.FG)

        self.vcurve_src = self.vp_src.plot(pen=pg.mkPen(Theme.ACC, width=2))
        self.vcurve_msr = self.vp_msr.plot(pen=pg.mkPen(Theme.ERR, width=2))

        # Embed Qt Widgets into Tkinter safely
        self.embed_qt_widget(self.live_glw, self.live_tk_frame)
        self.embed_qt_widget(self.view_glw, self.view_tk_frame)

    def embed_qt_widget(self, qt_widget, tk_frame):
        """Cross-platform trick to embed Qt window natively into Tkinter frame with 64-bit safe ctypes."""
        qt_widget.show()
        if sys.platform == 'win32':
            tk_hwnd = wintypes.HWND(tk_frame.winfo_id())
            qt_hwnd = wintypes.HWND(int(qt_widget.winId()))
            
            # Reparent window
            ctypes.windll.user32.SetParent(qt_hwnd, tk_hwnd)
            
            # Remove pop-up styling, set to standard child
            GWL_STYLE = -16
            WS_CHILD = 0x40000000
            WS_VISIBLE = 0x10000000
            
            user32 = ctypes.windll.user32
            
            # 64-BIT SAFE CTYPES DEFINITIONS
            if ctypes.sizeof(ctypes.c_void_p) == 8:
                GetWindowLong = user32.GetWindowLongPtrW
                GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
                GetWindowLong.restype = ctypes.c_ssize_t
                
                SetWindowLong = user32.SetWindowLongPtrW
                SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
                SetWindowLong.restype = ctypes.c_ssize_t
            else:
                GetWindowLong = user32.GetWindowLongW
                GetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int]
                GetWindowLong.restype = ctypes.c_long
                
                SetWindowLong = user32.SetWindowLongW
                SetWindowLong.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
                SetWindowLong.restype = ctypes.c_long

            style = GetWindowLong(qt_hwnd, GWL_STYLE)
            style = (style & ~0x80000000) | WS_CHILD | WS_VISIBLE
            SetWindowLong(qt_hwnd, GWL_STYLE, style)

            # Keep resizing synced between Tkinter and Qt
            def on_resize(e):
                qt_widget.resize(e.width, e.height)
            tk_frame.bind("<Configure>", on_resize)

    # ==============================================================================
    # 3. HARDWARE CONTROL & SCPI ENGINE
    # ==============================================================================
    def scan_ports(self):
        ports = self.rm.list_resources()
        self.visa_combo['values'] = ports
        if ports:
            self.visa_combo.set(ports[0])

    def connect_smu(self):
        try:
            self.smu = self.rm.open_resource(self.visa_combo.get())
            self.smu.timeout = 10000
            idn = self.smu.query("*IDN?").strip()
            self.lbl_status.config(text=f"Online: {idn.split(',')[1]}", foreground="#22c55e")
            self.btn_conn.config(state="disabled")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def stop_test(self):
        self.is_running = False
        if self.smu:
            try:
                self.smu.write(":OUTP OFF")
                self.lbl_status.config(text="Status: KILLED (Output Off)", foreground=Theme.ERR)
            except: pass

    def start_test(self):
        if not self.smu:
            messagebox.showwarning("Offline", "Please connect to the instrument.")
            return
        
        # Make sure file path is valid before starting
        save_file = self.save_var.get()
        if not save_file:
            messagebox.showerror("Error", "Please select a valid Save File Path.")
            return

        self.is_running = True
        self.btn_start.config(state="disabled", text="TEST RUNNING...")
        self.tabs.select(self.tab_live)

        # Clear historical plotting arrays
        self.plot_t, self.plot_src, self.plot_msr = [], [], []

        # Update Plot Titles dynamically
        if "Current" in self.src_mode_var.get():
            self.p_src.setTitle("Sourced Signal (Current)")
            self.p_msr.setTitle("Measured Response (Voltage)")
        else:
            self.p_src.setTitle("Sourced Signal (Voltage)")
            self.p_msr.setTitle("Measured Response (Current)")

        # Launch hardware communication on background thread so GUI doesn't freeze
        threading.Thread(target=self._hardware_thread, daemon=True).start()
        
        # Start GUI queue listener
        self.root.after(50, self._gui_queue_processor)

    def _hardware_thread(self):
        try:
            # 1. Read Setup Variables
            mode_is_curr = "Current" in self.src_mode_var.get()
            base = float(self.min_val_var.get())
            peak = float(self.max_val_var.get())
            comp = float(self.comp_var.get())
            period = float(self.period_var.get())
            pts = int(self.points_var.get())
            total_time = float(self.total_t_var.get())
            
            # Math Generator for Arbitrary Waveforms
            step_time = period / pts
            amp, off = (peak - base) / 2.0, (peak + base) / 2.0
            list_vals = []
            
            shape = self.shape_var.get()
            for tick in range(pts):
                t = tick * step_time
                if "Sine" in shape:    val = off - amp * math.cos(2 * math.pi * (t / period))
                elif "Cosine" in shape:val = off + amp * math.cos(2 * math.pi * (t / period))
                elif "Pulse" in shape: val = base if tick < (pts / 2) else peak
                elif "Triangle" in shape:
                    if tick < pts/2: val = base + (peak - base) * (tick / (pts/2))
                    else:            val = peak - (peak - base) * ((tick - pts/2) / (pts/2))
                elif "Staircase" in shape: val = base + (peak - base) * (tick / pts)
                else: val = peak
                list_vals.append(round(val, 6))

            # 2. Hardware SCPI Config
            self.smu.write("*RST")
            self.smu.write("*CLS")
            
            self.smu.write(f":SENS:REMO {'ON' if self.wire_var.get() else 'OFF'}")
            
            src_str = "CURR" if mode_is_curr else "VOLT"
            msr_str = "VOLT" if mode_is_curr else "CURR"
            
            self.smu.write(f":SOUR:FUNC:MODE {src_str}")
            self.smu.write(f":SOUR:{src_str}:MODE LIST")
            self.smu.write(f":SOUR:{src_str}:RANG {max(abs(base), abs(peak))}")
            self.smu.write(f":SOUR:LIST:{src_str} {','.join(map(str, list_vals))}")
            
            self.smu.write(":SENS:FUNC \"VOLT\",\"CURR\"")
            self.smu.write(f":SENS:{msr_str}:PROT {comp}")
            
            # Integration Limit checking
            ap_val = step_time * 0.5 if self.aperture_var.get() == "Auto" else 1e-5
            self.smu.write(f":SENS:VOLT:APER {ap_val}")
            self.smu.write(f":SENS:CURR:APER {ap_val}")

            # 3. Chunking Logic (Saves memory & ensures infinite stream)
            cycles_per_chunk = max(1, int(1.0 / period))
            ticks_per_chunk = cycles_per_chunk * pts
            total_ticks = int(total_time / step_time)
            num_chunks = math.ceil(total_ticks / ticks_per_chunk)

            self.smu.write(":TRIG:TRAN:SOUR TIM")
            self.smu.write(f":TRIG:TRAN:TIM {step_time}")
            self.smu.write(":TRIG:ACQ:SOUR TIM")
            self.smu.write(f":TRIG:ACQ:TIM {step_time}")
            self.smu.write(":FORM:DATA ASC")

            # Initialize Save File Headers
            save_file = self.save_var.get()
            with open(save_file, 'w', newline='') as f:
                csv.writer(f).writerow(["Relative Time (s)", f"Sourced ({src_str})", f"Measured ({msr_str})"])

            self.smu.write(":OUTP ON")
            global_t = 0.0

            # 4. Main Execution Loop
            for chunk in range(num_chunks):
                if not self.is_running: break
                
                t_count = min(ticks_per_chunk, total_ticks - chunk * ticks_per_chunk)
                self.smu.write(f":TRIG:TRAN:COUN {t_count}")
                self.smu.write(f":TRIG:ACQ:COUN {t_count}")
                
                self.smu.write(":INIT:ACQ")
                self.smu.write(":INIT:TRAN")
                
                # Dynamic timeout handling for massive chunks
                self.smu.timeout = int(((t_count * step_time) + 10) * 1000)
                self.smu.write("*WAI")
                
                t = self.smu.query_ascii_values(":FETC:ARR:TIME?")
                c = self.smu.query_ascii_values(":FETC:ARR:CURR?")
                v = self.smu.query_ascii_values(":FETC:ARR:VOLT?")
                
                t_rel = [x + global_t for x in t]
                src_data = c if mode_is_curr else v
                msr_data = v if mode_is_curr else c
                
                # Instantly append to file
                with open(save_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    for tt, ss, mm in zip(t_rel, src_data, msr_data):
                        writer.writerow([tt, ss, mm])
                
                # Send to GUI thread for live rendering
                self.data_queue.put((t_rel, src_data, msr_data))
                global_t += (t_count * step_time)

            self.smu.write(":OUTP OFF")
            
        except Exception as e:
            self.data_queue.put(Exception(str(e)))
        finally:
            self.is_running = False

    def _gui_queue_processor(self):
        """Processes the hardware data buffer into the PyQtGraph instantly."""
        try:
            while True:
                data = self.data_queue.get_nowait()
                if isinstance(data, Exception):
                    messagebox.showerror("Hardware Error", str(data))
                    break
                
                t, src, msr = data
                self.plot_t.extend(t)
                self.plot_src.extend(src)
                self.plot_msr.extend(msr)
                
                # Fast NumPy update for OpenGL Qt Render
                self.curve_src.setData(np.array(self.plot_t), np.array(self.plot_src))
                self.curve_msr.setData(np.array(self.plot_t), np.array(self.plot_msr))
                
        except queue.Empty:
            pass

        if self.is_running:
            self.root.after(30, self._gui_queue_processor)
        else:
            self.btn_start.config(state="normal", text="START TEST")
            self.lbl_status.config(text="Test Complete. Output Off.", foreground="#22c55e")

    # ==============================================================================
    # 4. OFFLINE DATA VIEWER
    # ==============================================================================
    def load_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV Data", "*.csv")])
        if path:
            try:
                df = pd.read_csv(path)
                t = df.iloc[:, 0].values
                src = df.iloc[:, 1].values
                msr = df.iloc[:, 2].values
                
                self.vcurve_src.setData(t, src)
                self.vcurve_msr.setData(t, msr)
                
                # Update viewer titles based on CSV headers
                self.vp_src.setTitle(df.columns[1])
                self.vp_msr.setTitle(df.columns[2])
                
                self.tabs.select(self.tab_viewer)
            except Exception as e:
                messagebox.showerror("Error Loading CSV", str(e))

# ==============================================================================
# 5. BOOTSTRAP: EVENT LOOP BRIDGE
# ==============================================================================
if __name__ == "__main__":
    set_hd_resolution()
    
    # 1. Initialize Qt Application in the background
    qt_app = QtWidgets.QApplication.instance()
    if qt_app is None:
        qt_app = QtWidgets.QApplication(sys.argv)
        
    # 2. Initialize Tkinter Window
    root = tk.Tk()
    app = B2910CL_MasterApp(root)
    
    # 3. Bridge the two event loops seamlessly
    def qt_loop_pump():
        qt_app.processEvents()
        root.after(10, qt_loop_pump)
        
    qt_loop_pump()
    root.mainloop()