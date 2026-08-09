"""Local password gate shared by the portfolio desktop managers.

The verifier is stored in the current Windows user's local application-data
folder.  The plaintext password is never written to disk or included in the
repository.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from tkinter import messagebox, simpledialog
from typing import Any


AUTH_VERSION = 1
AUTH_ALGORITHM = "scrypt"
MIN_PASSWORD_LENGTH = 10
MAX_LOGIN_ATTEMPTS = 5
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
DERIVED_KEY_LENGTH = 32


class PasswordProtectionError(Exception):
    """Raised when the local password record cannot be used safely."""


def default_auth_path() -> Path:
    """Return a user-specific location that is outside the Git repository."""

    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "FizasPortfolioManagers" / "auth.json"
    return Path.home() / ".fizas-portfolio-managers" / "auth.json"


def validate_new_password(password: str) -> str | None:
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Use at least {MIN_PASSWORD_LENGTH} characters. A memorable passphrase works well."
    if not password.strip():
        return "The password cannot contain only spaces."
    return None


def _derive_key(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=DERIVED_KEY_LENGTH,
        maxmem=64 * 1024 * 1024,
    )


class PasswordStore:
    """Create and verify a salted local password record."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or default_auth_path()).expanduser()

    def exists(self) -> bool:
        return self.path.is_file()

    def set_password(self, password: str) -> None:
        problem = validate_new_password(password)
        if problem:
            raise PasswordProtectionError(problem)

        salt = secrets.token_bytes(16)
        verifier = _derive_key(password, salt)
        record = {
            "version": AUTH_VERSION,
            "algorithm": AUTH_ALGORITHM,
            "salt": base64.b64encode(salt).decode("ascii"),
            "verifier": base64.b64encode(verifier).decode("ascii"),
            "n": SCRYPT_N,
            "r": SCRYPT_R,
            "p": SCRYPT_P,
            "keyLength": DERIVED_KEY_LENGTH,
        }
        self._write_record(record)

    def verify(self, password: str) -> bool:
        record = self._read_record()
        try:
            salt = base64.b64decode(record["salt"], validate=True)
            expected = base64.b64decode(record["verifier"], validate=True)
        except (KeyError, TypeError, ValueError) as error:
            raise PasswordProtectionError("The local password record is damaged.") from error

        supplied = _derive_key(password, salt)
        return hmac.compare_digest(supplied, expected)

    def authenticate_interactive(self, parent: Any, app_name: str) -> bool:
        """Set up a first-run password or require the existing shared password."""

        if not self.exists():
            messagebox.showinfo(
                "Create manager password",
                "Create one local password for both portfolio manager apps.\n\n"
                "The password itself will not be saved in the project or uploaded to GitHub.",
                parent=parent,
            )
            return self._prompt_and_store_new_password(parent, app_name, first_run=True)

        for attempt in range(MAX_LOGIN_ATTEMPTS):
            password = simpledialog.askstring(
                f"Unlock {app_name}",
                "Enter your manager password:",
                show="*",
                parent=parent,
            )
            if password is None:
                return False
            try:
                if self.verify(password):
                    return True
            except PasswordProtectionError as error:
                messagebox.showerror("Password protection error", str(error), parent=parent)
                return False

            remaining = MAX_LOGIN_ATTEMPTS - attempt - 1
            if remaining:
                messagebox.showerror(
                    "Incorrect password",
                    f"That password is incorrect. {remaining} attempt{'s' if remaining != 1 else ''} remaining.",
                    parent=parent,
                )

        messagebox.showerror(
            "Manager locked",
            "Too many incorrect attempts. Close the app and try again later.",
            parent=parent,
        )
        return False

    def change_password_interactive(self, parent: Any, app_name: str) -> bool:
        current = simpledialog.askstring(
            "Change manager password",
            "Enter the current manager password:",
            show="*",
            parent=parent,
        )
        if current is None:
            return False
        try:
            valid = self.verify(current)
        except PasswordProtectionError as error:
            messagebox.showerror("Password protection error", str(error), parent=parent)
            return False
        if not valid:
            messagebox.showerror("Incorrect password", "The current password is incorrect.", parent=parent)
            return False

        changed = self._prompt_and_store_new_password(parent, app_name, first_run=False)
        if changed:
            messagebox.showinfo(
                "Password changed",
                "The shared password for both portfolio managers has been changed.",
                parent=parent,
            )
        return changed

    def _prompt_and_store_new_password(self, parent: Any, app_name: str, *, first_run: bool) -> bool:
        while True:
            password = simpledialog.askstring(
                "Create manager password" if first_run else "New manager password",
                f"Choose a password for {app_name} (at least {MIN_PASSWORD_LENGTH} characters):",
                show="*",
                parent=parent,
            )
            if password is None:
                return False
            problem = validate_new_password(password)
            if problem:
                messagebox.showwarning("Choose a stronger password", problem, parent=parent)
                continue

            confirmation = simpledialog.askstring(
                "Confirm manager password",
                "Enter the new password again:",
                show="*",
                parent=parent,
            )
            if confirmation is None:
                return False
            if not hmac.compare_digest(password, confirmation):
                messagebox.showwarning("Passwords do not match", "Please enter the new password again.", parent=parent)
                continue

            try:
                self.set_password(password)
            except (OSError, PasswordProtectionError) as error:
                messagebox.showerror("Could not save password protection", str(error), parent=parent)
                return False
            return True

    def _read_record(self) -> dict[str, Any]:
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise PasswordProtectionError("The local password record is missing.") from error
        except (OSError, json.JSONDecodeError) as error:
            raise PasswordProtectionError("The local password record cannot be read.") from error

        if not isinstance(record, dict):
            raise PasswordProtectionError("The local password record is damaged.")
        expected_settings = {
            "version": AUTH_VERSION,
            "algorithm": AUTH_ALGORITHM,
            "n": SCRYPT_N,
            "r": SCRYPT_R,
            "p": SCRYPT_P,
            "keyLength": DERIVED_KEY_LENGTH,
        }
        if any(record.get(key) != value for key, value in expected_settings.items()):
            raise PasswordProtectionError("The local password record uses unsupported security settings.")
        return record

    def _write_record(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f"{self.path.name}.tmp")
        temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, self.path)

