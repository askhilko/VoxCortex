#pragma once

#include <DNSServer.h>
#include <WebServer.h>
#include "AppTypes.h"
#include "SettingsStore.h"

class ProvisioningPortal {
 public:
  void begin(const String& suffix, SettingsStore& store);
  void tick();
  String apName() const { return apName_; }

 private:
  String page(const String& error = "") const;
  void handleSave();
  String escapeHtml(const String& value) const;

  DNSServer dns_;
  WebServer server_{80};
  SettingsStore* store_ = nullptr;
  String apName_;
};

