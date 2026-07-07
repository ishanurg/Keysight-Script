import sys
import os
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pyvisa
import numpy as np
import time
import threading
import queue
import csv
from datetime import datetime

# --- PyQtGraph requires QApplication before any QWidget ---
from PyQt5 import QtWidgets, QtCore
# Create the global QApplication instance
qapp = QtWidgets.QApplication.instance()
if qapp is None:
    qapp = QtWidgets.QApplication(sys.argv)

import pyqtgraph as pg

# ----------------------------------------------------------------------
# 1. Theme & UI Utilities
# ----------------------------------------------------------------------
class Theme:
    BG   = '#f0f2f5'
    PNL  = '#ffffff'
    PNL2 = '#e8ecf1'
    ACC  = '#0055a4'
    FG   = '#1e293b'
    DIM  = '#64748b'
    BRD  = '#cbd5e1'
    SEP  = '#e2e8f0'
    CV_BG= '#fafcff'
    ERR  = '#dc2626'
    ACC_H= '#003d7a'
    is_dark = False

    @classmethod
    def toggle(cls):
        cls.is_dark = not cls.is_dark
        if cls.is_dark:
            cls.BG, cls.PNL, cls.PNL2 = '#0f172a', '#1e293b', '#334155'
            cls.FG, cls.DIM = '#f8fafc', '#94a3b8'
            cls.BRD, cls.SEP = '#475569', '#334155'
            cls.CV_BG = '#020617'
        else:
            cls.BG, cls.PNL, cls.PNL2 = '#f0f2f5', '#ffffff', '#e8ecf1'
            cls.FG, cls.DIM = '#1e293b', '#64748b'
            cls.BRD, cls.SEP = '#cbd5e1', '#e2e8f0'
            cls.CV_BG = '#fafcff'

def set_hd_resolution():
    if sys.platform == 'win32':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass

# ----------------------------------------------------------------------
# 2. Scrollable Frame with robust scrolling & always-visible scrollbar
# ----------------------------------------------------------------------
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        # Container: canvas + scrollbar (pack side by side)
        self.canvas = tk.Canvas(self, bg=Theme.PNL, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=Theme.PNL)

        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Pack canvas and scrollbar
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # Bind events
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Mousewheel binding on all widgets inside the scrollable area
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.inner)
        self._bind_mousewheel(self)

        # Force a small spacer at the bottom to ensure scrolling is always possible
        self.spacer = tk.Frame(self.inner, height=10, bg=Theme.PNL)
        self.spacer.pack(side="bottom", fill="x")

    def _bind_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel)
        widget.bind("<Button-4>", self._on_mousewheel)   # Linux scroll up
        widget.bind("<Button-5>", self._on_mousewheel)   # Linux scroll down

    def _on_mousewheel(self, event):
        # Determine scroll direction
        if event.num == 4:
            delta = -1
        elif event.num == 5:
            delta = 1
        else:
            delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta, "units")

    def _on_inner_configure(self, event):
        # Update scroll region to encompass the entire inner frame
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        # Set the inner frame width to match the canvas (prevents horizontal scrolling)
        self.canvas.itemconfig(self.window, width=event.width)

# ----------------------------------------------------------------------
# 3. Main Application Class (unchanged, except for left panel width)
# ----------------------------------------------------------------------
class Keithley2110App:
    def __init__(self, root):
        self.root = root
        self.root.title("Keithley 2110 5½ Digit Multimeter Control")
        self.root.configure(bg=Theme.BG)
        self.root.geometry("1300x750")
        self.root.minsize(900, 600)

        self.rm = pyvisa.ResourceManager()
        self.instr = None
        self.connected = False

        self.reading_queue = queue.Queue()
        self.is_reading = False
        self.read_thread = None
        self.start_time = None
        self.readings_data = []

        self.x_data = []
        self.y_data = []
        self.max_points = 1000

        self.current_function = "VOLTage:DC"
        self.tc_type = "K"
        self.tc_reference = "REAL"
        self.tc_sim_temp = 0.0
        self.temp_units = "C"

        self.trigger_source = "IMMediate"
        self.sample_count = 1
        self.trigger_count = 1
        self.trigger_delay = "AUTO"
        self.delay_value = 0.0

        self._build_ui()
        self._scan_visa()
        self.root.after(3000, self._periodic_scan)
        self._process_qt_events()

    def _process_qt_events(self):
        qapp.processEvents()
        self.root.after(50, self._process_qt_events)

    # ------------------------------------------------------------------
    # UI Construction with resizable panels
    # ------------------------------------------------------------------
    def _build_ui(self):
        menubar = tk.Menu(self.root)
        view_menu = tk.Menu(menubar, tearoff=0)
        view_menu.add_command(label="Toggle Dark/Light Mode", command=self._toggle_theme)
        menubar.add_cascade(label="View", menu=view_menu)
        self.root.config(menu=menubar)

        # PanedWindow for resizable panels
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL,
                                   sashrelief='raised', sashwidth=8)
        main_pane.pack(fill='both', expand=True)

        # Left panel – wider to accommodate content
        left_frame = tk.Frame(main_pane, bg=Theme.PNL, width=420)
        main_pane.add(left_frame, width=420)

        # Scrollable area inside left panel
        scrollable = ScrollableFrame(left_frame, bg=Theme.PNL)
        scrollable.pack(fill='both', expand=True)
        controls = scrollable.inner

        # Right panel
        right = tk.Frame(main_pane, bg=Theme.BG)
        main_pane.add(right, width=800)

        # Build sections in left panel (all packed fill='x')
        self._build_connection_section(controls)
        self._build_function_section(controls)
        self._build_range_resolution_section(controls)
        self._build_temperature_section(controls)
        self._build_math_section(controls)
        self._build_trigger_section(controls)
        self._build_action_section(controls)
        self._build_save_section(controls)

        # Build right side
        self._build_display(right)

        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(self.root, textvariable=self.status_var, bd=1,
                              relief='sunken', anchor='w',
                              bg=Theme.PNL2, fg=Theme.FG)
        status_bar.pack(side='bottom', fill='x')

    # ------------------------------------------------------------------
    # All sections – identical to previous working code
    # (I include them to keep the code complete)
    # ------------------------------------------------------------------
    def _build_connection_section(self, parent):
        frame = tk.LabelFrame(parent, text=" Connection ", bg=Theme.PNL, fg=Theme.ACC,
                              font=('Segoe UI', 10, 'bold'), padx=5, pady=5)
        frame.pack(fill='x', padx=8, pady=6)
        self.visa_combo = ttk.Combobox(frame, state='readonly', font=('Segoe UI', 10))
        self.visa_combo.pack(fill='x', pady=2)
        btn_frame = tk.Frame(frame, bg=Theme.PNL)
        btn_frame.pack(fill='x', pady=4)
        tk.Button(btn_frame, text="Scan", bg=Theme.PNL2, fg=Theme.FG, relief='flat',
                  font=('Segoe UI', 9, 'bold'), command=self._scan_visa).pack(side='left', fill='x', expand=True, padx=2)
        self.btn_connect = tk.Button(btn_frame, text="Connect", bg=Theme.ACC, fg='white', relief='flat',
                                     font=('Segoe UI', 9, 'bold'), command=self._toggle_connection)
        self.btn_connect.pack(side='right', fill='x', expand=True, padx=2)
        self.conn_status = tk.Label(frame, text="Disconnected", fg=Theme.ERR, bg=Theme.PNL,
                                    font=('Segoe UI', 9, 'bold'))
        self.conn_status.pack(anchor='w', pady=2)

    def _build_function_section(self, parent):
        frame = tk.LabelFrame(parent, text=" Measurement Function ", bg=Theme.PNL, fg=Theme.ACC,
                              font=('Segoe UI', 10, 'bold'), padx=5, pady=5)
        frame.pack(fill='x', padx=8, pady=6)
        self.func_var = tk.StringVar(value="DCV")
        funcs = [
            ("DCV", "VOLTage:DC"), ("ACV", "VOLTage:AC"),
            ("DCI", "CURRent:DC"), ("ACI", "CURRent:AC"),
            ("2W", "RESistance"), ("4W", "FRESistance"),
            ("FREQ", "FREQuency"), ("PERIOD", "PERiod"),
            ("CONT", "CONTinuity"), ("DIODE", "DIODE"),
            ("TEMP", "TEMPerature"), ("TCOUPL", "TCOuple"),
            ("CAP", "CAPacitance")
        ]
        row, col = 0, 0
        for label, scpi in funcs:
            btn = tk.Button(frame, text=label, bg=Theme.PNL2, fg=Theme.FG, relief='flat',
                            font=('Segoe UI', 9, 'bold'), width=6,
                            command=lambda f=scpi, lbl=label: self._set_function(f, lbl))
            btn.grid(row=row, column=col, padx=2, pady=2, sticky='w')
            col += 1
            if col >= 4:
                col = 0
                row += 1
        self.secondary_var = tk.StringVar(value="None")
        tk.Label(frame, text="Secondary:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=row, column=0, sticky='e', padx=2)
        sec_combo = ttk.Combobox(frame, textvariable=self.secondary_var,
                                 values=["None", "DCV", "ACV", "DCI", "ACI", "2W", "4W", "FREQ", "PERIOD", "TEMP"],
                                 state='readonly', width=10)
        sec_combo.grid(row=row, column=1, columnspan=3, sticky='w', padx=2, pady=2)

    def _build_range_resolution_section(self, parent):
        frame = tk.LabelFrame(parent, text=" Range / Resolution ", bg=Theme.PNL, fg=Theme.ACC,
                              font=('Segoe UI', 10, 'bold'), padx=5, pady=5)
        frame.pack(fill='x', padx=8, pady=6)
        tk.Label(frame, text="Range:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=0, column=0, sticky='e', padx=2)
        self.range_var = tk.StringVar(value="Auto")
        range_combo = ttk.Combobox(frame, textvariable=self.range_var,
                                   values=["Auto", "0.1V", "1V", "10V", "100V", "1000V", "0.1A", "1A", "3A", "10A",
                                           "100Ω", "1kΩ", "10kΩ", "100kΩ", "1MΩ", "10MΩ", "100MΩ"],
                                   state='readonly', width=12)
        range_combo.grid(row=0, column=1, padx=2, pady=2, sticky='w')
        tk.Label(frame, text="Res/PLC/BW:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=1, column=0, sticky='e', padx=2)
        self.res_var = tk.StringVar(value="Auto")
        res_combo = ttk.Combobox(frame, textvariable=self.res_var,
                                 values=["Auto", "0.001 NPLC", "0.006 NPLC", "0.02 NPLC", "0.06 NPLC", "0.2 NPLC",
                                         "0.6 NPLC", "1 NPLC", "2 NPLC", "10 NPLC", "100 NPLC",
                                         "3 Hz BW", "20 Hz BW", "200 Hz BW",
                                         "0.01s Aperture", "0.1s Aperture", "1s Aperture"],
                                 state='readonly', width=18)
        res_combo.grid(row=1, column=1, padx=2, pady=2, sticky='w')

    def _build_temperature_section(self, parent):
        frame = tk.LabelFrame(parent, text=" Temperature (TCOUPL / RTD) ", bg=Theme.PNL, fg=Theme.ACC,
                              font=('Segoe UI', 10, 'bold'), padx=5, pady=5)
        frame.pack(fill='x', padx=8, pady=6)
        tk.Label(frame, text="TC Type:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=0, column=0, sticky='e', padx=2)
        self.tc_type_var = tk.StringVar(value="K")
        tc_types = ["B", "C", "E", "J", "K", "N", "R", "S", "T"]
        tc_combo = ttk.Combobox(frame, textvariable=self.tc_type_var, values=tc_types, state='readonly', width=6)
        tc_combo.grid(row=0, column=1, padx=2, pady=2, sticky='w')
        tk.Label(frame, text="Ref Junction:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=1, column=0, sticky='e', padx=2)
        self.tc_ref_var = tk.StringVar(value="REAL")
        ref_combo = ttk.Combobox(frame, textvariable=self.tc_ref_var, values=["REAL", "SIMulated"], state='readonly', width=10)
        ref_combo.grid(row=1, column=1, padx=2, pady=2, sticky='w')
        ref_combo.bind("<<ComboboxSelected>>", self._update_tc_ref)
        self.tc_sim_frame = tk.Frame(frame, bg=Theme.PNL)
        self.tc_sim_frame.grid(row=2, column=0, columnspan=2, sticky='w', padx=2, pady=2)
        tk.Label(self.tc_sim_frame, text="Sim Temp (°C):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(side='left')
        self.tc_sim_var = tk.StringVar(value="0.0")
        sim_entry = tk.Entry(self.tc_sim_frame, textvariable=self.tc_sim_var, bg=Theme.PNL2, fg=Theme.FG,
                             insertbackground=Theme.FG, width=8)
        sim_entry.pack(side='left', padx=4)
        self.tc_sim_frame.grid_remove()
        tk.Label(frame, text="Units:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=3, column=0, sticky='e', padx=2)
        self.temp_units_var = tk.StringVar(value="C")
        units_combo = ttk.Combobox(frame, textvariable=self.temp_units_var, values=["C", "F", "K"], state='readonly', width=6)
        units_combo.grid(row=3, column=1, padx=2, pady=2, sticky='w')
        tk.Label(frame, text="RTD Type:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=4, column=0, sticky='e', padx=2)
        self.rtd_type_var = tk.StringVar(value="PT100")
        rtd_types = ["PT100", "D100", "F100", "PT385", "PT3916", "USER", "SPRTD", "NTCT"]
        rtd_combo = ttk.Combobox(frame, textvariable=self.rtd_type_var, values=rtd_types, state='readonly', width=10)
        rtd_combo.grid(row=4, column=1, padx=2, pady=2, sticky='w')
        tk.Label(frame, text="Transducer:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=5, column=0, sticky='e', padx=2)
        self.transducer_var = tk.StringVar(value="RTD")
        trans_combo = ttk.Combobox(frame, textvariable=self.transducer_var, values=["RTD", "FRTD"], state='readonly', width=6)
        trans_combo.grid(row=5, column=1, padx=2, pady=2, sticky='w')

    def _update_tc_ref(self, event=None):
        if self.tc_ref_var.get() == "SIMulated":
            self.tc_sim_frame.grid()
        else:
            self.tc_sim_frame.grid_remove()

    def _build_math_section(self, parent):
        frame = tk.LabelFrame(parent, text=" Math Operations ", bg=Theme.PNL, fg=Theme.ACC,
                              font=('Segoe UI', 10, 'bold'), padx=5, pady=5)
        frame.pack(fill='x', padx=8, pady=6)
        tk.Label(frame, text="Function:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=0, column=0, sticky='e', padx=2)
        self.math_var = tk.StringVar(value="OFF")
        math_options = ["OFF", "PERCent", "AVERage", "NULL", "LIMit", "MXB", "DB", "DBM"]
        math_combo = ttk.Combobox(frame, textvariable=self.math_var, values=math_options, state='readonly', width=12)
        math_combo.grid(row=0, column=1, padx=2, pady=2, sticky='w')
        math_combo.bind("<<ComboboxSelected>>", self._math_selected)
        self.math_params_frame = tk.Frame(frame, bg=Theme.PNL)
        self.math_params_frame.grid(row=1, column=0, columnspan=2, sticky='w', padx=2, pady=2)
        self.math_param_entries = {}

    def _math_selected(self, event=None):
        for w in self.math_params_frame.winfo_children():
            w.destroy()
        self.math_param_entries.clear()
        func = self.math_var.get()
        if func == "OFF":
            return
        if func == "PERCent":
            tk.Label(self.math_params_frame, text="Target:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(side='left')
            entry = tk.Entry(self.math_params_frame, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=10)
            entry.pack(side='left', padx=4)
            self.math_param_entries["target"] = entry
        elif func == "NULL":
            tk.Label(self.math_params_frame, text="Null Value:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(side='left')
            entry = tk.Entry(self.math_params_frame, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=10)
            entry.pack(side='left', padx=4)
            self.math_param_entries["null"] = entry
        elif func == "LIMit":
            tk.Label(self.math_params_frame, text="Low:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(side='left')
            low = tk.Entry(self.math_params_frame, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=8)
            low.pack(side='left', padx=2)
            tk.Label(self.math_params_frame, text="High:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(side='left')
            high = tk.Entry(self.math_params_frame, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=8)
            high.pack(side='left', padx=2)
            self.math_param_entries["low"] = low
            self.math_param_entries["high"] = high
        elif func == "MXB":
            tk.Label(self.math_params_frame, text="m:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(side='left')
            m = tk.Entry(self.math_params_frame, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=8)
            m.pack(side='left', padx=2)
            tk.Label(self.math_params_frame, text="b:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(side='left')
            b = tk.Entry(self.math_params_frame, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=8)
            b.pack(side='left', padx=2)
            self.math_param_entries["m"] = m
            self.math_param_entries["b"] = b
        elif func == "DB":
            tk.Label(self.math_params_frame, text="Ref (dBm):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(side='left')
            entry = tk.Entry(self.math_params_frame, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=10)
            entry.pack(side='left', padx=4)
            self.math_param_entries["ref"] = entry
        elif func == "DBM":
            tk.Label(self.math_params_frame, text="Ref Res (Ω):", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).pack(side='left')
            entry = tk.Entry(self.math_params_frame, bg=Theme.PNL2, fg=Theme.FG, insertbackground=Theme.FG, width=10)
            entry.pack(side='left', padx=4)
            self.math_param_entries["ref_res"] = entry
        tk.Button(self.math_params_frame, text="Apply Math", bg=Theme.ACC, fg='white', relief='flat',
                  font=('Segoe UI', 9, 'bold'), command=self._apply_math).pack(side='left', padx=8)

    def _apply_math(self):
        if not self.connected:
            messagebox.showerror("Not Connected", "Connect to instrument first.")
            return
        func = self.math_var.get()
        if func == "OFF":
            self._send_command("CALC:STAT OFF")
            return
        self._send_command(f"CALC:FUNC {func}")
        for key, entry in self.math_param_entries.items():
            val = entry.get()
            if val:
                if func == "PERCent" and key == "target":
                    self._send_command(f"CALC:PERC:TARG {val}")
                elif func == "NULL" and key == "null":
                    self._send_command(f"CALC:NULL:OFFS {val}")
                elif func == "LIMit":
                    if key == "low":
                        self._send_command(f"CALC:LIM:LOW {val}")
                    elif key == "high":
                        self._send_command(f"CALC:LIM:UPP {val}")
                elif func == "MXB":
                    if key == "m":
                        self._send_command(f"CALC:MXB:MMF {val}")
                    elif key == "b":
                        self._send_command(f"CALC:MXB:MBF {val}")
                elif func == "DB" and key == "ref":
                    self._send_command(f"CALC:DB:REF {val}")
                elif func == "DBM" and key == "ref_res":
                    self._send_command(f"CALC:DBM:REF {val}")
        self._send_command("CALC:STAT ON")
        messagebox.showinfo("Math", f"Math function {func} enabled.")

    def _build_trigger_section(self, parent):
        frame = tk.LabelFrame(parent, text=" Trigger / Data Buffer ", bg=Theme.PNL, fg=Theme.ACC,
                              font=('Segoe UI', 10, 'bold'), padx=5, pady=5)
        frame.pack(fill='x', padx=8, pady=6)
        tk.Label(frame, text="Source:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=0, column=0, sticky='e', padx=2)
        self.trig_source_var = tk.StringVar(value="IMMediate")
        trig_sources = ["IMMediate", "BUS", "EXternal"]
        trig_combo = ttk.Combobox(frame, textvariable=self.trig_source_var, values=trig_sources, state='readonly', width=10)
        trig_combo.grid(row=0, column=1, padx=2, pady=2, sticky='w')
        tk.Label(frame, text="Sample Count:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=1, column=0, sticky='e', padx=2)
        self.sample_count_var = tk.StringVar(value="1")
        sample_entry = tk.Entry(frame, textvariable=self.sample_count_var, bg=Theme.PNL2, fg=Theme.FG,
                                insertbackground=Theme.FG, width=10)
        sample_entry.grid(row=1, column=1, padx=2, pady=2, sticky='w')
        tk.Label(frame, text="Trigger Count:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=2, column=0, sticky='e', padx=2)
        self.trig_count_var = tk.StringVar(value="1")
        trig_count_entry = tk.Entry(frame, textvariable=self.trig_count_var, bg=Theme.PNL2, fg=Theme.FG,
                                    insertbackground=Theme.FG, width=10)
        trig_count_entry.grid(row=2, column=1, padx=2, pady=2, sticky='w')
        tk.Label(frame, text="Delay:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=3, column=0, sticky='e', padx=2)
        self.delay_var = tk.StringVar(value="AUTO")
        delay_combo = ttk.Combobox(frame, textvariable=self.delay_var, values=["AUTO", "MANUAL"], state='readonly', width=8)
        delay_combo.grid(row=3, column=1, padx=2, pady=2, sticky='w')
        self.delay_value_var = tk.StringVar(value="0.0")
        delay_entry = tk.Entry(frame, textvariable=self.delay_value_var, bg=Theme.PNL2, fg=Theme.FG,
                               insertbackground=Theme.FG, width=8)
        delay_entry.grid(row=3, column=2, padx=2, pady=2, sticky='w')
        tk.Label(frame, text="Reading Hold:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=4, column=0, sticky='e', padx=2)
        self.hold_var = tk.BooleanVar(value=False)
        hold_check = tk.Checkbutton(frame, variable=self.hold_var, bg=Theme.PNL, fg=Theme.FG,
                                    selectcolor=Theme.PNL2, command=self._set_reading_hold)
        hold_check.grid(row=4, column=1, sticky='w', padx=2, pady=2)

    def _set_reading_hold(self):
        if not self.connected:
            return
        try:
            if self.hold_var.get():
                self._send_command("SENS:HOLD:STAT ON")
            else:
                self._send_command("SENS:HOLD:STAT OFF")
        except:
            pass

    def _build_action_section(self, parent):
        frame = tk.Frame(parent, bg=Theme.PNL, pady=6)
        frame.pack(fill='x', padx=8, pady=6)
        self.btn_start = tk.Button(frame, text="▶ Start Reading", bg='#22c55e', fg='white',
                                   font=('Segoe UI', 10, 'bold'), relief='flat',
                                   command=self._start_reading)
        self.btn_start.pack(side='left', fill='x', expand=True, padx=2, ipady=4)
        self.btn_stop = tk.Button(frame, text="⏹ Stop", bg='#ef4444', fg='white',
                                  font=('Segoe UI', 10, 'bold'), relief='flat',
                                  command=self._stop_reading, state='disabled')
        self.btn_stop.pack(side='right', fill='x', expand=True, padx=2, ipady=4)
        self.btn_single = tk.Button(frame, text="Single", bg=Theme.PNL2, fg=Theme.FG,
                                    font=('Segoe UI', 9, 'bold'), relief='flat',
                                    command=self._single_reading)
        self.btn_single.pack(side='left', padx=2)

    def _build_save_section(self, parent):
        frame = tk.LabelFrame(parent, text=" Data Logging ", bg=Theme.PNL, fg=Theme.ACC,
                              font=('Segoe UI', 10, 'bold'), padx=5, pady=5)
        frame.pack(fill='x', padx=8, pady=6)
        tk.Label(frame, text="Save to CSV:", bg=Theme.PNL, fg=Theme.FG, font=('Segoe UI', 9)).grid(row=0, column=0, sticky='e', padx=2)
        self.save_path_var = tk.StringVar(value=os.path.join(os.getcwd(), "Keithley2110_data.csv"))
        save_entry = tk.Entry(frame, textvariable=self.save_path_var, bg=Theme.PNL2, fg=Theme.FG,
                              insertbackground=Theme.FG, width=25)
        save_entry.grid(row=0, column=1, padx=2, pady=2, sticky='w')
        tk.Button(frame, text="Browse", bg=Theme.PNL2, fg=Theme.FG, relief='flat',
                  font=('Segoe UI', 8), command=self._browse_save).grid(row=0, column=2, padx=2)
        self.auto_save_var = tk.BooleanVar(value=False)
        tk.Checkbutton(frame, text="Auto-save during reading", variable=self.auto_save_var, bg=Theme.PNL,
                       fg=Theme.FG, selectcolor=Theme.PNL2).grid(row=1, column=0, columnspan=3, sticky='w', padx=2)
        tk.Button(frame, text="Save Now", bg=Theme.ACC, fg='white', relief='flat',
                  font=('Segoe UI', 9, 'bold'), command=self._manual_save).grid(row=2, column=0, columnspan=3, pady=4, sticky='we')

    def _browse_save(self):
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV files", "*.csv")])
        if path:
            self.save_path_var.set(path)

    def _manual_save(self):
        if not self.readings_data:
            messagebox.showinfo("No Data", "No readings to save.")
            return
        self._save_readings_to_csv()

    def _save_readings_to_csv(self):
        path = self.save_path_var.get()
        if not path:
            messagebox.showwarning("No File", "Please choose a save file first.")
            return
        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["Relative Time (s)", "Value"])
                for t, v in self.readings_data:
                    writer.writerow([f"{t:.3f}", f"{v:.6f}"])
            self.status_var.set(f"Data saved to {path}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------
    def _build_display(self, parent):
        reading_frame = tk.Frame(parent, bg=Theme.PNL, highlightthickness=1, highlightbackground=Theme.BRD)
        reading_frame.pack(fill='x', pady=(0, 10))
        self.reading_label = tk.Label(reading_frame, text="--", bg=Theme.PNL, fg=Theme.ACC,
                                      font=('Segoe UI', 36, 'bold'), anchor='center')
        self.reading_label.pack(pady=20, padx=10)
        self.unit_label = tk.Label(reading_frame, text="", bg=Theme.PNL, fg=Theme.DIM,
                                   font=('Segoe UI', 14))
        self.unit_label.pack(side='bottom', pady=(0, 10))
        self.graph_frame = tk.Frame(parent, bg=Theme.CV_BG)
        self.graph_frame.pack(fill='both', expand=True)
        self.graph_widget = pg.PlotWidget(background=Theme.CV_BG)
        self.graph_widget.setLabel('left', 'Value')
        self.graph_widget.setLabel('bottom', 'Sample')
        self.graph_curve = self.graph_widget.plot(pen=pg.mkPen(color=Theme.ACC, width=2))
        self.graph_widget.setWindowFlags(QtCore.Qt.Window)
        self.graph_widget.show()
        if sys.platform == 'win32':
            qt_hwnd = int(self.graph_widget.winId())
            tk_hwnd = self.graph_frame.winfo_id()
            ctypes.windll.user32.SetParent(qt_hwnd, tk_hwnd)
            style = ctypes.windll.user32.GetWindowLongW(qt_hwnd, -16)
            style = style & ~(0x00CF0000)
            ctypes.windll.user32.SetWindowLongW(qt_hwnd, -16, style)
            self.graph_widget.show()
            self.graph_widget.setGeometry(0, 0, self.graph_frame.winfo_width(), self.graph_frame.winfo_height())
        else:
            self.graph_widget.setWindowTitle("Keithley 2110 Live Graph")
        self.graph_frame.bind("<Configure>", self._resize_qt)
        self.qt_widget = self.graph_widget

    def _resize_qt(self, event):
        if sys.platform == 'win32':
            self.qt_widget.setGeometry(0, 0, event.width, event.height)

    # ------------------------------------------------------------------
    # VISA & Connection
    # ------------------------------------------------------------------
    def _scan_visa(self):
        try:
            ports = self.rm.list_resources()
            self.visa_combo['values'] = ports
            if ports and not self.visa_combo.get():
                self.visa_combo.set(ports[0])
        except Exception as e:
            self.status_var.set(f"Scan error: {e}")

    def _periodic_scan(self):
        self._scan_visa()
        self.root.after(5000, self._periodic_scan)

    def _toggle_connection(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.visa_combo.get()
        if not port:
            messagebox.showwarning("No Port", "Select a VISA resource.")
            return
        try:
            self.instr = self.rm.open_resource(port)
            self.instr.timeout = 5000
            idn = self.instr.query("*IDN?").strip()
            self.connected = True
            self.conn_status.config(text=f"Connected: {idn[:30]}...", fg='#10b981')
            self.btn_connect.config(text="Disconnect", bg=Theme.ERR)
            self.status_var.set(f"Connected to {idn}")
            self._send_command("*RST")
            self._set_function("VOLTage:DC", "DCV")
            messagebox.showinfo("Connected", f"Connected to {idn}")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
            self.connected = False

    def _disconnect(self):
        if self.instr:
            try:
                self.instr.close()
            except:
                pass
        self.instr = None
        self.connected = False
        self.conn_status.config(text="Disconnected", fg=Theme.ERR)
        self.btn_connect.config(text="Connect", bg=Theme.ACC)
        self.status_var.set("Disconnected")
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        self.is_reading = False
        if self.readings_data:
            self._save_readings_to_csv()

    def _send_command(self, cmd):
        if not self.connected:
            raise Exception("Not connected")
        self.instr.write(cmd)

    def _query(self, cmd):
        if not self.connected:
            raise Exception("Not connected")
        return self.instr.query(cmd).strip()

    # ------------------------------------------------------------------
    # Measurement functions (unchanged from previous)
    # ------------------------------------------------------------------
    def _set_function(self, scpi_func, label):
        self.current_function = scpi_func
        self.status_var.set(f"Function: {label}")
        if not self.connected:
            return
        try:
            self._send_command(f"SENS:FUNC \"{scpi_func}\"")
            self.func_var.set(label)
        except Exception as e:
            messagebox.showerror("Function Error", str(e))

    def _apply_range_resolution(self):
        if not self.connected:
            return
        range_str = self.range_var.get()
        res_str = self.res_var.get()
        try:
            if range_str != "Auto":
                val = ''.join([c for c in range_str if c.isdigit() or c == '.'])
                if val:
                    self._send_command(f"SENS:{self.current_function}:RANG {val}")
                else:
                    self._send_command(f"SENS:{self.current_function}:RANG:AUTO ON")
            else:
                self._send_command(f"SENS:{self.current_function}:RANG:AUTO ON")
            if "NPLC" in res_str:
                nplc = res_str.split()[0]
                self._send_command(f"SENS:{self.current_function}:NPLC {nplc}")
            elif "BW" in res_str:
                bw = res_str.split()[0]
                self._send_command(f"SENS:DET:BAND {bw}")
            elif "Aperture" in res_str:
                ap = res_str.split()[0]
                self._send_command(f"SENS:FREQ:APER {ap}")
        except Exception as e:
            messagebox.showerror("Range/Res Error", str(e))

    def _apply_temperature_settings(self):
        if not self.connected:
            return
        try:
            if self.func_var.get() == "TCOUPL":
                self._send_command(f"SENS:TCO:TYPE {self.tc_type_var.get()}")
                ref = self.tc_ref_var.get()
                self._send_command(f"SENS:TCO:RJUN:RSEL {ref}")
                if ref == "SIMulated":
                    sim_temp = self.tc_sim_var.get()
                    self._send_command(f"SENS:TCO:RJUN:SIM {sim_temp}")
                unit = self.temp_units_var.get()
                unit_cmd = "Cel" if unit == "C" else "Far" if unit == "F" else "K"
                self._send_command(f"SENS:UNIT {unit_cmd}")
            elif self.func_var.get() == "TEMP":
                rtd = self.rtd_type_var.get()
                self._send_command(f"SENS:TEMP:RTD:TYPE {rtd}")
                trans = self.transducer_var.get()
                self._send_command(f"SENS:TEMP:TRANS {trans}")
                unit = self.temp_units_var.get()
                unit_cmd = "Cel" if unit == "C" else "Far" if unit == "F" else "K"
                self._send_command(f"SENS:UNIT {unit_cmd}")
        except Exception as e:
            messagebox.showerror("Temp Settings Error", str(e))

    def _apply_trigger_settings(self):
        if not self.connected:
            return
        try:
            src = self.trig_source_var.get()
            self._send_command(f"TRIG:SOUR {src}")
            sample = int(self.sample_count_var.get())
            self._send_command(f"SAMP:COUN {sample}")
            trig_cnt = int(self.trig_count_var.get())
            self._send_command(f"TRIG:COUN {trig_cnt}")
            delay_mode = self.delay_var.get()
            if delay_mode == "AUTO":
                self._send_command("TRIG:DEL:AUTO ON")
            else:
                self._send_command("TRIG:DEL:AUTO OFF")
                delay_val = float(self.delay_value_var.get())
                self._send_command(f"TRIG:DEL {delay_val}")
        except Exception as e:
            messagebox.showerror("Trigger Settings Error", str(e))

    # ------------------------------------------------------------------
    # Reading threads (unchanged)
    # ------------------------------------------------------------------
    def _start_reading(self):
        if not self.connected:
            messagebox.showwarning("Not Connected", "Connect to instrument first.")
            return
        if self.is_reading:
            return
        self._apply_range_resolution()
        self._apply_temperature_settings()
        self._apply_trigger_settings()
        self.x_data = []
        self.y_data = []
        self.readings_data = []
        self.start_time = time.time()
        self.is_reading = True
        self.btn_start.config(state='disabled')
        self.btn_stop.config(state='normal')
        self.read_thread = threading.Thread(target=self._reading_thread, daemon=True)
        self.read_thread.start()
        self._update_reading_display()

    def _stop_reading(self):
        self.is_reading = False
        self.btn_start.config(state='normal')
        self.btn_stop.config(state='disabled')
        try:
            self._send_command("ABOR")
        except:
            pass
        if self.readings_data:
            self._save_readings_to_csv()
            self.status_var.set(f"Stopped. {len(self.readings_data)} readings saved.")

    def _single_reading(self):
        if not self.connected:
            messagebox.showwarning("Not Connected", "Connect first.")
            return
        try:
            val = self._query("READ?")
            self._display_reading(val)
            self.status_var.set(f"Single reading: {val}")
        except Exception as e:
            messagebox.showerror("Single Reading Error", str(e))

    def _display_reading(self, raw_str):
        try:
            num = float(raw_str)
            if abs(num) < 0.0001 or abs(num) > 9999:
                display = f"{num:.4e}"
            else:
                display = f"{num:.4f}"
            self.reading_label.config(text=display)
        except:
            self.reading_label.config(text=raw_str)

    def _reading_thread(self):
        while self.is_reading:
            try:
                val = self._query("READ?")
                try:
                    num = float(val)
                except:
                    num = 0.0
                self.reading_queue.put((num, val))
                time.sleep(0.02)
            except Exception as e:
                self.reading_queue.put(("ERROR", str(e)))
                time.sleep(0.1)

    def _update_reading_display(self):
        while not self.reading_queue.empty():
            item = self.reading_queue.get_nowait()
            if isinstance(item, tuple) and len(item) == 2:
                if isinstance(item[0], float):
                    num = item[0]
                    val_str = item[1]
                    self._display_reading(val_str)
                    self.unit_label.config(text=self._get_unit())
                    rel_time = time.time() - self.start_time
                    self.readings_data.append((rel_time, num))
                    self.x_data.append(len(self.x_data))
                    self.y_data.append(num)
                    if len(self.x_data) > self.max_points:
                        self.x_data = self.x_data[-self.max_points:]
                        self.y_data = self.y_data[-self.max_points:]
                    self.graph_curve.setData(self.x_data, self.y_data)
                    if self.auto_save_var.get():
                        self._append_reading_to_csv(rel_time, num)
                else:
                    self.status_var.set(f"Read error: {item[1]}")
        if self.is_reading:
            self.root.after(50, self._update_reading_display)

    def _append_reading_to_csv(self, rel_time, value):
        path = self.save_path_var.get()
        if not path:
            return
        try:
            file_exists = os.path.isfile(path)
            with open(path, 'a', newline='') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Relative Time (s)", "Value"])
                writer.writerow([f"{rel_time:.3f}", f"{value:.6f}"])
        except:
            pass

    def _get_unit(self):
        func = self.func_var.get()
        if func in ["DCV", "ACV"]:
            return "V"
        elif func in ["DCI", "ACI"]:
            return "A"
        elif func in ["2W", "4W"]:
            return "Ω"
        elif func == "FREQ":
            return "Hz"
        elif func == "PERIOD":
            return "s"
        elif func == "CONT":
            return "Ω"
        elif func == "DIODE":
            return "V"
        elif func in ["TEMP", "TCOUPL"]:
            unit = self.temp_units_var.get()
            if unit == "C":
                return "°C"
            elif unit == "F":
                return "°F"
            else:
                return "K"
        elif func == "CAP":
            return "F"
        else:
            return ""

    # ------------------------------------------------------------------
    # Theme & cleanup
    # ------------------------------------------------------------------
    def _toggle_theme(self):
        Theme.toggle()
        self.root.configure(bg=Theme.BG)
        self.graph_widget.setBackground(Theme.CV_BG)
        self.graph_curve.setPen(pg.mkPen(color=Theme.ACC, width=2))
        self.reading_label.config(bg=Theme.PNL, fg=Theme.ACC)
        self.unit_label.config(bg=Theme.PNL, fg=Theme.DIM)

    def on_closing(self):
        self._stop_reading()
        if self.instr:
            try:
                self.instr.close()
            except:
                pass
        self.root.destroy()
        qapp.quit()

# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
if __name__ == '__main__':
    set_hd_resolution()
    root = tk.Tk()
    app = Keithley2110App(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()