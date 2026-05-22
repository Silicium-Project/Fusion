"use strict";

const crypto = require("crypto");
const Module = require("module");

if (!global.__siliciumUuidCjsShimInstalled) {
  const originalModuleLoad = Module._load;

  function uuidCompat() {
    if (typeof crypto.randomUUID === "function") {
      return crypto.randomUUID();
    }
    return crypto.randomBytes(16).toString("hex");
  }

  uuidCompat.v1 = uuidCompat;
  uuidCompat.v4 = uuidCompat;

  Module._load = function patchedModuleLoad(request, parent, isMain) {
    if (request === "uuid") {
      return uuidCompat;
    }
    return originalModuleLoad.call(this, request, parent, isMain);
  };

  global.__siliciumUuidCjsShimInstalled = true;
}
