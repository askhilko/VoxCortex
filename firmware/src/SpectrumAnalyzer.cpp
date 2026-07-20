#include "SpectrumAnalyzer.h"

#include <math.h>

namespace {
constexpr float kPi = 3.14159265358979323846f;
constexpr float kFrequencies[kSpectrumBandCount] = {
    100.0f, 150.0f, 220.0f, 320.0f, 460.0f, 680.0f, 1000.0f,
    1450.0f, 2100.0f, 3000.0f, 4000.0f, 5000.0f, 6000.0f, 7000.0f,
};
}  // namespace

void SpectrumAnalyzer::begin(uint32_t sampleRate) {
  for (uint8_t band = 0; band < kSpectrumBandCount; ++band) {
    coefficients_[band] = 2.0f * cosf(2.0f * kPi * kFrequencies[band] / sampleRate);
    values_[band] = 0;
  }
}

void SpectrumAnalyzer::analyze(const int16_t* samples, uint16_t count) {
  if (samples == nullptr || count == 0) return;

  int64_t sum = 0;
  for (uint16_t i = 0; i < count; ++i) sum += samples[i];
  const float mean = static_cast<float>(sum) / count;

  for (uint8_t band = 0; band < kSpectrumBandCount; ++band) {
    float previous = 0.0f;
    float previous2 = 0.0f;
    const float coefficient = coefficients_[band];
    for (uint16_t i = 0; i < count; ++i) {
      const float current = static_cast<float>(samples[i]) - mean + coefficient * previous - previous2;
      previous2 = previous;
      previous = current;
    }

    float power = previous2 * previous2 + previous * previous - coefficient * previous * previous2;
    if (power < 0.0f) power = 0.0f;
    const float magnitude = sqrtf(power) / count;
    const float decibels = 20.0f * log10f(magnitude + 1.0f);
    int target = static_cast<int>((decibels - 18.0f) * (255.0f / 58.0f));
    target = constrain(target, 0, 255);

    const int current = values_[band];
    if (target >= current) {
      values_[band] = static_cast<uint8_t>(current + ((target - current) * 3) / 4);
    } else {
      values_[band] = static_cast<uint8_t>(current - ((current - target + 7) / 8));
    }
  }
}

void SpectrumAnalyzer::copy(uint8_t output[kSpectrumBandCount]) const {
  for (uint8_t band = 0; band < kSpectrumBandCount; ++band) output[band] = values_[band];
}
