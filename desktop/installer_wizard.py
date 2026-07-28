from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


APP_NAME = "TK跨境助手"
EXE_NAME = "TKCrossBorderAssistant.exe"


def payload_path() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return root / "payload" / EXE_NAME


class Installer(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} 安装程序")
        self.geometry("560x360")
        self.resizable(False, False)
        self.install_dir = tk.StringVar(
            value=str(Path(os.environ.get("LOCALAPPDATA", Path.home())) / APP_NAME)
        )
        self._build_welcome()

    def _clear(self) -> None:
        for child in self.winfo_children():
            child.destroy()

    def _build_welcome(self) -> None:
        self._clear()
        outer = ttk.Frame(self, padding=32)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=APP_NAME, font=("Microsoft YaHei UI", 22, "bold")).pack(anchor="w")
        ttk.Label(outer, text="TikTok 日本选品专家", font=("Microsoft YaHei UI", 13)).pack(anchor="w", pady=(4, 22))
        ttk.Label(outer, text="欢迎使用安装向导。点击“下一步”选择安装位置并完成安装。", wraplength=480).pack(anchor="w")
        ttk.Label(outer, text="安装目录", font=("Microsoft YaHei UI", 10, "bold")).pack(anchor="w", pady=(34, 7))
        row = ttk.Frame(outer)
        row.pack(fill="x")
        ttk.Entry(row, textvariable=self.install_dir).pack(side="left", fill="x", expand=True)
        ttk.Button(row, text="浏览...", command=self.choose_dir).pack(side="left", padx=(8, 0))
        buttons = ttk.Frame(outer)
        buttons.pack(side="bottom", fill="x", pady=(24, 0))
        ttk.Button(buttons, text="取消", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="下一步", command=self.install).pack(side="right", padx=(0, 8))

    def choose_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.install_dir.get(), title="选择安装目录")
        if selected:
            self.install_dir.set(selected)

    def install(self) -> None:
        target = Path(self.install_dir.get().strip()).expanduser()
        source = payload_path()
        if not source.exists():
            messagebox.showerror("安装失败", "安装包文件不完整，请重新获取安装包。")
            return
        try:
            target.mkdir(parents=True, exist_ok=True)
            destination = target / EXE_NAME
            shutil.copy2(source, destination)
            self.create_shortcuts(destination)
        except Exception as exc:
            messagebox.showerror("安装失败", str(exc))
            return
        self._build_finished(destination)

    def create_shortcuts(self, executable: Path) -> None:
        desktop = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
        start_menu = Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        desktop.mkdir(parents=True, exist_ok=True)
        start_menu.mkdir(parents=True, exist_ok=True)
        script = (
            "$ws=New-Object -ComObject WScript.Shell;"
            "$s=$ws.CreateShortcut('{shortcut}');"
            "$s.TargetPath='{target}';$s.WorkingDirectory='{workdir}';$s.Save()"
        )
        for shortcut in (desktop / f"{APP_NAME}.lnk", start_menu / f"{APP_NAME}.lnk"):
            command = script.format(
                shortcut=str(shortcut).replace("'", "''"),
                target=str(executable).replace("'", "''"),
                workdir=str(executable.parent).replace("'", "''"),
            )
            try:
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", command],
                    check=False,
                    creationflags=0x08000000,
                )
            except FileNotFoundError:
                # Some Windows environments do not expose PowerShell in PATH.
                # The application itself is already installed, so shortcuts
                # should not make the installation fail.
                continue

    def _build_finished(self, executable: Path) -> None:
        self._clear()
        outer = ttk.Frame(self, padding=32)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="安装完成", font=("Microsoft YaHei UI", 22, "bold")).pack(anchor="w")
        ttk.Label(outer, text=f"{APP_NAME} 已安装到：\n{executable.parent}", wraplength=480).pack(anchor="w", pady=(24, 0))
        buttons = ttk.Frame(outer)
        buttons.pack(side="bottom", fill="x", pady=(24, 0))
        ttk.Button(buttons, text="关闭", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="启动软件", command=lambda: (subprocess.Popen([str(executable)]), self.destroy())).pack(side="right", padx=(0, 8))


if __name__ == "__main__":
    Installer().mainloop()
