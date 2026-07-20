#pragma once

#include <Arduino.h>

constexpr uint8_t kSpectrumBandCount = 14;

enum class AppState {
  Provisioning,
  ConnectingWifi,
  ConnectingServer,
  StartingRecording,
  Ready,
  AutoListening,
  AutoRecording,
  Recording,
  Receiving,
  Transcribing,
  Inserting,
  Sent,
  Cancelled,
  Error,
};

enum class OutputAction { Copy, Paste, PasteEnter, PasteCtrlEnter };

struct DeviceConfig {
  String ssid;
  String password;
  String serverHost = "ai-dictation.local";
  uint16_t serverPort = 8765;
  String deviceName;
  OutputAction action = OutputAction::Paste;
  uint16_t maxRecordingSeconds = 120;
  bool soundsEnabled = true;

  bool valid() const {
    return !ssid.isEmpty() && !serverHost.isEmpty();
  }
};

inline const char* actionId(OutputAction action) {
  switch (action) {
    case OutputAction::Copy: return "copy";
    case OutputAction::Paste: return "paste";
    case OutputAction::PasteEnter: return "paste_enter";
    case OutputAction::PasteCtrlEnter: return "paste_ctrl_enter";
  }
  return "paste";
}

inline const char* actionLabel(OutputAction action) {
  switch (action) {
    case OutputAction::Copy: return "COPY";
    case OutputAction::Paste: return "PASTE";
    case OutputAction::PasteEnter: return "PASTE + ENTER";
    case OutputAction::PasteCtrlEnter: return "PASTE + CTRL+ENTER";
  }
  return "PASTE";
}

// Protocol v1 compatibility fields let new firmware work with an older server.
inline const char* legacyProfile(OutputAction action) {
  switch (action) {
    case OutputAction::Copy: return "clipboard";
    case OutputAction::Paste: return "chatgpt";
    case OutputAction::PasteEnter: return "terminal";
    case OutputAction::PasteCtrlEnter: return "vscode";
  }
  return "chatgpt";
}

inline const char* legacyMode(OutputAction action) {
  switch (action) {
    case OutputAction::PasteEnter: return "enter";
    case OutputAction::PasteCtrlEnter: return "ctrl_enter";
    case OutputAction::Copy:
    case OutputAction::Paste: return "insert";
  }
  return "insert";
}
