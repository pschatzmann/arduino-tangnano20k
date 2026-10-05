# Building, installing, and verifying

## Prerequisites

- **RISC-V compiler**: any bare-metal `rv32i2p0`/`ilp32`-capable GCC.
  Installing via [Boards Manager](#installing-via-boards-manager) gets you
  one automatically (a Zephyr SDK `riscv64-zephyr-elf-gcc`, which is
  multilib and supports rv32i) for Linux x86_64, macOS Intel/Apple
  Silicon, or Windows 64-bit - see [Releasing](RELEASING.md) for how those
  archives are produced. Installing manually (below), you
  need one yourself; override `compiler.path`/`compiler.prefix` in a
  `platform.local.txt` next to `platform.txt` if yours lives elsewhere or
  uses a different prefix (e.g. `riscv32-unknown-elf-`).
- **FPGA tools**: yosys (synthesis), nextpnr-himbaechel with the Gowin
  backend (place & route), [Apicula](https://github.com/YosysHQ/apicula)'s
  `gowin_pack` (bitstream) and openFPGALoader (programming the board over
  USB). Installing via Boards Manager gets you all four automatically, as
  the `oss-cad-suite-gowin` tool: the parts of a
  [YosysHQ oss-cad-suite](https://github.com/YosysHQ/oss-cad-suite-build)
  build this flow needs, pinned to the version the gateware was tested
  with (`fpga_tools.path` in `platform.txt`; see [Releasing](RELEASING.md)).
  Installing manually, you need them yourself - the easiest way is to
  unpack a full oss-cad-suite to `~/oss-cad-suite`. yosys 0.33 (what Linux
  distributions ship) through 0.69 are known to work; nextpnr must be
  built with `-DARCH=himbaechel` (distributions' `nextpnr-gowin` is the
  old, unsupported backend).
- **Python 3** (used by `tools/*.py`) and **bash** (`tools/run_tests.sh`).

`tools/find_tool.py` looks each FPGA tool up in this order: its environment
variable (`YOSYS`, `NEXTPNR_HIMBAECHEL`, `GOWIN_PACK` or `OPENFPGALOADER`,
set to the program's full path), the Boards Manager `oss-cad-suite-gowin`
tool, PATH, and the usual install folders (`~/oss-cad-suite/bin`,
`~/.local/bin`, `~/miniconda3/bin`, `~/miniforge3/bin`, `~/anaconda3/bin`,
`/opt/oss-cad-suite/bin`, ...) - the Arduino IDE started from the desktop
does not read `~/.bashrc`, so a tool that is only on PATH through a line
there or a conda/venv activation is invisible to it. For `gowin_pack` it
also tries `python3 -m apycula.gowin_pack` before those folders.

## Installing via Boards Manager

Once a release is published (see [Releasing](RELEASING.md)), add this URL
under Arduino IDE's Preferences > "Additional Boards Manager URLs" (or
`arduino-cli`'s `--additional-urls`):

```
https://raw.githubusercontent.com/pschatzmann/arduino-tangnano20k/main/package_nanotang_index.json
```

Then install `nanotang:tangnano20k` from Boards Manager (IDE) or:

```sh
arduino-cli core update-index --additional-urls <url above>
arduino-cli core install nanotang:tangnano20k --additional-urls <url above>
```

This installs the board files *and* a working RISC-V compiler (Linux
x86_64, macOS Intel/Apple Silicon, or Windows 64-bit) with no other manual
steps.

## Installing manually (for development, or before a release exists)

Arduino-cli/IDE discover third-party hardware under
`<sketchbook>/hardware/<vendor>/<architecture>/`. Symlink (or copy) this
repo into place, e.g.:

```sh
mkdir -p ~/Arduino/hardware/nanotang
ln -s /path/to/arduino-tangnano20k ~/Arduino/hardware/nanotang/tangnano20k
```

Then the board is available as FQBN `nanotang:tangnano20k:tangnano20k`:

```sh
arduino-cli compile --fqbn nanotang:tangnano20k:tangnano20k libraries/Core/examples/Blink
arduino-cli upload  --fqbn nanotang:tangnano20k:tangnano20k -p /dev/ttyUSB1 libraries/Core/examples/Blink
```

(`-p` is required by arduino-cli's CLI parsing but unused by the upload
recipe, which always targets the board via `openFPGALoader -b tangnano20k`.)

## Tools menus

`boards.txt` exposes these Tools menus (in the IDE) / FQBN suffixes (on
the CLI). Combine as many as needed, e.g.:

```sh
arduino-cli compile --fqbn nanotang:tangnano20k:tangnano20k:optimize=fastest,sd_card=enabled libraries/SD/examples/SDReadWrite
```

Options that add gateware cost LUTs whether or not a sketch uses them
(see [FPGA resource usage](#fpga-resource-usage)), so they're all off by
default. The first build after changing any gateware option takes a full
FPGA flow (see [Build times](#build-times-and-the-routed-design-cache)).

| Menu | FQBN key: values (default first) | What it does |
|---|---|---|
| Optimize | `optimize`: `small` (`-Os`), `fast` (`-O2`), `fastest` (`-O3`), `debug` (`-Og -g`) | Compiler optimization. The whole program has to fit in 64KB of SRAM, so `-O2`/`-O3` can push a large sketch over; debug info costs no SRAM |
| Clock Speed | `f_cpu`: `normal` (27MHz), `low_power` (13.5MHz), `overclock` (54MHz) | [Clock architecture](PERIPHERALS.md#clock-architecture) |
| Boot Mode | `boot_mode`: `sram`, `flash`, `sram_sdram`, `flash_sdram` | Run the sketch from SRAM baked into the bitstream, or boot it from the onboard flash; the `_sdram` variants also put code off the hot path in SDRAM for sketches larger than the 64KB SRAM - see [Flash](PERIPHERALS.md#flash) and [Code in SDRAM](PERIPHERALS.md#code-in-sdram) |
| SPI Buses / I2C Buses | `spi_buses`, `i2c_buses`: `one`, `none`, `two` | Remove the port, or add `SPI2` (GPIO0-3) / `Wire2` (GPIO4-5) - see [SPI, I2C](PERIPHERALS.md#spi-i2c-wire-and-the-sd-card) |
| SD Card | `sd_card`: `disabled`, `enabled` | Allows `SD.h` to compile; it's GPLv3 - see [SD card](PERIPHERALS.md#sd-card). No gateware change |
| I2S Input | `i2s_rx`: `disabled`, `enabled` | Microphone input on `GPIO6` - see [Audio (I2S)](PERIPHERALS.md#audio-i2s) |
| PWM Audio | `pwm_audio`: `disabled`, `enabled` | Audio output on `GPIO16`/`GPIO17` - see [Audio (PWM)](PERIPHERALS.md#audio-pwm) |
| CAN | `can`: `disabled`, `enabled` | CAN controller, pins chosen at run time - see [CAN](PERIPHERALS.md#can) |
| AI Accelerator | `ai_accel`: `disabled`, `enabled` | INT8 dot-product engine - see [AI accelerator](PERIPHERALS.md#ai-accelerator) |
| Flash Cache | `flash_cache`: `disabled`, `enabled` | 512-byte cache for flash reads - see [Flash](PERIPHERALS.md#flash) |
| Hardware Multiply/Divide | `hw_muldiv`: `enabled`, `disabled` | RV32IM CPU and compiler flags, together - see [CPU features](PERIPHERALS.md#cpu-features) |
| Compressed Instructions | `compressed`: `disabled`, `enabled` | RV32IC CPU and compiler flags, together - see [CPU features](PERIPHERALS.md#cpu-features) |
| Barrel Shifter | `barrel_shifter`: `disabled`, `enabled` | Single-cycle shifts, gateware only - see [CPU features](PERIPHERALS.md#cpu-features) |
| C++ Exceptions | `exceptions`: `disabled`, `enabled` | Compiles with `-fexceptions`, see below |

Sketches compile as C++17 (`-std=gnu++17`) and link the toolchain's
`libstdc++`, newlib `libm` and `libc` for whatever the core doesn't
implement itself, so `std::string`, `std::vector`, `std::map`, `<cmath>`
and the like work. The core's own `malloc()`, `printf()`, `mem*()`/`str*()`
and `abort()` take precedence over newlib's (see `recipe.c.combine.pattern`
in `platform.txt`).

**C++ Exceptions**: compiles with `-fexceptions` and keeps the unwind
tables (`.eh_frame`), which `libgcc`'s unwinder needs;
`cores/tangnano20k/cxx_runtime.cpp` registers them at startup, since
`crtbegin.o` isn't linked. `throw`/`catch`, unwinding with destructors,
rethrow, library exceptions and `std::bad_alloc` from a failed `new` work
on hardware - see `libraries/Core/examples/ExceptionTest`. The tables cost
SRAM (about 7KB for that example), which is why it's off by default.

With the default (disabled), a failed `new` returns `nullptr`, and library
code that would throw - e.g. `std::bad_alloc` when a container runs out of
memory - ends in `abort()`. `abort()` prints
`abort(): out of memory or uncaught C++ exception - program stopped` on
`Serial` and stops the CPU in an endless loop. An uncaught exception with
the option enabled ends the same way.

## Build times and the routed-design cache

With the default Tools > Boot Mode: SRAM, the sketch's program is baked
into the FPGA's block RAM, so every upload is a new bitstream. But for a
given set of Tools options the placed-and-routed design is the same for
every sketch - only the RAM contents differ. So `tools/build_bitstream.py`
caches the routed design:

- The **first build** for a combination of Tools options runs the full
  flow (synthesis, place & route, pack): typically 15-25 minutes.
- **Every later build** with the same options only writes the new program
  into the cached design and packs it: about **6 seconds** in total.

The cache lives in `~/.cache/nanotang/routed/`, a few MB per option
combination. Its key covers the gateware sources, the pin constraints,
the Tools options, this package's version (so a new release always
rebuilds), `build_bitstream.py` itself, and the yosys, nextpnr and
apicula versions; deleting the directory is always safe. Set
`NANOTANG_NO_ROUTED_CACHE=1` to force the full flow. Tools > Boot Mode:
Flash has its own cache of the core bitstream, keyed the same way.

Full builds write several hundred MB of intermediate files to the
temporary directory. If `/tmp` is on a small partition, point `TMPDIR`
somewhere with room, e.g. `TMPDIR=~/tmp arduino-cli compile ...`.

## FPGA resource usage

How much of the GW2AR-18's logic each Tools option costs, from place &
route. Each row is the baseline configuration (one SPI bus, one I2C bus,
27MHz, SRAM boot, Hardware Multiply/Divide off) with that one option
added. These were measured before Hardware Multiply/Divide became the
default, so today's default is the baseline plus that row:

| Configuration | LUT4 (of 20,736) | vs. baseline | Max clock after routing |
|---|---|---|---|
| Minimal (Tools > SPI Buses / I2C Buses: None) | 10,327 (50%) | -426 | 79.8 MHz |
| **Baseline** | **10,753 (52%)** | - | 74.3 MHz |
| + Barrel Shifter | 10,678 | ~0 | not measured |
| + SPI Buses: Two | 11,173 | +420 | 71.9 MHz |
| + I2C Buses: Two | 11,284 | +531 | 73.7 MHz |
| + Compressed Instructions | 11,403 | +650 | 66.8 MHz |
| + Hardware Multiply/Divide (default) | 11,476 | +723 | not measured |
| + PWM Audio | 11,775 | +1,022 | 71.6 MHz |
| + I2S Input | 11,924 | +1,171 | 74.4 MHz |
| + Flash Cache | 12,983 | +2,230 | not measured |
| + CAN | 13,225 | +2,472 | 75.6 MHz |
| + AI Accelerator | 14,306 (69%) | +3,553 | 68.8 MHz |

Notes:

- The costs add up roughly when options are combined, so most
  combinations fit, but everything at once would not.
- A combination can fit and still fail to route with nextpnr's default
  placement seed ("Failed to find a route for arc ..."), e.g. AI
  Accelerator + Hardware Multiply/Divide + Overclocked (54 MHz): 56% of
  the LUTs but 89% of the block RAM. `tools/build_bitstream.py` then
  retries place & route with seeds 2, 3 and 4 (each attempt takes as long
  as the first); seeds 2 and 3 both routed that combination at about
  70 MHz. A placement failure (the design really doesn't fit) isn't
  retried.
- Other resources: the default design uses 32 of the 46 block RAMs (the
  64KB internal SRAM) and about 3,500 of 15,552 flip-flops. The AI
  accelerator adds 9 block RAMs and 32 of the 96 MULT9X9 DSP blocks.
  Hardware Multiply/Divide uses DSP blocks too.
- Differences below about 300 LUT4s are within run-to-run variation of the
  synthesis and placement tools, which is why the Barrel Shifter (a few
  hundred LUTs in synthesis) shows up as roughly zero here.
- Tools > Boot Mode: Flash showed no measurable difference in synthesis.
- Every configuration whose routing was measured runs well above the
  54MHz Overclocked setting. For Hardware Multiply/Divide, nextpnr's
  estimate before routing was 54.4MHz - right at that limit - so check
  timing before combining it with Overclocked.
- Measured on 2026-09-23 with yosys 0.33, nextpnr-himbaechel 0.11.1 and
  apicula 0.33. `tools/run_tests.sh --utilization` prints these figures
  for the option combinations it builds.

## Trying changes in the Arduino IDE

The IDE uses the core installed by Boards Manager, not this checkout.
`tools/install_local.sh` copies the checkout over that installation
(`-n` for a dry run first). The IDE caches each board's Tools menus per
core version, so the script also deletes that cache
(`~/.config/arduino-ide/"Local Storage"`) - quit the IDE before running
it, or the cache is left alone and the old menus stay.

## Verifying changes

```sh
tools/run_tests.sh                 # yosys check + tools/sim tests + compile every example,
                                   # then the FPGA flow once per Tools option combination
tools/run_tests.sh --compile-only  # skip the FPGA flow - a couple of minutes in total
tools/run_tests.sh --utilization   # also build the CPU options no example uses (LUT figures)
tools/run_tests.sh --full          # also run one standalone synth_gowin pass on the gateware
```

Every example is compiled and linked against this checkout (a temporary
arduino-cli config points at it, so an installed Boards Manager release
can't be picked up instead). The FPGA flow only depends on the Tools
options, not on the sketch, so it runs once per distinct option
combination the examples use, and prints nextpnr's device utilization for
each.

`tools/sim/run_sims.sh` (also run on its own in a few minutes) simulates
the Arduino-core gateware with iverilog - systick counters, UART FIFOs,
GPIO/LED set/clear registers, SPI in all four modes against a
spec-following slave model, WS2812 strip streaming, the SDRAM bus under
refresh, and the CAN controller against reference bitstreams - and tests the core's
`printf` family and `mem*()` functions against glibc on the host. Needs
`iverilog` and a host `gcc`; each part is skipped with a warning if the
tool is missing.

Each FPGA build (synthesis, place & route, and pack) is the same as an
actual upload in the default SRAM boot mode, and place & route alone can
take 20 minutes or more, so a full run takes hours. This confirms the
gateware elaborates and synthesizes, every example compiles and links,
and a real bitstream is produced - but not that everything works on the
chip: several real bugs only showed up there. See
[Hardware test status](HARDWARE_STATUS.md) for what has been verified on
a board.
