const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("desktop", {
  version: () => ipcRenderer.invoke("app:version"),
  openExternal: (url) => ipcRenderer.invoke("shell:open", url),
  savePdf: (html, filename) => ipcRenderer.invoke("report:save-pdf", { html, filename }),
  minimize: () => ipcRenderer.send("window:minimize"),
  toggleMaximize: () => ipcRenderer.send("window:toggle-maximize"),
  close: () => ipcRenderer.send("window:close"),
});
