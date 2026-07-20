#include "ProtocolClient.h"
#include "FirmwareInfo.h"

namespace {
bool parseAction(const String& value, OutputAction& action) {
  if (value == "copy") action = OutputAction::Copy;
  else if (value == "paste") action = OutputAction::Paste;
  else if (value == "paste_enter") action = OutputAction::PasteEnter;
  else if (value == "paste_ctrl_enter") action = OutputAction::PasteCtrlEnter;
  else return false;
  return true;
}
}  // namespace

void ProtocolClient::begin(const DeviceConfig& config, const String& deviceId, StatusCallback callback,
                           SettingsCallback settingsCallback) {
  config_ = config;
  deviceId_ = deviceId;
  callback_ = callback;
  settingsCallback_ = settingsCallback;
  socket_.begin(config.serverHost.c_str(), config.serverPort, "/ws");
  socket_.setReconnectInterval(3000);
  socket_.enableHeartbeat(15000, 3000, 2);
  socket_.onEvent([this](WStype_t type, uint8_t* payload, size_t length) { onEvent(type, payload, length); });
}

void ProtocolClient::tick() { socket_.loop(); }

void ProtocolClient::sendHello() {
  JsonDocument document;
  document["type"] = "hello";
  document["protocol_version"] = M5_PROTOCOL_VERSION;
  document["device_id"] = deviceId_;
  document["device_name"] = config_.deviceName;
  document["firmware_version"] = M5_FIRMWARE_VERSION;
  document["firmware_build"] = M5_FIRMWARE_BUILD;
  document["board"] = M5_FIRMWARE_BOARD;
  document["action"] = actionId(config_.action);
  document["max_recording_seconds"] = config_.maxRecordingSeconds;
  document["sounds_enabled"] = config_.soundsEnabled;
  JsonArray capabilities = document["capabilities"].to<JsonArray>();
  capabilities.add("settings_v1");
  capabilities.add("telemetry_v1");
  String json;
  serializeJson(document, json);
  socket_.sendTXT(json);
}

bool ProtocolClient::startRecording(uint32_t sequence, OutputAction action) {
  if (!connected_) return false;
  JsonDocument document;
  document["type"] = "recording_start";
  document["protocol_version"] = 1;
  document["device_id"] = deviceId_;
  document["sample_rate"] = 16000;
  document["channels"] = 1;
  document["sample_format"] = "pcm_s16le";
  document["sequence"] = sequence;
  document["action"] = actionId(action);
  document["profile"] = legacyProfile(action);
  document["mode"] = legacyMode(action);
  String json;
  serializeJson(document, json);
  return socket_.sendTXT(json);
}

bool ProtocolClient::sendAudio(const AudioBlock& block) {
  return connected_ && socket_.sendBIN(reinterpret_cast<const uint8_t*>(block.data), block.samples * sizeof(int16_t));
}

void ProtocolClient::endRecording(uint32_t sequence, bool cancelled) {
  JsonDocument document;
  document["type"] = "recording_end";
  document["protocol_version"] = 1;
  document["sequence"] = sequence;
  document["cancelled"] = cancelled;
  String json;
  serializeJson(document, json);
  socket_.sendTXT(json);
}

void ProtocolClient::cancel(uint32_t sequence) {
  JsonDocument document;
  document["type"] = "cancel";
  document["protocol_version"] = 1;
  document["sequence"] = sequence;
  String json;
  serializeJson(document, json);
  socket_.sendTXT(json);
}

void ProtocolClient::sendTelemetry(int32_t batteryPercent, bool charging, int32_t rssi) {
  if (!connected_) return;
  JsonDocument document;
  document["type"] = "telemetry";
  document["protocol_version"] = 1;
  document["device_id"] = deviceId_;
  document["battery_percent"] = batteryPercent;
  document["charging"] = charging;
  document["rssi"] = rssi;
  document["firmware_version"] = M5_FIRMWARE_VERSION;
  document["firmware_build"] = M5_FIRMWARE_BUILD;
  document["board"] = M5_FIRMWARE_BOARD;
  String json;
  serializeJson(document, json);
  socket_.sendTXT(json);
}

void ProtocolClient::applySettings(JsonDocument& document) {
  DeviceConfig updated = config_;
  bool applied = true;
  if (!document["device_name"].isNull()) {
    String name = document["device_name"].as<String>();
    if (name.length() <= 32) updated.deviceName = name;
    else applied = false;
  }
  OutputAction action = updated.action;
  if (!parseAction(document["action"].as<String>(), action)) applied = false;
  uint16_t maxRecording = document["max_recording_seconds"] | 0;
  if (maxRecording < 1 || maxRecording > 600) applied = false;
  if (applied) {
    updated.action = action;
    updated.maxRecordingSeconds = maxRecording;
    updated.soundsEnabled = document["sounds_enabled"] | true;
    config_ = updated;
    if (settingsCallback_) settingsCallback_(updated);
  }

  JsonDocument response;
  response["type"] = "settings_ack";
  response["protocol_version"] = 1;
  response["revision"] = document["revision"] | -1;
  response["applied"] = applied;
  response["device_name"] = config_.deviceName;
  response["action"] = actionId(config_.action);
  response["max_recording_seconds"] = config_.maxRecordingSeconds;
  response["sounds_enabled"] = config_.soundsEnabled;
  String json;
  serializeJson(response, json);
  socket_.sendTXT(json);
}

AppState ProtocolClient::stateFromId(const String& value) const {
  if (value == "ready") return AppState::Ready;
  if (value == "recording") return AppState::Recording;
  if (value == "receiving") return AppState::Receiving;
  if (value == "transcribing") return AppState::Transcribing;
  if (value == "inserting") return AppState::Inserting;
  if (value == "sent") return AppState::Sent;
  if (value == "cancelled") return AppState::Cancelled;
  if (value == "error") return AppState::Error;
  return AppState::ConnectingServer;
}

void ProtocolClient::onEvent(WStype_t type, uint8_t* payload, size_t length) {
  if (type == WStype_CONNECTED) {
    connected_ = true;
    sendHello();
  } else if (type == WStype_DISCONNECTED) {
    connected_ = false;
    if (callback_) callback_(AppState::ConnectingServer, "PC disconnected");
  } else if (type == WStype_TEXT) {
    JsonDocument document;
    if (deserializeJson(document, payload, length) != DeserializationError::Ok) return;
    if (document["type"] == "status") {
      String state = document["state"].as<String>();
      String message = document["message"].as<String>();
      if (callback_) callback_(stateFromId(state), message);
    } else if (document["type"] == "settings_update") {
      applySettings(document);
    }
  }
}
