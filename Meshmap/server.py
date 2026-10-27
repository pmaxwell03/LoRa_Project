"""
Web server: JSON API + the map page (static/).

Uses only Python's built-in libraries -- nothing to install.

    python server.py                 # opens http://localhost:8000 in your browser
    python server.py --no-browser    # don't open a browser (used on the Pi)

Settings (environment variables, all optional):
    MESHMAP_DB         path to the SQLite file        (default: ./data.db)
    MESHMAP_TITLE      title shown on the map page    (default: "Buoy Network")
    MESHMAP_INTERVAL   expected minutes between packets per node (default: 30)
                       -- used to flag buoys that have gone quiet
    MESHMAP_PORT       web port                       (default: 8000)
"""
import csv
import io
import json
import mimetypes
import os
import sqlite3
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import db
from params import BY_KEY, PARAMS

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")
TITLE = os.environ.get("MESHMAP_TITLE", "Buoy Network")
INTERVAL_MIN = int(os.environ.get("MESHMAP_INTERVAL", "30"))
PORT = int(os.environ.get("MESHMAP_PORT", "8000"))

# Windows sometimes maps these wrongly in the registry, which stops the page loading
for ext, typ in ((".js", "application/javascript"), (".css", "text/css"), (".html", "text/html"),
                 (".png", "image/png"), (".svg", "image/svg+xml")):
    mimetypes.add_type(typ, ext)


class HTTPError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code, self.msg = code, msg


def con():
    c = sqlite3.connect(db.DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    return c


def window(q):
    start, end = q.get("start"), q.get("end")
    return (int(start) if start else 0), (int(end) if end else int(time.time()) + 86400)


def depth_sql(q):
    """SQL fragment + args selecting one depth (or surface sensors when no depth given)."""
    d = q.get("depth")
    if not d:
        return "depth_m IS NULL", []
    return "ABS(depth_m - ?) < 0.01", [float(d)]


def need(q, name):
    if not q.get(name):
        raise HTTPError(400, f"missing '{name}'")
    return q[name]


def check_param(q):
    p = need(q, "param")
    if p not in BY_KEY:
        raise HTTPError(404, f"unknown parameter '{p}'")
    return p


# ---------------------------------------------------------------------------
# API endpoints: each takes the query dict and returns JSON-able data
_params_cache = {"t": 0, "data": None}


def api_config(q):
    return {"title": TITLE, "interval_min": INTERVAL_MIN}


def api_params(q):
    """Every known parameter, with the depths that actually have data."""
    if time.time() - _params_cache["t"] > 120:
        with con() as c:
            rows = c.execute("SELECT param, depth_m FROM readings GROUP BY param, depth_m").fetchall()
        have = {}
        for r in rows:
            have.setdefault(r["param"], []).append(r["depth_m"])
        out = []
        for pid in sorted(PARAMS):
            p = dict(BY_KEY[PARAMS[pid][0]])
            depths = have.get(p["key"])
            p["has_data"] = depths is not None
            p["depths"] = sorted(d for d in (depths or []) if d is not None)
            p["surface"] = depths is not None and None in depths
            out.append(p)
        _params_cache.update(t=time.time(), data=out)
    return _params_cache["data"]


def api_nodes(q):
    day_ago = int(time.time()) - 86400
    with con() as c:
        rows = c.execute("""
            SELECT n.*,
              (SELECT MAX(ts) FROM readings r WHERE r.node_id = n.node_id) AS last_ts,
              (SELECT value FROM readings r WHERE r.node_id = n.node_id AND param = 'battery_v'
                 ORDER BY ts DESC LIMIT 1) AS battery_v,
              (SELECT COUNT(DISTINCT ts) FROM readings r WHERE r.node_id = n.node_id
                 AND ts >= ?) AS pkts_24h
            FROM nodes n ORDER BY COALESCE(n.name, n.node_id)""", (day_ago,)).fetchall()
    return [dict(r) for r in rows]


def api_points(q):
    """Readings of one parameter with their positions. latest=true -> newest per buoy."""
    param = check_param(q)
    t0, t1 = window(q)
    dsql, dargs = depth_sql(q)
    base = f"param = ? AND {dsql} AND ts BETWEEN ? AND ? AND lat IS NOT NULL"
    args = [param, *dargs, t0, t1]
    with con() as c:
        if q.get("latest") in ("true", "1"):
            sql = f"""SELECT r.node_id, r.ts, r.lat, r.lon, r.value FROM readings r
                      JOIN (SELECT node_id, MAX(ts) mt FROM readings WHERE {base} GROUP BY node_id) m
                        ON r.node_id = m.node_id AND r.ts = m.mt
                      WHERE r.param = ? AND {dsql.replace('depth_m', 'r.depth_m')}"""
            rows = c.execute(sql, args + [param, *dargs]).fetchall()
        else:
            rows = c.execute(f"SELECT node_id, ts, lat, lon, value FROM readings WHERE {base} ORDER BY ts",
                             args).fetchall()
    return [[r["node_id"], r["ts"], round(r["lat"], 6), round(r["lon"], 6), round(r["value"], 4)] for r in rows]


def api_tracks(q):
    """Drift path of each buoy: one position per packet."""
    t0, t1 = window(q)
    with con() as c:
        rows = c.execute("""SELECT node_id, ts, MIN(lat) lat, MIN(lon) lon FROM readings
                            WHERE ts BETWEEN ? AND ? AND lat IS NOT NULL
                            GROUP BY node_id, ts ORDER BY node_id, ts""", (t0, t1)).fetchall()
    out = {}
    for r in rows:
        out.setdefault(r["node_id"], []).append([r["ts"], round(r["lat"], 6), round(r["lon"], 6)])
    return out


def api_packet(q):
    """Everything one buoy sent in one transmission."""
    node_id, ts = need(q, "node_id"), int(need(q, "ts"))
    with con() as c:
        rows = c.execute("""SELECT param, depth_m, value, lat, lon FROM readings
                            WHERE node_id = ? AND ts = ? ORDER BY param, depth_m""", (node_id, ts)).fetchall()
    if not rows:
        raise HTTPError(404, "no such packet")
    return {"node_id": node_id, "ts": ts, "lat": rows[0]["lat"], "lon": rows[0]["lon"],
            "values": [[r["param"], r["depth_m"], r["value"]] for r in rows]}


def api_series(q):
    node_id, param = need(q, "node_id"), check_param(q)
    t0, t1 = window(q)
    dsql, dargs = depth_sql(q)
    with con() as c:
        rows = c.execute(f"""SELECT ts, value FROM readings WHERE node_id = ? AND param = ?
                             AND {dsql} AND ts BETWEEN ? AND ? ORDER BY ts""",
                         [node_id, param, *dargs, t0, t1]).fetchall()
    return [[r["ts"], round(r["value"], 4)] for r in rows]


def export_csv(q):
    """One row per transmission, one column per parameter/depth. Opens in Excel."""
    t0, t1 = window(q)
    with con() as c:
        names = {r["node_id"]: r["name"] for r in c.execute("SELECT node_id, name FROM nodes")}
        rows = c.execute("""SELECT node_id, ts, lat, lon, param, depth_m, value FROM readings
                            WHERE ts BETWEEN ? AND ? ORDER BY ts, node_id""", (t0, t1)).fetchall()
    order = {PARAMS[i][0]: i for i in PARAMS}
    cols, packets = {}, {}
    for r in rows:
        p = BY_KEY.get(r["param"])
        if p is None:
            continue
        unit = f" ({p['unit']})" if p["unit"] else ""
        col = p["label"] + (f" @ {r['depth_m']:g} m" if r["depth_m"] is not None else "") + unit
        cols[col] = (order[r["param"]], r["depth_m"] if r["depth_m"] is not None else -1)
        pk = packets.setdefault((r["ts"], r["node_id"]), {"lat": r["lat"], "lon": r["lon"]})
        pk[col] = r["value"]
    colnames = sorted(cols, key=cols.get)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["time_utc", "node_id", "name", "latitude", "longitude", *colnames])
    for (ts, nid), pk in packets.items():
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(ts)), nid, names.get(nid) or "",
                    pk["lat"], pk["lon"], *[("" if pk.get(cn) is None else round(pk[cn], 4)) for cn in colnames]])
    return buf.getvalue()


ROUTES = {
    "/api/config": api_config, "/api/params": api_params, "/api/nodes": api_nodes,
    "/api/points": api_points, "/api/tracks": api_tracks, "/api/packet": api_packet,
    "/api/series": api_series,
}


# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):   # keep the terminal quiet
        pass

    def send(self, code, body, ctype, extra=None):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ROUTES:
                self.send(200, json.dumps(ROUTES[url.path](q)), "application/json")
            elif url.path == "/api/export.csv":
                fname = f"buoy-data-{time.strftime('%Y%m%d')}.csv"
                self.send(200, export_csv(q), "text/csv; charset=utf-8",
                          {"Content-Disposition": f'attachment; filename="{fname}"'})
            elif url.path in ("/", "/index.html"):
                self.static("index.html")
            elif url.path.startswith("/static/"):
                self.static(url.path[len("/static/"):])
            else:
                raise HTTPError(404, "not found")
        except HTTPError as e:
            self.send(e.code, json.dumps({"detail": e.msg}), "application/json")
        except (ValueError, TypeError) as e:
            self.send(400, json.dumps({"detail": str(e)}), "application/json")
        except (BrokenPipeError, ConnectionResetError):
            pass

    def static(self, rel):
        path = os.path.realpath(os.path.join(STATIC, rel))
        if not path.startswith(os.path.realpath(STATIC) + os.sep) or not os.path.isfile(path):
            raise HTTPError(404, "not found")
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "text/javascript"):
            ctype += "; charset=utf-8"
        with open(path, "rb") as f:
            self.send(200, f.read(), ctype)


def main():
    db.connect().close()   # make sure the database file + tables exist
    try:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    except OSError:
        print(f"Port {PORT} is already in use -- the map may already be running.")
        print(f"Open http://localhost:{PORT} in your browser, or close the other window first.")
        sys.exit(1)
    url = f"http://localhost:{PORT}"
    print(f"Map running at {url}")
    print("Leave this window open. Press Ctrl+C (or close the window) to stop.")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, lambda: webbrowser.open_new(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
