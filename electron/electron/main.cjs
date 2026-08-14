const { app, BrowserWindow, shell, ipcMain, session, Menu, dialog } = require("electron");
const path = require("node:path");
const fs = require("node:fs/promises");

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
  const revealWindow = () => {
    if (win.isDestroyed()) return;
    win.show();
    win.focus();
  };
  win.once("ready-to-show", revealWindow);
  win.webContents.once("did-fail-load", revealWindow);
  setTimeout(revealWindow, 2500);
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
ipcMain.handle("report:save-pdf", async (_event, payload) => {
  const html = String(payload?.html || "");
  if (!html) throw new Error("报告内容为空");
  const safeName = String(payload?.filename || "智能选品报告").replace(/[\\/:*?\"<>|]/g, "_");
  const parent = BrowserWindow.fromWebContents(_event.sender);
  const picked = await dialog.showOpenDialog(parent, { title: "选择报告保存文件夹", defaultPath: app.getPath("downloads"), properties: ["openDirectory", "createDirectory"] });
  if (picked.canceled || !picked.filePaths[0]) return { canceled: true };
  const filePath = path.join(picked.filePaths[0], safeName.endsWith(".pdf") ? safeName : `${safeName}.pdf`);
  const reportWindow = new BrowserWindow({ show: false, width: 1280, height: 960, webPreferences: { contextIsolation: true, sandbox: true } });
  try {
    await reportWindow.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(html)}`);
    const pdf = await reportWindow.webContents.printToPDF({ printBackground: true, preferCSSPageSize: true });
    await fs.writeFile(filePath, pdf);
    return { filePath };
  } finally {
    if (!reportWindow.isDestroyed()) reportWindow.destroy();
  }
});
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
    proxyBypassRules: "120.26.207.89;120.26.207.89:8000;120.26.207.89:8001;120.26.207.89:8002",
  });
  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
