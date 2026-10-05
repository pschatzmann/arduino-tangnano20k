#include "AIAccelerator.h"
#include "tangnano20k_soc.h"
#include <stdlib.h>
#include <string.h>

AIAccelerator *AIAccelerator::currentInstance_ = nullptr;

AIAccelerator::AIAccelerator()
{
}

AIAccelerator::AIAccelerator(uint16_t cinPadded, uint8_t k, uint8_t rows)
{
  config(cinPadded, k, rows);
}

AIAccelerator::~AIAccelerator()
{
  free(weights_);
  free(results_);
  if (currentInstance_ == this)
    currentInstance_ = nullptr;
}

void AIAccelerator::config(uint16_t cinPadded, uint8_t k, uint8_t rows)
{
  cinPadded_ = cinPadded;
  k_ = k;
  rows_ = rows;
}

bool AIAccelerator::begin(void)
{
  allocate();
  return weights_ && results_;
}

bool AIAccelerator::begin(uint16_t cinPadded, uint8_t k, uint8_t rows)
{
  config(cinPadded, k, rows);
  return begin();
}

void AIAccelerator::allocate(void)
{
  weightsLen_ = (size_t)rows_ * k_ * cinPadded_;
  weights_ = (int8_t *)malloc(weightsLen_);
  results_ = (int32_t *)malloc((size_t)rows_ * k_ * sizeof(int32_t));
}

void AIAccelerator::loadWeights(const int8_t *data, size_t len)
{
  if (weights_)
    memcpy(weights_, data, len < weightsLen_ ? len : weightsLen_);

  // New weights - whatever this instance last pushed to hardware (if
  // anything) no longer matches, so force a reprogram on the next
  // compute() even if this instance happens to still be "current".
  if (currentInstance_ == this)
    currentInstance_ = nullptr;
}

void AIAccelerator::ensureLoadedInHardware(void)
{
  if (currentInstance_ == this)
    return;

  TANGNANO20K_AI_CFG_REG = ((uint32_t)rows_ << 24) | ((uint32_t)k_ << 16) | cinPadded_;

  size_t rowBytes = (size_t)k_ * cinPadded_;
  const uint8_t *bytes = (const uint8_t *)weights_;
  for (uint8_t row = 0; row < rows_; row++)
  {
    TANGNANO20K_AI_WEIGHT_SEL_REG = row;
    const uint8_t *rowData = bytes + (size_t)row * rowBytes;
    for (size_t i = 0; i < rowBytes; i++)
      TANGNANO20K_AI_WEIGHT_DATA_REG = rowData[i];
  }

  currentInstance_ = this;
}

int32_t *AIAccelerator::compute(const int8_t *window, size_t len)
{
  if (!results_ || !weights_)
    return nullptr;

  ensureLoadedInHardware();

  TANGNANO20K_AI_ACT_RESET_REG = 1;
  const uint8_t *bytes = (const uint8_t *)window;
  for (size_t i = 0; i < len; i++)
    TANGNANO20K_AI_ACT_DATA_REG = bytes[i];
  TANGNANO20K_AI_START_REG = 1;

  // The engine stores results at row * kMaxTaps + tap (ai_accel_bus.v's
  // RESULT_ADDR), whatever k is; results_ is packed as row * k_ + tap.
  for (uint8_t row = 0; row < rows_; row++)
  {
    for (uint8_t tap = 0; tap < k_; tap++)
    {
      TANGNANO20K_AI_RESULT_ADDR_REG = (uint32_t)row * kMaxTaps + tap;
      results_[row * k_ + tap] = (int32_t)TANGNANO20K_AI_RESULT_DATA_REG;
    }
  }
  return results_;
}
