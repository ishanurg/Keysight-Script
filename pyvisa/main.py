import pyvisa
import time
import csv
import matplotlib.pyplot as plt

# ==============================================================================
# 1. TEST CONFIGURATION VARIABLES
# ==============================================================================
# Overall Duration Settings
test_duration_minutes  = 1.0     # Total time to run the test (in minutes)

# Current and Voltage Settings
base_current  = 0.005   # Base current: 5 mA
peak_current  = 0.040   # Peak current: 40 mA

# COMPLIANCE VOLTAGE: 
# 40mA * 180 ohms = 7.2V required. Setting limit to 10.0V for overhead safety.
voltage_limit = 10.0    

# Square Wave Timing Settings
time_at_base  = 2.0     # Time to stay at 5mA base (seconds)
time_at_peak  = 2.0     # Time to stay at 40mA peak (seconds)
total_cycle_time = time_at_base + time_at_peak  # Total = 4.0 seconds per cycle

# Measurement Settings
points_per_cycle = 400  # Number of measurement points per 4-second cycle
csv_filename  = "b2900_180ohm_square_wave.csv" 
# ==============================================================================

rm = pyvisa.ResourceManager()
visa_addr = 'USB0::0x2A8D::0x2404::MY65150204::INSTR'

# Master arrays to hold all data across the entire test
master_time = []
master_curr = []
master_volt = []

try:
    nst = rm.open_resource(visa_addr)
    nst.timeout = 15000  # 15 second timeout to safely handle 4s+ pulses
    
    print("Connected to --> " + nst.query("*IDN?").strip())
    
    # Reset instrument and clear errors
    nst.write("*RST")
    nst.write("*CLS")
    
    # --------------------------------------------------------------------------
    # 2. SOURCE CONFIGURATION (Square Wave Setup)
    # --------------------------------------------------------------------------
    nst.write(":SOUR:FUNC:MODE CURR")                # Sourcing Current
    nst.write(":SOUR:FUNC:SHAP PULS")                # Pulse shape for square wave
    
    nst.write(f":SOUR:CURR {base_current}")          # Low state (5mA)
    nst.write(f":SOUR:CURR:TRIG {peak_current}")     # High state (40mA)
    
    # Lock the range to maximum current to prevent auto-ranging delays
    range_val = max(abs(base_current), abs(peak_current))
    nst.write(f":SOUR:CURR:RANG {range_val}")
    
    # Timing configuration
    nst.write(f":SOUR:PULS:DEL {time_at_base}")      # Wait at base for 2s
    nst.write(f":SOUR:PULS:WIDT {time_at_peak}")     # Stay at peak for 2s
    
    # --------------------------------------------------------------------------
    # 3. MEASUREMENT CONFIGURATION
    # --------------------------------------------------------------------------
    nst.write(":SENS:FUNC \"VOLT\",\"CURR\"")        # Measure both Voltage & Current
    nst.write(f":SENS:VOLT:PROT {voltage_limit}")    # Set 10.0V Compliance limit
    
    # Calculate step time (how frequently a measurement point is taken)
    step_time = total_cycle_time / points_per_cycle
    aperture_time = step_time * 0.5                  # 50% integration time
    
    nst.write(f":SENS:VOLT:APER {aperture_time}")
    nst.write(f":SENS:CURR:APER {aperture_time}")
    
    # Timer syncs measurements evenly across the 4.0 second cycle
    nst.write(f":TRIG:ACQ:COUN {points_per_cycle}")
    nst.write(":TRIG:ACQ:SOUR TIM")
    nst.write(f":TRIG:ACQ:TIM {step_time}")
    
    nst.write(":TRIG:TRAN:COUN 1")                   # 1 source output sequence per trigger
    nst.write(":TRIG:TRAN:SOUR AINT")
    
    nst.write(":FORM:DATA ASC")
    
    # --------------------------------------------------------------------------
    # 4. CONTINUOUS TEST LOOP
    # --------------------------------------------------------------------------
    print(f"\nStarting test. Load = 180 ohms, Compliance = {voltage_limit} V")
    print(f"Cycle: {time_at_base}s at {base_current*1000}mA, then {time_at_peak}s at {peak_current*1000}mA.")
    
    nst.write(":OUTP ON") # Turns on the holding base current
    
    test_duration_seconds = test_duration_minutes * 60.0
    start_time = time.time()
    cycle_count = 1
    
    while (time.time() - start_time) < test_duration_seconds:
        loop_start = time.time()
        elapsed_test_time = loop_start - start_time
        
        print(f"[{elapsed_test_time:.1f}s] Triggering Square Wave Cycle #{cycle_count}...")
        
        # Arm measurement and source, then wait for the 4-second sequence to finish
        nst.write(":INIT:ACQ")
        nst.write(":INIT:TRAN")
        nst.write("*WAI") 
        
        # Fetch the burst of data
        time_data = nst.query_ascii_values(":FETC:ARR:TIME?")
        curr_data = nst.query_ascii_values(":FETC:ARR:CURR?")
        volt_data = nst.query_ascii_values(":FETC:ARR:VOLT?")
        
        # Convert instrument's relative loop time to continuous absolute time
        absolute_time_data = [t + elapsed_test_time for t in time_data]
        
        # Append to master lists
        master_time.extend(absolute_time_data)
        master_curr.extend(curr_data)
        master_volt.extend(volt_data)
        
        cycle_count += 1

    # End of test
    nst.write(":OUTP OFF")
    print(f"\nTest complete! Total cycles triggered: {cycle_count - 1}")

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
    master_curr_ma = [c * 1000 for c in master_curr] # Convert to mA for plotting

    fig, ax1 = plt.subplots(figsize=(12, 6))

    color1 = 'tab:red'
    ax1.set_xlabel('Elapsed Time (seconds)', fontsize=12)
    ax1.set_ylabel('Current (mA)', color=color1, fontsize=12)
    ax1.plot(master_time, master_curr_ma, color=color1, linewidth=2, label='Current (mA)')
    ax1.tick_params(axis='y', labelcolor=color1)
    
    # Add a horizontal line showing where the expected current limits are
    ax1.axhline(y=5, color='red', linestyle=':', alpha=0.5)
    ax1.axhline(y=40, color='red', linestyle=':', alpha=0.5)
    ax1.grid(True, linestyle='--', alpha=0.6)

    ax2 = ax1.twinx()  
    color2 = 'tab:blue'
    ax2.set_ylabel('Voltage (V)', color=color2, fontsize=12)  
    ax2.plot(master_time, master_volt, color=color2, linestyle='--', alpha=0.7, label='Voltage (V)')
    ax2.tick_params(axis='y', labelcolor=color2)
    
    # Set voltage axis limit slightly above compliance to see the headroom
    ax2.set_ylim(0, voltage_limit + 1)

    plt.title(f'Keysight B2900 Square Wave on 180Ω Load', fontsize=14)
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