import sys
import os
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import numpy as np
import pandas as pd
import math
import threading
import queue
import pyvisa
import csv
import time

# PyQtGraph with OpenGL Hardware Acceleration
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore

pg.setConfigOptions(useOpenGL=True, antialias=True)

# ------------------------------------------------------------------------
# 1. Global Theme Architecture
# ------------------------------------------------------------------------
class Theme:
    BG   = '#f4f6fb'
    PNL  = '#ffffff'
    PNL2 = '#eef1f8'
    ACC  = '#2563eb'
    FG   = '#1e293b'
    DIM  = '#64748b'
    BRD  = '#cbd5e1'
    SEP  = '#e2e8f0'
    CV_BG= '#f8fafc'
    
    C_HL   = '#dc2626'
    C_MARK = '#7c3aed'
    
    ERR    = '#ef4444' 
    ACC_H  = '#2563eb'
    
    is_dark = False

    LIGHT_TO_DARK = {
        '#f4f6fb': '#0f172a', '#ffffff': '#1e293b', '#eef1f8': '#334155',
        '#1e293b': '#f8fafc', '#64748b': '#94a3b8', '#cbd5e1': '#475569', 
        '#e2e8f0': '#334155', '#f8fafc': '#020617'
    }
    DARK_TO_LIGHT = {v: k for k, v in LIGHT_TO_DARK.items()}

    @classmethod
    def toggle(cls):
        cls.is_dark = not cls.is_dark
        if cls.is_dark:
            cls.BG, cls.PNL, cls.PNL2 = '#0f172a', '#1e293b', '#334155'
            cls.FG, cls.DIM = '#f8fafc', '#94a3b8'
            cls.BRD, cls.SEP = '#475569', '#334155'
            cls.CV_BG = '#020617'
        else:
            cls.BG, cls.PNL, cls.PNL2 = '#f4f6fb', '#ffffff', '#eef1f8'
            cls.FG, cls.DIM = '#1e293b', '#64748b'
            cls.BRD, cls.SEP = '#cbd5e1', '#e2e8f0'
            cls.CV_BG = '#f8fafc'

TRACE_COLORS = ['#2563eb', '#10b981', '#f59e0b', '#dc2626', '#7c3aed', '#db2777', '#06b6d4', '#059669']

def set_hd_resolution():
    if sys.platform == 'win32':
        try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception: pass

# ------------------------------------------------------------------------
# 2. Smooth Scrollable Frame Utility
# ------------------------------------------------------------------------
class VerticalScrollFrame(ttk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.canvas = tk.Canvas(self, bg=Theme.PNL, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=Theme.PNL)

        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.window, width=e.width))

        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        x, y = self.canvas.winfo_pointerxy()
        widget = self.canvas.winfo_containing(x, y)
        if widget and str(widget).startswith(str(self.canvas)):
            self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

# ------------------------------------------------------------------------
# 3. Chart Properties & Analytics Classes
# ------------------------------------------------------------------------
class ChartPropertiesDialog(tk.Toplevel):
    def __init__(self, parent, chart_obj, chart_key, callback):
        super().__init__(parent)
        self.title(f"Chart Properties - {chart_obj.title}")
        self.geometry("450x550")
        self.configure(bg=Theme.BG)
        self.transient(parent)
        self.grab_set()

        self.chart = chart_obj
        self.chart_key = chart_key
        self.callback = callback
        self.trace_entries = {}
        self._build_ui()

    def _build_ui(self):
        container = tk.Frame(self, bg=Theme.PNL, highlightthickness=1, highlightbackground=Theme.BRD)
        container.pack(fill='both', expand=True, padx=8, pady=8)

        lbl_frm = tk.LabelFrame(container, text=" Axis Labels & Titles ", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 9, 'bold'))
        lbl_frm.pack(fill='x', padx=8, pady=8)

        tk.Label(lbl_frm, text="Chart Title:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=0, column=0, padx=4, pady=4, sticky='e')
        self.ent_title = tk.Entry(lbl_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=25, font=('Segoe UI', 8))
        self.ent_title.insert(0, self.chart.title)
        self.ent_title.grid(row=0, column=1, padx=4, pady=4)

        tk.Label(lbl_frm, text="X-Axis Label:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=1, column=0, padx=4, pady=4, sticky='e')
        self.ent_xlabel = tk.Entry(lbl_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=25, font=('Segoe UI', 8))
        self.ent_xlabel.insert(0, self.chart.x_label)
        self.ent_xlabel.grid(row=1, column=1, padx=4, pady=4)

        tk.Label(lbl_frm, text="Y-Axis Label:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=2, column=0, padx=4, pady=4, sticky='e')
        self.ent_ylabel = tk.Entry(lbl_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=25, font=('Segoe UI', 8))
        self.ent_ylabel.insert(0, self.chart.y_label)
        self.ent_ylabel.grid(row=2, column=1, padx=4, pady=4)

        scale_frm = tk.LabelFrame(container, text=" Fixed Y-Axis Scale Bounds ", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 9, 'bold'))
        scale_frm.pack(fill='x', padx=8, pady=4)

        tk.Label(scale_frm, text="Y-Min:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=0, column=0, padx=4, pady=4, sticky='e')
        self.ent_ymin = tk.Entry(scale_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=12, font=('Segoe UI', 8))
        if self.chart.y_min_override is not None: self.ent_ymin.insert(0, str(self.chart.y_min_override))
        self.ent_ymin.grid(row=0, column=1, padx=4, pady=4)

        tk.Label(scale_frm, text="Y-Max:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=0, column=2, padx=4, pady=4, sticky='e')
        self.ent_ymax = tk.Entry(scale_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=12, font=('Segoe UI', 8))
        if self.chart.y_max_override is not None: self.ent_ymax.insert(0, str(self.chart.y_max_override))
        self.ent_ymax.grid(row=0, column=3, padx=4, pady=4)

        trace_frm = tk.LabelFrame(container, text=" Edit Trace Names (Legend) ", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 9, 'bold'))
        trace_frm.pack(fill='both', expand=True, padx=8, pady=8)

        cv = tk.Canvas(trace_frm, bg=Theme.PNL, highlightthickness=0)
        vsb = ttk.Scrollbar(trace_frm, orient="vertical", command=cv.yview)
        tr_container = tk.Frame(cv, bg=Theme.PNL)
        
        tr_container.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=tr_container, anchor="nw")
        cv.configure(yscrollcommand=vsb.set)
        cv.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        row_idx = 0
        for group in [self.chart.datasets, self.chart.analysis_layers]:
            for t_id, trace in group.items():
                col_box = tk.Label(tr_container, bg=trace["color"], width=3)
                col_box.grid(row=row_idx, column=0, padx=4, pady=3)
                
                tk.Label(tr_container, text=f"ID: {t_id[:12]}...", bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 8)).grid(row=row_idx, column=1, padx=4, sticky='w')
                
                ent_name = tk.Entry(tr_container, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=20, font=('Segoe UI', 8))
                ent_name.insert(0, trace.get("trace_name", t_id))
                ent_name.grid(row=row_idx, column=2, padx=4, pady=3)
                
                self.trace_entries[t_id] = ent_name
                row_idx += 1

        btn_frm = tk.Frame(container, bg=Theme.PNL)
        btn_frm.pack(fill='x', padx=8, pady=8)

        tk.Button(btn_frm, text="Apply Properties", bg=Theme.ACC, fg='#ffffff', font=('Segoe UI', 9, 'bold'), relief='flat', padx=10, pady=3, command=self._apply).pack(side='right', padx=4)
        tk.Button(btn_frm, text="Cancel", bg=Theme.PNL2, fg=Theme.FG, font=('Segoe UI', 9), relief='flat', padx=10, pady=3, command=self.destroy).pack(side='right', padx=4)

    def _apply(self):
        try:
            y_min = float(self.ent_ymin.get()) if self.ent_ymin.get().strip() else None
            y_max = float(self.ent_ymax.get()) if self.ent_ymax.get().strip() else None
        except ValueError:
            messagebox.showerror("Scale Error", "Y-Axis Min/Max must be valid numbers.")
            return

        props = {"title": self.ent_title.get().strip(), "x_label": self.ent_xlabel.get().strip(), "y_label": self.ent_ylabel.get().strip(), "y_min": y_min, "y_max": y_max}
        trace_names = {t_id: ent.get().strip() for t_id, ent in self.trace_entries.items()}
        self.callback(self.chart_key, props, trace_names)
        self.destroy()

class ListboxTooltip:
    def __init__(self, listbox, get_data_func):
        self.listbox = listbox
        self.get_data = get_data_func
        self.tw = None
        self.current_idx = None
        self.listbox.bind("<Motion>", self.on_motion)
        self.listbox.bind("<Leave>", self.hide_tooltip)

    def on_motion(self, event):
        idx = self.listbox.nearest(event.y)
        bbox = self.listbox.bbox(idx)
        if bbox and bbox[1] <= event.y <= bbox[1] + bbox[3]:
            if self.current_idx == idx: return
            self.current_idx = idx
            data = self.get_data(idx)
            if data:
                text = f"Trace: {data.get('trace_name', 'Unknown')}\nX: {data.get('x_col', 'N/A')} | Y: {data.get('y_col', 'N/A')}"
                self.show_tooltip(event, text)
            else: self.hide_tooltip()
        else: self.hide_tooltip()

    def show_tooltip(self, event, text):
        if self.tw: self.hide_tooltip()
        x = self.listbox.winfo_rootx() + event.x + 20
        y = self.listbox.winfo_rooty() + event.y + 10
        self.tw = tk.Toplevel(self.listbox)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        tk.Label(self.tw, text=text, bg=Theme.PNL2, fg=Theme.FG, relief='solid', borderwidth=1, font=("Segoe UI", 8)).pack(padx=4, pady=2)

    def hide_tooltip(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None
        self.current_idx = None

class MathEngine:
    @staticmethod
    def compute_derivative(x, y):
        if len(x) < 2: return x, y
        dx = np.diff(x)
        dy = np.diff(y)
        dx[dx == 0] = 1e-12 
        return x[:-1], dy / dx

    @staticmethod
    def compute_integral(x, y):
        if len(x) < 2: return x, np.zeros_like(y)
        dx = np.diff(x)
        cumulative_sum = np.cumsum(0.5 * (y[:-1] + y[1:]) * dx)
        integral = np.zeros(len(x))
        integral[1:] = cumulative_sum
        return x, integral

class AdvancedAnalysisCanvas:
    MAX_DRAW_PTS = 4000  

    def __init__(self, parent, chart_key, on_view_changed_callback=None, on_edit_request_callback=None, title=""):
        self._frame = tk.Frame(parent, bg=Theme.BG)
        self.canvas = tk.Canvas(self._frame, bg=Theme.CV_BG, highlightthickness=1, highlightbackground=Theme.BRD)
        self.canvas.pack(fill='both', expand=True)
        
        self.chart_key = chart_key
        self.title = title
        self.x_label, self.y_label = "", ""

        self.w = self.h = 0
        self.cw = self.ch = 1
        self.pad_l, self.pad_r = 80, 20
        self.pad_t = 35 if title else 25
        self.pad_b = 50  
        self.num_grid = 5

        self.datasets, self.analysis_layers, self.labels = {}, {}, []
        self.view_xmin = self.view_xmax = 0.0
        self.view_ymin = self.view_ymax = 0.0
        self.y_min_override = self.y_max_override = None

        self.on_view_changed = on_view_changed_callback
        self.on_edit_request = on_edit_request_callback

        self._last_mx = self._last_my = None
        self.marker_mode = self.label_drop_mode = False
        self.next_label_text = ""
        self.m1 = self.m2 = None

        self._apply_event_bindings()
        self._create_interactive_overlays()

    def _apply_event_bindings(self):
        self.canvas.bind('<Configure>', self._on_resize)
        self.canvas.bind('<Motion>', self._on_hover)
        self.canvas.bind('<Leave>', self._on_mouse_leave)
        self.canvas.bind('<ButtonPress-1>', self._on_mouse_down)
        self.canvas.bind('<B1-Motion>', self._on_mouse_drag)
        self.canvas.bind('<MouseWheel>', self._on_mouse_wheel)
        self.canvas.bind('<Button-4>', self._on_mouse_wheel)
        self.canvas.bind('<Button-5>', self._on_mouse_wheel)
        self.canvas.bind('<Button-3>', self._show_context_menu)
        self.canvas.bind('<Button-2>', self._show_context_menu)
        
        self.canvas.bind('<Left>', lambda e: self.execute_pan('left'))
        self.canvas.bind('<Right>', lambda e: self.execute_pan('right'))
        self.canvas.bind('<Up>', lambda e: self.execute_pan('up'))
        self.canvas.bind('<Down>', lambda e: self.execute_pan('down'))

    def _show_context_menu(self, e):
        self.canvas.focus_set()
        menu = tk.Menu(self.canvas, tearoff=0, bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9))
        if self.on_edit_request:
            menu.add_command(label="⚙ Properties (Title, Axes, Scale)", command=lambda: self.on_edit_request(self))
            menu.add_separator()
        menu.add_command(label="↺ Auto-Fit Bounds", command=self.reset_global_viewport)
        menu.add_command(label="🗑 Clear Markers & Pins", command=self._clear_annotations)
        menu.tk_popup(e.x_root, e.y_root)

    def _clear_annotations(self):
        self.labels.clear(); self.m1 = self.m2 = None; self.redraw()

    def _create_interactive_overlays(self):
        self.vl = self.canvas.create_line(0,0,0,0, fill=Theme.C_HL, dash=(3,3), state='hidden', tags='hover')
        self.hl = self.canvas.create_line(0,0,0,0, fill=Theme.C_HL, dash=(3,3), state='hidden', tags='hover')
        self.tt_bg = self.canvas.create_rectangle(0,0,0,0, fill='#1e293b', outline=Theme.BRD, state='hidden', tags='hover')
        self.tt_txt = self.canvas.create_text(0,0, text='', anchor='nw', fill='#ffffff', font=('Segoe UI', 9, 'bold'), state='hidden', tags='hover')

    def register_dataset(self, d_id, x, y, color, style="Solid", trace_name=""):
        self.datasets[d_id] = {"x": np.asarray(x, dtype=float), "y": np.asarray(y, dtype=float), "color": color, "style": style, "trace_name": trace_name or d_id}

    def add_analysis_trace(self, t_id, x, y, color, style="Dashed", trace_name=""):
        self.analysis_layers[t_id] = {"x": np.asarray(x, dtype=float), "y": np.asarray(y, dtype=float), "color": color, "style": style, "trace_name": trace_name}

    def reset_global_viewport(self):
        if not self.datasets and not self.analysis_layers:
            self.view_xmin, self.view_xmax = 0.0, 1.0
            self.view_ymin, self.view_ymax = 0.0, 1.0
            self.redraw()
            return
        
        all_xmin, all_xmax, all_ymin, all_ymax = np.inf, -np.inf, np.inf, -np.inf

        for layer in [self.datasets, self.analysis_layers]:
            for d in layer.values():
                if len(d["x"]) == 0: continue
                all_xmin, all_xmax = min(all_xmin, d["x"].min()), max(all_xmax, d["x"].max())
                all_ymin, all_ymax = min(all_ymin, d["y"].min()), max(all_ymax, d["y"].max())

        if all_xmin == np.inf: 
            self.view_xmin, self.view_xmax = 0.0, 1.0
            self.view_ymin, self.view_ymax = 0.0, 1.0
            self.redraw()
            return

        span_x = all_xmax - all_xmin if all_xmax != all_xmin else 1.0
        span_y = all_ymax - all_ymin if all_ymax != all_ymin else 1.0

        self.view_xmin, self.view_xmax = all_xmin - span_x * 0.05, all_xmax + span_x * 0.05
        self.view_ymin = self.y_min_override if self.y_min_override is not None else all_ymin - span_y * 0.05
        self.view_ymax = self.y_max_override if self.y_max_override is not None else all_ymax + span_y * 0.05
        self.redraw()

    def _cx(self, x): return self.pad_l + (x - self.view_xmin) / (self.view_xmax - self.view_xmin) * self.cw
    def _cy(self, y): return self.pad_t + (1.0 - (y - self.view_ymin) / (self.view_ymax - self.view_ymin)) * self.ch
    def _dx(self, cx): return self.view_xmin + (cx - self.pad_l) / self.cw * (self.view_xmax - self.view_xmin)
    def _dy(self, cy): return self.view_ymin + (1.0 - (cy - self.pad_t) / self.ch) * (self.view_ymax - self.view_ymin)

    def execute_pan(self, direction, factor=0.08):
        span_x, span_y = self.view_xmax - self.view_xmin, self.view_ymax - self.view_ymin
        if direction == 'left': self.view_xmin -= span_x * factor; self.view_xmax -= span_x * factor
        elif direction == 'right': self.view_xmin += span_x * factor; self.view_xmax += span_x * factor
        elif direction == 'up': self.view_ymin += span_y * factor; self.view_ymax += span_y * factor
        elif direction == 'down': self.view_ymin -= span_y * factor; self.view_ymax -= span_y * factor
        self.redraw()

    def _on_resize(self, e):
        self.w, self.h = e.width, e.height
        self.cw, self.ch = max(1, self.w - self.pad_l - self.pad_r), max(1, self.h - self.pad_t - self.pad_b)
        self.redraw()

    def _on_mouse_down(self, e):
        self.canvas.focus_set()
        if not (self.pad_l <= e.x <= self.w - self.pad_r and self.pad_t <= e.y <= self.h - self.pad_b): return
        
        if self.label_drop_mode:
            self.labels.append({"x": self._dx(e.x), "y": self._dy(e.y), "text": self.next_label_text})
            self.label_drop_mode = False
            self.canvas.config(cursor="")
            self.redraw()
            return

        if self.marker_mode:
            mx, my = self._dx(e.x), self._dy(e.y)
            if self.m1 is not None and self.m2 is not None: self.m1 = self.m2 = None
            if self.m1 is None: self.m1 = (mx, my)
            elif self.m2 is None: self.m2 = (mx, my)
            self.redraw()
            return

        self._last_mx, self._last_my = e.x, e.y

    def _on_mouse_drag(self, e):
        if self.marker_mode or self._last_mx is None: return
        dx_px, dy_px = e.x - self._last_mx, e.y - self._last_my
        span_x, span_y = self.view_xmax - self.view_xmin, self.view_ymax - self.view_ymin

        self.view_xmin -= (dx_px / self.cw) * span_x; self.view_xmax -= (dx_px / self.cw) * span_x
        self.view_ymin += (dy_px / self.ch) * span_y; self.view_ymax += (dy_px / self.ch) * span_y
        self._last_mx, self._last_my = e.x, e.y
        self.redraw()

    def _on_mouse_wheel(self, e):
        if not self.datasets: return
        scale = 0.85 if (hasattr(e, 'delta') and e.delta > 0) or e.num == 4 else 1.15
        ref_x, ref_y = self._dx(e.x), self._dy(e.y)
        new_span_x, new_span_y = (self.view_xmax - self.view_xmin) * scale, (self.view_ymax - self.view_ymin) * scale
        frac_x = max(0.0, min(1.0, (e.x - self.pad_l) / self.cw))
        frac_y = max(0.0, min(1.0, 1.0 - ((e.y - self.pad_t) / self.ch)))

        self.view_xmin, self.view_xmax = ref_x - new_span_x * frac_x, ref_x + new_span_x * (1 - frac_x)
        self.view_ymin, self.view_ymax = ref_y - new_span_y * frac_y, ref_y + new_span_y * (1 - frac_y)
        self.redraw()

    def _on_hover(self, e):
        if not self.datasets or not (self.pad_l <= e.x <= self.w - self.pad_r and self.pad_t <= e.y <= self.h - self.pad_b):
            self._on_mouse_leave(None); return

        hx = self._dx(e.x)
        closest, min_delta_x = None, np.inf

        for d_id, trace in {**self.datasets, **self.analysis_layers}.items():
            if len(trace["x"]) == 0: continue
            
            s_idx = np.searchsorted(trace["x"], self.view_xmin)
            e_idx = np.searchsorted(trace["x"], self.view_xmax)
            if s_idx > 0: s_idx -= 1
            if e_idx < len(trace["x"]): e_idx += 1
            
            sub_x = trace["x"][s_idx:e_idx]
            if len(sub_x) == 0: continue
            
            idx = np.searchsorted(sub_x, hx)
            idx = max(0, min(idx, len(sub_x) - 1))
            
            if abs(sub_x[idx] - hx) < min_delta_x:
                min_delta_x = abs(sub_x[idx] - hx)
                closest = (trace["trace_name"], sub_x[idx], trace["y"][s_idx:e_idx][idx], trace["color"])

        if closest:
            t_name, tx, ty, col = closest
            cx, cy = self._cx(tx), self._cy(ty)

            self.canvas.coords(self.vl, cx, self.pad_t, cx, self.h - self.pad_b)
            self.canvas.coords(self.hl, self.pad_l, cy, self.w - self.pad_r, cy)

            self.canvas.itemconfig(self.tt_txt, text=f"Trace: {t_name}\nX: {tx:.4f}\nY: {ty:.4f}")
            bbox = self.canvas.bbox(self.tt_txt)
            if bbox:
                self.canvas.coords(self.tt_bg, cx + 10, cy - 10, cx + 15 + (bbox[2]-bbox[0]), cy + 10 + (bbox[3]-bbox[1]))
                self.canvas.coords(self.tt_txt, cx + 12, cy - 6)

            self.canvas.itemconfig(self.vl, state='normal')
            self.canvas.itemconfig(self.hl, state='normal')
            self.canvas.itemconfig(self.tt_bg, state='normal')
            self.canvas.itemconfig(self.tt_txt, state='normal')

    def _on_mouse_leave(self, e):
        self.canvas.itemconfig(self.vl, state='hidden'); self.canvas.itemconfig(self.hl, state='hidden')
        self.canvas.itemconfig(self.tt_bg, state='hidden'); self.canvas.itemconfig(self.tt_txt, state='hidden')

    def redraw(self):
        self.canvas.delete('grid'); self.canvas.delete('trace')
        self.canvas.tag_raise('hover')
        self.canvas.config(bg=Theme.CV_BG, highlightbackground=Theme.BRD)

        if self.title:
            self.canvas.create_text(self.pad_l - 10, 15, text=self.title, fill=Theme.ACC, font=('Segoe UI', 9, 'bold'), anchor='w', tags='grid')
        if self.x_label:
            self.canvas.create_text(self.pad_l + self.cw/2, self.h - 10, text=self.x_label, fill=Theme.FG, font=('Segoe UI', 8, 'bold'), anchor='s', tags='grid')
        if self.y_label:
            self.canvas.create_text(15, self.pad_t + self.ch/2, text=self.y_label, fill=Theme.FG, font=('Segoe UI', 8, 'bold'), angle=90, anchor='s', tags='grid')

        for k in range(self.num_grid + 1):
            frac = k / self.num_grid
            gx, gy = self.pad_l + self.cw * frac, self.pad_t + self.ch * frac
            
            self.canvas.create_line(self.pad_l, gy, self.w - self.pad_r, gy, fill=Theme.SEP, tags='grid')
            self.canvas.create_text(self.pad_l - 6, gy, text=f"{self.view_ymax - (self.view_ymax - self.view_ymin) * frac:.3g}", anchor='e', font=('Segoe UI', 8), fill=Theme.DIM, tags='grid')

            self.canvas.create_line(gx, self.pad_t, gx, self.h - self.pad_b, fill=Theme.SEP, tags='grid')
            self.canvas.create_text(gx, self.h - self.pad_b + 6, text=f"{self.view_xmin + (self.view_xmax - self.view_xmin) * frac:.3g}", anchor='n', font=('Segoe UI', 8), fill=Theme.DIM, tags='grid')

        dash_map = {"Solid": None, "Dashed": (8, 4), "Dotted": (2, 4)}

        for group in [self.datasets, self.analysis_layers]:
            for d_id, trace in group.items():
                tx, ty = trace["x"], trace["y"]
                if len(tx) < 2: continue

                s_idx = np.searchsorted(tx, self.view_xmin)
                e_idx = np.searchsorted(tx, self.view_xmax)
                if s_idx > 0: s_idx -= 1 
                if e_idx < len(tx): e_idx += 1

                vx, vy = tx[s_idx:e_idx], ty[s_idx:e_idx]
                n_samples = len(vx)
                if n_samples < 2: continue

                if n_samples > self.MAX_DRAW_PTS:
                    stride = max(1, n_samples // self.MAX_DRAW_PTS)
                    vx, vy = vx[::stride], vy[::stride]

                px = self.pad_l + (vx - self.view_xmin) / (self.view_xmax - self.view_xmin) * self.cw
                py = self.pad_t + (1.0 - (vy - self.view_ymin) / (self.view_ymax - self.view_ymin)) * self.ch
                
                coords = np.empty(len(px) * 2, dtype=float)
                coords[0::2], coords[1::2] = px, py
                
                style = dash_map.get(trace.get("style", "Solid"), None)
                self.canvas.create_line(*coords.tolist(), fill=trace["color"], width=1.5, dash=style, tags='trace', joinstyle=tk.ROUND)

        items = list(self.datasets.items()) + list(self.analysis_layers.items())
        if items:
            lx, ly = self.w - self.pad_r - 180, self.pad_t + 10
            box_h = len(items) * 18 + 10
            self.canvas.create_rectangle(lx - 8, ly - 4, lx + 170, ly + box_h - 4, fill=Theme.PNL, outline=Theme.BRD, tags='trace')
            for d_id, trace in items:
                style = dash_map.get(trace.get("style", "Solid"), None)
                name = trace.get("trace_name")[:20] + "..." if len(trace.get("trace_name")) > 20 else trace.get("trace_name")
                self.canvas.create_line(lx, ly + 8, lx + 20, ly + 8, fill=trace["color"], width=1.5, dash=style, tags='trace')
                self.canvas.create_text(lx + 28, ly + 8, text=name, fill=Theme.FG, font=('Segoe UI', 8, 'bold'), anchor='w', tags='trace')
                ly += 18

        for lbl in self.labels:
            lx, ly = self._cx(lbl["x"]), self._cy(lbl["y"])
            if self.pad_l <= lx <= self.w - self.pad_r and self.pad_t <= ly <= self.h - self.pad_b:
                self.canvas.create_oval(lx-4, ly-4, lx+4, ly+4, fill='#10b981', outline='#ffffff', tags='trace')
                self.canvas.create_text(lx+8, ly-8, text=lbl["text"], anchor='sw', font=('Segoe UI', 8, 'bold'), fill=Theme.FG, tags='trace')

        self._render_markers()
        if self.on_view_changed: self.on_view_changed()

    def _render_markers(self):
        pts = [p for p in [self.m1, self.m2] if p]
        for p in pts:
            cx, cy = self._cx(p[0]), self._cy(p[1])
            self.canvas.create_oval(cx-4, cy-4, cx+4, cy+4, fill=Theme.C_MARK, outline='#ffffff', width=1, tags='trace')

        if len(pts) == 2:
            cx1, cy1 = self._cx(pts[0][0]), self._cy(pts[0][1])
            cx2, cy2 = self._cx(pts[1][0]), self._cy(pts[1][1])
            self.canvas.create_line(cx1, cy1, cx2, cy2, fill=Theme.C_MARK, width=1.5, dash=(4, 4), tags='trace')

            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
            slope = dy / dx if dx != 0 else float('inf')
            report = f"ΔX: {dx:.4g} | ΔY: {dy:.4g} | ∠: {math.degrees(math.atan2(dy, dx)):.1f}°"
            mid_x, mid_y = (cx1 + cx2) / 2, min(cy1, cy2) - 15
            
            self.canvas.create_rectangle(mid_x-100, mid_y-10, mid_x+100, mid_y+10, fill='#1e293b', outline=Theme.C_MARK, tags='trace')
            self.canvas.create_text(mid_x, mid_y, text=report, fill='#ffffff', font=('Segoe UI', 8, 'bold'), tags='trace')

# ------------------------------------------------------------------------
# 5. Global State & App Shell (Master Controller)
# ------------------------------------------------------------------------
MAX_LIVE_PTS = 50000  

class App:
    def __init__(self, root):
        self.root = root
        self.startup_path = os.path.join(os.path.abspath(os.getcwd()), "Experiment_Data.csv").replace("\\", "/")
            
        self.root.title("Keysight B2910CL Precision Control Dashboard")
        self.root.configure(bg=Theme.BG)
        self.root.geometry("1050x680")
        self.root.minsize(900, 550)

        self._build_top_menu()

        self.rm = pyvisa.ResourceManager()
        self.smu = None
        self.connected_port = None
        self.is_running = False
        self.manual_stop = False
        self.data_queue = queue.Queue()
        self.is_first_chunk = True
        self.custom_list_vals = []
        
        self.test_target_duration = 0.0
        self.test_start_time = 0.0

        self.global_datasets = {}
        self.global_math = {}
        self.registry_keys = []  
        self.charts = []
        self.chart_configs = {}  
        self.view_mode = "OVERLAY"
        self._stats_timer = None  
        
        self.btn_layout_smu = None
        self.btn_layout_ana = None

        # Custom pattern steps: list of (level, duration_seconds)
        self.custom_steps = []
        self.custom_locked = False

        self._build_ui_shell()
        self._rebuild_charts()
        
        threading.Thread(target=self._visa_monitor_thread, daemon=True).start()

    def _build_top_menu(self):
        menubar = tk.Menu(self.root)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Dark/Light Mode", command=self._toggle_dark_mode)
        menubar.add_cascade(label="View", menu=view_menu)
        self.root.config(menu=menubar)

    def _build_ui_shell(self):
        tb = tk.Frame(self.root, bg=Theme.PNL, height=40, relief='flat')
        tb.pack(fill='x', side='top')
        tk.Frame(self.root, bg=Theme.BRD, height=1).pack(fill='x', side='top')
        tb.pack_propagate(False)

        tk.Label(tb, text='B2910CL MASTER SYSTEM', bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 10, 'bold')).pack(side='left', padx=10)
        tk.Frame(tb, bg=Theme.BRD, width=1).pack(side='left', fill='y', pady=6)
        self.lbl_status = tk.Label(tb, text='Hardware Offline', bg=Theme.PNL, fg=Theme.ERR, font=('Segoe UI', 8, 'bold'))
        self.lbl_status.pack(side='left', padx=10)

        body = tk.Frame(self.root, bg=Theme.BG)
        body.pack(fill='both', expand=True)

        left = tk.Frame(body, bg=Theme.PNL, width=320, relief='flat')
        left.pack(side='left', fill='y')
        left.pack_propagate(False)
        tk.Frame(body, bg=Theme.BRD, width=1).pack(side='left', fill='y')

        left_bottom = tk.Frame(left, bg=Theme.PNL)
        left_bottom.pack(side='bottom', fill='x')

        left_top = tk.Frame(left, bg=Theme.PNL)
        left_top.pack(side='top', fill='both', expand=True)

        style = ttk.Style()
        style.theme_use('default')
        style.configure('Left.TNotebook', background=Theme.PNL, borderwidth=0)
        style.configure('Left.TNotebook.Tab', font=('Segoe UI', 8, 'bold'), padding=[6, 3], background=Theme.PNL2, foreground=Theme.DIM)
        style.map('Left.TNotebook.Tab', background=[('selected', Theme.PNL)], foreground=[('selected', Theme.ACC)])

        self.nb_left = ttk.Notebook(left_top, style='Left.TNotebook')
        self.nb_left.pack(fill='both', expand=True)

        tab_smu = VerticalScrollFrame(self.nb_left)
        tab_ana = tk.Frame(self.nb_left, bg=Theme.PNL)
        tab_scpi = tk.Frame(self.nb_left, bg=Theme.PNL)
        
        self.nb_left.add(tab_smu, text="🔌 SMU Setup")
        self.nb_left.add(tab_ana, text="📊 Analytics")
        self.nb_left.add(tab_scpi, text="💻 SCPI Terminal")
        
        def sec(parent, title):
            tk.Frame(parent, bg=Theme.SEP, height=1).pack(fill='x')
            f = tk.Frame(parent, bg=Theme.PNL)
            f.pack(fill='x', padx=10, pady=4)
            tk.Label(f, text=title, bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 7, 'bold')).pack(anchor='w', pady=(1, 2))
            return f

        smu_inner = tab_smu.inner
        conn_sec = sec(smu_inner, "HARDWARE CONNECTION")
        self.visa_combo = ttk.Combobox(conn_sec, state='readonly', font=('Segoe UI', 8))
        self.visa_combo.pack(fill='x', pady=2)
        btn_frm = tk.Frame(conn_sec, bg=Theme.PNL)
        btn_frm.pack(fill='x', pady=2)
        tk.Button(btn_frm, text="Manual Scan", bg=Theme.PNL2, fg=Theme.FG, relief='flat', font=('Segoe UI', 7, 'bold'), command=self._scan_visa).pack(side='left', fill='x', expand=True, padx=(0,2))
        self.btn_conn = tk.Button(btn_frm, text="Connect Hardware", bg=Theme.PNL2, fg=Theme.FG, relief='flat', font=('Segoe UI', 7, 'bold'), command=self._connect_smu)
        self.btn_conn.pack(side='right', fill='x', expand=True, padx=(2,0))

        cfg_sec = sec(smu_inner, "TEST CONFIGURATION")
        
        self.src_mode_var = tk.StringVar(value="Current (A)")
        tk.Label(cfg_sec, text="Source Mode:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).pack(anchor='w')
        cb_src = ttk.Combobox(cfg_sec, textvariable=self.src_mode_var, values=["Current (A)", "Voltage (V)"], state="readonly", font=('Segoe UI', 8))
        cb_src.pack(fill='x', pady=(0,3))
        
        self.msr_mode_var = tk.StringVar(value="Auto (Opposite)")
        tk.Label(cfg_sec, text="Primary Measurement Display:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).pack(anchor='w')
        cb_msr = ttk.Combobox(cfg_sec, textvariable=self.msr_mode_var, values=["Auto (Opposite)", "Voltage (V)", "Current (A)", "Resistance (Ω)", "Power (W)"], state="readonly", font=('Segoe UI', 8))
        cb_msr.pack(fill='x', pady=(0,3))

        # Waveform shape
        self.shape_var = tk.StringVar(value="Temple Run")
        tk.Label(cfg_sec, text="Waveform Shape:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).pack(anchor='w')
        
        shape_frm = tk.Frame(cfg_sec, bg=Theme.PNL)
        shape_frm.pack(fill='x', pady=(0,2))
        cb_shape = ttk.Combobox(shape_frm, textvariable=self.shape_var, values=["Constant DC", "Sine Wave", "Cosine Wave", "Square (Pulse)", "Triangle", "Staircase", "Temple Run", "Custom Pattern", "Custom (CSV List)"], state="readonly", font=('Segoe UI', 8))
        cb_shape.pack(side='left', fill='x', expand=True)
        # Preview button
        tk.Button(shape_frm, text="Preview", bg=Theme.PNL2, fg=Theme.ACC, relief='flat', font=('Segoe UI', 7, 'bold'), command=self._preview_waveform).pack(side='right', padx=(4,0))

        self.dynamic_params = tk.Frame(cfg_sec, bg=Theme.PNL)
        self.dynamic_params.pack(fill='x', pady=(0,0))
        
        self.lbl_min = tk.Label(self.dynamic_params, text="Base/Min Level (A):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8))
        self.lbl_min.grid(row=0, column=0, sticky='w', pady=1)
        self.ent_min = tk.Entry(self.dynamic_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 8), width=10)
        self.ent_min.insert(0, "0.005")
        self.ent_min.grid(row=0, column=1, sticky='e', pady=1)

        self.lbl_max = tk.Label(self.dynamic_params, text="Peak Level (A):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8))
        self.lbl_max.grid(row=1, column=0, sticky='w', pady=1)
        self.ent_max = tk.Entry(self.dynamic_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 8), width=10)
        self.ent_max.insert(0, "0.040")
        self.ent_max.grid(row=1, column=1, sticky='e', pady=1)

        self.lbl_cmp = tk.Label(self.dynamic_params, text="Compliance Limit (V):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8))
        self.lbl_cmp.grid(row=2, column=0, sticky='w', pady=1)
        self.ent_cmp = tk.Entry(self.dynamic_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 8), width=10)
        self.ent_cmp.insert(0, "10.0")
        self.ent_cmp.grid(row=2, column=1, sticky='e', pady=1)
        
        def _update_units(*args):
            is_curr = "Current" in self.src_mode_var.get()
            u_src = "A" if is_curr else "V"
            u_cmp = "V" if is_curr else "A"
            shape = self.shape_var.get()
            if "Constant DC" in shape:
                self.lbl_min.config(text=f"DC Constant Level ({u_src}):")
            else:
                self.lbl_min.config(text=f"Base/Min Level ({u_src}):")
            self.lbl_max.config(text=f"Peak/Max Level ({u_src}):")
            self.lbl_cmp.config(text=f"Compliance Limit ({u_cmp}):")
            self.root.after(100, self._update_dynamic_ui)
            
        self.src_mode_var.trace_add('write', _update_units)
        
        # Time frames for different shapes
        self.time_frame_std = tk.Frame(cfg_sec, bg=Theme.PNL)
        self.time_frame_pls = tk.Frame(cfg_sec, bg=Theme.PNL)
        self.time_frame_csv = tk.Frame(cfg_sec, bg=Theme.PNL)
        self.time_frame_custom = tk.Frame(cfg_sec, bg=Theme.PNL)
        
        tk.Label(self.time_frame_std, text="Cycle Period (s):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=0, column=0, sticky='w', pady=1)
        self.ent_per = tk.Entry(self.time_frame_std, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 8), width=10)
        self.ent_per.insert(0, "4.0")
        self.ent_per.grid(row=0, column=1, sticky='e', pady=1)
        
        self.pulse_base_var = tk.StringVar(value="2.0")
        self.pulse_peak_var = tk.StringVar(value="2.0")
        tk.Label(self.time_frame_pls, text="Time at Base (s):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=0, column=0, sticky='w', pady=1)
        tk.Entry(self.time_frame_pls, textvariable=self.pulse_base_var, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 8), width=10).grid(row=0, column=1, sticky='e', pady=1)
        tk.Label(self.time_frame_pls, text="Time at Peak (s):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=1, column=0, sticky='w', pady=1)
        tk.Entry(self.time_frame_pls, textvariable=self.pulse_peak_var, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 8), width=10).grid(row=1, column=1, sticky='e', pady=1)
        self.lbl_duty = tk.Label(self.time_frame_pls, text="Duty: 50.0% | Period: 4.0s", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 7, 'bold'))
        self.lbl_duty.grid(row=2, column=0, columnspan=2, sticky='e', pady=1)
        
        # ---- Custom Pattern Builder (with Lock) ----
        custom_frame = self.time_frame_custom

        # Step listbox
        self.custom_steps_listbox = tk.Listbox(custom_frame, bg=Theme.PNL2, fg=Theme.FG, height=5, font=('Segoe UI', 8))
        self.custom_steps_listbox.pack(fill='x', pady=2)
        # Buttons row
        btn_row = tk.Frame(custom_frame, bg=Theme.PNL)
        btn_row.pack(fill='x', pady=1)
        self.btn_add_step = tk.Button(btn_row, text="Add Step (+)", bg=Theme.PNL2, fg=Theme.ACC, relief='flat', font=('Segoe UI', 7, 'bold'), command=self._add_custom_step)
        self.btn_add_step.pack(side='left', fill='x', expand=True, padx=(0,2))
        self.btn_remove_step = tk.Button(btn_row, text="Remove Sel. (-)", bg=Theme.PNL2, fg='#dc2626', relief='flat', font=('Segoe UI', 7, 'bold'), command=self._remove_custom_step)
        self.btn_remove_step.pack(side='left', fill='x', expand=True, padx=(2,2))
        self.btn_clear_steps = tk.Button(btn_row, text="Clear All", bg=Theme.PNL2, fg=Theme.DIM, relief='flat', font=('Segoe UI', 7, 'bold'), command=self._clear_custom_steps)
        self.btn_clear_steps.pack(side='left', fill='x', expand=True, padx=(2,0))
        # Lock/Unlock button
        self.btn_lock_custom = tk.Button(custom_frame, text="🔒 Lock Pattern", bg=Theme.PNL2, fg=Theme.ACC, relief='flat', font=('Segoe UI', 7, 'bold'), command=self._toggle_custom_lock)
        self.btn_lock_custom.pack(fill='x', pady=1)

        self.lbl_custom_period = tk.Label(custom_frame, text="Total Cycle Period: 0.0 s", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 8, 'bold'))
        self.lbl_custom_period.pack(anchor='e', pady=2)

        # --- CSV custom ---
        tk.Button(self.time_frame_csv, text="Browse Custom CSV...", bg=Theme.PNL2, fg=Theme.ACC, font=('Segoe UI', 7, 'bold'), relief='flat', command=self._load_custom_csv).pack(fill='x', pady=1)
        self.lbl_custom = tk.Label(self.time_frame_csv, text="No File Loaded.", bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 7))
        self.lbl_custom.pack(anchor='w')

        # Bottom parameters: Sampling rate, Cycles, Total Time, Infinite
        self.bottom_params = tk.Frame(cfg_sec, bg=Theme.PNL)
        self.bottom_params.pack(fill='x', pady=(0,0))
        
        # Sampling Rate (universal)
        tk.Label(self.bottom_params, text="Sampling Rate (samples/s):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=0, column=0, sticky='w', pady=1)
        self.ent_sampling = tk.Entry(self.bottom_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 8), width=10)
        self.ent_sampling.insert(0, "100")
        self.ent_sampling.grid(row=0, column=1, sticky='e', pady=1)

        # Number of Cycles
        tk.Label(self.bottom_params, text="Cycles (0=use Total Time):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=1, column=0, sticky='w', pady=1)
        self.ent_cycles = tk.Entry(self.bottom_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 8), width=10)
        self.ent_cycles.insert(0, "0")
        self.ent_cycles.grid(row=1, column=1, sticky='e', pady=1)
        self.ent_cycles.bind("<KeyRelease>", self._on_cycles_changed)

        # Total Test Time (with Infinite checkbox)
        tk.Label(self.bottom_params, text="Total Test Time (s):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=2, column=0, sticky='w', pady=1)
        time_entry_frm = tk.Frame(self.bottom_params, bg=Theme.PNL)
        time_entry_frm.grid(row=2, column=1, sticky='e', pady=1)
        self.ent_tot = tk.Entry(time_entry_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 8), width=6)
        self.ent_tot.insert(0, "14.0")
        self.ent_tot.pack(side='left')
        self.inf_run_var = tk.BooleanVar(value=False)
        chk_inf = tk.Checkbutton(time_entry_frm, text="∞", variable=self.inf_run_var, bg=Theme.PNL, fg=Theme.C_HL, selectcolor=Theme.PNL2, font=('Segoe UI', 8, 'bold'))
        chk_inf.pack(side='left', padx=(2,0))
        
        def _on_inf_run_toggle(*args):
            if self.inf_run_var.get():
                self.ent_tot.config(state='disabled')
                self.ent_cycles.config(state='disabled')
            else:
                self.ent_tot.config(state='normal')
                self.ent_cycles.config(state='normal')
                self._on_cycles_changed()  # re-evaluate
        self.inf_run_var.trace_add('write', _on_inf_run_toggle)

        # Swap UI based on shape
        def _swap_ui(*args):
            shape = self.shape_var.get()
            self.time_frame_std.pack_forget()
            self.time_frame_pls.pack_forget()
            self.time_frame_csv.pack_forget()
            self.time_frame_custom.pack_forget()
            
            if "Constant DC" in shape:
                self.lbl_max.grid_remove()
                self.ent_max.grid_remove()
                self.lbl_min.grid(row=0, column=0, sticky='w', pady=1)
                self.ent_min.grid(row=0, column=1, sticky='e', pady=1)
                self.lbl_cmp.grid(row=2, column=0, sticky='w', pady=1)
                self.ent_cmp.grid(row=2, column=1, sticky='e', pady=1)
            elif shape == "Custom Pattern":
                self.lbl_max.grid_remove()
                self.ent_max.grid_remove()
                self.lbl_min.grid_remove()
                self.ent_min.grid_remove()
                self.lbl_cmp.grid(row=0, column=0, sticky='w', pady=1)
                self.ent_cmp.grid(row=0, column=1, sticky='e', pady=1)
                self.time_frame_custom.pack(fill='x', after=self.dynamic_params)
            elif shape == "Custom (CSV List)":
                self.lbl_max.grid(row=1, column=0, sticky='w', pady=1)
                self.ent_max.grid(row=1, column=1, sticky='e', pady=1)
                self.lbl_min.grid(row=0, column=0, sticky='w', pady=1)
                self.ent_min.grid(row=0, column=1, sticky='e', pady=1)
                self.lbl_cmp.grid(row=2, column=0, sticky='w', pady=1)
                self.ent_cmp.grid(row=2, column=1, sticky='e', pady=1)
                self.time_frame_csv.pack(fill='x', after=self.dynamic_params)
            elif shape == "Temple Run":
                self.lbl_max.grid_remove()
                self.ent_max.grid_remove()
                self.lbl_min.grid_remove()
                self.ent_min.grid_remove()
                self.lbl_cmp.grid(row=0, column=0, sticky='w', pady=1)
                self.ent_cmp.grid(row=0, column=1, sticky='e', pady=1)
            else:
                self.lbl_max.grid(row=1, column=0, sticky='w', pady=1)
                self.ent_max.grid(row=1, column=1, sticky='e', pady=1)
                self.lbl_min.grid(row=0, column=0, sticky='w', pady=1)
                self.ent_min.grid(row=0, column=1, sticky='e', pady=1)
                self.lbl_cmp.grid(row=2, column=0, sticky='w', pady=1)
                self.ent_cmp.grid(row=2, column=1, sticky='e', pady=1)
                if "Pulse" in shape:
                    self.time_frame_pls.pack(fill='x', after=self.dynamic_params)
                else:
                    self.time_frame_std.pack(fill='x', after=self.dynamic_params)
            self._update_dynamic_ui()
            
        self.shape_var.trace_add('write', _swap_ui)
        _swap_ui()

        # Viewport control
        sys_sec_smu = sec(smu_inner, "VIEWPORT CONTROL")
        self.btn_layout_smu = tk.Button(sys_sec_smu, text='🗖  Split to Grid View', bg=Theme.PNL2, fg=Theme.FG, state='disabled', relief='flat', bd=0, font=('Segoe UI', 8, 'bold'), cursor='hand2', command=self._toggle_layout_mode)
        self.btn_layout_smu.pack(fill='x', ipady=2, pady=2)
        tk.Button(sys_sec_smu, text='↺  Auto-Fit Graphics', bg='#fff7ed', fg='#c2410c', relief='flat', bd=0, font=('Segoe UI', 8, 'bold'), cursor='hand2', command=self._reset_chart_bounds).pack(fill='x', ipady=2, pady=2)

        self.pulse_base_var.trace_add('write', lambda *a: self.root.after(200, self._update_dynamic_ui))
        self.pulse_peak_var.trace_add('write', lambda *a: self.root.after(200, self._update_dynamic_ui))

        # ==========================================
        # FIXED BOTTOM ACTION PANEL
        # ==========================================
        tk.Frame(left_bottom, bg=Theme.SEP, height=1).pack(fill='x')
        action_frm = tk.Frame(left_bottom, bg=Theme.PNL)
        action_frm.pack(fill='x', padx=10, pady=5)

        self.save_var = tk.StringVar(value=self.startup_path)
        tk.Label(action_frm, text="Save Data To:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 7, 'bold')).pack(anchor='w')
        sv_frm = tk.Frame(action_frm, bg=Theme.PNL)
        sv_frm.pack(fill='x', pady=(0, 2))
        tk.Entry(sv_frm, textvariable=self.save_var, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 7)).pack(side='left', fill='x', expand=True)
        tk.Button(sv_frm, text="Browse", bg=Theme.PNL2, fg=Theme.FG, relief='flat', command=self._browse_save, font=('Segoe UI', 7, 'bold')).pack(side='right', padx=(2,0))

        tk.Label(action_frm, text="Post-Test Output State:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 7)).pack(anchor='w')
        self.off_mode_var = tk.StringVar(value="Hold Last Level")
        ttk.Combobox(action_frm, textvariable=self.off_mode_var, values=["Turn OFF (Normal)", "Turn OFF (High-Z)", "Hold Last Level"], state="readonly", font=('Segoe UI', 8)).pack(fill='x', pady=(0,4))

        ctrl_btn_frm = tk.Frame(action_frm, bg=Theme.PNL)
        ctrl_btn_frm.pack(fill='x', pady=2)
        
        self.btn_start = tk.Button(ctrl_btn_frm, text="▶ START", bg=Theme.ACC, fg="#ffffff", font=('Segoe UI', 9, 'bold'), relief='flat', command=self._start_test)
        self.btn_start.pack(side='left', fill='x', expand=True, ipady=4, padx=(0, 3))
        
        self.btn_stop = tk.Button(ctrl_btn_frm, text="⏹ STOP", bg=Theme.ERR, fg="#ffffff", font=('Segoe UI', 9, 'bold'), relief='flat', command=self._stop_test)
        self.btn_stop.pack(side='right', fill='x', expand=True, ipady=4, padx=(3, 0))

        # ==========================================
        # TAB 2: ANALYTICS 
        # ==========================================
        ds_sec = sec(tab_ana, "DATA SOURCE")
        tk.Button(ds_sec, text='📂  Load Offline CSV', bg=Theme.PNL2, fg=Theme.ACC, relief='flat', bd=0, font=('Segoe UI', 8, 'bold'), cursor='hand2', command=self._browse_and_load_csv).pack(fill='x', ipady=3, pady=2)
        self.line_registry_box = tk.Listbox(ds_sec, height=5, bg=Theme.PNL2, fg=Theme.FG, font=('Segoe UI', 8), selectmode='single', highlightthickness=0, bd=0)
        self.line_registry_box.pack(fill='x', pady=2)
        self.listbox_tooltip = ListboxTooltip(self.line_registry_box, lambda idx: self.global_datasets.get(self.registry_keys[idx]) if idx < len(self.registry_keys) else None)
        self.line_registry_box.bind('<<ListboxSelect>>', self._on_listbox_select)
        
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8))
        self.context_menu.add_command(label="⚙ Re-configure CSV Map", command=self._reconfigure_selected_line)
        self.context_menu.add_command(label="👁 Toggle Visibility", command=self._toggle_visibility)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✕ Remove Trace", command=self._purge_selected_line, foreground="#dc2626")

        self.line_registry_box.bind("<Button-3>", self._show_listbox_context_menu)
        self.line_registry_box.bind("<Button-2>", self._show_listbox_context_menu)

        btn_frm_a = tk.Frame(ds_sec, bg=Theme.PNL)
        btn_frm_a.pack(fill='x', pady=1)
        tk.Button(btn_frm_a, text='👁 Toggle Vis', bg=Theme.PNL2, fg=Theme.FG, relief='flat', bd=0, font=('Segoe UI', 7, 'bold'), cursor='hand2', command=self._toggle_visibility).pack(side='left', fill='x', expand=True, padx=(0, 2))
        tk.Button(btn_frm_a, text='✕ Remove', bg='#fef2f2', fg='#dc2626', relief='flat', bd=0, font=('Segoe UI', 7, 'bold'), cursor='hand2', command=self._purge_selected_line).pack(side='right', fill='x', expand=True, padx=(2, 0))

        lay_sec = sec(tab_ana, "LAYOUT & VIEWPORT")
        self.btn_layout_ana = tk.Button(lay_sec, text='🗖  Split to Grid View', bg=Theme.PNL2, fg=Theme.FG, state='disabled', relief='flat', bd=0, font=('Segoe UI', 8, 'bold'), cursor='hand2', command=self._toggle_layout_mode)
        self.btn_layout_ana.pack(fill='x', ipady=3, pady=2)
        tk.Button(lay_sec, text='↺  Auto-Fit Graphics', bg='#fff7ed', fg='#c2410c', relief='flat', bd=0, font=('Segoe UI', 8, 'bold'), cursor='hand2', command=self._reset_chart_bounds).pack(fill='x', ipady=3, pady=2)

        math_sec = sec(tab_ana, "CALCULUS TOOLS")
        self.math_target_var = tk.StringVar()
        self.math_combo = ttk.Combobox(math_sec, textvariable=self.math_target_var, state='readonly', font=('Segoe UI', 8))
        self.math_combo.pack(fill='x', pady=2)
        tk.Button(math_sec, text='⚡ Differentiation (Slope)', bg=Theme.PNL2, fg=Theme.FG, relief='flat', bd=0, font=('Segoe UI', 8), cursor='hand2', command=self._run_derivative_pipeline).pack(fill='x', ipady=2, pady=2)
        tk.Button(math_sec, text='∫ Integration (Area)', bg=Theme.PNL2, fg=Theme.FG, relief='flat', bd=0, font=('Segoe UI', 8), cursor='hand2', command=self._run_integral_pipeline).pack(fill='x', ipady=2, pady=2)
        tk.Button(math_sec, text='✕ Clear Math Traces', bg=Theme.PNL2, fg='#dc2626', relief='flat', bd=0, font=('Segoe UI', 8, 'bold'), cursor='hand2', command=self._clear_math_traces).pack(fill='x', pady=2)

        # ==========================================
        # TAB 3: SCPI TERMINAL
        # ==========================================
        scpi_sec = sec(tab_scpi, "RAW HARDWARE COMMUNICATION")
        tk.Label(scpi_sec, text="Send custom SCPI commands directly.", bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 7)).pack(anchor='w', pady=(0,5))
        
        self.txt_term = tk.Text(scpi_sec, bg=Theme.PNL2, fg=Theme.FG, font=('Consolas', 8), height=15)
        self.txt_term.pack(fill='x', pady=5)
        
        cmd_frm = tk.Frame(scpi_sec, bg=Theme.PNL)
        cmd_frm.pack(fill='x', pady=5)
        self.ent_cmd = tk.Entry(cmd_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Consolas', 9))
        self.ent_cmd.pack(side='left', fill='x', expand=True)
        self.ent_cmd.bind("<Return>", lambda e: self._send_scpi())
        tk.Button(cmd_frm, text="SEND", bg=Theme.ACC, fg="#ffffff", relief='flat', font=('Segoe UI', 7, 'bold'), command=self._send_scpi).pack(side='right', padx=(5,0))

        # -- RIGHT PANEL (Graph) --
        right = tk.Frame(body, bg=Theme.BG)
        right.pack(side='left', fill='both', expand=True, padx=10, pady=10)

        self.timer_frame = tk.Frame(right, bg=Theme.PNL, highlightthickness=1, highlightbackground=Theme.SEP)
        self.timer_frame.pack(fill='x', side='top', pady=(0, 6))
        
        self.lbl_exp_status = tk.Label(self.timer_frame, text="EXPERIMENT IDLE", bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 10, 'bold'))
        self.lbl_exp_status.pack(side='left', padx=10, pady=6)
        
        self.lbl_exp_time = tk.Label(self.timer_frame, text="Time Remaining: --:--", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 10, 'bold'))
        self.lbl_exp_time.pack(side='right', padx=10, pady=6)

        stats_frame = tk.Frame(right, bg=Theme.BG)
        stats_frame.pack(fill='x', side='top', pady=(0, 6))

        self.metric_boxes = {}
        ordered_metrics = [('min', 'Min (Vis)'), ('max', 'Max (Vis)'), ('mean', 'Mean μ'), ('std', 'Std Dev σ'), ('count', 'Samples in View')]
        for m_key, label_text in ordered_metrics:
            cell = tk.Frame(stats_frame, bg=Theme.PNL, highlightthickness=1, highlightbackground=Theme.SEP)
            cell.pack(side='left', fill='x', expand=True, padx=2)
            tk.Label(cell, text=label_text.upper(), bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 7, 'bold')).pack(anchor='w', padx=6, pady=(4, 0))
            val_lbl = tk.Label(cell, text='--', bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 9, 'bold'))
            val_lbl.pack(anchor='w', padx=6, pady=(0, 4))
            self.metric_boxes[m_key] = val_lbl

        nb = ttk.Notebook(right, style='Sim.TNotebook')
        nb.pack(fill='both', expand=True)

        chart_tab_panel = tk.Frame(nb, bg=Theme.BG)
        nb.add(chart_tab_panel, text='📈  High-Definition Interactive Viewports')

        self.chart_container = tk.Frame(chart_tab_panel, bg=Theme.BG)
        self.chart_container.pack(fill='both', expand=True, padx=4, pady=4)

    # ------------------------------------------------------------------
    # Custom Pattern Step Management (with Lock)
    # ------------------------------------------------------------------
    def _toggle_custom_lock(self):
        self.custom_locked = not self.custom_locked
        if self.custom_locked:
            self.btn_lock_custom.config(text="🔓 Unlock Pattern", bg='#fef2f2', fg='#dc2626')
            self.btn_add_step.config(state='disabled')
            self.btn_remove_step.config(state='disabled')
            self.btn_clear_steps.config(state='disabled')
            self.custom_steps_listbox.config(state='disabled')
        else:
            self.btn_lock_custom.config(text="🔒 Lock Pattern", bg=Theme.PNL2, fg=Theme.ACC)
            self.btn_add_step.config(state='normal')
            self.btn_remove_step.config(state='normal')
            self.btn_clear_steps.config(state='normal')
            self.custom_steps_listbox.config(state='normal')

    def _add_custom_step(self):
        if self.custom_locked:
            messagebox.showinfo("Locked", "Pattern is locked. Unlock to edit.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Add Custom Step")
        dialog.geometry("280x150")
        dialog.configure(bg=Theme.PNL)
        dialog.transient(self.root)
        dialog.grab_set()

        tk.Label(dialog, text="Level (A or V):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=0, column=0, padx=5, pady=5, sticky='e')
        entry_level = tk.Entry(dialog, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=15, font=('Segoe UI', 8))
        entry_level.grid(row=0, column=1, padx=5, pady=5)
        entry_level.insert(0, "0.0")

        tk.Label(dialog, text="Duration (ms):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 8)).grid(row=1, column=0, padx=5, pady=5, sticky='e')
        entry_dur = tk.Entry(dialog, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=15, font=('Segoe UI', 8))
        entry_dur.grid(row=1, column=1, padx=5, pady=5)
        entry_dur.insert(0, "1000")

        def confirm():
            try:
                level = float(entry_level.get())
                dur_ms = float(entry_dur.get())
                if dur_ms <= 0:
                    raise ValueError("Duration must be positive")
                dur_s = dur_ms / 1000.0
                self.custom_steps.append((level, dur_s))
                self._update_custom_ui()
                dialog.destroy()
            except ValueError as e:
                messagebox.showerror("Invalid Input", str(e))

        btn_frame = tk.Frame(dialog, bg=Theme.PNL)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        tk.Button(btn_frame, text="OK", bg=Theme.ACC, fg="white", relief='flat', command=confirm, font=('Segoe UI', 8)).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancel", bg=Theme.PNL2, fg=Theme.FG, relief='flat', command=dialog.destroy, font=('Segoe UI', 8)).pack(side='left', padx=5)

        entry_level.focus_set()
        dialog.bind('<Return>', lambda e: confirm())

    def _remove_custom_step(self):
        if self.custom_locked:
            messagebox.showinfo("Locked", "Pattern is locked. Unlock to edit.")
            return
        sel = self.custom_steps_listbox.curselection()
        if not sel:
            messagebox.showinfo("Info", "Please select a step to remove.")
            return
        idx = sel[0]
        if 0 <= idx < len(self.custom_steps):
            del self.custom_steps[idx]
            self._update_custom_ui()

    def _clear_custom_steps(self):
        if self.custom_locked:
            messagebox.showinfo("Locked", "Pattern is locked. Unlock to edit.")
            return
        if self.custom_steps and messagebox.askyesno("Clear All", "Remove all custom steps?"):
            self.custom_steps.clear()
            self._update_custom_ui()

    def _update_custom_ui(self):
        self.custom_steps_listbox.delete(0, tk.END)
        for idx, (level, dur) in enumerate(self.custom_steps):
            self.custom_steps_listbox.insert(tk.END, f"Step {idx+1}: {level:.4g} A  {dur*1000:.0f} ms")
        total = sum(dur for _, dur in self.custom_steps)
        self.lbl_custom_period.config(text=f"Total Cycle Period: {total:.3f} s")
        # Also update period label for other shapes? Not needed.

    def _on_cycles_changed(self, event=None):
        """If cycles > 0, compute total time and disable total time entry."""
        try:
            cycles = int(self.ent_cycles.get())
        except ValueError:
            cycles = 0
        if cycles > 0 and not self.inf_run_var.get():
            period = self._get_current_period()
            total_time = cycles * period + 2.0  # buffer 2s
            self.ent_tot.config(state='normal')
            self.ent_tot.delete(0, tk.END)
            self.ent_tot.insert(0, f"{total_time:.3f}")
            self.ent_tot.config(state='disabled')
        else:
            self.ent_tot.config(state='normal')
            if self.inf_run_var.get():
                self.ent_tot.config(state='disabled')
            else:
                # If cycles == 0, enable total time
                pass

    # ------------------------------------------------------------------
    # Data Array Generation Logic 
    # ------------------------------------------------------------------
    def safe_float(self, entry, default=0.0):
        try: return float(entry.get())
        except ValueError: return default

    def _get_current_period(self):
        shape = self.shape_var.get()
        if shape == "Pulse":
            try: return float(self.pulse_base_var.get()) + float(self.pulse_peak_var.get())
            except: return 4.0
        elif shape == "Temple Run": 
            return 14.0
        elif shape == "Custom Pattern":
            total = sum(dur for _, dur in self.custom_steps)
            return total if total > 0 else 1.0
        elif shape == "Constant DC": 
            return 1.0
        else:
            return self.safe_float(self.ent_per, 4.0)

    def _update_dynamic_ui(self, *args):
        period = self._get_current_period()
        shape = self.shape_var.get()
        if shape == "Pulse":
            try:
                b = float(self.pulse_base_var.get())
                p = float(self.pulse_peak_var.get())
                duty = (p / period) * 100 if period > 0 else 0
                self.lbl_duty.config(text=f"Duty Cycle: {duty:.1f}% | Total Period: {period:.3f}s")
            except: pass
        # Update cycles total time if needed
        self._on_cycles_changed()

    def _generate_waveform_arrays(self, pts):
        shape = self.shape_var.get()
        base = self.safe_float(self.ent_min, 0.005)
        peak = self.safe_float(self.ent_max, 0.040)
        period = self._get_current_period()
        
        if period <= 0: period = 1.0
        step_time = period / pts if pts > 0 else 1.0
        list_vals = []
        
        if shape == "Temple Run":
            tr_levels = [0.0, 0.0015, 0.010, 0.020, 0.030, 0.040, 0.030, 0.020, 0.010, 0.0015]
            tr_durs = [5.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
            cumulative_times = [sum(tr_durs[:i+1]) for i in range(len(tr_durs))]
            for tick in range(pts):
                t = tick * step_time
                for i, c_time in enumerate(cumulative_times):
                    if t < c_time + 1e-9:
                        list_vals.append(round(tr_levels[i], 6))
                        break
                else:
                    list_vals.append(round(tr_levels[-1], 6))
        
        elif shape == "Custom Pattern":
            if not self.custom_steps:
                return [], period
            steps = self.custom_steps
            boundaries = [0.0]
            for _, dur in steps:
                boundaries.append(boundaries[-1] + dur)
            for tick in range(pts):
                t = tick * step_time
                for i in range(len(steps)):
                    if boundaries[i] <= t < boundaries[i+1]:
                        list_vals.append(round(steps[i][0], 6))
                        break
                else:
                    list_vals.append(round(steps[-1][0], 6))
        
        elif "Custom" in shape:
            if not self.custom_list_vals: return [], period
            list_vals = self.custom_list_vals
            
        elif "Constant DC" in shape:
            list_vals = [base] * pts
            
        else:
            amp, off = (peak - base) / 2.0, (peak + base) / 2.0
            t_base = self.safe_float(self.pulse_base_var, 2.0)
            
            for tick in range(pts):
                t = tick * step_time
                if "Sine" in shape:    val = off - amp * math.cos(2 * math.pi * (t / period))
                elif "Cosine" in shape:val = off + amp * math.cos(2 * math.pi * (t / period))
                elif "Pulse" in shape: val = base if t < t_base else peak
                elif "Triangle" in shape:
                    if tick < pts/2: val = base + (peak - base) * (tick / (pts/2))
                    else:            val = peak - (peak - base) * ((tick - pts/2) / (pts/2))
                elif "Staircase" in shape: val = base + (peak - base) * (tick / pts)
                else: val = base
                list_vals.append(round(val, 6))

        return list_vals, period

    # ------------------------------------------------------------------
    # Preview Waveform (one cycle)
    # ------------------------------------------------------------------
    def _preview_waveform(self):
        """Open a new window showing one cycle of the current waveform."""
        shape = self.shape_var.get()
        period = self._get_current_period()
        if period <= 0:
            messagebox.showerror("Error", "Invalid period.")
            return
        # Get sampling rate
        sampling_rate = self.safe_float(self.ent_sampling, 100)
        if sampling_rate <= 0: sampling_rate = 100
        pts = int(sampling_rate * period)
        if pts < 2: pts = 2
        if pts > 5000: pts = 5000  # limit for preview

        list_vals, _ = self._generate_waveform_arrays(pts)
        if not list_vals:
            messagebox.showerror("Error", "Could not generate waveform. Check settings.")
            return

        # Create time array
        t = np.linspace(0, period, len(list_vals))

        # Create a new window with pyqtgraph
        win = QtWidgets.QMainWindow()
        win.setWindowTitle("Waveform Preview (One Cycle)")
        win.setGeometry(100, 100, 600, 400)
        central_widget = QtWidgets.QWidget()
        win.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        plot_widget = pg.PlotWidget()
        layout.addWidget(plot_widget)

        # Plot
        plot_widget.plot(t, list_vals, pen=pg.mkPen(color='b', width=2))
        plot_widget.setLabel('left', 'Level', units='A' if "Current" in self.src_mode_var.get() else 'V')
        plot_widget.setLabel('bottom', 'Time', units='s')
        plot_widget.setTitle(f"{shape} - Period = {period:.3f} s, Samples = {len(list_vals)}")

        # Show some stats
        stats = f"Min: {min(list_vals):.4g}, Max: {max(list_vals):.4g}, Mean: {np.mean(list_vals):.4g}"
        label = QtWidgets.QLabel(stats)
        label.setStyleSheet("font-family: Segoe UI; font-size: 10px; color: #2563eb;")
        layout.addWidget(label)

        win.show()
        # Keep reference to avoid garbage collection
        self._preview_window = win

    # ------------------------------------------------------------------
    # Hardware SMU Control Functions
    # ------------------------------------------------------------------
    def _visa_monitor_thread(self):
        while True:
            if not self.is_running:
                try:
                    ports = self.rm.list_resources()
                    self.root.after(0, self._update_ports_gui, ports)
                except: pass
            time.sleep(2)

    def _update_ports_gui(self, ports):
        self.visa_combo['values'] = ports
        if self.connected_port:
            if self.connected_port not in ports:
                self.lbl_status.config(text="Hardware Offline (Disconnected!)", fg=Theme.ERR)
                self.smu = None
            else:
                self.lbl_status.config(text=f"Online: {self.connected_port}", fg="#10b981")

    def _scan_visa(self):
        ports = self.rm.list_resources()
        self.visa_combo['values'] = ports
        if ports: self.visa_combo.set(ports[0])

    def _connect_smu(self):
        port = self.visa_combo.get()
        if not port: return
        try:
            self.smu = self.rm.open_resource(port)
            self.smu.timeout = 10000
            idn = self.smu.query("*IDN?").strip()
            self.connected_port = port
            self.lbl_status.config(text=f"Online: {idn.split(',')[1]}", fg="#10b981")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))

    def _send_scpi(self):
        if not self.smu:
            messagebox.showerror("Offline", "Please connect to the instrument first.")
            return
        cmd = self.ent_cmd.get().strip()
        if not cmd: return
        self.ent_cmd.delete(0, tk.END)
        self.txt_term.insert(tk.END, f"\n> {cmd}\n")
        try:
            if '?' in cmd:
                resp = self.smu.query(cmd)
                self.txt_term.insert(tk.END, f"{resp}\n")
            else:
                self.smu.write(cmd)
        except Exception as e:
            self.txt_term.insert(tk.END, f"ERROR: {str(e)}\n")
        self.txt_term.see(tk.END)

    def _load_custom_csv(self):
        path = filedialog.askopenfilename(filetypes=[("CSV Data", "*.csv")])
        if not path: return
        try:
            df = pd.read_csv(path, header=None)
            self.custom_list_vals = df.iloc[:, 0].dropna().tolist()
            self.lbl_custom.config(text=f"Loaded: {len(self.custom_list_vals)} points", fg=Theme.ACC)
        except Exception as e:
            messagebox.showerror("File Error", str(e))

    def _browse_save(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if path: self.save_var.set(path)

    def _stop_test(self):
        self.is_running = False
        self.manual_stop = True
        self.btn_start.config(state="normal", text="▶ START TEST")
        self.lbl_exp_status.config(text="ABORTING...", fg=Theme.ERR)
        if self.smu:
            try:
                self.smu.write(":ABOR") 
            except: pass

    def _update_timer_loop(self):
        if not self.is_running:
            return
            
        if self.inf_run_var.get():
            self.lbl_exp_time.config(text="Time Remaining: INFINITE (∞)")
            self.root.after(500, self._update_timer_loop)
            return

        elapsed = time.time() - self.test_start_time
        rem = max(0, self.test_target_duration - elapsed)
        
        mins, secs = divmod(int(rem), 60)
        self.lbl_exp_time.config(text=f"Time Remaining: {mins:02d}:{secs:02d}")
        
        if rem > 0:
            self.root.after(200, self._update_timer_loop)

    def _start_test(self):
        if not self.smu:
            messagebox.showwarning("Offline", "Please connect to the instrument.")
            return

        self.is_running = True
        self.manual_stop = False
        self.btn_start.config(state="disabled", text="TEST RUNNING...")
        
        self.nb_left.tab(1, state='disabled')
        
        inf_run = self.inf_run_var.get()
        if inf_run:
            self.test_target_duration = float('inf')
        else:
            # Check if cycles > 0 and total time is computed
            try:
                cycles = int(self.ent_cycles.get())
            except ValueError:
                cycles = 0
            if cycles > 0:
                period = self._get_current_period()
                self.test_target_duration = cycles * period + 2.0  # buffer 2s
                # Update total time entry (already disabled)
            else:
                try:
                    self.test_target_duration = float(self.ent_tot.get())
                except ValueError:
                    self.test_target_duration = 12.0
            
        self.test_start_time = time.time()
        self.lbl_exp_status.config(text="EXPERIMENT RUNNING...", fg="#f59e0b")
        self.lbl_exp_time.config(text="Time Remaining: --:--", fg=Theme.ACC)
        self._update_timer_loop()
        
        src_label = f"Sourced ({self.src_mode_var.get()})"
        msr_sel = self.msr_mode_var.get()
        msr_label = f"Measured ({msr_sel})"
        
        if "Auto" in msr_sel:
            msr_label = "Measured (Voltage (V))" if "Current" in self.src_mode_var.get() else "Measured (Current (A))"
        
        self.global_datasets.clear()
        self.registry_keys.clear()
        
        self.global_datasets["Live_Source"] = {
            "x": np.array([], dtype=float), "y": np.array([], dtype=float), 
            "color": TRACE_COLORS[0], "trace_name": src_label, "visible": True
        }
        self.global_datasets["Live_Measure"] = {
            "x": np.array([], dtype=float), "y": np.array([], dtype=float), 
            "color": TRACE_COLORS[3], "trace_name": msr_label, "visible": True
        }
        self.registry_keys.extend(["Live_Source", "Live_Measure"])
            
        self._refresh_listbox()
        self._update_selection_combos()
        self._update_layout_button_state()
        self._rebuild_charts()
        
        self.is_first_chunk = True

        threading.Thread(target=self._hardware_thread, daemon=True).start()
        self.root.after(50, self._gui_queue_processor)

    def _hardware_thread(self):
        try:
            mode_curr = "Current" in self.src_mode_var.get()
            comp = self.safe_float(self.ent_cmp, 10.0)
            off_mode = self.off_mode_var.get()
            inf_run = self.inf_run_var.get()
            msr_sel = self.msr_mode_var.get()
            
            sampling_rate = self.safe_float(self.ent_sampling, 100)
            if sampling_rate <= 0: sampling_rate = 100
            
            period = self._get_current_period()
            if period <= 0: period = 1.0
            pts = int(sampling_rate * period)
            if pts < 2: pts = 2
            if pts > 100000: pts = 100000
            
            # Total time and cycles handling
            if inf_run:
                total_ticks = float('inf')
            else:
                try:
                    cycles = int(self.ent_cycles.get())
                except ValueError:
                    cycles = 0
                if cycles > 0:
                    total_time = cycles * period + 2.0  # buffer
                else:
                    total_time = self.safe_float(self.ent_tot, 12.0)
                total_ticks = int(total_time / (period / pts)) if period > 0 else 0
            
            list_vals, period = self._generate_waveform_arrays(pts)
            if not list_vals:
                raise ValueError("Empty waveform array generated. Check your configuration.")
                
            step_time = period / pts
            initial_val = list_vals[0]
            final_val = list_vals[-1]
            max_val = max([abs(v) for v in list_vals])

            self.smu.write("*RST")
            self.smu.write("*CLS")
            
            self.smu.write(":SENS:REMO OFF")
            self.smu.write(":SENS:AVER:STAT OFF")
            
            src_str = "CURR" if mode_curr else "VOLT"
            msr_str = "VOLT" if mode_curr else "CURR"
            
            self.smu.write(f":SOUR:FUNC:MODE {src_str}")
            self.smu.write(f":SOUR:{src_str} {initial_val}") 
            
            self.smu.write(f":SOUR:{src_str}:MODE LIST")
            self.smu.write(f":SOUR:{src_str}:RANG {max_val}")
            self.smu.write(f":SOUR:LIST:{src_str} {','.join(map(str, list_vals))}")
            
            self.smu.write(":SENS:FUNC \"VOLT\",\"CURR\"")
            self.smu.write(f":SENS:{msr_str}:PROT {comp}")
            
            ap_val = max(1e-5, step_time * 0.5)
            self.smu.write(f":SENS:VOLT:APER {ap_val}")
            self.smu.write(f":SENS:CURR:APER {ap_val}")

            target_chunk_time = 0.25
            if "Constant DC" in self.shape_var.get():
                cycles_per_chunk = 1
            else:
                cycles_per_chunk = max(1, math.floor(target_chunk_time / period))
                
            ticks_per_chunk = int(cycles_per_chunk * pts)
            MAX_POINTS_PER_CHUNK = 20000 
            if ticks_per_chunk > MAX_POINTS_PER_CHUNK:
                cycles_per_chunk = max(1, MAX_POINTS_PER_CHUNK // pts)
                ticks_per_chunk = int(cycles_per_chunk * pts)

            if inf_run:
                num_chunks = float('inf')
            else:
                num_chunks = math.ceil(total_ticks / ticks_per_chunk)

            self.smu.write(":TRIG:TRAN:SOUR TIM")
            self.smu.write(f":TRIG:TRAN:TIM {step_time}")
            self.smu.write(":TRIG:ACQ:SOUR TIM")
            self.smu.write(f":TRIG:ACQ:TIM {step_time}")
            self.smu.write(":FORM:DATA ASC")

            save_file = self.save_var.get()
            csv_msr_label = f"Measured ({msr_sel})"
            if "Auto" in msr_sel:
                csv_msr_label = "Measured (Voltage (V))" if mode_curr else "Measured (Current (A))"
                
            with open(save_file, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(["Time (s)", f"Sourced ({src_str})", csv_msr_label])

            self.smu.write(":OUTP ON")
            global_t = 0.0
            chunk = 0

            while self.is_running:
                if not inf_run and chunk >= num_chunks:
                    break
                
                self.smu.write(":TRAC:CLE") 
                
                if inf_run:
                    t_count = ticks_per_chunk
                else:
                    t_count = min(ticks_per_chunk, total_ticks - chunk * ticks_per_chunk)
                    
                self.smu.write(f":TRIG:TRAN:COUN {t_count}")
                self.smu.write(f":TRIG:ACQ:COUN {t_count}")
                
                self.smu.write(":INIT:ACQ")
                self.smu.write(":INIT:TRAN")
                
                self.smu.timeout = int(((t_count * step_time) + 10) * 1000)
                self.smu.write("*WAI")
                
                if not self.is_running: break
                
                t = self.smu.query_ascii_values(":FETC:ARR:TIME?")
                c = self.smu.query_ascii_values(":FETC:ARR:CURR?")
                v = self.smu.query_ascii_values(":FETC:ARR:VOLT?")
                
                if not t: break
                
                chunk_start_time = t[0]
                t_rel = [(x - chunk_start_time) + global_t for x in t]
                
                v_arr = np.array(v)
                c_arr = np.array(c)
                
                if "Voltage" in msr_sel: msr_data = v_arr
                elif "Current" in msr_sel: msr_data = c_arr
                elif "Power" in msr_sel: msr_data = v_arr * c_arr
                elif "Resistance" in msr_sel: 
                    c_safe = np.where(c_arr == 0, 1e-12, c_arr)
                    msr_data = v_arr / c_safe
                else:
                    msr_data = v_arr if mode_curr else c_arr
                    
                src_data = c_arr if mode_curr else v_arr
                
                with open(save_file, 'a', newline='', encoding='utf-8') as f:
                    csv.writer(f).writerows(zip(t_rel, src_data, msr_data))
                
                self.data_queue.put((t_rel, src_data, msr_data))
                global_t += (t_count * step_time)
                chunk += 1

            if off_mode == "Hold Last Level":
                self.smu.write(f":SOUR:{src_str}:MODE FIX")
                self.smu.write(f":SOUR:{src_str} {final_val}") 
            elif off_mode == "Turn OFF (High-Z)":
                self.smu.write(f":SOUR:{src_str}:MODE FIX")
                self.smu.write(f":SOUR:{src_str} {final_val}")
                self.smu.write(":OUTP:OFF:MODE HIZ")
                self.smu.write(":OUTP OFF")
            else:
                self.smu.write(f":SOUR:{src_str}:MODE FIX")
                self.smu.write(f":SOUR:{src_str} {final_val}")
                self.smu.write(":OUTP:OFF:MODE NORM")
                self.smu.write(":OUTP OFF")
            
        except Exception as e:
            self.data_queue.put(Exception(str(e)))
        finally:
            self.is_running = False

    def _gui_queue_processor(self):
        try:
            while True:
                data = self.data_queue.get_nowait()
                if isinstance(data, Exception):
                    messagebox.showerror("Hardware Error", str(data))
                    break
                
                t_rel, src_data, msr_data = data
                
                ls = self.global_datasets["Live_Source"]
                lm = self.global_datasets["Live_Measure"]
                
                ls["x"] = np.concatenate([ls["x"], t_rel])
                ls["y"] = np.concatenate([ls["y"], src_data])
                lm["x"] = np.concatenate([lm["x"], t_rel])
                lm["y"] = np.concatenate([lm["y"], msr_data])

                if len(ls["x"]) > MAX_LIVE_PTS:
                    ls["x"] = ls["x"][-MAX_LIVE_PTS:]
                    ls["y"] = ls["y"][-MAX_LIVE_PTS:]
                    lm["x"] = lm["x"][-MAX_LIVE_PTS:]
                    lm["y"] = lm["y"][-MAX_LIVE_PTS:]

                for chart in self.charts:
                    chart.register_dataset("Live_Source", ls["x"], ls["y"], ls["color"], trace_name=ls["trace_name"])
                    chart.register_dataset("Live_Measure", lm["x"], lm["y"], lm["color"], trace_name=lm["trace_name"])
                    
                    if self.is_first_chunk:
                        chart.reset_global_viewport()
                    else:
                        span = chart.view_xmax - chart.view_xmin
                        chart.view_xmax = max(chart.view_xmax, t_rel[-1] + span*0.05)
                        chart.redraw()
                
                self.is_first_chunk = False
                self._reprocess_visible_window_metrics()
                
        except queue.Empty:
            pass

        if self.is_running:
            self.root.after(30, self._gui_queue_processor)
        else:
            self.btn_start.config(state="normal", text="▶ START TEST")
            self.nb_left.tab(1, state='normal') 
            if self.manual_stop:
                self.lbl_exp_status.config(text="EXPERIMENT ABORTED", fg=Theme.ERR)
                self.lbl_exp_time.config(text="Time Remaining: 00:00", fg=Theme.ERR)
            else:
                self.lbl_exp_status.config(text="EXPERIMENT FINISHED", fg="#10b981")
                self.lbl_exp_time.config(text="Time Remaining: 00:00", fg="#10b981")

    # ------------------------------------------------------------------
    # Theme & Analytics Methods
    # ------------------------------------------------------------------
    def _toggle_dark_mode(self):
        Theme.toggle()
        theme_map = Theme.LIGHT_TO_DARK if Theme.is_dark else Theme.DARK_TO_LIGHT
        
        def apply_theme_recursive(w):
            try: bg = w.cget('bg'); w.config(bg=theme_map[bg.lower()]) if bg.lower() in theme_map else None
            except: pass
            try: fg = w.cget('fg'); w.config(fg=theme_map[fg.lower()]) if fg.lower() in theme_map else None
            except: pass
            try: hb = w.cget('highlightbackground'); w.config(highlightbackground=theme_map[hb.lower()]) if hb.lower() in theme_map else None
            except: pass
            for child in w.winfo_children(): apply_theme_recursive(child)
                
        apply_theme_recursive(self.root)
        
        sty = ttk.Style()
        sty.configure('Sim.TNotebook', background=Theme.BG)
        sty.configure('Sim.TNotebook.Tab', background=Theme.PNL2, foreground=Theme.DIM)
        sty.map('Sim.TNotebook.Tab', background=[('selected', Theme.PNL)], foreground=[('selected', Theme.ACC)])

        sty.configure('Left.TNotebook', background=Theme.PNL)
        sty.configure('Left.TNotebook.Tab', background=Theme.PNL2, foreground=Theme.DIM)
        sty.map('Left.TNotebook.Tab', background=[('selected', Theme.PNL)], foreground=[('selected', Theme.ACC)])

        for chart in self.charts: chart.redraw()
        self._refresh_listbox()

    def _refresh_listbox(self):
        sel = self.line_registry_box.curselection()
        self.line_registry_box.delete(0, tk.END)
        for idx, d_id in enumerate(self.registry_keys):
            is_vis = self.global_datasets[d_id].get("visible", True)
            prefix = "👁 " if is_vis else "✕ [Hidden] "
            self.line_registry_box.insert(tk.END, f"{prefix}{d_id}")
            if not is_vis: self.line_registry_box.itemconfig(idx, fg=Theme.DIM)
        if sel: self.line_registry_box.selection_set(sel[0])

    def _on_listbox_select(self, event):
        pass

    def _show_listbox_context_menu(self, event):
        try:
            index = self.line_registry_box.nearest(event.y)
            self.line_registry_box.selection_clear(0, tk.END)
            self.line_registry_box.selection_set(index)
            self.line_registry_box.activate(index)
            
            bbox = self.line_registry_box.bbox(index)
            if bbox and bbox[1] <= event.y <= bbox[1] + bbox[3]:
                self.context_menu.tk_popup(event.x_root, event.y_root)
                self._on_listbox_select(None)
        finally:
            self.context_menu.grab_release()

    def _reconfigure_selected_line(self):
        sel = self.line_registry_box.curselection()
        if not sel: return
        d_id = self.registry_keys[sel[0]]
        ds = self.global_datasets.get(d_id)
        if not ds or "df" not in ds: return
        DataImportDialog(self.root, ds["df"], ds["filename"], self._on_import_confirmed, existing_id=d_id, existing_config=ds)

    def _purge_selected_line(self):
        sel = self.line_registry_box.curselection()
        if not sel: return
        d_id = self.registry_keys[sel[0]]
        del self.registry_keys[sel[0]]
        if d_id in self.global_datasets: del self.global_datasets[d_id]
        
        keys_to_delete = [k for k in self.global_math if k.startswith(d_id)]
        for k in keys_to_delete: del self.global_math[k]

        self._refresh_listbox()
        self._update_selection_combos()
        self._update_layout_button_state()
        self._rebuild_charts()
        self._on_listbox_select(None)

    def _toggle_visibility(self):
        sel = self.line_registry_box.curselection()
        if not sel: return
        d_id = self.registry_keys[sel[0]]
        is_visible = self.global_datasets[d_id].get("visible", True)
        self.global_datasets[d_id]["visible"] = not is_visible
        
        self._refresh_listbox()
        self._update_layout_button_state()
        self._rebuild_charts()

    def _browse_and_load_csv(self):
        path = filedialog.askopenfilename(filetypes=[('CSV Datasets', '*.csv'), ('All Files', '*.*')])
        if not path: return
        try:
            df = pd.read_csv(path, sep=None, engine='python', on_bad_lines='warn')
            df.columns = [str(c).strip() for c in df.columns]
            filename = os.path.basename(path)
            
            d_id = filename
            counter = 1
            while d_id in self.global_datasets:
                d_id = f"{filename} ({counter})"
                counter += 1
                
            self.registry_keys.append(d_id)
            self.global_datasets[d_id] = {
                "x": df.iloc[:, 0].values, 
                "y": df.iloc[:, 1].values, 
                "color": TRACE_COLORS[len(self.registry_keys) % len(TRACE_COLORS)], 
                "trace_name": d_id, 
                "visible": True
            }
            self._refresh_listbox()
            self._update_selection_combos()
            self._update_layout_button_state()
            self._rebuild_charts()
            
        except Exception as ex:
            messagebox.showerror('Parsing Error', f"Could not process file:\n{str(ex)}")

    def _on_import_confirmed(self, filename, df, x_col, y_col, start_row, end_row, trace_name, scale, line_style, existing_id=None):
        pass

    def _update_selection_combos(self):
        vals = [self.global_datasets[k]["trace_name"] for k in self.registry_keys]
        self.math_combo['values'] = vals
        if vals: self.math_combo.current(0)
        else: self.math_target_var.set("")

    def _open_chart_properties(self, chart):
        ChartPropertiesDialog(self.root, chart, chart.chart_key, self._apply_chart_properties)

    def _apply_chart_properties(self, chart_key, props, trace_names):
        self.chart_configs[chart_key] = props
        for t_id, new_name in trace_names.items():
            if t_id in self.global_datasets: self.global_datasets[t_id]["trace_name"] = new_name
            elif t_id in self.global_math: self.global_math[t_id]["trace_name"] = new_name
        self._rebuild_charts()

    def _rebuild_charts(self):
        for chart in self.charts:
            chart._frame.destroy()
        self.charts.clear()

        for i in range(10):
            self.chart_container.rowconfigure(i, weight=0)
            self.chart_container.columnconfigure(i, weight=0)

        vis_datasets = {k: v for k, v in self.global_datasets.items() if v.get("visible", True)}
        n = len(vis_datasets)
        
        if n <= 1 or self.view_mode == "OVERLAY":
            chart = AdvancedAnalysisCanvas(self.chart_container, chart_key="OVERLAY", on_view_changed_callback=self._reprocess_visible_window_metrics, on_edit_request_callback=self._open_chart_properties, title="Combined Trace Overlay" if n > 0 else "Waiting for Data...")
            chart._frame.grid(row=0, column=0, sticky='nsew')
            self.chart_container.rowconfigure(0, weight=1)
            self.chart_container.columnconfigure(0, weight=1)
            
            for d_id, data in vis_datasets.items():
                chart.register_dataset(d_id, data["x"], data["y"], data["color"], style=data.get("line_style", "Solid"), trace_name=data.get("trace_name", d_id))
            
            for t_id, m_data in self.global_math.items():
                parent_id = t_id.replace("_diff", "").replace("_int", "")
                if self.global_datasets.get(parent_id, {}).get("visible", True):
                    chart.add_analysis_trace(t_id, m_data["x"], m_data["y"], m_data["color"], style=m_data.get("style", "Dashed"), trace_name=m_data.get("trace_name", t_id))
            
            self.charts.append(chart)

        else:
            if n == 2: rows, cols = 1, 2
            elif n <= 4: rows, cols = 2, 2
            elif n <= 6: rows, cols = 2, 3
            else: rows, cols = 3, 3 

            for i in range(rows): self.chart_container.rowconfigure(i, weight=1)
            for j in range(cols): self.chart_container.columnconfigure(j, weight=1)

            idx = 0
            for d_id, data in vis_datasets.items():
                r, c = divmod(idx, cols)
                chart = AdvancedAnalysisCanvas(self.chart_container, chart_key=d_id, on_view_changed_callback=self._reprocess_visible_window_metrics, on_edit_request_callback=self._open_chart_properties, title=data.get("trace_name", d_id))
                chart._frame.grid(row=r, column=c, sticky='nsew', padx=4, pady=4)
                chart.register_dataset(d_id, data["x"], data["y"], data["color"], style=data.get("line_style", "Solid"), trace_name=data.get("trace_name", d_id))
                
                for t_id, m_data in self.global_math.items():
                    if t_id.startswith(d_id):
                        chart.add_analysis_trace(t_id, m_data["x"], m_data["y"], m_data["color"], style=m_data.get("style", "Dashed"), trace_name=m_data.get("trace_name", t_id))
                
                self.charts.append(chart)
                idx += 1
                if idx >= rows * cols: break 

        for chart in self.charts:
            config = self.chart_configs.get(chart.chart_key, {})
            chart.title = config.get("title", chart.title)
            chart.x_label = config.get("x_label", "")
            chart.y_label = config.get("y_label", "")
            chart.y_min_override = config.get("y_min", None)
            chart.y_max_override = config.get("y_max", None)
            chart.reset_global_viewport()

        if self.charts: self.charts[0].canvas.focus_set()
        self._reprocess_visible_window_metrics()

    def _toggle_layout_mode(self):
        vis_count = sum(1 for v in self.global_datasets.values() if v.get("visible", True))
        if vis_count <= 1: return
        
        if self.view_mode == "OVERLAY":
            self.view_mode = "GRID"
            txt = "⬒  Merge to Overlay"
        else:
            self.view_mode = "OVERLAY"
            txt = "🗖  Split to Grid View"
            
        if hasattr(self, 'btn_layout_ana'): self.btn_layout_ana.config(text=txt)
        if hasattr(self, 'btn_layout_smu'): self.btn_layout_smu.config(text=txt)
        
        self._rebuild_charts()

    def _update_layout_button_state(self):
        vis_count = sum(1 for v in self.global_datasets.values() if v.get("visible", True))
        if vis_count > 1: 
            if hasattr(self, 'btn_layout_ana'): self.btn_layout_ana.config(state='normal')
            if hasattr(self, 'btn_layout_smu'): self.btn_layout_smu.config(state='normal')
        else:
            self.view_mode = "OVERLAY"
            txt = "🗖  Split to Grid View"
            if hasattr(self, 'btn_layout_ana'): self.btn_layout_ana.config(text=txt, state='disabled')
            if hasattr(self, 'btn_layout_smu'): self.btn_layout_smu.config(text=txt, state='disabled')

    def _run_derivative_pipeline(self):
        idx = self.math_combo.current()
        if idx < 0 or idx >= len(self.registry_keys): return
        target = self.registry_keys[idx]
        trace = self.global_datasets[target]
        dx, dy = MathEngine.compute_derivative(trace["x"], trace["y"])
        self.global_math[f"{target}_diff"] = {"x": dx, "y": dy, "color": '#dc2626', "style": "Dashed", "trace_name": f"d/dx ({trace['trace_name']})"}
        self._rebuild_charts()

    def _run_integral_pipeline(self):
        idx = self.math_combo.current()
        if idx < 0 or idx >= len(self.registry_keys): return
        target = self.registry_keys[idx]
        trace = self.global_datasets[target]
        ix, iy = MathEngine.compute_integral(trace["x"], trace["y"])
        self.global_math[f"{target}_int"] = {"x": ix, "y": iy, "color": '#10b981', "style": "Dotted", "trace_name": f"∫ ({trace['trace_name']})"}
        self._rebuild_charts()

    def _clear_math_traces(self):
        self.global_math.clear()
        self._rebuild_charts()

    def _reset_chart_bounds(self):
        for chart in self.charts: chart.reset_global_viewport()

    def _reprocess_visible_window_metrics(self):
        if self._stats_timer: self.root.after_cancel(self._stats_timer)
        self._stats_timer = self.root.after(100, self._calculate_metrics_task)

    def _calculate_metrics_task(self):
        vis_pool = []
        for chart in self.charts:
            for trace in chart.datasets.values():
                tx, ty = trace["x"], trace["y"]
                if len(tx) == 0: continue
                s_idx = np.searchsorted(tx, chart.view_xmin)
                e_idx = np.searchsorted(tx, chart.view_xmax)
                if s_idx < e_idx: vis_pool.append(ty[s_idx:e_idx])

        if not vis_pool:
            for k in self.metric_boxes: self.metric_boxes[k].config(text="--")
            self.metric_boxes['count'].config(text="0")
            return

        vector = np.concatenate(vis_pool)
        self.metric_boxes['min'].config(text=f"{vector.min():.4g}")
        self.metric_boxes['max'].config(text=f"{vector.max():.4g}")
        self.metric_boxes['mean'].config(text=f"{vector.mean():.4g}")
        self.metric_boxes['std'].config(text=f"{vector.std():.4g}")
        self.metric_boxes['count'].config(text=f"{len(vector):,}")

# ------------------------------------------------------------------------
# Startup Context
# ------------------------------------------------------------------------
if __name__ == '__main__':
    set_hd_resolution()
    root = tk.Tk()
    app = App(root)
    root.mainloop()