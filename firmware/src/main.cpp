#include <Arduino.h>
#include <M5Unified.h>
#include <ESPmDNS.h>
#include <WiFi.h>
#include <esp_system.h>

#include "AppTypes.h"
#include "AudioCapture.h"
#include "FirmwareInfo.h"
#include "ProtocolClient.h"
#include "ProvisioningPortal.h"
#include "SettingsStore.h"
#include "UserInterface.h"

namespace {
constexpr uint8_t kPowerButtonPin = 35;
constexpr uint8_t kButtonBPin = 39;
constexpr uint32_t kMinRecordingMs = 300;
constexpr uint8_t kAutoPreRollBlocks = 20;       // 640 ms at 16 kHz / 512 samples.
constexpr uint8_t kAutoCalibrationBlocks = 20;   // Initial room-noise estimate.
constexpr uint8_t kAutoSpeechStartBlocks = 8;    // 256 ms of sustained sound.
constexpr uint8_t kAutoSilenceEndBlocks = 38;    // 1.216 seconds of silence.
constexpr uint16_t kAutoMinimumThreshold = 900;
constexpr uint16_t kAutoMaximumThreshold = 12000;

SettingsStore settingsStore;
ProvisioningPortal portal;
ProtocolClient protocol;
AudioCapture audio;
UserInterface ui;
DeviceConfig config;
AppState state = AppState::ConnectingWifi;
String stateMessage;
String deviceId;
uint32_t sequence = 0;
uint32_t recordingStartedAt = 0;
uint32_t lastWifiAttempt = 0;
uint32_t lastProtocolStartAttempt = 0;
uint32_t lastStateChange = 0;
uint32_t lastTelemetry = 0;
bool cWasPressed = false;
bool mdnsStarted = false;
bool protocolStarted = false;
bool recordingRequested = false;
uint32_t cPressedAt = 0;
bool autoMode = false;
bool autoRecording = false;
uint8_t autoSpeechBlocks = 0;
uint8_t autoSilenceBlocks = 0;
uint8_t autoCalibrationBlocks = 0;
uint16_t autoNoiseFloor = 300;
uint32_t autoSpeechStartedAt = 0;
AudioBlock autoPreRoll[kAutoPreRollBlocks]{};
uint8_t autoPreRollHead = 0;
uint8_t autoPreRollCount = 0;

String chipSuffix() {
  uint64_t chip = ESP.getEfuseMac();
  char suffix[5];
  snprintf(suffix, sizeof(suffix), "%04X", static_cast<uint16_t>(chip));
  return String(suffix);
}

void printFirmwareInfo() {
  Serial.printf(
      "M5AI_INFO {\"board\":\"%s\",\"version\":\"%s\",\"build\":\"%s\","
      "\"protocol\":%u,\"device_id\":\"%s\"}\n",
      M5_FIRMWARE_BOARD,
      M5_FIRMWARE_VERSION,
      M5_FIRMWARE_BUILD,
      static_cast<unsigned>(M5_PROTOCOL_VERSION),
      deviceId.c_str());
}

void handleSerialCommands() {
  static String command;
  while (Serial.available()) {
    const char value = static_cast<char>(Serial.read());
    if (value == '\r') continue;
    if (value == '\n') {
      command.trim();
      if (command == "M5AI INFO") printFirmwareInfo();
      command = "";
    } else if (command.length() < 64) {
      command += value;
    } else {
      command = "";
    }
  }
}

void setState(AppState next, const String& message) {
  AppState previous = state;
  state = next;
  stateMessage = message;
  lastStateChange = millis();
  Serial.printf("[STATE %u] %s\n", static_cast<unsigned>(next), message.c_str());
  const bool autoScreenTransition =
      (previous == AppState::AutoListening || previous == AppState::AutoRecording) &&
      (next == AppState::AutoListening || next == AppState::AutoRecording);
  if (!autoScreenTransition) {
    ui.showState(state, message, config, WiFi.status() == WL_CONNECTED, protocol.connected());
  }
  if (config.soundsEnabled && !audio.running() && next != previous) {
    uint16_t frequency = next == AppState::Sent ? 2200 : (next == AppState::Error ? 450 : 0);
    if (frequency) {
      M5.Speaker.begin();
      M5.Speaker.tone(frequency, next == AppState::Error ? 90 : 45);
      delay(next == AppState::Error ? 95 : 50);
      M5.Speaker.end();
    }
  }
}

void beep(uint16_t frequency, uint16_t durationMs) {
  if (!config.soundsEnabled || audio.running()) return;
  M5.Speaker.begin();
  M5.Speaker.tone(frequency, durationMs);
  delay(durationMs + 5);
  M5.Speaker.end();
}

uint16_t autoVoiceThreshold() {
  uint32_t threshold = static_cast<uint32_t>(autoNoiseFloor) * 3;
  return static_cast<uint16_t>(constrain(threshold, kAutoMinimumThreshold, kAutoMaximumThreshold));
}

void updateAutoNoiseFloor(uint16_t peak) {
  const uint16_t bounded = peak < 8000 ? peak : 8000;
  autoNoiseFloor = static_cast<uint16_t>((static_cast<uint32_t>(autoNoiseFloor) * 31 + bounded) / 32);
}

void pushAutoPreRoll(const AudioBlock& block) {
  autoPreRoll[autoPreRollHead] = block;
  autoPreRollHead = (autoPreRollHead + 1) % kAutoPreRollBlocks;
  if (autoPreRollCount < kAutoPreRollBlocks) ++autoPreRollCount;
}

bool sendAutoPreRoll() {
  const uint8_t start = (autoPreRollHead + kAutoPreRollBlocks - autoPreRollCount) % kAutoPreRollBlocks;
  for (uint8_t i = 0; i < autoPreRollCount; ++i) {
    if (!protocol.sendAudio(autoPreRoll[(start + i) % kAutoPreRollBlocks])) return false;
  }
  autoPreRollHead = 0;
  autoPreRollCount = 0;
  return true;
}

void resetAutoDetector(bool calibrate) {
  autoSpeechBlocks = 0;
  autoSilenceBlocks = 0;
  autoPreRollHead = 0;
  autoPreRollCount = 0;
  if (calibrate) {
    autoCalibrationBlocks = 0;
    autoNoiseFloor = 300;
  } else {
    autoCalibrationBlocks = kAutoCalibrationBlocks;
  }
}

void startAutoMode() {
  if (!protocol.connected()) {
    setState(AppState::Error, "PC unavailable");
    return;
  }
  beep(1850, 45);
  if (!audio.begin()) {
    setState(AppState::Error, "Microphone unavailable");
    return;
  }
  autoMode = true;
  autoRecording = false;
  recordingRequested = false;
  resetAutoDetector(true);
  setState(AppState::AutoListening, "Calibrating room noise");
}

void finishAutoPhrase(bool cancelled, const String& message) {
  if (autoRecording) {
    AudioBlock pending{};
    while (audio.pop(pending)) {
      if (!protocol.sendAudio(pending)) {
        cancelled = true;
        break;
      }
    }
    protocol.endRecording(sequence, cancelled);
  } else if (recordingRequested) {
    protocol.endRecording(sequence, true);
  }
  autoRecording = false;
  recordingRequested = false;
  resetAutoDetector(false);
  if (autoMode) setState(AppState::AutoListening, message);
}

void stopAutoMode() {
  bool cancelPhrase = millis() - autoSpeechStartedAt < kMinRecordingMs;
  if (autoRecording || recordingRequested) finishAutoPhrase(cancelPhrase, "Stopping auto mode");
  audio.end();
  AudioBlock discarded{};
  while (audio.pop(discarded)) {}
  autoMode = false;
  autoRecording = false;
  recordingRequested = false;
  resetAutoDetector(true);
  beep(950, 45);
  setState(AppState::Ready, "Hold A or double M5");
}

void connectWifi() {
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.setSleep(false);
  WiFi.begin(config.ssid.c_str(), config.password.c_str());
  lastWifiAttempt = millis();
  setState(AppState::ConnectingWifi, "Joining " + config.ssid);
}

bool startProtocol() {
  lastProtocolStartAttempt = millis();
  DeviceConfig connectionConfig = config;
  if (connectionConfig.serverHost.endsWith(".local")) {
    if (!mdnsStarted) mdnsStarted = MDNS.begin(deviceId.c_str());
    if (!mdnsStarted) {
      setState(AppState::ConnectingServer, "mDNS start failed");
      return false;
    }
    String mdnsName = connectionConfig.serverHost.substring(0, connectionConfig.serverHost.length() - 6);
    IPAddress resolved = MDNS.queryHost(mdnsName, 1500);
    if (resolved == INADDR_NONE) {
      setState(AppState::ConnectingServer, "Waiting for " + config.serverHost);
      return false;
    }
    connectionConfig.serverHost = resolved.toString();
  }
  protocol.begin(connectionConfig, deviceId, [](AppState next, const String& message) {
    if (next == AppState::Recording) {
      if (!recordingRequested) return;
      recordingRequested = false;
      if (autoMode) {
        if (!sendAutoPreRoll()) {
          autoMode = false;
          audio.end();
          protocol.endRecording(sequence, true);
          setState(AppState::Error, "Audio send failed");
          return;
        }
        autoRecording = true;
        // Count the transmitted pre-roll toward the server-side duration limit.
        recordingStartedAt = millis() - static_cast<uint32_t>(kAutoPreRollBlocks) * 32;
        setState(AppState::AutoRecording, "Pause to transcribe");
        return;
      }
      if (!M5.BtnA.isPressed()) {
        protocol.endRecording(sequence, true);
        setState(AppState::Cancelled, "Recording cancelled");
        return;
      }
      beep(1600, 35);
      if (audio.begin()) {
        recordingStartedAt = millis();
        setState(AppState::Recording, "Release A to send");
      } else {
        protocol.endRecording(sequence, true);
        setState(AppState::Error, "Microphone unavailable");
      }
      return;
    }
    if (autoMode) {
      if (next == AppState::ConnectingServer) {
        autoMode = false;
        autoRecording = false;
        recordingRequested = false;
        audio.end();
        setState(next, message);
      } else if (next == AppState::Error) {
        if (recordingRequested) {
          recordingRequested = false;
          resetAutoDetector(false);
          setState(AppState::AutoListening, "Phrase rejected; listening");
        } else if (autoRecording) {
          finishAutoPhrase(true, "Phrase rejected; listening");
        } else {
          setState(AppState::AutoListening, "Last phrase failed; listening");
        }
      } else {
        Serial.printf("[AUTO JOB %u] %s\n", static_cast<unsigned>(next), message.c_str());
      }
      return;
    }
    if ((recordingRequested || audio.running()) &&
        (next == AppState::Error || next == AppState::ConnectingServer)) {
      recordingRequested = false;
      audio.end();
      setState(next, message);
      return;
    }
    if (state != AppState::Recording || next == AppState::Error) setState(next, message);
  }, [](const DeviceConfig& updated) {
    config = updated;
    settingsStore.save(config);
    if (state == AppState::Ready) setState(AppState::Ready, "Settings synced");
  });
  setState(AppState::ConnectingServer, config.serverHost);
  return true;
}

void handleButtons() {
  if (M5.BtnA.wasDoubleClicked()) {
    if (autoMode) stopAutoMode();
    else if (state == AppState::Ready) startAutoMode();
  } else if (!autoMode && M5.BtnA.wasHold() && state == AppState::Ready) {
    ++sequence;
    if (protocol.startRecording(sequence, config.action)) {
      recordingRequested = true;
      setState(AppState::StartingRecording, "Waiting for PC");
    } else {
      setState(AppState::Error, "PC unavailable");
    }
  } else if (!autoMode && M5.BtnA.wasReleasedAfterHold() && state == AppState::StartingRecording) {
    recordingRequested = false;
    protocol.endRecording(sequence, true);
    setState(AppState::Cancelled, "Recording cancelled");
  } else if (!autoMode && M5.BtnA.wasReleasedAfterHold() && state == AppState::Recording) {
    audio.end();
    AudioBlock pending{};
    while (audio.pop(pending)) protocol.sendAudio(pending);
    bool tooShort = millis() - recordingStartedAt < kMinRecordingMs;
    beep(1100, 30);
    protocol.endRecording(sequence, tooShort);
    setState(tooShort ? AppState::Cancelled : AppState::Receiving,
             tooShort ? "Press at least 300 ms" : "Audio sent");
  } else if (autoMode && M5.BtnA.wasSingleClicked() && (autoRecording || recordingRequested)) {
    bool tooShort = millis() - autoSpeechStartedAt < kMinRecordingMs;
    finishAutoPhrase(tooShort, tooShort ? "Phrase too short; listening" : "Phrase sent; listening");
  }

  if (state == AppState::Ready && M5.BtnB.wasClicked()) {
    setState(AppState::Ready, "Change action on PC");
  }

  if (autoMode && M5.BtnPWR.wasClicked()) {
    if (autoRecording || recordingRequested) finishAutoPhrase(true, "Phrase cancelled; listening");
  } else if (state == AppState::Recording && M5.BtnPWR.wasClicked()) {
    audio.end();
    protocol.endRecording(sequence, true);
    setState(AppState::Cancelled, "Recording cancelled");
  } else if (state != AppState::Recording && state != AppState::Ready && M5.BtnPWR.wasClicked()) {
    protocol.cancel(sequence);
    setState(AppState::Cancelled, "Operation cancelled");
  }

  // Use raw GPIO only for short-click screen toggling. Long C remains available to hardware power control.
  bool cPressed = digitalRead(kPowerButtonPin) == LOW;
  if (cPressed && !cWasPressed) cPressedAt = millis();
  if (!cPressed && cWasPressed && millis() - cPressedAt < 1000 && state == AppState::Ready) {
    ui.setScreenEnabled(!ui.screenEnabled());
    if (ui.screenEnabled()) setState(AppState::Ready, "Hold A or double M5");
  }
  cWasPressed = cPressed;
}
}  // namespace

void setup() {
  pinMode(4, OUTPUT);
  digitalWrite(4, HIGH);
  pinMode(kPowerButtonPin, INPUT_PULLUP);
  pinMode(kButtonBPin, INPUT_PULLUP);
  Serial.begin(115200);
  auto m5config = M5.config();
  m5config.internal_mic = true;
  m5config.internal_spk = true;
  M5.begin(m5config);
  ui.begin();
  // The server remembers completed sequence numbers across reconnects. Start
  // each boot in a random part of the 32-bit space so a reboot or reflash does
  // not collide with an earlier recording from the same device.
  sequence = esp_random();

  config = settingsStore.load();
  deviceId = "m5stick-" + chipSuffix();
  printFirmwareInfo();
  if (config.deviceName.isEmpty()) config.deviceName = "M5 AI Remote " + chipSuffix();
  bool resetRequested = digitalRead(kButtonBPin) == LOW;
  uint8_t bootFailures = config.valid() ? settingsStore.incrementBootFailures() : 0;
  if (resetRequested) {
    settingsStore.clearNetwork();
    config = DeviceConfig{};
  }
  if (!config.valid() || bootFailures >= 3) {
    state = AppState::Provisioning;
    portal.begin(chipSuffix(), settingsStore);
    ui.showProvisioning(portal.apName(), WiFi.softAPIP().toString());
    Serial.printf("Provisioning AP: %s, http://%s\n", portal.apName().c_str(), WiFi.softAPIP().toString().c_str());
    return;
  }
  connectWifi();
}

void loop() {
  M5.update();
  handleSerialCommands();
  if (state == AppState::Provisioning) {
    portal.tick();
    delay(2);
    return;
  }

  if (WiFi.status() != WL_CONNECTED) {
    if (state != AppState::ConnectingWifi) setState(AppState::ConnectingWifi, "WiFi disconnected");
    if (millis() - lastWifiAttempt > 10000) {
      WiFi.disconnect();
      WiFi.begin(config.ssid.c_str(), config.password.c_str());
      lastWifiAttempt = millis();
    }
  } else {
    if (!protocolStarted &&
        (lastProtocolStartAttempt == 0 || millis() - lastProtocolStartAttempt >= 5000)) {
      settingsStore.clearBootFailures();
      protocolStarted = startProtocol();
    }
    if (protocolStarted) protocol.tick();
    if (protocol.connected() && (lastTelemetry == 0 || millis() - lastTelemetry >= 15000)) {
      bool charging = M5.Power.isCharging() == m5::Power_Class::is_charging;
      protocol.sendTelemetry(M5.Power.getBatteryLevel(), charging, WiFi.RSSI());
      lastTelemetry = millis();
    }
  }

  handleButtons();
  if (autoMode) {
    AudioBlock block{};
    while (audio.pop(block)) {
      if (autoRecording) {
        if (!protocol.sendAudio(block)) {
          autoMode = false;
          autoRecording = false;
          audio.end();
          setState(AppState::Error, "Audio send failed");
          break;
        }
        const bool voice = block.peak >= autoVoiceThreshold();
        if (voice) autoSilenceBlocks = 0;
        else if (autoSilenceBlocks < 255) ++autoSilenceBlocks;
        if (autoSilenceBlocks >= kAutoSilenceEndBlocks &&
            millis() - autoSpeechStartedAt >= kMinRecordingMs) {
          protocol.endRecording(sequence, false);
          autoRecording = false;
          resetAutoDetector(false);
          setState(AppState::AutoListening, "Phrase sent; listening");
        }
      } else {
        pushAutoPreRoll(block);
        if (recordingRequested) continue;
        if (autoCalibrationBlocks < kAutoCalibrationBlocks) {
          updateAutoNoiseFloor(block.peak);
          ++autoCalibrationBlocks;
          if (autoCalibrationBlocks == kAutoCalibrationBlocks) {
            setState(AppState::AutoListening, "Waiting for speech");
          }
          continue;
        }

        const bool voice = block.peak >= autoVoiceThreshold();
        if (voice) {
          if (autoSpeechBlocks < 255) ++autoSpeechBlocks;
        } else {
          autoSpeechBlocks = 0;
          updateAutoNoiseFloor(block.peak);
        }
        if (autoSpeechBlocks >= kAutoSpeechStartBlocks) {
          autoSpeechStartedAt = millis() - static_cast<uint32_t>(kAutoSpeechStartBlocks) * 32;
          ++sequence;
          if (protocol.startRecording(sequence, config.action)) {
            recordingRequested = true;
            autoSilenceBlocks = 0;
            setState(AppState::AutoListening, "Speech detected; starting");
          } else {
            autoMode = false;
            audio.end();
            setState(AppState::Error, "PC unavailable");
          }
          autoSpeechBlocks = 0;
        }
      }
    }
    if (audio.overflowed()) {
      const bool phraseActive = autoRecording || recordingRequested;
      autoMode = false;
      autoRecording = false;
      audio.end();
      if (phraseActive) protocol.endRecording(sequence, true);
      recordingRequested = false;
      setState(AppState::Error, "Audio buffer overflow");
    } else if (autoRecording &&
               millis() - recordingStartedAt >= static_cast<uint32_t>(config.maxRecordingSeconds) * 1000) {
      protocol.endRecording(sequence, false);
      autoRecording = false;
      resetAutoDetector(false);
      setState(AppState::AutoListening, "Maximum reached; listening");
    } else if (autoMode) {
      uint8_t spectrum[kSpectrumBandCount]{};
      audio.copySpectrum(spectrum);
      ui.showRecording(autoRecording ? millis() - recordingStartedAt : 0, spectrum,
                       audio.loud(), audio.clipping(), true, autoRecording);
    }
  } else if (state == AppState::Recording) {
    AudioBlock block{};
    while (audio.pop(block)) {
      if (!protocol.sendAudio(block)) {
        audio.end();
        setState(AppState::Error, "Audio send failed");
        break;
      }
    }
    if (audio.overflowed()) {
      audio.end();
      protocol.endRecording(sequence, true);
      setState(AppState::Error, "Audio buffer overflow");
    } else if (millis() - recordingStartedAt >= static_cast<uint32_t>(config.maxRecordingSeconds) * 1000) {
      audio.end();
      AudioBlock pending{};
      while (audio.pop(pending)) protocol.sendAudio(pending);
      protocol.endRecording(sequence, false);
      setState(AppState::Receiving, "Maximum duration reached");
    } else {
      uint8_t spectrum[kSpectrumBandCount]{};
      audio.copySpectrum(spectrum);
      ui.showRecording(millis() - recordingStartedAt, spectrum, audio.loud(), audio.clipping());
    }
  }
  if (!autoMode && (state == AppState::Sent || state == AppState::Cancelled) &&
      millis() - lastStateChange > 1500) {
    setState(AppState::Ready, "Hold A or double M5");
  }
  if (!autoMode && state == AppState::Error && protocol.connected() && millis() - lastStateChange > 2500) {
    setState(AppState::Ready, "Hold A or double M5");
  }
  delay(1);
}
