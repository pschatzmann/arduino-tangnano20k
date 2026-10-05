#pragma once

#include <Arduino.h>

/* The accelerator gateware only exists in the bitstream when Tools > AI
 * Accelerator is enabled. Fail at compile time rather than letting a
 * sketch talk to registers that aren't there (TANGNANO20K_AI_ACCEL is set
 * by platform.txt - see docs/ARCHITECTURE.md "Preprocessor defines").
 * Libraries that only *optionally* use the engine should check
 * TANGNANO20K_AI_ACCEL themselves and not include this header when it's 0. */
#if defined(TANGNANO20K_AI_ACCEL) && !TANGNANO20K_AI_ACCEL
#error "AIAccelerator needs Tools > AI Accelerator: Enabled - see docs/PERIPHERALS.md \"AI accelerator\""
#endif

/* On-chip INT8 dot-product accelerator: same compute engine
 * (dot_product_engine.v) as the standalone NanoTangAI project's
 * SPI-attached TangNanoAccelerator, but wired directly onto this core's
 * own picorv32 bus (gateware/src/ai_accel_bus.v) instead of going through
 * an external SPI link to a second Tang Nano 20K board - see
 * docs/PERIPHERALS.md "AI accelerator".
 *
 * Usage mirrors dspsDotProdS8()'s role in TinyTTS's Ops.h (see NanoTangAI's
 * own docs/architecture.md): construct once with the tile shape, load a
 * kWeightTileRows-row weight tile once (loadWeights()), then for each
 * timestep's gathered activation window, compute() returns the same raw
 * INT8xINT8->INT32 dot products dspsDotProdS8() would have, one per
 * (row, tap) - rescaling (x_scale/w_rowScale/bias) is unchanged, still
 * done by the caller in float, exactly as Ops.h's conv1d() already does.
 *
 * Multiple instances: there is exactly one physical engine
 * (gateware/src/ai_accel_bus.v isn't duplicated - it's a real LUT/BRAM
 * cost, see docs/BUILDING.md "AI Accelerator"), so instances share it by
 * time-slicing rather than running concurrently. Each instance keeps its
 * own weight tile and results buffer in heap-allocated copies (this
 * core's heap is the embedded 8MB SDRAM); compute() re-programs the
 * hardware from that copy only if a *different* instance's compute() ran
 * more recently, so using a single instance repeatedly costs nothing
 * extra, and alternating between instances costs one weight-tile reload
 * (up to rows*k*cinPadded byte-at-a-time register writes) each time you
 * switch. Because of this sharing, one instance's compute() call must
 * fully finish (it always returns only once the result is ready - see
 * compute()) before any *other* instance's compute() runs; there's no
 * way to interleave two instances' in-flight computations, since both
 * would be reading/writing the same physical result registers. */
class AIAccelerator
{
public:
  /// Leaves the shape unset - call begin(cinPadded, k, rows) before
  /// loadWeights()/compute(). Useful when the shape isn't known until
  /// setup() (e.g. a global instance whose tile size depends on runtime
  /// configuration).
  AIAccelerator();

  /// `rows` must be <= 8, `k` <= 16, `cinPadded` a multiple of 4 (the
  /// gateware's fixed ROWS/MAX_K/LANES parameters - see
  /// gateware/src/ai_accel_bus.v; any multiple of 16, NanoTangAI's
  /// original requirement, still works), and `k * cinPadded` <= 1024. Only stores the shape - call begin()
  /// before loadWeights()/compute() to actually allocate this instance's
  /// weight/results buffers.
  AIAccelerator(uint16_t cinPadded, uint8_t k, uint8_t rows);
  ~AIAccelerator();

  /// Allocates this instance's own weight buffer (rows*k*cinPadded bytes)
  /// and results buffer (rows*k int32_t entries) on the heap (this core's
  /// heap is the embedded 8MB SDRAM), using the shape passed to the
  /// constructor. Call once, before loadWeights()/compute(). Returns
  /// false if either allocation failed (out of heap) - compute() returns
  /// nullptr in that case rather than crashing.
  bool begin(void);

  /// Same as begin(void), but also sets the shape first - for use with
  /// the empty constructor above, when the shape wasn't known at
  /// construction time. Equivalent to calling the shape-setting
  /// constructor followed by begin(void).
  bool begin(uint16_t cinPadded, uint8_t k, uint8_t rows);

  /// `data` is `rows*k*cinPadded` INT8 bytes, row-major: row0's
  /// `k*cinPadded` bytes (tap-major, `[tap][cinPadded]`) then row1's, etc -
  /// exactly the tile layout TinyTTS's Ops.h already builds for INT8
  /// weights. Copies `data` into this instance's own heap buffer (see the
  /// class comment above) rather than pushing it to hardware immediately;
  /// only needs to be called once per instance, even if the hardware gets
  /// re-programmed for another instance in between compute() calls.
  void loadWeights(const int8_t *data, size_t len);

  /// `window` is `k*cinPadded` INT8 bytes, `[tap][cinPadded]`, zero-padded
  /// at sequence boundaries. Re-programs the hardware's config/weights
  /// first if a different instance last used the engine (see the class
  /// comment above), starts the engine, blocks (via bus backpressure, not
  /// a software poll loop or a delay sized from a cycle-count formula)
  /// until it's done, and returns this instance's own results buffer -
  /// `rows*k` raw INT32 dot products, row-major [row][tap], valid until
  /// this instance's next compute() call. Returns nullptr if begin()
  /// wasn't called or its allocation failed.
  int32_t *compute(const int8_t *window, size_t len);

private:
  // ai_accel_bus.v's MAX_K: the result memory has this many slots per row.
  static const uint8_t kMaxTaps = 16;

  uint16_t cinPadded_ = 0;
  uint8_t k_ = 0;
  uint8_t rows_ = 0;
  int8_t *weights_ = nullptr;
  size_t weightsLen_ = 0; // rows_*k_*cinPadded_ bytes, set by allocate()
  int32_t *results_ = nullptr;

  void config(uint16_t cinPadded, uint8_t k, uint8_t rows);
  void allocate(void);
  void ensureLoadedInHardware(void);

  // Which instance's config/weights are currently live in the one
  // physical engine - nullptr means "unknown/none", forcing the next
  // compute() (on any instance) to reprogram it.
  static AIAccelerator *currentInstance_;
};
