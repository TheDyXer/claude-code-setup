#!/usr/bin/env python3
"""claude-code-setup installer.

Dry run by default: nothing on your machine changes unless you pass --apply.
Python 3.8+, standard library only. It never asks for, reads or stores a secret.

  python install.py                         show what would happen (core only)
  python install.py --list-extras           list the optional extras
  python install.py --with all              plan with every extra
  python install.py --with all --apply      do it

What it does, in order: back up what it will touch, add the CLAUDE.md block (extra `advisor`),
copy rules and skills, install plugins and MCP servers through the `claude` command, then
merge preferences into settings.json. Existing values of yours are never replaced.
"""
import argparse
import copy
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BEGIN = "<!-- claude-code-setup:begin -->"
END = "<!-- claude-code-setup:end -->"


class Refuse(Exception):
    """Stop before changing anything."""


def is_link(p):
    return p.is_symlink() or getattr(os.path, "isjunction", lambda _: False)(str(p))


def read_json(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError) as e:
        raise Refuse(f"{path} is not valid JSON ({e}). Nothing was changed. Fix or move that file, then run again.")
    if not isinstance(data, dict):
        raise Refuse(f"{path} does not hold a JSON object. Nothing was changed.")
    return data


def merge_add_only(dst, src, path=()):
    """Add keys of src that dst lacks. Never replace a value of dst. Returns [(status, 'a/b')]."""
    out = []
    for k, v in src.items():
        here = path + (k,)
        label = "/".join(here)
        if k not in dst:
            dst[k] = copy.deepcopy(v)
            out.append(("added", label))
        elif isinstance(dst[k], dict) and isinstance(v, dict):
            out.extend(merge_add_only(dst[k], v, here))
        elif dst[k] == v:
            out.append(("same", label))
        else:
            out.append(("kept", label))
    return out


def tree_bytes(src, token=None, replacement=None):
    """{relative path: bytes} for a file or folder, with the home token filled in."""
    def fix(b):
        return b.replace(token.encode(), replacement.encode()) if token and token.encode() in b else b
    if src.is_file():
        return {"": fix(src.read_bytes())}
    out = {}
    for p in sorted(src.rglob("*")):
        if p.is_file():
            out[p.relative_to(src).as_posix()] = fix(p.read_bytes())
    return out


class Installer:
    def __init__(self, args, manifest):
        self.apply = args.apply
        self.policy = args.on_conflict
        self.skip_cli = args.skip_cli
        self.statusline_source = args.statusline_source
        self.manifest = manifest
        self.token = manifest["token"]
        default = Path.home() / ".claude"
        chosen = args.config_dir or os.environ.get("CLAUDE_CONFIG_DIR")
        self.cfg = Path(chosen).expanduser() if chosen else default
        self.env = os.environ.copy()
        if self.cfg.resolve() != default.resolve():
            self.env["CLAUDE_CONFIG_DIR"] = str(self.cfg)
            self.claude_json = self.cfg / ".claude.json"
        else:
            self.claude_json = Path.home() / ".claude.json"
        self.extras = args.extras
        self.groups = [manifest["core"]] + [manifest["extras"][e] for e in self.extras]
        self.claude = None if self.skip_cli else shutil.which("claude")
        self.stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.backup_dir = self.cfg / "backups" / f"claude-code-setup-{self.stamp}"
        self.backed_up = set()
        self.counts = {"added": 0, "same": 0, "kept": 0, "failed": 0}
        self.manual = []
        self.extra_settings = {}

    # ---- output -------------------------------------------------------------------------
    def say(self, kind, msg):
        tag = {"added": "+", "same": "=", "kept": "~", "failed": "!", "info": " "}[kind]
        if kind in self.counts:
            self.counts[kind] += 1
        verb = {"added": "add" if not self.apply else "added", "same": "ok", "kept": "kept", "failed": "FAILED", "info": ""}[kind]
        print(f"  {tag} {verb:<6} {msg}".rstrip())

    def backup(self, path):
        if not self.apply or not path.exists() or str(path) in self.backed_up:
            return
        self.backed_up.add(str(path))
        try:
            dest = self.backup_dir / path.relative_to(self.cfg)
        except ValueError:
            dest = self.backup_dir / path.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            shutil.copytree(path, dest, symlinks=False)
        else:
            shutil.copy2(path, dest)

    @staticmethod
    def write_atomic(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp-claude-code-setup")
        tmp.write_bytes(data)
        os.replace(tmp, path)

    # ---- CLAUDE.md ----------------------------------------------------------------------
    def step_claude_md(self):
        if "advisor" not in self.extras:
            return
        print("CLAUDE.md")
        block = (ROOT / self.manifest["extras"]["advisor"]["claude_md"]).read_text(encoding="utf-8").strip()
        new_block = f"{BEGIN}\n{block}\n{END}"
        path = self.cfg / "CLAUDE.md"
        raw = path.read_bytes().decode("utf-8") if path.exists() else ""
        nl = "\r\n" if "\r\n" in raw else "\n"
        text = raw.replace("\r\n", "\n")
        if BEGIN in text and END in text and text.index(BEGIN) < text.index(END):
            s, e = text.index(BEGIN), text.index(END) + len(END)
            new = text[:s] + new_block + text[e:]
        elif text.strip():
            new = text.rstrip("\n") + "\n\n" + new_block + "\n"
        else:
            new = new_block + "\n"
        if new == text:
            self.say("same", "CLAUDE.md block already present")
            return
        self.say("added", "CLAUDE.md: advisor rule (between claude-code-setup markers; your own text is untouched)")
        if self.apply:
            self.backup(path)
            self.write_atomic(path, new.replace("\n", nl).encode("utf-8"))

    # ---- rules and skills ---------------------------------------------------------------
    def place(self, src, dest, label):
        home = self.cfg.as_posix()
        want = tree_bytes(src, self.token, home)
        if is_link(dest):
            self.say("kept", f"{label}: {dest.name} is a link on your machine, left alone")
            return False
        if not dest.exists():
            self.say("added", label)
            if self.apply:
                for rel, data in want.items():
                    target = dest / rel if rel else dest
                    self.write_atomic(target, data)
            return True
        have = tree_bytes(dest)
        if have == {k: v for k, v in want.items()}:
            self.say("same", label)
            return True
        if self.policy == "overwrite":
            self.say("added", f"{label}: replaced yours (old copy kept in the backup folder)")
            if self.apply:
                self.backup(dest)
                if dest.is_dir():
                    shutil.rmtree(dest)
                else:
                    dest.unlink()
                for rel, data in want.items():
                    self.write_atomic(dest / rel if rel else dest, data)
            return True
        self.say("kept", f"{label}: you already have a different version, kept yours (--on-conflict overwrite replaces it)")
        return False

    def step_files(self):
        core = self.manifest["core"]
        print("Rules")
        for name in core["rules"]:
            self.place(ROOT / "config" / "rules" / name, self.cfg / "rules" / name, f"rules/{name}")
        print("Skills")
        for name in core["skills"]:
            self.place(ROOT / "config" / "skills" / name, self.cfg / "skills" / name, f"skills/{name}")

    # ---- status line --------------------------------------------------------------------
    def step_statusline(self):
        if "statusline" not in self.extras:
            return
        print("Status line")
        if platform.system() != "Windows":
            self.say("kept", "status line is Windows-only, skipped")
            return
        spec = self.manifest["extras"]["statusline"]["source"]
        if self.statusline_source:
            data = Path(self.statusline_source).read_bytes()
        else:
            url = f"https://raw.githubusercontent.com/{spec['repo']}/{spec['commit']}/{spec['file']}"
            try:
                with urllib.request.urlopen(url, timeout=30) as r:
                    data = r.read()
            except Exception as e:
                self.say("failed", f"could not download {spec['file']} ({e.__class__.__name__})")
                return
            if hashlib.sha256(data).hexdigest() != spec["sha256"]:
                self.say("failed", "downloaded status line does not match the pinned checksum; not installing it")
                return
        pwsh = shutil.which("pwsh")
        ps5 = shutil.which("powershell")
        dest = self.cfg / "statusline.ps1"
        path = dest.as_posix()
        path = f'"{path}"' if " " in path else path
        if pwsh:
            cmd = f"pwsh -NoProfile -ExecutionPolicy Bypass -File {path}"
        elif ps5:
            cmd = f"powershell -NoProfile -ExecutionPolicy Bypass -File {path}"
        else:
            self.say("kept", "no PowerShell found, status line skipped")
            return
        if dest.exists() and dest.read_bytes() != data and self.policy != "overwrite":
            self.say("kept", "statusline.ps1: you already have a different one, kept yours")
            return
        if not dest.exists() or dest.read_bytes() != data:
            self.say("added", f"statusline.ps1 (checksum-verified from {spec['repo']} @ {spec['commit'][:7]})")
            if self.apply:
                self.backup(dest)
                self.write_atomic(dest, data)
        else:
            self.say("same", "statusline.ps1")
        self.extra_settings["statusLine"] = {"type": "command", "command": cmd, "refreshInterval": 30}

    # ---- plugins and MCP (through the claude command) -----------------------------------
    def claude_run(self, args):
        return subprocess.run([self.claude] + args, env=self.env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=900, stdin=subprocess.DEVNULL)

    def cli_json(self, args):
        try:
            p = self.claude_run(args)
            if p.returncode == 0:
                return json.loads(p.stdout)
        except Exception:
            pass
        return None

    def cli_do(self, args, label):
        shown = "claude " + " ".join(args)
        if not self.apply:
            self.say("added", f"{label}   [{shown}]")
            return True
        try:
            p = self.claude_run(args)
        except Exception as e:
            self.say("failed", f"{label}: {e.__class__.__name__}")
            return False
        if p.returncode != 0:
            lines = [ln.strip() for ln in (p.stdout + "\n" + p.stderr).splitlines() if ln.strip()]
            pick = next((ln for ln in lines if "fail" in ln.lower() or "error" in ln.lower() or "fatal" in ln.lower()),
                        lines[-1] if lines else "no error text")
            self.say("failed", f"{label}: {pick[:200]}")
            return False
        self.say("added", label)
        return True

    def step_plugins_and_mcp(self):
        markets = [m for g in self.groups for m in g.get("marketplaces", [])]
        plugins = [p for g in self.groups for p in g.get("plugins", [])]
        servers = [s for g in self.groups for s in g.get("mcp", [])]
        print("Plugins")
        if self.skip_cli:
            self.say("info", "skipped (--skip-cli): " + ", ".join(plugins))
        elif not self.claude:
            self.say("failed", "the `claude` command was not found on PATH, so plugins and MCP servers were not set up")
            self.manual.append("Install Claude Code, then run this installer again to add the plugins and MCP servers.")
        else:
            have_m = self.cli_json(["plugin", "marketplace", "list", "--json"])
            have_p = self.cli_json(["plugin", "list", "--json"])
            if have_m is None or have_p is None:
                self.say("failed", "could not read the current plugin list from `claude`; skipped plugins")
            else:
                names = {m.get("name") for m in have_m}
                ids = {p.get("id") for p in have_p}
                ok_market = set(names)
                for m in markets:
                    if m["name"] in names:
                        self.say("same", f"marketplace {m['name']}")
                    # Explicit HTTPS: the owner/repo shorthand clones over SSH, which fails on a machine
                    # that has never connected to github.com over SSH (host key not in known_hosts).
                    elif self.cli_do(["plugin", "marketplace", "add", f"https://github.com/{m['repo']}.git"],
                                     f"marketplace {m['name']}"):
                        ok_market.add(m["name"])
                for pid in plugins:
                    mk = pid.split("@", 1)[1]
                    if pid in ids:
                        self.say("same", f"plugin {pid}")
                    elif mk in ok_market:
                        self.cli_do(["plugin", "install", pid, "--scope", "user"], f"plugin {pid}")
                    else:
                        self.say("failed", f"plugin {pid}: its marketplace could not be added")
        print("MCP servers")
        if self.skip_cli or not self.claude:
            self.say("info", "skipped: " + ", ".join(s["name"] for s in servers))
            return
        self.backup(self.claude_json)
        existing = read_json(self.claude_json).get("mcpServers", {})
        for s in servers:
            if s["name"] in existing:
                self.say("same", f"mcp {s['name']} (already configured, kept yours)")
                continue
            if s["transport"] == "http":
                args = ["mcp", "add", "--scope", "user", "--transport", "http", s["name"], s["url"]]
                # --header takes several values, so it goes last. The value is a ${VAR} placeholder that
                # Claude Code expands when it connects; the secret itself never passes through here.
                for k, v in s.get("headers", {}).items():
                    args += ["--header", f"{k}: {v}"]
            else:
                args = ["mcp", "add", "--scope", "user", s["name"], "--", s["command"], *s["args"]]
            self.cli_do(args, f"mcp {s['name']}")

    # ---- settings.json ------------------------------------------------------------------
    def step_settings(self):
        print("Settings")
        shareable = json.loads((ROOT / "config" / "settings.shareable.json").read_text(encoding="utf-8"))
        wanted = copy.deepcopy(shareable["core"])
        for e in self.extras:
            merge_add_only(wanted, shareable["extras"].get(e, {}))
        merge_add_only(wanted, self.extra_settings)
        path = self.cfg / "settings.json"
        current = read_json(path)
        before = json.dumps(current, sort_keys=True)
        results = merge_add_only(current, wanted)
        for status, label in results:
            self.say(status, f"setting {label}")
        if json.dumps(current, sort_keys=True) != before and self.apply:
            self.backup(path)
            self.write_atomic(path, (json.dumps(current, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))

    # ---- report -------------------------------------------------------------------------
    def report(self):
        print()
        c = self.counts
        head = "DRY RUN, nothing was changed" if not self.apply else "DONE"
        print(f"{head}: {c['added']} to add, {c['same']} already in place, {c['kept']} kept as yours, {c['failed']} failed")
        if self.apply and self.backed_up:
            print(f"Backups of anything replaced or edited: {self.backup_dir}")
        for e in self.extras:
            m = self.manifest["extras"][e].get("manual")
            if m:
                self.manual.append(m)
        if platform.system() == "Windows" and shutil.which("git"):
            lp = subprocess.run(["git", "config", "--get", "core.longpaths"], capture_output=True, text=True)
            if lp.stdout.strip().lower() != "true":
                self.manual.append("If a plugin ever fails to install with 'Filename too long', run once: git config --global core.longpaths true")
        self.manual.append("Cloudflare: its MCP server needs a sign-in. Start Claude Code, run /mcp, pick cloudflare and log in. Skip this if you don't use Cloudflare.")
        self.manual.append("Optional: for a higher Context7 docs quota, run: npx ctx7@latest login")
        self.manual.append("Optional: connect Gmail, Google Drive, Calendar and Docs at claude.ai (Settings > Connectors). They belong to your account, so this installer can't do it.")
        self.manual.append("Restart Claude Code so the new plugins, skills and settings load.")
        print("Manual steps for you:")
        for m in self.manual:
            print(f"  - {m}")
        if not self.apply:
            print("To apply: run the same command again with --apply")

    def run(self):
        print(f"{'APPLY' if self.apply else 'DRY RUN'}  config folder: {self.cfg}")
        print(f"Extras: {', '.join(self.extras) if self.extras else '(none)'}")
        print("Compaction: " + ("fast-jev-compaction (replaces the built-in one)" if "fast-jev" in self.extras
                                else "Claude Code's default (recommended; nothing to install)"))
        # Refuse early, before anything is written.
        read_json(self.cfg / "settings.json")
        if self.claude:
            read_json(self.claude_json)
        self.step_claude_md()
        self.step_files()
        self.step_statusline()
        self.step_plugins_and_mcp()
        self.step_settings()
        self.report()
        return 1 if self.counts["failed"] else 0


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="make the changes (default is a dry run)")
    ap.add_argument("--with", dest="with_", default="", help="comma list of extras, or 'all'")
    ap.add_argument("--list-extras", action="store_true", help="list the optional extras and exit")
    ap.add_argument("--on-conflict", choices=["skip", "overwrite"], default="skip",
                    help="when a rule or skill of yours differs: keep yours (default) or replace it (old copy is backed up)")
    ap.add_argument("--config-dir", help="Claude Code config folder (default: $CLAUDE_CONFIG_DIR or ~/.claude)")
    ap.add_argument("--skip-cli", action="store_true", help="don't call the claude command (plugins and MCP)")
    ap.add_argument("--statusline-source", help=argparse.SUPPRESS)
    args = ap.parse_args()
    extras_all = list(manifest["extras"])
    if args.list_extras:
        for name, e in manifest["extras"].items():
            note = "  [ask separately; never part of 'all']" if e.get("explicit_only") else ""
            print(f"{name}: {e['description']}{note}")
        return 0
    wanted = [x.strip() for x in args.with_.split(",") if x.strip()]
    if "all" in wanted:
        # "all" never includes extras marked explicit_only (fast-jev): those must be named on purpose.
        wanted = [x for x in extras_all if not manifest["extras"][x].get("explicit_only")] + [x for x in wanted if x in extras_all]
    unknown = [x for x in wanted if x not in extras_all]
    if unknown:
        print(f"Unknown extra(s): {', '.join(unknown)}. Known: {', '.join(extras_all)}", file=sys.stderr)
        return 2
    args.extras = [x for x in extras_all if x in wanted]
    try:
        return Installer(args, manifest).run()
    except Refuse as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
