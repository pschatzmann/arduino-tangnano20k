// Vendored from ../../../NanoTangAI/gateware/rtl/int8_mac_lane.v,
// part of the AI accelerator integration - see docs/PERIPHERALS.md "AI accelerator".
// License: Apache-2.0 (see that project's library.properties/README;
// same author as this repo). One deliberate deviation from the vendored
// original: under synthesis the multiply uses a Gowin MULT9X9 DSP block
// instead of `*`. This yosys (0.33) has no DSP inference for Gowin, and
// maps each 8x8 signed `*` onto ~250 LUT4s plus muxes - with 32 lanes
// that alone overflowed the GW2AR-18. Simulation (no SYNTHESIS define)
// keeps the plain `*`, since yosys's MULT9X9 is a blackbox with no model.
// The product is still registered in fabric exactly as before.
//
// Keep it that way, with the MULT9X9's own input registers off
// (AREG/BREG = 0). Registering the operands in the DSP block instead
// (AREG/BREG = 1, CE = en - once used to dodge a gowin_pack bug in
// apicula 0.33 that the bundled toolchain has since fixed) packs fine,
// but on hardware every product came out as 0.
//
`timescale 1ns / 1ps
//
// Single INT8 x INT8 -> INT32-safe multiply-accumulate lane.
//
// One clock of pipeline latency: `prod` registers the product of `a`/`b`
// (both signed 8-bit, matching TinyTTS's symmetric-quantized activations
// and weights, see WeightStore.h dtype 2 / Ops.h conv1d()'s `xq`/`wtile_i8`).
// `clear` loads `prod` with the multiply result instead of accumulating,
// used by dot_product_engine.v to start a new reduction chunk.
//
module int8_mac_lane (
    input  wire        clk,
    input  wire        rst_n,
    input  wire         en,     // advance the pipeline this cycle
    input  wire  signed [7:0] a,
    input  wire  signed [7:0] b,
    output reg   signed [16:0] prod  // max |a*b| = 128*128 = 16384, fits comfortably in 17 bits
);

`ifdef SYNTHESIS
  wire [17:0] mult_out;
  MULT9X9 #(
      .AREG(1'b0), .BREG(1'b0), .OUT_REG(1'b0), .PIPE_REG(1'b0),
      .ASIGN_REG(1'b0), .BSIGN_REG(1'b0), .SOA_REG(1'b0)
  ) u_mult (
      .A({a[7], a}), .B({b[7], b}),   // sign-extended to 9 bits
      .SIA(9'd0), .SIB(9'd0),
      .ASIGN(1'b1), .BSIGN(1'b1),
      .ASEL(1'b0), .BSEL(1'b0),       // use A/B, not the shift-chain inputs
      .CE(1'b1), .CLK(clk), .RESET(1'b0),
      .DOUT(mult_out),
      .SOA(), .SOB()
  );
`else
  wire signed [17:0] mult_out = $signed(a) * $signed(b);
`endif

  always @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      prod <= 17'sd0;
    end else if (en) begin
      prod <= mult_out[16:0];
    end
  end

endmodule
