# Buoy Network map

Collects sensor packets from Meshtastic buoys and shows them on a web map:
color-coded readings at the exact position each one was taken, drift tracks,
and an interpolated heat surface for any parameter (pH, turbidity, water temp,
temp-string depth, weather and so on).

```
buoys --LoRa mesh--> gateway radio --USB--> Raspberry Pi
                                             ├─ gateway.py  (decode + store)
                                             ├─ data.db     (SQLite, one file)
                                             └─ server.py   (map at :8000)
```

## Try it now (no hardware needed)

Nothing to install: the map and simulator only use Python's built-in parts.

**Easiest:** double-click `start.command` (Mac) or `start.bat` (Windows).
It creates demo data the first time and opens the map in your browser.
(On a Mac, the first time: right-click `start.command` and choose Open.)

**Or from a terminal, in this folder:**

```bash
python simulate.py --reset     # 14 days of fake data from 6 drifting buoys (sonde, temp string and weather on each)
python server.py               # starts the map and opens it in your browser
```

(Use `python3` on a Mac.) Leave the window open while you use the map.
Close it, or press Ctrl+C, to stop.

`python simulate.py --live` keeps adding fresh packets in real time, so you
can watch the map update.

## Install on the site Pi

1. Copy this folder to the Pi, e.g. `/home/pi/meshmap`.
2. Plug the gateway Meshtastic radio into USB.
3. Run `bash deploy/install.sh`.

That sets up two services that start on boot and restart if they crash:

| Service | What it does |
|---|---|
| `meshmap-gateway` | Listens to the radio and writes packets to `data.db` |
| `meshmap-web` | Serves the map on port 8000 |

The client then opens `http://<pi-address>:8000` in any browser, on the same
network. Useful commands:

```bash
journalctl -u meshmap-gateway -f       # watch packets arrive
sudo systemctl restart meshmap-web     # after changing settings
```

To remove the simulated data before going live: `rm data.db*`, then restart
both services.

**Settings** go in `deploy/meshmap-web.service` as `Environment=` lines:
- `MESHMAP_TITLE`: the page title.
- `MESHMAP_INTERVAL`: minutes between transmissions. Used to flag late buoys.
- `MESHMAP_PORT`: the web port.

**Buoy names** come from each node's Meshtastic "long name". Set them in the
Meshtastic app.

**Backups:** copy `data.db`. That one file holds everything. At 6 buoys, every
30 minutes, it grows by about 20 MB per month (around 150 MB for a 7-month season).

## What the client sees

- **Show:** pick any parameter. Temp string gets a depth picker.
- **Time period:** 24 h / 3 d / 7 d / 30 d / All, or a custom range.
  - **Every reading** plots every position in the period, so a drifting buoy
    paints a trail of measurements.
  - **Latest only** shows where each buoy is now.
- **Heat surface:** inverse-distance-weighted interpolation between readings.
  - Areas farther than *Heat reach* from any reading are left blank, so the map
    never invents values far from real measurements.
  - There is no shoreline mask, so the surface can spill onto land near shore.
    Lower the reach if that happens.
- **Fixed / Auto color scale:**
  - Fixed uses the ranges in `params.py`, so colors mean the same thing day to
    day.
  - Auto stretches the scale to the current data, which shows small
    differences.
- **Click a point** for everything that buoy sent in that packet, plus a trend
  line for the selected parameter.
- **Buoy list:** shows each buoy's status.
  - Green: reporting.
  - Amber: late.
  - Red: silent for more than 6 h.
  - Also shows battery voltage and packets received today vs. expected.
- **Download data (CSV):** one row per transmission, one column per
  parameter. Opens in Excel.

## Packet format (for the firmware)

Each 30-minute transmission is one packet on Meshtastic port 256
(`PRIVATE_APP`). The packet carries its own GPS position and timestamp, so
drifting buoys are mapped exactly where each reading was taken.

- The full byte layout is in `payload.py`.
- A ready-to-use C++ encoder is in `firmware/buoy_payload.h`.
- A full buoy (sonde + 8-depth temp string + weather + battery) is about 153 bytes,
  which is well inside one LoRa packet.

Edge cases:
- **No GPS fix:** set the flag to 0. The gateway uses the buoy's last known
  position.
- **No GPS time yet:** send 0. The gateway uses the time it received the
  packet.
- **Failed sensor read:** send `NAN`. The value is dropped.
- **Duplicate packets** from mesh rebroadcasts are ignored.

**Adding a sensor value:** add an ID to `params.py` and the matching enum in
`buoy_payload.h`. The map picks it up automatically. Never renumber existing
IDs.

## Files

| File | Purpose |
|---|---|
| `params.py` | Parameter list: IDs, names, units, color ranges |
| `payload.py` | Packet encode/decode |
| `db.py` | SQLite schema and storage |
| `gateway.py` | Radio → database. Use `--port /dev/ttyACM0` for a specific USB port, or `--host <ip>` for a WiFi-connected radio |
| `server.py` | JSON API and map page. No add-ons needed. `--no-browser` stops it opening a browser |
| `start.command` / `start.bat` | Double-click starters for Mac / Windows |
| `requirements.txt` | Only needed for `gateway.py` (the meshtastic library) |
| `static/` | Map page. Leaflet is bundled, so only the background tiles need internet |
| `simulate.py` | Fake drifting buoys for testing |
| `firmware/buoy_payload.h` | Encoder for the buoy firmware |
