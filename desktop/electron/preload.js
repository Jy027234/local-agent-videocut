const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("localStudioShell", {
  shell: "electron",
  serviceUrl: "http://127.0.0.1:8769",
});
