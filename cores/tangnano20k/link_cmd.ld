/* Linker script for the arduino-tangnano20k PicoRV32 SoC.
 * Must match gateware/src/sys_parameters.v (SRAM_ADDR_WIDTH=14 -> 64KB).
 *
 * Fixed low-memory layout for interrupts (see irq_vec.S, top.v's
 * PROGADDR_RESET/PROGADDR_IRQ, and docs/PERIPHERALS.md "Interrupts"):
 *   0x000            picorv32's PROGADDR_IRQ - irq_vec.S's handler
 *   0x200            register-save scratch + interrupt handler stack
 *   0x380            Tools > Boot Mode: Flash only - boot.S's stub
 *   0x400            picorv32's PROGADDR_RESET - normal program start
 * picorv32 has no ENABLE_IRQ_QREGS-free way to relocate the scratch
 * region elsewhere; irq_vec.S hardcodes 0x200-relative save addresses
 * directly (see that file's header comment for why).
 *
 * IMPORTANT: every one of these four addresses is given EXPLICITLY on its
 * own output section header (`.name 0xNNN : { ... }`), never via a bare
 * `. = 0xNNN;` assignment between sections. This project had a real,
 * previously-undetected bug where bare `. = 0x400;` (etc.) between
 * sections was silently NOT taking effect with this exact toolchain -
 * `.text` (and therefore `_start`) ended up linked at whatever address
 * happened to follow `.irq_scratch` naturally, NOT at 0x400, silently
 * mismatching top.v's hardware-fixed PROGADDR_RESET, for as long as the
 * interrupts feature existed in this repo (undetected because nothing
 * here has run on real hardware yet - see docs/KNOWN_LIMITATIONS.md).
 * Giving every address-critical section its own explicit header address
 * is confirmed reliable; do not reintroduce bare mid-script `. = X;`
 * jumps for anything that must land at a specific address a `` `ifdef``'d
 * gateware parameter or another file's literal offset depends on.
 */
MEMORY
{
  SRAM (rwx) : ORIGIN = 0x00000000, LENGTH = 64K

  /* Bookkeeping only, not a real loaded memory region - gives FLASH_DATA
   * arrays (see tangnano20k_soc.h) correct addresses within the onboard
   * flash's memory-mapped window (gateware/src/qspi_flash.v) without
   * reserving any SRAM space or being copied there at startup. Their raw
   * bytes are extracted straight from the ELF's .flash_data section (see
   * tools/upload.py) and written directly to the physical flash chip -
   * see docs/PERIPHERALS.md "Flash". Sized to the whole 8MB flash chip
   * minus the bitstream+program partitions that precede it. */
  FLASH_DATA (r) : ORIGIN = 0x20110000, LENGTH = 8M - 0x110000
}

ENTRY(_start)

SECTIONS
{
  .text.irq 0x000 : {
    KEEP(*(.text.irq))
  } > SRAM
  ASSERT(SIZEOF(.text.irq) <= 0x200, "link_cmd.ld: .text.irq grew past its reserved 0x200 budget - irq_vec.S's hardcoded 0x200-relative save/restore addresses must be updated to match, and this reserved size increased")

  .irq_scratch 0x200 (NOLOAD) : {
    irq_regs = .;
    . += 32 * 4;  /* saved x0..x31 (x0 slot holds the saved PC on entry) */

    /* Fixed slot holding &tangnano20k_irq_dispatch, written once by
     * startup.S before interrupts can ever be unmasked. irq_vec.S loads
     * through this pointer indirectly instead of calling the sketch's
     * dispatch function by a direct jal/call - a direct call's encoding
     * bakes in the link-time PC-relative distance to that function, which
     * moves with every sketch (it lives in the ordinary, sketch-sized
     * .text region past 0x400), which would make .text.irq's own bytes
     * sketch-dependent despite being part of the fixed core image that
     * Tools > Boot Mode: Flash bakes into SRAM once and reuses across
     * sketches (see build_bitstream.py's core_bitstream_cache_key) - a
     * real bug found and fixed this way, confirmed via two different
     * sketches' otherwise-identical .text.irq differing at this exact
     * jal instruction's immediate. */
    irq_dispatch_ptr = .;
    . += 1 * 4;

    . += 63 * 4;  /* interrupt handler's own stack (one word narrower to make room for irq_dispatch_ptr above) */
    irq_stack = .;
  } > SRAM
  ASSERT(irq_stack <= 0x380, "link_cmd.ld: .irq_scratch overflowed past the reserved 0x380 boot-stub start - shrink the interrupt handler stack above or move boot.S's fixed address")

  /* Tools > Boot Mode: Flash only (see boot.S) - baked into the core's
   * SRAM image, never part of a per-sketch compile. Unused (dead space)
   * in the default SRAM boot mode. */
  .text.boot 0x380 : {
    KEEP(*(.text.boot))
  } > SRAM
  ASSERT(SIZEOF(.text.boot) <= 0x80, "link_cmd.ld: .text.boot grew past its reserved 128-byte budget before the fixed 0x400 program-start boundary")

  .text 0x400 : {
    *(.text.start)
    /* SRAM_CODE/SDRAM_CODE (tangnano20k_soc.h) only matter for Tools >
     * Boot Mode: ... + SDRAM (link_cmd_sdram.ld) - here everything is
     * in SRAM anyway. */
    *(.sram_text .sram_text.*)
    *(.sdram_text .sdram_text.*)
    *(.text .text.*)
  } > SRAM

  .rodata : {
    *(.rodata .rodata.*)
    *(.srodata .srodata.*)
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

  /* FLASH_DATA-attributed const arrays (tangnano20k_soc.h) - addressed
   * within the flash-mapped window, never loaded into SRAM at all. See
   * the FLASH_DATA memory region comment above and tools/upload.py. */
  .flash_data : {
    *(.flash_data)
  } > FLASH_DATA

  /* No code in SDRAM (see link_cmd_sdram.ld): an empty image, so
   * startup.S skips its copy and the heap starts at the SDRAM base. */
  __sdram_img_start = 0x10000000;
  __sdram_img_end = 0x10000000;
  __sdram_img_load = 0;

  _end = .;
}
