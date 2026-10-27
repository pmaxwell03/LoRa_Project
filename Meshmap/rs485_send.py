#!/usr/bin/env python3
"""
Simple RS485 send tool.
Sends a known test pattern every 2 seconds so the RAK5802 should see it
arrive on its UART RX, and the Meshtastic firmware should print it.

Usage:
    python3 rs485_send.py /dev/cu.usbserial-1120
"""

import sys
import time
import serial

if len(sys.argv) < 2:
    print("Usage: python3 rs485_send.py <serial_port>")
    sys.exit(1)

PORT = sys.argv[1]
BAUD = 9600

# Simple recognizable pattern — different from the sonde's expected traffic
# so it's unambiguous in the firmware log.
TX_FRAME = bytes([0xDE, 0xAD, 0xBE, 0xEF, 0x00])

print(f"Opening {PORT} at {BAUD} baud...")
ser = serial.Serial(PORT, BAUD, timeout=1)
print("Open. Sending DE AD BE EF <counter> every 2 seconds. Ctrl+C to stop.")
print()

counter = 0
try:
    while True:
        counter = (counter + 1) & 0xFF
        frame = TX_FRAME[:4] + bytes([counter])
        tx_hex = " ".join(f"{b:02X}" for b in frame)
        print(f"TX #{counter}: {tx_hex}")
        ser.write(frame)
        ser.flush()
        time.sleep(2.0)
except KeyboardInterrupt:
    print("\nStopping.")
    ser.close()