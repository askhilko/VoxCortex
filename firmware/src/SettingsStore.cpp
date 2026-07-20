#include "SettingsStore.h"

DeviceConfig SettingsStore::load() {
  DeviceConfig result;
  // Read/write mode creates the namespace on a factory-clean NVS without logging NOT_FOUND.
  preferences_.begin("dictation", false);
  result.ssid = preferences_.isKey("ssid") ? preferences_.getString("ssid") : "";
  result.password = preferences_.isKey("wifi_pass") ? preferences_.getString("wifi_pass") : "";
  result.serverHost = preferences_.isKey("host") ? preferences_.getString("host") : "voxcortex.local";
  result.serverPort = preferences_.getUShort("port", 8765);
  result.deviceName = preferences_.isKey("name") ? preferences_.getString("name") : "";
  if (preferences_.isKey("action")) {
    result.action = static_cast<OutputAction>(preferences_.getUChar("action", 1) % 4);
  } else {
    // Migrate the profile + mode pair used by firmware 1.3 and earlier.
    const String profile = preferences_.isKey("profile") ? preferences_.getString("profile") : "chatgpt";
    const uint8_t mode = preferences_.getUChar("mode", 0) % 3;
    if (profile == "clipboard") {
      result.action = OutputAction::Copy;
    } else if (mode == 2 || (mode == 0 && profile == "vscode")) {
      result.action = OutputAction::PasteCtrlEnter;
    } else if (mode == 1 || (mode == 0 && profile == "terminal")) {
      result.action = OutputAction::PasteEnter;
    } else {
      result.action = OutputAction::Paste;
    }
    preferences_.putUChar("action", static_cast<uint8_t>(result.action));
  }
  result.maxRecordingSeconds = preferences_.getUShort("max_rec", 120);
  result.soundsEnabled = preferences_.getBool("sounds", true);
  preferences_.end();
  return result;
}

bool SettingsStore::save(const DeviceConfig& config) {
  preferences_.begin("dictation", false);
  bool ok = preferences_.putString("ssid", config.ssid) > 0;
  ok &= preferences_.putString("wifi_pass", config.password) > 0 || config.password.isEmpty();
  ok &= preferences_.putString("host", config.serverHost) > 0;
  ok &= preferences_.putUShort("port", config.serverPort) > 0;
  ok &= preferences_.putString("name", config.deviceName) > 0;
  ok &= preferences_.putUShort("max_rec", config.maxRecordingSeconds) > 0;
  preferences_.putBool("sounds", config.soundsEnabled);
  preferences_.putUChar("boot_fail", 0);
  preferences_.end();
  return ok;
}

void SettingsStore::clearNetwork() {
  preferences_.begin("dictation", false);
  preferences_.remove("ssid");
  preferences_.remove("wifi_pass");
  preferences_.remove("host");
  preferences_.remove("port");
  preferences_.putUChar("boot_fail", 0);
  preferences_.end();
}

uint8_t SettingsStore::incrementBootFailures() {
  preferences_.begin("dictation", false);
  uint8_t value = preferences_.getUChar("boot_fail", 0);
  if (value < 255) ++value;
  preferences_.putUChar("boot_fail", value);
  preferences_.end();
  return value;
}

void SettingsStore::clearBootFailures() {
  preferences_.begin("dictation", false);
  preferences_.putUChar("boot_fail", 0);
  preferences_.end();
}

void SettingsStore::saveAction(OutputAction action) {
  preferences_.begin("dictation", false);
  preferences_.putUChar("action", static_cast<uint8_t>(action));
  preferences_.end();
}
