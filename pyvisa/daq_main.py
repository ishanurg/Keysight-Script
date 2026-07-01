#!/usr/bin/env python3
"""
Keysight B2910CL Precision SMU Control Dashboard
Inspired by keithley-tool (https://github.com/schwemmdx/keithley-tool)
Merged with original B2910CL dashboard features.
"""

import sys
import os
import ctypes
import json
import socket
import select
import threading
import queue
import time
import math
import csv
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

import numpy as np
import pyvisa
import pyqtgraph as pg
from PyQt5 import QtWidgets, QtCore, QtGui

# ----------------------------------------------------------------------
# 1. Theme & Constants
# ----------------------------------------------------------------------
class Theme:
    """Modern dark/light theme with seamless toggle."""
    BG   = '#0f172a'
    PNL  = '#1e293b'
    PNL2 = '#334155'
    ACC  = '#38bdf8'
    ACC_H= '#0ea5e9'          # <--- ADDED
    FG   = '#f8fafc'
    DIM  = '#94a3b8'
    BRD  = '#475569'
    SEP  = '#334155'
    CV_BG= '#020617'
    ERR  = '#ef4444'
    is_dark = True

    DARK_TO_LIGHT = {
        '#0f172a': '#f4f6fb', '#1e293b': '#ffffff', '#334155': '#eef1f8',
        '#f8fafc': '#1e293b', '#94a3b8': '#64748b', '#475569': '#cbd5e1',
        '#334155': '#e2e8f0', '#020617': '#f8fafc', '#38bdf8': '#2563eb',
        '#0ea5e9': '#2563eb'   # added for ACC_H
    }
    LIGHT_TO_DARK = {v: k for k, v in DARK_TO_LIGHT.items()}

    @classmethod
    def toggle(cls):
        cls.is_dark = not cls.is_dark
        if cls.is_dark:
            cls.BG, cls.PNL, cls.PNL2 = '#0f172a', '#1e293b', '#334155'
            cls.FG, cls.DIM, cls.ACC = '#f8fafc', '#94a3b8', '#38bdf8'
            cls.ACC_H = '#0ea5e9'
            cls.BRD, cls.SEP = '#475569', '#334155'
            cls.CV_BG = '#020617'
        else:
            cls.BG, cls.PNL, cls.PNL2 = '#f4f6fb', '#ffffff', '#eef1f8'
            cls.FG, cls.DIM, cls.ACC = '#1e293b', '#64748b', '#2563eb'
            cls.ACC_H = '#2563eb'
            cls.BRD, cls.SEP = '#cbd5e1', '#e2e8f0'
            cls.CV_BG = '#f8fafc'

TRACE_COLORS = [
    '#38bdf8', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899',
    '#06b6d4', '#84cc16', '#a855f7', '#f43f5e', '#14b8a6', '#f97316'
]

def set_hd_resolution():
    if sys.platform == 'win32':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

# ----------------------------------------------------------------------
# 2. Low-level Communication (TCP/IP & VISA)
# ----------------------------------------------------------------------
class TCPInstrument:
    """Raw TCP socket communication (no VISA)."""
    def __init__(self, debug=False):
        self.debug = debug
        self.sock = None
        self.connected = False
        self.timeout_s = 5.0
        self._readbuf = []
        self._recvbuf = b''

    def connect(self, ip: str, port: int = 5025, timeout: float = 5.0):
        self.timeout_s = timeout
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((ip, port))
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.connected = True

    def write(self, cmd: str):
        if not self.connected or not cmd:
            return
        if self.debug:
            print(f"Send: {cmd}")
        self.sock.sendall((cmd + '\n').encode())

    def read(self) -> str:
        if not self.connected:
            return ''
        # Read with timeout
        ready = select.select([self.sock], [], [], self.timeout_s)
        if not ready[0]:
            return ''
        data = self.sock.recv(4096)
        if not data:
            return ''
        self._recvbuf += data
        if b'\n' not in self._recvbuf:
            return ''
        idx = self._recvbuf.find(b'\n')
        line = self._recvbuf[:idx].decode().strip()
        self._recvbuf = self._recvbuf[idx+1:]
        if self.debug:
            print(f"Recv: {line}")
        return line

    def query(self, cmd: str) -> str:
        self.write(cmd)
        return self.read()

    def close(self):
        if self.sock:
            self.sock.close()
        self.connected = False

class VISAInstrument:
    """PyVISA wrapper for B2910CL."""
    def __init__(self):
        self.rm = pyvisa.ResourceManager()
        self.instr = None
        self.connected = False

    def list_resources(self):
        try:
            return self.rm.list_resources()
        except:
            return []

    def connect(self, resource: str, timeout: int = 10000):
        self.instr = self.rm.open_resource(resource)
        self.instr.timeout = timeout
        idn = self.instr.query('*IDN?').strip()
        self.connected = True
        return idn

    def write(self, cmd: str):
        if self.connected and self.instr:
            self.instr.write(cmd)

    def query(self, cmd: str) -> str:
        if self.connected and self.instr:
            return self.instr.query(cmd).strip()
        return ''

    def query_ascii_values(self, cmd: str):
        if self.connected and self.instr:
            return self.instr.query_ascii_values(cmd)
        return []

    def close(self):
        if self.instr:
            self.instr.close()
        self.connected = False

# ----------------------------------------------------------------------
# 3. B2910CL Instrument Controller
# ----------------------------------------------------------------------
class B2910CL:
    """High-level controller for Keysight B2910CL SMU."""
    def __init__(self, use_tcp=False, debug=False):
        self.use_tcp = use_tcp
        self.debug = debug
        self._tcp = TCPInstrument(debug=debug) if use_tcp else None
        self._visa = VISAInstrument() if not use_tcp else None
        self.connected = False
        self._mode = 'voltage'  # 'voltage' or 'current'

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect_tcp(self, ip: str, port: int = 5025, timeout: float = 5.0):
        if not self.use_tcp:
            raise RuntimeError("Not in TCP mode")
        self._tcp.connect(ip, port, timeout)
        idn = self._tcp.query('*IDN?')
        self.connected = True
        return idn

    def connect_visa(self, resource: str, timeout: int = 10000):
        if self.use_tcp:
            raise RuntimeError("Not in VISA mode")
        idn = self._visa.connect(resource, timeout)
        self.connected = True
        return idn

    def disconnect(self):
        if self.use_tcp:
            self._tcp.close()
        else:
            self._visa.close()
        self.connected = False

    def list_resources(self):
        if self.use_tcp:
            return []  # TCP mode doesn't scan
        return self._visa.list_resources()

    # ------------------------------------------------------------------
    # Core SCPI
    # ------------------------------------------------------------------
    def write(self, cmd: str):
        if self.use_tcp:
            self._tcp.write(cmd)
        else:
            self._visa.write(cmd)

    def query(self, cmd: str) -> str:
        if self.use_tcp:
            return self._tcp.query(cmd)
        return self._visa.query(cmd)

    def query_ascii_values(self, cmd: str):
        if self.use_tcp:
            # TCP fallback: parse ASCII response
            resp = self.query(cmd)
            if not resp:
                return []
            return [float(x) for x in resp.split(',')]
        return self._visa.query_ascii_values(cmd)

    # ------------------------------------------------------------------
    # High-level SMU control
    # ------------------------------------------------------------------
    def reset(self):
        self.write('*RST')
        self.write('*CLS')

    def set_mode(self, mode: str):
        """Set source mode: 'voltage' or 'current'."""
        self._mode = mode
        if mode == 'voltage':
            self.write(':SOUR:FUNC:MODE VOLT')
        else:
            self.write(':SOUR:FUNC:MODE CURR')

    def set_voltage(self, voltage: float, compliance: float = 0.1):
        """Set voltage source level and current compliance."""
        self.write(f':SOUR:VOLT {voltage}')
        self.write(f':SOUR:CURR:PROT {compliance}')

    def set_current(self, current: float, compliance: float = 10.0):
        """Set current source level and voltage compliance."""
        self.write(f':SOUR:CURR {current}')
        self.write(f':SOUR:VOLT:PROT {compliance}')

    def output_on(self, state: bool = True):
        self.write(f':OUTP {"ON" if state else "OFF"}')

    def measure_voltage(self) -> float:
        vals = self.query_ascii_values(':MEAS:VOLT?')
        return vals[0] if vals else 0.0

    def measure_current(self) -> float:
        vals = self.query_ascii_values(':MEAS:CURR?')
        return vals[0] if vals else 0.0

    def measure_resistance(self) -> float:
        vals = self.query_ascii_values(':MEAS:RES?')
        return vals[0] if vals else 0.0

    def measure_power(self) -> float:
        v = self.measure_voltage()
        i = self.measure_current()
        return v * i

    def measure_iv(self) -> Tuple[float, float]:
        """Return (current, voltage) pair."""
        vals = self.query_ascii_values(':MEAS:CURR?;:MEAS:VOLT?')
        if len(vals) >= 2:
            return vals[0], vals[1]
        return 0.0, 0.0

    def set_sweep(self, start: float, stop: float, steps: int, mode: str = 'voltage'):
        """Configure a sweep list."""
        if mode == 'voltage':
            self.write(':SOUR:FUNC:MODE VOLT')
            self.write(f':SOUR:LIST:VOLT {start},{stop},{steps}')
        else:
            self.write(':SOUR:FUNC:MODE CURR')
            self.write(f':SOUR:LIST:CURR {start},{stop},{steps}')

    def run_sweep(self):
        """Execute the configured sweep."""
        self.write(':SOUR:SWE:RANG AUTO')
        self.write(':INIT:IMM')
        # Wait for completion
        time.sleep(0.1)
        self.write('*WAI')

    def fetch_sweep(self) -> List[float]:
        """Fetch sweep measurement data."""
        return self.query_ascii_values(':FETC:ARR?')

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------
    def check_errors(self) -> bool:
        """Return True if there are errors in the queue."""
        resp = self.query('SYST:ERR?')
        return 'No error' not in resp

    def read_errors(self) -> List[str]:
        """Read and clear all errors."""
        errors = []
        while True:
            resp = self.query('SYST:ERR?')
            if 'No error' in resp:
                break
            errors.append(resp)
        return errors

# ----------------------------------------------------------------------
# 4. PyQtGraph Plotting Widget
# ----------------------------------------------------------------------
class LivePlotWidget(pg.PlotWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBackground(Theme.CV_BG)
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setLabel('left', 'Value', units='')
        self.setLabel('bottom', 'Time', units='s')
        self.curves = {}
        self.data = {}
        self.max_points = 5000

    def add_trace(self, name: str, color: str):
        pen = pg.mkPen(color=color, width=2)
        curve = self.plot([], [], pen=pen, name=name)
        self.curves[name] = curve
        self.data[name] = {'x': [], 'y': []}
        self.addLegend()

    def update_trace(self, name: str, x: float, y: float):
        if name not in self.data:
            return
        d = self.data[name]
        d['x'].append(x)
        d['y'].append(y)
        if len(d['x']) > self.max_points:
            d['x'] = d['x'][-self.max_points:]
            d['y'] = d['y'][-self.max_points:]
        self.curves[name].setData(d['x'], d['y'])

    def clear_all(self):
        for name in self.curves:
            self.curves[name].clear()
            self.data[name] = {'x': [], 'y': []}

# ----------------------------------------------------------------------
# 5. Main Application Window
# ----------------------------------------------------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Keysight B2910CL Precision SMU Dashboard')
        self.setGeometry(100, 100, 1400, 850)
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {Theme.BG}; }}
            QWidget {{ background-color: {Theme.PNL}; color: {Theme.FG}; }}
            QLabel {{ color: {Theme.FG}; }}
            QPushButton {{ background-color: {Theme.ACC}; color: white; border: none; padding: 6px 12px; border-radius: 4px; }}
            QPushButton:hover {{ background-color: {Theme.ACC_H}; }}
            QPushButton:pressed {{ background-color: {Theme.ACC_H}; }}
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{ background-color: {Theme.PNL2}; color: {Theme.FG}; border: 1px solid {Theme.BRD}; border-radius: 4px; padding: 4px; }}
            QTabWidget::pane {{ border: 1px solid {Theme.BRD}; background-color: {Theme.PNL}; }}
            QTabBar::tab {{ background-color: {Theme.PNL2}; color: {Theme.DIM}; padding: 8px 16px; }}
            QTabBar::tab:selected {{ background-color: {Theme.PNL}; color: {Theme.ACC}; }}
            QListWidget, QTextEdit {{ background-color: {Theme.PNL2}; color: {Theme.FG}; border: 1px solid {Theme.BRD}; }}
        """)

        # Instrument
        self.instr = None
        self.use_tcp = False
        self.is_running = False
        self.data_queue = queue.Queue()
        self.sweep_data = []

        # Build UI
        self._create_menu()
        self._create_central_widget()
        self._create_status_bar()

        # Start GUI update timer
        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self._process_queue)
        self.timer.start(50)

        # Load settings
        self._load_settings()

    # ------------------------------------------------------------------
    # UI Creation
    # ------------------------------------------------------------------
    def _create_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu('File')
        file_menu.addAction('Save Settings', self._save_settings)
        file_menu.addAction('Load Settings', self._load_settings_dialog)
        file_menu.addSeparator()
        file_menu.addAction('Exit', self.close)

        view_menu = menubar.addMenu('View')
        view_menu.addAction('Toggle Theme', self._toggle_theme, QtCore.Qt.Key_T)

        help_menu = menubar.addMenu('Help')
        help_menu.addAction('About', self._show_about)

    def _create_central_widget(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(5, 5, 5, 5)

        # Tab widget
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)

        # --- Tab 1: Connection ---
        self.conn_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.conn_tab, '🔌 Connection')
        self._build_connection_tab()

        # --- Tab 2: SMU Control ---
        self.control_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.control_tab, '⚡ SMU Control')
        self._build_control_tab()

        # --- Tab 3: Sweep ---
        self.sweep_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.sweep_tab, '📈 Sweep')
        self._build_sweep_tab()

        # --- Tab 4: SCPI Terminal ---
        self.scpi_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.scpi_tab, '💻 Terminal')
        self._build_scpi_tab()

        # --- Tab 5: Errors ---
        self.error_tab = QtWidgets.QWidget()
        self.tabs.addTab(self.error_tab, '⚠️ Errors')
        self._build_error_tab()

    def _create_status_bar(self):
        self.status = self.statusBar()
        self.status_label = QtWidgets.QLabel('Ready')
        self.status.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # Connection Tab
    # ------------------------------------------------------------------
    def _build_connection_tab(self):
        layout = QtWidgets.QVBoxLayout(self.conn_tab)

        # Mode selection
        mode_group = QtWidgets.QGroupBox('Connection Mode')
        mode_layout = QtWidgets.QHBoxLayout()
        self.tcp_radio = QtWidgets.QRadioButton('TCP/IP (Raw Socket)')
        self.tcp_radio.setChecked(True)
        self.visa_radio = QtWidgets.QRadioButton('VISA (PyVISA)')
        mode_layout.addWidget(self.tcp_radio)
        mode_layout.addWidget(self.visa_radio)
        mode_layout.addStretch()
        mode_group.setLayout(mode_layout)
        layout.addWidget(mode_group)

        # TCP settings
        self.tcp_group = QtWidgets.QGroupBox('TCP/IP Settings')
        tcp_layout = QtWidgets.QFormLayout()
        self.tcp_ip = QtWidgets.QLineEdit('192.168.0.100')
        self.tcp_port = QtWidgets.QSpinBox()
        self.tcp_port.setRange(1, 65535)
        self.tcp_port.setValue(5025)
        self.tcp_timeout = QtWidgets.QDoubleSpinBox()
        self.tcp_timeout.setRange(0.5, 60.0)
        self.tcp_timeout.setValue(5.0)
        tcp_layout.addRow('IP Address:', self.tcp_ip)
        tcp_layout.addRow('Port:', self.tcp_port)
        tcp_layout.addRow('Timeout (s):', self.tcp_timeout)
        self.tcp_group.setLayout(tcp_layout)
        layout.addWidget(self.tcp_group)

        # VISA settings
        self.visa_group = QtWidgets.QGroupBox('VISA Settings')
        visa_layout = QtWidgets.QVBoxLayout()
        self.visa_combo = QtWidgets.QComboBox()
        self.visa_combo.setEditable(True)
        self.refresh_btn = QtWidgets.QPushButton('Refresh Resources')
        self.refresh_btn.clicked.connect(self._refresh_visa)
        visa_layout.addWidget(QtWidgets.QLabel('Resource:'))
        visa_layout.addWidget(self.visa_combo)
        visa_layout.addWidget(self.refresh_btn)
        self.visa_group.setLayout(visa_layout)
        layout.addWidget(self.visa_group)

        # Connect button
        self.connect_btn = QtWidgets.QPushButton('Connect')
        self.connect_btn.clicked.connect(self._connect)
        self.connect_btn.setMinimumHeight(40)
        layout.addWidget(self.connect_btn)

        # Status
        self.conn_status = QtWidgets.QLabel('Not connected')
        self.conn_status.setStyleSheet(f'color: {Theme.ERR};')
        layout.addWidget(self.conn_status)

        layout.addStretch()

        # Connect mode toggling
        self.tcp_radio.toggled.connect(self._on_mode_toggle)
        self.visa_radio.toggled.connect(self._on_mode_toggle)
        self._on_mode_toggle()

    def _on_mode_toggle(self):
        tcp = self.tcp_radio.isChecked()
        self.tcp_group.setVisible(tcp)
        self.visa_group.setVisible(not tcp)

    def _refresh_visa(self):
        if self.instr and not self.instr.use_tcp:
            resources = self.instr.list_resources()
            self.visa_combo.clear()
            self.visa_combo.addItems(resources)
        else:
            # Create temporary VISA instance to scan
            tmp = VISAInstrument()
            resources = tmp.list_resources()
            self.visa_combo.clear()
            self.visa_combo.addItems(resources)

    def _connect(self):
        try:
            self.use_tcp = self.tcp_radio.isChecked()
            self.instr = B2910CL(use_tcp=self.use_tcp, debug=False)

            if self.use_tcp:
                ip = self.tcp_ip.text()
                port = self.tcp_port.value()
                timeout = self.tcp_timeout.value()
                idn = self.instr.connect_tcp(ip, port, timeout)
            else:
                resource = self.visa_combo.currentText()
                if not resource:
                    QtWidgets.QMessageBox.warning(self, 'Error', 'No VISA resource selected.')
                    return
                idn = self.instr.connect_visa(resource, 10000)

            self.conn_status.setText(f'Connected: {idn}')
            self.conn_status.setStyleSheet(f'color: #10b981;')
            self.connect_btn.setText('Disconnect')
            self.connect_btn.clicked.disconnect()
            self.connect_btn.clicked.connect(self._disconnect)
            self._enable_controls(True)
            self.status_label.setText('Connected')

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Connection Error', str(e))
            self.conn_status.setText('Connection failed')
            self.conn_status.setStyleSheet(f'color: {Theme.ERR};')

    def _disconnect(self):
        if self.instr:
            self.instr.disconnect()
        self.instr = None
        self.conn_status.setText('Disconnected')
        self.conn_status.setStyleSheet(f'color: {Theme.ERR};')
        self.connect_btn.setText('Connect')
        self.connect_btn.clicked.disconnect()
        self.connect_btn.clicked.connect(self._connect)
        self._enable_controls(False)
        self.status_label.setText('Disconnected')

    def _enable_controls(self, enabled: bool):
        # Enable/disable all control widgets
        pass  # Will be implemented in control tab

    # ------------------------------------------------------------------
    # SMU Control Tab
    # ------------------------------------------------------------------
    def _build_control_tab(self):
        layout = QtWidgets.QHBoxLayout(self.control_tab)

        # Left: Controls
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)

        # Mode
        mode_group = QtWidgets.QGroupBox('Source Mode')
        mode_layout = QtWidgets.QHBoxLayout()
        self.mode_voltage = QtWidgets.QRadioButton('Voltage')
        self.mode_voltage.setChecked(True)
        self.mode_current = QtWidgets.QRadioButton('Current')
        mode_layout.addWidget(self.mode_voltage)
        mode_layout.addWidget(self.mode_current)
        mode_group.setLayout(mode_layout)
        left_layout.addWidget(mode_group)

        # Level
        level_group = QtWidgets.QGroupBox('Source Level')
        level_layout = QtWidgets.QFormLayout()
        self.level_spin = QtWidgets.QDoubleSpinBox()
        self.level_spin.setRange(-200, 200)
        self.level_spin.setDecimals(6)
        self.level_spin.setValue(1.0)
        self.level_spin.setSingleStep(0.1)
        level_layout.addRow('Level:', self.level_spin)

        self.compliance_spin = QtWidgets.QDoubleSpinBox()
        self.compliance_spin.setRange(0, 200)
        self.compliance_spin.setDecimals(6)
        self.compliance_spin.setValue(0.1)
        level_layout.addRow('Compliance:', self.compliance_spin)
        level_group.setLayout(level_layout)
        left_layout.addWidget(level_group)

        # Output
        output_group = QtWidgets.QGroupBox('Output')
        output_layout = QtWidgets.QHBoxLayout()
        self.output_btn = QtWidgets.QPushButton('Output OFF')
        self.output_btn.setCheckable(True)
        self.output_btn.setStyleSheet('QPushButton { background-color: #ef4444; color: white; } QPushButton:checked { background-color: #10b981; }')
        self.output_btn.toggled.connect(self._on_output_toggle)
        output_layout.addWidget(self.output_btn)
        output_group.setLayout(output_layout)
        left_layout.addWidget(output_group)

        # Apply button
        self.apply_btn = QtWidgets.QPushButton('Apply Settings')
        self.apply_btn.clicked.connect(self._apply_settings)
        self.apply_btn.setMinimumHeight(40)
        left_layout.addWidget(self.apply_btn)

        # Readback
        read_group = QtWidgets.QGroupBox('Readback')
        read_layout = QtWidgets.QFormLayout()
        self.read_v_label = QtWidgets.QLabel('--')
        self.read_i_label = QtWidgets.QLabel('--')
        self.read_p_label = QtWidgets.QLabel('--')
        read_layout.addRow('Voltage:', self.read_v_label)
        read_layout.addRow('Current:', self.read_i_label)
        read_layout.addRow('Power:', self.read_p_label)
        read_group.setLayout(read_layout)
        left_layout.addWidget(read_group)

        left_layout.addStretch()

        # Right: Plot
        self.plot = LivePlotWidget()
        self.plot.add_trace('Voltage', '#38bdf8')
        self.plot.add_trace('Current', '#10b981')
        self.plot.add_trace('Power', '#f59e0b')

        # Splitter
        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.plot)
        splitter.setSizes([400, 800])
        layout.addWidget(splitter)

        # Update timer for readback
        self.read_timer = QtCore.QTimer()
        self.read_timer.timeout.connect(self._update_readback)
        self.read_timer.start(200)

    def _on_output_toggle(self, checked: bool):
        if not self.instr or not self.instr.connected:
            self.output_btn.setChecked(False)
            return
        try:
            self.instr.output_on(checked)
            self.output_btn.setText('Output ON' if checked else 'Output OFF')
        except Exception as e:
            self.output_btn.setChecked(not checked)
            QtWidgets.QMessageBox.warning(self, 'Output Error', str(e))

    def _apply_settings(self):
        if not self.instr or not self.instr.connected:
            QtWidgets.QMessageBox.warning(self, 'Error', 'Not connected.')
            return
        try:
            level = self.level_spin.value()
            compliance = self.compliance_spin.value()
            if self.mode_voltage.isChecked():
                self.instr.set_mode('voltage')
                self.instr.set_voltage(level, compliance)
            else:
                self.instr.set_mode('current')
                self.instr.set_current(level, compliance)
            self.status_label.setText('Settings applied')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', str(e))

    def _update_readback(self):
        if not self.instr or not self.instr.connected or not self.output_btn.isChecked():
            return
        try:
            v = self.instr.measure_voltage()
            i = self.instr.measure_current()
            p = v * i
            self.read_v_label.setText(f'{v:.6f} V')
            self.read_i_label.setText(f'{i:.6f} A')
            self.read_p_label.setText(f'{p:.6f} W')

            # Update plot
            t = time.time()
            self.plot.update_trace('Voltage', t, v)
            self.plot.update_trace('Current', t, i)
            self.plot.update_trace('Power', t, p)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Sweep Tab
    # ------------------------------------------------------------------
    def _build_sweep_tab(self):
        layout = QtWidgets.QHBoxLayout(self.sweep_tab)

        # Left: Controls
        left = QtWidgets.QWidget()
        left_layout = QtWidgets.QVBoxLayout(left)

        sweep_group = QtWidgets.QGroupBox('Sweep Parameters')
        sweep_layout = QtWidgets.QFormLayout()

        self.sweep_mode = QtWidgets.QComboBox()
        self.sweep_mode.addItems(['Voltage Sweep', 'Current Sweep'])
        sweep_layout.addRow('Mode:', self.sweep_mode)

        self.sweep_start = QtWidgets.QDoubleSpinBox()
        self.sweep_start.setRange(-200, 200)
        self.sweep_start.setValue(0.0)
        sweep_layout.addRow('Start:', self.sweep_start)

        self.sweep_stop = QtWidgets.QDoubleSpinBox()
        self.sweep_stop.setRange(-200, 200)
        self.sweep_stop.setValue(1.0)
        sweep_layout.addRow('Stop:', self.sweep_stop)

        self.sweep_steps = QtWidgets.QSpinBox()
        self.sweep_steps.setRange(2, 1000)
        self.sweep_steps.setValue(20)
        sweep_layout.addRow('Steps:', self.sweep_steps)

        self.sweep_compliance = QtWidgets.QDoubleSpinBox()
        self.sweep_compliance.setRange(0, 200)
        self.sweep_compliance.setValue(0.1)
        sweep_layout.addRow('Compliance:', self.sweep_compliance)

        self.sweep_delay = QtWidgets.QDoubleSpinBox()
        self.sweep_delay.setRange(0, 60)
        self.sweep_delay.setValue(0.01)
        sweep_layout.addRow('Delay (s):', self.sweep_delay)

        sweep_group.setLayout(sweep_layout)
        left_layout.addWidget(sweep_group)

        self.sweep_btn = QtWidgets.QPushButton('Run Sweep')
        self.sweep_btn.clicked.connect(self._run_sweep)
        self.sweep_btn.setMinimumHeight(40)
        left_layout.addWidget(self.sweep_btn)

        self.sweep_export_btn = QtWidgets.QPushButton('Export CSV')
        self.sweep_export_btn.clicked.connect(self._export_sweep)
        left_layout.addWidget(self.sweep_export_btn)

        left_layout.addStretch()

        # Right: Plot
        self.sweep_plot = pg.PlotWidget()
        self.sweep_plot.setBackground(Theme.CV_BG)
        self.sweep_plot.showGrid(x=True, y=True, alpha=0.3)
        self.sweep_plot.setLabel('left', 'Current', units='A')
        self.sweep_plot.setLabel('bottom', 'Voltage', units='V')
        self.sweep_curve = self.sweep_plot.plot([], [], pen=pg.mkPen(color='#38bdf8', width=2))

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.sweep_plot)
        splitter.setSizes([350, 800])
        layout.addWidget(splitter)

    def _run_sweep(self):
        if not self.instr or not self.instr.connected:
            QtWidgets.QMessageBox.warning(self, 'Error', 'Not connected.')
            return
        try:
            start = self.sweep_start.value()
            stop = self.sweep_stop.value()
            steps = self.sweep_steps.value()
            compliance = self.sweep_compliance.value()
            delay = self.sweep_delay.value()
            mode = 'voltage' if self.sweep_mode.currentIndex() == 0 else 'current'

            # Build sweep list
            sweep_vals = np.linspace(start, stop, steps)

            # Configure instrument
            self.instr.reset()
            if mode == 'voltage':
                self.instr.set_mode('voltage')
                self.instr.write(f':SOUR:VOLT:MODE LIST')
                self.instr.write(f':SOUR:LIST:VOLT {",".join(map(str, sweep_vals))}')
                self.instr.write(f':SOUR:CURR:PROT {compliance}')
            else:
                self.instr.set_mode('current')
                self.instr.write(f':SOUR:CURR:MODE LIST')
                self.instr.write(f':SOUR:LIST:CURR {",".join(map(str, sweep_vals))}')
                self.instr.write(f':SOUR:VOLT:PROT {compliance}')

            self.instr.write(f':TRIG:DEL {delay}')
            self.instr.write(':OUTP ON')
            self.instr.write(':INIT:IMM')
            self.instr.write('*WAI')

            # Fetch results
            if mode == 'voltage':
                # Measure current for each step
                data = self.instr.query_ascii_values(':FETC:ARR:CURR?')
            else:
                data = self.instr.query_ascii_values(':FETC:ARR:VOLT?')

            self.sweep_data = list(zip(sweep_vals, data))

            # Update plot
            x_vals = [d[0] for d in self.sweep_data]
            y_vals = [d[1] for d in self.sweep_data]
            self.sweep_curve.setData(x_vals, y_vals)
            self.sweep_plot.setLabel('bottom', 'Voltage' if mode == 'voltage' else 'Current')
            self.sweep_plot.setLabel('left', 'Current' if mode == 'voltage' else 'Voltage')
            self.status_label.setText('Sweep completed')

            # Turn output off
            self.instr.output_on(False)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Sweep Error', str(e))
            self.instr.output_on(False)

    def _export_sweep(self):
        if not self.sweep_data:
            QtWidgets.QMessageBox.warning(self, 'Error', 'No sweep data to export.')
            return
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self, 'Export Sweep Data', '', 'CSV Files (*.csv)'
        )
        if not path:
            return
        try:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Source', 'Measure'])
                writer.writerows(self.sweep_data)
            self.status_label.setText(f'Data exported to {path}')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Export Error', str(e))

    # ------------------------------------------------------------------
    # SCPI Terminal Tab
    # ------------------------------------------------------------------
    def _build_scpi_tab(self):
        layout = QtWidgets.QVBoxLayout(self.scpi_tab)

        self.scpi_output = QtWidgets.QTextEdit()
        self.scpi_output.setReadOnly(True)
        self.scpi_output.setFont(QtGui.QFont('Consolas', 10))
        layout.addWidget(self.scpi_output)

        input_row = QtWidgets.QHBoxLayout()
        self.scpi_input = QtWidgets.QLineEdit()
        self.scpi_input.returnPressed.connect(self._send_scpi)
        input_row.addWidget(self.scpi_input)

        send_btn = QtWidgets.QPushButton('Send')
        send_btn.clicked.connect(self._send_scpi)
        input_row.addWidget(send_btn)

        clear_btn = QtWidgets.QPushButton('Clear')
        clear_btn.clicked.connect(self.scpi_output.clear)
        input_row.addWidget(clear_btn)

        layout.addLayout(input_row)

    def _send_scpi(self):
        if not self.instr or not self.instr.connected:
            QtWidgets.QMessageBox.warning(self, 'Error', 'Not connected.')
            return
        cmd = self.scpi_input.text().strip()
        if not cmd:
            return
        self.scpi_input.clear()
        self.scpi_output.append(f'>>> {cmd}')
        try:
            if '?' in cmd:
                resp = self.instr.query(cmd)
                self.scpi_output.append(resp)
            else:
                self.instr.write(cmd)
                self.scpi_output.append('Command sent.')
        except Exception as e:
            self.scpi_output.append(f'ERROR: {e}')

    # ------------------------------------------------------------------
    # Error Tab
    # ------------------------------------------------------------------
    def _build_error_tab(self):
        layout = QtWidgets.QVBoxLayout(self.error_tab)

        self.error_output = QtWidgets.QTextEdit()
        self.error_output.setReadOnly(True)
        self.error_output.setFont(QtGui.QFont('Consolas', 10))
        layout.addWidget(self.error_output)

        btn_row = QtWidgets.QHBoxLayout()
        refresh_btn = QtWidgets.QPushButton('Refresh Errors')
        refresh_btn.clicked.connect(self._fetch_errors)
        btn_row.addWidget(refresh_btn)

        clear_btn = QtWidgets.QPushButton('Clear Display')
        clear_btn.clicked.connect(self.error_output.clear)
        btn_row.addWidget(clear_btn)

        layout.addLayout(btn_row)

    def _fetch_errors(self):
        if not self.instr or not self.instr.connected:
            QtWidgets.QMessageBox.warning(self, 'Error', 'Not connected.')
            return
        try:
            errors = self.instr.read_errors()
            if errors:
                self.error_output.append(f'--- {datetime.now().strftime("%H:%M:%S")} ---')
                for err in errors:
                    self.error_output.append(err)
            else:
                self.error_output.append(f'--- {datetime.now().strftime("%H:%M:%S")} --- No errors')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', str(e))

    # ------------------------------------------------------------------
    # GUI Update Loop
    # ------------------------------------------------------------------
    def _process_queue(self):
        try:
            while True:
                item = self.data_queue.get_nowait()
                if isinstance(item, Exception):
                    self.status_label.setText(f'Error: {item}')
                elif isinstance(item, dict):
                    # Update plot from worker thread
                    pass
        except queue.Empty:
            pass

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def _toggle_theme(self):
        Theme.toggle()
        # Update stylesheet
        self.setStyleSheet(f"""
            QMainWindow {{ background-color: {Theme.BG}; }}
            QWidget {{ background-color: {Theme.PNL}; color: {Theme.FG}; }}
            QLabel {{ color: {Theme.FG}; }}
            QPushButton {{ background-color: {Theme.ACC}; color: white; border: none; padding: 6px 12px; border-radius: 4px; }}
            QPushButton:hover {{ background-color: {Theme.ACC_H}; }}
            QPushButton:pressed {{ background-color: {Theme.ACC_H}; }}
            QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox {{ background-color: {Theme.PNL2}; color: {Theme.FG}; border: 1px solid {Theme.BRD}; border-radius: 4px; padding: 4px; }}
            QTabWidget::pane {{ border: 1px solid {Theme.BRD}; background-color: {Theme.PNL}; }}
            QTabBar::tab {{ background-color: {Theme.PNL2}; color: {Theme.DIM}; padding: 8px 16px; }}
            QTabBar::tab:selected {{ background-color: {Theme.PNL}; color: {Theme.ACC}; }}
            QListWidget, QTextEdit {{ background-color: {Theme.PNL2}; color: {Theme.FG}; border: 1px solid {Theme.BRD}; }}
        """)
        # Update plots
        self.plot.setBackground(Theme.CV_BG)
        self.sweep_plot.setBackground(Theme.CV_BG)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _load_settings(self):
        try:
            with open('b2910cl_settings.json', 'r') as f:
                data = json.load(f)
                self.tcp_ip.setText(data.get('tcp_ip', '192.168.0.100'))
                self.tcp_port.setValue(data.get('tcp_port', 5025))
                self.tcp_timeout.setValue(data.get('tcp_timeout', 5.0))
                self.level_spin.setValue(data.get('level', 1.0))
                self.compliance_spin.setValue(data.get('compliance', 0.1))
                self.sweep_start.setValue(data.get('sweep_start', 0.0))
                self.sweep_stop.setValue(data.get('sweep_stop', 1.0))
                self.sweep_steps.setValue(data.get('sweep_steps', 20))
        except:
            pass

    def _save_settings(self):
        data = {
            'tcp_ip': self.tcp_ip.text(),
            'tcp_port': self.tcp_port.value(),
            'tcp_timeout': self.tcp_timeout.value(),
            'level': self.level_spin.value(),
            'compliance': self.compliance_spin.value(),
            'sweep_start': self.sweep_start.value(),
            'sweep_stop': self.sweep_stop.value(),
            'sweep_steps': self.sweep_steps.value(),
        }
        try:
            with open('b2910cl_settings.json', 'w') as f:
                json.dump(data, f, indent=2)
            self.status_label.setText('Settings saved')
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, 'Error', f'Could not save settings: {e}')

    def _load_settings_dialog(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, 'Load Settings', '', 'JSON Files (*.json)'
        )
        if not path:
            return
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                self.tcp_ip.setText(data.get('tcp_ip', '192.168.0.100'))
                self.tcp_port.setValue(data.get('tcp_port', 5025))
                self.tcp_timeout.setValue(data.get('tcp_timeout', 5.0))
                self.level_spin.setValue(data.get('level', 1.0))
                self.compliance_spin.setValue(data.get('compliance', 0.1))
                self.sweep_start.setValue(data.get('sweep_start', 0.0))
                self.sweep_stop.setValue(data.get('sweep_stop', 1.0))
                self.sweep_steps.setValue(data.get('sweep_steps', 20))
            self.status_label.setText(f'Settings loaded from {path}')
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, 'Error', f'Could not load settings: {e}')

    # ------------------------------------------------------------------
    # About
    # ------------------------------------------------------------------
    def _show_about(self):
        QtWidgets.QMessageBox.about(
            self, 'About B2910CL Dashboard',
            'Keysight B2910CL Precision SMU Control Dashboard\n'
            'Version 1.0\n\n'
            'Features:\n'
            '- VISA & TCP/IP (raw socket) connection\n'
            '- Power supply mode with live plotting\n'
            '- IV sweep with CSV export\n'
            '- SCPI terminal\n'
            '- Error logging\n'
            '- Dark/light theme toggle\n\n'
            'Inspired by keithley-tool (github.com/schwemmdx/keithley-tool)'
        )

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        self._save_settings()
        if self.instr:
            try:
                self.instr.output_on(False)
                self.instr.disconnect()
            except:
                pass
        event.accept()

# ----------------------------------------------------------------------
# 6. Main entry point
# ----------------------------------------------------------------------
if __name__ == '__main__':
    set_hd_resolution()
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle('Fusion')
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())