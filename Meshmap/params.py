"""
Parameter registry -- the single source of truth shared by the payload
decoder, the database and the map.

The firmware sends a 1-byte PARAM ID per value. Add new sensors here (and in
the firmware's matching enum) -- never renumber an existing ID, or old data
will decode as the wrong parameter.
"""

PARAMS = {
    # id: (key, label, unit, group, default color-scale min, max)
    # --- Sonde ---------------------------------------------------------
    1:  ("ph",            "pH",                  "",       "Sonde",   6.0, 9.0),
    2:  ("turbidity",     "Turbidity",           "NTU",    "Sonde",   0.0, 50.0),
    3:  ("water_temp",    "Water temperature",   "°C",     "Sonde",   0.0, 30.0),
    4:  ("do_mgl",        "Dissolved oxygen",    "mg/L",   "Sonde",   0.0, 14.0),
    5:  ("conductivity",  "Specific conductance","µS/cm",  "Sonde",   0.0, 1000.0),
    6:  ("chlorophyll",   "Chlorophyll",         "µg/L",   "Sonde",   0.0, 40.0),
    # --- Temperature string (one value per depth) ------------------------
    20: ("string_temp",   "Temp string",         "°C",     "Temp string", 0.0, 30.0),
    # --- Weather station ------------------------------------------------
    40: ("air_temp",      "Air temperature",     "°C",     "Weather", -30.0, 35.0),
    41: ("humidity",      "Relative humidity",   "%",      "Weather", 0.0, 100.0),
    42: ("pressure",      "Barometric pressure", "hPa",    "Weather", 960.0, 1050.0),
    43: ("wind_speed",    "Wind speed",          "m/s",    "Weather", 0.0, 20.0),
    44: ("wind_dir",      "Wind direction",      "°",      "Weather", 0.0, 360.0),
    45: ("rain",          "Rainfall",            "mm",     "Weather", 0.0, 25.0),
    46: ("solar",         "Solar radiation",     "W/m²",   "Weather", 0.0, 1000.0),
    # --- Node health ------------------------------------------------------
    60: ("battery_v",     "Battery voltage",     "V",      "Node",    3.3, 4.2),
    61: ("solar_v",       "Panel voltage",       "V",      "Node",    0.0, 7.0),
}

BY_KEY = {v[0]: dict(id=k, key=v[0], label=v[1], unit=v[2], group=v[3],
                     vmin=v[4], vmax=v[5]) for k, v in PARAMS.items()}


def param_by_id(pid):
    v = PARAMS.get(pid)
    return None if v is None else BY_KEY[v[0]]
