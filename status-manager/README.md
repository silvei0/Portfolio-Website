# Portfolio Status Manager

This small Windows utility updates the temporary message displayed in the
thought bubble on the portfolio homepage. It saves `status.json`, commits only
that file, and pushes the current branch using the Git authentication already
configured on this computer. The app also requires the shared local manager
password before its interface opens.

No plaintext manager password, GitHub password, access token, or SSH private
key is stored in this project.

## Local password protection

The first launch of either portfolio manager asks you to create one shared
password of at least 10 characters. Later launches of both apps require that
password. Use **Security > Change manager password…** to replace it, or
**Security > Lock and exit** when finished.

Only a randomly salted `scrypt` verifier is stored at:

```text
%LOCALAPPDATA%\FizasPortfolioManagers\auth.json
```

The plaintext password is not stored there, in the Python source, or on
GitHub. A strong password cannot simply be read from the verifier, although a
weak password could still be guessed offline.

This is a local convenience lock, not the security boundary for the live
website. Someone able to edit the Python source or delete the verifier can
bypass/reset their local copy. They still cannot push to your repository
without a GitHub account that has write permission and valid Git credentials.
Windows sign-in security, device encryption, GitHub permissions, and GitHub
two-factor authentication remain the important protections.

## What each file does

The shared password code lives in `../manager_auth.py`; it creates and verifies
the salted local password record for both manager apps.

- `app.py` — the Tkinter desktop interface and safe Git workflow.
- `config.json` — your local settings. Git ignores this file.
- `config.example.json` — a safe example that can remain in the repository.
- `launch-status-manager.cmd` — opens the app without a terminal window.
- `install-desktop-shortcut.cmd` — creates a clickable Desktop shortcut.
- `recent-statuses.json` — created automatically and kept local by `.gitignore`.
- `../status.json` — the public status data read by the homepage.

## 1. Install dependencies

The app uses only Python's standard library, so there are no packages to
install. Install Python 3.10 or newer from <https://www.python.org/downloads/>
if it is not already installed. During installation, enable **Add Python to
PATH** and ensure **tcl/tk and IDLE** remains selected.

Git must also be installed and available from the command line:

```powershell
git --version
python --version
```

## 2. Configure the repository

Open `config.json`. The supplied settings already match this repository:

```json
{
  "repositoryPath": "..",
  "statusJsonPath": "status.json",
  "defaultStatus": "No specific thoughts right now...",
  "gitRemote": "origin",
  "gitBranch": "master",
  "commitMessage": "Update status",
  "autoPush": true,
  "characterLimit": 80,
  "recentStatusesLimit": 8
}
```

- `repositoryPath` may be relative to this folder or an absolute path.
- `statusJsonPath` must remain inside the repository.
- Set `defaultStatus` to an empty string (`""`) if the thought bubble should
  show no text after a status expires.
- Change `gitBranch` if the publishing branch is renamed.
- Set `autoPush` to `false` while testing if you do not want Git commits.

`config.json` is deliberately ignored by Git so machine-specific paths stay
local. If it is deleted, the app recreates it from `config.example.json`.

## 3. Run and test the desktop app

Double-click `launch-status-manager.cmd`. On the first launch, create the
shared manager password; later launches ask you to enter it. Then enter a
status, choose a duration, and select **Update status**. The message at the
bottom reports either:

- `Status updated and pushed ✓`, or
- `Status saved locally, but GitHub push failed. ...`

The latter means the website data is safe on the computer even if Git or the
network failed. Correct the reported problem and update again.

For a local website test, open PowerShell in the repository and run:

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

Then visit <http://127.0.0.1:8765/home/>. Do not open `home/index.html`
directly as a `file://` page because browsers restrict JSON requests from local
files.

## 4. Create the Desktop shortcut

Double-click `install-desktop-shortcut.cmd` once. It creates **Portfolio Status
Manager** on the Windows Desktop. Afterwards, open the editor using that
shortcut; the repository or code editor does not need to be open.

## 5. Test status expiry

1. Set the duration input to `1` and choose `minutes`.
2. Update the status.
3. Keep the local homepage open.
4. After one minute, the message changes to the lighter `No specific thoughts right now...` fallback automatically.

The webpage reloads `status.json` every minute and also schedules the exact
expiry time after each successful load.

## 6. Confirm the live website update

After the app reports a successful push:

```powershell
git log -1 -- status.json
git status --short
```

The newest commit should be `Update status`. Check the repository on GitHub and
wait for the existing deployment to complete. Then open the live homepage with
a hard refresh (`Ctrl+F5`). Hosting/CDN caches can take a short time to refresh.

## Secure Git authentication

The app relies on the same credentials as a normal `git push`. To configure
them securely on Windows, run one push manually from this repository:

```powershell
git push -u origin master
```

For an HTTPS remote, Git Credential Manager should open a browser sign-in and
store the resulting credential in Windows Credential Manager. For SSH, add a
key to the Windows/OpenSSH agent and change the remote to its SSH URL. Never
paste a password, token, or private key into `app.py`, `config.json`, or
`status.json`.

Git also requires an author identity for commits:

```powershell
git config --global user.name "Fiza Mansoor"
git config --global user.email "your-email@example.com"
```

Use the email associated with the GitHub account, or the GitHub-provided
`noreply` address if you prefer to keep the personal address private.
