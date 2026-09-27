# Hardware test status

What has been verified on a real board and what hasn't yet. For
limitations found on the board, see [Known limitations](KNOWN_LIMITATIONS.md).

Tested on a Sipeed Tang Nano 20K (GW2AR-LV18QN88C8/I7, onboard BL616
debugger firmware 2025030317) in September 2026, with Boot Mode: SRAM,
yosys 0.33, nextpnr-himbaechel 0.11.1 and apicula 0.33. Unless a row says
otherwise, the other Tools options were at their defaults.

## Verified on the board

| Feature | How it was tested |
|---|---|
| Boot, CPU, C++ startup | Test sketches run `setup()`/`loop()`, including ones with several global constructors |
| Program memory (64KB SRAM) | Hardware self-test reading all 16,384 words of the block RAM |
| `Serial` output | `print()`/`println()` with every argument type (integers, `HEX`/`BIN`/`OCT`, floats, `String`), `printf()` including `%f` |
| `Serial` input | Bursts of up to 128 bytes received completely; `overflow()` stays clear (but see [the USB bridge limitation](KNOWN_LIMITATIONS.md)) |
| `millis()`/`micros()`/`delay()` | Checked against each other over several seconds |
| C++ exceptions (Tools > C++ Exceptions: Enabled) | `libraries/Core/examples/ExceptionTest`: throw/catch by value and base class, `what()`, unwinding through 6 frames with destructors, rethrow, `std::out_of_range` from `vector::at()`, `std::bad_alloc` from a failed 64MB `new`, `catch (...)` - all pass |
| SDRAM heap | A pattern over every word of the 8MB; word, halfword and byte access; a 64KB `malloc` pattern test; `new[]`/`delete[]`; unaligned `memcpy()` |
| SPI and the SD card | `SD.begin()`, writing a 2KB file, reading it back: 0 mismatches |
| I2S audio (onboard MAX98357A) | A clean continuous 440Hz sine at 44.1kHz (written in blocks of 64 frames); 22.05kHz square waves |
| `digitalRead()` and `attachInterrupt()` | The KEY2 button (`BTN1`): reads 1 while pressed, 0 released, one interrupt per change; the reset button restarts the SoC |
| Onboard LEDs | `digitalWrite()`; LED1-LED5 fade smoothly with `analogWrite()` |
| GPIO inputs, pull-ups, `OUTPUT_OPENDRAIN` | An unconnected pin reads HIGH with `INPUT_PULLUP`; open-drain drives LOW and releases HIGH |
| `analogWrite()`/PWM, `analogWriteResolution()`, `pulseIn()` | 1kHz at 25% measured 247/745us high/low with `pulseIn()` on the pin itself; 12-bit 50% measured 500us |
| `tone()` | 2kHz measured 247us half-periods; a 100ms tone stops on time; `tone(LED0, 2, 3000)` blinks and stops by itself |
| `attachInterrupt()` on a GPIO | 200 rising edges counted from a 1kHz PWM in 200ms |
| `Servo` | `write(90)` measured a 1469us pulse (1472 expected) |
| `TangTimer` | A 10ms periodic callback fired 99 times per second |
| DMA | Blocking SRAM/SDRAM copies and a background SDRAM copy with its completion callback, data verified |
| `Wire` (I2C) | A scan with nothing attached finds nothing and finishes in 35ms (no device tested yet) |
| Onboard WS2812 LED | `WS2812.write()` shows red, green, blue and white correctly |
| CAN (Tools > CAN) | Internal loopback mode: frames sent and received back (no transceiver) |
| Hardware Multiply/Divide, Barrel Shifter, Compressed Instructions, 54MHz clock | A benchmark runs correctly with each; results in [CPU features](PERIPHERALS.md#cpu-features). At 54MHz `Serial` and the timers keep the right speed |
| AI accelerator | A dot product of all-ones vectors returns the expected 32 per tap |
| Boot Mode: SRAM, SRAM + SDRAM, Flash + SDRAM | Sketches start in each mode; with Flash + SDRAM the sketch starts again by itself after unplugging and replugging the board (core bitstream and program in flash). Flash starts Blink after the upload |
| Code in SDRAM (Boot Mode: SRAM + SDRAM) | `SdramCodeTest`: the image is copied from flash into SDRAM at reset, a function runs from there with the same result as its SRAM copy (2.4x slower at 27MHz), and the heap starts after the image |

## Not yet tested on the board

- WS2812 strips on a GPIO (the onboard LED works)
- `Wire` talking to a real I2C device, and the second SPI/I2C bus
- `SoftwareSerial` (needs a jumper wire), CAN on a real bus (needs a
  transceiver), PWM Audio, I2S input
- The AI accelerator with signed and mixed values (only an all-ones test so far)
- `FLASH_DATA` constants on their own (the flash data partition itself
  works - see Boot Mode: SRAM + SDRAM above)
- Tools > Boot Mode: Flash starting the sketch after a power cycle (the
  same mechanism works with Flash + SDRAM, see above)
- The 13.5MHz clock

## Testing on the board yourself

- Load a bitstream into the FPGA's RAM (temporary; a power cycle restores
  what's in the flash): `openFPGALoader -b tangnano20k prog.fs`. If a
  load hangs at "Erase SRAM" (seen after an interrupted load), reset the
  FPGA with `openFPGALoader -b tangnano20k -r` and load again.
- `Serial` is the board's second USB serial port (see
  [Known limitations](KNOWN_LIMITATIONS.md)).
- After the first build for a set of Tools options, test builds take
  seconds - see [Building: build times](BUILDING.md#build-times-and-the-routed-design-cache).
