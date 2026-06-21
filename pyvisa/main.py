import sys
import os
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, simpledialog
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
        self.geometry("600x700")
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
        container.pack(fill='both', expand=True, padx=12, pady=12)

        lbl_frm = tk.LabelFrame(container, text=" Axis Labels & Titles ", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 10, 'bold'))
        lbl_frm.pack(fill='x', padx=10, pady=10)

        tk.Label(lbl_frm, text="Chart Title:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.ent_title = tk.Entry(lbl_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=30, font=('Segoe UI', 9))
        self.ent_title.insert(0, self.chart.title)
        self.ent_title.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(lbl_frm, text="X-Axis Label:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=1, column=0, padx=5, pady=5, sticky='e')
        self.ent_xlabel = tk.Entry(lbl_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=30, font=('Segoe UI', 9))
        self.ent_xlabel.insert(0, self.chart.x_label)
        self.ent_xlabel.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(lbl_frm, text="Y-Axis Label:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=2, column=0, padx=5, pady=5, sticky='e')
        self.ent_ylabel = tk.Entry(lbl_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=30, font=('Segoe UI', 9))
        self.ent_ylabel.insert(0, self.chart.y_label)
        self.ent_ylabel.grid(row=2, column=1, padx=5, pady=5)

        scale_frm = tk.LabelFrame(container, text=" Fixed Y-Axis Scale Bounds ", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 10, 'bold'))
        scale_frm.pack(fill='x', padx=10, pady=5)

        tk.Label(scale_frm, text="Y-Min:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=0, column=0, padx=5, pady=5, sticky='e')
        self.ent_ymin = tk.Entry(scale_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=15, font=('Segoe UI', 9))
        if self.chart.y_min_override is not None: self.ent_ymin.insert(0, str(self.chart.y_min_override))
        self.ent_ymin.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(scale_frm, text="Y-Max:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=0, column=2, padx=5, pady=5, sticky='e')
        self.ent_ymax = tk.Entry(scale_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=15, font=('Segoe UI', 9))
        if self.chart.y_max_override is not None: self.ent_ymax.insert(0, str(self.chart.y_max_override))
        self.ent_ymax.grid(row=0, column=3, padx=5, pady=5)

        trace_frm = tk.LabelFrame(container, text=" Edit Trace Names (Legend) ", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 10, 'bold'))
        trace_frm.pack(fill='both', expand=True, padx=10, pady=10)

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
                col_box.grid(row=row_idx, column=0, padx=5, pady=4)
                
                tk.Label(tr_container, text=f"ID: {t_id[:15]}...", bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 9)).grid(row=row_idx, column=1, padx=5, sticky='w')
                
                ent_name = tk.Entry(tr_container, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=25, font=('Segoe UI', 9))
                ent_name.insert(0, trace.get("trace_name", t_id))
                ent_name.grid(row=row_idx, column=2, padx=5, pady=4)
                
                self.trace_entries[t_id] = ent_name
                row_idx += 1

        btn_frm = tk.Frame(container, bg=Theme.PNL)
        btn_frm.pack(fill='x', padx=10, pady=10)

        tk.Button(btn_frm, text="Apply Chart Properties", bg=Theme.ACC, fg='#ffffff', font=('Segoe UI', 10, 'bold'), relief='flat', padx=15, pady=5, command=self._apply).pack(side='right', padx=5)
        tk.Button(btn_frm, text="Cancel", bg=Theme.PNL2, fg=Theme.FG, font=('Segoe UI', 10), relief='flat', padx=15, pady=5, command=self.destroy).pack(side='right', padx=5)

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
        tk.Label(self.tw, text=text, bg=Theme.PNL2, fg=Theme.FG, relief='solid', borderwidth=1, font=("Segoe UI", 9)).pack(padx=4, pady=2)

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
        self.pad_l, self.pad_r = 95, 25
        self.pad_t = 45 if title else 30
        self.pad_b = 65  
        self.num_grid = 5

        self.datasets, self.analysis_layers, self.labels = {}, {}, []
        self.view_xmin = self.view_xmax = self.view_ymin = self.view_ymax = 0.0
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
        menu = tk.Menu(self.canvas, tearoff=0, bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10))
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
        self.tt_txt = self.canvas.create_text(0,0, text='', anchor='nw', fill='#ffffff', font=('Segoe UI', 10, 'bold'), state='hidden', tags='hover')

    def register_dataset(self, d_id, x, y, color, style="Solid", trace_name=""):
        self.datasets[d_id] = {"x": np.asarray(x, dtype=float), "y": np.asarray(y, dtype=float), "color": color, "style": style, "trace_name": trace_name or d_id}

    def add_analysis_trace(self, t_id, x, y, color, style="Dashed", trace_name=""):
        self.analysis_layers[t_id] = {"x": np.asarray(x, dtype=float), "y": np.asarray(y, dtype=float), "color": color, "style": style, "trace_name": trace_name}

    def reset_global_viewport(self):
        if not self.datasets and not self.analysis_layers:
            self.redraw(); return
        
        all_xmin, all_xmax, all_ymin, all_ymax = np.inf, -np.inf, np.inf, -np.inf

        for layer in [self.datasets, self.analysis_layers]:
            for d in layer.values():
                if len(d["x"]) == 0: continue
                all_xmin, all_xmax = min(all_xmin, d["x"].min()), max(all_xmax, d["x"].max())
                all_ymin, all_ymax = min(all_ymin, d["y"].min()), max(all_ymax, d["y"].max())

        if all_xmin == np.inf: return

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
            self.canvas.create_text(self.pad_l - 10, 20, text=self.title, fill=Theme.ACC, font=('Segoe UI', 11, 'bold'), anchor='w', tags='grid')
        if self.x_label:
            self.canvas.create_text(self.pad_l + self.cw/2, self.h - 15, text=self.x_label, fill=Theme.FG, font=('Segoe UI', 10, 'bold'), anchor='s', tags='grid')
        if self.y_label:
            self.canvas.create_text(20, self.pad_t + self.ch/2, text=self.y_label, fill=Theme.FG, font=('Segoe UI', 10, 'bold'), angle=90, anchor='s', tags='grid')

        for k in range(self.num_grid + 1):
            frac = k / self.num_grid
            gx, gy = self.pad_l + self.cw * frac, self.pad_t + self.ch * frac
            
            self.canvas.create_line(self.pad_l, gy, self.w - self.pad_r, gy, fill=Theme.SEP, tags='grid')
            self.canvas.create_text(self.pad_l - 8, gy, text=f"{self.view_ymax - (self.view_ymax - self.view_ymin) * frac:.3g}", anchor='e', font=('Segoe UI', 9), fill=Theme.DIM, tags='grid')

            self.canvas.create_line(gx, self.pad_t, gx, self.h - self.pad_b, fill=Theme.SEP, tags='grid')
            self.canvas.create_text(gx, self.h - self.pad_b + 8, text=f"{self.view_xmin + (self.view_xmax - self.view_xmin) * frac:.3g}", anchor='n', font=('Segoe UI', 9), fill=Theme.DIM, tags='grid')

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
                self.canvas.create_line(*coords.tolist(), fill=trace["color"], width=2.0, dash=style, tags='trace', joinstyle=tk.ROUND)

        items = list(self.datasets.items()) + list(self.analysis_layers.items())
        if items:
            lx, ly = self.w - self.pad_r - 200, self.pad_t + 10
            box_h = len(items) * 22 + 10
            self.canvas.create_rectangle(lx - 10, ly - 5, lx + 190, ly + box_h - 5, fill=Theme.PNL, outline=Theme.BRD, tags='trace')
            for d_id, trace in items:
                style = dash_map.get(trace.get("style", "Solid"), None)
                name = trace.get("trace_name")[:22] + "..." if len(trace.get("trace_name")) > 22 else trace.get("trace_name")
                self.canvas.create_line(lx, ly + 10, lx + 30, ly + 10, fill=trace["color"], width=2, dash=style, tags='trace')
                self.canvas.create_text(lx + 40, ly + 10, text=name, fill=Theme.FG, font=('Segoe UI', 9, 'bold'), anchor='w', tags='trace')
                ly += 22

        for lbl in self.labels:
            lx, ly = self._cx(lbl["x"]), self._cy(lbl["y"])
            if self.pad_l <= lx <= self.w - self.pad_r and self.pad_t <= ly <= self.h - self.pad_b:
                self.canvas.create_oval(lx-5, ly-5, lx+5, ly+5, fill='#10b981', outline='#ffffff', tags='trace')
                self.canvas.create_text(lx+10, ly-10, text=lbl["text"], anchor='sw', font=('Segoe UI', 9, 'bold'), fill=Theme.FG, tags='trace')

        self._render_markers()
        if self.on_view_changed: self.on_view_changed()

    def _render_markers(self):
        pts = [p for p in [self.m1, self.m2] if p]
        for p in pts:
            cx, cy = self._cx(p[0]), self._cy(p[1])
            self.canvas.create_oval(cx-6, cy-6, cx+6, cy+6, fill=Theme.C_MARK, outline='#ffffff', width=2, tags='trace')

        if len(pts) == 2:
            cx1, cy1 = self._cx(pts[0][0]), self._cy(pts[0][1])
            cx2, cy2 = self._cx(pts[1][0]), self._cy(pts[1][1])
            self.canvas.create_line(cx1, cy1, cx2, cy2, fill=Theme.C_MARK, width=2, dash=(4, 4), tags='trace')

            dx, dy = pts[1][0] - pts[0][0], pts[1][1] - pts[0][1]
            slope = dy / dx if dx != 0 else float('inf')
            report = f"ΔX: {dx:.4g} | ΔY: {dy:.4g} | ∠: {math.degrees(math.atan2(dy, dx)):.1f}°"
            mid_x, mid_y = (cx1 + cx2) / 2, min(cy1, cy2) - 20
            
            self.canvas.create_rectangle(mid_x-130, mid_y-12, mid_x+130, mid_y+12, fill='#1e293b', outline=Theme.C_MARK, tags='trace')
            self.canvas.create_text(mid_x, mid_y, text=report, fill='#ffffff', font=('Segoe UI', 9, 'bold'), tags='trace')

# ------------------------------------------------------------------------
# 5. Global State & App Shell (Master Controller)
# ------------------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.root.title("Keysight B2910CL Precision Control & Analytics Dashboard")
        self.root.configure(bg=Theme.BG)
        self.root.geometry("1400x850")
        self.root.minsize(1200, 700)

        self._build_top_menu()

        # SMU Hardware Variables
        self.rm = pyvisa.ResourceManager()
        self.smu = None
        self.connected_port = None
        self.is_running = False
        self.data_queue = queue.Queue()
        self.is_first_chunk = True
        self.custom_list_vals = []

        # Graphing Variables
        self.global_datasets = {}
        self.global_math = {}
        self.registry_keys = []  
        self.charts = []
        self.chart_configs = {}  
        self.view_mode = "OVERLAY"
        self._stats_timer = None  
        
        self.btn_layout_smu = None
        self.btn_layout_ana = None

        self._build_ui_shell()
        self._rebuild_charts()
        
        # Start Background Visa Scanner
        threading.Thread(target=self._visa_monitor_thread, daemon=True).start()

    def _build_top_menu(self):
        menubar = tk.Menu(self.root)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Dark/Light Mode", command=self._toggle_dark_mode)
        menubar.add_cascade(label="View", menu=view_menu)
        self.root.config(menu=menubar)

    def _build_ui_shell(self):
        # -- TOP HEADER --
        tb = tk.Frame(self.root, bg=Theme.PNL, height=50, relief='flat')
        tb.pack(fill='x', side='top')
        tk.Frame(self.root, bg=Theme.BRD, height=1).pack(fill='x', side='top')
        tb.pack_propagate(False)

        tk.Label(tb, text='B2910CL MASTER SYSTEM', bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 13, 'bold')).pack(side='left', padx=15)
        tk.Frame(tb, bg=Theme.BRD, width=1).pack(side='left', fill='y', pady=8)
        self.lbl_status = tk.Label(tb, text='Hardware Offline', bg=Theme.PNL, fg=Theme.ERR, font=('Segoe UI', 11, 'bold'))
        self.lbl_status.pack(side='left', padx=15)

        # -- MAIN BODY --
        body = tk.Frame(self.root, bg=Theme.BG)
        body.pack(fill='both', expand=True)

        # -- LEFT PANEL (Fixed Width: 420px) --
        left = tk.Frame(body, bg=Theme.PNL, width=420, relief='flat')
        left.pack(side='left', fill='y')
        left.pack_propagate(False)
        tk.Frame(body, bg=Theme.BRD, width=1).pack(side='left', fill='y')

        left_top = tk.Frame(left, bg=Theme.PNL)
        left_top.pack(side='top', fill='both', expand=True)
        
        left_bottom = tk.Frame(left, bg=Theme.PNL)
        left_bottom.pack(side='bottom', fill='x')

        style = ttk.Style()
        style.theme_use('default')
        style.configure('Left.TNotebook', background=Theme.PNL, borderwidth=0)
        style.configure('Left.TNotebook.Tab', font=('Segoe UI', 10, 'bold'), padding=[12, 6], background=Theme.PNL2, foreground=Theme.DIM)
        style.map('Left.TNotebook.Tab', background=[('selected', Theme.PNL)], foreground=[('selected', Theme.ACC)])

        nb_left = ttk.Notebook(left_top, style='Left.TNotebook')
        nb_left.pack(fill='both', expand=True)

        # Tabs
        tab_smu = VerticalScrollFrame(nb_left)
        tab_ana = tk.Frame(nb_left, bg=Theme.PNL)
        tab_scpi = tk.Frame(nb_left, bg=Theme.PNL)
        
        nb_left.add(tab_smu, text="🔌 SMU Setup")
        nb_left.add(tab_ana, text="📊 Analytics")
        nb_left.add(tab_scpi, text="💻 SCPI Terminal")
        
        def sec(parent, title):
            tk.Frame(parent, bg=Theme.SEP, height=1).pack(fill='x')
            f = tk.Frame(parent, bg=Theme.PNL)
            f.pack(fill='x', padx=15, pady=8)
            tk.Label(f, text=title, bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 9, 'bold')).pack(anchor='w', pady=(2, 6))
            return f

        # ==========================================
        # TAB 1: SMU SETUP
        # ==========================================
        smu_inner = tab_smu.inner
        conn_sec = sec(smu_inner, "HARDWARE CONNECTION")
        self.visa_combo = ttk.Combobox(conn_sec, state='readonly', font=('Segoe UI', 10))
        self.visa_combo.pack(fill='x', pady=2)
        btn_frm = tk.Frame(conn_sec, bg=Theme.PNL)
        btn_frm.pack(fill='x', pady=4)
        tk.Button(btn_frm, text="Manual Scan", bg=Theme.PNL2, fg=Theme.FG, relief='flat', font=('Segoe UI', 9, 'bold'), command=self._scan_visa).pack(side='left', fill='x', expand=True, padx=(0,4))
        self.btn_conn = tk.Button(btn_frm, text="Connect Hardware", bg=Theme.PNL2, fg=Theme.FG, relief='flat', font=('Segoe UI', 9, 'bold'), command=self._connect_smu)
        self.btn_conn.pack(side='right', fill='x', expand=True, padx=(4,0))

        cfg_sec = sec(smu_inner, "TEST CONFIGURATION")
        
        self.src_mode_var = tk.StringVar(value="Current (A)")
        tk.Label(cfg_sec, text="Source Mode:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10)).pack(anchor='w')
        cb_src = ttk.Combobox(cfg_sec, textvariable=self.src_mode_var, values=["Current (A)", "Voltage (V)"], state="readonly", font=('Segoe UI', 10))
        cb_src.pack(fill='x', pady=(0,6))
        
        self.msr_mode_var = tk.StringVar(value="Auto (Opposite)")
        tk.Label(cfg_sec, text="Primary Measurement Display:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10)).pack(anchor='w')
        cb_msr = ttk.Combobox(cfg_sec, textvariable=self.msr_mode_var, values=["Auto (Opposite)", "Voltage (V)", "Current (A)", "Resistance (Ω)", "Power (W)"], state="readonly", font=('Segoe UI', 10))
        cb_msr.pack(fill='x', pady=(0,6))

        self.shape_var = tk.StringVar(value="Square (Pulse)")
        tk.Label(cfg_sec, text="Waveform Shape:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10)).pack(anchor='w')
        cb_shape = ttk.Combobox(cfg_sec, textvariable=self.shape_var, values=["Sine Wave", "Cosine Wave", "Square (Pulse)", "Triangle", "Staircase", "Custom (CSV List)"], state="readonly", font=('Segoe UI', 10))
        cb_shape.pack(fill='x', pady=(0,6))
        
        self.dynamic_params = tk.Frame(cfg_sec, bg=Theme.PNL)
        self.dynamic_params.pack(fill='x', pady=(0,0))
        
        self.lbl_min = tk.Label(self.dynamic_params, text="Base/Min Level (A):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10))
        self.lbl_min.grid(row=0, column=0, sticky='w', pady=2)
        self.ent_min = tk.Entry(self.dynamic_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 10), width=15)
        self.ent_min.insert(0, "0.005")
        self.ent_min.grid(row=0, column=1, sticky='e', pady=2)

        self.lbl_max = tk.Label(self.dynamic_params, text="Peak/Max Level (A):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10))
        self.lbl_max.grid(row=1, column=0, sticky='w', pady=2)
        self.ent_max = tk.Entry(self.dynamic_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 10), width=15)
        self.ent_max.insert(0, "0.040")
        self.ent_max.grid(row=1, column=1, sticky='e', pady=2)

        self.lbl_cmp = tk.Label(self.dynamic_params, text="Compliance Limit (V):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10))
        self.lbl_cmp.grid(row=2, column=0, sticky='w', pady=2)
        self.ent_cmp = tk.Entry(self.dynamic_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 10), width=15)
        self.ent_cmp.insert(0, "10.0")
        self.ent_cmp.grid(row=2, column=1, sticky='e', pady=2)
        
        def _update_units(*args):
            is_curr = "Current" in self.src_mode_var.get()
            u_src = "A" if is_curr else "V"
            u_cmp = "V" if is_curr else "A"
            self.lbl_min.config(text=f"Base/Min Level ({u_src}):")
            self.lbl_max.config(text=f"Peak/Max Level ({u_src}):")
            self.lbl_cmp.config(text=f"Compliance Limit ({u_cmp}):")
        self.src_mode_var.trace_add('write', _update_units)
        
        self.time_frame_std = tk.Frame(cfg_sec, bg=Theme.PNL)
        self.time_frame_pls = tk.Frame(cfg_sec, bg=Theme.PNL)
        self.time_frame_csv = tk.Frame(cfg_sec, bg=Theme.PNL)
        
        tk.Label(self.time_frame_std, text="Cycle Period (s):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w', pady=2)
        self.ent_per = tk.Entry(self.time_frame_std, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 10), width=15)
        self.ent_per.insert(0, "4.0")
        self.ent_per.grid(row=0, column=1, sticky='e', pady=2)
        
        self.pulse_base_var = tk.StringVar(value="2.0")
        self.pulse_peak_var = tk.StringVar(value="2.0")
        tk.Label(self.time_frame_pls, text="Time at Base (s):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w', pady=2)
        tk.Entry(self.time_frame_pls, textvariable=self.pulse_base_var, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 10), width=15).grid(row=0, column=1, sticky='e', pady=2)
        tk.Label(self.time_frame_pls, text="Time at Peak (s):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10)).grid(row=1, column=0, sticky='w', pady=2)
        tk.Entry(self.time_frame_pls, textvariable=self.pulse_peak_var, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 10), width=15).grid(row=1, column=1, sticky='e', pady=2)
        
        self.lbl_duty = tk.Label(self.time_frame_pls, text="Duty: 50.0% | Period: 4.0s", bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 9, 'bold'))
        self.lbl_duty.grid(row=2, column=0, columnspan=2, sticky='e', pady=2)
        
        def _update_duty(*args):
            try:
                b = float(self.pulse_base_var.get())
                p = float(self.pulse_peak_var.get())
                t = b + p
                duty = (p / t) * 100 if t > 0 else 0
                self.lbl_duty.config(text=f"Duty Cycle: {duty:.1f}% | Total Period: {t:.3f}s")
            except: pass
        self.pulse_base_var.trace_add('write', _update_duty)
        self.pulse_peak_var.trace_add('write', _update_duty)
        
        tk.Button(self.time_frame_csv, text="Browse Custom CSV List...", bg=Theme.PNL2, fg=Theme.ACC, font=('Segoe UI', 9, 'bold'), relief='flat', command=self._load_custom_csv).pack(fill='x', pady=2)
        self.lbl_custom = tk.Label(self.time_frame_csv, text="No File Loaded.", bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 9))
        self.lbl_custom.pack(anchor='w')

        self.bottom_params = tk.Frame(cfg_sec, bg=Theme.PNL)
        self.bottom_params.pack(fill='x', pady=(0,0))
        tk.Label(self.bottom_params, text="Points/Cycle (Res):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10)).grid(row=0, column=0, sticky='w', pady=2)
        self.ent_pts = tk.Entry(self.bottom_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 10), width=15)
        self.ent_pts.insert(0, "360")
        self.ent_pts.grid(row=0, column=1, sticky='e', pady=2)
        
        tk.Label(self.bottom_params, text="Total Test Time (s):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10)).grid(row=1, column=0, sticky='w', pady=2)
        self.ent_tot = tk.Entry(self.bottom_params, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 10), width=15)
        self.ent_tot.insert(0, "12.0")
        self.ent_tot.grid(row=1, column=1, sticky='e', pady=2)

        def _swap_ui(*args):
            shape = self.shape_var.get()
            self.time_frame_std.pack_forget()
            self.time_frame_pls.pack_forget()
            self.time_frame_csv.pack_forget()
            if "Pulse" in shape: self.time_frame_pls.pack(fill='x', after=self.dynamic_params)
            elif "Custom" in shape: self.time_frame_csv.pack(fill='x', after=self.dynamic_params)
            else: self.time_frame_std.pack(fill='x', after=self.dynamic_params)
        self.shape_var.trace_add('write', _swap_ui)
        _swap_ui()

        adv_sec = sec(smu_inner, "ADVANCED SETTINGS")
        self.avg_var = tk.BooleanVar(value=False)
        tk.Checkbutton(adv_sec, text="Enable Hardware Averaging", variable=self.avg_var, bg=Theme.PNL, fg=Theme.FG, selectcolor=Theme.PNL2, font=('Segoe UI', 10)).pack(anchor='w', pady=(0,2))
        self.wire_var = tk.BooleanVar(value=False)
        tk.Checkbutton(adv_sec, text="4-Wire Kelvin Sensing", variable=self.wire_var, bg=Theme.PNL, fg=Theme.FG, selectcolor=Theme.PNL2, font=('Segoe UI', 10)).pack(anchor='w', pady=(0,4))
        
        tk.Label(adv_sec, text="Aperture (Integration):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10)).pack(anchor='w')
        self.aperture_var = tk.StringVar(value="Auto")
        ttk.Combobox(adv_sec, textvariable=self.aperture_var, values=["Auto", "1e-5 (10 µs High-Speed)"], state="readonly", font=('Segoe UI', 10)).pack(fill='x', pady=(0,4))

        sys_sec_smu = sec(smu_inner, "VIEWPORT CONTROL")
        self.btn_layout_smu = tk.Button(sys_sec_smu, text='🗖  Split to Grid View', bg=Theme.PNL2, fg=Theme.FG, state='disabled', relief='flat', bd=0, font=('Segoe UI', 10, 'bold'), cursor='hand2', command=self._toggle_layout_mode)
        self.btn_layout_smu.pack(fill='x', ipady=3, pady=2)
        tk.Button(sys_sec_smu, text='↺  Auto-Fit Graphics', bg='#fff7ed', fg='#c2410c', relief='flat', bd=0, font=('Segoe UI', 10, 'bold'), cursor='hand2', command=self._reset_chart_bounds).pack(fill='x', ipady=3, pady=2)


        # ==========================================
        # FIXED BOTTOM ACTION PANEL 
        # ==========================================
        tk.Frame(left_bottom, bg=Theme.SEP, height=1).pack(fill='x')
        action_frm = tk.Frame(left_bottom, bg=Theme.PNL)
        action_frm.pack(fill='x', padx=15, pady=10)

        self.save_var = tk.StringVar(value=os.path.join(os.path.dirname(os.path.abspath(__file__)), "B2910CL_Live.csv"))
        tk.Label(action_frm, text="Save Data To:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(anchor='w')
        sv_frm = tk.Frame(action_frm, bg=Theme.PNL)
        sv_frm.pack(fill='x', pady=(0, 4))
        tk.Entry(sv_frm, textvariable=self.save_var, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Segoe UI', 9)).pack(side='left', fill='x', expand=True)
        tk.Button(sv_frm, text="Browse", bg=Theme.PNL2, fg=Theme.FG, relief='flat', command=self._browse_save, font=('Segoe UI', 9, 'bold')).pack(side='right', padx=(4,0))

        tk.Label(action_frm, text="Post-Test Output State:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(anchor='w')
        self.off_mode_var = tk.StringVar(value="Hold Last Level")
        ttk.Combobox(action_frm, textvariable=self.off_mode_var, values=["Turn OFF (Normal)", "Turn OFF (High-Z)", "Hold Last Level"], state="readonly", font=('Segoe UI', 10)).pack(fill='x', pady=(0,8))

        ctrl_btn_frm = tk.Frame(action_frm, bg=Theme.PNL)
        ctrl_btn_frm.pack(fill='x', pady=4)
        
        self.btn_start = tk.Button(ctrl_btn_frm, text="▶ START TEST", bg=Theme.ACC, fg="#ffffff", font=('Segoe UI', 12, 'bold'), relief='flat', command=self._start_test)
        self.btn_start.pack(side='left', fill='x', expand=True, ipady=6, padx=(0, 4))
        
        self.btn_stop = tk.Button(ctrl_btn_frm, text="⏹ STOP / KILL", bg=Theme.ERR, fg="#ffffff", font=('Segoe UI', 12, 'bold'), relief='flat', command=self._stop_test)
        self.btn_stop.pack(side='right', fill='x', expand=True, ipady=6, padx=(4, 0))

        # ==========================================
        # TAB 2: ANALYTICS 
        # ==========================================
        ds_sec = sec(tab_ana, "DATA SOURCE")
        tk.Button(ds_sec, text='📂  Load Offline CSV', bg=Theme.PNL2, fg=Theme.ACC, relief='flat', bd=0, font=('Segoe UI', 10, 'bold'), cursor='hand2', command=self._browse_and_load_csv).pack(fill='x', ipady=4, pady=2)
        self.line_registry_box = tk.Listbox(ds_sec, height=5, bg=Theme.PNL2, fg=Theme.FG, font=('Segoe UI', 10), selectmode='single', highlightthickness=0, bd=0)
        self.line_registry_box.pack(fill='x', pady=4)
        self.listbox_tooltip = ListboxTooltip(self.line_registry_box, lambda idx: self.global_datasets.get(self.registry_keys[idx]) if idx < len(self.registry_keys) else None)
        self.line_registry_box.bind('<<ListboxSelect>>', self._on_listbox_select)
        
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 10))
        self.context_menu.add_command(label="⚙ Re-configure CSV Map", command=self._reconfigure_selected_line)
        self.context_menu.add_command(label="👁 Toggle Visibility", command=self._toggle_visibility)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="✕ Remove Trace", command=self._purge_selected_line, foreground="#dc2626")

        self.line_registry_box.bind("<Button-3>", self._show_listbox_context_menu)
        self.line_registry_box.bind("<Button-2>", self._show_listbox_context_menu)

        btn_frm_a = tk.Frame(ds_sec, bg=Theme.PNL)
        btn_frm_a.pack(fill='x', pady=1)
        tk.Button(btn_frm_a, text='👁 Toggle Vis', bg=Theme.PNL2, fg=Theme.FG, relief='flat', bd=0, font=('Segoe UI', 9, 'bold'), cursor='hand2', command=self._toggle_visibility).pack(side='left', fill='x', expand=True, padx=(0, 2))
        tk.Button(btn_frm_a, text='✕ Remove', bg='#fef2f2', fg='#dc2626', relief='flat', bd=0, font=('Segoe UI', 9, 'bold'), cursor='hand2', command=self._purge_selected_line).pack(side='right', fill='x', expand=True, padx=(2, 0))

        lay_sec = sec(tab_ana, "LAYOUT & VIEWPORT")
        self.btn_layout_ana = tk.Button(lay_sec, text='🗖  Split to Grid View', bg=Theme.PNL2, fg=Theme.FG, state='disabled', relief='flat', bd=0, font=('Segoe UI', 10, 'bold'), cursor='hand2', command=self._toggle_layout_mode)
        self.btn_layout_ana.pack(fill='x', ipady=4, pady=2)
        tk.Button(lay_sec, text='↺  Auto-Fit Graphics', bg='#fff7ed', fg='#c2410c', relief='flat', bd=0, font=('Segoe UI', 10, 'bold'), cursor='hand2', command=self._reset_chart_bounds).pack(fill='x', ipady=4, pady=2)

        math_sec = sec(tab_ana, "CALCULUS TOOLS")
        self.math_target_var = tk.StringVar()
        self.math_combo = ttk.Combobox(math_sec, textvariable=self.math_target_var, state='readonly', font=('Segoe UI', 10))
        self.math_combo.pack(fill='x', pady=4)
        tk.Button(math_sec, text='⚡ Differentiation (Slope)', bg=Theme.PNL2, fg=Theme.FG, relief='flat', bd=0, font=('Segoe UI', 10), cursor='hand2', command=self._run_derivative_pipeline).pack(fill='x', ipady=3, pady=2)
        tk.Button(math_sec, text='∫ Integration (Area)', bg=Theme.PNL2, fg=Theme.FG, relief='flat', bd=0, font=('Segoe UI', 10), cursor='hand2', command=self._run_integral_pipeline).pack(fill='x', ipady=3, pady=2)
        tk.Button(math_sec, text='✕ Clear Math Traces', bg=Theme.PNL2, fg='#dc2626', relief='flat', bd=0, font=('Segoe UI', 10, 'bold'), cursor='hand2', command=self._clear_math_traces).pack(fill='x', pady=4)

        # ==========================================
        # TAB 3: SCPI TERMINAL
        # ==========================================
        scpi_sec = sec(tab_scpi, "RAW HARDWARE COMMUNICATION")
        tk.Label(scpi_sec, text="Send custom SCPI commands directly.", bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 9)).pack(anchor='w', pady=(0,5))
        
        self.txt_term = tk.Text(scpi_sec, bg=Theme.PNL2, fg=Theme.FG, font=('Consolas', 10), height=18)
        self.txt_term.pack(fill='x', pady=5)
        
        cmd_frm = tk.Frame(scpi_sec, bg=Theme.PNL)
        cmd_frm.pack(fill='x', pady=5)
        self.ent_cmd = tk.Entry(cmd_frm, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, font=('Consolas', 11))
        self.ent_cmd.pack(side='left', fill='x', expand=True)
        self.ent_cmd.bind("<Return>", lambda e: self._send_scpi())
        tk.Button(cmd_frm, text="SEND", bg=Theme.ACC, fg="#ffffff", relief='flat', font=('Segoe UI', 9, 'bold'), command=self._send_scpi).pack(side='right', padx=(5,0))

        # -- RIGHT PANEL (Graph) --
        right = tk.Frame(body, bg=Theme.BG)
        right.pack(side='left', fill='both', expand=True, padx=15, pady=15)

        stats_frame = tk.Frame(right, bg=Theme.BG)
        stats_frame.pack(fill='x', side='top', pady=(0, 8))

        self.metric_boxes = {}
        ordered_metrics = [('min', 'Min (Vis)'), ('max', 'Max (Vis)'), ('mean', 'Mean μ'), ('std', 'Std Dev σ'), ('count', 'Samples in View')]
        for m_key, label_text in ordered_metrics:
            cell = tk.Frame(stats_frame, bg=Theme.PNL, highlightthickness=1, highlightbackground=Theme.SEP)
            cell.pack(side='left', fill='x', expand=True, padx=4)
            tk.Label(cell, text=label_text.upper(), bg=Theme.PNL, fg=Theme.DIM, font=('Segoe UI', 9, 'bold')).pack(anchor='w', padx=10, pady=(6, 0))
            val_lbl = tk.Label(cell, text='--', bg=Theme.PNL, fg=Theme.ACC, font=('Segoe UI', 13, 'bold'))
            val_lbl.pack(anchor='w', padx=10, pady=(0, 6))
            self.metric_boxes[m_key] = val_lbl

        nb = ttk.Notebook(right, style='Sim.TNotebook')
        nb.pack(fill='both', expand=True)

        chart_tab_panel = tk.Frame(nb, bg=Theme.BG)
        nb.add(chart_tab_panel, text='📈  High-Definition Interactive Viewports')

        self.chart_container = tk.Frame(chart_tab_panel, bg=Theme.BG)
        self.chart_container.pack(fill='both', expand=True, padx=6, pady=6)


    # ------------------------------------------------------------------
    # Hardware SMU Control Functions
    # ------------------------------------------------------------------
    def _visa_monitor_thread(self):
        while True:
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
            self.ent_pts.delete(0, tk.END)
            self.ent_pts.insert(0, str(len(self.custom_list_vals)))
        except Exception as e:
            messagebox.showerror("File Error", str(e))

    def _browse_save(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV Files", "*.csv")])
        if path: self.save_var.set(path)

    def _stop_test(self):
        self.is_running = False
        if self.smu:
            try:
                self.smu.write(":OUTP OFF")
                self.lbl_status.config(text="Hardware KILLED (Output OFF)", fg=Theme.ERR)
            except: pass

    def _start_test(self):
        if not self.smu:
            messagebox.showwarning("Offline", "Please connect to the instrument.")
            return

        self.is_running = True
        self.btn_start.config(state="disabled", text="TEST RUNNING...")
        
        src_label = f"Sourced ({self.src_mode_var.get()})"
        msr_label = f"Measured ({self.msr_mode_var.get()})"
        if "Auto" in msr_label:
            msr_label = "Measured (Voltage (V))" if "Current" in self.src_mode_var.get() else "Measured (Current (A))"
        
        self.global_datasets["Live_Source"] = {
            "x": np.array([], dtype=float), "y": np.array([], dtype=float), 
            "color": TRACE_COLORS[0], "trace_name": src_label, "visible": True
        }
        self.global_datasets["Live_Measure"] = {
            "x": np.array([], dtype=float), "y": np.array([], dtype=float), 
            "color": TRACE_COLORS[3], "trace_name": msr_label, "visible": True
        }
        
        if "Live_Source" not in self.registry_keys:
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
            base = float(self.ent_min.get())
            peak = float(self.ent_max.get())
            comp = float(self.ent_cmp.get())
            pts = int(self.ent_pts.get())
            total_time = float(self.ent_tot.get())
            shape = self.shape_var.get()
            off_mode = self.off_mode_var.get()
            
            if "Pulse" in shape:
                t_base = float(self.pulse_base_var.get())
                t_peak = float(self.pulse_peak_var.get())
                period = t_base + t_peak
            else:
                period = float(self.ent_per.get())
                
            step_time = period / pts
            amp, off = (peak - base) / 2.0, (peak + base) / 2.0
            list_vals = []
            
            if "Custom" in shape:
                if not self.custom_list_vals: raise ValueError("No Custom CSV loaded!")
                list_vals = self.custom_list_vals
            else:
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

            # EXTRACT EXACT START AND END TO PREVENT ZERO-SPIKE GLITCH
            initial_val = list_vals[0] if list_vals else base
            final_val = list_vals[-1] if list_vals else base

            self.smu.write("*RST")
            self.smu.write("*CLS")
            
            self.smu.write(f":SENS:REMO {'ON' if self.wire_var.get() else 'OFF'}")
            if self.avg_var.get(): self.smu.write(":SENS:AVER:STAT ON")
            
            src_str = "CURR" if mode_curr else "VOLT"
            msr_str = "VOLT" if mode_curr else "CURR"
            
            self.smu.write(f":SOUR:FUNC:MODE {src_str}")
            
            # CRITICAL ZERO-GLITCH FIX: Bias the hardware to the exact first point of the wave BEFORE output turns on
            self.smu.write(f":SOUR:{src_str} {initial_val}") 
            
            self.smu.write(f":SOUR:{src_str}:MODE LIST")
            self.smu.write(f":SOUR:{src_str}:RANG {max(abs(base), abs(peak))}")
            self.smu.write(f":SOUR:LIST:{src_str} {','.join(map(str, list_vals))}")
            
            self.smu.write(":SENS:FUNC \"VOLT\",\"CURR\"")
            self.smu.write(f":SENS:{msr_str}:PROT {comp}")
            
            ap_val = step_time * 0.5 if self.aperture_var.get() == "Auto" else 1e-5
            self.smu.write(f":SENS:VOLT:APER {ap_val}")
            self.smu.write(f":SENS:CURR:APER {ap_val}")

            cycles_per_chunk = max(1, int(1.0 / period))
            ticks_per_chunk = cycles_per_chunk * pts
            total_ticks = int(total_time / step_time)
            num_chunks = math.ceil(total_ticks / ticks_per_chunk)

            self.smu.write(":TRIG:TRAN:SOUR TIM")
            self.smu.write(f":TRIG:TRAN:TIM {step_time}")
            self.smu.write(":TRIG:ACQ:SOUR TIM")
            self.smu.write(f":TRIG:ACQ:TIM {step_time}")
            self.smu.write(":FORM:DATA ASC")

            save_file = self.save_var.get()
            with open(save_file, 'w', newline='') as f:
                csv.writer(f).writerow(["Time (s)", f"Sourced ({src_str})", "Voltage (V)", "Current (A)"])

            self.smu.write(":OUTP ON")
            global_t = 0.0

            for chunk in range(num_chunks):
                if not self.is_running: break
                
                t_count = min(ticks_per_chunk, total_ticks - chunk * ticks_per_chunk)
                self.smu.write(f":TRIG:TRAN:COUN {t_count}")
                self.smu.write(f":TRIG:ACQ:COUN {t_count}")
                
                self.smu.write(":INIT:ACQ")
                self.smu.write(":INIT:TRAN")
                
                self.smu.timeout = int(((t_count * step_time) + 10) * 1000)
                self.smu.write("*WAI")
                
                t = self.smu.query_ascii_values(":FETC:ARR:TIME?")
                c = self.smu.query_ascii_values(":FETC:ARR:CURR?")
                v = self.smu.query_ascii_values(":FETC:ARR:VOLT?")
                
                t_rel = [x + global_t for x in t]
                src_data = c if mode_curr else v
                
                with open(save_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    for tt, ss, vv, cc in zip(t_rel, src_data, v, c):
                        writer.writerow([tt, ss, vv, cc])
                
                self.data_queue.put((t_rel, src_data, v, c))
                global_t += (t_count * step_time)

            # GRACEFUL EXIT (Advanced Off State with Zero Glitch Protection)
            if self.is_running:
                if off_mode == "Hold Last Level":
                    self.smu.write(f":SOUR:{src_str}:MODE FIX")
                    self.smu.write(f":SOUR:{src_str} {final_val}") # Safely rest exactly where the wave finished
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
                
                t, src, v, c = data
                
                msr_sel = self.msr_mode_var.get()
                v_arr = np.array(v)
                c_arr = np.array(c)
                
                if "Voltage" in msr_sel: msr = v_arr
                elif "Current" in msr_sel: msr = c_arr
                elif "Power" in msr_sel: msr = v_arr * c_arr
                elif "Resistance" in msr_sel: 
                    c_safe = np.where(c_arr == 0, 1e-12, c_arr)
                    msr = v_arr / c_safe
                else:
                    msr = v_arr if "Current" in self.src_mode_var.get() else c_arr
                
                ls = self.global_datasets["Live_Source"]
                lm = self.global_datasets["Live_Measure"]
                
                ls["x"] = np.concatenate([ls["x"], t])
                ls["y"] = np.concatenate([ls["y"], src])
                lm["x"] = np.concatenate([lm["x"], t])
                lm["y"] = np.concatenate([lm["y"], msr])

                for chart in self.charts:
                    chart.register_dataset("Live_Source", ls["x"], ls["y"], ls["color"], trace_name=ls["trace_name"])
                    chart.register_dataset("Live_Measure", lm["x"], lm["y"], lm["color"], trace_name=lm["trace_name"])
                    
                    if self.is_first_chunk:
                        chart.reset_global_viewport()
                    else:
                        span = chart.view_xmax - chart.view_xmin
                        chart.view_xmax = max(chart.view_xmax, t[-1] + span*0.05)
                        chart.redraw()
                
                self.is_first_chunk = False
                self._reprocess_visible_window_metrics()
                
        except queue.Empty:
            pass

        if self.is_running:
            self.root.after(30, self._gui_queue_processor)
        else:
            self.btn_start.config(state="normal", text="▶ START TEST")

    # ------------------------------------------------------------------
    # Theme & Analytics Methods (From combined.py template)
    # ------------------------------------------------------------------
    def _toggle_dark_mode(self):
        Theme.toggle()
        theme_map = Theme.LIGHT_TO_DARK if Theme.is_dark else Theme.DARK_TO_LIGHT
        
        def apply_theme_recursive(w):
            try:
                bg = w.cget('bg')
                if bg.lower() in theme_map: w.config(bg=theme_map[bg.lower()])
            except: pass
            try:
                fg = w.cget('fg')
                if fg.lower() in theme_map: w.config(fg=theme_map[fg.lower()])
            except: pass
            try:
                hb = w.cget('highlightbackground')
                if hb.lower() in theme_map: w.config(highlightbackground=theme_map[hb.lower()])
            except: pass
            for child in w.winfo_children():
                apply_theme_recursive(child)
                
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
        sel = self.line_registry_box.curselection()
        if sel:
            d_id = self.registry_keys[sel[0]]
            ds = self.global_datasets.get(d_id)

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
            DataImportDialog(self.root, df, filename, self._on_import_confirmed)
        except Exception as ex:
            messagebox.showerror('Parsing Error', f"Could not process file:\n{str(ex)}")

    def _on_import_confirmed(self, filename, df, x_col, y_col, start_row, end_row, trace_name, scale, line_style, existing_id=None):
        try:
            subset = df.iloc[start_row:end_row].copy()
            subset[x_col] = pd.to_numeric(subset[x_col], errors='coerce')
            subset[y_col] = pd.to_numeric(subset[y_col], errors='coerce')
            subset.dropna(subset=[x_col, y_col], inplace=True)
            subset.sort_values(by=x_col, inplace=True)

            x_data = subset[x_col].values
            y_data = subset[y_col].values * scale

            if len(x_data) < 2:
                messagebox.showerror("Data Error", "Not enough valid numeric data in the selected bounds.")
                return

            if existing_id:
                d_id = existing_id
                assigned_color = self.global_datasets[existing_id]["color"]
                was_visible = self.global_datasets[existing_id].get("visible", True)
                keys_to_delete = [k for k in self.global_math if k.startswith(d_id)]
                for k in keys_to_delete: del self.global_math[k]
            else:
                d_id = filename
                base_id = d_id
                counter = 1
                while d_id in self.global_datasets:
                    d_id = f"{base_id} ({counter})"
                    counter += 1
                assigned_color = TRACE_COLORS[len(self.registry_keys) % len(TRACE_COLORS)]
                self.registry_keys.append(d_id)
                was_visible = True
            
            self.global_datasets[d_id] = {
                "x": x_data, "y": y_data, "color": assigned_color, "df": df, "filename": filename,
                "x_col": x_col, "y_col": y_col, "start_row": start_row, "end_row": end_row,
                "trace_name": trace_name, "scale": scale, "line_style": line_style,
                "visible": was_visible
            }
            
            self._refresh_listbox()
            self._update_selection_combos()
            self._update_layout_button_state()
            self._rebuild_charts()
            
        except Exception as ex:
             messagebox.showerror('Import Processing Error', f"Failed extracting selected metrics:\n{str(ex)}")

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