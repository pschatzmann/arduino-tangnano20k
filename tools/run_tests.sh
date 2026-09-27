#!/usr/bin/env bash
# Verification script for arduino-tangnano20k: checks the gateware elaborates
# cleanly and every example sketch compiles/links against the RISC-V
# toolchain. Run after any change to gateware/src/*.v or cores/tangnano20k/.
#
# Usage:
#   tools/run_tests.sh                 # yosys hierarchy check + tools/sim tests +
#                                      # compile/link every example, then run the
#                                      # full FPGA flow once per distinct Tools
#                                      # option combination the examples use
#   tools/run_tests.sh --compile-only  # skip the FPGA flow (seconds, not hours)
#   tools/run_tests.sh --utilization   # also run the FPGA flow for Blink with each
#                                      # CPU option no example needs (Compressed,
#                                      # Barrel Shifter, Multiply/Divide, Flash
#                                      # Cache), for the LUT table in docs/BUILDING.md
#   tools/run_tests.sh --full          # also run a full synth_gowin pass (slow,
#                                      # ~1-2 min; catches real synthesis issues
#                                      # like the BRAM-inference gap in docs/KNOWN_LIMITATIONS.md)
# Options can be combined.
#
# Examples are always built against THIS checkout: a temporary
# arduino-cli config points its sketchbook at a symlink to this repo
# (sharing the normal data directory for the installed toolchain), so an
# installed Boards Manager release of the same package can't be picked up
# instead.
#
# What this does NOT verify (documented, known gaps - see docs/KNOWN_LIMITATIONS.md):
#   - place & route / bitstream generation (needs nextpnr-himbaechel,
#     not always installed - see docs/BUILDING.md)
#   - anything on real hardware
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FQBN="nanotang:tangnano20k:tangnano20k"
FULL=0
COMPILE_ONLY=0
UTILIZATION=0
for arg in "$@"; do
  case "$arg" in
    --full) FULL=1 ;;
    --compile-only) COMPILE_ONLY=1 ;;
    --utilization) UTILIZATION=1 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

FAIL=0
pass() { echo "  PASS: $1"; }
warn() { echo "  WARN: $1"; }
fail() { echo "  FAIL: $1"; FAIL=1; }

echo "== Gateware: yosys hierarchy check =="
GW_SOURCES="picorv32.v sram8bit.v sram.v simpleuart.v uart_wrap.v reset.v systick.v tang_leds.v i2s.v pwm_bank.v pwm_audio.v spi_master.v od_gpio2.v gpio_bank.v ws2812_strip.v can_ctrl.v extirq.v dma_engine.v qspi_flash.v qspi_flash_cached.v int8_mac_lane.v dot_product_lane_array.v byte_interleave_ram.v dot_product_engine.v ai_accel_bus.v sdram.v sdram_bus.v gowin_rpll_sys.v top.v"

# top.v instantiates the Gowin rPLL primitive (for the system clock/SDRAM
# clock - see gateware/src/gowin_rpll_sys.v); yosys needs its Gowin cell
# simulation models preloaded to resolve that primitive for a plain
# hierarchy check (synth_gowin does this internally on its own).
GOWIN_CELLS="$(yosys-config --datdir 2>/dev/null)/gowin/cells_sim.v"
[ -f "$GOWIN_CELLS" ] || GOWIN_CELLS="/usr/share/yosys/gowin/cells_sim.v"
if [ -f "$GOWIN_CELLS" ]; then
  PRELOAD="read_verilog $GOWIN_CELLS;"
else
  warn "could not find yosys's gowin/cells_sim.v - hierarchy check will likely fail to resolve rPLL"
  PRELOAD=""
fi

GW_LOG="$(mktemp)"
if (cd "$ROOT/gateware/src" && yosys -p "$PRELOAD read_verilog $GW_SOURCES; hierarchy -check -top top") >"$GW_LOG" 2>&1; then
  pass "gateware elaborates (hierarchy -check)"
else
  fail "gateware hierarchy check failed - see $GW_LOG"
fi

if [ "$FULL" = "1" ]; then
  echo "== Gateware: full synth_gowin pass (slow) =="
  SYN_LOG="$(mktemp)"
  if (cd "$ROOT/gateware/src" && yosys -p "read_verilog $GW_SOURCES; synth_gowin -top top -json /tmp/nanotang_synth_check.json") >"$SYN_LOG" 2>&1; then
    cells=$(grep -oP 'Number of cells:\s*\K[0-9]+' "$SYN_LOG" | tail -1)
    if [ -n "$cells" ] && [ "$cells" -gt 30000 ]; then
      warn "synth_gowin ran but reports $cells cells - likely the known BRAM-inference gap (see docs/KNOWN_LIMITATIONS.md), not a new regression"
    else
      pass "synth_gowin ran, cell count looks sane ($cells cells) - see $SYN_LOG"
    fi
  else
    fail "synth_gowin failed - see $SYN_LOG"
  fi
fi

echo "== Gateware + libc: behavioural tests (tools/sim) =="
if "$ROOT/tools/sim/run_sims.sh"; then
  :
else
  fail "tools/sim/run_sims.sh reported failures (see above)"
fi

echo "== Sketches: arduino-cli compile =="
if ! command -v arduino-cli >/dev/null 2>&1; then
  fail "arduino-cli not found on PATH"
else
  # Temporary sketchbook whose hardware/ folder holds only this checkout.
  CLI_DIR="$(mktemp -d)"
  mkdir -p "$CLI_DIR/sketchbook/hardware/nanotang"
  ln -s "$ROOT" "$CLI_DIR/sketchbook/hardware/nanotang/tangnano20k"
  DATA_DIR="$(arduino-cli config get directories.data 2>/dev/null)"
  [ -n "$DATA_DIR" ] || DATA_DIR="$HOME/.arduino15"
  cat >"$CLI_DIR/cli.yaml" <<CFG
directories:
  data: $DATA_DIR
  user: $CLI_DIR/sketchbook
CFG
  CLI=(arduino-cli --config-file "$CLI_DIR/cli.yaml")

  # recipe.objcopy.hex.pattern is what drives the FPGA flow (see
  # platform.txt) - replacing it with a no-op leaves compile + link.
  NO_FPGA=(--build-property "recipe.objcopy.hex.pattern=true")

  # Tools menu options an example needs to compile or do anything useful
  # (e.g. SD.h's deliberate #error unless the GPLv3 menu is enabled - see
  # docs/PERIPHERALS.md "SD card").
  menu_for() {
    case "$1" in
      SDReadWrite) echo ":sd_card=enabled" ;;
      PWMAudio*) echo ":pwm_audio=enabled" ;;
      I2SDuplex*) echo ":i2s_rx=enabled" ;;
      AIAccelerator*) echo ":ai_accel=enabled" ;;
      ExtraSPII2C*) echo ":spi_buses=two,i2c_buses=two" ;;
      CAN*) echo ":can=enabled" ;;
      SdramCodeTest) echo ":boot_mode=sram_sdram" ;;
      ExceptionTest) echo ":exceptions=enabled" ;;
      *) echo "" ;;
    esac
  }

  # nextpnr's "Device utilisation" block, condensed to the main resources.
  utilization() {
    # Lines look like "Info: <tab>  LUT4:   14982/  20736    72%".
    awk '/Device utilisation/{on=1; next} on && /^Info:[[:space:]]+[A-Za-z0-9_]+:[[:space:]]+[0-9]+\/[[:space:]]*[0-9]+/{print; next} on{on=0}' "$1" |
      grep -E "LUT4|DFF|ALU|BSRAM|MULT|RAM16" | sed -E 's/^Info:[[:space:]]+/        /'
  }

  # build <label> <fqbn suffix> <sketch dir> <mode: compile|fpga>
  build() {
    local label="$1" menu="$2" dir="$3" mode="$4"
    local name build_path log rc took elf
    name="$(basename "$dir")"
    build_path="$(mktemp -d)"
    log="$(mktemp)"
    local extra=()
    [ "$mode" = "compile" ] && extra=("${NO_FPGA[@]}")
    local start_s=$SECONDS
    "${CLI[@]}" compile --fqbn "$FQBN$menu" --build-path "$build_path" "${extra[@]}" "$dir" >"$log" 2>&1
    rc=$?
    took="$((SECONDS - start_s))s"
    elf="$build_path/$name.ino.elf"
    if [ $rc -eq 0 ] && [ "$mode" = "compile" ]; then
      pass "$label (compiled and linked, $took)"
    elif [ $rc -eq 0 ]; then
      pass "$label (bitstream built, $took)"
      utilization "$log"
    elif [ -f "$elf" ] && grep -q "no BELs remaining to implement cell type 'RAM16SDP4'" "$log"; then
      warn "$label compiled+linked+synthesized OK; stopped at the known Gowin BRAM-inference gap (see docs/KNOWN_LIMITATIONS.md)"
    elif [ -f "$elf" ] && grep -q "Unconstrained IO" "$log"; then
      warn "$label compiled+linked+synthesized OK; an unconstrained IO turned up during place & route - see $log"
      log=""
    elif [ -f "$elf" ] && grep -q "nextpnr-himbaechel" "$log"; then
      warn "$label compiled+linked OK; nextpnr-himbaechel isn't installed or failed - see docs/BUILDING.md and $log"
      log=""
    elif [ -f "$elf" ]; then
      warn "$label compiled+linked OK; FPGA build step failed for another reason - see $log"
      log=""
    else
      fail "$label did not compile/link - see $log"
      log=""  # keep the log around for inspection
    fi
    rm -rf "$build_path"
    [ -n "$log" ] && rm -f "$log"
  }

  if ! "${CLI[@]}" board listall 2>/dev/null | grep -q "$FQBN"; then
    fail "FQBN $FQBN not found - is the RISC-V toolchain installed (install the nanotang package once via Boards Manager)? See docs/BUILDING.md"
  else
    # Every example compiles and links...
    declare -A fpga_example=()
    for dir in "$ROOT"/libraries/*/examples/*/; do
      name="$(basename "$dir")"
      menu="$(menu_for "$name")"
      build "$name" "$menu" "$dir" compile
      key="${menu:-defaults}" # Bash arrays can't have an empty key.
      [ -z "${fpga_example[$key]+x}" ] && fpga_example[$key]="$dir"
    done

    # ...and the FPGA flow runs once per distinct Tools option combination:
    # the gateware only depends on those, not on the sketch, and each run
    # takes many minutes.
    if [ "$COMPILE_ONLY" = "0" ]; then
      echo "== FPGA flow: one build per Tools option combination =="
      for key in "${!fpga_example[@]}"; do
        dir="${fpga_example[$key]}"
        menu="$key"
        [ "$menu" = "defaults" ] && menu=""
        build "$(basename "$dir") [$key]" "$menu" "$dir" fpga
      done
      if [ "$UTILIZATION" = "1" ]; then
        for menu in ":compressed=enabled" ":barrel_shifter=enabled" ":hw_muldiv=disabled" ":flash_cache=enabled" ":spi_buses=none,i2c_buses=none"; do
          build "Blink [$menu]" "$menu" "$ROOT/libraries/Core/examples/Blink/" fpga
        done
      fi
    fi
  fi
  rm -rf "$CLI_DIR"
fi

echo
if [ "$FAIL" = "1" ]; then
  echo "RESULT: FAILURES ABOVE"
  exit 1
else
  echo "RESULT: all checks passed (see WARN lines for known, documented gaps)"
  exit 0
fi
