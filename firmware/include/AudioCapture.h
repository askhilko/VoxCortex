#pragma once

#include <Arduino.h>
#include <M5Unified.h>

#include "SpectrumAnalyzer.h"

struct AudioBlock {
  uint16_t samples;
  uint16_t peak;
  int16_t data[512];
};

class AudioCapture {
 public:
  bool begin();
  void end();
  bool pop(AudioBlock& block);
  void copySpectrum(uint8_t output[kSpectrumBandCount]) const { spectrum_.copy(output); }
  bool overflowed() const { return overflowed_; }
  uint16_t level() const { return level_; }
  bool loud() const { return static_cast<int32_t>(loudUntil_ - millis()) > 0; }
  bool clipping() const { return static_cast<int32_t>(clippingUntil_ - millis()) > 0; }
  bool running() const { return running_; }

 private:
  static void taskEntry(void* context);
  void taskLoop();

  QueueHandle_t queue_ = nullptr;
  TaskHandle_t task_ = nullptr;
  volatile bool running_ = false;
  volatile bool overflowed_ = false;
  volatile uint16_t level_ = 0;
  volatile uint32_t loudUntil_ = 0;
  volatile uint32_t clippingUntil_ = 0;
  SpectrumAnalyzer spectrum_;
};
