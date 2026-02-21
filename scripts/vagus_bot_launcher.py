"""
GUI Launcher for Vagus Telegram Bot — Start and Restart.
"""
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOT_CMD_PATTERN = "start_telegram_bot"


def _get_pythonpath() -> str:
    return f"{PROJECT_ROOT}{os.pathsep}{PROJECT_ROOT / 'src'}"


def _get_launch_command() -> list[str]:
    return [
        sys.executable,
        "-c",
        "import asyncio; from dotenv import load_dotenv; load_dotenv(); "
        "from vagus.layer3.channels.telegram.bot import start_telegram_bot; "
        "asyncio.run(start_telegram_bot())",
    ]


def _get_bot_pids_ps() -> list[int]:
    """Use PowerShell (works on modern Windows, WMIC deprecated)."""
    try:
        ps_cmd = (
            "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
            f"Where-Object {{ $_.CommandLine -like '*{BOT_CMD_PATTERN}*' }} | "
            "Select-Object -ExpandProperty ProcessId"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
        )
        if result.returncode != 0:
            return []
        pids = []
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
        return pids
    except Exception:
        return []


def get_bot_pids() -> list[int]:
    """Return list of PIDs for running bot processes."""
    return _get_bot_pids_ps()


def is_bot_running() -> bool:
    """Check if the Telegram bot process is running."""
    return len(get_bot_pids()) > 0


def kill_bot_processes() -> bool:
    """Kill all Telegram bot processes."""
    pids = get_bot_pids()
    if not pids:
        return True
    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0,
            )
        except Exception:
            pass
    return True


def start_bot() -> bool:
    """Start the Telegram bot in background (no terminal window)."""
    env = os.environ.copy()
    env["PYTHONPATH"] = _get_pythonpath()
    cmd = _get_launch_command()
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    try:
        subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            env=env,
            creationflags=creation_flags,
        )
        return True
    except Exception:
        return False


class VagusBotLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Vagus Bot — Старт / Рестарт")
        self.root.geometry("320x140")
        self.root.resizable(False, False)

        self.status_var = tk.StringVar(value="Проверка статуса...")
        self.root.after(100, self._refresh_status)

        # Status label
        tk.Label(self.root, textvariable=self.status_var, font=("Segoe UI", 10)).pack(
            pady=(12, 8)
        )

        # Buttons frame
        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=8)

        self.start_btn = tk.Button(
            btn_frame, text="Старт", width=12, command=self._on_start
        )
        self.start_btn.pack(side=tk.LEFT, padx=6)

        self.restart_btn = tk.Button(
            btn_frame, text="Рестарт", width=12, command=self._on_restart
        )
        self.restart_btn.pack(side=tk.LEFT, padx=6)

        # Refresh button
        tk.Button(
            self.root, text="Обновить статус", width=14, command=self._refresh_status
        ).pack(pady=(4, 12))

    def _refresh_status(self):
        if is_bot_running():
            self.status_var.set("Бот запущен")
        else:
            self.status_var.set("Бот остановлен")

    def _on_start(self):
        self.status_var.set("Проверка...")
        self.root.update_idletasks()
        if is_bot_running():
            messagebox.showwarning(
                "Уже запущен",
                "Telegram-бот уже запущен. Используйте «Рестарт» для перезапуска.",
            )
            self._refresh_status()
            return
        self.status_var.set("Запуск...")
        self.root.update_idletasks()
        if start_bot():
            self.root.after(1500, self._refresh_status)
        else:
            messagebox.showerror(
                "Ошибка", "Не удалось запустить бота. Проверьте .env и TELEGRAM_BOT_TOKEN."
            )
            self._refresh_status()

    def _on_restart(self):
        self.status_var.set("Остановка...")
        self.root.update_idletasks()
        kill_bot_processes()
        self.root.after(2000, self._do_start_after_restart)

    def _do_start_after_restart(self):
        self.status_var.set("Запуск...")
        self.root.update_idletasks()
        if start_bot():
            self.root.after(1500, self._refresh_status)
        else:
            messagebox.showerror(
                "Ошибка", "Не удалось запустить бота. Проверьте .env и TELEGRAM_BOT_TOKEN."
            )
            self._refresh_status()

    def run(self):
        self.root.mainloop()


def main():
    launcher = VagusBotLauncher()
    launcher.run()


if __name__ == "__main__":
    main()
