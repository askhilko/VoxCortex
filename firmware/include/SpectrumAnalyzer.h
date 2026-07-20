#pragma once

#include <Arduino.h>

#include "AppTypes.h"

class SpectrumAnalyzer {
 public:
  void begin(uint32_t sampleRate);
  void analyze(const int16_t* samples, uint16_t count);
  void copy(uint8_t output[kSpectrumBandCount]) const;

 private:
  float coefficients_[kSpectrumBandCount]{};
  volatile uint8_t values_[kSpectrumBandCount]{};
};
