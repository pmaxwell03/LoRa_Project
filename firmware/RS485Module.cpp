#include "RS485Module.h"
#include "configuration.h"

RS485Module *rs485Module;

RS485Module::RS485Module()
    : SinglePortModule("rs485", meshtastic_PortNum_PRIVATE_APP),
      concurrency::OSThread("RS485") {

    // --- 1) Power the 3V3_S rail that feeds the RAK5802 ---
    // WB_IO2 = Arduino pin 34 on RAK4631
    pinMode(POWER_EN_PIN, OUTPUT);
    digitalWrite(POWER_EN_PIN, HIGH);
    delay(50);

    // --- 2) Force the RAK5802 into RECEIVE mode ---
    // The SP3485 chip has DE/RE tied together and wired to one of the
    // WisBlock IO pins. We don't know for certain which GPIO it is on the
    // RAK4631 so we drive every plausible WB_IO as OUTPUT LOW. The real
    // DE/RE pin ends up LOW (receiver enabled, driver disabled); the other
    // pins are harmless no-ops.
    //
    // RAK4631 WisBlock -> Arduino digital pin mapping:
    //   WB_IO1 = 17, WB_IO3 = 21, WB_IO4 = 4, WB_IO5 = 9, WB_IO6 = 10
    //   (WB_IO2 = 34 is already in use as POWER_EN above, don't touch it)
    const uint8_t candidateDirPins[] = {
        4,   // WB_IO4
        9,   // WB_IO5
        10,  // WB_IO6
        17,  // WB_IO1
        21,  // WB_IO3
    };
    for (uint8_t p : candidateDirPins) {
        pinMode(p, OUTPUT);
        digitalWrite(p, LOW);
    }
    delay(10);

    // --- 3) Open Serial1 on IO Slot A UART ---
    // On RAK4631, Serial1 is pre-wired to the WisBlock IO Slot A's
    // TXD0/RXD0 lines via the RAK4631 variant.h. No pin remapping needed.
    Serial1.begin(RS485_BAUD);

    LOG_INFO("=========================================");
    LOG_INFO("RS485 RECEIVE-ONLY DIAGNOSTIC v4 (RAK4631)");
    LOG_INFO("=========================================");
    LOG_INFO("3V3_S rail (WB_IO2 = pin %u) HIGH", POWER_EN_PIN);
    LOG_INFO("DE/RE candidate pins driven LOW (RX mode)");
    LOG_INFO("Serial1 @ %u baud on IO Slot A UART", (unsigned)RS485_BAUD);
    LOG_INFO("");
    LOG_INFO("Listening on IO Slot A RS485 bus.");
    LOG_INFO("Heartbeat every 5s so you know firmware is alive.");
    LOG_INFO("=========================================");

    lastHeartbeatMs = millis();
}

int32_t RS485Module::runOnce() {
    uint32_t now = millis();

    // Pull any pending bytes from the UART
    while (Serial1.available() > 0) {
        if (rxLen < RX_BUFFER_SIZE) {
            rxBuffer[rxLen++] = Serial1.read();
            lastByteMs = now;
            totalBytesReceived++;
        } else {
            Serial1.read();  // overflow guard
        }
    }

    // If we have bytes and the line has been quiet for 50ms, dump them
    if (rxLen > 0 && (now - lastByteMs) > 50) {
        char line[1024];
        int off = snprintf(line, sizeof(line), ">>> RX[%u]:", (unsigned)rxLen);
        for (size_t i = 0; i < rxLen && off < (int)sizeof(line) - 4; i++) {
            off += snprintf(line + off, sizeof(line) - off, " %02X", rxBuffer[i]);
        }
        LOG_INFO("%s", line);
        rxLen = 0;
    }

    // 5-second heartbeat
    if (now - lastHeartbeatMs > 5000) {
        LOG_INFO("[heartbeat] alive, %u bytes received total",
                 (unsigned)totalBytesReceived);
        lastHeartbeatMs = now;
    }

    return 10;
}
