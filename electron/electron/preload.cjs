const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  version: () => ipcRenderer.invoke("app:version"),
  openExternal: (url) => ipcRenderer.invoke("shell:open", url),
});
