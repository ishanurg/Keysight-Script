import pyvisa
import time
import csv
import matplotlib.pyplot as plt

# ==============================================================================
# 1. TEST CONFIGURATION VARIABLES (Edit these as needed)
# ==============================================================================
# Overall Duration Settings
test_duration_minutes  = 1.0     # Total time to run the continuous loop (in minutes)
cycle_interval_seconds = 6.0     # Total time between the START of each cycle 
                                 # (e.g., 4s triangle + 2s idle time = 6s cycle)

# Current and Voltage Settings
base_current  = 0.005   # Starting and ending current of the triangle in Amps (5 mA)
peak_current  = 0.020   # Peak current of the triangle in Amps (20 mA)
voltage_limit = 5.0     # Compliance voltage limit in Volts

# Triangle Sweep Timing
ramp_up_time   = 2.0    # Time to ramp from base to peak (seconds)
ramp_down_time = 2.0    # Time to ramp from peak back to base (seconds)
total_sweep_time = ramp_up_time + ramp_down_time  # Total active pulse = 4.0 seconds

# Measurement Settings
num_points    = 400     # Number of data points per triangle (400 pts = very smooth 10ms steps)
csv_filename  = "b2900_triangle_data.csv" # File to save the long-run data
# ==============================================================================

rm = pyvisa.ResourceManager()
visa_addr = 'USB0::0x2A8D::0x2404::MY65150204::INSTR'

# Master arrays to hold all data across the entire test duration
master_time = []
master_curr = []
master_volt = []

try:
    nst = rm.open_resource(visa_addr)
    nst.timeout = 10000  
    
    print("Connected to --> " + nst.query("*IDN?").strip())
    
    # Reset instrument and clear errors
    nst.write("*RST")
    nst.write("*CLS")
    
    # --------------------------------------------------------------------------
    # 2. SOURCE & MEASUREMENT CONFIGURATION (Triangle Sweep)
    # --------------------------------------------------------------------------
    nst.write(":SOUR:FUNC:MODE CURR")
    nst.write(":SOUR:CURR:MODE SWE")                 # Use Sweep mode instead of fixed pulse
    
    nst.write(f":SOUR:CURR:STAR {base_current}")     # Start at 5mA
    nst.write(f":SOUR:CURR:STOP {peak_current}")     # Peak at 20mA
    
    # Set fixed range to max current to prevent range-switching delays
    range_val = max(abs(base_current), abs(peak_current))
    if range_val == 0: range_val = 1e-3
    nst.write(f":SOUR:CURR:RANG {range_val}")
    
    nst.write(f":SOUR:SWE:POIN {num_points}")        # Total points in the sweep
    nst.write(":SOUR:SWE:DIR UPDO")                  # Up-Down Sweep (Start -> Stop -> Start)
    
    nst.write(":SENS:FUNC \"VOLT\",\"CURR\"")
    nst.write(f":SENS:VOLT:PROT {voltage_limit}")
    
    # Calculate step time (how long the SMU stays at each micro-step of the triangle)
    step_time = total_sweep_time / num_points
    aperture_time = step_time * 0.5                  # 50% integration time
    
    nst.write(f":SENS:VOLT:APER {aperture_time}")
    nst.write(f":SENS:CURR:APER {aperture_time}")
    
    # Trigger routing: Timer handles the source steps, Acquisition syncs to Source
    nst.write(f":TRIG:TRAN:COUN {num_points}")
    nst.write(":TRIG:TRAN:SOUR TIM")
    nst.write(f":TRIG:TRAN:TIM {step_time}")
    
    nst.write(f":TRIG:ACQ:COUN {num_points}")
    nst.write(":TRIG:ACQ:SOUR AINT")                 # Auto Internal: Sync measurement exactly to source step
    
    nst.write(":FORM:DATA ASC")
    
    # --------------------------------------------------------------------------
    # 3. CONTINUOUS TEST LOOP
    # --------------------------------------------------------------------------
    print(f"\nStarting {test_duration_minutes}-minute triangle pulse test...")
    print(f"A 4-second triangle will trigger every {cycle_interval_seconds} seconds.")
    
    nst.write(":OUTP ON") # Turns on holding at the start point (5mA)
    
    test_duration_seconds = test_duration_minutes * 60.0
    start_time = time.time()
    pulse_count = 1
    
    while (time.time() - start_time) < test_duration_seconds:
        loop_start = time.time()
        elapsed_test_time = loop_start - start_time
        
        print(f"[{elapsed_test_time:.1f}s] Triggering Triangle Cycle #{pulse_count}...")
        
        # Arm measurement and source, then wait for completion
        nst.write(":INIT:ACQ")
        nst.write(":INIT:TRAN")
        nst.write("*WAI") 
        
        # Fetch the short burst of data
        time_data = nst.query_ascii_values(":FETC:ARR:TIME?")
        curr_data = nst.query_ascii_values(":FETC:ARR:CURR?")
        volt_data = nst.query_ascii_values(":FETC:ARR:VOLT?")
        
        # Convert instrument relative time to continuous absolute time
        absolute_time_data = [t + elapsed_test_time for t in time_data]
        
        # Append to master lists
        master_time.extend(absolute_time_data)
        master_curr.extend(curr_data)
        master_volt.extend(volt_data)
        
        # Calculate how long to sleep before starting the next triangle
        processing_time = time.time() - loop_start
        sleep_time = cycle_interval_seconds - processing_time
        if sleep_time > 0:
            time.sleep(sleep_time)
            
        pulse_count += 1

    # End of test
    nst.write(":OUTP OFF")
    print(f"\nTest complete! Total cycles triggered: {pulse_count - 1}")

    # --------------------------------------------------------------------------
    # 4. SAVE TO CSV
    # --------------------------------------------------------------------------
    print(f"Saving data to {csv_filename}...")
    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Absolute Time (s)", "Current (A)", "Voltage (V)"])
        for t, c, v in zip(master_time, master_curr, master_volt):
            writer.writerow([t, c, v])
            
    # --------------------------------------------------------------------------
    # 5. PLOT THE GRAPH
    # --------------------------------------------------------------------------
    print("Generating plot...")
    master_curr_ma = [c * 1000 for c in master_curr] # Convert to mA for plotting

    fig, ax1 = plt.subplots(figsize=(12, 6))

    color1 = 'tab:red'
    ax1.set_xlabel('Elapsed Time (seconds)', fontsize=12)
    ax1.set_ylabel('Current (mA)', color=color1, fontsize=12)
    ax1.plot(master_time, master_curr_ma, color=color1, label='Current (mA)')
    ax1.tick_params(axis='y', labelcolor=color1)
    ax1.grid(True, linestyle='--', alpha=0.6)

    ax2 = ax1.twinx()  
    color2 = 'tab:blue'
    ax2.set_ylabel('Voltage (V)', color=color2, fontsize=12)  
    ax2.plot(master_time, master_volt, color=color2, linestyle='--', alpha=0.7, label='Voltage (V)')
    ax2.tick_params(axis='y', labelcolor=color2)

    plt.title(f'Keysight B2900 Triangle Pulse Test ({test_duration_minutes} min)', fontsize=14)
    fig.tight_layout()  
    plt.show()

except pyvisa.VisaIOError as e:
    print(f"VISA Error: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
except KeyboardInterrupt:
    print("\nTest interrupted by user! Ensuring output is turned off...")
finally:
    try:
        nst.write(":OUTP OFF")
        nst.close()
        rm.close()
        print("Connection safely closed.")
    except:
        pass