"""Full desktop editor for JSON-driven project posts in Fiza's portfolio."""

from __future__ import annotations

import json
import os
import queue
import shutil
import sys
import threading
import tkinter as tk
from copy import deepcopy
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any, Callable

APP_DIR = Path(__file__).resolve().parent
REPOSITORY_DIR = APP_DIR.parent
if str(REPOSITORY_DIR) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_DIR))

from manager_auth import PasswordStore
from schemas import (
    BLOCK_ORDER,
    BLOCK_SCHEMAS,
    COMMON_BLOCK_FIELDS,
    TOP_LEVEL_TABS,
    UPDATE_FIELDS,
    new_block,
)
from services import (
    GitPublisher,
    PreviewServer,
    ProjectManagerError,
    ProjectRepository,
    SLUG_PATTERN,
    ValidationIssue,
    atomic_write_json,
    load_config,
    slugify,
    validate_manifest,
    validate_project,
)


def get_nested(data: dict[str, Any], path: str, default: Any = "") -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def set_nested(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    current = data
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value


def delete_nested(data: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    chain: list[tuple[dict[str, Any], str]] = []
    current: Any = data
    for part in parts[:-1]:
        if not isinstance(current, dict) or not isinstance(current.get(part), dict):
            return
        chain.append((current, part))
        current = current[part]
    if isinstance(current, dict):
        current.pop(parts[-1], None)
    for parent, key in reversed(chain):
        if parent.get(key) == {}:
            parent.pop(key, None)


def compact_summary(value: Any, limit: int = 72) -> str:
    if isinstance(value, list):
        value = " / ".join(str(item) for item in value if str(item).strip())
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else f"{text[: limit - 1]}…"


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, **kwargs: Any) -> None:
        super().__init__(parent, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, background="#f5f1e8")
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, style="Panel.TFrame")
        self.window = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.content.bind("<Configure>", self._sync_scrollregion)
        self.canvas.bind("<Configure>", self._sync_width)
        self.canvas.bind_all("<MouseWheel>", self._on_wheel, add="+")

    def _sync_scrollregion(self, _event: tk.Event[Any]) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _sync_width(self, event: tk.Event[Any]) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)

    def _on_wheel(self, event: tk.Event[Any]) -> None:
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
            while widget is not None:
                if widget in {self, self.canvas, self.content}:
                    self.canvas.yview_scroll(int(-event.delta / 120), "units")
                    break
                widget = getattr(widget, "master", None)
        except (AttributeError, tk.TclError):
            pass


class FormPane(ttk.Frame):
    """Schema-driven form that edits nested keys without discarding unknown JSON."""

    def __init__(
        self,
        parent: tk.Misc,
        fields: list[dict[str, Any]],
        *,
        changed: Callable[[], None] | None = None,
        path_picker: Callable[[str], str | None] | None = None,
        scrollable: bool = True,
    ) -> None:
        super().__init__(parent, style="Panel.TFrame")
        self.fields = fields
        self.changed = changed or (lambda: None)
        self.path_picker = path_picker
        self.widgets: dict[str, dict[str, Any]] = {}
        self.record_values: dict[str, list[dict[str, Any]]] = {}
        self.loading = False

        if scrollable:
            scroll = ScrollableFrame(self)
            scroll.pack(fill="both", expand=True)
            self.form_parent = scroll.content
        else:
            self.form_parent = self
        self._build()

    def _build(self) -> None:
        self.form_parent.columnconfigure(1, weight=1)
        row = 0
        for spec in self.fields:
            kind = spec["kind"]
            label = ttk.Label(self.form_parent, text=spec["label"], style="Field.TLabel")
            label.grid(row=row, column=0, sticky="nw", padx=(16, 12), pady=(12, 3))
            holder = ttk.Frame(self.form_parent, style="Panel.TFrame")
            holder.grid(row=row, column=1, sticky="ew", padx=(0, 16), pady=(8, 3))
            holder.columnconfigure(0, weight=1)

            descriptor: dict[str, Any] = {"spec": spec, "kind": kind}
            if kind in {"text", "paragraphs", "string_list", "code"}:
                height = 7 if kind in {"paragraphs", "code"} else 4
                widget = tk.Text(holder, height=height, wrap="word" if kind != "code" else "none", undo=True, font=("Consolas", 10) if kind == "code" else ("Segoe UI", 10))
                widget.grid(row=0, column=0, sticky="ew")
                widget.bind("<<Modified>>", lambda event, text=widget: self._text_changed(text))
                descriptor["widget"] = widget
            elif kind == "bool":
                variable = tk.BooleanVar(value=bool(spec.get("default", False)))
                widget = ttk.Checkbutton(holder, variable=variable)
                widget.grid(row=0, column=0, sticky="w")
                variable.trace_add("write", self._variable_changed)
                descriptor.update({"widget": widget, "variable": variable})
            elif kind == "choice":
                variable = tk.StringVar()
                widget = ttk.Combobox(holder, textvariable=variable, values=spec.get("choices", ()), state="readonly")
                widget.grid(row=0, column=0, sticky="ew", ipady=3)
                variable.trace_add("write", self._variable_changed)
                descriptor.update({"widget": widget, "variable": variable})
            elif kind in {"record_list", "key_value_list"}:
                summary = tk.StringVar(value="No entries")
                ttk.Label(holder, textvariable=summary, style="MutedPanel.TLabel").grid(row=0, column=0, sticky="w")
                button = ttk.Button(holder, text="Manage…", command=lambda s=spec: self._manage_records(s))
                button.grid(row=0, column=1, padx=(8, 0))
                descriptor.update({"widget": button, "summary": summary})
                self.record_values[spec["path"]] = []
            else:
                variable = tk.StringVar()
                entry = ttk.Entry(holder, textvariable=variable)
                entry.grid(row=0, column=0, sticky="ew", ipady=4)
                variable.trace_add("write", self._variable_changed)
                descriptor.update({"widget": entry, "variable": variable})
                if kind == "path":
                    ttk.Button(holder, text="Browse…", command=lambda s=spec, v=variable: self._browse_path(s, v)).grid(row=0, column=1, padx=(8, 0))
                elif kind == "date":
                    ttk.Button(holder, text="Today", command=lambda v=variable: v.set(date.today().isoformat())).grid(row=0, column=1, padx=(8, 0))

            self.widgets[spec["path"]] = descriptor
            row += 1
            if spec.get("help"):
                ttk.Label(self.form_parent, text=spec["help"], style="Help.TLabel", wraplength=590).grid(
                    row=row, column=1, sticky="w", padx=(0, 16), pady=(0, 2)
                )
                row += 1

    def _text_changed(self, widget: tk.Text) -> None:
        if widget.edit_modified():
            widget.edit_modified(False)
            if not self.loading:
                self.changed()

    def _variable_changed(self, *_args: Any) -> None:
        if not self.loading:
            self.changed()

    def _browse_path(self, spec: dict[str, Any], variable: tk.StringVar) -> None:
        if not self.path_picker:
            return
        value = self.path_picker(spec.get("mediaDir", "files"))
        if value:
            variable.set(value)

    def _manage_records(self, spec: dict[str, Any]) -> None:
        path = spec["path"]
        dialog = RecordListDialog(
            self,
            spec["label"],
            self.record_values.get(path, []),
            spec.get("fields", []),
            path_picker=self.path_picker,
        )
        self.wait_window(dialog)
        if dialog.result is not None:
            self.record_values[path] = dialog.result
            self._update_record_summary(path)
            self.changed()

    def _update_record_summary(self, path: str) -> None:
        descriptor = self.widgets[path]
        values = self.record_values.get(path, [])
        descriptor["summary"].set(f"{len(values)} entr{'y' if len(values) == 1 else 'ies'}" if values else "No entries")

    def load(self, data: dict[str, Any]) -> None:
        self.loading = True
        try:
            for path, descriptor in self.widgets.items():
                spec = descriptor["spec"]
                kind = descriptor["kind"]
                value = get_nested(data, path, spec.get("default", ""))
                if kind in {"text", "paragraphs", "string_list", "code"}:
                    widget: tk.Text = descriptor["widget"]
                    widget.delete("1.0", "end")
                    if isinstance(value, list):
                        separator = "\n\n" if kind == "paragraphs" else "\n"
                        value = separator.join(str(item) for item in value)
                    widget.insert("1.0", "" if value is None else str(value))
                    widget.edit_modified(False)
                elif kind in {"record_list", "key_value_list"}:
                    if kind == "key_value_list" and isinstance(value, dict):
                        value = [{"label": key, "value": item} for key, item in value.items()]
                    self.record_values[path] = deepcopy(value) if isinstance(value, list) else []
                    self._update_record_summary(path)
                elif kind == "bool":
                    descriptor["variable"].set(bool(value))
                else:
                    descriptor["variable"].set("" if value is None else str(value))
        finally:
            self.loading = False

    def apply(self, data: dict[str, Any]) -> None:
        for path, descriptor in self.widgets.items():
            kind = descriptor["kind"]
            spec = descriptor["spec"]
            if kind in {"text", "paragraphs", "string_list", "code"}:
                raw = descriptor["widget"].get("1.0", "end-1c")
                if kind == "paragraphs":
                    paragraphs = [item.strip() for item in raw.split("\n\n") if item.strip()]
                    value: Any = paragraphs[0] if len(paragraphs) == 1 else paragraphs
                elif kind == "string_list":
                    value = [item.strip() for item in raw.splitlines() if item.strip()]
                else:
                    value = raw.strip()
            elif kind in {"record_list", "key_value_list"}:
                records = deepcopy(self.record_values.get(path, []))
                if kind == "key_value_list":
                    value = {
                        str(item.get("label", "")).strip(): item.get("value", "")
                        for item in records
                        if str(item.get("label", "")).strip()
                    }
                else:
                    value = records
            elif kind == "bool":
                value = bool(descriptor["variable"].get())
            else:
                raw = descriptor["variable"].get().strip()
                if kind == "integer" and raw:
                    try:
                        value = int(raw)
                    except ValueError:
                        value = raw
                elif kind == "number" and raw:
                    try:
                        numeric = float(raw)
                        value = int(numeric) if numeric.is_integer() else numeric
                    except ValueError:
                        value = raw
                else:
                    value = raw

            keep_false = kind == "bool"
            if value in ("", [], {}) and not keep_false:
                delete_nested(data, path)
            else:
                set_nested(data, path, value)


class RecordListDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        records: list[dict[str, Any]],
        fields: list[dict[str, Any]],
        *,
        path_picker: Callable[[str], str | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("720x500")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.records = deepcopy(records)
        self.fields = fields
        self.path_picker = path_picker
        self.result: list[dict[str, Any]] | None = None

        outer = ttk.Frame(self, padding=16, style="App.TFrame")
        outer.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(outer, font=("Segoe UI", 10), activestyle="none")
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<Double-Button-1>", lambda _event: self._edit())
        buttons = ttk.Frame(outer, style="App.TFrame")
        buttons.pack(side="left", fill="y", padx=(10, 0))
        for text, command in (
            ("Add", self._add),
            ("Edit", self._edit),
            ("Duplicate", self._duplicate),
            ("Move up", lambda: self._move(-1)),
            ("Move down", lambda: self._move(1)),
            ("Remove", self._remove),
        ):
            ttk.Button(buttons, text=text, command=command, width=13).pack(fill="x", pady=(0, 6))

        footer = ttk.Frame(self, padding=(16, 0, 16, 16), style="App.TFrame")
        footer.pack(fill="x")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Use these entries", style="Primary.TButton", command=self._accept).pack(side="right", padx=(0, 8))
        self._refresh()

    def _selected(self) -> int | None:
        selection = self.listbox.curselection()
        return selection[0] if selection else None

    def _record_label(self, record: dict[str, Any], index: int) -> str:
        parts = []
        for spec in self.fields[:3]:
            value = get_nested(record, spec["path"], "")
            if value not in ("", None, False):
                parts.append(compact_summary(value, 34))
        return f"{index + 1}. {' — '.join(parts) if parts else 'Untitled entry'}"

    def _refresh(self, selected: int | None = None) -> None:
        self.listbox.delete(0, "end")
        for index, record in enumerate(self.records):
            self.listbox.insert("end", self._record_label(record, index))
        if self.records:
            index = min(selected if selected is not None else 0, len(self.records) - 1)
            self.listbox.selection_set(index)
            self.listbox.see(index)

    def _edit_record(self, initial: dict[str, Any], title: str) -> dict[str, Any] | None:
        dialog = RecordEditorDialog(self, title, initial, self.fields, path_picker=self.path_picker)
        self.wait_window(dialog)
        return dialog.result

    def _add(self) -> None:
        result = self._edit_record({}, "Add entry")
        if result is not None:
            self.records.append(result)
            self._refresh(len(self.records) - 1)

    def _edit(self) -> None:
        index = self._selected()
        if index is None:
            return
        result = self._edit_record(self.records[index], "Edit entry")
        if result is not None:
            self.records[index] = result
            self._refresh(index)

    def _duplicate(self) -> None:
        index = self._selected()
        if index is None:
            return
        self.records.insert(index + 1, deepcopy(self.records[index]))
        self._refresh(index + 1)

    def _move(self, direction: int) -> None:
        index = self._selected()
        if index is None:
            return
        target = index + direction
        if not 0 <= target < len(self.records):
            return
        self.records[index], self.records[target] = self.records[target], self.records[index]
        self._refresh(target)

    def _remove(self) -> None:
        index = self._selected()
        if index is None:
            return
        self.records.pop(index)
        self._refresh(max(0, index - 1))

    def _accept(self) -> None:
        self.result = self.records
        self.destroy()


class RecordEditorDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        title: str,
        initial: dict[str, Any],
        fields: list[dict[str, Any]],
        *,
        path_picker: Callable[[str], str | None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("700x650")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.result: dict[str, Any] | None = None
        self.initial = deepcopy(initial)
        self.form = FormPane(self, fields, path_picker=path_picker)
        self.form.pack(fill="both", expand=True, padx=10, pady=10)
        self.form.load(self.initial)
        footer = ttk.Frame(self, padding=12, style="App.TFrame")
        footer.pack(fill="x")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Save entry", style="Primary.TButton", command=self._save).pack(side="right", padx=(0, 8))

    def _save(self) -> None:
        result = deepcopy(self.initial)
        self.form.apply(result)
        self.result = result
        self.destroy()


class BlockTypeDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent)
        self.title("Choose block type")
        self.geometry("540x440")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.result: str | None = None
        self.types = list(BLOCK_ORDER)

        outer = ttk.Frame(self, padding=16, style="App.TFrame")
        outer.pack(fill="both", expand=True)
        ttk.Label(
            outer,
            text="Choose a block type. Scroll to see every option, including Margin notes.",
            style="AppHelp.TLabel",
        ).pack(anchor="w", pady=(0, 8))
        list_frame = ttk.Frame(outer, style="App.TFrame")
        list_frame.pack(fill="both", expand=True)
        self.listbox = tk.Listbox(list_frame, font=("Segoe UI", 10), activestyle="none")
        scrollbar = ttk.Scrollbar(list_frame, orient="vertical", command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        for block_type in self.types:
            schema = BLOCK_SCHEMAS[block_type]
            self.listbox.insert("end", f"{schema['label']} — {schema['description']}")
        self.listbox.selection_set(0)
        self.listbox.bind("<Double-Button-1>", lambda _event: self._accept())
        buttons = ttk.Frame(outer, style="App.TFrame")
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Add block", style="Primary.TButton", command=self._accept).pack(side="right", padx=(0, 8))

    def _accept(self) -> None:
        selection = self.listbox.curselection()
        if selection:
            self.result = self.types[selection[0]]
            self.destroy()


class BlockEditorDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        block: dict[str, Any],
        path_picker: Callable[[str], str | None],
    ) -> None:
        super().__init__(parent)
        self.block = deepcopy(block)
        block_type = str(block.get("type", ""))
        if block_type == "comparison":
            for side_name in ("left", "right"):
                side = self.block.get(side_name)
                if isinstance(side, dict) and isinstance(side.get("image"), str):
                    side["image"] = {
                        "src": side["image"],
                        "alt": side.pop("alt", ""),
                        "caption": side.pop("caption", ""),
                    }
        schema = BLOCK_SCHEMAS[block_type]
        self.title(f"Edit {schema['label']}")
        self.geometry("780x760")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.result: dict[str, Any] | None = None

        header = ttk.Frame(self, padding=(16, 14), style="App.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text=schema["label"], style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(header, text=schema["description"], style="DialogHelp.TLabel", wraplength=720).pack(anchor="w", pady=(2, 0))

        self.form = FormPane(self, COMMON_BLOCK_FIELDS + schema.get("fields", []), path_picker=path_picker)
        self.form.pack(fill="both", expand=True)
        self.form.load(self.block)

        footer = ttk.Frame(self, padding=14, style="App.TFrame")
        footer.pack(fill="x")
        ttk.Button(footer, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(footer, text="Save block", style="Primary.TButton", command=self._save).pack(side="right", padx=(0, 8))

    def _save(self) -> None:
        result = deepcopy(self.block)
        self.form.apply(result)
        result["type"] = self.block["type"]
        self.result = result
        self.destroy()


class NewProjectDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str = "Create project", duplicate: bool = False) -> None:
        super().__init__(parent)
        self.title(title)
        self.geometry("520x310")
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.result: tuple[str, str, bool] | None = None
        self.project_title = tk.StringVar()
        self.slug = tk.StringVar()
        self.use_template = tk.BooleanVar(value=True)
        self.manual_slug = False

        outer = ttk.Frame(self, padding=20, style="App.TFrame")
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Project title", style="FieldApp.TLabel").pack(anchor="w")
        title_entry = ttk.Entry(outer, textvariable=self.project_title)
        title_entry.pack(fill="x", pady=(5, 14), ipady=4)
        ttk.Label(outer, text="Folder slug", style="FieldApp.TLabel").pack(anchor="w")
        slug_entry = ttk.Entry(outer, textvariable=self.slug)
        slug_entry.pack(fill="x", pady=(5, 4), ipady=4)
        ttk.Label(outer, text="Lowercase letters, numbers, and hyphens only.", style="AppHelp.TLabel").pack(anchor="w")
        if not duplicate:
            ttk.Checkbutton(outer, text="Start with the full reusable project template", variable=self.use_template).pack(anchor="w", pady=(14, 0))
        else:
            self.use_template.set(False)
        buttons = ttk.Frame(outer, style="App.TFrame")
        buttons.pack(fill="x", pady=(22, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Create", style="Primary.TButton", command=self._accept).pack(side="right", padx=(0, 8))
        title_entry.focus_set()

        self.project_title.trace_add("write", self._title_changed)
        slug_entry.bind("<Key>", lambda _event: setattr(self, "manual_slug", True))

    def _title_changed(self, *_args: Any) -> None:
        if not self.manual_slug:
            self.slug.set(slugify(self.project_title.get()))

    def _accept(self) -> None:
        title = self.project_title.get().strip()
        slug = self.slug.get().strip()
        if not title:
            messagebox.showwarning("Project title", "Enter a project title.", parent=self)
            return
        if not SLUG_PATTERN.fullmatch(slug):
            messagebox.showwarning("Folder slug", "Use lowercase letters, numbers, and single hyphens.", parent=self)
            return
        self.result = (slug, title, self.use_template.get())
        self.destroy()


class ProjectManager(tk.Tk):
    def __init__(self, password_store: PasswordStore) -> None:
        super().__init__()
        self.title("Portfolio Project Manager")
        self.geometry("1420x900")
        self.minsize(1120, 720)
        self.configure(background="#e9e1d4")
        self.password_store = password_store

        self.config_data = load_config()
        self.repository = ProjectRepository(self.config_data)
        self.preview = PreviewServer(
            self.config_data["repository"],
            self.config_data["previewPort"],
            self.config_data["autoOpenPreview"],
        )
        self.publisher = GitPublisher(self.config_data)
        self.current_slug: str | None = None
        self.current_data: dict[str, Any] = {}
        self.manifest: dict[str, Any] = {"projects": [], "updates": []}
        self.in_manifest = tk.BooleanVar(value=True)
        self.dirty = False
        self.loading = False
        self.publish_queue: queue.Queue[tuple[bool, str]] = queue.Queue()
        self.tree_nodes: dict[str, dict[str, Any]] = {}
        self.project_rows: list[str] = []
        self.forms: list[FormPane] = []
        self.updates: list[dict[str, Any]] = []

        icon_path = self.config_data["repository"] / "assets" / "site-icon-favicon.png"
        if icon_path.exists():
            try:
                self.app_icon = tk.PhotoImage(file=icon_path)
                self.iconphoto(True, self.app_icon)
            except tk.TclError:
                pass

        self._style()
        self._build_menu()
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._refresh_projects()
        self.after(250, self._poll_publish)

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)
        security_menu = tk.Menu(menu_bar, tearoff=False)
        security_menu.add_command(label="Change manager password…", command=self._change_manager_password)
        security_menu.add_separator()
        security_menu.add_command(label="Lock and exit", command=self._close)
        menu_bar.add_cascade(label="Security", menu=security_menu)
        self.config(menu=menu_bar)

    def _change_manager_password(self) -> None:
        self.password_store.change_password_interactive(self, "Portfolio Project Manager")

    def _style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background="#e9e1d4")
        style.configure("Panel.TFrame", background="#f5f1e8")
        style.configure("Sidebar.TFrame", background="#203d3b")
        style.configure("Toolbar.TFrame", background="#dfd3c2")
        style.configure("Title.TLabel", background="#203d3b", foreground="#fffaf0", font=("Segoe UI", 18, "bold"))
        style.configure("Sidebar.TLabel", background="#203d3b", foreground="#d9e4df", font=("Segoe UI", 9))
        style.configure("Field.TLabel", background="#f5f1e8", foreground="#30271e", font=("Segoe UI", 10, "bold"))
        style.configure("Help.TLabel", background="#f5f1e8", foreground="#75695e", font=("Segoe UI", 8))
        style.configure("MutedPanel.TLabel", background="#f5f1e8", foreground="#75695e", font=("Segoe UI", 9))
        style.configure("FieldApp.TLabel", background="#e9e1d4", foreground="#30271e", font=("Segoe UI", 10, "bold"))
        style.configure("AppHelp.TLabel", background="#e9e1d4", foreground="#75695e", font=("Segoe UI", 9))
        style.configure("DialogTitle.TLabel", background="#e9e1d4", foreground="#203d3b", font=("Segoe UI", 16, "bold"))
        style.configure("DialogHelp.TLabel", background="#e9e1d4", foreground="#675e54", font=("Segoe UI", 9))
        style.configure("Status.TLabel", background="#dfd3c2", foreground="#203d3b", font=("Segoe UI", 9, "bold"))
        style.configure("Primary.TButton", background="#1f5b57", foreground="white", font=("Segoe UI", 9, "bold"), padding=(12, 7))
        style.map("Primary.TButton", background=[("active", "#2a736d"), ("disabled", "#91a4a1")])
        style.configure("Danger.TButton", background="#8b4b46", foreground="white", padding=(10, 6))
        style.map("Danger.TButton", background=[("active", "#a25b54")])
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _build(self) -> None:
        paned = ttk.Panedwindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        sidebar = ttk.Frame(paned, style="Sidebar.TFrame", width=270, padding=16)
        workspace = ttk.Frame(paned, style="App.TFrame")
        paned.add(sidebar, weight=0)
        paned.add(workspace, weight=1)

        ttk.Label(sidebar, text="Project Manager", style="Title.TLabel").pack(anchor="w")
        ttk.Label(sidebar, text="JSON project posts", style="Sidebar.TLabel").pack(anchor="w", pady=(0, 14))
        self.project_list = tk.Listbox(sidebar, bg="#f7f2e8", fg="#243633", selectbackground="#b98b5f", activestyle="none", font=("Segoe UI", 9), borderwidth=0)
        self.project_list.pack(fill="both", expand=True)
        self.project_list.bind("<<ListboxSelect>>", self._select_project)
        side_buttons = ttk.Frame(sidebar, style="Sidebar.TFrame")
        side_buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(side_buttons, text="New", command=self._new_project).pack(side="left", fill="x", expand=True)
        ttk.Button(side_buttons, text="Duplicate", command=self._duplicate_project).pack(side="left", fill="x", expand=True, padx=5)
        ttk.Button(side_buttons, text="Remove", style="Danger.TButton", command=self._remove_project).pack(side="left", fill="x", expand=True)

        toolbar = ttk.Frame(workspace, style="Toolbar.TFrame", padding=(12, 10))
        toolbar.pack(fill="x")
        self.project_title_var = tk.StringVar(value="Select a project")
        ttk.Label(toolbar, textvariable=self.project_title_var, style="Status.TLabel").pack(side="left")
        ttk.Checkbutton(toolbar, text="Included in archive manifest", variable=self.in_manifest, command=self._mark_dirty).pack(side="left", padx=(16, 0))
        self.publish_button = ttk.Button(toolbar, text="Commit & push", style="Primary.TButton", command=self._publish)
        self.publish_button.pack(side="right")
        ttk.Button(toolbar, text="Preview", command=self._preview_project).pack(side="right", padx=(0, 6))
        ttk.Button(toolbar, text="Validate", command=self._validate).pack(side="right", padx=(0, 6))
        ttk.Button(toolbar, text="Save", style="Primary.TButton", command=self._save).pack(side="right", padx=(0, 6))

        self.notebook = ttk.Notebook(workspace)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self._build_forms()
        self._build_blocks_tab()
        self._build_updates_tab()
        self._build_media_tab()
        self._build_json_tab()

        status_bar = ttk.Frame(workspace, style="Toolbar.TFrame", padding=(12, 8))
        status_bar.pack(fill="x", padx=10, pady=(8, 10))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status_bar, textvariable=self.status_var, style="Status.TLabel").pack(side="left")
        ttk.Button(status_bar, text="Preview archive", command=self._preview_archive).pack(side="right")
        ttk.Button(status_bar, text="Open project folder", command=self._open_project_folder).pack(side="right", padx=(0, 6))

    def _build_forms(self) -> None:
        for tab_name, fields in TOP_LEVEL_TABS.items():
            frame = ttk.Frame(self.notebook, style="Panel.TFrame")
            self.notebook.add(frame, text=tab_name)
            form = FormPane(frame, fields, changed=self._mark_dirty, path_picker=self._pick_media_path)
            form.pack(fill="both", expand=True)
            self.forms.append(form)

    def _build_blocks_tab(self) -> None:
        frame = ttk.Frame(self.notebook, style="Panel.TFrame", padding=10)
        self.notebook.add(frame, text="Content blocks")
        self.block_tree = ttk.Treeview(frame, columns=("type", "summary"), show="tree headings")
        self.block_tree.heading("#0", text="Order / nesting")
        self.block_tree.heading("type", text="Block type")
        self.block_tree.heading("summary", text="Content")
        self.block_tree.column("#0", width=230)
        self.block_tree.column("type", width=140)
        self.block_tree.column("summary", width=520)
        self.block_tree.pack(side="left", fill="both", expand=True)
        self.block_tree.bind("<Double-Button-1>", lambda _event: self._edit_block())
        controls = ttk.Frame(frame, style="Panel.TFrame")
        controls.pack(side="left", fill="y", padx=(10, 0))
        for text, command in (
            ("Add sibling", self._add_sibling_block),
            ("Add child", self._add_child_block),
            ("Edit", self._edit_block),
            ("Duplicate", self._duplicate_block),
            ("Move up", lambda: self._move_block(-1)),
            ("Move down", lambda: self._move_block(1)),
            ("Delete", self._delete_block),
        ):
            ttk.Button(controls, text=text, command=command, width=15).pack(fill="x", pady=(0, 6))

    def _build_updates_tab(self) -> None:
        frame = ttk.Frame(self.notebook, style="Panel.TFrame", padding=14)
        self.notebook.add(frame, text="Archive updates")
        ttk.Label(frame, text="Updates shown at the top of the project archive", style="Field.TLabel").pack(anchor="w", pady=(0, 8))
        self.update_list = tk.Listbox(frame, font=("Segoe UI", 10), activestyle="none")
        self.update_list.pack(side="left", fill="both", expand=True)
        self.update_list.bind("<Double-Button-1>", lambda _event: self._edit_update())
        controls = ttk.Frame(frame, style="Panel.TFrame")
        controls.pack(side="left", fill="y", padx=(10, 0))
        for text, command in (
            ("Add update", self._add_update),
            ("Edit", self._edit_update),
            ("Duplicate", self._duplicate_update),
            ("Move up", lambda: self._move_update(-1)),
            ("Move down", lambda: self._move_update(1)),
            ("Remove", self._remove_update),
        ):
            ttk.Button(controls, text=text, command=command, width=14).pack(fill="x", pady=(0, 6))

    def _build_media_tab(self) -> None:
        frame = ttk.Frame(self.notebook, style="Panel.TFrame", padding=14)
        self.notebook.add(frame, text="Media & files")
        ttk.Label(frame, text="Files stored with this project", style="Field.TLabel").pack(anchor="w", pady=(0, 8))
        self.media_list = ttk.Treeview(frame, columns=("kind", "size"), show="tree headings")
        self.media_list.heading("#0", text="Relative path")
        self.media_list.heading("kind", text="Folder")
        self.media_list.heading("size", text="Size")
        self.media_list.pack(side="left", fill="both", expand=True)
        controls = ttk.Frame(frame, style="Panel.TFrame")
        controls.pack(side="left", fill="y", padx=(10, 0))
        ttk.Button(controls, text="Add images", command=lambda: self._add_media("images")).pack(fill="x", pady=(0, 6))
        ttk.Button(controls, text="Add videos", command=lambda: self._add_media("videos")).pack(fill="x", pady=(0, 6))
        ttk.Button(controls, text="Add files", command=lambda: self._add_media("files")).pack(fill="x", pady=(0, 6))
        ttk.Button(controls, text="Refresh", command=self._refresh_media).pack(fill="x", pady=(0, 6))
        ttk.Button(controls, text="Copy path", command=self._copy_media_path).pack(fill="x", pady=(0, 6))

    def _build_json_tab(self) -> None:
        frame = ttk.Frame(self.notebook, style="Panel.TFrame", padding=10)
        self.notebook.add(frame, text="JSON & validation")
        top = ttk.Frame(frame, style="Panel.TFrame")
        top.pack(fill="x", pady=(0, 8))
        ttk.Button(top, text="Refresh JSON from forms", command=self._sync_json).pack(side="left")
        ttk.Button(top, text="Apply edited JSON", command=self._apply_json).pack(side="left", padx=6)
        ttk.Button(top, text="Import JSON…", command=self._import_json).pack(side="left")
        ttk.Button(top, text="Export copy…", command=self._export_json).pack(side="left", padx=6)
        vertical = ttk.Panedwindow(frame, orient="vertical")
        vertical.pack(fill="both", expand=True)
        json_frame = ttk.Frame(vertical, style="Panel.TFrame")
        validation_frame = ttk.Frame(vertical, style="Panel.TFrame")
        vertical.add(json_frame, weight=3)
        vertical.add(validation_frame, weight=1)
        self.json_text = tk.Text(json_frame, wrap="none", font=("Consolas", 10), undo=True)
        self.json_text.pack(fill="both", expand=True)
        self.validation_text = tk.Text(validation_frame, wrap="word", font=("Consolas", 9), state="disabled", height=8)
        self.validation_text.pack(fill="both", expand=True)

    def _mark_dirty(self) -> None:
        if self.loading or not self.current_slug:
            return
        self.dirty = True
        self._update_window_title()

    def _update_window_title(self) -> None:
        marker = " *" if self.dirty else ""
        project = self.current_data.get("title", self.current_slug or "No project")
        self.title(f"Portfolio Project Manager — {project}{marker}")

    def _refresh_projects(self, select_slug: str | None = None) -> None:
        slugs = self.repository.list_projects()
        self.project_list.delete(0, "end")
        self.project_rows = slugs
        for slug in slugs:
            try:
                title = self.repository.load_project(slug).get("title", "Untitled project")
            except ProjectManagerError:
                title = "Invalid project.json"
            self.project_list.insert("end", f"{title}  —  {slug}")
        if select_slug in slugs:
            index = slugs.index(select_slug)
            self.project_list.selection_set(index)
            self.project_list.see(index)
            self._load_project(select_slug)
        elif slugs and self.current_slug is None:
            self.project_list.selection_set(0)
            self._load_project(slugs[0])

    def _select_project(self, _event: tk.Event[Any]) -> None:
        selection = self.project_list.curselection()
        if not selection:
            return
        slug = self.project_rows[selection[0]]
        if slug == self.current_slug:
            return
        if not self._confirm_discard_or_save():
            self._restore_project_selection()
            return
        self._load_project(slug)

    def _restore_project_selection(self) -> None:
        self.project_list.selection_clear(0, "end")
        if self.current_slug in self.project_rows:
            self.project_list.selection_set(self.project_rows.index(self.current_slug))

    def _confirm_discard_or_save(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel("Unsaved project", "Save changes before switching projects?", parent=self)
        if answer is None:
            return False
        if answer:
            return self._save(show_message=False)
        return True

    def _load_project(self, slug: str) -> None:
        try:
            data = self.repository.load_project(slug)
            manifest = self.repository.load_manifest()
        except ProjectManagerError as error:
            messagebox.showerror("Open project", str(error), parent=self)
            return
        self.loading = True
        try:
            self.current_slug = slug
            self.current_data = data
            self.manifest = manifest
            self.updates = deepcopy(manifest.get("updates", []))
            self.in_manifest.set(self.repository.is_in_manifest(slug, manifest))
            for form in self.forms:
                form.load(data)
            self._refresh_block_tree()
            self._refresh_updates()
            self._refresh_media()
            self._sync_json(collect=False)
            self.project_title_var.set(f"{data.get('title', 'Untitled project')}  ·  projects/{slug}/")
            self.status_var.set("Project loaded")
            self.dirty = False
            self._update_window_title()
        finally:
            self.loading = False

    def _collect(self) -> dict[str, Any]:
        data = deepcopy(self.current_data)
        for form in self.forms:
            form.apply(data)
        data.setdefault("blocks", self.current_data.get("blocks", []))
        self.current_data = data
        self.manifest["updates"] = deepcopy(self.updates)
        return data

    def _save(self, show_message: bool = True) -> bool:
        if not self.current_slug:
            return False
        try:
            data = self._collect()
            self.repository.save_project(self.current_slug, data, self.manifest, self.in_manifest.get())
        except ProjectManagerError as error:
            messagebox.showerror("Save project", str(error), parent=self)
            return False
        self.dirty = False
        self.project_title_var.set(f"{data.get('title', 'Untitled project')}  ·  projects/{self.current_slug}/")
        self.status_var.set("Project and archive manifest saved")
        self._update_window_title()
        self._refresh_projects(self.current_slug)
        if show_message:
            messagebox.showinfo("Project saved", "Project JSON and archive manifest were saved.", parent=self)
        return True

    def _new_project(self) -> None:
        if not self._confirm_discard_or_save():
            return
        dialog = NewProjectDialog(self)
        self.wait_window(dialog)
        if not dialog.result:
            return
        slug, title, use_template = dialog.result
        try:
            self.repository.create_project(slug, title, use_template)
        except ProjectManagerError as error:
            messagebox.showerror("Create project", str(error), parent=self)
            return
        self.current_slug = None
        self._refresh_projects(slug)
        self.status_var.set("New private project created and added to the manifest")

    def _duplicate_project(self) -> None:
        if not self.current_slug:
            return
        if not self._confirm_discard_or_save():
            return
        dialog = NewProjectDialog(self, title="Duplicate project", duplicate=True)
        self.wait_window(dialog)
        if not dialog.result:
            return
        slug, title, _ = dialog.result
        try:
            self.repository.duplicate_project(self.current_slug, slug, title)
        except ProjectManagerError as error:
            messagebox.showerror("Duplicate project", str(error), parent=self)
            return
        self.current_slug = None
        self._refresh_projects(slug)

    def _remove_project(self) -> None:
        if not self.current_slug:
            return
        slug = self.current_slug
        title = str(self.current_data.get("title", slug))
        project_path = self.repository.project_dir(slug)
        if not messagebox.askyesno(
            "Remove project",
            f"Move '{slug}' to the Project Manager trash and remove it from the archive manifest?\n\nThe folder remains recoverable.",
            icon="warning",
            parent=self,
        ):
            return
        try:
            destination = self.repository.move_project_to_trash(slug)
        except ProjectManagerError as error:
            messagebox.showerror("Remove project", str(error), parent=self)
            return
        self.current_slug = None
        self.current_data = {}
        self.dirty = False
        self._refresh_projects()
        publish_removal = messagebox.askyesno(
            "Project moved",
            f"Recoverable copy:\n{destination}\n\nCommit and push the project removal now?",
            parent=self,
        )
        if publish_removal:
            self.publish_button.configure(state="disabled")
            self.status_var.set("Committing and pushing project removal…")

            def work() -> None:
                try:
                    message = self.publisher.publish(
                        slug,
                        title,
                        self.repository.manifest_path,
                        project_path,
                        commit_message=f"Remove project: {title}",
                    )
                    result = (True, message)
                except ProjectManagerError as error:
                    result = (False, f"Project moved locally, but GitHub push failed. {error}")
                except Exception as error:
                    result = (False, f"Unexpected publishing error: {error}")
                self.publish_queue.put(result)

            threading.Thread(target=work, daemon=True).start()

    def _selected_tree_node(self) -> dict[str, Any] | None:
        selection = self.block_tree.selection()
        return self.tree_nodes.get(selection[0]) if selection else None

    def _block_title(self, block: dict[str, Any]) -> str:
        for key in ("title", "text", "label", "caption", "placeholder", "src", "content"):
            value = block.get(key)
            if value:
                return compact_summary(value)
        return ""

    def _refresh_block_tree(self, select_block: dict[str, Any] | None = None) -> None:
        self.block_tree.delete(*self.block_tree.get_children())
        self.tree_nodes.clear()
        blocks = self.current_data.setdefault("blocks", [])

        def walk(container: list[dict[str, Any]], parent: str = "") -> None:
            for index, block in enumerate(container):
                block_type = str(block.get("type", "unknown"))
                schema = BLOCK_SCHEMAS.get(block_type, {"label": "Unknown"})
                item = self.block_tree.insert(
                    parent,
                    "end",
                    text=f"{index + 1}",
                    values=(schema["label"], self._block_title(block)),
                    open=True,
                )
                self.tree_nodes[item] = {"kind": "block", "block": block, "container": container, "index": index}
                if block_type == "section":
                    child = block.setdefault("blocks", [])
                    walk(child, item)
                elif block_type in {"two-column", "three-column"}:
                    count = 2 if block_type == "two-column" else 3
                    columns = block.setdefault("columns", [])
                    while len(columns) < count:
                        columns.append({"blocks": []})
                    for column_index, column in enumerate(columns[:count]):
                        children = column.setdefault("blocks", [])
                        column_item = self.block_tree.insert(item, "end", text=f"Column {column_index + 1}", values=("Container", ""), open=True)
                        self.tree_nodes[column_item] = {"kind": "container", "container": children, "owner": block}
                        walk(children, column_item)

        walk(blocks)
        if select_block:
            for item, node in self.tree_nodes.items():
                if node.get("block") is select_block:
                    self.block_tree.selection_set(item)
                    self.block_tree.see(item)
                    break

    def _choose_new_block(self) -> dict[str, Any] | None:
        chooser = BlockTypeDialog(self)
        self.wait_window(chooser)
        if not chooser.result:
            return None
        block = new_block(chooser.result)
        editor = BlockEditorDialog(self, block, self._pick_media_path)
        self.wait_window(editor)
        return editor.result

    def _add_sibling_block(self) -> None:
        if not self.current_slug:
            return
        block = self._choose_new_block()
        if not block:
            return
        node = self._selected_tree_node()
        if node and node["kind"] == "block":
            container = node["container"]
            container.insert(node["index"] + 1, block)
        elif node and node["kind"] == "container":
            node["container"].append(block)
        else:
            self.current_data.setdefault("blocks", []).append(block)
        self._mark_dirty()
        self._refresh_block_tree(block)

    def _add_child_block(self) -> None:
        node = self._selected_tree_node()
        if not node:
            messagebox.showinfo("Add child", "Select a section or column first.", parent=self)
            return
        if node["kind"] == "container":
            container = node["container"]
        else:
            block = node["block"]
            if block.get("type") != "section":
                messagebox.showinfo("Add child", "Child blocks can be added to sections or an individual column.", parent=self)
                return
            container = block.setdefault("blocks", [])
        child = self._choose_new_block()
        if child:
            container.append(child)
            self._mark_dirty()
            self._refresh_block_tree(child)

    def _edit_block(self) -> None:
        node = self._selected_tree_node()
        if not node or node["kind"] != "block":
            return
        dialog = BlockEditorDialog(self, node["block"], self._pick_media_path)
        self.wait_window(dialog)
        if dialog.result is not None:
            container = node["container"]
            container[node["index"]] = dialog.result
            self._mark_dirty()
            self._refresh_block_tree(dialog.result)

    def _duplicate_block(self) -> None:
        node = self._selected_tree_node()
        if not node or node["kind"] != "block":
            return
        duplicate = deepcopy(node["block"])
        node["container"].insert(node["index"] + 1, duplicate)
        self._mark_dirty()
        self._refresh_block_tree(duplicate)

    def _move_block(self, direction: int) -> None:
        node = self._selected_tree_node()
        if not node or node["kind"] != "block":
            return
        container = node["container"]
        index = node["index"]
        target = index + direction
        if not 0 <= target < len(container):
            return
        block = container[index]
        container[index], container[target] = container[target], container[index]
        self._mark_dirty()
        self._refresh_block_tree(block)

    def _delete_block(self) -> None:
        node = self._selected_tree_node()
        if not node or node["kind"] != "block":
            return
        if not messagebox.askyesno("Delete block", "Delete this block and all of its nested content?", parent=self):
            return
        node["container"].pop(node["index"])
        self._mark_dirty()
        self._refresh_block_tree()

    def _refresh_updates(self, selected: int | None = None) -> None:
        self.update_list.delete(0, "end")
        for index, update in enumerate(self.updates):
            self.update_list.insert("end", f"{update.get('date', 'Undated')} — {compact_summary(update.get('content', 'Untitled update'))} [{update.get('visibility', 'public')}]")
        if self.updates:
            index = min(selected if selected is not None else 0, len(self.updates) - 1)
            self.update_list.selection_set(index)

    def _selected_update(self) -> int | None:
        selection = self.update_list.curselection()
        return selection[0] if selection else None

    def _add_update(self) -> None:
        initial = {"date": date.today().isoformat(), "content": self.current_data.get("title", ""), "visibility": "public"}
        dialog = RecordEditorDialog(self, "Add archive update", initial, UPDATE_FIELDS)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.updates.append(dialog.result)
            self._mark_dirty()
            self._refresh_updates(len(self.updates) - 1)

    def _edit_update(self) -> None:
        index = self._selected_update()
        if index is None:
            return
        dialog = RecordEditorDialog(self, "Edit archive update", self.updates[index], UPDATE_FIELDS)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.updates[index] = dialog.result
            self._mark_dirty()
            self._refresh_updates(index)

    def _duplicate_update(self) -> None:
        index = self._selected_update()
        if index is None:
            return
        self.updates.insert(index + 1, deepcopy(self.updates[index]))
        self._mark_dirty()
        self._refresh_updates(index + 1)

    def _move_update(self, direction: int) -> None:
        index = self._selected_update()
        if index is None:
            return
        target = index + direction
        if not 0 <= target < len(self.updates):
            return
        self.updates[index], self.updates[target] = self.updates[target], self.updates[index]
        self._mark_dirty()
        self._refresh_updates(target)

    def _remove_update(self) -> None:
        index = self._selected_update()
        if index is None:
            return
        self.updates.pop(index)
        self._mark_dirty()
        self._refresh_updates(max(0, index - 1))

    def _pick_media_path(self, media_dir: str) -> str | None:
        if not self.current_slug:
            messagebox.showinfo("Select project", "Open or create a project first.", parent=self)
            return None
        source = filedialog.askopenfilename(parent=self, title="Choose project file")
        if not source:
            return None
        source_path = Path(source).resolve()
        project_dir = self.repository.project_dir(self.current_slug)
        try:
            return source_path.relative_to(project_dir).as_posix()
        except ValueError:
            pass
        try:
            relative_repo = source_path.relative_to(self.config_data["repository"])
            return os.path.relpath(self.config_data["repository"] / relative_repo, project_dir).replace("\\", "/")
        except ValueError:
            pass
        if not messagebox.askyesno("Copy file", f"Copy this file into the project's {media_dir}/ folder?", parent=self):
            return None
        try:
            paths = self.repository.import_media(self.current_slug, [source], media_dir or "files")
        except OSError as error:
            messagebox.showerror("Copy file", str(error), parent=self)
            return None
        self._refresh_media()
        return paths[0] if paths else None

    def _add_media(self, media_dir: str) -> None:
        if not self.current_slug:
            return
        sources = filedialog.askopenfilenames(parent=self, title=f"Add files to {media_dir}")
        if not sources:
            return
        try:
            paths = self.repository.import_media(self.current_slug, sources, media_dir)
        except OSError as error:
            messagebox.showerror("Add media", str(error), parent=self)
            return
        self._refresh_media()
        self.status_var.set(f"Added {len(paths)} file(s) to {media_dir}/")

    def _refresh_media(self) -> None:
        if not hasattr(self, "media_list"):
            return
        self.media_list.delete(*self.media_list.get_children())
        if not self.current_slug:
            return
        project_dir = self.repository.project_dir(self.current_slug)
        for folder_name in ("images", "videos", "files"):
            folder = project_dir / folder_name
            if not folder.exists():
                continue
            for path in sorted(item for item in folder.rglob("*") if item.is_file()):
                size = path.stat().st_size
                size_label = f"{size / 1_048_576:.1f} MB" if size >= 1_048_576 else f"{max(1, size // 1024)} KB"
                self.media_list.insert("", "end", text=path.relative_to(project_dir).as_posix(), values=(folder_name, size_label))

    def _copy_media_path(self) -> None:
        selection = self.media_list.selection()
        if not selection:
            return
        path = self.media_list.item(selection[0], "text")
        self.clipboard_clear()
        self.clipboard_append(path)
        self.status_var.set(f"Copied: {path}")

    def _open_project_folder(self) -> None:
        if not self.current_slug:
            return
        path = self.repository.project_dir(self.current_slug)
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except (AttributeError, OSError) as error:
            messagebox.showerror("Open folder", str(error), parent=self)

    def _sync_json(self, collect: bool = True) -> None:
        if not self.current_slug:
            return
        data = self._collect() if collect else self.current_data
        self.json_text.delete("1.0", "end")
        self.json_text.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
        self._show_validation(self._validation_issues(data))

    def _apply_json(self) -> None:
        if not self.current_slug:
            return
        try:
            data = json.loads(self.json_text.get("1.0", "end-1c"))
        except json.JSONDecodeError as error:
            messagebox.showerror("Invalid JSON", f"Line {error.lineno}, column {error.colno}: {error.msg}", parent=self)
            return
        if not isinstance(data, dict):
            messagebox.showerror("Invalid project", "Project JSON must contain one object.", parent=self)
            return
        if not messagebox.askyesno("Apply JSON", "Replace the form values and block tree with this JSON?", parent=self):
            return
        self.current_data = data
        self.loading = True
        try:
            for form in self.forms:
                form.load(data)
            self._refresh_block_tree()
        finally:
            self.loading = False
        self._mark_dirty()
        self._show_validation(self._validation_issues(data))

    def _import_json(self) -> None:
        source = filedialog.askopenfilename(parent=self, title="Import project JSON", filetypes=(("JSON files", "*.json"), ("All files", "*.*")))
        if not source:
            return
        try:
            data = json.loads(Path(source).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            messagebox.showerror("Import JSON", str(error), parent=self)
            return
        if not isinstance(data, dict):
            messagebox.showerror("Import JSON", "Imported JSON must contain one object.", parent=self)
            return
        self.json_text.delete("1.0", "end")
        self.json_text.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))
        self._apply_json()

    def _export_json(self) -> None:
        if not self.current_slug:
            return
        target = filedialog.asksaveasfilename(parent=self, defaultextension=".json", initialfile=f"{self.current_slug}-project.json", filetypes=(("JSON files", "*.json"),))
        if not target:
            return
        try:
            atomic_write_json(Path(target), self._collect())
        except ProjectManagerError as error:
            messagebox.showerror("Export JSON", str(error), parent=self)

    def _show_validation(self, issues: list[ValidationIssue]) -> None:
        self.validation_text.configure(state="normal")
        self.validation_text.delete("1.0", "end")
        if issues:
            self.validation_text.insert("1.0", "\n".join(issue.display() for issue in issues))
        else:
            self.validation_text.insert("1.0", "No validation problems found ✓")
        self.validation_text.configure(state="disabled")

    def _validation_issues(self, data: dict[str, Any] | None = None) -> list[ValidationIssue]:
        if not self.current_slug:
            return []
        project = data if data is not None else self._collect()
        return validate_project(project, self.repository.project_dir(self.current_slug)) + validate_manifest(
            self.manifest,
            self.repository.projects_dir,
        )

    def _validate(self, show_dialog: bool = True) -> list[ValidationIssue]:
        if not self.current_slug:
            return []
        data = self._collect()
        issues = self._validation_issues(data)
        self._show_validation(issues)
        self.notebook.select(self.notebook.tabs()[-1])
        errors = sum(issue.level == "error" for issue in issues)
        warnings = len(issues) - errors
        self.status_var.set(f"Validation: {errors} error(s), {warnings} warning(s)")
        if show_dialog:
            messagebox.showinfo("Validation complete", f"Errors: {errors}\nWarnings: {warnings}", parent=self)
        return issues

    def _preview_project(self) -> None:
        if not self.current_slug or not self._save(show_message=False):
            return
        try:
            url = self.preview.open_project(self.current_slug)
        except OSError as error:
            messagebox.showerror("Preview", str(error), parent=self)
            return
        self.status_var.set(f"Preview opened: {url}")

    def _preview_archive(self) -> None:
        try:
            url = self.preview.open_archive()
        except OSError as error:
            messagebox.showerror("Preview", str(error), parent=self)
            return
        self.status_var.set(f"Archive preview opened: {url}")

    def _publish(self) -> None:
        if not self.current_slug or not self._save(show_message=False):
            return
        issues = self._validate(show_dialog=False)
        errors = [issue for issue in issues if issue.level == "error"]
        warnings = [issue for issue in issues if issue.level == "warning"]
        if errors:
            messagebox.showerror("Cannot publish", f"Fix {len(errors)} validation error(s) before publishing.", parent=self)
            return
        if warnings and not messagebox.askyesno("Publish with warnings?", f"There are {len(warnings)} warning(s). Publish anyway?", parent=self):
            return
        slug = self.current_slug
        title = str(self.current_data.get("title", slug))
        project_path = self.repository.project_dir(slug)
        self.publish_button.configure(state="disabled")
        self.status_var.set("Committing and pushing project…")

        def work() -> None:
            try:
                message = self.publisher.publish(slug, title, self.repository.manifest_path, project_path)
                result = (True, message)
            except ProjectManagerError as error:
                result = (False, f"Project saved locally, but GitHub push failed. {error}")
            except Exception as error:
                result = (False, f"Unexpected publishing error: {error}")
            self.publish_queue.put(result)

        threading.Thread(target=work, daemon=True).start()

    def _poll_publish(self) -> None:
        try:
            while True:
                success, message = self.publish_queue.get_nowait()
                self.publish_button.configure(state="normal")
                self.status_var.set(message)
                if success:
                    messagebox.showinfo("Project published", message, parent=self)
                else:
                    messagebox.showerror("Publishing failed", message, parent=self)
        except queue.Empty:
            pass
        self.after(250, self._poll_publish)

    def _close(self) -> None:
        if not self._confirm_discard_or_save():
            return
        self.preview.stop()
        self.destroy()


def main() -> None:
    password_store = PasswordStore()
    unlock_window = tk.Tk()
    unlock_window.withdraw()
    if not password_store.authenticate_interactive(unlock_window, "Portfolio Project Manager"):
        unlock_window.destroy()
        return
    unlock_window.destroy()

    try:
        app = ProjectManager(password_store)
    except ProjectManagerError as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Project Manager setup", str(error), parent=root)
        root.destroy()
        return
    app.mainloop()


if __name__ == "__main__":
    main()
