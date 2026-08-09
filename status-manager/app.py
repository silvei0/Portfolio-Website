"""Tiny desktop status editor for Fiza's Project Portfolio.

Uses only the Python standard library: Tkinter for the interface and the
existing Git installation for publishing status.json.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable


APP_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = APP_DIR.parent
if str(REPOSITORY_DIR) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_DIR))

from manager_auth import PasswordStore


CONFIG_PATH = APP_DIR / "config.json"
EXAMPLE_CONFIG_PATH = APP_DIR / "config.example.json"
RECENT_PATH = APP_DIR / "recent-statuses.json"

PRESETS = (
    ("30 min", 30, "minutes"),
    ("1 hour", 1, "hours"),
    ("3 hours", 3, "hours"),
    ("8 hours", 8, "hours"),
    ("1 day", 1, "days"),
)

UNIT_SECONDS = {
    "minutes": 60,
    "hours": 60 * 60,
    "days": 24 * 60 * 60,
}


class StatusManagerError(Exception):
    """A friendly error that can be shown directly in the interface."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_json(path: Path, fallback: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def resolve_inside(base: Path, configured_path: str, label: str) -> Path:
    path = Path(configured_path).expanduser()
    if not path.is_absolute():
        path = base / path
    path = path.resolve()
    try:
        path.relative_to(base.resolve())
    except ValueError as error:
        raise StatusManagerError(f"{label} must stay inside the portfolio repository.") from error
    return path


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        if not EXAMPLE_CONFIG_PATH.exists():
            raise StatusManagerError("config.json and config.example.json are missing.")
        CONFIG_PATH.write_text(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    config = load_json(CONFIG_PATH, None)
    if not isinstance(config, dict):
        raise StatusManagerError("config.json is not valid JSON.")

    required = ("repositoryPath", "statusJsonPath")
    missing = [key for key in required if not str(config.get(key, "")).strip()]
    if missing:
        raise StatusManagerError(f"Missing configuration: {', '.join(missing)}")

    repository = Path(str(config["repositoryPath"])).expanduser()
    if not repository.is_absolute():
        repository = APP_DIR / repository
    repository = repository.resolve()
    if not repository.is_dir():
        raise StatusManagerError(f"Repository folder does not exist: {repository}")

    status_path = resolve_inside(repository, str(config["statusJsonPath"]), "statusJsonPath")
    config["repository"] = repository
    config["statusPath"] = status_path
    config["defaultStatus"] = str(config.get("defaultStatus", "No specific thoughts right now...")).strip()
    config["gitRemote"] = str(config.get("gitRemote", "origin")).strip() or "origin"
    config["gitBranch"] = str(config.get("gitBranch", "")).strip()
    config["commitMessage"] = str(config.get("commitMessage", "Update status")).strip() or "Update status"
    config["autoPush"] = bool(config.get("autoPush", True))
    config["characterLimit"] = max(1, int(config.get("characterLimit", 80)))
    config["recentStatusesLimit"] = max(1, int(config.get("recentStatusesLimit", 8)))
    return config


class StatusManager(tk.Tk):
    def __init__(self, password_store: PasswordStore) -> None:
        super().__init__()
        self.title("Portfolio Status Manager")
        self.geometry("510x640")
        self.minsize(480, 590)
        self.configure(background="#eee7d9")
        self.password_store = password_store

        self.config_data = load_config()
        icon_path = self.config_data["repository"] / "assets" / "site-icon-favicon.png"
        if icon_path.exists():
            try:
                self.app_icon = tk.PhotoImage(file=icon_path)
                self.iconphoto(True, self.app_icon)
            except tk.TclError:
                pass
        self.status_var = tk.StringVar()
        self.duration_var = tk.StringVar(value="3")
        self.unit_var = tk.StringVar(value="hours")
        self.character_var = tk.StringVar()
        self.preview_var = tk.StringVar()
        self.current_var = tk.StringVar(value="Checking current status…")
        self.result_var = tk.StringVar(value="Ready")
        self.recent_var = tk.StringVar()
        self.busy = False
        self.result_queue: queue.Queue[tuple[bool, str]] = queue.Queue()

        self._configure_style()
        self._build_menu()
        self._build_interface()
        self.status_var.trace_add("write", self._on_status_change)
        self._on_status_change()
        self._refresh_current_status()
        self.after(1_000, self._tick)

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        security_menu = tk.Menu(menu_bar, tearoff=False)
        security_menu.add_command(label="Change manager password…", command=self._change_manager_password)
        security_menu.add_separator()
        security_menu.add_command(label="Lock and exit", command=self.destroy)
        menu_bar.add_cascade(label="Security", menu=security_menu)
        self.config(menu=menu_bar)

    def _change_manager_password(self) -> None:
        self.password_store.change_password_interactive(self, "Portfolio Status Manager")

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("App.TFrame", background="#eee7d9")
        style.configure("Card.TFrame", background="#f8f4eb", relief="solid", borderwidth=1)
        style.configure("Title.TLabel", background="#eee7d9", foreground="#203d3b", font=("Segoe UI", 20, "bold"))
        style.configure("Subtitle.TLabel", background="#eee7d9", foreground="#6e6256", font=("Segoe UI", 9))
        style.configure("Field.TLabel", background="#f8f4eb", foreground="#30271e", font=("Segoe UI", 10, "bold"))
        style.configure("Body.TLabel", background="#f8f4eb", foreground="#30271e", font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background="#f8f4eb", foreground="#75695e", font=("Segoe UI", 9))
        style.configure("Preview.TLabel", background="#fffdf8", foreground="#203d3b", font=("Segoe UI", 12, "italic"), padding=14)
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"), foreground="#ffffff", background="#1f5b57", padding=(14, 9))
        style.map("Primary.TButton", background=[("active", "#2a736d"), ("disabled", "#9ca9a7")])
        style.configure("Secondary.TButton", font=("Segoe UI", 9), padding=(10, 7))
        style.configure("Status.TLabel", background="#eee7d9", foreground="#1f5b57", font=("Segoe UI", 9, "bold"))

    def _build_interface(self) -> None:
        outer = ttk.Frame(self, style="App.TFrame", padding=22)
        outer.pack(fill="both", expand=True)

        ttk.Label(outer, text="Portfolio status", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Update the thought bubble on your homepage.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 16))

        current_card = ttk.Frame(outer, style="Card.TFrame", padding=14)
        current_card.pack(fill="x", pady=(0, 12))
        ttk.Label(current_card, text="CURRENT", style="Field.TLabel").pack(anchor="w")
        ttk.Label(current_card, textvariable=self.current_var, style="Body.TLabel", wraplength=430).pack(anchor="w", pady=(5, 0))

        editor = ttk.Frame(outer, style="Card.TFrame", padding=16)
        editor.pack(fill="both", expand=True)

        status_header = ttk.Frame(editor, style="Card.TFrame")
        status_header.pack(fill="x")
        ttk.Label(status_header, text="Status", style="Field.TLabel").pack(side="left")
        ttk.Label(status_header, textvariable=self.character_var, style="Muted.TLabel").pack(side="right")

        self.status_entry = ttk.Entry(editor, textvariable=self.status_var, font=("Segoe UI", 11))
        self.status_entry.pack(fill="x", pady=(6, 10), ipady=5)
        self.status_entry.focus_set()

        ttk.Label(editor, text="Recent", style="Field.TLabel").pack(anchor="w")
        self.recent_box = ttk.Combobox(editor, textvariable=self.recent_var, state="readonly")
        self.recent_box.pack(fill="x", pady=(6, 14))
        self.recent_box.bind("<<ComboboxSelected>>", self._choose_recent)
        self._load_recent_menu()

        ttk.Label(editor, text="Duration", style="Field.TLabel").pack(anchor="w")
        duration_row = ttk.Frame(editor, style="Card.TFrame")
        duration_row.pack(fill="x", pady=(6, 8))
        self.duration_input = ttk.Spinbox(duration_row, from_=0.1, to=999, increment=0.5, textvariable=self.duration_var, width=12)
        self.duration_input.pack(side="left", ipady=4)
        self.unit_box = ttk.Combobox(duration_row, textvariable=self.unit_var, values=tuple(UNIT_SECONDS), state="readonly", width=12)
        self.unit_box.pack(side="left", padx=(8, 0), ipady=4)

        preset_row = ttk.Frame(editor, style="Card.TFrame")
        preset_row.pack(fill="x", pady=(0, 14))
        for label, amount, unit in PRESETS:
            ttk.Button(
                preset_row,
                text=label,
                style="Secondary.TButton",
                command=lambda a=amount, u=unit: self._set_duration(a, u),
            ).pack(side="left", padx=(0, 5))

        ttk.Label(editor, text="Preview", style="Field.TLabel").pack(anchor="w")
        ttk.Label(editor, textvariable=self.preview_var, style="Preview.TLabel", anchor="center", wraplength=410).pack(fill="x", pady=(6, 16))

        actions = ttk.Frame(editor, style="Card.TFrame")
        actions.pack(fill="x")
        self.update_button = ttk.Button(actions, text="Update status", style="Primary.TButton", command=self._update_status)
        self.update_button.pack(side="left", fill="x", expand=True)
        self.clear_button = ttk.Button(actions, text="Clear status", style="Secondary.TButton", command=self._clear_status)
        self.clear_button.pack(side="left", padx=(8, 0))

        ttk.Label(outer, textvariable=self.result_var, style="Status.TLabel", wraplength=450).pack(anchor="w", pady=(12, 0))

    def _on_status_change(self, *_args: Any) -> None:
        limit = self.config_data["characterLimit"]
        value = self.status_var.get()
        if len(value) > limit:
            value = value[:limit]
            self.status_var.set(value)
            return
        self.character_var.set(f"{len(value)} / {limit}")
        preview = value.strip() or self.config_data["defaultStatus"] or "(hidden)"
        self.preview_var.set(preview)

    def _set_duration(self, amount: float, unit: str) -> None:
        self.duration_var.set(str(amount))
        self.unit_var.set(unit)

    def _choose_recent(self, _event: tk.Event[Any]) -> None:
        selected = self.recent_var.get().strip()
        if selected:
            self.status_var.set(selected)

    def _load_recent_menu(self) -> None:
        recent = load_json(RECENT_PATH, [])
        values = [str(value) for value in recent if isinstance(value, str) and value.strip()]
        self.recent_box["values"] = values

    def _remember_status(self, status: str) -> None:
        if not status:
            return
        recent = load_json(RECENT_PATH, [])
        if not isinstance(recent, list):
            recent = []
        recent = [status] + [item for item in recent if isinstance(item, str) and item != status]
        recent = recent[: self.config_data["recentStatusesLimit"]]
        RECENT_PATH.write_text(json.dumps(recent, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _duration_seconds(self) -> float:
        try:
            amount = float(self.duration_var.get())
        except ValueError as error:
            raise StatusManagerError("Duration must be a number.") from error
        if amount <= 0:
            raise StatusManagerError("Duration must be greater than zero.")
        unit = self.unit_var.get()
        if unit not in UNIT_SECONDS:
            raise StatusManagerError("Choose minutes, hours, or days.")
        return amount * UNIT_SECONDS[unit]

    def _update_status(self) -> None:
        status = self.status_var.get().strip()
        if not status:
            messagebox.showwarning("Status needed", "Enter a status before updating.", parent=self)
            self.status_entry.focus_set()
            return
        try:
            duration = self._duration_seconds()
        except StatusManagerError as error:
            messagebox.showwarning("Check duration", str(error), parent=self)
            return

        created = utc_now()
        payload = {
            "status": status,
            "createdAt": iso_utc(created),
            "expiresAt": iso_utc(created + timedelta(seconds=duration)),
            "defaultStatus": self.config_data["defaultStatus"],
        }
        self._start_publish(payload, status, "Status updated")

    def _clear_status(self) -> None:
        created = utc_now()
        payload = {
            "status": "",
            "createdAt": iso_utc(created),
            "expiresAt": iso_utc(created),
            "defaultStatus": self.config_data["defaultStatus"],
        }
        self._start_publish(payload, "", "Status cleared")

    def _start_publish(self, payload: dict[str, Any], recent_status: str, success_prefix: str) -> None:
        if self.busy:
            return
        self._set_busy(True)
        self.result_var.set("Saving and publishing…")

        def work() -> None:
            try:
                outcome = self._save_and_publish(payload)
                if recent_status:
                    try:
                        self._remember_status(recent_status)
                    except OSError:
                        pass
                result = (True, f"{success_prefix}. {outcome}")
            except StatusManagerError as error:
                result = (False, str(error))
            except Exception as error:  # Keeps unexpected errors visible without closing the app.
                result = (False, f"Unexpected error: {error}")
            self.result_queue.put(result)

        threading.Thread(target=work, daemon=True).start()

    def _save_and_publish(self, payload: dict[str, Any]) -> str:
        status_path: Path = self.config_data["statusPath"]
        status_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = status_path.with_name(f".{status_path.name}.tmp")
        try:
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(status_path)
        except OSError as error:
            raise StatusManagerError(f"Could not save status.json: {error}") from error

        if not self.config_data["autoPush"]:
            return "Saved locally (automatic Git push is off)."

        try:
            self._git_publish(status_path)
        except StatusManagerError as error:
            raise StatusManagerError(f"Status saved locally, but GitHub push failed. {error}") from error
        return "Published to GitHub ✓"

    def _git_publish(self, status_path: Path) -> None:
        repository: Path = self.config_data["repository"]
        root = Path(self._run_git("rev-parse", "--show-toplevel").strip()).resolve()
        if root != repository:
            raise StatusManagerError(f"Configured folder is not the Git repository root: {repository}")

        current_branch = self._run_git("branch", "--show-current").strip()
        configured_branch = self.config_data["gitBranch"]
        if not current_branch:
            raise StatusManagerError("Git is in a detached HEAD state.")
        if configured_branch and current_branch != configured_branch:
            raise StatusManagerError(
                f"Repository is on '{current_branch}', but config.json expects '{configured_branch}'."
            )

        relative = status_path.relative_to(repository).as_posix()
        self._run_git("add", "--", relative)

        diff = self._run_git_allow_failure("diff", "--cached", "--quiet", "--", relative)
        if diff.returncode == 0:
            return
        if diff.returncode != 1:
            raise StatusManagerError(self._command_error(diff, "Could not inspect staged status changes."))

        self._run_git("commit", "-m", self.config_data["commitMessage"], "--", relative)
        self._run_git("push", self.config_data["gitRemote"], current_branch, timeout=180)

    def _run_git_allow_failure(self, *arguments: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            return subprocess.run(
                ["git", *arguments],
                cwd=self.config_data["repository"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=flags,
                check=False,
            )
        except FileNotFoundError as error:
            raise StatusManagerError("Git was not found. Install Git or add it to PATH.") from error
        except subprocess.TimeoutExpired as error:
            raise StatusManagerError("Git took too long to respond. Check your network and try again.") from error

    def _run_git(self, *arguments: str, timeout: int = 60) -> str:
        result = self._run_git_allow_failure(*arguments, timeout=timeout)
        if result.returncode != 0:
            raise StatusManagerError(self._command_error(result, f"Git {' '.join(arguments)} failed."))
        return result.stdout

    @staticmethod
    def _command_error(result: subprocess.CompletedProcess[str], fallback: str) -> str:
        detail = (result.stderr or result.stdout).strip()
        return detail or fallback

    def _publish_finished(self, success: bool, message: str) -> None:
        self._set_busy(False)
        self.result_var.set(message)
        self._load_recent_menu()
        self._refresh_current_status()
        if success:
            self.status_var.set("")

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.update_button.configure(state=state)
        self.clear_button.configure(state=state)

    def _refresh_current_status(self) -> None:
        data = load_json(self.config_data["statusPath"], {})
        status = str(data.get("status", "")).strip() if isinstance(data, dict) else ""
        expires = parse_iso(data.get("expiresAt")) if isinstance(data, dict) else None
        remaining = (expires - utc_now()).total_seconds() if expires else 0
        if status and remaining > 0:
            self.current_var.set(f"{status} · {self._format_remaining(remaining)} remaining")
        else:
            fallback = self.config_data["defaultStatus"] or "No status shown"
            self.current_var.set(f"{fallback} · no active temporary status")

    @staticmethod
    def _format_remaining(seconds: float) -> str:
        seconds = max(0, int(seconds))
        if seconds >= 86_400:
            days, remainder = divmod(seconds, 86_400)
            hours = remainder // 3_600
            return f"{days}d {hours}h"
        if seconds >= 3_600:
            hours, remainder = divmod(seconds, 3_600)
            minutes = remainder // 60
            return f"{hours}h {minutes}m"
        minutes, remaining_seconds = divmod(seconds, 60)
        return f"{minutes}m {remaining_seconds}s"

    def _tick(self) -> None:
        try:
            while True:
                self._publish_finished(*self.result_queue.get_nowait())
        except queue.Empty:
            pass
        self._refresh_current_status()
        self.after(1_000, self._tick)


def main() -> None:
    password_store = PasswordStore()
    unlock_window = tk.Tk()
    unlock_window.withdraw()
    if not password_store.authenticate_interactive(unlock_window, "Portfolio Status Manager"):
        unlock_window.destroy()
        return
    unlock_window.destroy()

    try:
        app = StatusManager(password_store)
    except StatusManagerError as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Status Manager setup", str(error), parent=root)
        root.destroy()
        return
    app.mainloop()


if __name__ == "__main__":
    main()
