#!/bin/bash
# Double-click to start the buoy map (Mac). Opens it in your browser.
cd "$(dirname "$0")"
[ -f data.db ] || python3 simulate.py
python3 server.py
