#pragma once

#include <ArduinoJson.h>
#include <WebSocketsClient.h>
#include "AppTypes.h"
#include "AudioCapture.h"

using StatusCallback = std::function<void(AppState, const String&)>;
using SettingsCallback = std::function<void(const DeviceConfig&)>;

class ProtocolClient {
 public:
  void begin(const DeviceConfig& config, const String& deviceId, StatusCallback callback,
             SettingsCallback settingsCallback);
  void tick();
  bool connected() const { return connected_; }
  bool startRecording(uint32_t sequence, OutputAction action);
  bool sendAudio(const AudioBlock& block);
  void endRecording(uint32_t sequence, bool cancelled);
  void cancel(uint32_t sequence);
  void sendTelemetry(int32_t batteryPercent, bool charging, int32_t rssi);

 private:
  void onEvent(WStype_t type, uint8_t* payload, size_t length);
  void sendHello();
  void applySettings(JsonDocument& document);
  AppState stateFromId(const String& value) const;

  WebSocketsClient socket_;
  DeviceConfig config_;
  String deviceId_;
  StatusCallback callback_;
  SettingsCallback settingsCallback_;
  bool connected_ = false;
};
