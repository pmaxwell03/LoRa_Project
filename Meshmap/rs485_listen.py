#!/usr/bin/env python3
"""Listen on RS485 and print anything that arrives."""
import sys
import time
import serial

if len(sys.argv) < 2:
    print("Usage: python3 rs485_listen.py <serial_port>")
    sys.exit(1)

ser = serial.Serial(sys.argv[1], 9600, timeout=0.1)
print(f"Listening on {sys.argv[1]} at 9600 baud. Ctrl+C to stop.\n")

try:
    buf = bytearray()
    last_byte_time = 0
    while True:
        data = ser.read(256)
        if data:
            buf.extend(data)
            last_byte_time = time.time()
        elif buf and (time.time() - last_byte_time) > 0.1:
            # No bytes for 100ms — treat as end of frame
            hex_str = " ".join(f"{b:02X}" for b in buf)
            print(f"RX[{len(buf)}]: {hex_str}")
            buf.clear()
except KeyboardInterrupt:
    print("\nStopping.")
    ser.close()