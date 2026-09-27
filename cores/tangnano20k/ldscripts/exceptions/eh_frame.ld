/* INCLUDEd by link_cmd.ld / link_cmd_sdram.ld when Tools > C++
 * Exceptions is enabled: build.exceptions_ldflags (boards.txt) puts this
 * directory on the linker's -L search path, instead of
 * ../no_exceptions/, whose eh_frame.ld is empty.
 *
 * Keeps the C++ unwind tables: without an output section for them the
 * linker discards .eh_frame, and every throw ends in std::terminate().
 * KEEP because nothing references .eh_frame directly - cxx_runtime.cpp
 * registers it with libgcc's unwinder at startup, via __eh_frame_start.
 * The zero word ends the table (crtend.o's job on a hosted toolchain).
 * Not used without exceptions: KEEP also keeps the unwind entries of
 * every libstdc++ function a sketch uses, about 5KB of SRAM. */
  .eh_frame : {
    __eh_frame_start = .;
    KEEP(*(.eh_frame))
    LONG(0)
  } > SRAM
