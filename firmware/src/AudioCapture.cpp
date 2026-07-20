#include "AudioCapture.h"

bool AudioCapture::begin() {
  if (running_) return true;
  if (queue_ == nullptr) queue_ = xQueueCreate(8, sizeof(AudioBlock));
  if (queue_ == nullptr) return false;
  xQueueReset(queue_);
  overflowed_ = false;
  loudUntil_ = 0;
  clippingUntil_ = 0;
  // The start beep already stops the speaker. Calling end() a second time makes
  // the ESP32 I2S driver report that port 1 is not installed.
  if (M5.Speaker.isRunning()) M5.Speaker.end();
  auto config = M5.Mic.config();
  config.sample_rate = 16000;
  M5.Mic.config(config);
  if (!M5.Mic.begin()) return false;
  spectrum_.begin(16000);
  running_ = true;
  if (xTaskCreatePinnedToCore(taskEntry, "mic-capture", 4096, this, 3, &task_, 0) != pdPASS) {
    running_ = false;
    M5.Mic.end();
    return false;
  }
  return true;
}

void AudioCapture::end() {
  running_ = false;
  if (task_ != nullptr) {
    for (uint8_t i = 0; i < 50 && task_ != nullptr; ++i) vTaskDelay(1);
  }
  while (M5.Mic.isRecording()) vTaskDelay(1);
  M5.Mic.end();
}

bool AudioCapture::pop(AudioBlock& block) {
  return queue_ != nullptr && xQueueReceive(queue_, &block, 0) == pdTRUE;
}

void AudioCapture::taskEntry(void* context) {
  static_cast<AudioCapture*>(context)->taskLoop();
}

void AudioCapture::taskLoop() {
  AudioBlock block{};
  block.samples = 512;
  while (running_) {
    if (!M5.Mic.record(block.data, block.samples, 16000)) {
      vTaskDelay(1);
      continue;
    }
    uint32_t peak = 0;
    uint16_t saturatedSamples = 0;
    for (uint16_t i = 0; i < block.samples; ++i) {
      uint32_t value = abs(static_cast<int32_t>(block.data[i]));
      if (value > peak) peak = value;
      if (value >= 32500) ++saturatedSamples;
    }
    level_ = static_cast<uint16_t>(peak);
    block.peak = level_;
    if (peak >= 28000) loudUntil_ = millis() + 200;
    if (saturatedSamples >= 3) clippingUntil_ = millis() + 700;
    spectrum_.analyze(block.data, block.samples);
    if (xQueueSend(queue_, &block, 0) != pdTRUE) {
      overflowed_ = true;
      running_ = false;
    }
  }
  task_ = nullptr;
  vTaskDelete(nullptr);
}
