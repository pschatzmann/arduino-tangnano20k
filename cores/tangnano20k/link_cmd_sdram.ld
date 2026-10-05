/* Linker script for Tools > Boot Mode: SRAM + SDRAM / Flash + SDRAM
 * (docs/PERIPHERALS.md "Code in SDRAM"). Identical to
 * link_cmd.ld (read its header comment first - the fixed low-memory
 * layout and the "explicit address on every section header" rule apply
 * here unchanged), except that code and constants of everything that is
 * not on a hot or timing-critical path are placed in the embedded SDRAM
 * instead of the 64KB internal SRAM - see docs/PERIPHERALS.md "Code in
 * SDRAM".
 *
 * The SDRAM is empty at power-up and the bitstream can only preload the
 * block RAM, so .sdram_image is linked to run at SDRAM_IMG but stored
 * (LMA) in the flash's constant-data partition right after .flash_data.
 * tools/build_bitstream.py extracts both into data.bin, tools/upload.py
 * writes that to flash, and startup.S copies the image into SDRAM before
 * any constructor runs. tangnano20k_malloc.c starts the heap after
 * __sdram_img_end.
 *
 * Placement is by input file, first match wins: the SRAM .text/.rodata
 * statements below claim the core, libgcc's integer and single-precision
 * float helpers, the helix MP3 decoder and the timing-sensitive bundled
 * libraries; .sdram_image then takes whatever is left. SRAM_CODE /
 * SDRAM_CODE (tangnano20k_soc.h) override this per function.
 */
MEMORY
{
  SRAM (rwx) : ORIGIN = 0x00000000, LENGTH = 64K
  SDRAM_IMG (rwx) : ORIGIN = 0x10000000, LENGTH = 1M
  FLASH_DATA (r) : ORIGIN = 0x20110000, LENGTH = 8M - 0x110000
}

ENTRY(_start)

SECTIONS
{
  .text.irq 0x000 : {
    KEEP(*(.text.irq))
  } > SRAM
  ASSERT(SIZEOF(.text.irq) <= 0x200, "link_cmd_sdram.ld: .text.irq grew past its reserved 0x200 budget - see link_cmd.ld")

  .irq_scratch 0x200 (NOLOAD) : {
    irq_regs = .;
    . += 32 * 4;
    irq_dispatch_ptr = .;
    . += 1 * 4;
    . += 63 * 4;
    irq_stack = .;
  } > SRAM
  ASSERT(irq_stack <= 0x380, "link_cmd_sdram.ld: .irq_scratch overflowed past the reserved 0x380 boot-stub start - see link_cmd.ld")

  .text.boot 0x380 : {
    KEEP(*(.text.boot))
  } > SRAM
  ASSERT(SIZEOF(.text.boot) <= 0x80, "link_cmd_sdram.ld: .text.boot grew past its reserved 128-byte budget - see link_cmd.ld")

  .text 0x400 : {
    *(.text.start)
    *(.sram_text .sram_text.*)
    *core.a:*(.text .text.*)
    *libgcc.a:_*.o(.text .text.*)
    *libgcc.a:*sf*.o(.text .text.*)
    */libhelix-mp3/*(.text .text.*)
    */libraries/I2S/*(.text .text.*)
    */libraries/PWMAudio/*(.text .text.*)
    */libraries/SPI/*(.text .text.*)
    */libraries/Wire/*(.text .text.*)
    */libraries/SoftwareSerial/*(.text .text.*)
    */libraries/DMA/*(.text .text.*)
    */libraries/TangTimer/*(.text .text.*)
    */libraries/Servo/*(.text .text.*)
    */libraries/WS2812/*(.text .text.*)
    */libraries/CAN/*(.text .text.*)
    */libraries/AIAccelerator/*(.text .text.*)
  } > SRAM

  .rodata : {
    *core.a:*(.rodata .rodata.* .srodata .srodata.*)
    *libgcc.a:*(.rodata .rodata.* .srodata .srodata.*)
    */libhelix-mp3/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/I2S/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/PWMAudio/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/SPI/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/Wire/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/SoftwareSerial/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/DMA/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/TangTimer/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/Servo/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/WS2812/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/CAN/*(.rodata .rodata.* .srodata .srodata.*)
    */libraries/AIAccelerator/*(.rodata .rodata.* .srodata .srodata.*)
  } > SRAM

  .init_array : {
    __init_array_start = .;
    KEEP(*(.init_array))
    KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*)))
    __init_array_end = .;
  } > SRAM

  /* .eh_frame (C++ unwind tables) only gets an output section with
   * Tools > C++ Exceptions enabled - see ldscripts/exceptions/eh_frame.ld;
   * the -L path in build.exceptions_ldflags picks which eh_frame.ld this
   * includes. */
  INCLUDE eh_frame.ld

  .gcc_except_table : {
    *(.gcc_except_table .gcc_except_table.*)
  } > SRAM

  .data : {
    *(.data .data.*)
    *(.sdata .sdata.*)
  } > SRAM

  .bss (NOLOAD) : {
    __bss_start = .;
    *(.bss .bss.*)
    *(.sbss .sbss.*)
    *(COMMON)
    __bss_end = .;
  } > SRAM

  . = ALIGN(16);
  __heap_start = .;
  __stack_top = ORIGIN(SRAM) + LENGTH(SRAM);

  .flash_data : {
    *(.flash_data)
    . = ALIGN(4);
  } > FLASH_DATA

  /* Everything not claimed above. Word-aligned at both ends so startup.S
   * can copy it one 32-bit word at a time. */
  .sdram_image : ALIGN(4) {
    __sdram_img_start = .;
    *(.sdram_text .sdram_text.*)
    *(.text .text.*)
    *(.rodata .rodata.* .srodata .srodata.*)
    . = ALIGN(4);
    __sdram_img_end = .;
  } > SDRAM_IMG AT > FLASH_DATA
  __sdram_img_load = LOADADDR(.sdram_image);

  _end = .;
}
