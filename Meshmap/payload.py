"""
Binary payload sent by each node on Meshtastic PRIVATE_APP (portnum 256).

All little-endian. Total = 15 + 6*N bytes, so up to ~35 values fit in one
LoRa packet (keep it well under that to save airtime).

  offset size type    field
  0      1    uint8   version          (currently 1)
  1      4    uint32  unix timestamp   (UTC seconds, from GPS)
  5      4    int32   latitude  * 1e7
  9      4    int32   longitude * 1e7
  13     1    uint8   flags            (bit0 = GPS fix valid)
  14     1    uint8   N  (number of values)
  then N times:
  +0     1    uint8   param id         (see params.py)
  +1     1    uint8   depth in 0.1 m   (0xFF = no depth / surface sensor)
  +2     4    float32 value

Matching C struct for the firmware side:

  #pragma pack(push, 1)
  typedef struct { uint8_t param; uint8_t depth_dm; float value; } reading_t;
  typedef struct {
      uint8_t  version;  uint32_t ts;  int32_t lat_e7;  int32_t lon_e7;
      uint8_t  flags;    uint8_t  n;   reading_t r[];
  } payload_t;
  #pragma pack(pop)
"""
import struct

from params import param_by_id

VERSION = 1
HEADER = struct.Struct("<BIiiBB")
ITEM = struct.Struct("<BBf")
NO_DEPTH = 0xFF


def encode(ts, lat, lon, readings, gps_ok=True):
    """readings: list of (param_id, depth_m or None, value)"""
    out = HEADER.pack(VERSION, int(ts), round(lat * 1e7), round(lon * 1e7),
                      1 if gps_ok else 0, len(readings))
    for pid, depth, val in readings:
        d = NO_DEPTH if depth is None else max(0, min(254, round(depth * 10)))
        out += ITEM.pack(pid, d, float(val))
    return out


def decode(buf):
    """Returns dict(ts, lat, lon, gps_ok, readings=[(key, depth_m|None, value)]).
    Unknown param IDs are skipped (so old gateways tolerate new firmware)."""
    if len(buf) < HEADER.size:
        raise ValueError(f"payload too short ({len(buf)} bytes)")
    ver, ts, lat, lon, flags, n = HEADER.unpack_from(buf, 0)
    if ver != VERSION:
        raise ValueError(f"unsupported payload version {ver}")
    need = HEADER.size + n * ITEM.size
    if len(buf) < need:
        raise ValueError(f"payload truncated: {len(buf)} < {need} bytes")
    readings = []
    for i in range(n):
        pid, d, val = ITEM.unpack_from(buf, HEADER.size + i * ITEM.size)
        p = param_by_id(pid)
        if p is None or val != val:  # unknown id or NaN (sensor fault)
            continue
        readings.append((p["key"], None if d == NO_DEPTH else d / 10.0, val))
    return dict(ts=ts, lat=lat / 1e7, lon=lon / 1e7, gps_ok=bool(flags & 1),
                readings=readings)
