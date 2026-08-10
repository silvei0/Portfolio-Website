"""Repository, validation, preview, media, and Git services for Project Manager."""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from schemas import BLOCK_SCHEMAS


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"
EXAMPLE_CONFIG_PATH = APP_DIR / "config.example.json"
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ProjectManagerError(Exception):
    """Friendly application error."""


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    path: str
    message: str

    def display(self) -> str:
        marker = "ERROR" if self.level == "error" else "WARNING"
        return f"[{marker}] {self.path}: {self.message}"


def load_json(path: Path, fallback: Any = None) -> Any:
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return fallback
    except json.JSONDecodeError as error:
        raise ProjectManagerError(f"Invalid JSON in {path.name}: line {error.lineno}, column {error.colno}.") from error
    except OSError as error:
        raise ProjectManagerError(f"Could not read {path}: {error}") from error


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    try:
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    except OSError as error:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise ProjectManagerError(f"Could not save {path}: {error}") from error


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def resolve_from(base: Path, configured: str) -> Path:
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def ensure_inside(base: Path, path: Path, label: str = "Path") -> Path:
    base = base.resolve()
    path = path.resolve()
    try:
        path.relative_to(base)
    except ValueError as error:
        raise ProjectManagerError(f"{label} must stay inside {base}.") from error
    return path


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        if not EXAMPLE_CONFIG_PATH.exists():
            raise ProjectManagerError("config.json and config.example.json are missing.")
        CONFIG_PATH.write_text(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    config = load_json(CONFIG_PATH)
    if not isinstance(config, dict):
        raise ProjectManagerError("project-manager/config.json must contain one JSON object.")

    repository = resolve_from(APP_DIR, str(config.get("repositoryPath", "..")))
    if not (repository / ".git").exists():
        raise ProjectManagerError(f"Configured repository is not a Git working tree: {repository}")

    projects_directory = ensure_inside(
        repository,
        resolve_from(repository, str(config.get("projectsDirectory", "projects"))),
        "projectsDirectory",
    )
    manifest_path = ensure_inside(
        repository,
        resolve_from(repository, str(config.get("manifestPath", "projects/projects.json"))),
        "manifestPath",
    )
    template_directory = ensure_inside(
        repository,
        resolve_from(repository, str(config.get("templateDirectory", "projects/project-template"))),
        "templateDirectory",
    )

    config.update(
        {
            "repository": repository,
            "projectsDirectoryPath": projects_directory,
            "manifestFile": manifest_path,
            "templateDirectoryPath": template_directory,
            "gitRemote": str(config.get("gitRemote", "origin")).strip() or "origin",
            "gitBranch": str(config.get("gitBranch", "")).strip(),
            "previewPort": int(config.get("previewPort", 8767)),
            "autoOpenPreview": bool(config.get("autoOpenPreview", True)),
            "commitMessage": str(config.get("commitMessage", "Update project: {title}")).strip()
            or "Update project: {title}",
            "backupCount": max(1, int(config.get("backupCount", 10))),
        }
    )
    return config


def clean_empty(value: Any) -> Any:
    """Remove empty UI values while preserving meaningful false/zero values."""
    if isinstance(value, dict):
        cleaned = {key: clean_empty(item) for key, item in value.items()}
        return {
            key: item
            for key, item in cleaned.items()
            if item not in (None, "", [], {})
            and not (key in {"hideFromContents"} and item is False)
        }
    if isinstance(value, list):
        return [clean_empty(item) for item in value if clean_empty(item) not in (None, "", [], {})]
    return value


def default_project(title: str) -> dict[str, Any]:
    return {
        "siteName": "Fiza's Project Portfolio",
        "title": title,
        "subtitle": "",
        "description": "",
        "metaDescription": f"A project case study by Fiza Mansoor: {title}.",
        "tags": [],
        "archive": {
            "visibility": "private",
            "featured": False,
            "currentlyWorking": False,
            "date": date.today().isoformat(),
            "cardDescription": "",
            "thumbnail": {"placeholder": "Project preview", "alt": f"Placeholder for {title}"},
        },
        "discipline": "",
        "status": "In progress",
        "timeline": "",
        "projectType": "Personal",
        "role": "",
        "tools": [],
        "hero": {
            "placeholder": "Main project image",
            "placeholderHint": "Add the strongest project image.",
            "alt": f"Placeholder for the {title} hero image",
        },
        "blocks": [
            {
                "type": "section",
                "id": "overview",
                "title": "Overview",
                "intro": "Explain the project context, purpose, and why it mattered.",
                "blocks": [],
            }
        ],
    }


class ProjectRepository:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.repository: Path = config["repository"]
        self.projects_dir: Path = config["projectsDirectoryPath"]
        self.manifest_path: Path = config["manifestFile"]
        self.template_dir: Path = config["templateDirectoryPath"]
        self.backup_dir = APP_DIR / ".backups"
        self.trash_dir = APP_DIR / ".trash"

    def list_projects(self) -> list[str]:
        if not self.projects_dir.exists():
            return []
        names = []
        for folder in self.projects_dir.iterdir():
            if folder.is_dir() and folder.name != self.template_dir.name and (folder / "project.json").exists():
                names.append(folder.name)
        return sorted(names)

    def project_dir(self, slug: str) -> Path:
        if not SLUG_PATTERN.fullmatch(slug):
            raise ProjectManagerError("Project slug must use lowercase letters, numbers, and single hyphens.")
        return ensure_inside(self.projects_dir, self.projects_dir / slug, "Project folder")

    def project_json(self, slug: str) -> Path:
        return self.project_dir(slug) / "project.json"

    def load_project(self, slug: str) -> dict[str, Any]:
        data = load_json(self.project_json(slug))
        if not isinstance(data, dict):
            raise ProjectManagerError(f"{slug}/project.json must contain one JSON object.")
        data.setdefault("blocks", [])
        return data

    def load_manifest(self) -> dict[str, Any]:
        manifest = load_json(self.manifest_path, {"projects": [], "updates": []})
        if isinstance(manifest, list):
            manifest = {"projects": manifest, "updates": []}
        if not isinstance(manifest, dict):
            raise ProjectManagerError("projects.json must contain an object or project array.")
        manifest.setdefault("projects", [])
        manifest.setdefault("updates", [])
        if not isinstance(manifest["projects"], list) or not isinstance(manifest["updates"], list):
            raise ProjectManagerError("projects.json projects and updates values must be arrays.")
        return manifest

    def save_manifest(self, manifest: dict[str, Any]) -> None:
        atomic_write_json(self.manifest_path, manifest)

    def is_in_manifest(self, slug: str, manifest: dict[str, Any] | None = None) -> bool:
        manifest = manifest or self.load_manifest()
        for entry in manifest.get("projects", []):
            name = entry if isinstance(entry, str) else entry.get("folder") if isinstance(entry, dict) else ""
            if str(name).strip().strip("/").removeprefix("./") == slug:
                return True
        return False

    def set_manifest_membership(self, slug: str, included: bool, manifest: dict[str, Any]) -> None:
        entries = manifest.setdefault("projects", [])
        filtered = []
        found = False
        for entry in entries:
            name = entry if isinstance(entry, str) else entry.get("folder") if isinstance(entry, dict) else ""
            normalised = str(name).strip().strip("/").removeprefix("./")
            if normalised == slug:
                if included and not found:
                    filtered.append(entry)
                    found = True
                continue
            filtered.append(entry)
        if included and not found:
            filtered.append(slug)
        manifest["projects"] = filtered

    def create_project(self, slug: str, title: str, use_template: bool) -> dict[str, Any]:
        destination = self.project_dir(slug)
        if destination.exists():
            raise ProjectManagerError(f"A project folder named '{slug}' already exists.")
        if not self.template_dir.exists():
            raise ProjectManagerError(f"Template folder is missing: {self.template_dir}")

        try:
            destination.mkdir(parents=True)
            shutil.copy2(self.template_dir / "index.html", destination / "index.html")
            for media_folder in ("images", "videos", "files"):
                (destination / media_folder).mkdir()
            if use_template:
                project = load_json(self.template_dir / "project.json")
                if not isinstance(project, dict):
                    raise ProjectManagerError("The template project.json is invalid.")
                project["title"] = title
                project["siteName"] = "Fiza's Project Portfolio"
                project.setdefault("archive", {})["visibility"] = "private"
                project["archive"]["featured"] = False
            else:
                project = default_project(title)
            atomic_write_json(destination / "project.json", project)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise

        manifest = self.load_manifest()
        self.set_manifest_membership(slug, True, manifest)
        self.save_manifest(manifest)
        return project

    def duplicate_project(self, source_slug: str, target_slug: str, title: str) -> dict[str, Any]:
        source = self.project_dir(source_slug)
        destination = self.project_dir(target_slug)
        if destination.exists():
            raise ProjectManagerError(f"A project folder named '{target_slug}' already exists.")
        try:
            shutil.copytree(source, destination)
            project = self.load_project(target_slug)
            project["title"] = title
            project.setdefault("archive", {})["visibility"] = "private"
            project["archive"]["featured"] = False
            atomic_write_json(destination / "project.json", project)
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        manifest = self.load_manifest()
        self.set_manifest_membership(target_slug, True, manifest)
        self.save_manifest(manifest)
        return project

    def backup_project(self, slug: str, data: dict[str, Any]) -> None:
        target = self.backup_dir / slug
        target.mkdir(parents=True, exist_ok=True)
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        atomic_write_json(target / f"project-{stamp}.json", data)
        backups = sorted(target.glob("project-*.json"), reverse=True)
        for old in backups[self.config["backupCount"] :]:
            old.unlink(missing_ok=True)

    def save_project(self, slug: str, data: dict[str, Any], manifest: dict[str, Any], included: bool) -> None:
        existing = self.project_json(slug)
        if existing.exists():
            try:
                current = self.load_project(slug)
                self.backup_project(slug, current)
            except ProjectManagerError:
                pass
        atomic_write_json(existing, data)
        self.set_manifest_membership(slug, included, manifest)
        self.save_manifest(manifest)

    def move_project_to_trash(self, slug: str) -> Path:
        source = self.project_dir(slug)
        if not source.exists():
            raise ProjectManagerError(f"Project folder does not exist: {source}")
        self.trash_dir.mkdir(parents=True, exist_ok=True)
        stamp = __import__("datetime").datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = self.trash_dir / f"{slug}-{stamp}"
        shutil.move(str(source), str(destination))
        manifest = self.load_manifest()
        self.set_manifest_membership(slug, False, manifest)
        self.save_manifest(manifest)
        return destination

    def import_media(self, slug: str, sources: Iterable[str], media_dir: str) -> list[str]:
        destination_dir = self.project_dir(slug) / media_dir
        destination_dir.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for source_string in sources:
            source = Path(source_string)
            if not source.is_file():
                continue
            destination = destination_dir / source.name
            if destination.exists() and source.resolve() != destination.resolve():
                stem, suffix = destination.stem, destination.suffix
                counter = 2
                while destination.exists():
                    destination = destination_dir / f"{stem}-{counter}{suffix}"
                    counter += 1
            if source.resolve() != destination.resolve():
                shutil.copy2(source, destination)
            paths.append(destination.relative_to(self.project_dir(slug)).as_posix())
        return paths


def _is_external(value: str) -> bool:
    return value.startswith(("http://", "https://", "mailto:", "#", "data:"))


def _validate_local_path(project_dir: Path, value: Any, path: str, issues: list[ValidationIssue]) -> None:
    if not isinstance(value, str) or not value.strip() or _is_external(value.strip()):
        return
    value = value.strip()
    if "\\" in value:
        issues.append(ValidationIssue("error", path, "Use forward slashes, not Windows backslashes."))
        return
    if value.startswith("/"):
        issues.append(ValidationIssue("warning", path, "Root-relative paths can break on GitHub Pages."))
    candidate = (project_dir / value).resolve()
    if not candidate.exists():
        issues.append(ValidationIssue("error", path, f"Referenced file does not exist: {value}"))


def _validate_image(image: Any, path: str, project_dir: Path, issues: list[ValidationIssue]) -> None:
    if not isinstance(image, dict):
        return
    _validate_local_path(project_dir, image.get("src"), f"{path}.src", issues)
    if image.get("src") and image.get("decorative") is not True and not str(image.get("alt", "")).strip():
        issues.append(ValidationIssue("warning", f"{path}.alt", "Informative images should have useful alternative text."))
    rotation = image.get("rotation")
    if rotation not in (None, ""):
        try:
            if not -6 <= float(rotation) <= 6:
                issues.append(ValidationIssue("warning", f"{path}.rotation", "The renderer clamps rotation to the -6 to 6 range."))
        except (TypeError, ValueError):
            issues.append(ValidationIssue("error", f"{path}.rotation", "Rotation must be a number."))


def _validate_blocks(
    blocks: Any,
    project_dir: Path,
    issues: list[ValidationIssue],
    path: str = "blocks",
    seen_ids: set[str] | None = None,
) -> None:
    if seen_ids is None:
        seen_ids = set()
    if not isinstance(blocks, list):
        issues.append(ValidationIssue("error", path, "Blocks must be an array."))
        return
    for index, block in enumerate(blocks):
        block_path = f"{path}[{index}]"
        if not isinstance(block, dict):
            issues.append(ValidationIssue("error", block_path, "Each block must be a JSON object."))
            continue
        block_type = block.get("type")
        if block_type not in BLOCK_SCHEMAS:
            issues.append(ValidationIssue("error", f"{block_path}.type", f"Unknown block type: {block_type!r}"))
            continue
        block_id = str(block.get("id", "")).strip()
        if block_id:
            if block_id in seen_ids:
                issues.append(ValidationIssue("error", f"{block_path}.id", f"Duplicate block ID: {block_id}"))
            seen_ids.add(block_id)
            if not re.fullmatch(r"[A-Za-z0-9_-]+", block_id):
                issues.append(ValidationIssue("warning", f"{block_path}.id", "The renderer removes spaces and unsafe ID characters."))
        if block_type == "section":
            if not str(block.get("title", "")).strip():
                issues.append(ValidationIssue("warning", f"{block_path}.title", "A section should have a title."))
            _validate_blocks(block.get("blocks", []), project_dir, issues, f"{block_path}.blocks", seen_ids)
        elif block_type in {"two-column", "three-column"}:
            expected = 2 if block_type == "two-column" else 3
            columns = block.get("columns")
            if not isinstance(columns, list) or len(columns) < expected:
                issues.append(ValidationIssue("error", f"{block_path}.columns", f"{block_type} needs {expected} columns."))
            else:
                for column_index, column in enumerate(columns[:expected]):
                    _validate_blocks(
                        column.get("blocks", []) if isinstance(column, dict) else None,
                        project_dir,
                        issues,
                        f"{block_path}.columns[{column_index}].blocks",
                        seen_ids,
                    )
        elif block_type == "image":
            _validate_image(block, block_path, project_dir, issues)
            if not block.get("src") and not block.get("placeholder"):
                issues.append(ValidationIssue("warning", block_path, "Image block has neither a file nor a placeholder."))
        elif block_type == "gallery":
            images = block.get("images", [])
            if not isinstance(images, list) or not images:
                issues.append(ValidationIssue("error", f"{block_path}.images", "Gallery needs at least one image."))
            else:
                for image_index, image in enumerate(images):
                    _validate_image(image, f"{block_path}.images[{image_index}]", project_dir, issues)
        elif block_type == "video":
            if not block.get("src"):
                issues.append(ValidationIssue("error", f"{block_path}.src", "Video file is required."))
            _validate_local_path(project_dir, block.get("src"), f"{block_path}.src", issues)
            _validate_local_path(project_dir, block.get("poster"), f"{block_path}.poster", issues)
            captions = block.get("captions")
            if isinstance(captions, dict):
                _validate_local_path(project_dir, captions.get("src"), f"{block_path}.captions.src", issues)
            if block.get("autoplay") is True and block.get("muted") is not True:
                issues.append(ValidationIssue("warning", block_path, "Autoplay video should normally be muted."))
        elif block_type == "youtube":
            url = str(block.get("url", ""))
            if not url or not ("youtube.com" in url or "youtu.be" in url):
                issues.append(ValidationIssue("error", f"{block_path}.url", "Enter a valid YouTube URL."))
            if not str(block.get("title", "")).strip():
                issues.append(ValidationIssue("warning", f"{block_path}.title", "YouTube embeds need an accessible title."))
        elif block_type == "image-text":
            _validate_image(block.get("image"), f"{block_path}.image", project_dir, issues)
        elif block_type == "process-step":
            _validate_image(block.get("image"), f"{block_path}.image", project_dir, issues)
        elif block_type == "comparison":
            for side in ("left", "right"):
                value = block.get(side)
                if isinstance(value, dict):
                    image = value.get("image")
                    if isinstance(image, dict):
                        _validate_image(image, f"{block_path}.{side}.image", project_dir, issues)
                    else:
                        _validate_local_path(project_dir, image, f"{block_path}.{side}.image", issues)
                        if image and not str(value.get("alt", "")).strip():
                            issues.append(ValidationIssue("warning", f"{block_path}.{side}.alt", "Comparison image needs alt text."))
        elif block_type == "download":
            if not block.get("label") or not block.get("file"):
                issues.append(ValidationIssue("error", block_path, "Download blocks require label and file."))
            _validate_local_path(project_dir, block.get("file"), f"{block_path}.file", issues)
        elif block_type in {"stats", "timeline", "links", "margin-notes"}:
            item_key = "notes" if block_type == "margin-notes" else "items"
            if not isinstance(block.get(item_key), list) or not block.get(item_key):
                issues.append(ValidationIssue("warning", f"{block_path}.{item_key}", f"{block_type} has no entries."))
            if block_type == "margin-notes":
                if len(block.get("notes", [])) > 3:
                    issues.append(ValidationIssue("warning", f"{block_path}.notes", "The renderer displays only the first three notes."))
                for note_index, note in enumerate(block.get("notes", [])[:3]):
                    if isinstance(note, dict):
                        _validate_local_path(project_dir, note.get("image"), f"{block_path}.notes[{note_index}].image", issues)
            elif block_type == "links":
                for link_index, link in enumerate(block.get("items", [])):
                    if not isinstance(link, dict) or not link.get("label") or not link.get("url"):
                        issues.append(ValidationIssue("error", f"{block_path}.items[{link_index}]", "Link items require label and URL."))
                    elif isinstance(link, dict):
                        _validate_local_path(project_dir, link.get("url"), f"{block_path}.items[{link_index}].url", issues)
        elif block_type == "custom-html":
            issues.append(ValidationIssue("warning", block_path, "Custom HTML is inserted directly. Only use markup you trust."))


def validate_project(data: Any, project_dir: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(data, dict):
        return [ValidationIssue("error", "project", "Project data must be one JSON object.")]
    if not str(data.get("title", "")).strip():
        issues.append(ValidationIssue("error", "title", "Project title is required."))
    if not str(data.get("description", "")).strip():
        issues.append(ValidationIssue("warning", "description", "Add a concise project summary."))
    if not str(data.get("metaDescription", "")).strip():
        issues.append(ValidationIssue("warning", "metaDescription", "Add a search-engine description."))
    tags = data.get("tags")
    if isinstance(tags, list) and len(tags) > 8:
        issues.append(ValidationIssue("warning", "tags", "The renderer displays only the first eight unique tags."))
    archive = data.get("archive", {})
    if not isinstance(archive, dict):
        issues.append(ValidationIssue("error", "archive", "Archive settings must be an object."))
    else:
        visibility = archive.get("visibility", "private")
        if visibility not in {"public", "private"}:
            issues.append(ValidationIssue("error", "archive.visibility", "Visibility must be public or private."))
        archive_date = archive.get("date")
        if archive_date:
            try:
                if not DATE_PATTERN.fullmatch(str(archive_date)):
                    raise ValueError
                date.fromisoformat(str(archive_date))
            except ValueError:
                issues.append(ValidationIssue("error", "archive.date", "Use a real date in YYYY-MM-DD format."))
        thumbnail = archive.get("thumbnail")
        if isinstance(thumbnail, dict):
            _validate_image(thumbnail, "archive.thumbnail", project_dir, issues)
        if visibility == "public" and not archive_date:
            issues.append(ValidationIssue("warning", "archive.date", "Public projects should have a publication date."))
    _validate_image(data.get("hero"), "hero", project_dir, issues)
    for index, link in enumerate(data.get("externalLinks", []) if isinstance(data.get("externalLinks"), list) else []):
        if isinstance(link, dict):
            if not link.get("label") or not link.get("url"):
                issues.append(ValidationIssue("error", f"externalLinks[{index}]", "External links require label and URL."))
            _validate_local_path(project_dir, link.get("icon"), f"externalLinks[{index}].icon", issues)
    _validate_blocks(data.get("blocks"), project_dir, issues)
    return issues


def validate_manifest(manifest: Any, projects_dir: Path) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not isinstance(manifest, dict):
        return [ValidationIssue("error", "manifest", "projects.json must contain one object.")]
    projects = manifest.get("projects")
    updates = manifest.get("updates")
    if not isinstance(projects, list):
        issues.append(ValidationIssue("error", "manifest.projects", "Projects must be an array."))
    else:
        seen: set[str] = set()
        for index, entry in enumerate(projects):
            folder = entry if isinstance(entry, str) else entry.get("folder") if isinstance(entry, dict) else ""
            folder = str(folder).strip().strip("/").removeprefix("./")
            if not folder or not SLUG_PATTERN.fullmatch(folder):
                issues.append(ValidationIssue("error", f"manifest.projects[{index}]", "Project folder must be a safe lowercase slug."))
                continue
            if folder in seen:
                issues.append(ValidationIssue("warning", f"manifest.projects[{index}]", f"Duplicate manifest entry: {folder}"))
            seen.add(folder)
            if not (projects_dir / folder / "project.json").exists():
                issues.append(ValidationIssue("error", f"manifest.projects[{index}]", f"Project folder or project.json is missing: {folder}"))
    if not isinstance(updates, list):
        issues.append(ValidationIssue("error", "manifest.updates", "Updates must be an array."))
    else:
        for index, update in enumerate(updates):
            path = f"manifest.updates[{index}]"
            if not isinstance(update, dict):
                issues.append(ValidationIssue("error", path, "Update must be an object."))
                continue
            content = update.get("content") or update.get("description") or update.get("title")
            if not str(content or "").strip():
                issues.append(ValidationIssue("warning", path, "Empty update is skipped by the archive."))
            update_date = update.get("date")
            if update_date:
                try:
                    if not DATE_PATTERN.fullmatch(str(update_date)):
                        raise ValueError
                    date.fromisoformat(str(update_date))
                except ValueError:
                    issues.append(ValidationIssue("error", f"{path}.date", "Use a real date in YYYY-MM-DD format."))
            visibility = update.get("visibility", "public")
            if visibility not in {"public", "private"}:
                issues.append(ValidationIssue("error", f"{path}.visibility", "Visibility must be public or private."))
    return issues


class PreviewServer:
    def __init__(self, repository: Path, port: int, auto_open: bool = True) -> None:
        self.repository = repository
        self.port = port
        self.auto_open = auto_open
        self.process: subprocess.Popen[bytes] | None = None

    def _port_open(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
            connection.settimeout(0.2)
            return connection.connect_ex(("127.0.0.1", self.port)) == 0

    def ensure_running(self) -> None:
        if self._port_open():
            return
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(
            [sys.executable, str(APP_DIR / "preview_server.py"), str(self.port), str(self.repository)],
            cwd=self.repository,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
        )
        for _attempt in range(20):
            if self._port_open():
                return
            if self.process.poll() is not None:
                raise OSError("The local preview server could not be started.")
            time.sleep(0.05)
        self.stop()
        raise OSError("The local preview server did not become ready in time.")

    def stop(self) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)

    def open_project(self, slug: str) -> str:
        self.ensure_running()
        url = f"http://127.0.0.1:{self.port}/projects/{slug}/?preview={time.time_ns()}"
        if self.auto_open:
            webbrowser.open(url)
        return url

    def open_archive(self) -> str:
        self.ensure_running()
        url = f"http://127.0.0.1:{self.port}/projects/?preview={time.time_ns()}"
        if self.auto_open:
            webbrowser.open(url)
        return url


class GitPublisher:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.repository: Path = config["repository"]

    def _run(self, *arguments: str, timeout: int = 90, check: bool = True) -> subprocess.CompletedProcess[str]:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        try:
            result = subprocess.run(
                ["git", *arguments],
                cwd=self.repository,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=flags,
                check=False,
            )
        except FileNotFoundError as error:
            raise ProjectManagerError("Git was not found. Install Git or add it to PATH.") from error
        except subprocess.TimeoutExpired as error:
            raise ProjectManagerError("Git timed out. Check the network and try again.") from error
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ProjectManagerError(detail or f"Git {' '.join(arguments)} failed.")
        return result

    def publish(
        self,
        slug: str,
        title: str,
        manifest_path: Path,
        project_path: Path,
        commit_message: str | None = None,
    ) -> str:
        root = Path(self._run("rev-parse", "--show-toplevel").stdout.strip()).resolve()
        if root != self.repository.resolve():
            raise ProjectManagerError("Configured repository path does not match the Git repository root.")
        branch = self._run("branch", "--show-current").stdout.strip()
        if not branch:
            raise ProjectManagerError("Git is in a detached HEAD state.")
        expected = self.config.get("gitBranch", "")
        if expected and branch != expected:
            raise ProjectManagerError(f"Repository is on '{branch}', but config expects '{expected}'.")

        relative_manifest = manifest_path.relative_to(self.repository).as_posix()
        relative_project = project_path.relative_to(self.repository).as_posix()
        self._run("add", "-A", "--", relative_project, relative_manifest)
        staged = self._run("diff", "--cached", "--quiet", "--", relative_project, relative_manifest, check=False)
        if staged.returncode == 0:
            return "No project changes needed committing."
        if staged.returncode != 1:
            raise ProjectManagerError((staged.stderr or staged.stdout).strip() or "Could not inspect staged changes.")

        message = commit_message or self.config["commitMessage"].format(title=title, slug=slug)
        self._run("commit", "-m", message, "--", relative_project, relative_manifest)
        self._run("push", self.config["gitRemote"], branch, timeout=180)
        return "Project committed and pushed ✓"
