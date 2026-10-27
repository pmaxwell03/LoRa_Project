// buoy_payload.h -- packet format shared with the gateway (payload.py).
// Send the bytes on Meshtastic portnum 256 (PRIVATE_APP).
//
// Layout (little-endian, packed) -- 15 + 6*N bytes:
//   u8  version (=1) | u32 unix time | i32 lat*1e7 | i32 lon*1e7 | u8 flags | u8 N
//   N x { u8 param id | u8 depth in 0.1 m (0xFF = none) | f32 value }
//
// Param IDs must match params.py. Never renumber -- only add new ones.
// Send NAN for a value if a sensor read fails; the gateway drops it.
#pragma once
#include <stdint.h>
#include <string.h>

enum BuoyParam : uint8_t {
    // Sonde
    P_PH = 1, P_TURBIDITY = 2, P_WATER_TEMP = 3, P_DO_MGL = 4,
    P_CONDUCTIVITY = 5, P_CHLOROPHYLL = 6,
    // Temperature string (one entry per depth, use depth_dm)
    P_STRING_TEMP = 20,
    // Weather station
    P_AIR_TEMP = 40, P_HUMIDITY = 41, P_PRESSURE = 42, P_WIND_SPEED = 43,
    P_WIND_DIR = 44, P_RAIN = 45, P_SOLAR = 46,
    // Node health
    P_BATTERY_V = 60, P_SOLAR_V = 61,
};

#define BUOY_PAYLOAD_VERSION 1
#define BUOY_NO_DEPTH 0xFF
#define BUOY_FLAG_GPS_OK 0x01
#define BUOY_MAX_BYTES 233   // keep well below; 15 + 6*N

class BuoyPayload {
  public:
    // ts: unix seconds (GPS time; 0 if unknown -> gateway uses receive time)
    void begin(uint32_t ts, double lat, double lon, bool gpsOk) {
        len = 0;
        put8(BUOY_PAYLOAD_VERSION);
        put32(ts);
        put32((uint32_t)(int32_t)(lat * 1e7));
        put32((uint32_t)(int32_t)(lon * 1e7));
        put8(gpsOk ? BUOY_FLAG_GPS_OK : 0);
        countPos = len;
        put8(0);
    }
    // depth_m < 0 means "no depth" (surface or air sensor)
    bool add(BuoyParam p, float value, float depth_m = -1) {
        if (len + 6 > BUOY_MAX_BYTES) return false;
        put8(p);
        put8(depth_m < 0 ? BUOY_NO_DEPTH : (uint8_t)(depth_m * 10 + 0.5f > 254 ? 254 : depth_m * 10 + 0.5f));
        memcpy(buf + len, &value, 4);   // nRF52/ESP32 are little-endian
        len += 4;
        buf[countPos]++;
        return true;
    }
    const uint8_t *data() const { return buf; }
    size_t size() const { return len; }

  private:
    uint8_t buf[BUOY_MAX_BYTES];
    size_t len = 0, countPos = 0;
    void put8(uint8_t v) { buf[len++] = v; }
    void put32(uint32_t v) { for (int i = 0; i < 4; i++) buf[len++] = (v >> (8 * i)) & 0xFF; }
};

/* Example (inside your Meshtastic module, every 30 min):

    BuoyPayload pl;
    pl.begin(getValidTime(RTCQualityFromNet), gpsLat, gpsLon, hasFix);
    pl.add(P_PH, sonde.ph);
    pl.add(P_TURBIDITY, sonde.ntu);
    for (int i = 0; i < nDepths; i++) pl.add(P_STRING_TEMP, tstring[i], depths[i]);
    pl.add(P_BATTERY_V, batteryVolts);
    // copy pl.data()/pl.size() into a meshtastic_MeshPacket with
    // decoded.portnum = meshtastic_PortNum_PRIVATE_APP and send it.
*/
