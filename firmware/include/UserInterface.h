#pragma once

#include <M5Unified.h>
#include "AppTypes.h"

class UserInterface {
 public:
  void begin();
  void showProvisioning(const String& apName, const String& ip);
  void showState(AppState state, const String& message, const DeviceConfig& config,
                 bool wifiOk, bool serverOk);
  void showRecording(uint32_t elapsedMs, const uint8_t spectrum[kSpectrumBandCount],
                     bool loud, bool clipping, bool autoMode = false, bool speech = true);
  void setScreenEnabled(bool enabled);
  bool screenEnabled() const { return screenEnabled_; }

 private:
  const char* stateTitle(AppState state) const;
  bool screenEnabled_ = true;
  AppState lastState_ = AppState::Error;
  uint32_t lastRecordingDraw_ = 0;
  uint32_t lastRecordingSecond_ = UINT32_MAX;
  uint8_t lastSpectrumHeights_[kSpectrumBandCount]{};
  uint16_t lastSpectrumColor_ = 0;
  bool recordingScreenDrawn_ = false;
  bool lastAutoSpeech_ = false;
};
