/* arduino-tangnano20k-specific addition (not part of arduino-libraries/SD,
 * see docs/PERIPHERALS.md "SD card"): an FS.h so libraries written against
 * the ESP32/ESP8266/RP2040 cores' <FS.h> build here, backed by this SD
 * library. fs::File and fs::FS are this library's own File and SDClass, so
 * `File f = SD.open(...)` passes straight to any function taking fs::File&.
 * Like SD.h, it needs Tools > SD Card: Enabled (GPLv3). */

#ifndef __TANGNANO20K_FS_H__
#define __TANGNANO20K_FS_H__

#include "SD.h"

namespace fs {
using File = SDLib::File;
using FS = SDLib::SDClass;
} // namespace fs

using fs::FS;

#endif
