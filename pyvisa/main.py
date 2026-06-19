import pyvisa
import csv
import math
import matplotlib.pyplot as plt

# ==============================================================================
# 1. TEST CONFIGURATION VARIABLES (Easily Editable)
# ==============================================================================
test_duration_minutes = 1.0     # Total time to run the test (in minutes)

# Current and Voltage Settings
min_current   = 0.005   # Base (valley) current: 5 mA
max_current   = 0.040   # Peak (crest) current: 40 mA

# Compliance Limit: Set to 10V (safely covers 40mA * 180 ohms = 7.2V)
voltage_limit = 10.0    

# Sine Wave Timing Settings
cycle_period  = 4.0     # Time it takes to complete ONE full sine wave (seconds)

# RESOLUTION: 360 points per cycle ensures a perfectly round, high-def curve.
points_per_cycle = 360  

csv_filename  = "b2910cl_sine_wave_data.csv" 
# ==============================================================================

# ------------------------------------------------------------------------------
# MATH: Calculate ONE Perfect Cycle in Python
# ------------------------------------------------------------------------------
# Calculate the middle offset and the amplitude (height) of the wave
amplitude = (max_current - min_current) / 2.0
offset    = (max_current + min_current) / 2.0

# Calculate the precise timing for each micro-step
step_time = cycle_period / points_per_cycle
total_test_seconds = test_duration_minutes * 60.0

# Calculate total ticks needed to fulfill the entire multi-minute duration
total_source_ticks = int(total_test_seconds / step_time)

# Build the custom array for ONLY ONE CYCLE to save instrument buffer memory
list_values = []
for tick in range(points_per_cycle):
    t = tick * step_time
    # We use negative cosine (-cos) so the wave naturally starts exactly at the bottom (5mA)
    current_val = offset - amplitude * math.cos(2 * math.pi * (t / cycle_period))
    list_values.append(round(current_val, 6))

# Convert the Python list to a comma-separated string for the SCPI command
list_str = ",".join(map(str, list_values))

# ------------------------------------------------------------------------------
# START VISA SCRIPT
# ------------------------------------------------------------------------------
rm = pyvisa.ResourceManager()
visa_addr = 'USB0::0x2A8D::0x2404::MY65150204::INSTR'

try:
    nst = rm.open_resource(visa_addr)
    # Give PyVISA a long timeout so it waits patiently for the whole test to finish
    nst.timeout = int((total_test_seconds + 10) * 1000)  
    
    print("Connected to --> " + nst.query("*IDN?").strip())
    
    # Reset instrument and clear the error queue
    nst.write("*RST")
    nst.write("*CLS")
    
    # --------------------------------------------------------------------------
    # 2. SOURCE CONFIGURATION
    # --------------------------------------------------------------------------
    nst.write(":SOUR:FUNC:MODE CURR")
    
    # Enable LIST Sweep Mode (The B2910CL's equivalent to an Arbitrary mode)
    nst.write(":SOUR:CURR:MODE LIST")                
    
    # Lock the range so the instrument's internal relays don't click and glitch the wave
    range_val = max(abs(min_current), abs(max_current))
    nst.write(f":SOUR:CURR:RANG {range_val}")
    
    # Upload our mathematically perfect sine wave to the instrument's memory
    nst.write(f":SOUR:LIST:CURR {list_str}")
    
    # Tell the hardware timer to advance through our list automatically
    nst.write(":TRIG:TRAN:SOUR TIM")
    nst.write(f":TRIG:TRAN:TIM {step_time}") 
      
    # By setting the trigger count higher than the 360-point list length, 
    # the hardware natively loops our sine wave back to the beginning automatically!
    nst.write(f":TRIG:TRAN:COUN {total_source_ticks}")    
    
    # --------------------------------------------------------------------------
    # 3. MEASUREMENT CONFIGURATION
    # --------------------------------------------------------------------------
    nst.write(":SENS:FUNC \"VOLT\",\"CURR\"")
    nst.write(f":SENS:VOLT:PROT {voltage_limit}")
    
    # Sync measurement perfectly 1:1 with the source steps to capture the curve flawlessly
    aperture_time = step_time * 0.5
    nst.write(f":SENS:VOLT:APER {aperture_time}")
    nst.write(f":SENS:CURR:APER {aperture_time}")
    
    nst.write(":TRIG:ACQ:SOUR TIM")
    nst.write(f":TRIG:ACQ:TIM {step_time}")
    nst.write(f":TRIG:ACQ:COUN {total_source_ticks}")      
    
    nst.write(":FORM:DATA ASC")
    
    # --------------------------------------------------------------------------
    # 4. EXECUTE TEST
    # --------------------------------------------------------------------------
    print(f"\nStarting {test_duration_minutes}-minute Sine Wave test...")
    print("Test is running smoothly on the B2910CL hardware. Please do not close the window...")
    
    nst.write(":OUTP ON") 
    
    # Arm both the measurement buffer and the source generator
    nst.write(":INIT:ACQ")
    nst.write(":INIT:TRAN")
    
    # *WAI pauses the Python script until the instrument's internal clock finishes the whole test
    nst.write("*WAI") 
    
    nst.write(":OUTP OFF")
    print("Test complete! Fetching all data...")

    # Pull the massive array of data off the instrument
    master_time = nst.query_ascii_values(":FETC:ARR:TIME?")
    master_curr = nst.query_ascii_values(":FETC:ARR:CURR?")
    master_volt = nst.query_ascii_values(":FETC:ARR:VOLT?")

    # --------------------------------------------------------------------------
    # 5. SAVE TO CSV
    # --------------------------------------------------------------------------
    print(f"Saving {len(master_time)} data points to {csv_filename}...")
    with open(csv_filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Absolute Time (s)", "Current (A)", "Voltage (V)"])
        for t, c, v in zip(master_time, master_curr, master_volt):
            writer.writerow([t, c, v])
            
    # --------------------------------------------------------------------------
    # 6. PLOT THE GRAPH
    # --------------------------------------------------------------------------
    print("Generating plot...")
    master_curr_ma = [c * 1000 for c in master_curr] # Convert Amps to mA for a clean graph

    fig, ax1 = plt.subplots(figsize=(12, 6))

    color1 = 'tab:red'
    ax1.set_xlabel('Time (seconds)', fontsize=12)
    ax1.set_ylabel('Current (mA)', color=color1, fontsize=12)
    ax1.plot(master_time, master_curr_ma, color=color1, linewidth=2, label='Current (mA)')
    ax1.tick_params(axis='y', labelcolor=color1)
    
    # Add visual baselines to confirm it hits 5mA and 40mA perfectly
    ax1.axhline(y=min_current * 1000, color='red', linestyle=':', alpha=0.5)
    ax1.axhline(y=max_current * 1000, color='red', linestyle=':', alpha=0.5)
    ax1.grid(True, linestyle='--', alpha=0.6)

    ax2 = ax1.twinx()  
    color2 = 'tab:blue'
    ax2.set_ylabel('Voltage (V)', color=color2, fontsize=12)  
    ax2.plot(master_time, master_volt, color=color2, linestyle='--', alpha=0.7, label='Voltage (V)')
    ax2.tick_params(axis='y', labelcolor=color2)
    
    ax2.set_ylim(0, voltage_limit + 1)

    plt.title(f'Keysight B2910CL Perfect Sine Wave (180Ω Load)', fontsize=14)
    fig.tight_layout()  
    plt.show()

except pyvisa.VisaIOError as e:
    print(f"VISA Error: {e}")
except Exception as e:
    print(f"An error occurred: {e}")
except KeyboardInterrupt:
    print("\nTest interrupted! Ensuring output is turned off...")
finally:
    # Failsafe to always turn off the current if something goes wrong
    try:
        nst.write(":OUTP OFF")
        nst.close()
        rm.close()
        print("Connection safely closed.")
    except:
        pass