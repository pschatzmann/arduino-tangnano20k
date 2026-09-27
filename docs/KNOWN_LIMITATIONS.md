# Known limitations

- **`Serial` is the board's second USB serial port.** The onboard BL616
  exposes a JTAG/programming interface and a UART bridge over the same
  USB cable, which enumerate as two serial devices. The first
  (`/dev/ttyUSB0` on Linux) is the JTAG interface `tools/upload.py` uses;
  the second (`/dev/ttyUSB1`) carries `Serial` - point the Serial Monitor
  at that one. (FPGA pin 69 `uart_tx` → `BL616_UART_RX`, pin 70 `uart_rx`
  ← `BL616_UART_TX`, per
  [Sipeed's schematic](https://dl.sipeed.com/shareURL/TANG/Nano_20K/2_Schematic).)
- **Data from the board to the PC gets lost while the PC is sending at the
  same time.** This is the onboard BL616 USB bridge (debugger firmware
  2025030317 on the tested board), not the FPGA: a test board streaming
  2,000 bytes to the PC delivered all of them - unless the PC sent 1,000
  bytes to the board during the transfer, in which case the board still
  received every byte but only 1,156 of its 2,000 reached the PC, in
  bursts matching the bridge's 64-byte USB packets. The loss doesn't
  depend on the baud rate (9600 and 115200 behave alike). Normal use is
  unaffected - printing while you occasionally type in the Serial Monitor,
  or either direction on its own - but echoing a large paste back, or any
  protocol that streams both ways at once, loses data. A newer BL616
  firmware from Sipeed (see their "Update debugger" page) may fix it; that
  hasn't been tried.
- **Long `Serial` prints during 44.1kHz I2S audio cause clicks** with the
  default CPU settings. A print of more than about 32 characters stalls
  the CPU on the UART long enough to empty the I2S FIFO. Short prints are
  fine - see [Audio (I2S)](PERIPHERALS.md#audio-i2s) for the CPU budget
  and how to get more headroom.
- **The first build for each combination of Tools options takes 15-25
  minutes** (synthesis, place & route and pack), because in the default
  SRAM boot mode the program is part of the bitstream. Later builds with
  the same options reuse the routed design and take seconds - see
  [Build times](BUILDING.md#build-times-and-the-routed-design-cache).
- **No FPU.** picorv32 has no floating-point extension - every
  `float`/`double` operation is a call into libgcc's software routines,
  each costing many dozens of cycles. Tools > Hardware Multiply/Divide
  speeds them up (about 1.6x), but there's no hardware float math. Prefer
  fixed-point arithmetic in hot loops, or the AI accelerator's INT8 path
  where applicable.
- **C library math functions (`sin()`, `sqrt()`, `pow()`, ...) come from
  the toolchain's newlib `libm`**, in software like all float math above,
  so they are slow. The core's own `printf`, `mem*()`/`str*()`, `malloc()`
  and `abort()` take precedence over newlib's; newlib functions that need
  an operating system (files, `time()`, signals, ...) fail to link.
- **C++ exceptions are off by default** (their unwind tables cost SRAM) -
  see [Tools menus](BUILDING.md#tools-menus).
- **DMA's async/background mode only reaches the embedded SDRAM heap,
  not the internal SRAM** (see [DMA](PERIPHERALS.md#dma)). That would need
  true dual-port block RAM where both ports can read or write, and this
  toolchain's BRAM inference only supports dual-port memories whose ports
  are each fixed read-only or write-only; yosys reports `ERROR: no valid
  mapping found for memory` for that combination however the Verilog is
  written. The blocking DMA mode has no such restriction, but stalls the
  CPU for the whole transfer.
- No USB (the BL616 owns the board's USB port), no ADC (`analogRead()`
  always returns 0), no HDMI or RGB LCD support.
- **Not everything has been tested on real hardware yet** - see
  [Hardware test status](HARDWARE_STATUS.md). Everything else is
  verified in simulation, synthesis and `arduino-cli compile` (see
  `tools/run_tests.sh`).
