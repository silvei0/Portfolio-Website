"""Lightweight standard-library checks for the project manager."""

from __future__ import annotations

import socket
import tempfile
import subprocess
import sys
from pathlib import Path
from urllib.request import urlopen

REPOSITORY_DIR = Path(__file__).resolve().parent.parent
if str(REPOSITORY_DIR) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_DIR))

from manager_auth import PasswordStore, validate_new_password
from schemas import BLOCK_SCHEMAS, TOP_LEVEL_TABS
from services import GitPublisher, PreviewServer, ProjectRepository, atomic_write_json, validate_manifest, validate_project


def all_block_project(project_dir: Path) -> dict:
    (project_dir / "images").mkdir(parents=True)
    (project_dir / "videos").mkdir()
    (project_dir / "files").mkdir()
    for relative in ("images/demo.jpg", "videos/demo.mp4", "videos/demo.vtt", "files/report.pdf"):
        (project_dir / relative).write_bytes(b"test")

    return {
        "siteName": "Fiza's Project Portfolio",
        "title": "All blocks test",
        "description": "Validation fixture for every renderer block.",
        "metaDescription": "A complete project-manager validation fixture.",
        "archive": {"visibility": "private", "date": "2026-08-09"},
        "hero": {"placeholder": "Hero", "alt": "Hero placeholder"},
        "blocks": [
            {"type": "section", "id": "overview", "title": "Overview", "blocks": [{"type": "text", "content": "Nested text"}]},
            {"type": "heading", "text": "Heading", "level": 3},
            {"type": "image", "placeholder": "Image", "alt": "Image placeholder"},
            {
                "type": "video",
                "src": "videos/demo.mp4",
                "poster": "images/demo.jpg",
                "muted": True,
                "captions": {"src": "videos/demo.vtt", "srclang": "en", "label": "English"},
            },
            {"type": "youtube", "url": "https://www.youtube.com/watch?v=abcdefghi", "title": "Video walkthrough"},
            {"type": "gallery", "columns": 2, "images": [{"placeholder": "Gallery image", "alt": "Gallery placeholder"}]},
            {
                "type": "two-column",
                "ratio": "2-1",
                "columns": [{"blocks": [{"type": "text", "content": "Left"}]}, {"blocks": [{"type": "text", "content": "Right"}]}],
            },
            {
                "type": "three-column",
                "columns": [
                    {"blocks": [{"type": "text", "content": "One"}]},
                    {"blocks": [{"type": "text", "content": "Two"}]},
                    {"blocks": [{"type": "text", "content": "Three"}]},
                ],
            },
            {"type": "image-text", "title": "Image text", "content": "Copy", "image": {"placeholder": "Image", "alt": "Placeholder"}},
            {"type": "process-step", "title": "Research", "content": "Process", "image": {"placeholder": "Evidence", "alt": "Evidence placeholder"}},
            {"type": "callout", "variant": "problem", "title": "Problem", "content": "Explanation"},
            {"type": "quote", "content": "Useful quotation", "source": "Reviewer"},
            {"type": "stats", "items": [{"value": "35%", "label": "reduction"}]},
            {"type": "timeline", "items": [{"date": "Week 1", "title": "Research", "content": "Mapped the site"}]},
            {
                "type": "comparison",
                "left": {"label": "Before", "image": {"placeholder": "Before", "alt": "Before placeholder"}},
                "right": {"label": "After", "image": {"placeholder": "After", "alt": "After placeholder"}},
            },
            {"type": "links", "items": [{"label": "Project link", "url": "https://example.com/", "newTab": True}]},
            {"type": "download", "label": "Download report", "file": "files/report.pdf", "download": True},
            {"type": "divider"},
            {"type": "spacer", "size": "medium"},
            {"type": "custom-html", "html": "<p>Trusted fixture markup.</p>"},
            {"type": "margin-notes", "notes": [{"text": "Remember the evidence."}]},
        ],
    }


def test_schema_and_validation() -> None:
    assert len(BLOCK_SCHEMAS) == 22
    hero_paths = [field["path"] for field in TOP_LEVEL_TABS["Hero"]]
    assert "externalLinks" in hero_paths
    assert sum(
        field["path"] == "externalLinks"
        for fields in TOP_LEVEL_TABS.values()
        for field in fields
    ) == 1
    with tempfile.TemporaryDirectory() as temporary:
        project_dir = Path(temporary) / "project"
        project = all_block_project(project_dir)
        issues = validate_project(project, project_dir)
        errors = [issue for issue in issues if issue.level == "error"]
        assert not errors, "\n".join(issue.display() for issue in errors)
        assert any("Custom HTML" in issue.message for issue in issues)


def test_repository_workflow() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / ".git").mkdir()
        template = root / "projects" / "project-template"
        template.mkdir(parents=True)
        (template / "index.html").write_text("<!doctype html><title>Project</title>", encoding="utf-8")
        atomic_write_json(template / "project.json", {"title": "Template", "archive": {"visibility": "private"}, "blocks": []})
        atomic_write_json(root / "projects" / "projects.json", {"projects": [], "updates": []})
        config = {
            "repository": root,
            "projectsDirectoryPath": root / "projects",
            "manifestFile": root / "projects" / "projects.json",
            "templateDirectoryPath": template,
            "backupCount": 3,
        }
        repository = ProjectRepository(config)
        repository.backup_dir = root / ".backups"
        repository.trash_dir = root / ".trash"

        created = repository.create_project("rain-garden", "Rain Garden", use_template=False)
        assert created["title"] == "Rain Garden"
        assert repository.is_in_manifest("rain-garden")
        assert (root / "projects" / "rain-garden" / "images").is_dir()

        duplicated = repository.duplicate_project("rain-garden", "rain-garden-two", "Rain Garden Two")
        assert duplicated["title"] == "Rain Garden Two"
        manifest = repository.load_manifest()
        repository.save_project("rain-garden-two", duplicated, manifest, included=False)
        assert not repository.is_in_manifest("rain-garden-two")

        manifest_issues = validate_manifest(repository.load_manifest(), root / "projects")
        assert not [issue for issue in manifest_issues if issue.level == "error"]

        trash = repository.move_project_to_trash("rain-garden-two")
        assert trash.exists()
        assert not (root / "projects" / "rain-garden-two").exists()


def test_scoped_git_publish() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        root = base / "portfolio"
        remote = base / "remote.git"
        root.mkdir()

        def git(*arguments: str, cwd: Path = root) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                ["git", *arguments],
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

        git("init", "--initial-branch=master")
        git("config", "user.name", "Project Manager Test")
        git("config", "user.email", "project-manager-test@example.invalid")
        (root / "projects" / "demo").mkdir(parents=True)
        atomic_write_json(root / "projects" / "demo" / "project.json", {"title": "Demo", "blocks": []})
        atomic_write_json(root / "projects" / "projects.json", {"projects": ["demo"], "updates": []})
        (root / "unrelated.txt").write_text("initial", encoding="utf-8")
        git("add", ".")
        git("commit", "-m", "Initial")
        git("init", "--bare", str(remote), cwd=base)
        git("remote", "add", "origin", str(remote))

        atomic_write_json(root / "projects" / "demo" / "project.json", {"title": "Demo updated", "blocks": []})
        (root / "unrelated.txt").write_text("user change", encoding="utf-8")
        publisher = GitPublisher(
            {
                "repository": root,
                "gitBranch": "master",
                "gitRemote": "origin",
                "commitMessage": "Update project: {title}",
            }
        )
        result = publisher.publish(
            "demo",
            "Demo updated",
            root / "projects" / "projects.json",
            root / "projects" / "demo",
        )
        assert "pushed" in result
        status = git("status", "--short").stdout.strip().replace("\\", "/")
        assert status == "M unrelated.txt", status
        assert git("--git-dir", str(remote), "rev-parse", "refs/heads/master", cwd=base).stdout.strip()


def test_local_password_store() -> None:
    assert validate_new_password("short") is not None
    first_password = "A memorable first passphrase"
    second_password = "A different secure passphrase"

    with tempfile.TemporaryDirectory() as temporary:
        auth_path = Path(temporary) / "auth.json"
        store = PasswordStore(auth_path)
        assert not store.exists()

        store.set_password(first_password)
        assert store.exists()
        assert store.verify(first_password)
        assert not store.verify("Definitely the wrong password")
        assert first_password not in auth_path.read_text(encoding="utf-8")

        reloaded = PasswordStore(auth_path)
        assert reloaded.verify(first_password)
        reloaded.set_password(second_password)
        assert reloaded.verify(second_password)
        assert not reloaded.verify(first_password)
        assert second_password not in auth_path.read_text(encoding="utf-8")


def test_preview_server_disables_caching() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        project_dir = root / "projects" / "demo"
        project_dir.mkdir(parents=True)
        (project_dir / "index.html").write_text("<!doctype html><title>Preview</title>", encoding="utf-8")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as available_port:
            available_port.bind(("127.0.0.1", 0))
            port = available_port.getsockname()[1]

        preview = PreviewServer(root, port, auto_open=False)
        try:
            first_url = preview.open_project("demo")
            second_url = preview.open_project("demo")
            assert first_url != second_url
            assert "?preview=" in first_url
            with urlopen(second_url, timeout=3) as response:
                assert response.status == 200
                assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, max-age=0"
        finally:
            preview.stop()


def main() -> None:
    test_schema_and_validation()
    test_repository_workflow()
    test_scoped_git_publish()
    test_local_password_store()
    test_preview_server_disables_caching()
    print(
        "Project Manager tests passed: password hashing, schemas, all blocks, validation, "
        "repository workflow, no-cache preview, scoped commit, and local push."
    )


if __name__ == "__main__":
    main()
