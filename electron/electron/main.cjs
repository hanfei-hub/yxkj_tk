const { app, BrowserWindow, shell, ipcMain, session, Menu, dialog, screen } = require("electron");
const path = require("node:path");
const fs = require("node:fs/promises");

// 直接运行 Electron 二进制时也应加载内置 dist；只有 npm run dev 才使用 Vite 地址。
const isDev = !app.isPackaged && process.env.ELECTRON_DEV === "1";

function entryTarget() {
  if (isDev) {
    return "http://127.0.0.1:5173";
  }
  return path.join(__dirname, "../dist/index.html");
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function fitWindowToWorkArea(win) {
  if (!win || win.isDestroyed() || win.isMaximized() || win.isFullScreen()) return;
  const bounds = win.getBounds();
  const display = screen.getDisplayMatching(bounds);
  const { x: wx, y: wy, width: ww, height: wh } = display.workArea;
  const margin = 16;
  let { x, y, width, height } = bounds;

  const maxWidth = Math.max(1024, ww - margin * 2);
  const maxHeight = Math.max(680, wh - margin * 2);
  width = clamp(width, 1024, maxWidth);
  height = clamp(height, 680, maxHeight);

  if (x + width > wx + ww - margin) x = wx + ww - width - margin;
  if (y + height > wy + wh - margin) y = wy + wh - height - margin;
  if (x < wx + margin) x = wx + margin;
  if (y < wy + margin) y = wy + margin;

  win.setBounds({ x, y, width, height });
}

function createWindow() {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  const width = Math.min(1540, Math.max(1024, Math.round(sw * 0.92)));
  const height = Math.min(960, Math.max(680, Math.round(sh * 0.92)));
  const win = new BrowserWindow({
    width,
    height,
    minWidth: 1024,
    minHeight: 680,
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
  win.once("ready-to-show", () => {
    fitWindowToWorkArea(win);
    win.show();
  });
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  const target = entryTarget();
  if (isDev) {
    win.loadURL(target);
  } else {
    win.loadFile(target);
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

  let metricsDebounce;
  screen.on("display-metrics-changed", () => {
    clearTimeout(metricsDebounce);
    metricsDebounce = setTimeout(() => {
      BrowserWindow.getAllWindows().forEach((win) => {
        if (!win.isDestroyed() && win.isVisible()) fitWindowToWorkArea(win);
      });
    }, 200);
  });

  createWindow();
  app.on("activate", () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});
app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
