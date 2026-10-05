#!/usr/bin/env python3
"""Turn a linked arduino-tangnano20k .elf into a Gowin bitstream (.fs) by baking
a program into the gateware's SRAM initialization files and running the
open-source FPGA flow (yosys -> nextpnr-himbaechel -> gowin_pack).

Usage: build_bitstream.py [--tools-dir=<dir>] <prog.elf> <objcopy> <build_dir> [ai_accel] [boot_flash] [spi_count] [i2c_count] [hw_muldiv] [i2s_rx] [clk_freq_hz] [pll_idiv] [pll_fbdiv] [pll_odiv] [pwm_audio] [flash_cache] [compressed] [barrel_shifter] [can]

ai_accel: "1" to synthesize the AI accelerator (gateware/src/ai_accel_bus.v
and friends, integrated from NanoTangAI) into the bitstream, per the
Tools > AI Accelerator board menu; "0" (default) leaves it out entirely.
Unlike an unused software library, that gateware costs real LUTs/BRAM
whenever it's present, whether or not a sketch uses it - see top.v's
`ifdef WITH_AI_ACCEL and docs/PERIPHERALS.md "AI accelerator".

boot_flash: "1" for Tools > Boot Mode: Flash, "0" (default) for the
original SRAM boot mode. This changes what actually gets baked into the
SRAM init files, and what tools/upload.py needs to do:

- boot_flash=0 (default, unchanged from before this mode existed): the
  WHOLE compiled program (0x000 - the IRQ vector - through the sketch's
  own .text/.data) is baked into SRAM. Every upload re-runs the full FPGA
  flow (~1-3 minutes), because the program lives in block RAM initialized
  at synthesis time.
- boot_flash=1: only the *fixed* low-memory core code (irq_vec.S's
  .text.irq at 0x000, boot.S's .text.boot at 0x380 - see link_cmd.ld) gets
  baked into SRAM - identical across every sketch compile, since neither
  file depends on sketch content. The sketch's actual program (0x400
  onward) is instead extracted to `{build_dir}/prog_flash.bin`, meant for
  tools/upload.py to write directly to the onboard SPI flash at
  TANGNANO20K_FLASH_PROGRAM_OFFSET (see flash_layout.h) - boot.S copies it
  into SRAM at runtime.

  Because that core-only SRAM image is identical across sketch compiles
  (for a given ai_accel/spi_count/i2c_count/hw_muldiv/clock combination),
  the resulting bitstream is cached at ~/.cache/nanotang/bitstreams/<hash>.fs,
  keyed on the core image's own bytes plus every gateware source file plus
  the .cst plus those menu flags - so an actual "resynthesize this SoC"
  cost is only ever paid once per distinct core/menu combination, not on
  every compile. A cache hit skips straight to copying the cached .fs; a
  miss runs the full flow as usual and then populates the cache. Deleting
  ~/.cache/nanotang/bitstreams/ is always safe - it only ever holds
  reproducible build outputs.

Independent of boot_flash: if the ELF has a `.flash_data` section (see
FLASH_DATA in tangnano20k_soc.h), its raw bytes are extracted to
`{build_dir}/data.bin` for tools/upload.py to write to
TANGNANO20K_FLASH_DATA_OFFSET - available in either boot mode.

spi_count/i2c_count: "0"/"1" (default)/"2" per the Tools > SPI Buses / I2C
Buses board menus. "1" is the original, always-present primary port
(microSD slot's pins); "0" removes that port's gateware entirely
(spi_master.v/od_gpio2.v cost real LUTs whether or not a sketch actually
calls SPI/Wire) and SPI/Wire silently read back 0/no-op instead, same as
any other menu-gated peripheral used without enabling it. "2" adds a
second, independent port (SPI2 on GPIO0-3, Wire2 on GPIO4-5 - these do NOT
overlap, unlike what a single old combined toggle implied) - real
GPIO-pin cost like AI Accelerator's LUT/BRAM cost, so gated the same way.

hw_muldiv: "1" for Tools > Hardware Multiply/Divide: Enabled, enabling
picorv32's real M-extension (ENABLE_MUL/ENABLE_DIV/ENABLE_FAST_MUL in
top.v); "0" (default) leaves the CPU as plain RV32I. This MUST match
platform.txt's build.march for this same sketch - boards.txt drives both
from the one menu choice, never set independently, since a mismatch means
an illegal instruction on real hardware (a sketch compiled for
rv32im_zicsr_zifencei run on a bitstream without ENABLE_MUL, or vice
versa the CPU having unused hardware for a plain-RV32I sketch, which is
harmless).

i2s_rx: "1" to wire GPIO6 to the I2S peripheral's receive input (Tools >
I2S Input), enabling I2S.read()/full duplex against an external I2S
microphone sharing the onboard MAX98357A's BCLK/WS lines; "0" (default)
leaves GPIO6 as plain GPIO and I2S.read() always reads back zero
immediately. Same real GPIO-pin cost as spi_count=2/i2c_count=2, gated the
same way - see gateware/src/i2s.v and docs/PERIPHERALS.md "Audio (I2S)".

clk_freq_hz/pll_idiv/pll_fbdiv/pll_odiv: driven together by the Tools >
Clock Speed board menu (Normal 27MHz / Low Power 13.5MHz / Overclocked
54MHz, default Normal). clk_freq_hz becomes gowin_rpll_sys.v's actual PLL
output and sys_parameters.v's CLK_FREQ (which top.v feeds to
sdram_bus.v/ws2812_strip.v for their own FREQ-derived timing); pll_idiv/
pll_fbdiv/pll_odiv are the exact IDIV_SEL/FBDIV_SEL/ODIV_SEL divider values
that produce it from the board's 27MHz oscillator - computed per option
with apycula's gowin_pll calculator against this exact part (GW2AR-18C),
not derived at build time, since only certain divider combinations are
valid PLL configurations. All four MUST move together (a clk_freq_hz that
doesn't match what the given dividers actually produce would desync
software baud-rate/timing math in build.f_cpu from the gateware's real
clock) - boards.txt drives all four from the one menu choice, same pattern
as hw_muldiv's build.march/build.libgcc_path. Defaults (27000000/0/0/32)
match the original fixed, non-configurable clock this core shipped with.

pwm_audio: "1" to synthesize the PWM audio peripheral (gateware/src/
pwm_audio.v, Tools > PWM Audio) onto GPIO16 (left)/GPIO17 (right); "0"
(default) leaves those pins as plain GPIO and libraries/PWMAudio's begin()
reports failure. Same real GPIO-pin cost as i2s_rx, gated the same way -
see docs/PERIPHERALS.md "Audio (PWM)". Last on the command line (rather
than next to i2s_rx) only so every existing positional argument keeps its
index.

flash_cache: "1" for Tools > Flash Cache: Enabled - synthesizes
gateware/src/qspi_flash_cached.v (a 512-byte read cache in front of the
onboard flash, ~1,700 LUT4s) instead of the plain qspi_flash.v; "0"
(default) keeps the uncached reader. See docs/PERIPHERALS.md "Flash".
Last on the command line for the same reason as pwm_audio.

compressed: "1" for Tools > Compressed Instructions: Enabled - builds
picorv32 with COMPRESSED_ISA (the RISC-V "C" extension). Must match
platform.txt's -march (the "c" in rv32i[m]c_...), which boards.txt drives
from the same menu choice.

barrel_shifter: "1" for Tools > Barrel Shifter: Enabled - builds picorv32
with BARREL_SHIFTER (single-cycle shifts). Gateware only.

can: "1" for Tools > CAN: Enabled - synthesizes gateware/src/can_ctrl.v
(see libraries/CAN). Its TX/RX pins are chosen at run time, so no GPIO is
claimed at build time.
"""
import gzip
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

from find_tool import (bundled_gowin_pack_cmd, find_tool, not_found_message,
                       require_tool, take_tools_dir_arg)

SRAM_ADDR_WIDTH = 14  # Must match gateware/src/sys_parameters.v and link_cmd.ld
DEVICE = "GW2AR-LV18QN88C8/I7"
FAMILY = "GW2A-18C"

REPO_ROOT = Path(__file__).resolve().parent.parent
GATEWARE_SRC = REPO_ROOT / "gateware" / "src"
CST_FILE = REPO_ROOT / "gateware" / "picorv32_20k.cst"
CACHE_DIR = Path.home() / ".cache" / "nanotang" / "bitstreams"

GATEWARE_SOURCES = [
    "picorv32.v",
    "sram8bit.v",
    "sram.v",
    "simpleuart.v",
    "uart_wrap.v",
    "reset.v",
    "systick.v",
    "tang_leds.v",
    "i2s.v",
    "pwm_bank.v",
    "pwm_audio.v",
    "spi_master.v",
    "od_gpio2.v",
    "gpio_bank.v",
    "ws2812_strip.v",
    "can_ctrl.v",
    "extirq.v",
    "dma_engine.v",
    "qspi_flash.v",
    "qspi_flash_cached.v",
    "int8_mac_lane.v",
    "dot_product_lane_array.v",
    "byte_interleave_ram.v",
    "dot_product_engine.v",
    "ai_accel_bus.v",
    "sdram.v",
    "sdram_bus.v",
    "gowin_rpll_sys.v",
    "top.v",
]


def run(cmd, **kwargs):
    print("+ " + " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


# nextpnr's placement starts from a random seed. With a well-filled chip
# (e.g. AI Accelerator + Hardware Multiply/Divide + 54MHz) the default
# seed can end in a placement the router can't finish ("Failed to find a
# route for arc ..."), while other seeds route the same netlist fine with
# timing to spare - so retry routing failures with a few other seeds.
# Placement failures (the design doesn't fit at all) aren't retried.
PNR_SEEDS = [None, 2, 3, 4]
ROUTING_FAILED = ("Routing design failed", "Failed to find a route", "Failed to route")


def place_and_route(json_path, pnr_json):
    nextpnr = require_tool("nextpnr-himbaechel", "place & route", YOSYS_HINT)
    for attempt, seed in enumerate(PNR_SEEDS):
        cmd = [nextpnr, "--json", str(json_path), "--write", str(pnr_json),
               "--device", DEVICE, "--vopt", f"family={FAMILY}", "--vopt", f"cst={CST_FILE}"]
        if seed is not None:
            cmd += ["--seed", str(seed)]
        print("+ " + " ".join(str(c) for c in cmd))
        routing_failed = False
        with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) as proc:
            for line in proc.stdout:
                sys.stdout.write(line)
                routing_failed = routing_failed or any(m in line for m in ROUTING_FAILED)
        if proc.returncode == 0:
            return
        if not routing_failed or attempt == len(PNR_SEEDS) - 1:
            raise subprocess.CalledProcessError(proc.returncode, cmd)
        print(f"Routing failed with seed {seed or 'default'} - retrying place & route with seed "
              f"{PNR_SEEDS[attempt + 1]}")


YOSYS_HINT = ("Install oss-cad-suite (https://github.com/YosysHQ/oss-cad-suite-build) "
              "to ~/oss-cad-suite")

_gowin_pack_cmd = None


def gowin_pack_cmd():
    """The command that runs apicula's gowin_pack, as a list: $GOWIN_PACK if
    set, else the bundled tools' gowin_pack or the one on PATH, else the
    apycula module if this Python can import it, else gowin_pack from one of
    find_tool.TOOL_DIRS. Exits with an explanation if none of them exists."""
    global _gowin_pack_cmd
    if _gowin_pack_cmd is not None:
        return _gowin_pack_cmd
    if not os.environ.get("GOWIN_PACK") and bundled_gowin_pack_cmd():
        _gowin_pack_cmd = bundled_gowin_pack_cmd()
        return _gowin_pack_cmd
    found = find_tool("gowin_pack", fallback_dirs=False)
    if found:
        _gowin_pack_cmd = [found]
        return _gowin_pack_cmd
    try:
        import importlib.util
        if importlib.util.find_spec("apycula") is not None:
            _gowin_pack_cmd = [sys.executable, "-m", "apycula.gowin_pack"]
            return _gowin_pack_cmd
    except ImportError:
        pass
    found = find_tool("gowin_pack")
    if found:
        _gowin_pack_cmd = [found]
        return _gowin_pack_cmd
    sys.exit(not_found_message(
        "gowin_pack", "apicula",
        "The Python running this script (" + sys.executable + ") cannot "
        "import apycula either. Install it with `pip install apycula` or "
        "oss-cad-suite"))


# Block RAM primitives: each output clock-enable port and the read-side
# clock-enable port that drives it (see fix_bram_oce()).
BRAM_OCE_PORTS = {
    "SP": [("OCE", "CE")], "SPX9": [("OCE", "CE")],
    "SDPB": [("OCE", "CEB")], "SDPX9B": [("OCE", "CEB")],
    "DPB": [("OCEA", "CEA"), ("OCEB", "CEB")], "DPX9B": [("OCEA", "CEA"), ("OCEB", "CEB")],
    "pROM": [("OCE", "CE")], "pROMX9": [("OCE", "CE")],
}


def fix_bram_oce(json_path):
    """Drives every block RAM's output clock enable (OCE) from its read
    clock enable in yosys's netlist. yosys 0.33 (still what distribution
    packages ship) maps inferred memories with OCE tied low - upstream
    ties it high since January 2024 ("gowin: fix the BRAM mapping").
    Gowin's documentation says OCE is ignored in the bypass read mode
    these memories use, but on a real GW2AR-18 a block with OCE low never
    updates its output: every read returns the same garbage, so the CPU
    traps on its first instruction. Verified on hardware with the SP
    primitive directly: OCE=0 fails half the bits, OCE=1 and OCE=CE read
    back their init content. OCE=CE is used rather than a constant 1
    because routing a constant to all 32 blocks made nextpnr 0.11 fail to
    route the full design; the CE net already reaches each block. Returns
    how many ports were changed."""
    with open(json_path) as f:
        netlist = json.load(f)
    changed = 0
    for module in netlist["modules"].values():
        for cell in module.get("cells", {}).values():
            conns = cell["connections"]
            for oce, ce in BRAM_OCE_PORTS.get(cell["type"], []):
                if oce in conns and ce in conns and conns[oce] != conns[ce]:
                    conns[oce] = list(conns[ce])
                    changed += 1
    if changed:
        with open(json_path, "w") as f:
            json.dump(netlist, f)
    return changed


def build_version_stamp():
    """Everything besides the design itself that a cached result depends
    on: this package's version (platform.txt `version=`, so deploying a new
    release always rebuilds), this script's own contents (fixes to the
    flow, such as fix_bram_oce(), invalidate old results) and the versions
    of yosys, nextpnr and apicula."""
    lines = []
    for line in (REPO_ROOT / "platform.txt").read_text().splitlines():
        if line.startswith("version="):
            lines.append("package " + line.split("=", 1)[1].strip())
    lines.append("script " + hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    for name, flag in (("yosys", "-V"), ("nextpnr-himbaechel", "--version")):
        cmd = [find_tool(name) or name, flag]
        try:
            r = subprocess.run(cmd, capture_output=True, text=True)
            lines.append((r.stdout + r.stderr).strip())
        except OSError:
            lines.append(cmd[0] + " not found")
    # apicula's version, from the Python interpreter gowin_pack runs under.
    cmd = gowin_pack_cmd()
    gowin_pack = cmd[0] if len(cmd) == 1 else None
    version = "unknown"
    if len(cmd) > 1:
        # run as a module: it is this Python's apycula
        try:
            import importlib.metadata
            version = importlib.metadata.version("Apycula")
        except Exception:
            pass
    if gowin_pack:
        try:
            with open(gowin_pack) as f:
                shebang = f.readline()
            python = shebang[2:].strip() if shebang.startswith("#!") else sys.executable
            r = subprocess.run(
                python.split() + ["-c", "import importlib.metadata as m; print(m.version('Apycula'))"],
                capture_output=True, text=True)
            version = r.stdout.strip() or version
        except OSError:
            pass
        if version == "unknown":
            version = hashlib.sha256(Path(gowin_pack).read_bytes()).hexdigest()
    lines.append("apicula " + version)
    return "\n".join(lines)


def hash_design(h, options):
    """Adds every gateware source, the pin constraints and the Tools menu
    options to hash h."""
    for name in GATEWARE_SOURCES + ["sys_parameters.v"]:
        h.update((GATEWARE_SRC / name).read_bytes())
    h.update(CST_FILE.read_bytes())
    h.update(options.encode())


def core_bitstream_cache_key(boot_image_path, options, version_stamp):
    """Hashes everything that can affect a Boot Mode: Flash core bitstream,
    independent of sketch content: the fixed core image (irq_vec.S/boot.S,
    the only trace of those build_bitstream.py otherwise never reads), the
    design (see hash_design()) and build_version_stamp()."""
    h = hashlib.sha256()
    h.update(boot_image_path.read_bytes())
    hash_design(h, options)
    h.update(version_stamp.encode())
    return h.hexdigest()


# --- Routed-design cache (Boot Mode: SRAM) ----------------------------------
#
# For a given set of Tools options the placed-and-routed design is the same
# for every sketch; only the program baked into the SRAM's block RAMs
# differs, and that is just the INIT_RAM_xx parameters of those 32 cells.
# So the first build for an option combination synthesizes and routes the
# design with a "signature" placeholder in the SRAM - every (byte lane,
# bit) column a distinct pseudo-random bit pattern, which identifies which
# block RAM cell holds which column without relying on cell names - and
# caches the routed netlist plus that cell map. Every later build only
# writes its program into those cells' INIT parameters and runs gowin_pack:
# about a minute instead of 15. Set NANOTANG_NO_ROUTED_CACHE=1 to force the
# full flow.

ROUTED_CACHE_DIR = Path.home() / ".cache" / "nanotang" / "routed"
SRAM_LANES = 4
SRAM_DEPTH = 1 << SRAM_ADDR_WIDTH
BRAM_TYPES = set(BRAM_OCE_PORTS)


def routed_cache_key(options, version_stamp):
    h = hashlib.sha256()
    hash_design(h, options)
    h.update(f"sram_addr_width={SRAM_ADDR_WIDTH}".encode())
    h.update(version_stamp.encode())
    return h.hexdigest()


def signature_columns():
    """{(lane, bit): int} - bit a of the int is that column's value at SRAM
    word a. Deterministic, and all 32 columns distinct."""
    cols = {}
    for lane in range(SRAM_LANES):
        for bit in range(8):
            cols[(lane, bit)] = random.Random(0x5EED + lane * 8 + bit).getrandbits(SRAM_DEPTH)
    assert len(set(cols.values())) == len(cols)
    return cols


def write_mem_init(out_dir, columns):
    """Writes mem_init0..3.ini (see gen_mem_init.py) from {(lane, bit): int}."""
    for lane in range(SRAM_LANES):
        lines = []
        for a in range(SRAM_DEPTH):
            byte = 0
            for bit in range(8):
                byte |= ((columns[(lane, bit)] >> a) & 1) << bit
            lines.append(f"{byte:02x}")
        (out_dir / f"mem_init{lane}.ini").write_text("\n".join(lines) + "\n")


def program_columns(bin_path):
    """{(lane, bit): int} for a program binary, like signature_columns()."""
    data = bin_path.read_bytes()
    if len(data) > SRAM_LANES * SRAM_DEPTH:
        raise SystemExit(f"error: program is {len(data)} bytes, SRAM only holds "
                         f"{SRAM_LANES * SRAM_DEPTH} bytes")
    cols = {}
    for lane in range(SRAM_LANES):
        lane_bytes = data[lane::SRAM_LANES]
        for bit in range(8):
            v = 0
            for a, byte in enumerate(lane_bytes):
                if (byte >> bit) & 1:
                    v |= 1 << a
            cols[(lane, bit)] = v
    return cols


def cell_init_value(cell):
    """A 1-bit-wide block RAM cell's contents as an int (bit a = address a).
    INIT_RAM_xx are 256-character binary strings, most significant bit
    first."""
    v = 0
    for r in range(64):
        v |= int(cell["parameters"][f"INIT_RAM_{r:02X}"], 2) << (256 * r)
    return v


def set_cell_init_value(cell, v):
    for r in range(64):
        cell["parameters"][f"INIT_RAM_{r:02X}"] = format((v >> (256 * r)) & ((1 << 256) - 1), "0256b")


def sram_cells(netlist):
    return {name: cell for module in netlist["modules"].values()
            for name, cell in module.get("cells", {}).items()
            if cell["type"] == "SP" and int(cell["parameters"].get("BIT_WIDTH", "0"), 2) == 1}


def map_signature_cells(netlist):
    """{cell name: [lane, bit]} for the routed signature design, or None if
    the SRAM wasn't mapped as the expected 32 16Kx1 block RAMs (then the
    cache can't be used)."""
    lookup = {v: key for key, v in signature_columns().items()}
    cellmap = {}
    for name, cell in sram_cells(netlist).items():
        key = lookup.get(cell_init_value(cell))
        if key is not None:
            cellmap[name] = list(key)
    if len(cellmap) != SRAM_LANES * 8 or len({tuple(k) for k in cellmap.values()}) != SRAM_LANES * 8:
        return None
    return cellmap


def patch_program(netlist, cellmap, columns):
    cells = sram_cells(netlist)
    for name, (lane, bit) in cellmap.items():
        set_cell_init_value(cells[name], columns[(lane, bit)])


def main():
    take_tools_dir_arg(sys.argv)
    if len(sys.argv) not in range(4, 20):
        sys.stderr.write(__doc__)
        return 1

    elf_path, objcopy, build_dir = Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
    ai_accel = len(sys.argv) >= 5 and sys.argv[4] == "1"
    boot_flash = len(sys.argv) >= 6 and sys.argv[5] == "1"
    # SPI Buses / I2C Buses menus: "1" (default, each) is the original
    # always-present primary port - see the docstring above.
    spi_count = int(sys.argv[6]) if len(sys.argv) >= 7 else 1
    i2c_count = int(sys.argv[7]) if len(sys.argv) >= 8 else 1
    hw_muldiv = len(sys.argv) >= 9 and sys.argv[8] == "1"
    i2s_rx = len(sys.argv) >= 10 and sys.argv[9] == "1"
    # Clock Speed menu: all four move together (see the docstring above) -
    # default to the original fixed 27MHz/0/0/32 config if not given.
    clk_freq_hz = int(sys.argv[10]) if len(sys.argv) >= 11 else 27_000_000
    pll_idiv = int(sys.argv[11]) if len(sys.argv) >= 12 else 0
    pll_fbdiv = int(sys.argv[12]) if len(sys.argv) >= 13 else 0
    pll_odiv = int(sys.argv[13]) if len(sys.argv) >= 14 else 32
    pwm_audio = len(sys.argv) >= 15 and sys.argv[14] == "1"
    flash_cache = len(sys.argv) >= 16 and sys.argv[15] == "1"
    compressed = len(sys.argv) >= 17 and sys.argv[16] == "1"
    barrel_shifter = len(sys.argv) >= 18 and sys.argv[17] == "1"
    can = len(sys.argv) >= 19 and sys.argv[18] == "1"
    build_dir.mkdir(parents=True, exist_ok=True)

    # FLASH_DATA payload, independent of boot_flash - empty (0 bytes) if the
    # sketch doesn't use any (objcopy's --only-section produces an empty,
    # valid file rather than erroring when the section doesn't exist).
    # With Tools > Boot Mode: ... + SDRAM it also carries .sdram_image,
    # whose load address (LMA) follows .flash_data in the same partition
    # (see link_cmd_sdram.ld) - -O binary lays sections out by LMA, so
    # this is one contiguous blob starting at the partition's base.
    data_bin_path = build_dir / "data.bin"
    run([
        objcopy, "-O", "binary", "--only-section=.flash_data", "--only-section=.sdram_image",
        str(elf_path), str(data_bin_path),
    ])

    options = (
        f"ai_accel={int(ai_accel)},spi_count={spi_count},i2c_count={i2c_count},"
        f"hw_muldiv={int(hw_muldiv)},i2s_rx={int(i2s_rx)},clk_freq_hz={clk_freq_hz},"
        f"pll_idiv={pll_idiv},pll_fbdiv={pll_fbdiv},pll_odiv={pll_odiv},"
        f"pwm_audio={int(pwm_audio)},flash_cache={int(flash_cache)},"
        f"compressed={int(compressed)},barrel_shifter={int(barrel_shifter)},can={int(can)},"
        f"boot_flash={int(boot_flash)}"
    )
    version_stamp = build_version_stamp()

    cached_fs = None
    routed_dir = None
    if boot_flash:
        # Fixed, sketch-independent core image for SRAM: just the IRQ
        # vector and the boot stub (see link_cmd.ld/boot.S) - everything
        # else is zero-padded by gen_mem_init.py below.
        bin_path = build_dir / "boot_image.bin"
        run([
            objcopy, "-O", "binary",
            "--only-section=.text.irq", "--only-section=.text.boot",
            str(elf_path), str(bin_path),
        ])

        # The sketch's own program (0x400 onward), extracted separately for
        # tools/upload.py to write to flash instead of baking it into SRAM.
        # objcopy's binary output starts at the lowest remaining section's
        # address, so the program's first byte is SRAM address 0x400's
        # byte. boot.S expects the partition to start with the program's
        # size (4 bytes, little-endian) followed by those bytes, so the
        # header is prepended here - without it boot.S took the first
        # instruction for the size and copied from 4 bytes too far on.
        prog_raw_path = build_dir / "prog_flash_raw.bin"
        run([
            objcopy, "-O", "binary",
            "-R", ".text.irq", "-R", ".irq_scratch", "-R", ".text.boot", "-R", ".flash_data",
            "-R", ".sdram_image",
            str(elf_path), str(prog_raw_path),
        ])
        prog = prog_raw_path.read_bytes()
        prog_flash_path = build_dir / "prog_flash.bin"
        prog_flash_path.write_bytes(len(prog).to_bytes(4, "little") + prog)

        cache_key = core_bitstream_cache_key(bin_path, options, version_stamp)
        cached_fs = CACHE_DIR / f"{cache_key}.fs"
        fs_path = build_dir / "prog.fs"
        if cached_fs.exists():
            shutil.copy(cached_fs, fs_path)
            print(f"Reused cached core bitstream ({cached_fs}) - skipped resynthesis")
            print(f"Bitstream written to {fs_path}")
            return 0
    else:
        bin_path = build_dir / "prog.bin"
        run([objcopy, "-O", "binary", "-R", ".flash_data", "-R", ".sdram_image", str(elf_path), str(bin_path)])

        if os.environ.get("NANOTANG_NO_ROUTED_CACHE") != "1":
            routed_dir = ROUTED_CACHE_DIR / routed_cache_key(options, version_stamp)
            fs_path = build_dir / "prog.fs"
            if (routed_dir / "pnrtop.json.gz").exists() and (routed_dir / "cellmap.json").exists():
                # Fast path: only the program changes - patch it into the
                # cached routed design and pack.
                with gzip.open(routed_dir / "pnrtop.json.gz", "rt") as f:
                    netlist = json.load(f)
                cellmap = json.loads((routed_dir / "cellmap.json").read_text())
                patch_program(netlist, cellmap, program_columns(bin_path))
                pnr_json = build_dir / "pnrtop.json"
                with open(pnr_json, "w") as f:
                    json.dump(netlist, f)
                print(f"Reused cached routed design ({routed_dir}) - skipped synthesis and place & route")
                run(gowin_pack_cmd() + ["-d", FAMILY, "-o", str(fs_path), str(pnr_json)])
                print(f"Bitstream written to {fs_path}")
                return 0

    # Copy the gateware sources into the build directory and generate this
    # program's SRAM init files there, next to them, where yosys's
    # read_verilog below picks them up. Never in gateware/src/: its
    # mem_init*.ini are checked-in placeholders (read by the yosys checks
    # and simulations in tools/), and writing there made every build
    # dirty the working tree - and two builds running at the same time
    # could bake each other's program into their bitstreams.
    build_gateware = build_dir / "gateware"
    build_gateware.mkdir(parents=True, exist_ok=True)
    for name in GATEWARE_SOURCES + ["sys_parameters.v"]:
        shutil.copy(GATEWARE_SRC / name, build_gateware / name)
    if routed_dir is not None:
        # First build for these options: route with the signature
        # placeholder, so the result can be cached (see routed_cache_key()).
        write_mem_init(build_gateware, signature_columns())
    else:
        run([
            sys.executable,
            str(REPO_ROOT / "tools" / "gen_mem_init.py"),
            str(bin_path),
            str(SRAM_ADDR_WIDTH),
            str(build_gateware),
        ])

    # All gateware sources are always read - yosys prunes any module never
    # instantiated from `top` (confirmed via its "Removing unused module"
    # output), so ai_accel_bus.v and its dependencies cost nothing when
    # WITH_AI_ACCEL isn't defined and top.v's `ifdef excludes them.
    defines = []
    if ai_accel:
        defines.append("-DWITH_AI_ACCEL")
    if boot_flash:
        defines.append("-DBOOT_FROM_FLASH")
    if spi_count >= 1:
        defines.append("-DWITH_SPI1")
    if spi_count >= 2:
        defines.append("-DWITH_SPI2")
    if i2c_count >= 1:
        defines.append("-DWITH_I2C1")
    if i2c_count >= 2:
        defines.append("-DWITH_I2C2")
    if hw_muldiv:
        defines.append("-DWITH_HW_MULDIV")
    if i2s_rx:
        defines.append("-DWITH_I2S_RX")
    if pwm_audio:
        defines.append("-DWITH_PWM_AUDIO")
    if flash_cache:
        defines.append("-DWITH_FLASH_CACHE")
    if compressed:
        defines.append("-DWITH_COMPRESSED_ISA")
    if barrel_shifter:
        defines.append("-DWITH_BARREL_SHIFTER")
    if can:
        defines.append("-DWITH_CAN")
    # Clock Speed menu - always passed explicitly (rather than relying on
    # the Verilog `ifndef defaults) so the PLL dividers and CLK_FREQ can
    # never drift out of step with each other.
    defines.append(f"-DCLK_FREQ_HZ={clk_freq_hz}")
    defines.append(f"-DPLL_IDIV_SEL={pll_idiv}")
    defines.append(f"-DPLL_FBDIV_SEL={pll_fbdiv}")
    defines.append(f"-DPLL_ODIV_SEL={pll_odiv}")
    define = "read_verilog " + " ".join(defines) if defines else "read_verilog"
    json_path = build_dir / "top.json"
    # Newer yosys (seen with 0.69) can leave $buf cells in the netlist -
    # driving registers some of whose bits were optimized away - which
    # nextpnr-himbaechel can't place ("no BELs remaining to implement cell
    # type '$buf'"). simplemap turns them back into plain connections; with
    # older yosys there are none and it does nothing.
    run([
        require_tool("yosys", "Verilog synthesis", YOSYS_HINT),
        "-p",
        f"{define} {' '.join(GATEWARE_SOURCES)}; synth_gowin -top top; "
        f"simplemap t:$buf; opt_clean; write_json {json_path}",
    ], cwd=build_gateware)
    changed = fix_bram_oce(json_path)
    if changed:
        print(f"Connected {changed} block RAM output enables (OCE) to their read enables - see fix_bram_oce()")

    pnr_json = build_dir / "pnrtop.json"
    place_and_route(json_path, pnr_json)

    fs_path = build_dir / "prog.fs"
    if routed_dir is not None:
        with open(pnr_json) as f:
            netlist = json.load(f)
        cellmap = map_signature_cells(netlist)
        if cellmap is None:
            # Unexpected SRAM mapping: can't cache. Redo the build with the
            # real program in the SRAM instead of the signature.
            print("warning: SRAM block RAMs not mapped as expected - routed-design cache not used")
            os.environ["NANOTANG_NO_ROUTED_CACHE"] = "1"
            return main()
        # Store atomically: a half-written entry must never look complete.
        tmp_dir = routed_dir.with_name(routed_dir.name + f".tmp{os.getpid()}")
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True)
        with gzip.open(tmp_dir / "pnrtop.json.gz", "wt") as f:
            json.dump(netlist, f)
        (tmp_dir / "cellmap.json").write_text(json.dumps(cellmap))
        (tmp_dir / "key.txt").write_text(options + "\n" + version_stamp + "\n")
        shutil.rmtree(routed_dir, ignore_errors=True)
        os.replace(tmp_dir, routed_dir)
        print(f"Cached routed design at {routed_dir} for future fast builds")
        patch_program(netlist, cellmap, program_columns(bin_path))
        with open(pnr_json, "w") as f:
            json.dump(netlist, f)

    run(gowin_pack_cmd() + ["-d", FAMILY, "-o", str(fs_path), str(pnr_json)])

    if cached_fs is not None:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(fs_path, cached_fs)
        print(f"Cached core bitstream at {cached_fs} for future fast uploads")

    print(f"Bitstream written to {fs_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
