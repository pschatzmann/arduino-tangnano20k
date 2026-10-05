# Peripherals

What each API does and how it maps to the gateware and pins. What has
been tried on a real board is listed in
[Hardware test status](HARDWARE_STATUS.md).

## Serial and `printf`

`Serial` runs over the onboard BL616's USB-UART bridge (8N1 only; see
[Known limitations](KNOWN_LIMITATIONS.md) for which USB port to open).
`gateware/src/uart_wrap.v` puts a 64-byte receive FIFO and a 32-byte
transmit FIFO in front of the UART. Incoming bytes wait in hardware until
`read()` collects them (about 5.5ms of slack at 115200 baud), and
`write()` only blocks once 32 bytes are queued. `availableForWrite()`
reports the free TX space, `flush()` waits until the last stop bit has
gone out, and `Serial.overflow()` reports (and clears) whether received
bytes were lost because the FIFO was full. A sketch-defined
`serialEvent()` is called after each `loop()` while bytes are waiting.

The core has a compact `printf` family (`tangnano20k_printf.c`):
`printf()`/`puts()` write to `Serial`, and `snprintf()`/`sprintf()`/
`vsnprintf()` format into a buffer. It covers the usual integer, string,
character, pointer and floating-point conversions (`%f`/`%e`/`%g` are
software-emulated, since there's no FPU), but not `%n`/`%a` or wide
characters.

`Serial.printf()` is available too, as on the ESP32/RP2040 cores (it
isn't part of the standard Arduino `Print` class). It formats with the
same `vsnprintf()`, on the stack for up to 63 characters and in a heap
buffer of the exact size beyond that.

## Digital I/O and PWM

Pins 0-5 are the 6 onboard LEDs: `pinMode`/`digitalWrite`/`digitalRead`
work, plus `analogWrite()` (real hardware PWM, `gateware/src/pwm_bank.v`) —
calling it switches that LED into PWM mode; a later `digitalWrite()`/`pinMode()`
call switches it back to plain on/off, matching real-Arduino behavior. Pin
6 (`BTN1`) is the board's second button (KEY_S2), `digitalRead`-only.
Pins 14-34 (`GPIO0`-`GPIO20`) are real general-purpose I/O — see
[General GPIO](#general-gpio) below. There's no `analogRead()` — the board
has no ADC wired to any pin, so that function is stubbed to always
return 0.

### PWM on GPIO pins and `analogWriteFrequency()`

`analogWrite()` works the same way on the LEDs and on `GPIO0`-`GPIO20`:
all 27 pins share a pool of **6** PWM channels. The first `analogWrite()`
to a pin takes a free channel, and `pinMode()`/`digitalWrite()` on that
pin gives it back. So up to 6 pins (LEDs and GPIO in any mix) can be in
PWM mode at once. With all 6 in use, `analogWrite()` on a seventh pin
falls back to plain on/off (HIGH for values >= 128), as AVR Arduinos do
on non-PWM pins.

`analogWriteFrequency(pin, hz)` sets the frequency per pin, independently
for every channel. It takes effect immediately if the pin is already in
PWM mode, otherwise at its next `analogWrite()`.

| | 27MHz clock | Formula |
|---|---|---|
| Default (`hz` = 0) | 105.5kHz | `F_CPU/256` (unchanged from before) |
| Maximum | 13.5MHz | `F_CPU/2` |
| Minimum | ~1.6Hz | `F_CPU/2^24` |

Values are Arduino's 0-255 by default at any frequency (0 = always low,
255 = always high). `analogWriteResolution(bits)` (1-16) changes the range
to 0..2^bits-1, for example 12 bits for 0-4095. The real resolution is
`log2(F_CPU/hz)` bits, up to 16. Above the default frequency, neighboring
values start mapping to the same duty cycle, and at the maximum only
0%/50%/100% remain. 16 useful bits need `hz` <= `F_CPU/65536` (~412Hz at
27MHz). A new value takes effect at the start of the next PWM period, so
no pulse is ever cut short. See `libraries/Core/examples/PWMFrequency`.

The same channels also serve `tone()` and the `Servo` library, so all
three together are limited to 6 pins at once:

- **`tone()`** plays a hardware 50% square wave from a channel, with no
  CPU load. A timer is only used to end it after `duration`. Only when
  all channels are busy does it fall back to toggling the pin from a
  timer interrupt. One tone plays at a time; a new `tone()` replaces the
  current one.
- **`Servo`** (`#include <Servo.h>`, `libraries/Servo/`) has the standard
  Arduino API (`attach()`, `write()` in degrees, `writeMicroseconds()`,
  `read()`, `detach()`). Each servo runs a 50Hz frame on a channel with
  ~0.33us pulse resolution at 27MHz, and uses no interrupts. `attach()`
  returns `INVALID_SERVO` if no channel is free. See
  `libraries/Servo/examples/ServoSweep`.

## General GPIO

`gateware/src/gpio_bank.v` exposes 21 pins as real `pinMode(INPUT/OUTPUT)`/
`digitalWrite`/`digitalRead` GPIO, as `GPIO0`-`GPIO20` (pins 14-34). Unlike
the LED/`BTN1` pins above, `pinMode()` here actually changes hardware
direction.

Every GPIO pin has a weak pull-up, fixed at synthesis time in
`gateware/picorv32_20k.cst` (Gowin pull modes can't be switched at run
time). So `INPUT_PULLUP` works for buttons wired to ground, `INPUT`
behaves the same (an undriven pin reads `HIGH` rather than floating), and
`INPUT_PULLDOWN` isn't available. `OUTPUT_OPENDRAIN` is emulated on top of
the pull-up: `digitalWrite(LOW)` drives the pin low, `digitalWrite(HIGH)`
releases it.

`digitalWrite()` changes a pin with a single write to a SET/CLR register
(`TANGNANO20K_GPIO_OUT_SET_REG`/`..._CLR_REG`, and `TANGNANO20K_LED_SET_REG`/
`..._CLR_REG` for the LEDs) rather than a read-modify-write, so it's safe
to call from an interrupt handler while `loop()` is writing other pins.

These are 21 of the official datasheet's "34 free IOs" on the J5/J6
expansion headers — the other 13 header positions are the *same physical
pins* already wired to the LEDs (15-20), I2S (51/54/55/56), I2C (80/85),
and WS2812 (79) peripherals documented elsewhere on this page; this board
ties those header positions directly to those onboard functions, so
there's no separate way to reach them as plain GPIO. Several of the 21
below also double as the optional RGB LCD FPC connector or the HDMI EDID
I2C bus — using them as GPIO is fine as long as you're not also using
that connector/bus.

| Pin | FPGA pin | Also known as (if in use elsewhere on the board) |
|---|---|---|
| GPIO0 | 73 | — |
| GPIO1 | 74 | — |
| GPIO2 | 75 | — |
| GPIO3 | 77 | RGB LCD connector: LCD_CLK |
| GPIO4 | 27 | RGB LCD connector: LCD_B7 |
| GPIO5 | 28 | RGB LCD connector: LCD_B6 |
| GPIO6 | 25 | RGB LCD connector: LCD_HS |
| GPIO7 | 26 | RGB LCD connector: LCD_VS |
| GPIO8 | 29 | RGB LCD connector: LCD_B5 |
| GPIO9 | 30 | RGB LCD connector: LCD_B4 |
| GPIO10 | 31 | RGB LCD connector: LCD_B3 |
| GPIO11 | 76 | — |
| GPIO12 | 42 | RGB LCD connector: LCD_R3 |
| GPIO13 | 41 | RGB LCD connector: LCD_R4 |
| GPIO14 | 48 | RGB LCD connector: LCD_DE |
| GPIO15 | 49 | RGB LCD connector: LCD_BL (backlight) |
| GPIO16 | 86 | PWM audio left (Tools > PWM Audio) |
| GPIO17 | 72 | PWM audio right (Tools > PWM Audio) |
| GPIO18 | 71 | — |
| GPIO19 | 53 | HDMI connector: EDID_CLK |
| GPIO20 | 52 | HDMI connector: EDID_DAT |

(Pin 79, formerly `GPIO17`, is now the dedicated [WS2812 LED](#ws2812-led) pin.)

See `libraries/Core/examples/GPIOBlink`. Pin numbers are sourced from the official
[Tang Nano 20K Datasheet v1.3](https://dl.sipeed.com/fileList/TANG/Nano_20K/1_Datasheet/Sipeed%20Tang%20nano%2020K%20Datasheet%20V1.3-en_US.pdf)'s
pinout table, cross-checked against the schematic pin numbers used
elsewhere in this file. `variants/tangnano20k/pins_arduino.h` has
compile-time lookups both ways: `TANGNANO20K_PHYSICAL_PIN(GPIOn)` (e.g.
`TANGNANO20K_PHYSICAL_PIN(GPIO3)` is `77`) and, the other direction,
`TANGNANO20K_GPIO_FOR_PIN(n)` (e.g. `TANGNANO20K_GPIO_FOR_PIN(77)` is
`GPIO3`).

## WS2812 LED

`#include <WS2812.h>` (`libraries/WS2812/`). `WS2812.write(r, g, b)` sets
the onboard addressable RGB LED (physical FPGA pin 79).

`WS2812Strip` drives an external strip of any length on any GPIO pin,
with an Adafruit_NeoPixel-style API (`begin()`, `setPixelColor()`,
`fill()`, `setBrightness()`, `show()`, `Color()`, `ColorHSV()`); the pixel
buffer lives on the SDRAM heap:

```cpp
WS2812Strip strip(30, GPIO0);
strip.begin();
strip.setPixelColor(0, 255, 0, 0);
strip.show();
```

Both are backed by `gateware/src/ws2812_strip.v`, a hardware shift-timer
rather than software bit-banging, since WS2812's protocol needs
~400ns-precision pulses. It streams back-to-back pixels as one frame and
latches the frame (~300us low) only once no further pixel is queued.
`show()` disables interrupts while the pixels go out (~30us per pixel),
because a pause of more than ~50us mid-frame would latch a partial one.
That can delay other interrupt work, such as I2S buffering or
`SoftwareSerial` reception, by that long.

There's one hardware driver: each `show()` routes it to that strip's
pin, so several strips work, one after another. While a strip on a GPIO
pin is being driven, the onboard LED is left alone. See
`libraries/WS2812/examples/WS2812Rainbow` and `WS2812StripRainbow`.

This replaces `ws2812b.v`/`ws2812b_tgt.v` vendored from
[grughuhler/picorv32_tang_nano_20k](https://github.com/grughuhler/picorv32_tang_nano_20k),
which sent a latch pulse after every pixel, so it could only ever drive a
single LED.

## Audio (I2S)

`#include <I2STangNano.h>` (`libraries/I2S/`, backed by `gateware/src/i2s.v`).
`I2S.begin(config)` takes an `I2SConfig` - get one from
`I2S.defaultConfig(mode)`, adjust its fields, and pass it in:

```cpp
I2SConfig config = I2S.defaultConfig(I2S_MODE_DUPLEX);
config.sampleRate = 44100;
I2S.begin(config);
```

`sampleRate` (default `44100`) sets the shared BCLK to `sampleRate * 32` (a fractional-N clock, so any rate is exact on average - 44100 at 27MHz included) (the hardware always moves
16-bit samples, regardless of `bits` below) - this same clock paces both
transmit and receive, regardless of `mode`. `mode` is one of
`I2S_MODE_OUTPUT` (default), `I2S_MODE_INPUT`, or `I2S_MODE_DUPLEX` - it
only controls whether `begin()` enables the amplifier (`PA_EN`, skipped
for `I2S_MODE_INPUT`) and what `available()` reports (see Stream below);
the hardware runs transmit and receive simultaneously either way, so a
sketch calling `write()` and `read()` around the same loop is running
duplex regardless of which `mode` was passed - there's no separate
hardware mode to switch into. `channels` is `1` (mono) or `2` (stereo,
the default); with `1`, writes duplicate the sample onto both hardware
channels and reads only expose the left channel. `ringSamples` (default
`512`) sets the depth of each direction's software ring buffer - see
"Buffering and interrupts" below; `I2S.ringSamples()` reports the size
actually in effect if an oversized request fell back to a smaller one.
`I2S.config()` returns the full configuration actually in effect.

`I2SClass` is an `arduino::Stream` - `write(uint8_t)`/`read()`/`peek()`/
`available()` (plus `Print`'s bulk `write(const uint8_t*, size_t)`) are
the only way in or out, working on raw little-endian PCM bytes at the
configured `bits` depth - `I2S_BITS_8`, `I2S_BITS_8_UNSIGNED`,
`I2S_BITS_16` (default), `I2S_BITS_24`, or `I2S_BITS_32` - channels
interleaved left-then-right, converting to/from the hardware's native
16-bit samples internally. This lets I2S output/input be piped directly
into or out of any other `Stream`-based code (e.g. playing a PCM WAV
file's bytes straight through). To write or read a single sample pair
directly, go through the bulk form: `int16_t frame[2] = {left, right};
I2S.write((uint8_t*)frame, sizeof(frame));` (and the receive-side
mirror, `I2S.readBytes((uint8_t*)frame, sizeof(frame));`, inherited from
`Stream`). See "Buffering and interrupts" below for what backs this.

### Buffering and interrupts

Both directions in `i2s.v` are backed by a 16-sample hardware FIFO
(rather than a single-sample shadow register), plus a software ring
buffer per direction (`libraries/I2S/src/I2S.cpp`, `ringSamples` deep,
4 bytes per sample; up to 512 samples live in internal SRAM, larger rings
come from the much slower SDRAM heap) that a dedicated interrupt keeps synchronized with the
hardware FIFO in the background. `write()` puts a sample straight into
the hardware FIFO while nothing is queued and it has room; otherwise it
pushes onto the software ring and arms the interrupt. The transmit
interrupt fires when the hardware FIFO is at most half full, and the ISR
refills it from the ring, disarming itself once the ring is empty.
Receive mirrors this: the interrupt continuously fills
the software ring from the hardware FIFO whenever `mode` includes input,
disarming itself if the ring fills up (freed again the next time
`read()` pops a sample). This means a sketch can call `write()`/`read()`
in bursts, or skip a few `loop()` iterations doing other work, without
needing to hit the exact sample rate every time - up to `ringSamples`
(plus the hardware FIFO's own 16) of slack in either direction; raise it
in `I2SConfig` for a sketch with bursty timing, or lower it to save
memory if `loop()` is reliably fast and regular. `available()` is
genuinely non-blocking, reporting exactly what's already been captured
in the background rather than assuming more is always imminent.

- **Transmit** (always available): like `Serial`'s UART writes, `write()`
  blocks via hardware bus backpressure (ultimately - see above) rather
  than a software timer, pacing output to the configured sample rate
  automatically. Pin numbers (`PA_EN`=51, `DIN`=54, `WS`=55, `BCLK`=56)
  are confirmed against Sipeed's own
  [audio example](https://github.com/sipeed/TangNano-20K-example/tree/main/audio).
  See `libraries/I2S/examples/I2SToneTest`.
- **Receive**: select **Tools > I2S Input: Enabled** (disabled by
  default, same real GPIO-pin cost/opt-in pattern as a
  [second SPI/I2C port](#a-second-spi--i2c-port)) and wire an external I2S
  microphone's data-out line to `GPIO6`, sharing the same `WS`/`BCLK`
  lines the onboard amplifier uses - this is a synthesis-time decision
  (it removes `GPIO6` from the general-purpose GPIO pool in the
  bitstream itself), independent of the `mode` passed to `begin()`. With
  the menu left disabled, `GPIO6` stays plain GPIO and captured samples
  are always silence.
- **Duplex**: see above - `libraries/I2S/examples/I2SDuplexTest` passes each captured
  frame straight back out to the amplifier.

| Object | Menu | Function | Pin printed on the device |
|---|---|---|---|
| `I2S` | always present | PA_EN | 51 |
| `I2S` | always present | DIN | 54 |
| `I2S` | always present | WS | 55 |
| `I2S` | always present | BCLK | 56 |
| `I2S` | Tools > I2S Input: Enabled | RX_DIN | 25 (`GPIO6`) |

Pin numbers are the same physical FPGA pin numbers used throughout this
page (sourced from the official datasheet's pinout table - see
[General GPIO](#general-gpio)); `RX_DIN` doubles as `GPIO6` when Tools >
I2S Input is left at its default, Disabled.

The frame follows the Philips/I2S convention.

The CPU time budget matters at 27MHz: each 44.1kHz stereo sample leaves
about 600 clock cycles for the sketch and the library together, and the
CPU needs roughly 4 cycles per instruction. Write samples in blocks
(e.g. 64 frames per `I2S.write()` call) rather than one at a time, keep
per-sample work small (precompute tables, avoid divisions), and avoid
`Serial` prints longer than about 32 characters while playing - they
stall the CPU on the UART long enough to empty the FIFO (an audible
click). For more headroom use a lower sample rate, a faster Tools > Clock
Speed, or the Barrel Shifter and Hardware Multiply/Divide options.
`I2S.availableForWrite()` reports how many samples can be written
without blocking.

## Audio (PWM)

`#include <PWMAudio.h>` (`libraries/PWMAudio/`, backed by
`gateware/src/pwm_audio.v`). Needs **Tools > PWM Audio: Enabled**
(disabled by default, the same opt-in pattern as I2S Input): it claims
`GPIO16` (left) and `GPIO17` (right), removing both from the
general-purpose GPIO pool. `PWMAudio.h` raises a compile error if the
menu is left disabled, and `begin()` returns `false` on a bitstream built
without it.

```cpp
PWMAudioConfig config = PWMAudio.defaultConfig();
config.sampleRate = 44100; // default
config.channels = 2;       // default; 1 = mono, driven on both pins
config.pwmRate = 50000;    // default, PWM carrier frequency in Hz
PWMAudio.begin(config);
```

Each pin carries a `pwmRate` square wave whose duty cycle follows the
signal, so it needs a low-pass filter before a speaker. A 1k resistor
plus a 10nF capacitor to ground on each pin, feeding an amplifier or
headphones, works. Resolution is `log2(CLK_FREQ / pwmRate)` bits, about
9 bits at 50kHz and 27MHz, so a lower `pwmRate` gives more resolution
but is harder to filter out. Both rates are integer dividers of the
system clock: 44100 Hz at 27MHz actually runs at 44118 Hz.

The API is the output half of [I2S](#audio-i2s)'s: `PWMAudioClass` is an
`arduino::Stream` that takes little-endian signed 16-bit PCM,
left-then-right, through `write()`. `availableForWrite()` reports free
buffer space; `read()`/`available()` are always empty. Samples go
through a `ringSamples`-deep software ring buffer (default `64`, SDRAM
heap) into a 16-sample hardware FIFO. The hardware pops one sample per
sample period and scales it onto the PWM period itself, so the CPU never
multiplies per sample. An interrupt (`irq[6]`) refills the FIFO whenever
it drops to half full, so each interrupt pushes at least 8 samples. If
the FIFO runs dry, the last level is held. New duty values only take
effect at the start of a PWM period, so no pulse is ever cut short. See
`libraries/PWMAudio/examples/PWMAudioToneTest`.

| Object | Menu | Function | Pin printed on the device |
|---|---|---|---|
| `PWMAudio` | Tools > PWM Audio: Enabled | Left | 86 (`GPIO16`) |
| `PWMAudio` | Tools > PWM Audio: Enabled | Right | 72 (`GPIO17`) |

## SPI, I2C (`Wire`), and the SD card

The primary SPI and I2C **share the onboard microSD card slot's bus
pins** — use at most one of them at a time.

Both are present by default but independently configurable via
**Tools > SPI Buses** / **Tools > I2C Buses** (0/1/2 each - see
[Tools menus](BUILDING.md#tools-menus)):

- **None**: removes that port's gateware entirely to save LUTs. `SPI`/
  `Wire` (and anything built on them, e.g. `SD`) then silently read back
  0/no-op instead of talking to real hardware - the same "claim the
  address, answer with 0" pattern this core uses for every other
  menu-gated peripheral, rather than hanging.
- **One** (the default): the primary port on the microSD slot's pins.
- **Two**: adds a second, independent port on general-purpose GPIO - see
  below.

- **SPI** (`#include <SPI.h>`, `libraries/SPI/`, backed by
  `gateware/src/spi_master.v`): a real hardware shift register supporting
  all four SPI modes and both bit orders, taken from `SPISettings`. The
  clock is the fastest `F_CPU/(2n)` that doesn't exceed the requested
  one, at most `F_CPU/2`. There's a single fixed CS line asserted for the
  duration of `beginTransaction()`/`endTransaction()`, not a
  general-purpose CS pin — only one SPI device at a time. See
  `libraries/SPI/examples/SPITransfer`.
- **I2C** (`#include <Wire.h>`, `libraries/Wire/`, backed by
  `gateware/src/od_gpio2.v`): bit-banged in software over an open-drain
  SDA/SCL pair (internal pull-ups enabled in the `.cst`), master mode
  only, with bit timing from the cycle counter, so 400kHz is reachable.
  A device holding SCL low is waited for only up to the timeout (25ms by
  default, `setWireTimeout()`/`getWireTimeoutFlag()`/
  `clearWireTimeoutFlag()` as on AVR). After that the transfer is
  abandoned: `endTransmission()` returns 5 and `requestFrom()` returns 0,
  so a missing pull-up or a stuck device can't hang the sketch. See
  `libraries/Wire/examples/I2CScanner`.

| Object | Menu | Function | Pin printed on the device |
|---|---|---|---|
| `SPI` | Tools > SPI Buses: One+ | SCLK | 83 |
| `SPI` | Tools > SPI Buses: One+ | MOSI | 82 |
| `SPI` | Tools > SPI Buses: One+ | MISO | 84 |
| `SPI` | Tools > SPI Buses: One+ | CS | 81 |
| `SPI2` | Tools > SPI Buses: Two | SCLK | 73 (`GPIO0`) |
| `SPI2` | Tools > SPI Buses: Two | MOSI | 74 (`GPIO1`) |
| `SPI2` | Tools > SPI Buses: Two | MISO | 75 (`GPIO2`) |
| `SPI2` | Tools > SPI Buses: Two | CS | 77 (`GPIO3`) |
| `Wire` | Tools > I2C Buses: One+ | SDA | 85 |
| `Wire` | Tools > I2C Buses: One+ | SCL | 80 |
| `Wire2` | Tools > I2C Buses: Two | SDA | 27 (`GPIO4`) |
| `Wire2` | Tools > I2C Buses: Two | SCL | 28 (`GPIO5`) |

Pin numbers are the same physical FPGA pin numbers used throughout this
page (sourced from the official datasheet's pinout table - see
[General GPIO](#general-gpio)); `SPI2`/`Wire2`'s pins double as
`GPIO0`-`GPIO5` when Tools > SPI/I2C Buses is left at the default **One**
instead.

### A second SPI + I2C port

Select **Tools > SPI Buses: Two** and/or **Tools > I2C Buses: Two**
(independent of each other - they use non-overlapping pins) for a second, fully
independent SPI and/or I2C port - `SPI2`/`Wire2` (see the table above),
same `TangNanoSPIClass`/`TwoWire` API as the first port, backed by a
second instance of the same `spi_master.v`/`od_gpio2.v` gateware. This
board has only one dedicated SPI/I2C-capable bus (the microSD slot's pins
used above), so the second port runs on general-purpose GPIO instead.
Selecting **Two** permanently removes those specific GPIO pins (0-3 for
SPI, 4-5 for I2C) from the general-purpose GPIO pool (see
[General GPIO](#general-gpio)). See `libraries/SPI/examples/ExtraSPII2CTest`.

### SD card

`#include <SD.h>` (`libraries/SD/`, plus `#include <SPI.h>`) **and**
select **Tools > SD Card: Enabled (GPLv3)** - unlike every other library
in this repo, `SD.h` won't compile (a deliberate `#error`) unless you've
explicitly made that menu choice, because linking it in makes your
sketch's binary a GPLv3 derivative. This is the real [arduino-libraries/SD](https://github.com/arduino-libraries/SD)
(**GPLv3** - see [Licensing](LICENSING.md)) talking to the onboard microSD slot
over the `SPI` library above, in standard SD-over-SPI mode - the same
electrical wiring the slot actually uses. Call `SD.begin(SS)`.

Deliberate patches to the otherwise-vendored-unmodified code:

1. This hardware's SPI chip select is controlled internally by the SPI
   peripheral (asserted for a whole transaction), not through an arbitrary
   GPIO pin the way the SD library expects to toggle it directly.
   `pins_arduino.h` defines a virtual `SS` pin (10) that
   `wiring_digital.cpp`'s `digitalWrite()`/`digitalRead()` special-case to
   drive/read that hardware CS bit, so the vendored library's plain
   `pinMode()`/`digitalWrite()` calls on `SS` work unmodified; the actual
   edit is a small added architecture branch in
   `libraries/SD/src/utility/Sd2PinMap.h` (clearly marked in that file),
   since it otherwise `#error`s on any board it doesn't explicitly recognize.
2. The `TANGNANO20K_SD_ENABLED` guard at the top of `libraries/SD/src/SD.h`
   described above.
3. An added `libraries/SD/src/FS.h`, so libraries written for the
   ESP32/ESP8266/RP2040 cores' `<FS.h>` compile here: `fs::File` and
   `fs::FS` are SD's own `File` and `SDClass`, so a `File` from
   `SD.open()` can be passed to them directly. It includes `SD.h`, so it
   needs the same menu selection.
4. A `File::read(uint8_t *buf, size_t size)` overload in `SD.h`: the
   original `read(void *, uint16_t)` truncates lengths over 65535, which
   ESP32-style `file.read(buf, file.size())` hits for any file over 64KB.

Enabling the menu doesn't change the gateware/bitstream at all -
`libraries/SD` is pure software on top of the always-present SPI
peripheral; the menu only gates whether `SD.h` compiles.

See `libraries/SD/examples/SDReadWrite`.

## CAN

`#include <CAN.h>` (`libraries/CAN/`), with **Tools > CAN: Enabled**. It
implements Arduino's standard `HardwareCAN` API, the same one as on the
UNO R4:

```cpp
CAN.begin(CanBitRate::BR_500k);
uint8_t data[] = {1, 2, 3};
CAN.write(CanMsg(CanStandardId(0x123), sizeof(data), data));
while (CAN.available()) {
  CanMsg msg = CAN.read();
  Serial.println(msg);
}
```

It's backed by `gateware/src/can_ctrl.v`, a compact CAN 2.0A/B controller
written for this core:

- Standard (11-bit) and extended (29-bit) data frames; remote frames are
  received too (with zeroed data, since `CanMsg` can't mark them).
- Bit timing with hard and soft resynchronization, bit stuffing, CRC-15
  and arbitration. A node that loses arbitration retries automatically,
  and so does one whose frame hits an error.
- ACK, bit, stuff, CRC and form error detection with error frames, the
  TEC/REC error counters, error-passive and bus-off states, and bus-off
  recovery after 128 x 11 recessive bits.
- Not implemented: overload frames. A dominant bit anywhere in the
  intermission is taken as a start of frame.

Enabling it costs about 2,500 LUT4s, roughly 12% of the chip (see
[Building: FPGA resource usage](BUILDING.md#fpga-resource-usage)).

It needs an external 3.3V CAN transceiver, such as an SN65HVD230, whose
TXD/RXD go to two GPIO pins: GPIO18 (TX, FPGA pin 71) and GPIO11 (RX,
pin 76) by default. `CAN.setPins(tx, rx)` before `begin()` picks others,
since the pins are routed at run time. Avoid pins claimed by another
Tools option, such as SPI2 or PWM Audio. `CAN.setLoopback(true)` connects
TX to RX inside the FPGA and acknowledges its own frames, a self-test
that needs no transceiver (see `libraries/CAN/examples/CANLoopback`).

Bit rates are the API's 125k/250k/500k/1M. `begin()` returns false if the
rate can't be made exactly from the system clock: 1 Mbit/s needs the 27 or
54MHz clock, not Low Power (13.5MHz). The sample point is at about 80%.
The controller holds one outgoing frame: `write()` waits up to about
three frame times for the previous one to leave, then returns -1 (still
pending, for example because no other node acknowledges it), -2 when bus
off, or 1 when queued. Received frames move from the controller's 8-frame
FIFO into a 32-frame software buffer from an interrupt (`irq[7]`), so
`loop()` needn't keep up with a busy bus. `overflow()` reports dropped
frames, and `txErrorCount()`/`rxErrorCount()`/`isErrorPassive()`/
`isBusOff()` expose the error state.

`tools/sim/tb_can.v` checks three controllers on one bus against
reference bitstreams from an independent encoder, covering arbitration,
errors, bus-off and loopback. See `libraries/CAN/examples/CANSendReceive`.

## Heap / `malloc`

The board's GW2AR-18 package has an **embedded** 64Mbit (8MB, 32-bit bus)
SDR SDRAM — not a separate chip, so it needs no `IO_LOC` pin constraints
(it's fixed internal package bonding), but it does need its own PLL-derived
clock (see [Clock architecture](#clock-architecture)). `gateware/src/sdram.v`
(vendored, see [Licensing](LICENSING.md)) is the controller;
`gateware/src/sdram_bus.v` bridges picorv32's word-oriented bus to its
byte-oriented interface and handles periodic refresh.
`cores/tangnano20k/tangnano20k_malloc.c` implements
`malloc()`/`free()`/`calloc()`/`realloc()` — a small first-fit, address-
sorted free list with coalescing (this is `-nostdlib`, so there is no libc
heap unless we provide one) — backed by that 8MB region. The internal
64KB block-RAM (program/data/stack) is **not** part of this heap. See
`libraries/Core/examples/MallocTest`. With Tools > Boot Mode: ... +
SDRAM, the heap starts after the code image at the bottom of the SDRAM
(see [Code in SDRAM](#code-in-sdram)).

## AI accelerator

`#include <AIAccelerator.h>` (`libraries/AIAccelerator/`), select
**Tools > AI Accelerator: Enabled** (disabled by default for its LUT and
block RAM cost). Without that selection `AIAccelerator.h` stops the build
with an `#error`, because the engine's registers aren't in the bitstream.
Code that only uses the engine when it's there can check the
`TANGNANO20K_AI_ACCEL` define (`0` or `1`, see
[Preprocessor defines](ARCHITECTURE.md#preprocessor-defines)) and
include the header only when it's `1`. [TinyTTS](https://github.com/pschatzmann/TinyTTS)
does that to run its INT8 dot products on the engine.

This is the compute engine from the standalone
[NanoTangAI](https://github.com/pschatzmann/NanoTangAI) project (same
author, Apache-2.0) - a row-parallel, lane-parallel INT8 dot-product
engine sized for TinyTTS's decoder (8 weight-tile rows, up to 16 taps,
1KB per row) - but integrated directly onto this core's own
picorv32 bus (`gateware/src/ai_accel_bus.v`) instead of going through
NanoTangAI's original external SPI link to a *second* Tang Nano 20K board.
`gateware/src/dot_product_engine.v`, `dot_product_lane_array.v`,
`int8_mac_lane.v`, and `byte_interleave_ram.v` are vendored from that
project, with deliberate deviations so it actually fits the GW2AR-18.
As vendored, it needed about 6x the chip's LUTs and failed place & route
("no BELs remaining") even on its own:

- Its 9 activation/weight buffers (1KB each) are one 32-bit-wide block
  RAM each, instead of 16 byte-wide lane memories each too small for
  block RAM that all landed in LUT RAM.
- That means 4 parallel lanes per row instead of 16 (`ai_accel_bus.v`'s
  `LANES`/`WORDS`), so `cinPadded` only needs to be a multiple of 4.
  The multiply-accumulate phase is 4x slower, which is negligible next
  to loading weights one bus write per byte. Results are bit-identical.
- The 32 multipliers use the FPGA's `MULT9X9` DSP blocks. This yosys
  version doesn't infer Gowin DSPs and builds each 8x8 multiply from
  ~250 LUTs.
- The result memory is split per row, so each part has one write port
  and maps onto LUT RAM instead of 4096 flip-flops.

The API is a simplified, instance-based take on NanoTangAI's
`TangNanoAccelerator`: `AIAccelerator accel(cinPadded, k, rows);` sets
the tile shape at construction (instead of a separate `config()` call);
`begin()` then allocates this instance's own weight/results buffers on
the heap (constructors stay light - no allocation before `setup()`
runs); `loadWeights()` copies in the weight tile once, and `compute()`
returns the result pointer directly - no separate `getResults()` call,
and no `begin(SPIClass&, csPin, sckHz)`/`ping()`/`protocolVersion()`/
`computeDelayMicros()` at all, since there's no SPI link to manage or
probe. `compute()`'s underlying register read blocks in hardware until
the engine's `done` actually fires, rather than a software poll loop or
a delay sized from a cycle-count formula. See `libraries/AIAccelerator/examples/AIAcceleratorTest`.

**Multiple instances**: `AIAccelerator instanceA(...), instanceB(...);`
each keep their own weight tile and results buffer in heap-allocated
copies, letting a sketch juggle several weight tiles/shapes with a plain
C++ object per tile. There is only one physical engine
(`ai_accel_bus.v` isn't duplicated - real LUT/BRAM cost, same as the
Tools menu note above), so instances time-slice it: `compute()` only
re-pushes an instance's config/weights to hardware if a *different*
instance's `compute()` ran more recently - free if you stick to one
instance, one weight-tile reload if you alternate. Each instance's
`compute()` always blocks until its own result is ready before
returning, so there's no way to interleave two instances' in-flight
computations - one instance's `compute()` call fully finishes before
another instance's can start. See `libraries/AIAccelerator/examples/AIAcceleratorMultiInstanceTest`.

In RTL simulation the gateware matches a reference kernel bit for bit.

## Interrupts

picorv32 is built with `ENABLE_IRQ(1)`, `ENABLE_IRQ_QREGS(0)` (see
`gateware/src/top.v`). The IRQ entry point (`cores/tangnano20k/irq_vec.S`)
lives at a fixed low address (`PROGADDR_IRQ=0x000`); normal program
execution starts at `PROGADDR_RESET=0x400` instead of `0x000` — see
`cores/tangnano20k/link_cmd.ld`. This is adapted directly from
[YosysHQ/picorv32](https://github.com/YosysHQ/picorv32)'s own official
`firmware/start.S`/`custom_ops.S` non-QREGS register save/restore sequence
and custom-0 opcode encodings (public domain). `init()` enables
interrupts before `setup()` runs, as on other Arduino cores.

- `interrupts()`/`noInterrupts()` mask/unmask **all** maskable IRQ lines via
  picorv32's `maskirq` instruction (`cores/tangnano20k/irq_asm.S`) — like
  AVR's `sei()`/`cli()`, these aren't nesting-counted.
- `attachInterrupt(digitalPinToInterrupt(pin), callback, mode)` /
  `detachInterrupt()` work on the 21 `GPIO0`-`GPIO20` pins and `BTN1`
  (`digitalPinToInterrupt()` is the identity function on this core — the
  "interrupt number" is just the pin number, like SAMD/ESP32, not the old
  Uno-style 0/1 mapping). `mode` supports `CHANGE`, `RISING`, `FALLING`
  (not `LOW`, which needs a held-level interrupt this core doesn't
  implement). Backed by `gateware/src/extirq.v`, a small peripheral that
  watches all 22 pins for a level change each clock cycle and latches a
  sticky per-pin flag, driving picorv32's `irq[3]`; software classifies
  the edge direction by comparing the latched level against what it saw
  last time.
- `tone(pin, frequency, duration)`/`noTone(pin)` use a PWM channel (see
  [Digital I/O and PWM](#digital-io-and-pwm)) and a software timer to end
  the tone.
- `#include <TangTimer.h>` (`libraries/TangTimer/`) — a general-purpose
  one-shot/repeating callback timer: `TangTimer t; t.begin(callback,
  interval_us, repeat);`. Runs the callback in interrupt context, same as
  `attachInterrupt()`.

All of the above share one software timer engine
(`cores/tangnano20k/tangnano20k_timer.h`/`wiring_irq.cpp`) driven by
picorv32's single built-in one-shot countdown timer (`irq[0]`, the `timer`
custom instruction): each active timer's deadline is an absolute tick count
against the free-running `systick` counter (not the countdown register
itself, which is only ever armed for whichever deadline is soonest), so
timers don't drift and re-arming never needs to "peek" a decrementing
register mid-countdown. There are `TANGNANO20K_SW_TIMER_COUNT` (6) slots
total; one is reserved for `tone()` (which needs it only to end a timed
tone, or when it has to fall back to toggling the pin), leaving up to 5
concurrent `TangTimer` instances.

See `libraries/Core/examples/ButtonInterrupt`, `libraries/Core/examples/ToneTest`,
`libraries/TangTimer/examples/TangTimerBlink`.

## Software Serial

`#include <SoftwareSerial.h>` (`libraries/SoftwareSerial/`) - a
bit-banged 8N1 UART on any two of the 21 `GPIO0`-`GPIO20` pins, for a
second/third serial port beyond the hardware `Serial` when you don't
need it fast: `SoftwareSerial ss(rxPin, txPin); ss.begin(9600);`.

- **Transmit** is blocking, bit-banged against the free-running
  `systick` counter with interrupts disabled for the whole byte to keep
  timing jitter-free - the same "blocks, no software buffering"
  tradeoff as this project's other blocking peripherals.
- **Receive** is interrupt-driven: `begin()` uses `attachInterrupt()`
  (see [Interrupts](#interrupts) above) to catch the start bit's edge,
  then the ISR busy-waits to sample the remaining bits and buffers the
  completed byte - so `available()`/`read()` are non-blocking. Because
  sampling happens *inside* that interrupt handler, receiving one byte
  blocks every other interrupt (timers, `tone()`, other
  `attachInterrupt()` callbacks, DMA completion, I2S's own background
  buffering, another `SoftwareSerial` instance's start-bit edge...) for
  roughly one byte period - keep baud rates modest (9600 is a safe
  default) and avoid overlapping traffic across multiple simultaneous
  instances if you can help it. Unlike the classic Arduino
  `SoftwareSerial`, there's no shared "listening" hardware to arbitrate
  between instances - each gets its own `attachInterrupt()` slot (one
  per GPIO pin already), so multiple instances can each buffer
  independently; `listen()`/`stopListening()` here just pause/resume
  that one instance's own interrupt, kept for API familiarity.
- `overflow()` reports (and clears) whether the small receive buffer
  (16 bytes) has dropped a byte since the last call - there's no flow
  control to slow a sender down.

See `libraries/SoftwareSerial/examples/SoftwareSerialTest`.

## DMA

`#include <DMA.h>` (`libraries/DMA/`), backed by `gateware/src/dma_engine.v`
— the SoC's **first true second bus master**. Every other peripheral added
to this core is a new *slave* on picorv32's single-master bus, decoded the
same way `leds_sel`/`sram_sel`/etc. always have been; `dma_engine.v`
instead becomes bus master itself to copy memory in hardware instead of a
software loop. It has two independent modes:

- **Blocking**: `dmaCopyWords(dst, src, wordCount)` / `dmaCopy(dst, src,
  byteCount)`. Works for any address (SRAM, SDRAM, or a mix). Writing the
  `START` register hands the *entire* shared CPU request bus
  (`mem_valid`/`mem_addr`/`mem_wdata`/`mem_wstrb` in `top.v`) to the DMA
  engine, which issues its own read-then-write cycles against the same,
  unmodified address-decoded peripherals/memory every other master uses,
  while picorv32's own `mem_ready` is held low. Since picorv32 has no
  separate instruction bus, that stalls instruction fetch too — the CPU
  cannot run any other code during the transfer, and just resumes
  automatically, on the instruction after `dmaCopyWords()` returns, the
  instant the engine hands the bus back. There is nothing to poll: by the
  time any of your code after the call runs, the copy has already
  finished. This is a throughput accelerator for the copy itself, not a
  way to overlap a copy with other work. See `libraries/DMA/examples/DMACopyTest`.
- **Async**: `dmaCopyWordsAsync(dst, src, wordCount, callback)`. Returns
  immediately; `loop()` (and timers, `tone()`, `attachInterrupt()`
  callbacks, everything) keeps running normally while the copy happens in
  the background, and `callback` runs from interrupt context when it's
  done. This works by giving the async path its **own dedicated
  bus-master port straight into `gateware/src/sdram_bus.v`'s second port**
  (see that module), entirely bypassing the CPU's shared bus arbiter above
  — so it only ever reaches the embedded SDRAM heap (`dst`/`src` must both
  lie within `TANGNANO20K_SDRAM_BASE`/`TANGNANO20K_SDRAM_SIZE`;
  `dmaCopyWordsAsync()` returns `false` otherwise), and only one
  background transfer can be in flight at a time. `sdram_bus.v` arbitrates
  its one physical SDR SDRAM chip between the CPU's normal path and this
  dedicated DMA path at **word granularity** (the CPU always wins ties),
  so a long background copy never delays an ordinary CPU SDRAM access
  (e.g. a `malloc()`'d buffer touched from `loop()`) by more than the
  current in-flight word. Completion is a sticky interrupt (`irq[3]` is
  `extirq`; this is `irq[4]`), read-clear like `extirq`'s `STATUS`
  register — `dmaAsyncBusy()` polls the same register, so don't mix
  polling and the callback for the same transfer (whichever reads first
  clears it for the other). See `libraries/DMA/examples/DMAAsyncTest`, which blinks an
  LED from `loop()` throughout a 1MB background copy to make the
  difference from the blocking mode visible.

Async mode is deliberately scoped to SDRAM↔SDRAM: giving the internal SRAM
a second, independent port for true background SRAM copies too would need
true dual-port block RAM with both ports doing flexible read/write, which
this toolchain's BRAM inference cannot produce - see
[Known limitations](KNOWN_LIMITATIONS.md).

## Flash

The onboard SPI NOR flash (also used by the Gowin configuration engine to
boot the bitstream itself) is memory-mapped read-only at
`TANGNANO20K_FLASH_WINDOW_BASE` (`0x20000000`) via
`gateware/src/qspi_flash.v` - a raw window, like the SDRAM's convention
(`addr` is a byte offset within the flash chip). Layout:

| Offset | Contents |
|---|---|
| `0x000000` | Gowin bitstream |
| `0x100000` | Program partition: a 4-byte little-endian size, then the program bytes (Boot Mode: Flash only) |
| `0x110000` - end | Constant-data partition (`FLASH_DATA`), followed by the [Code in SDRAM](#code-in-sdram) image when that option is enabled |

### Boot Mode (Tools menu)

- **SRAM (default)**: the sketch is part of the bitstream, as the initial
  contents of the internal SRAM. Each upload is a new bitstream (seconds
  to build once the routed design is cached - see
  [Build times](BUILDING.md#build-times-and-the-routed-design-cache)).
- **Flash**: `cores/tangnano20k/boot.S`, a fixed stub baked into SRAM as
  part of the *core* (not the sketch), copies the sketch's program from
  the flash's program partition into SRAM at `0x400` on reset, then jumps
  there - the sketch itself is linked exactly the same way as in SRAM
  mode (same `0x400` start address, same `link_cmd.ld` layout), so nothing
  about writing a sketch changes. The board then starts the sketch by
  itself at power-up. `tools/upload.py` writes the core bitstream to
  flash (replacing whatever bitstream was stored there, e.g. the demo
  the board shipped with) and the program to the program partition, via
  `openFPGALoader -f`. The core bitstream is the same for every sketch,
  so it is built once and cached, and the upload only rewrites it when it
  changed (after a core update or a change to a gateware Tools option) -
  it remembers the last one it wrote in
  `~/.cache/nanotang/flashed_bitstream.sha256`. If the flash was changed
  by other means, or for another board, upload with
  `NANOTANG_FORCE_BITSTREAM=1` set to write it anyway.
  The SRAM modes never change the bitstream in flash: after a power
  cycle, the board boots whatever is stored there.
- **SRAM + SDRAM** / **Flash + SDRAM**: the same two modes for sketches
  larger than the 64KB SRAM - code off the hot path runs from the
  embedded SDRAM instead, see [Code in SDRAM](#code-in-sdram).

### Constant data (`FLASH_DATA`)

Independent of Boot Mode - available in either setting. Mark a big
`const` array with the `FLASH_DATA` attribute
(`cores/tangnano20k/tangnano20k_soc.h`) to place it in the flash's
constant-data partition instead of the 64KB internal SRAM:

```cpp
const uint8_t bigTable[4096] FLASH_DATA = { ... };
```

`PROGMEM`, the usual Arduino spelling, is an alias for `FLASH_DATA`, so
existing AVR-style code works unchanged: `const uint8_t table[] PROGMEM
= {...};` lands in flash too, and `pgm_read_byte()`/`memcpy_P()` etc.
work as plain reads. `PSTR()`/`F()` strings are *not* moved; they stay
in SRAM. Libraries that use `PROGMEM` also put their tables in flash,
which saves SRAM at the cost of slower reads (see below).

Reads happen through ordinary array/pointer syntax - no special API -
blocking via the same bus backpressure every other peripheral in this
design uses. By default every 32-bit read is one SPI transaction, about
510 system clocks. **Tools > Flash Cache: Enabled** adds a 512-byte read
cache (16 lines of 32 bytes, a valid bit per word,
`gateware/src/qspi_flash_cached.v`) at a cost of ~1,700 LUT4s (~8% of
the FPGA):

| Access | Without cache | With cache |
|---|---|---|
| Repeated (e.g. a small table read in a loop) | ~510 | ~2 |
| Sequential (streams to the end of the 32-byte line) | ~510 | ~290 |
| Scattered, not cached | ~510 | ~510 |

With the cache, a lookup table up to about 512 bytes costs almost
nothing after its first pass, and Boot Mode: Flash copies the program
about 1.8x faster. Without it, copy hot data to SRAM or SDRAM first. `tools/build_bitstream.py`
extracts the `.flash_data`
section's raw bytes from the compiled ELF; `tools/upload.py` writes them
to the flash's data partition as part of every upload, in either boot
mode. See `libraries/Core/examples/FlashDataTest`.

### Code in SDRAM

Code, constants, variables and stack normally all share the 64KB
internal SRAM. For sketches that don't fit, such as an MP3 player built
on audio-tools, SD and the helix decoder (about 125KB), select **Tools >
Boot Mode: SRAM + SDRAM** (or **Flash + SDRAM**, which adds the fast
uploads of Boot Mode: Flash). The sketch is then linked with
`cores/tangnano20k/link_cmd_sdram.ld`:

- **Kept in SRAM**: the core (interrupt dispatch, timing, digital I/O),
  libgcc's integer and single-precision `float` helpers, the helix MP3
  decoder, and the bundled I2S, PWMAudio, SPI, Wire, SoftwareSerial,
  DMA, TangTimer, Servo, WS2812, CAN and AIAccelerator libraries. The
  linker places code by library, so the timing-sensitive code keeps its
  speed.
- **Moved to SDRAM**: all other code and constants (the sketch itself,
  other libraries, `double` math, strings), up to 1MB. Variables and
  the stack stay in SRAM.

Override the placement per function with `SRAM_CODE` (keep it in SRAM,
for example an interrupt callback in the sketch) or `SDRAM_CODE` (move
it out), both from `cores/tangnano20k/tangnano20k_soc.h`:

```cpp
SRAM_CODE void onTimer() { ... }
```

How it works: SDRAM is empty at power-up, and the bitstream can only
preload the block RAM. So the SDRAM part is stored in the flash's
constant-data partition (`tools/build_bitstream.py` adds it to
`data.bin`, `tools/upload.py` writes it before the program), and
`startup.S` copies it into SDRAM on reset, before any constructor runs.
The heap (see [Heap / `malloc`](#heap--malloc)) then starts after it.

Costs:

- **Speed**: code in SDRAM runs about 2.4x slower than in SRAM (every
  instruction fetch is an SDRAM access; measured on the board at 27MHz
  with `libraries/Core/examples/SdramCodeTest`). Fine for setup, file
  handling and logging; keep hot loops in SRAM.
- **Boot time**: the copy reads the flash at about 510 clocks per word
  (fewer with Flash Cache), about 0.15s for a 64KB image at 54MHz.
- **Flash writes**: every upload writes the image to the flash, in
  either Boot Mode.
- The "program storage" size the IDE reports only counts the SRAM part.

## CPU features

Hardware Multiply/Divide is enabled by default; Barrel Shifter and
Compressed Instructions are disabled. Measured on the board with a
benchmark (20,000 operations each, 27MHz), each option against a
baseline with all three disabled:

| | Integer divide | Integer multiply | `float` math | Shifts |
|---|---|---|---|---|
| All three disabled | 567ms | 611ms | 1,516ms | 42ms |
| Hardware Multiply/Divide | 9.5x faster | 19.6x faster | 1.6x faster | - |
| Barrel Shifter | 8% faster | 7% faster | 15% faster | 17% faster |
| Compressed Instructions | same | same | same | same |

The 54MHz clock (Tools > Clock Speed) halves every figure.

**Tools > Hardware Multiply/Divide** enables picorv32's M-extension
(`ENABLE_MUL`/`ENABLE_DIV`/`ENABLE_FAST_MUL` in `top.v`) instead of
software-emulated integer multiply/divide. This speeds up every integer
`*`/`/`/`%`, and indirectly `float`/`double` math, since libgcc's
software floating-point routines are built from integer multiplies and
shifts (there's no FPU - see [Known limitations](KNOWN_LIMITATIONS.md)).
The compiler flag (the `m` in `-march=rv32im_zicsr_zifencei`) and the
gateware always change together from this one menu choice - never set
independently, since a sketch compiled expecting hardware `mul`/`div`
would execute an illegal instruction on a bitstream built without this
enabled.

**Tools > Compressed Instructions** enables the
RISC-V "C" extension (`COMPRESSED_ISA` in `top.v`, plus the `c` in
`-march`, again always together). Many instructions get a 16-bit
encoding: a sketch using Serial, SPI, Wire, Servo and WS2812 went from
26.2KB to 21.6KB of code (about 18% smaller) - the option to reach for
when a sketch gets close to the 64KB SRAM limit. It costs some LUTs,
but no measurable speed. libgcc stays the uncompressed build (the toolchain has no
RV32IC variant), which a C-capable CPU runs unchanged.

**Tools > Barrel Shifter** makes every shift a
single-cycle operation (`BARREL_SHIFTER` in `top.v`) instead of one cycle
per bit position. It's gateware only - no compiler change. Shifts are
everywhere (bit manipulation, CRCs, fixed-point math, and libgcc's
software floating-point routines), so this speeds up more than it sounds,
for a few hundred LUTs.

## Clock architecture

The system clock is derived from the board's fixed 27MHz oscillator (pin
4) through an on-chip PLL (`Gowin_rPLL_sys`, vendored from `nestang`'s
configuration) — **no one-time board setup is needed**. The PLL's
phase-shifted second output clocks the embedded SDRAM.

The output frequency is selectable via **Tools > Clock Speed**:

| Option | Frequency | Notes |
| --- | --- | --- |
| Normal (default) | 27 MHz | |
| Low Power | 13.5 MHz | Roughly half the dynamic power; sketches run half as fast, and CAN can't reach 1 Mbit/s |
| Overclocked | 54 MHz | Twice as fast. Routing closes at 67-80MHz for every measured configuration (see [FPGA resource usage](BUILDING.md#fpga-resource-usage)) and the SDRAM controller is rated to 66.7MHz |

Every option regenerates both the PLL's dividers (`gowin_rpll_sys.v`) and
`sys_parameters.v`'s `CLK_FREQ` together (see `tools/build_bitstream.py`),
so UART baud rate, I2S sample rate, SPI clock, `millis()`/`micros()`, and
the SDRAM/WS2812 timing derived from `CLK_FREQ` in `top.v` all stay
consistent with whichever frequency is selected.
