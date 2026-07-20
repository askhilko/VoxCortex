#include "ProvisioningPortal.h"

#include <WiFi.h>

void ProvisioningPortal::begin(const String& suffix, SettingsStore& store) {
  store_ = &store;
  apName_ = "M5-AI-Remote-" + suffix;
  WiFi.mode(WIFI_AP);
  WiFi.softAP(apName_.c_str());
  dns_.start(53, "*", WiFi.softAPIP());
  server_.on("/", HTTP_GET, [this] { server_.send(200, "text/html; charset=utf-8", page()); });
  server_.on("/save", HTTP_POST, [this] { handleSave(); });
  server_.onNotFound([this] { server_.sendHeader("Location", "/", true); server_.send(302); });
  server_.begin();
}

void ProvisioningPortal::tick() {
  dns_.processNextRequest();
  server_.handleClient();
}

String ProvisioningPortal::escapeHtml(const String& value) const {
  String out = value;
  out.replace("&", "&amp;");
  out.replace("\"", "&quot;");
  out.replace("<", "&lt;");
  out.replace(">", "&gt;");
  return out;
}

String ProvisioningPortal::page(const String& error) const {
  return String("<!doctype html><meta name=viewport content='width=device-width'><title>M5 AI Remote</title>") +
      "<style>body{font:16px sans-serif;max-width:32rem;margin:2rem auto;padding:0 1rem}input{width:100%;padding:.6rem;margin:.25rem 0 1rem;box-sizing:border-box}button{padding:.7rem 1.2rem}.e{color:#b00}</style>" +
      "<h1>M5 AI Dictation</h1><p>Connect this device to your 2.4 GHz Wi-Fi.</p><p class=e>" + escapeHtml(error) + "</p>" +
      "<form method=post action=/save><label>Wi-Fi SSID<input name=ssid maxlength=32 required></label>" +
      "<label>Wi-Fi password<input name=password type=password maxlength=63></label>" +
      "<label>PC host or IP<input name=host value='ai-dictation.local' maxlength=128 required></label>" +
      "<label>Port<input name=port type=number value=8765 min=1 max=65535 required></label>" +
      "<label>Device name<input name=name value='M5 AI Remote' maxlength=48></label>" +
      "<label>Maximum recording, seconds<input name=max_rec type=number value=120 min=1 max=600></label>" +
      "<label><input name=sounds type=checkbox checked style='width:auto'> Enable sounds</label><br><br>" +
      "<button>Save and restart</button></form>";
}

void ProvisioningPortal::handleSave() {
  DeviceConfig config;
  config.ssid = server_.arg("ssid");
  config.password = server_.arg("password");
  config.serverHost = server_.arg("host");
  config.serverPort = static_cast<uint16_t>(server_.arg("port").toInt());
  config.deviceName = server_.arg("name");
  config.maxRecordingSeconds = constrain(server_.arg("max_rec").toInt(), 1, 600);
  config.soundsEnabled = server_.hasArg("sounds");
  if (!config.valid() || config.serverPort == 0) {
    server_.send(400, "text/html; charset=utf-8", page("Fill all required fields."));
    return;
  }
  if (!store_->save(config)) {
    server_.send(500, "text/html; charset=utf-8", page("Could not save settings."));
    return;
  }
  server_.send(200, "text/html; charset=utf-8", "<h1>Saved</h1><p>Device is restarting...</p>");
  delay(250);
  ESP.restart();
}
