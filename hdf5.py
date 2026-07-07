import h5py

# Note the raw 'r' string and the updated 'OneDrive' desktop structure
path = r'C:\Users\ishan\OneDrive\Desktop\Mems-Sensor-Testing\test.h5'

with h5py.File(path, 'r') as file:
    print("Successfully opened! Keys:", list(file.keys()))
