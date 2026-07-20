#include "UserInterface.h"

void UserInterface::begin() {
  M5.Display.setRotation(1);
  M5.Display.setTextSize(1);
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.fillScreen(TFT_BLACK);
}

void UserInterface::showProvisioning(const String& apName, const String& ip) {
  if (!screenEnabled_) return;
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setCursor(8, 8);
  M5.Display.setTextColor(TFT_CYAN, TFT_BLACK);
  M5.Display.println("FIRST SETUP");
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.println("Connect phone/PC to:");
  M5.Display.println(apName);
  M5.Display.println("Open: http://" + ip);
}

const char* UserInterface::stateTitle(AppState state) const {
  switch (state) {
    case AppState::Ready: return "VOXCORTEX";
    case AppState::AutoListening: return "AUTO LISTEN";
    case AppState::AutoRecording: return "AUTO SPEECH";
    case AppState::Recording: return "LISTENING";
    case AppState::Receiving: return "RECEIVING";
    case AppState::Transcribing: return "TRANSCRIBING";
    case AppState::Inserting: return "INSERTING";
    case AppState::Sent: return "DONE";
    case AppState::Cancelled: return "CANCELLED";
    case AppState::Error: return "ERROR";
    case AppState::ConnectingWifi: return "CONNECTING WIFI";
    case AppState::ConnectingServer: return "CONNECTING PC";
    case AppState::StartingRecording: return "STARTING MIC";
    case AppState::Provisioning: return "SETUP";
  }
  return "VOXCORTEX";
}

void UserInterface::showState(AppState state, const String& message, const DeviceConfig& config,
                              bool wifiOk, bool serverOk) {
  if (!screenEnabled_) return;
  lastState_ = state;
  recordingScreenDrawn_ = false;
  M5.Display.fillScreen(TFT_BLACK);
  M5.Display.setCursor(6, 5);
  M5.Display.setTextColor(state == AppState::Error ? TFT_RED : TFT_CYAN, TFT_BLACK);
  M5.Display.println(stateTitle(state));
  M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
  M5.Display.printf("WiFi: %-3s  PC: %s\n", wifiOk ? "OK" : "---", serverOk ? "CONNECTED" : "---");
  M5.Display.printf("ACTION: %s\n", actionLabel(config.action));
  int battery = M5.Power.getBatteryLevel();
  M5.Display.printf("BATTERY: %d%%\n", battery);
  M5.Display.setTextColor(TFT_YELLOW, TFT_BLACK);
  M5.Display.println(message.substring(0, 36));
}

void UserInterface::showRecording(uint32_t elapsedMs, const uint8_t spectrum[kSpectrumBandCount],
                                  bool loud, bool clipping, bool autoMode, bool speech) {
  if (!screenEnabled_) return;
  uint32_t seconds = elapsedMs / 1000;
  const uint16_t spectrumColor = clipping ? TFT_RED : (loud ? TFT_YELLOW : TFT_GREEN);

  if (!recordingScreenDrawn_) {
    M5.Display.fillScreen(TFT_BLACK);
    M5.Display.setCursor(6, 5);
    M5.Display.setTextColor(TFT_CYAN, TFT_BLACK);
    M5.Display.print(autoMode ? (speech ? "AUTO SPEECH" : "AUTO LISTEN") : "LISTENING");
    M5.Display.setCursor(92, 5);
    M5.Display.setTextColor(TFT_DARKGREY, TFT_BLACK);
    M5.Display.print("SPECTRUM");
    M5.Display.drawRect(5, 25, 226, 78, TFT_DARKGREY);
    M5.Display.setCursor(6, 111);
    M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
    M5.Display.println(autoMode ? "Double M5 to stop" : "Release A to send");
    recordingScreenDrawn_ = true;
    lastAutoSpeech_ = speech;
    lastRecordingSecond_ = UINT32_MAX;
    for (uint8_t band = 0; band < kSpectrumBandCount; ++band) lastSpectrumHeights_[band] = 0;
    lastSpectrumColor_ = 0;
  }

  if (autoMode && speech != lastAutoSpeech_) {
    M5.Display.fillRect(6, 5, 82, 10, TFT_BLACK);
    M5.Display.setCursor(6, 5);
    M5.Display.setTextColor(TFT_CYAN, TFT_BLACK);
    M5.Display.print(speech ? "AUTO SPEECH" : "AUTO LISTEN");
    lastAutoSpeech_ = speech;
  }

  if (autoMode && !speech) {
    if (lastRecordingSecond_ != UINT32_MAX - 1) {
      M5.Display.fillRect(196, 5, 38, 10, TFT_BLACK);
      M5.Display.setCursor(202, 5);
      M5.Display.setTextColor(TFT_GREEN, TFT_BLACK);
      M5.Display.print("AUTO");
      lastRecordingSecond_ = UINT32_MAX - 1;
    }
  } else if (seconds != lastRecordingSecond_) {
    M5.Display.fillRect(196, 5, 38, 10, TFT_BLACK);
    M5.Display.setCursor(196, 5);
    M5.Display.setTextColor(TFT_WHITE, TFT_BLACK);
    M5.Display.printf("%02lu:%02lu", seconds / 60, seconds % 60);
    lastRecordingSecond_ = seconds;
  }

  if (millis() - lastRecordingDraw_ >= 50) {
    lastRecordingDraw_ = millis();
    constexpr uint8_t kBaseY = 100;
    constexpr uint8_t kMaximumHeight = 72;
    constexpr uint8_t kBarWidth = 12;
    constexpr uint8_t kBarStep = 16;
    const bool colorChanged = spectrumColor != lastSpectrumColor_;
    for (uint8_t band = 0; band < kSpectrumBandCount; ++band) {
      const uint8_t height = map(spectrum[band], 0, 255, 0, kMaximumHeight);
      const uint8_t previous = lastSpectrumHeights_[band];
      if (height == previous && !colorChanged) continue;

      const int16_t x = 8 + band * kBarStep;
      if (colorChanged) {
        M5.Display.fillRect(x, kBaseY - kMaximumHeight, kBarWidth, kMaximumHeight, TFT_BLACK);
        if (height > 0) M5.Display.fillRect(x, kBaseY - height, kBarWidth, height, spectrumColor);
      } else if (height > previous) {
        M5.Display.fillRect(x, kBaseY - height, kBarWidth, height - previous, spectrumColor);
      } else {
        M5.Display.fillRect(x, kBaseY - previous, kBarWidth, previous - height, TFT_BLACK);
      }
      lastSpectrumHeights_[band] = height;
    }
    lastSpectrumColor_ = spectrumColor;
  }
}

void UserInterface::setScreenEnabled(bool enabled) {
  screenEnabled_ = enabled;
  M5.Display.setBrightness(enabled ? 100 : 0);
}
