# Architecture

```
sketch.ino ──arduino-cli/IDE──> RISC-V ELF (cores/tangnano20k + api/)
                                      │
                     tools/build_bitstream.py
                                      │
                    elf → bin → SRAM $readmemh init files
                                      │
                 yosys → nextpnr-himbaechel → gowin_pack
                 (or: program patched into a cached routed design → gowin_pack)
                                      │
                                  prog.fs
                                      │
                         tools/upload.py (openFPGALoader)
                                      │
                              Tang Nano 20K
```

- `gateware/` — the PicoRV32-based SoC (forked from
  [grughuhler/picorv32_tang_nano_20k](https://github.com/grughuhler/picorv32_tang_nano_20k)),
  extended with: a free-running `systick` peripheral (`millis()`/
  `micros()` counters that wrap at the full 2^32, like on AVR), RX/TX
  FIFOs in front of the UART, `i2s` (MAX98357A audio, plus an optional receive path for
  an external I2S microphone), `pwm_bank` (`analogWrite()`/`analogWriteFrequency()` on the
  LEDs and GPIO pins), `spi_master` and `od_gpio2` (bit-banged I2C), `gpio_bank`
  (general-purpose expansion-header GPIO), `ws2812_strip` (the
  onboard addressable RGB LED and external WS2812 strips), `can_ctrl`
  (CAN bus, Tools > CAN), `extirq` (pin-change source for
  `attachInterrupt()` — see [Interrupts](PERIPHERALS.md#interrupts)),
  `dma_engine` (the SoC's second bus master, see
  [DMA](PERIPHERALS.md#dma)),
  `qspi_flash` (the onboard SPI flash - boot mode and constant data, see
  [Flash](PERIPHERALS.md#flash)),
  `ai_accel_bus`/`dot_product_engine` (the
  optional [AI accelerator](PERIPHERALS.md#ai-accelerator)), and
  `sdram`/`sdram_bus` (the embedded 8MB heap) plus the
  `Gowin_rPLL_sys` PLL that clocks it all from the board's fixed 27MHz
  oscillator.
- `cores/tangnano20k/` — the Arduino core runtime: startup code, linker
  script, `HardwareSerial`, digital/analog I/O, timing, `malloc`. This is
  what every sketch links against; kept deliberately minimal given the
  64KB internal SRAM budget. Implements the interfaces from
  [arduino/ArduinoCore-API](https://github.com/arduino/ArduinoCore-API)
  (vendored under `cores/tangnano20k/api/` — see
  [Updating the vendored ArduinoCore-API](UPDATING_ARDUINOCORE_API.md)).
- `libraries/` — bundled libraries (`SPI`, `Wire`, `I2S`, `PWMAudio`,
  `SD`, `CAN`, `AIAccelerator`, `WS2812`, `Servo`, `TangTimer`, `DMA`,
  `SoftwareSerial`), plus `Core` for the core's own examples. As on other
  Arduino cores, a sketch only links in the ones it `#include`s.
- `variants/tangnano20k/` — pin definitions.
- `tools/` — the FPGA build (`build_bitstream.py`), SRAM-init generation
  (`gen_mem_init.py`), upload (`upload.py`), ArduinoCore-API vendoring
  (`vendor_arduino_api.sh`), verification (`run_tests.sh`, `sim/`) and
  release packaging (`package/`) scripts.
- `boards.txt` / `platform.txt` — the Arduino board definition.

## Preprocessor defines

Set unconditionally by `build.defines` in [`platform.txt`](../platform.txt)
for every sketch compiled against this board:

| Define                  | Source                                              |
|--------------------------|------------------------------------------------------|
| `ARDUINO_TANGNANO20K`    | `-DARDUINO_{build.board}`, from `tangnano20k.build.board=TANGNANO20K` in [`boards.txt`](../boards.txt) |
| `ARDUINO_ARCH_TANGNANO20K` | architecture-level define, always set alongside the board one |
| `TANGNANO20K_SPI_COUNT`  | `0`, `1` (default), or `2` - mirrors **Tools > SPI Buses**' `build.spi_count`, see [A second SPI + I2C port](PERIPHERALS.md#a-second-spi--i2c-port) |
| `TANGNANO20K_I2C_COUNT`  | `0`, `1` (default), or `2` - mirrors **Tools > I2C Buses**' `build.i2c_count`, same menu |
| `TANGNANO20K_PWM_AUDIO`  | `0` (default) or `1` - mirrors **Tools > PWM Audio**' `build.pwm_audio`, see [Audio (PWM)](PERIPHERALS.md#audio-pwm) |
| `TANGNANO20K_AI_ACCEL`   | `0` (default) or `1` - mirrors **Tools > AI Accelerator**' `build.ai_accel`, see [AI accelerator](PERIPHERALS.md#ai-accelerator) |

Use `#ifdef ARDUINO_TANGNANO20K` to guard code specific to this board, e.g.:

```cpp
#ifdef ARDUINO_TANGNANO20K
  // Tang Nano 20K-specific code
#endif
```

`ARDUINO_ARCH_TANGNANO20K` is the broader check, for code that should apply
to any board sharing this architecture, should one ever exist alongside
the Tang Nano 20K.

`TANGNANO20K_SPI_COUNT`/`TANGNANO20K_I2C_COUNT` let a sketch check at
compile time whether `SPI2`/`Wire2` were actually built into the gateware,
instead of silently talking to a port that reads back 0/no-ops:

```cpp
#if TANGNANO20K_I2C_COUNT >= 2
  Wire2.begin();
#else
  #error "This sketch needs Tools > I2C Buses: Two"
#endif
```

Also set when the corresponding `Tools >` menu option is enabled (see
[boards.txt](../boards.txt)'s `menu.*` entries): `TANGNANO20K_SD_ENABLED`
(SD card wiring).

## Memory map

| Address                     | Peripheral                                        |
|------------------------------|---------------------------------------------------|
| `0x0000_0000`                | Internal SRAM (64KB: program + data + stack)       |
| `0x8000_0000`                | LEDs, bits `[5:0]`, read/write                     |
| `0x8000_0004`                | UART status: RX FIFO count, TX FIFO free, TX idle, RX overflow (read) |
| `0x8000_0008`                | UART clock divisor register                        |
| `0x8000_000C`                | UART data register (64-byte RX / 32-byte TX FIFOs) |
| `0x8000_0010`-`0x8000_0018`  | LED SET/CLR/TOGGLE (write 1 bits to act)           |
| `0x8000_0020`                | `systick` free-running 32-bit cycle counter        |
| `0x8000_0024`                | `systick` microsecond counter (`micros()`)         |
| `0x8000_0028`                | `systick` millisecond counter (`millis()`)         |
| `0x8000_0040`                | I2S BCLK phase increment register (write)          |
| `0x8000_0044`                | I2S transmit data register: `{left16,right16}` (write) |
| `0x8000_0048`                | I2S control register: bit0 = PA_EN (write)         |
| `0x8000_004C`                | I2S receive data register: `{left16,right16}` (read, blocks - Tools > I2S Input only) |
| `0x8000_0050`                | KEY_S2 button, bit0, read-only                     |
| `0x8000_0080`                | SPI SCLK divisor register (write) - Tools > SPI Buses: One+ only |
| `0x8000_0084`                | SPI CS register: bit0 = asserted (write) - Tools > SPI Buses: One+ only |
| `0x8000_0088`                | SPI data register (read/write) - Tools > SPI Buses: One+ only |
| `0x8000_0090`                | I2C open-drain SDA/SCL: write=drive low, read=level - Tools > I2C Buses: One+ only |
| `0x8000_00A0`                | SPI2 SCLK divisor register (write) - Tools > SPI Buses: Two only |
| `0x8000_00A4`                | SPI2 CS register: bit0 = asserted (write) - Tools > SPI Buses: Two only |
| `0x8000_00A8`                | SPI2 data register (read/write) - Tools > SPI Buses: Two only |
| `0x8000_00B0`                | I2C2 open-drain SDA/SCL - Tools > I2C Buses: Two only |
| `0x8000_00C0`-`0x8000_00C8`  | GPIO OUT SET/CLR/TOGGLE (write 1 bits to act)      |
| `0x8000_00D0`-`0x8000_00D4`  | GPIO DIR SET/CLR (write 1 bits to act)             |
| `0x8000_00E0`-`0x8000_00F8`  | CAN controller - Tools > CAN only (see `can_ctrl.v`) |
| `0x8000_0100`                | GPIO direction register (bits [20:0], 1=output)    |
| `0x8000_0104`                | GPIO output register (bits [20:0])                 |
| `0x8000_0108`                | GPIO input register (bits [20:0], read-only)       |
| `0x8000_0110`                | WS2812: write queues a `{G[7:0],R[7:0],B[7:0]}` pixel; read bit0 = busy |
| `0x8000_0114`                | WS2812 config: route output to a GPIO pin         |
| `0x8000_0120`                | External-interrupt ENABLE register (bits [21:0], see [Peripherals](PERIPHERALS.md#interrupts)) |
| `0x8000_0124`                | External-interrupt STATUS register (read-clears)   |
| `0x8000_0128`                | External-interrupt LEVEL register (read-only)      |
| `0x8000_0130`-`0x8000_013C`  | DMA SRC/DST/LEN/START registers (see [Peripherals](PERIPHERALS.md#dma)) |
| `0x8000_0140`-`0x8000_015C`  | AI accelerator registers (see [Peripherals](PERIPHERALS.md#ai-accelerator)) |
| `0x8000_0160`                | I2S IRQ_ENABLE: bit0=TX FIFO at most half full, bit1=RX data (read/write, see [Peripherals](PERIPHERALS.md#audio-i2s)) |
| `0x8000_0164`                | I2S STATUS: bits[4:0]=TX FIFO free slots, bits[9:5]=RX FIFO count (read-only) |
| `0x8000_0170`-`0x8000_017C`  | PWM audio PERIOD/SAMPLE_DIV/DATA/CTRL (Tools > PWM Audio only - see [Peripherals](PERIPHERALS.md#audio-pwm)) |
| `0x8000_0180`-`0x8000_01AC`  | PWM DUTY/CFG register pairs, 6 channels, each routable to any LED or GPIO pin (see `pwm_bank.v`) |
| `0x1000_0000`-`0x107f_ffff`  | Embedded SDRAM, 8MB (heap - see [Peripherals](PERIPHERALS.md#heap--malloc)) |
| `0x2000_0000`-`0x207f_ffff`  | Onboard SPI flash, memory-mapped read-only (boot/constant data - see [Peripherals](PERIPHERALS.md#flash)) |

## Gateware notes

Toolchain details that matter when changing the gateware:

- **yosys 0.33 (what Linux distributions ship) maps block RAMs so they
  never return data on the real chip**: it ties each block RAM's output
  clock enable (`OCE`) low. `tools/build_bitstream.py` drives `OCE` from
  the read enable after synthesis (`fix_bram_oce()`); other flows using
  this gateware with yosys 0.33 need the same fix. Newer yosys versions
  (2024 onwards) are fine.
- **Bidirectional pins must use the plain `assign pin = en ? d : 1'bz;`
  form.** yosys 0.33 builds an output-only buffer from anything more
  nested, and the pin can then never be read.
- **`gateware/src/sram8bit.v`'s memory needs its `(* ram_style = "block"
  *)` attribute** to map onto block RAM; without it yosys picks LUT-based
  distributed RAM, which doesn't fit.
- **A memory's ready signal must pulse once per access.** picorv32 with
  Compressed Instructions keeps `mem_valid` high and moves straight on to
  the next address for the second half of an unaligned 32-bit
  instruction; a ready that simply follows the select signal hands it the
  previous word.
- **The embedded SDRAM's pins are placed by name**: nextpnr's Gowin
  backend recognizes the top-level ports `O_sdram_clk`, `O_sdram_cke`,
  `O_sdram_cs_n`, `O_sdram_cas_n`, `O_sdram_ras_n`, `O_sdram_wen_n`,
  `O_sdram_dqm[3:0]`, `O_sdram_addr[10:0]`, `O_sdram_ba[1:0]` and
  `IO_sdram_dq[31:0]` (see
  [YosysHQ/nextpnr#1370](https://github.com/YosysHQ/nextpnr/pull/1370));
  they aren't in the `.cst` file. Renaming them breaks place & route with
  `ERROR: Unconstrained IO:...`.
- **Tools > Boot Mode: Flash caches one bitstream per option
  combination**, which only works because the core's SRAM image is
  identical for every sketch: `irq_vec.S` calls the sketch's interrupt
  dispatcher through a fixed pointer slot (`irq_dispatch_ptr`) rather than
  a direct call, whose encoding would depend on where the dispatcher
  links.
