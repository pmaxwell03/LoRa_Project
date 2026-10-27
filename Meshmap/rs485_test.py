#!/usr/bin/env python3
"""
Simple RS485 test tool.
Sends a Modbus "read holding registers" request every 2 seconds
and prints anything that comes back.

Usage:
    python3 rs485_test.py /dev/cu.usbserial-XXXXX
"""

import sys
import time
import serial

if len(sys.argv) < 2:
    print("Usage: python3 rs485_test.py <serial_port>")
    print("Example: python3 rs485_test.py /dev/cu.usbserial-A50285BI")
    sys.exit(1)

PORT = sys.argv[1]
BAUD = 9600

# Modbus "read 10 holding registers from address 0x2600 at slave 0x01"
# This is the exact frame our Meshtastic firmware sends to the Y4000.
TX_FRAME = bytes([0x01, 0x03, 0x26, 0x00, 0x00, 0x0A, 0xCE, 0x85])

print(f"Opening {PORT} at {BAUD} baud...")
ser = serial.Serial(PORT, BAUD, timeout=1)
print("Open. Sending request every 2 seconds. Ctrl+C to stop.")
print()

try:
    while True:
        # Clear anything stale
        ser.reset_input_buffer()

        # Send the request
        tx_hex = " ".join(f"{b:02X}" for b in TX_FRAME)
        print(f"TX: {tx_hex}")
        ser.write(TX_FRAME)
        ser.flush()

        # Wait up to 1 second for a response
        time.sleep(1.0)
        rx = ser.read(256)

        if rx:
            rx_hex = " ".join(f"{b:02X}" for b in rx)
            print(f"RX: {rx_hex}  ({len(rx)} bytes)")
        else:
            print("RX: (nothing)")

        print()
        time.sleep(1.0)

except KeyboardInterrupt:
    print("\nStopping.")
    ser.close()