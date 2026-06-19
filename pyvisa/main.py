import pyvisa
import time
import csv
import matplotlib.pyplot as plt

test_duration_minutes  = 1.0     # Total time to run the test (in minutes)
pulse_interval_seconds = 2.0     # Time to wait between each pulse trigger (in seconds)

# Current and Voltage Settings
base_current  = 0.0     # Base current in Amps (e.g., 0.0 A = 0 mA)
peak_current  = 0.04    # Peak current in Amps (e.g., 0.04 A = 40 mA)
voltage_limit = 5.0     # Compliance voltage limit in Volts

# Single Pulse Timing Settings
pulse_delay   = 0.01    # Delay before the pulse starts in seconds
pulse_width   = 0.05    # Duration of the peak pulse in seconds
total_time    = 0.1     # Total time to record data per pulse event in seconds

# Measurement Settings
num_points    = 500     # Number of measurement points PER PULSE (keep reasonable for long tests)
csv_filename  = "b2900_pulse_data.csv" # File to save the long-run data
# ==============================================================================

rm = pyvisa.ResourceManager()
visa_addr = 'USB0::0x2A8D::0x2404::MY65150204::INSTR'

# Master arrays to hold all data across the entire test duration
master_time = []
master_curr = []
master_volt = []

try:
    nst = rm.open_resource(visa_addr)
    nst.timeout = 10000  # 10 seconds timeout for standard operations
    
    print("Connected to --> " + nst.query("*IDN?").strip())
    
    # Reset instrument and clear errors
    nst.write("*RST")
    nst.write("*CLS")
    
    # --------------------------------------------------------------------------
    # 2. SOURCE & MEASUREMENT CONFIGURATION (Done once)
    # --------------------------------------------------------------------------
    nst.write(":SOUR:FUNC:MODE CURR")
    nst.write(":SOUR:FUNC:SHAP PULS")
    nst.write(f":SOUR:CURR {base_current}")
    nst.write(f":SOUR:CURR:TRIG {peak_current}")
    
    range_val = max(abs(base_current), abs(peak_current))
    if range_val == 0: range_val = 1e-3
    nst.write(f":SOUR:CURR:RANG {range_val}")
    
    nst.write(f":SOUR:PULS:DEL {pulse_delay}")
    nst.write(f":SOUR:PULS:WIDT {pulse_width}")
    
    nst.write(":SENS:FUNC \"VOLT\",\"CURR\"")
    nst.write(f":SENS:VOLT:PROT {voltage_limit}")
    
    step_time = total_time / num_points
    aperture_time = step_time * 0.5
    nst.write(f":SENS:VOLT:APER {aperture_time}")
    nst.write(f":SENS:CURR:APER {aperture_time}")
    
    nst.write(f":TRIG:ACQ:COUN {num_points}")
    nst.write(":TRIG:ACQ:SOUR TIM")
    nst.write(f":TRIG:ACQ:TIM {step_time}")
    nst.write(":TRIG:TRAN:COUN 1")
    nst.write(":TRIG:TRAN:SOUR AINT")
    
    nst.write(":FORM:DATA ASC")
    
    # --------------------------------------------------------------------------
    # 3. CONTINUOUS TEST LOOP
    # --------------------------------------------------------------------------
    print(f"\nStarting {test_duration_minutes}-minute test...")
    print(f"A pulse will be triggered every {pulse_interval_seconds} seconds.")
    
    nst.write(":OUTP ON") # Turn on base current
    
    test_duration_seconds = test_duration_minutes * 60.0
    start_time = time.time()
    pulse_count = 1
    
    while (time.time() - start_time) < test_duration_seconds:
        loop_start = time.time()
        elapsed_test_time = loop_start - start_time
        
        print(f"[{elapsed_test_time:.1f}s] Triggering Pulse #{pulse_count}...")
        
        # Arm and trigger the measurement and pulse
        nst.write(":INIT:ACQ")
        nst.write(":INIT:TRAN")
        nst.write("*WAI") # Wait for this specific pulse to finish
        
        # Fetch the short burst of data
        time_data = nst.query_ascii_values(":FETC:ARR:TIME?")
        curr_data = nst.query_ascii_values(":FETC:ARR:CURR?")
        volt_data = nst.query_ascii_values(":FETC:ARR:VOLT?")
        
        # The instrument returns time relative to the trigger (0 to 0.1s).
        # We need to add the elapsed test time so the graph continuously moves forward.
        absolute_time_data = [t + elapsed_test_time for t in time_data]
        
        # Append to master lists
        master_time.extend(absolute_time_data)
        master_curr.extend(curr_data)
        master_volt.extend(volt_data)
        
        # Calculate how long to sleep before the next pulse
        processing_time = time.time() - loop_start
        sleep_time = pulse_interval_seconds - processing_time
        if sleep_time > 0:
            time.sleep(sleep_time)
            
        pulse_count += 1

    # End of test
    nst.write(":OUTP OFF")
    print(f"\nTest complete! Total pulses triggered: {pulse_count - 1}")

    # --------------------------------------------------------------------------
    # 4. SAVE TO CSV (Highly recommended for long tests)
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
    master_curr_ma = [c * 1000 for c in master_curr] # Convert to mA

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

    plt.title(f'Keysight B2900 Continuous Pulse Test ({test_duration_minutes} min)', fontsize=14)
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