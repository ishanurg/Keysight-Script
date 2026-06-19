import pyvisa
import csv
import math
import matplotlib.pyplot as plt

# ==============================================================================
# 1. TEST CONFIGURATION VARIABLES
# ==============================================================================
# Overall Duration Settings
test_duration_minutes  = 1.0    # Total time to run the test (in minutes)

# Current and Voltage Settings
base_current  = 0.005   # Base current: 5 mA
peak_current  = 0.040   # Peak current: 40 mA
voltage_limit = 10.0    # Compliance limit: 10V (safely covers 40mA * 180 ohms = 7.2V)

# Square Wave Timing Settings
time_at_base  = 2.0     # Time to stay at 5mA base (seconds)
time_at_peak  = 2.0     # Time to stay at 40mA peak (seconds)

csv_filename  = "b2900_perfect_list_square.csv" 
# ==============================================================================

# ------------------------------------------------------------------------------
# MATH: Build the Arbitrary Waveform List
# ------------------------------------------------------------------------------
# We will tell the source to move to a new step every 0.5 seconds.
# This gives us the flexibility to easily edit the base/peak times later.
source_step_time = 0.5  

ticks_base = int(time_at_base / source_step_time)  # 2.0s / 0.5s = 4 ticks
ticks_peak = int(time_at_peak / source_step_time)  # 2.0s / 0.5s = 4 ticks

total_test_seconds = test_duration_minutes * 60.0
total_source_ticks = int(total_test_seconds / source_step_time)

# Build the custom array of current values
list_values = []
tick_count = 0
while tick_count < total_source_ticks:
    # Append the low states
    for _ in range(ticks_base):
        if tick_count < total_source_ticks:
            list_values.append(base_current)
            tick_count += 1
    # Append the high states
    for _ in range(ticks_peak):
        if tick_count < total_source_ticks:
            list_values.append(peak_current)
            tick_count += 1

# Convert the Python list into a comma-separated string for the SCPI command
list_str = ",".join(map(str, list_values))

# ------------------------------------------------------------------------------
# START VISA SCRIPT
# ------------------------------------------------------------------------------
rm = pyvisa.ResourceManager()
visa_addr = 'USB0::0x2A8D::0x2404::MY65150204::INSTR'

try:
    nst = rm.open_resource(visa_addr)
    # Increase PyVISA timeout so it doesn't crash during the long WAI operation
    nst.timeout = int((total_test_seconds + 10) * 1000)  
    
    print("Connected to --> " + nst.query("*IDN?").strip())
    
    nst.write("*RST")
    nst.write("*CLS")
    
    # --------------------------------------------------------------------------
    # 2. SOURCE CONFIGURATION (Arbitrary List Sweep)
    # --------------------------------------------------------------------------
    nst.write(":SOUR:FUNC:MODE CURR")
    
    # Switch from PULS to LIST Sweep
    nst.write(":SOUR:CURR:MODE LIST")                
    
    # Lock the range so it doesn't glitch while changing currents
    range_val = max(abs(base_current), abs(peak_current))
    nst.write(f":SOUR:CURR:RANG {range_val}")
    
    # Upload our custom generated waveform to the instrument
    nst.write(f":SOUR:LIST:CURR {list_str}")
    
    # Tell the Transient timer to advance through our list every 0.5s
    nst.write(":TRIG:TRAN:SOUR TIM")
    nst.write(f":TRIG:TRAN:TIM {source_step_time}")       
    nst.write(f":TRIG:TRAN:COUN {total_source_ticks}")    
    
    # --------------------------------------------------------------------------
    # 3. MEASUREMENT CONFIGURATION
    # --------------------------------------------------------------------------
    nst.write(":SENS:FUNC \"VOLT\",\"CURR\"")
    nst.write(f":SENS:VOLT:PROT {voltage_limit}")
    
    # We want to measure smoothly, 10 times a second (every 0.1s)
    meas_step_time = 0.1
    total_measurements = int(total_test_seconds / meas_step_time)
    
    # Ensure aperture (integration time) is smaller than our measurement window
    aperture_time = meas_step_time * 0.5
    nst.write(f":SENS:VOLT:APER {aperture_time}")
    nst.write(f":SENS:CURR:APER {aperture_time}")
    
    # Set the Acquisition timer to run concurrently
    nst.write(":TRIG:ACQ:SOUR TIM")
    nst.write(f":TRIG:ACQ:TIM {meas_step_time}")
    nst.write(f":TRIG:ACQ:COUN {total_measurements}")      
    
    nst.write(":FORM:DATA ASC")
    
    # --------------------------------------------------------------------------
    # 4. EXECUTE TEST
    # --------------------------------------------------------------------------
    print(f"\nStarting {test_duration_minutes}-minute hardware-synchronized test...")
    print("Test is running. Please do not close the window...")
    
    nst.write(":OUTP ON") 
    
    # Arm both measurement and source
    nst.write(":INIT:ACQ")
    nst.write(":INIT:TRAN")
    
    # Wait for the instrument to finish the multi-minute sequence natively
    nst.write("*WAI") 
    
    nst.write(":OUTP OFF")
    print("Test complete! Fetching all data...")

    # Fetch data arrays
    master_time = nst.query_ascii_values(":FETC:ARR:TIME?")
    master_curr = nst.query_ascii_values(":FETC:ARR:CURR?")
    master_volt = nst.query_ascii_values(":FETC:ARR:VOLT?")

    # --------------------------------------------------------------------------
    # 5. SAVE TO CSV
    # --------------------------------------------------------------------------
    print(f"Saving data to {csv_filename}...")
    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Absolute Time (s)", "Current (A)", "Voltage (V)"])
        for t, c, v in zip(master_time, master_curr, master_volt):
            writer.writerow([t, c, v])
            
    # --------------------------------------------------------------------------
    # 6. PLOT THE GRAPH
    # --------------------------------------------------------------------------
    print("Generating plot...")
    master_curr_ma = [c * 1000 for c in master_curr]

    fig, ax1 = plt.subplots(figsize=(12, 6))

    color1 = 'tab:red'
    ax1.set_xlabel('Time (seconds)', fontsize=12)
    ax1.set_ylabel('Current (mA)', color=color1, fontsize=12)
    ax1.plot(master_time, master_curr_ma, color=color1, linewidth=2, label='Current (mA)')
    ax1.tick_params(axis='y', labelcolor=color1)
    
    # Visual baselines
    ax1.axhline(y=5, color='red', linestyle=':', alpha=0.5)
    ax1.axhline(y=40, color='red', linestyle=':', alpha=0.5)
    ax1.grid(True, linestyle='--', alpha=0.6)

    ax2 = ax1.twinx()  
    color2 = 'tab:blue'
    ax2.set_ylabel('Voltage (V)', color=color2, fontsize=12)  
    ax2.plot(master_time, master_volt, color=color2, linestyle='--', alpha=0.7, label='Voltage (V)')
    ax2.tick_params(axis='y', labelcolor=color2)
    
    ax2.set_ylim(0, voltage_limit + 1)

    plt.title(f'Keysight B2900 180Ω Custom Waveform (List Sweep)', fontsize=14)
    fig.tight_layout()  
    plt.show()

except pyvisa.VisaIOError as e:
    print(f"VISA Error: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
except KeyboardInterrupt:
    print("\nTest interrupted! Ensuring output is turned off...")
finally:
    try:
        nst.write(":OUTP OFF")
        nst.close()
        rm.close()
        print("Connection safely closed.")
    except:
        pass