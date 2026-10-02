# INSTALL.md: instructions for Claude

You are setting up the user's Claude Code from this repo. Follow these steps in order. The
installer does the work; your job is to check prerequisites, show the plan, ask the user, and
report honestly.

## Ground rules

- Do not change anything until the user says yes to the dry-run plan (step 5).
- Do **not** edit `settings.json`, `.claude.json` or `CLAUDE.md` by hand. Only `install.py` does that.
- Never ask the user to paste a key, token or password into the chat, and never print one. Anything
  that needs a secret is a manual step the user does themselves (step 8).
- Do not use `--on-conflict overwrite` unless the user asks for it after seeing what would be replaced.
- Do not delete or move anything outside the temp clone.
- If a step fails, say what failed and show the installer's own message. Do not retry blindly.

## 1. Check prerequisites

Run each and note what is missing:

```powershell
claude --version
git --version
node --version
python --version      # if this opens the Microsoft Store or fails, try: py -3 --version
pwsh --version        # optional; the status line falls back to Windows PowerShell
```

If something required is missing (git, node, python), tell the user and offer to install it, and
only run the command after they agree:

```powershell
winget install -e --id Git.Git --accept-source-agreements --accept-package-agreements
winget install -e --id OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
```

Open a new terminal afterwards if the command is still not found. If `python` is only reachable
as `py -3`, use `py -3` in place of `python` below.

## 2. Clone to a temp folder

```powershell
$dir = "$env:TEMP\claude-code-setup"
if (Test-Path $dir) { git -C $dir pull --ff-only } else { git clone --depth 1 https://github.com/TheDyXer/claude-code-setup $dir }
cd $dir
```

(If the folder is already there from an earlier run, this updates it instead of failing.)

## 3. Ask which extras they want

```powershell
python install.py --list-extras
```

The core set (24 skills, 2 rules, 3 plugins, 3 MCP servers, a few preferences) is always
installed. Ask the user which extras they want, using AskUserQuestion with multi-select if you
have it, and explain each in one plain sentence from the list. Point out:

- `claude-mem` records their session activity in a local database.
- `fast-jev` and `github-mcp` need a sign-in or key that **they** set up afterwards.
- `model-prefs` and `advisor` assume their plan offers those models.

"All of them" is a fine answer: use `--with all`.

## 4. Dry run

```powershell
python install.py --with claude-mem,statusline        # their chosen extras, or: --with all
```

It changes nothing and prints each action: `+ add` (new), `= ok` (already there), `~ kept`
(they have something different; yours is kept), `! FAILED`. Show the user a short summary:
how many items to add, anything marked `kept`, and anything `FAILED`.

## 5. Get the go-ahead

Ask plainly: "Apply this now?" Only continue on a clear yes.

## 6. Apply

Run the same command with `--apply`:

```powershell
python install.py --with claude-mem,statusline --apply
```

This takes a few minutes: some plugin repos are several hundred MB. If a marketplace or plugin
shows `FAILED`, read its message. A "Filename too long" error means:
`git config --global core.longpaths true`, then run the same command again (it is safe to repeat).

## 7. Verify

```powershell
claude plugin list
claude mcp list
python install.py --with claude-mem,statusline          # should now say "0 to add"
```

Check that the plugins and MCP servers the user chose appear, and that the dry run reports
nothing left to add.

Two statuses in `claude mcp list` are **expected right after install** and are not errors to fix:
`github` shows *Failed to connect* until the user has set their GitHub token (see step 8), and the
Cloudflare plugin's server shows *Needs authentication* until the user signs in. Do not try to
repair either; just list them under the manual steps.

## 8. Report and hand over the manual steps

Tell the user what was added, what was kept as theirs, and the backup folder the installer
printed. Then repeat the **Manual steps for you** list from the installer output: setting a GitHub
token, a TypeSafe key, signing in to Cloudflare, `npx ctx7@latest login`, connecting claude.ai connectors. These are
theirs to do. Finish by telling them to **restart Claude Code**.

## 9. Clean up

Offer to delete the temp clone: `Remove-Item -Recurse -Force "$env:TEMP\claude-code-setup"`.
