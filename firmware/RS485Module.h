#pragma once
#include "SinglePortModule.h"
#include "concurrency/OSThread.h"

class RS485Module : public SinglePortModule, private concurrency::OSThread {
  public:
    RS485Module();
  protected:
    virtual int32_t runOnce() override;
  private:
    // --- RAK4631 (nRF52840) WisBlock pin mapping ---
    // WB_IO2 = Arduino pin 34 on RAK4631 — the 3V3_S rail enable
    static constexpr uint8_t  POWER_EN_PIN   = 34;

    // Serial1 is pre-wired to IO Slot A's TXD0/RXD0 by the RAK4631 variant
    // (so we DON'T call setTX/setRX/setPins — just Serial1.begin())

    static constexpr uint32_t RS485_BAUD     = 9600;
    static constexpr size_t   RX_BUFFER_SIZE = 256;

    uint8_t  rxBuffer[RX_BUFFER_SIZE];
    size_t   rxLen = 0;
    uint32_t lastByteMs = 0;
    uint32_t totalBytesReceived = 0;
    uint32_t lastHeartbeatMs = 0;
};

extern RS485Module *rs485Module;
