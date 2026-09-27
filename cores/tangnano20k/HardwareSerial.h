#pragma once

#include "api/HardwareSerial.h"

namespace tangnano20k {

/* Serial over the onboard BL616 USB-UART bridge. Received bytes queue in
 * a 64-byte hardware FIFO and written bytes in a 32-byte one (see
 * gateware/src/uart_wrap.v), so loop() doesn't have to poll within one
 * character time and write() only blocks once the TX FIFO is full. */
class HardwareSerial : public arduino::HardwareSerial
{
public:
  void begin(unsigned long baudrate) override;
  void begin(unsigned long baudrate, uint16_t config) override;
  void end() override;

  int available(void) override;
  int availableForWrite(void) override;
  int peek(void) override;
  int read(void) override;
  void flush(void) override;
  size_t write(uint8_t c) override;
  using Print::write;

  // printf-style output, formatted by the core's own vsnprintf()
  // (tangnano20k_printf.c). Not in ArduinoCore-API's Print, but many
  // libraries written for ESP32/RP2040 call Serial.printf().
  size_t printf(const char *format, ...) __attribute__((format(printf, 2, 3)));

  operator bool() override { return true; }

  // Returns whether received bytes were lost (the RX FIFO was full) since
  // the last call, and clears the flag.
  bool overflow(void);

private:
  void refillRxCache(void);
  uint32_t readStatus(void);

  bool rxHasByte = false;
  bool rxOverflow = false;
  uint8_t rxByte = 0;
};

} // namespace tangnano20k
