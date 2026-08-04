const { app, BrowserWindow, shell, ipcMain } = require("electron");
const path = require("node:path");

const isDev = !app.isPackaged;

function createWindow() {
  const win = new BrowserWindow({
    width: 1540,
    height: 960,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#f5f8fb",
    show: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  win.once("ready-to-show", () => win.show());
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  win.loadURL(isDev ? "http://127.0.0.1:5173" : `file://${path.join(__dirname, "../dist/index.html")}`);
}

ipcMain.handle("app:version", () => app.getVersion());
ipcMain.handle("shell:open", (_event, url) => shell.openExternal(String(url)));
app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
