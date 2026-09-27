#include "HardwareSerial.h"
#include "tangnano20k_soc.h"

#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>

namespace tangnano20k {

void HardwareSerial::begin(unsigned long baudrate)
{
  /* simpleuart's bit period is (divisor + 2) clock cycles, so round the
   * ideal cycles-per-bit and subtract 2 - plain F_CPU/baud runs ~5% slow
   * at 921600 baud and 27MHz, beyond what a receiver tolerates. */
  if (baudrate == 0)
    return;
  uint32_t cycles = (TANGNANO20K_CLK_FREQ + baudrate / 2) / baudrate;
  TANGNANO20K_UART_DIV_REG = (cycles > 2) ? cycles - 2 : 0;
}

void HardwareSerial::begin(unsigned long baudrate, uint16_t /*config*/)
{
  /* Only 8N1 is supported by the simpleuart peripheral; config is ignored. */
  begin(baudrate);
}

void HardwareSerial::end()
{
}

void HardwareSerial::refillRxCache(void)
{
  if (rxHasByte)
    return;

  uint32_t v = TANGNANO20K_UART_DAT_REG;
  if (v != 0xFFFFFFFFUL) {
    rxByte = (uint8_t)v;
    rxHasByte = true;
  }
}

/* Every STATUS read clears the hardware's sticky overflow bit, so it's
 * latched here for overflow() whichever call happened to read it. */
uint32_t HardwareSerial::readStatus(void)
{
  uint32_t status = TANGNANO20K_UART_STATUS_REG;
  if (status & TANGNANO20K_UART_STATUS_RX_OVERFLOW)
    rxOverflow = true;
  return status;
}

int HardwareSerial::available(void)
{
  return (rxHasByte ? 1 : 0) + (int)TANGNANO20K_UART_STATUS_RX_COUNT(readStatus());
}

int HardwareSerial::availableForWrite(void)
{
  return (int)TANGNANO20K_UART_STATUS_TX_FREE(readStatus());
}

bool HardwareSerial::overflow(void)
{
  readStatus();
  bool result = rxOverflow;
  rxOverflow = false;
  return result;
}

int HardwareSerial::peek(void)
{
  refillRxCache();
  return rxHasByte ? rxByte : -1;
}

int HardwareSerial::read(void)
{
  refillRxCache();
  if (!rxHasByte)
    return -1;

  rxHasByte = false;
  return rxByte;
}

void HardwareSerial::flush(void)
{
  // Waits until the TX FIFO has drained and the last stop bit is out.
  while (!(readStatus() & TANGNANO20K_UART_STATUS_TX_IDLE)) {
  }
}

size_t HardwareSerial::write(uint8_t c)
{
  TANGNANO20K_UART_DAT_REG = c;
  return 1;
}

size_t HardwareSerial::printf(const char *format, ...)
{
  // Short messages format on the stack; longer ones get a heap buffer of
  // the exact size vsnprintf() reports.
  char stackBuf[64];
  va_list ap;
  va_start(ap, format);
  int len = vsnprintf(stackBuf, sizeof(stackBuf), format, ap);
  va_end(ap);
  if (len < 0)
    return 0;
  if ((size_t)len < sizeof(stackBuf))
    return write((const uint8_t *)stackBuf, len);

  char *heapBuf = (char *)malloc(len + 1);
  if (!heapBuf)
    return 0;
  va_start(ap, format);
  vsnprintf(heapBuf, len + 1, format, ap);
  va_end(ap);
  size_t written = write((const uint8_t *)heapBuf, len);
  free(heapBuf);
  return written;
}

} // namespace tangnano20k

tangnano20k::HardwareSerial Serial;

/* printf()/puts() (tangnano20k_printf.c) write through this, so stdout
 * goes to Serial like on the ESP32/RP2040 cores. */
extern "C" int putchar(int c)
{
  Serial.write((uint8_t)c);
  return (unsigned char)c;
}

/* Called by main() after every loop(): runs the sketch's serialEvent(),
 * if it defines one, while received bytes are waiting. */
void serialEvent(void) __attribute__((weak));

void serialEventRun(void)
{
  if (serialEvent && Serial.available())
    serialEvent();
}
