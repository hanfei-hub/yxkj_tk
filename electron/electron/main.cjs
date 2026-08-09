const { app, BrowserWindow, shell, ipcMain, session, Menu } = require("electron");
const path = require("node:path");

// 直接运行 Electron 二进制时也应加载内置 dist；只有 npm run dev 才使用 Vite 地址。
const isDev = !app.isPackaged && process.env.ELECTRON_DEV === "1";

function createWindow() {
  const win = new BrowserWindow({
    width: 1540,
    height: 960,
    minWidth: 1180,
    minHeight: 760,
    backgroundColor: "#f5f8fb",
    frame: false,
    titleBarStyle: "hidden",
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
  if (isDev) {
    win.loadURL("http://127.0.0.1:5173");
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }
}

ipcMain.handle("app:version", () => app.getVersion());
ipcMain.handle("shell:open", (_event, url) => shell.openExternal(String(url)));
ipcMain.on("window:minimize", (event) => BrowserWindow.fromWebContents(event.sender)?.minimize());
ipcMain.on("window:toggle-maximize", (event) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win) return;
  win.isMaximized() ? win.unmaximize() : win.maximize();
});
ipcMain.on("window:close", (event) => BrowserWindow.fromWebContents(event.sender)?.close());
app.whenReady().then(async () => {
  Menu.setApplicationMenu(null);
  await session.defaultSession.setProxy({
    mode: "system",
    proxyBypassRules: "120.26.207.89;120.26.207.89:8000",
  });
  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
