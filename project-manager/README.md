# Portfolio Project Manager

This desktop utility creates, edits, previews, validates, and publishes the
JSON-driven project posts used by Fiza's Project Portfolio. It works with the
existing `project-renderer.js`, `projects.js`, reusable HTML shell, project
folders, and `projects/projects.json` manifest. It does not replace or rewrite
the website architecture.

The interface exposes every JSON option currently supported by the renderer.
An advanced raw-JSON editor is also included, so future or unusual fields can
still be used without waiting for the form interface to change.

## Main features

- Create a clean project or start from the complete reusable template.
- Duplicate an existing project, including all media.
- Move removed projects to recoverable local trash rather than deleting them.
- Edit basic details, archive settings, hero media, navigation wording,
  metadata, custom metadata, and external links.
- Add, edit, duplicate, reorder, nest, and remove all 22 content-block types.
- Build nested sections, two-column layouts, and three-column layouts visually.
- Manage galleries, statistics, timelines, links, notes, and archive updates
  through repeatable row editors.
- Select existing repository files or copy external media into the appropriate
  `images/`, `videos/`, or `files/` folder.
- See every file stored with a project and copy its relative path.
- Edit and import raw JSON, or export a standalone JSON copy.
- Validate dates, block types, nesting, local paths, alt text, media, columns,
  YouTube links, captions, public archive settings, and other common mistakes.
- Save timestamped automatic JSON backups.
- Preview the project or archive through a local HTTP server.
- Commit and push only the current project folder and archive manifest.
- Require the shared local manager password before the interface opens.
- Create a one-click Windows Desktop shortcut.

No plaintext manager password, GitHub password, token, or SSH private key is
stored in this project.

## Local password protection

The first launch of either portfolio manager asks you to create one shared
password of at least 10 characters. Both apps then require it at startup. Use
**Security > Change manager password…** from either manager to change it for
both, or **Security > Lock and exit** when finished.

The plaintext password is never saved. A randomly salted `scrypt` verifier is
stored outside the repository at:

```text
%LOCALAPPDATA%\FizasPortfolioManagers\auth.json
```

Someone cannot read a strong password directly from that file or from the
source code, although weak passwords may be guessed. Because this is a local
Python application, someone who can edit the source or delete the verifier can
bypass/reset the lock on their own copy. That does not grant permission to
push to Fiza's repository: GitHub write access and authenticated Git
credentials are still required. Protect the Windows account and use GitHub
two-factor authentication.

## Files

The shared password code lives in `../manager_auth.py`; it supplies the login
and password-change dialogs used by both managers.

- `app.py` — Tkinter interface and project workflow.
- `schemas.py` — editable definitions for all fields and block types.
- `services.py` — file handling, backups, validation, preview, and Git.
- `config.json` — local machine settings; ignored by Git.
- `config.example.json` — safe configuration example for the repository.
- `launch-project-manager.cmd` — opens the application without a console.
- `install-desktop-shortcut.cmd` — creates a Desktop shortcut.
- `.backups/` — automatic local JSON backups; ignored by Git.
- `.trash/` — recoverable projects removed through the app; ignored by Git.

## 1. Requirements

The manager uses only the Python standard library. No `pip install` command is
needed.

Install:

- Python 3.10 or newer, including **tcl/tk and IDLE**
- Git for Windows

During Python installation, enable **Add Python to PATH**. You can check both
programs in PowerShell:

```powershell
python --version
git --version
```

## 2. Launch the app

Double-click:

```text
project-manager\launch-project-manager.cmd
```

On the first launch, create the shared password. On later launches, enter it to
unlock the manager. The existing `project-1` folder then appears in the project
library; select it to open its data.

## 3. Create a Desktop shortcut

Double-click this once:

```text
project-manager\install-desktop-shortcut.cmd
```

Windows creates **Portfolio Project Manager** on the Desktop using the site
icon. The portfolio folder and code editor do not need to be open when using
the shortcut.

## 4. Configuration

The included local `config.json` already matches this repository:

```json
{
  "repositoryPath": "..",
  "projectsDirectory": "projects",
  "manifestPath": "projects/projects.json",
  "templateDirectory": "projects/project-template",
  "gitRemote": "origin",
  "gitBranch": "master",
  "commitMessage": "Update project: {title}",
  "previewPort": 8767,
  "autoOpenPreview": true,
  "backupCount": 10
}
```

`config.json` is ignored by Git because repository locations can differ between
computers. If it is missing, the app copies `config.example.json` automatically.

- Use `{title}` and `{slug}` inside `commitMessage` if desired.
- Change `gitBranch` if the publishing branch is renamed.
- Change `previewPort` if another program already uses port 8767.
- Set `autoOpenPreview` to `false` if Preview should start the server and copy
  the URL to the status bar without opening the default browser.
- `backupCount` controls how many previous JSON copies are retained per project.

## 5. Normal publishing workflow

1. Choose a project from the left-hand library or press **New**.
2. Complete the tabs from left to right.
3. Build the page in **Content blocks**.
4. Add media using **Browse…** or the **Media & files** tab.
5. Keep archive visibility `private` while the page is unfinished.
6. Press **Validate** and correct all errors.
7. Press **Preview** and inspect the page in the browser.
8. Change visibility to `public` when ready.
9. Press **Commit & push**.

Publishing stages only:

- `projects/<current-slug>/`
- `projects/projects.json`

Other unrelated working-tree changes are not included in the project commit.

## 6. Project and archive tabs

### Basics

Controls the project title, subtitle, summary, search description, tags,
discipline, status, timeline, project type, role, and tools. Use one line per
tag or tool. The website displays a maximum of eight unique tags.

### Archive

Controls:

- `private` or `public` archive visibility
- featured-project placement
- currently-working placement
- publication date and archive-card summary
- archive thumbnail, placeholder, alt text, caption, loading, and dimensions

`private` means unlisted, not password-protected. Do not push genuinely private
material to a public GitHub Pages repository.

### Hero

Supports a real image or intentional placeholder, alternative text, caption,
placeholder guidance, decorative-image mode, eager/lazy loading, and intrinsic
dimensions.

### Navigation

Allows every project-specific pagination URL, label, link caption, and back-link
wording to be changed. The supplied defaults match the current project folders.

### Metadata & links

- **Custom metadata** creates label/value details without fixed ordering.
- **Ordered metadata** preserves the exact order of label/value rows.
- **Hero links** support label, hint, URL, icon, primary style, and new-tab mode.

## 7. Every supported content block

The Content blocks tab represents nesting as a tree. Double-click a block to
edit it. Select a section or column before using **Add child**.

| Block | Supported options |
| --- | --- |
| Section | ID, title, contents label, hide-from-contents, intro, guide, nested blocks |
| Text | Heading, one or many paragraphs, list items, numbered mode, tick style |
| Heading | Text and levels 2–6 |
| Image | File/placeholder, alt, caption, size, alignment, style, offset, rotation, loading, dimensions, decorative mode |
| Local video | File, poster, caption, size, controls, autoplay, loop, mute, preload, WebVTT captions and language settings |
| YouTube | URL, accessible title, caption, size |
| Gallery | One-to-four columns and repeatable image records |
| Two-column | Ratios 1-1, 2-1, or 1-2 plus blocks in each column |
| Three-column | Blocks in each of three columns |
| Image and text | Left/right image, full image options, heading, paragraphs |
| Process step | Optional number, title, explanation, evidence prompt, full image options |
| Callout | Standard, problem, subtle, or conclusion style; title and paragraphs |
| Quote | Quotation and source |
| Statistics | Repeatable value/label items |
| Timeline | Repeatable date/title/content milestones |
| Comparison | Left and right labels, titles, explanations, and full image options |
| Links | Repeatable label/URL/new-tab buttons |
| Download | Label, local file, downloaded filename, download/open behavior |
| Divider | Horizontal divider |
| Spacer | Small, medium, or large pause |
| Custom HTML | Trusted raw HTML escape hatch |
| Margin notes | Accessible label and up to three text/image notes |

Every block also supports an optional block ID, safe CSS class names, contents
label, and hide-from-contents setting.

## 8. Reordering and nesting blocks

- **Add sibling** inserts after the selected block.
- **Add child** adds inside a selected section or selected column.
- **Duplicate** copies the complete block, including nested content.
- **Move up/down** changes order within the current parent.
- **Delete** removes the block and all children after confirmation.

Two- and three-column blocks display separate **Column 1**, **Column 2**, and
**Column 3** container rows. Select the intended column before adding its child.

## 9. Media and file paths

When **Browse…** selects a file:

- files already inside the project use their project-relative path;
- shared files already inside the repository use a safe relative path;
- external files can be copied into the current project's suggested folder.

Suggested folders:

- photographs and diagrams → `images/`
- MP4/WebM and WebVTT captions → `videos/`
- PDFs, spreadsheets, drawings, and reports → `files/`

The app avoids Windows backslashes in JSON paths. Validation reports missing
files and warns about root-relative paths that can break on GitHub Pages.

## 10. Archive updates

The Archive updates tab edits the shared `updates` array in
`projects/projects.json`. Each update supports date, text, and public/private
visibility. Entries can be duplicated, reordered, or removed.

The **Included in archive manifest** checkbox controls whether the current
folder appears in the manifest. A project must be in the manifest and have
`archive.visibility` set to `public` before archive cards are generated.

## 11. Raw JSON and future fields

Press **Refresh JSON from forms** to see exactly what the forms and block tree
will save. Advanced users can edit this text and press **Apply edited JSON**.

The raw editor is useful for:

- importing existing project JSON;
- fields added to the renderer in the future;
- object or array values that are more complex than the standard form;
- making a precise bulk edit.

The app never silently applies raw text. It validates JSON syntax and asks for
confirmation first. Unknown keys are preserved by the normal forms.

## 12. Validation

Errors prevent Git publishing. Warnings can be accepted after review.

Checks include:

- required title and block array
- valid archive visibility and real `YYYY-MM-DD` date
- all 22 recognised block types
- correct section and column nesting
- required video, gallery, download, and link data
- valid YouTube links and accessible embed titles
- missing local images, videos, captions, icons, posters, and downloads
- Windows backslashes and risky root-relative paths
- missing alternative text for informative images
- rotations outside the renderer's supported range
- autoplay video without mute
- more items than a renderer displays
- trusted-HTML safety warning

## 13. Previewing

Preview saves the current project first, starts a hidden local HTTP server on
port 8767, and opens:

```text
http://127.0.0.1:8767/projects/<slug>/
```

Use **Preview archive** to open `/projects/`. Opening project HTML directly as
`file://` will not work reliably because browsers restrict JSON `fetch` calls.

## 14. Backups and recoverable removal

Every normal save stores the previous `project.json` under:

```text
project-manager/.backups/<slug>/
```

Only the newest configured number of backups is retained. These files stay
local and are ignored by Git.

**Remove** moves the complete project folder to:

```text
project-manager/.trash/
```

and removes its manifest entry. Nothing is permanently deleted. The app then
asks whether to commit and push that removal. Restore a project by moving its
folder back under `projects/` and reselecting archive membership.

## 15. Secure Git setup

The app uses the existing Git authentication. Configure the commit identity if
needed:

```powershell
git config --global user.name "Fiza Mansoor"
git config --global user.email "your-email@example.com"
```

Use a GitHub `noreply` address if you prefer. For the existing HTTPS remote, run
one manual push and complete Git Credential Manager's browser sign-in:

```powershell
git push -u origin master
```

For SSH, configure the Windows/OpenSSH agent and change the repository remote
to its SSH URL. Never paste a password, personal access token, or private key
into Python, JSON, or the repository.

## 16. Confirming deployment

After **Commit & push** reports success:

```powershell
git log -1 -- projects
git status --short
```

Check GitHub for the new commit and wait for the existing Pages deployment.
Open the live project folder URL with a trailing slash and use `Ctrl+F5` if a
cached version remains visible.
