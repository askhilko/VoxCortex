#pragma once

#include <Preferences.h>
#include "AppTypes.h"

class SettingsStore {
 public:
  DeviceConfig load();
  bool save(const DeviceConfig& config);
  void clearNetwork();
  uint8_t incrementBootFailures();
  void clearBootFailures();
  void saveAction(OutputAction action);

 private:
  Preferences preferences_;
};
