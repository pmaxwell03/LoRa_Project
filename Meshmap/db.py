"""SQLite storage. One file, no server, easy to back up (just copy data.db)."""
import os
import sqlite3
import time

DB_PATH = os.environ.get("MESHMAP_DB", os.path.join(os.path.dirname(__file__), "data.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    node_id    TEXT PRIMARY KEY,      -- Meshtastic id, e.g. !a1b2c3d4
    name       TEXT,                  -- friendly name shown on the map
    lat        REAL,
    lon        REAL,
    last_seen  INTEGER,
    snr        REAL,
    rssi       INTEGER
);
CREATE TABLE IF NOT EXISTS readings (
    id       INTEGER PRIMARY KEY,
    node_id  TEXT NOT NULL,
    ts       INTEGER NOT NULL,        -- unix seconds UTC (sample time)
    rx_ts    INTEGER NOT NULL,        -- when the gateway received it
    lat      REAL,
    lon      REAL,
    param    TEXT NOT NULL,           -- key from params.py
    depth_m  REAL,                    -- NULL for surface/air sensors
    value    REAL NOT NULL
);
-- drops duplicate copies of the same packet (mesh re-broadcasts, retries)
CREATE UNIQUE INDEX IF NOT EXISTS ux_read_dedup
    ON readings(node_id, ts, param, COALESCE(depth_m, -1));
CREATE INDEX IF NOT EXISTS ix_read_param_ts ON readings(param, ts);
CREATE INDEX IF NOT EXISTS ix_read_node_ts  ON readings(node_id, ts);
"""


def connect(path=DB_PATH):
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")   # reader (web) + writer (gateway) at once
    con.execute("PRAGMA synchronous=NORMAL")
    con.executescript(SCHEMA)
    return con


def store_packet(con, node_id, pkt, name=None, snr=None, rssi=None, rx_ts=None):
    """pkt is the dict returned by payload.decode()."""
    rx_ts = int(rx_ts or time.time())
    lat, lon = (pkt["lat"], pkt["lon"]) if pkt["gps_ok"] else (None, None)
    with con:
        if lat is None:  # no fix: fall back to the node's last known position
            row = con.execute("SELECT lat, lon FROM nodes WHERE node_id=?", (node_id,)).fetchone()
            if row:
                lat, lon = row["lat"], row["lon"]
        con.execute(
            """INSERT INTO nodes(node_id, name, lat, lon, last_seen, snr, rssi)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(node_id) DO UPDATE SET
                 name=COALESCE(excluded.name, nodes.name),
                 lat=COALESCE(excluded.lat, nodes.lat),
                 lon=COALESCE(excluded.lon, nodes.lon),
                 last_seen=MAX(excluded.last_seen, COALESCE(nodes.last_seen,0)),
                 snr=excluded.snr, rssi=excluded.rssi""",
            (node_id, name, lat, lon, rx_ts, snr, rssi))
        con.executemany(
            """INSERT OR IGNORE INTO readings(node_id, ts, rx_ts, lat, lon, param, depth_m, value)
               VALUES (?,?,?,?,?,?,?,?)""",
            [(node_id, pkt["ts"], rx_ts, lat, lon, k, d, v) for k, d, v in pkt["readings"]])
