"""
Fake sensor data so the map can be built and demoed before hardware exists.

Every simulated reading goes through payload.encode() -> payload.decode()
-> db.store_packet(), i.e. exactly the path real packets take.

    python simulate.py                 # 14 days of history, 30-min interval
    python simulate.py --days 60 --interval 15
    python simulate.py --live          # also keep adding a packet per node in real time
    python simulate.py --reset         # wipe the database first

Edit STATIONS to put the fake nodes somewhere near your client's site.
"""
import argparse
import math
import os
import random
import time

import db
import payload
from params import BY_KEY

# node_id, name, start lat, start lon, kind, drift_km
#   kind: "buoy" = sonde + temp string + weather station
#         "weather" = weather station only (e.g. a shore mast, if you add one)
#   drift_km: how far the buoy wanders from its start point (0 = fixed)
STATIONS = [
    ("!sim00001", "Buoy 1 - Bay",        44.4790, -73.2520, "buoy", 0.8),
    ("!sim00002", "Buoy 2 - Breakwater", 44.4640, -73.2420, "buoy", 0.3),
    ("!sim00003", "Buoy 3 - North",      44.5150, -73.2860, "buoy", 1.5),
    ("!sim00004", "Buoy 4 - Mid lake",   44.4700, -73.2950, "buoy", 1.5),
    ("!sim00005", "Buoy 5 - South",      44.4330, -73.2780, "buoy", 1.2),
    ("!sim00006", "Buoy 6 - Inlet",      44.5000, -73.2580, "buoy", 0.5),
]
STRING_DEPTHS = [0.5, 1, 2, 3, 4, 6, 8, 10]
INLET = (44.5000, -73.2530)   # turbid, warmer, lower-pH inflow near this point

P = {k: v["id"] for k, v in BY_KEY.items()}


def dist_km(a, b):
    return math.hypot((a[0] - b[0]) * 111, (a[1] - b[1]) * 111 * math.cos(math.radians(a[0])))


def position(st, t):
    """Smooth, repeatable wander around the start point (wind + current)."""
    node_id, _, lat0, lon0, _, drift = st
    if not drift:
        return lat0, lon0
    ph = int(node_id[-3:]) * 1.37
    d = t / 86400 * 2 * math.pi
    dx = drift * (0.6 * math.sin(d / 3.1 + ph) + 0.4 * math.sin(d / 0.9 + 2 * ph))
    dy = drift * (0.6 * math.cos(d / 4.3 + 1.7 * ph) + 0.4 * math.sin(d / 1.3 + ph))
    return lat0 + dy / 111, lon0 + dx / (111 * math.cos(math.radians(lat0)))


def sample(kind, lat, lon, t, rng):
    doy = time.gmtime(t).tm_yday
    hour = (t % 86400) / 3600 - 5            # rough local solar time
    diurnal = math.sin((hour - 9) / 24 * 2 * math.pi)
    season = 14 - 10 * (doy - 270) / 90      # cooling through autumn
    storm = max(0, math.sin(t / 86400 / 4.3 * 2 * math.pi)) ** 6   # a storm every ~4 days
    near = math.exp(-dist_km((lat, lon), INLET) / 1.5)            # 1 at inlet, ->0 away
    r = []
    if kind == "buoy":
        surf = season + 1.2 * diurnal + 2.5 * near + rng.gauss(0, 0.15)
        r += [
            (P["water_temp"], None, surf),
            (P["ph"], None, 7.9 - 0.7 * near + 0.15 * diurnal - 0.2 * storm + rng.gauss(0, 0.03)),
            (P["turbidity"], None, max(0.1, 2 + 25 * near + 30 * storm * (0.4 + near) + rng.gauss(0, 0.5))),
            (P["do_mgl"], None, 14.6 - 0.38 * surf + 0.6 * diurnal - 1.0 * near + rng.gauss(0, 0.1)),
            (P["conductivity"], None, 300 + 220 * near + rng.gauss(0, 4)),
            (P["chlorophyll"], None, max(0, 6 + 10 * near + 4 * diurnal + rng.gauss(0, 0.6))),
        ]
        thermo = 5 + 1.5 * math.sin(t / 86400 / 9)    # wandering thermocline depth
        for d in STRING_DEPTHS:
            cold = 6.0 + 0.3 * near
            frac = 1 / (1 + math.exp((d - thermo) / 0.8))
            r.append((P["string_temp"], d, cold + (surf - cold) * frac + rng.gauss(0, 0.05)))
    # every node carries a weather station; open water is a bit windier and
    # air near the warm inlet a bit warmer, so the weather maps show some pattern
    r += [
        (P["air_temp"], None, season - 2 + 5 * diurnal + 0.8 * near + rng.gauss(0, 0.3)),
        (P["humidity"], None, min(100, 70 - 15 * diurnal + 25 * storm + rng.gauss(0, 2))),
        (P["pressure"], None, 1015 - 18 * storm + rng.gauss(0, 0.4)),
        (P["wind_speed"], None, max(0, 3 + 1.5 * (1 - near) + 9 * storm + rng.gauss(0, 0.8))),
        (P["wind_dir"], None, (220 + 60 * storm + rng.gauss(0, 15)) % 360),
        (P["rain"], None, max(0, 6 * storm + rng.gauss(0, 0.3)) if storm > 0.3 else 0.0),
        (P["solar"], None, max(0, 600 * diurnal * (1 - storm)) if diurnal > 0 else 0.0),
    ]
    batt = 3.85 + 0.2 * max(diurnal, 0) - 0.15 * storm + rng.gauss(0, 0.01)
    r += [(P["battery_v"], None, batt), (P["solar_v"], None, max(0, 6.2 * diurnal) if diurnal > 0 else 0.0)]
    return r


def send(con, st, t, rng):
    node_id, name, _, _, kind, _ = st
    lat, lon = position(st, t)
    jitter = lambda: rng.gauss(0, 0.00003)    # ~3 m GPS noise
    gps_ok = rng.random() > 0.03              # occasional lost fix
    buf = payload.encode(t, lat + jitter(), lon + jitter(), sample(kind, lat, lon, t, rng), gps_ok)
    assert len(buf) <= 233, "payload too big for one LoRa packet"
    db.store_packet(con, node_id, payload.decode(buf), name=name,
                    snr=rng.uniform(-8, 9), rssi=rng.randint(-120, -70), rx_ts=t)
    return len(buf)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=float, default=14)
    ap.add_argument("--interval", type=int, default=30, help="minutes between samples")
    ap.add_argument("--live", action="store_true")
    ap.add_argument("--reset", action="store_true")
    a = ap.parse_args()
    if a.reset and os.path.exists(db.DB_PATH):
        for ext in ("", "-wal", "-shm"):
            if os.path.exists(db.DB_PATH + ext):
                os.remove(db.DB_PATH + ext)
    con = db.connect()
    rng = random.Random(42)
    step = a.interval * 60
    now = int(time.time()) // step * step
    t, n, size = now - int(a.days * 86400), 0, 0
    while t <= now:
        for st in STATIONS:
            if rng.random() < 0.04:           # ~4 % of packets lost on the mesh
                continue
            size = max(size, send(con, st, t, rng))
            n += 1
        t += step
    print(f"stored {n} packets ({len(STATIONS)} nodes, largest payload {size} bytes) -> {db.DB_PATH}")
    while a.live:
        time.sleep(step if step < 120 else 60)
        for st in STATIONS:
            send(con, st, int(time.time()), rng)
        print("live packet batch stored", time.strftime("%H:%M:%S"))


if __name__ == "__main__":
    main()
