# claude-code-setup

Copy one prompt into [Claude Code](https://claude.com/claude-code) and it sets itself up with a
ready-made collection of plugins, skills, MCP servers and preferences. Windows.

## The prompt

Paste this into Claude Code:

```text
Set up my Claude Code from https://github.com/TheDyXer/claude-code-setup. Clone it to a temp folder, read INSTALL.md and follow it exactly: check what I have installed, ask me whether to keep Claude Code's default compaction (recommended) or install fast-jev-compaction, ask me which other optional extras I want, run the installer as a dry run first and show me the plan, and only apply it after I say yes.
```

That's all. Claude first asks whether you want to keep Claude Code's default compaction
(recommended) or install fast-jev-compaction, then asks about the other optional parts, and shows
you what it is about to change before it changes anything.

## What you get

**Always included**

- 24 skills for design, UI polish, animation, API design, security review, planning and more
  (see `config/skills/`)
- 2 rules files: how to look up current library docs, and how the design skills divide up the work
- Plugins: [superpowers](https://github.com/anthropics/claude-plugins-official),
  [impeccable](https://github.com/pbakaus/impeccable), [cloudflare](https://github.com/cloudflare/skills)
- MCP servers: Playwright, Chrome DevTools, Context7 (public)
- A few safe preferences (theme, auto-update channel, questions that wait for your answer instead of
  auto-continuing, impeccable's telemetry off)

**Optional extras** (Claude asks which you want; `python install.py --list-extras` lists them)

| Extra | What it is |
|---|---|
| `claude-mem` | Memory across sessions. Runs a local background worker and keeps its database on your machine. |
| `fast-jev` | Replaces Claude Code's built-in compaction. Asked about separately and never part of "all"; the default compaction is recommended. Needs your own TypeSafe API key. |
| `unity` | Unity's agent plugin (beta). Only useful for Unity projects. |
| `github-mcp` | GitHub's hosted MCP server. You create a GitHub token and set it as an environment variable yourself. |
| `statusline` | A pace-aware status line, from [claude-statusline](https://github.com/TheDyXer/claude-statusline). |
| `model-prefs` | Sonnet as the default model with high effort. Check your plan offers it. |
| `advisor` | An advisor model setting and a rule in your `CLAUDE.md` to consult it. Needs a plan that has the advisor. |

## Is it safe to paste?

The prompt makes your Claude download this repo and run `install.py`, so read before you trust:

- **Nothing changes until you say yes.** The installer is a dry run by default. You see the plan
  first and Claude waits for your OK before running it with `--apply`.
- **It never overwrites your stuff.** Settings you already have win. Rules and skills you already
  have are kept. Your own `CLAUDE.md` text is never touched; its one block sits between marker comments.
- **Everything it edits is backed up** to `<config folder>/backups/claude-code-setup-<time>/`.
- **No secrets, ever.** It doesn't ask for, read or store a key or password. The few things that
  need a key (Context7, TypeSafe, GitHub) are steps you do yourself.
- **Small and readable.** `install.py` is one file of standard-library Python (about 400 lines).
  The status line it downloads is pinned to an exact commit and checked against a SHA-256.

## What you need first

Claude Code, Git, Node.js (the Playwright and Chrome DevTools servers run through `npx`) and
Python 3.8+ (the installer, and the `ui-ux-pro-max` skill's scripts). Claude checks for these
and offers to install what's missing with `winget`.

## After it runs

Claude prints the steps only you can do, such as setting a GitHub token, setting a TypeSafe key, signing in to Cloudflare, or
connecting Gmail and Drive in your claude.ai account (those belong to your account, not to files).
Then restart Claude Code.

Running the prompt again is safe: it reports "0 to add" when everything is in place.

## Undo

Copy the files back from the backup folder the installer printed. Remove plugins with
`claude plugin uninstall <name>` and MCP servers with `claude mcp remove <name>`.

## For the owner of this repo

`export.py` rebuilds `config/` from a live setup using only what `manifest.json` allows, then
scans the whole repo for secrets and personal data. `python -m unittest discover -s tests` runs
the installer tests in throwaway folders.

Third-party skills and their terms are listed in [NOTICE.md](NOTICE.md).
