import pyvisa

# 1. Initialize the VISA Resource Manager
rm = pyvisa.ResourceManager()

print("Available Visa address is " + str(rm.list_resources()))


# 2. Open a connection to your DAQ970A
# Replace 'YOUR_VISA_ADDRESS' with the exact address from Keysight Connection Expert
# Example: USB0::0x2A8D::0x8601::MYXXXXXXXX::0::INSTR or TCPIP0::192.168.1.10::inst0::INSTR
# daq = rm.open_resource('')

# # Set timeout for long scans (in milliseconds)
# daq.timeout = 10000 

# try:
#     # 3. Reset the instrument
#     daq.write('*RST')
    
#     # 4. Configure channels for measurement: 
#     # Measure DC Volts on channel 101, with 10V range and 0.1 PLC resolution
#     daq.write('CONF:VOLT:DC 10, 0.1, (@101)')
    
#     # Measure Temperature (Thermocouple) on channel 102
#     daq.write('CONF:TEMP TCO, K, (@102)')
    
#     # 5. Define the scan list
#     daq.write('ROUTE:SCAN (@101,102)')
    
#     # 6. Initialize the scan and read data
#     daq.write('INIT')
    
#     # Wait and fetch the data (Fetches readings from memory to the output buffer)
#     readings = daq.query('FETCh?')
    
#     print("Scan Readings: ")
#     print(readings)

# finally:
#     # 7. Close the VISA session
#     daq.close()
#     rm.close()
