import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import pyvisa
import threading
import math
import csv
import pandas as pd
import numpy as np

# Matplotlib for embedded graphing
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

# Set modern theme
ctk.set_appearance_mode("Dark")  
ctk.set_default_color_theme("blue")  

class B2910CL_ControllerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Keysight B2910CL Master Controller")
        self.geometry("1200x800")
        self.rm = pyvisa.ResourceManager()
        self.smu = None
        self.is_running = False

        # Build the UI
        self.build_ui()
        self.scan_visa_resources()

    def build_ui(self):
        # Configure grid layout (1 column for sidebar, 1 for main content)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ==========================================
        # LEFT SIDEBAR: Connection & Status
        # ==========================================
        self.sidebar = ctk.CTkFrame(self, width=250, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(8, weight=1)

        ctk.CTkLabel(self.sidebar, text="Connection Setup", font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=0, padx=20, pady=(20, 10))
        
        self.visa_dropdown = ctk.CTkComboBox(self.sidebar, values=["Scanning..."])
        self.visa_dropdown.grid(row=1, column=0, padx=20, pady=10, sticky="ew")
        
        self.btn_rescan = ctk.CTkButton(self.sidebar, text="Rescan USB Ports", command=self.scan_visa_resources)
        self.btn_rescan.grid(row=2, column=0, padx=20, pady=10, sticky="ew")

        self.btn_connect = ctk.CTkButton(self.sidebar, text="Connect to SMU", command=self.connect_instrument, fg_color="green")
        self.btn_connect.grid(row=3, column=0, padx=20, pady=10, sticky="ew")

        self.lbl_status = ctk.CTkLabel(self.sidebar, text="Status: Disconnected", text_color="red")
        self.lbl_status.grid(row=4, column=0, padx=20, pady=10)

        # Run/Stop Controls
        ctk.CTkLabel(self.sidebar, text="Execution", font=ctk.CTkFont(size=20, weight="bold")).grid(row=5, column=0, padx=20, pady=(40, 10))
        
        self.btn_run = ctk.CTkButton(self.sidebar, text="START TEST", command=self.start_test_thread, height=50, font=ctk.CTkFont(size=18, weight="bold"))
        self.btn_run.grid(row=6, column=0, padx=20, pady=10, sticky="ew")
        
        self.btn_stop = ctk.CTkButton(self.sidebar, text="EMERGENCY STOP", command=self.emergency_stop, fg_color="red", hover_color="darkred", height=50, font=ctk.CTkFont(size=18, weight="bold"))
        self.btn_stop.grid(row=7, column=0, padx=20, pady=10, sticky="ew")

        # ==========================================
        # RIGHT PANEL: Tabs
        # ==========================================
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=1, padx=20, pady=20, sticky="nsew")
        
        self.tab_config = self.tabview.add("Test Configuration")
        self.tab_live   = self.tabview.add("Live Results Plot")
        self.tab_viewer = self.tabview.add("CSV Data Viewer")

        self.build_config_tab()
        self.build_plot_tab(self.tab_live, live=True)
        self.build_viewer_tab()

    def build_config_tab(self):
        # Waveform Selection
        frame_wave = ctk.CTkFrame(self.tab_config)
        frame_wave.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_wave, text="1. Select Waveform Shape", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        
        self.wave_var = ctk.StringVar(value="Sine Wave")
        waves = ["Sine Wave", "Cosine Wave", "Square Wave (Pulse)", "Staircase Sweep", "DC Hold"]
        self.wave_dropdown = ctk.CTkComboBox(frame_wave, values=waves, variable=self.wave_var, width=300)
        self.wave_dropdown.pack(anchor="w", padx=10, pady=5)

        # Parameters Input Grid
        frame_params = ctk.CTkFrame(self.tab_config)
        frame_params.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_params, text="2. Electrical Parameters", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=5)

        self.inputs = {}
        params = [
            ("Base/Min Current (A):", "0.005"),
            ("Peak/Max Current (A):", "0.040"),
            ("Compliance Voltage (V):", "10.0"),
            ("Cycle Period/Duration (s):", "4.0"),
            ("Total Test Time (s):", "12.0"),
            ("Resolution (Points/Cycle):", "200")
        ]

        for i, (label_text, default_val) in enumerate(params):
            ctk.CTkLabel(frame_params, text=label_text).grid(row=i+1, column=0, padx=10, pady=5, sticky="w")
            entry = ctk.CTkEntry(frame_params, width=150)
            entry.insert(0, default_val)
            entry.grid(row=i+1, column=1, padx=10, pady=5, sticky="w")
            self.inputs[label_text] = entry

        # File Saving
        frame_save = ctk.CTkFrame(self.tab_config)
        frame_save.pack(fill="x", padx=20, pady=10)
        ctk.CTkLabel(frame_save, text="3. Data Logging", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        
        self.save_name = ctk.CTkEntry(frame_save, width=400, placeholder_text="Enter filename (e.g., test_run_1.csv)")
        self.save_name.insert(0, "b2910cl_test_data.csv")
        self.save_name.pack(anchor="w", padx=10, pady=5)

    def build_plot_tab(self, parent, live=False):
        self.fig = Figure(figsize=(8, 5), dpi=100)
        self.ax1 = self.fig.add_subplot(111)
        self.ax2 = self.ax1.twinx()
        
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        
        toolbar = NavigationToolbar2Tk(self.canvas, parent)
        toolbar.update()
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

    def build_viewer_tab(self):
        btn_load = ctk.CTkButton(self.tab_viewer, text="Load CSV File", command=self.load_csv_file)
        btn_load.pack(pady=10)
        self.build_plot_tab(self.tab_viewer)

    # ==========================================
    # HARDWARE COMMUNICATION
    # ==========================================
    def scan_visa_resources(self):
        self.visa_dropdown.set("Scanning...")
        self.update()
        try:
            resources = self.rm.list_resources()
            if not resources:
                self.visa_dropdown.configure(values=["No Instruments Found!"])
                self.visa_dropdown.set("No Instruments Found!")
            else:
                self.visa_dropdown.configure(values=list(resources))
                # Auto-select the first USB device if available
                usb_devs = [r for r in resources if "USB" in r]
                self.visa_dropdown.set(usb_devs[0] if usb_devs else resources[0])
        except Exception as e:
            self.visa_dropdown.set(f"Error: {e}")

    def connect_instrument(self):
        addr = self.visa_dropdown.get()
        if not addr or "No" in addr or "Error" in addr:
            messagebox.showerror("Connection Error", "Please select a valid VISA address.")
            return

        try:
            self.smu = self.rm.open_resource(addr)
            self.smu.timeout = 10000
            idn = self.smu.query("*IDN?").strip()
            self.lbl_status.configure(text=f"Connected:\n{idn.split(',')[1]}", text_color="green")
            self.btn_connect.configure(state="disabled")
        except Exception as e:
            self.lbl_status.configure(text="Connection Failed", text_color="red")
            messagebox.showerror("VISA Error", str(e))

    def emergency_stop(self):
        if self.smu:
            try:
                self.smu.write(":OUTP OFF")
                self.lbl_status.configure(text="OUTPUT KILLED", text_color="orange")
            except:
                pass
        self.is_running = False

    # ==========================================
    # TEST EXECUTION ENGINE (Threaded)
    # ==========================================
    def start_test_thread(self):
        if not self.smu:
            messagebox.showwarning("Not Connected", "Please connect to the instrument first.")
            return
        if self.is_running:
            return
            
        self.is_running = True
        self.btn_run.configure(state="disabled", text="TEST RUNNING...")
        self.tabview.set("Live Results Plot")
        
        # Start hardware control in a background thread to keep GUI active
        thread = threading.Thread(target=self.execute_test)
        thread.daemon = True
        thread.start()

    def execute_test(self):
        try:
            # 1. Read UI Parameters
            min_i  = float(self.inputs["Base/Min Current (A):"].get())
            max_i  = float(self.inputs["Peak/Max Current (A):"].get())
            v_lim  = float(self.inputs["Compliance Voltage (V):"].get())
            period = float(self.inputs["Cycle Period/Duration (s):"].get())
            total_time = float(self.inputs["Total Test Time (s):"].get())
            pts_per_cycle = int(self.inputs["Resolution (Points/Cycle):"].get())
            shape = self.wave_var.get()

            # 2. Mathematical Generator Engine
            list_values = []
            step_time = period / pts_per_cycle
            
            if shape == "Sine Wave":
                amp = (max_i - min_i) / 2.0
                off = (max_i + min_i) / 2.0
                for tick in range(pts_per_cycle):
                    t = tick * step_time
                    val = off - amp * math.cos(2 * math.pi * (t / period))
                    list_values.append(round(val, 6))
                    
            elif shape == "Cosine Wave":
                amp = (max_i - min_i) / 2.0
                off = (max_i + min_i) / 2.0
                for tick in range(pts_per_cycle):
                    t = tick * step_time
                    val = off + amp * math.cos(2 * math.pi * (t / period))
                    list_values.append(round(val, 6))
                    
            elif shape == "Square Wave (Pulse)":
                half_pts = pts_per_cycle // 2
                list_values = [min_i]*half_pts + [max_i]*half_pts
                
            elif shape == "Staircase Sweep":
                # Linear spaced points
                list_values = list(np.linspace(min_i, max_i, pts_per_cycle))
            
            elif shape == "DC Hold":
                list_values = [max_i] * pts_per_cycle

            list_str = ",".join(map(str, list_values))
            total_source_ticks = int(total_time / step_time)

            # 3. Hardware SCPI Sequence
            self.smu.write("*RST")
            self.smu.write("*CLS")
            
            # Source Setup
            self.smu.write(":SOUR:FUNC:MODE CURR")
            self.smu.write(":SOUR:CURR:MODE LIST")
            self.smu.write(f":SOUR:CURR:RANG {max(abs(min_i), abs(max_i))}")
            self.smu.write(f":SOUR:LIST:CURR {list_str}")
            
            self.smu.write(":TRIG:TRAN:SOUR TIM")
            self.smu.write(f":TRIG:TRAN:TIM {step_time}") 
            self.smu.write(f":TRIG:TRAN:COUN {total_source_ticks}") 
            
            # Measurement Setup
            self.smu.write(":SENS:FUNC \"VOLT\",\"CURR\"")
            self.smu.write(f":SENS:VOLT:PROT {v_lim}")
            self.smu.write(f":SENS:VOLT:APER {step_time * 0.5}")
            self.smu.write(f":SENS:CURR:APER {step_time * 0.5}")
            
            self.smu.write(":TRIG:ACQ:SOUR TIM")
            self.smu.write(f":TRIG:ACQ:TIM {step_time}")
            self.smu.write(f":TRIG:ACQ:COUN {total_source_ticks}")
            self.smu.write(":FORM:DATA ASC")

            # Extend timeout safely for the length of the test
            self.smu.timeout = int((total_time + 10) * 1000)

            # 4. EXECUTE
            self.smu.write(":OUTP ON")
            self.smu.write(":INIT:ACQ")
            self.smu.write(":INIT:TRAN")
            
            self.smu.write("*WAI") # Wait for hardware completion
            self.smu.write(":OUTP OFF")

            # 5. Fetch Data
            if self.is_running: # Check if emergency stop was hit
                time_data = self.smu.query_ascii_values(":FETC:ARR:TIME?")
                curr_data = self.smu.query_ascii_values(":FETC:ARR:CURR?")
                volt_data = self.smu.query_ascii_values(":FETC:ARR:VOLT?")

                # Save Data
                filename = self.save_name.get()
                with open(filename, mode='w', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow(["Time (s)", "Current (A)", "Voltage (V)"])
                    for t, c, v in zip(time_data, curr_data, volt_data):
                        writer.writerow([t, c, v])

                # Update Plot via UI Thread
                self.after(0, self.update_live_plot, time_data, curr_data, volt_data)

        except Exception as e:
            self.after(0, lambda: messagebox.showerror("Hardware Error", str(e)))
        finally:
            self.after(0, self.reset_run_button)

    def reset_run_button(self):
        self.is_running = False
        self.btn_run.configure(state="normal", text="START TEST")
        try:
            self.smu.write(":OUTP OFF")
        except: pass

    # ==========================================
    # DATA VISUALIZATION
    # ==========================================
    def update_live_plot(self, t, c, v):
        self.ax1.clear()
        self.ax2.clear()

        c_ma = [x * 1000 for x in c] # Convert to mA
        
        self.ax1.plot(t, c_ma, color='tab:red', label="Current (mA)")
        self.ax1.set_xlabel("Time (s)")
        self.ax1.set_ylabel("Current (mA)", color='tab:red')
        self.ax1.tick_params(axis='y', labelcolor='tab:red')
        self.ax1.grid(True, linestyle='--', alpha=0.5)

        self.ax2.plot(t, v, color='tab:blue', linestyle='--', label="Voltage (V)")
        self.ax2.set_ylabel("Voltage (V)", color='tab:blue')
        self.ax2.tick_params(axis='y', labelcolor='tab:blue')

        self.fig.tight_layout()
        self.canvas.draw()

    def load_csv_file(self):
        file_path = filedialog.askopenfilename(filetypes=[("CSV Files", "*.csv")])
        if file_path:
            df = pd.read_csv(file_path)
            # Assuming headers: Time (s), Current (A), Voltage (V)
            t = df.iloc[:, 0].values
            c = df.iloc[:, 1].values
            v = df.iloc[:, 2].values
            
            # Update the plot in the Viewer Tab
            self.update_live_plot(t, c, v)

if __name__ == "__main__":
    app = B2910CL_ControllerApp()
    app.mainloop()