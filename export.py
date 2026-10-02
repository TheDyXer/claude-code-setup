#!/usr/bin/env python3
"""Owner-side tool: rebuild config/ from the live Claude Code setup, then scan the repo.

Only what manifest.json allowlists is copied. Absolute paths into the config folder are
rewritten to {{CLAUDE_HOME}}. The scan fails the run if anything secret or personal is left.

Personal patterns (hostnames, e-mail, names) live outside the repo, one per line, in
~/.claude-code-setup-private/scan-patterns.txt (or the file named by CLAUDE_SETUP_SCAN_PRIVATE).
Format: `regex` or `scope|regex`, where scope is a top-level folder name or `*`.
"""
import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKIP_DIRS = {"__pycache__", "node_modules", ".git"}
SKIP_SUFFIXES = {".pyc", ".pyo"}

# Generic patterns: safe to publish because they name no person, host or account.
GENERIC_PATTERNS = [
    ("api-key-ctx7", r"ctx7sk-[A-Za-z0-9-]{8,}"),
    ("github-token", r"\bgh[pousr]_[A-Za-z0-9]{20,}|\bgithub_pat_[A-Za-z0-9_]{20,}"),
    ("secret-key-sk", r"(?<![A-Za-z])sk-[A-Za-z0-9_-]{20,}"),
    ("aws-key", r"\bAKIA[0-9A-Z]{16}\b"),
    ("private-key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("bearer-token", r"(?i)\bbearer\s+(?!YOUR_TOKEN|<)[A-Za-z0-9._~+/=-]{16,}"),
    ("secret-assignment", r"(?i)(api[_-]?key|token|secret|passwd|password)[\"']?\s*[:=]\s*[\"']?[A-Za-z0-9_\-]{20,}"),
    ("private-ip", r"\b(?:10\.\d{1,3}|192\.168|172\.(?:1[6-9]|2\d|3[01]))\.\d{1,3}\.\d{1,3}\b"),
    ("windows-user-path", r"(?i)\b[A-Z]:[\\/]+Users[\\/]+(?!<|\$|%|\{|you\b|your\b|name\b|username\b|Public\b|Default\b)[^\\/\s\"'`<>]+"),
    ("unix-home-path", r"(?<![\w.])/(?:home|Users)/(?!<|\$|\{|you\b|your\b|name\b|username\b|user\b|runner\b)[a-z][\w.-]*"),
    ("email", r"\b[\w.+-]+@(?!example\.|anthropic\.com\b|users\.noreply\.github\.com\b)[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}\b"),
]

# Files that must never be in the repo, whatever their content: memory databases, session
# logs, credentials and whole settings/config files. Matched on the file name or any folder.
FORBIDDEN_NAMES = re.compile(
    r"(?i)(\.db|\.sqlite3?|\.jsonl|\.bak[-.\w]*|\.env(\..*)?|\.pem|\.key)$"
    r"|^(\.credentials\.json|\.claude\.json|settings\.json|settings\.local\.json|history\.jsonl|CLAUDE\.md)$"
)
FORBIDDEN_DIRS = re.compile(r"(?i)^(\.claude-mem|claude-mem-data|projects|sessions|session-env|shell-snapshots|backups)$")


def load_manifest():
    return json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def live_config_dir():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"


def live_claude_json(config_dir):
    home_json = Path.home() / ".claude.json"
    if config_dir.resolve() == (Path.home() / ".claude").resolve():
        return home_json
    return config_dir / ".claude.json"


def path_variants(p):
    s = str(p)
    fwd = s.replace("\\", "/")
    return sorted({s, fwd, s.replace("\\", "\\\\"), fwd.lower(), s.lower()}, key=len, reverse=True)


def rewrite_bytes(data, variants, token):
    for v in variants:
        data = data.replace(v.encode("utf-8"), token.encode("utf-8"))
    return data


def copy_tree(src, dst, variants, token):
    """Copy src to dst following junctions/symlinks, skipping build junk, rewriting paths."""
    count = 0
    for dirpath, dirnames, filenames in os.walk(src, followlinks=True):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel = Path(dirpath).relative_to(src)
        (dst / rel).mkdir(parents=True, exist_ok=True)
        for name in filenames:
            if Path(name).suffix in SKIP_SUFFIXES:
                continue
            data = (Path(dirpath) / name).read_bytes()
            (dst / rel / name).write_bytes(rewrite_bytes(data, variants, token))
            count += 1
    return count


def dig(obj, path):
    for key in path:
        if not isinstance(obj, dict) or key not in obj:
            raise KeyError("/".join(path))
        obj = obj[key]
    return obj


def put(obj, path, value):
    for key in path[:-1]:
        obj = obj.setdefault(key, {})
    obj[path[-1]] = value


def setting_entry(entry, live_settings):
    """A manifest settings entry is a path copied from the live value, or {"path", "value"} pinned."""
    if isinstance(entry, dict):
        return entry["path"], entry["value"]
    return entry, dig(live_settings, entry)


def build_settings(manifest, live_settings):
    out = {"core": {}, "extras": {}}
    for entry in manifest["core"]["settings"]:
        path, value = setting_entry(entry, live_settings)
        put(out["core"], path, value)
    for name, extra in manifest["extras"].items():
        for entry in extra.get("settings", []):
            path, value = setting_entry(entry, live_settings)
            out["extras"].setdefault(name, {})
            put(out["extras"][name], path, value)
    return out


def check_drift(manifest, config_dir, warnings):
    """Compare manifest marketplaces and MCP servers with the live config."""
    km = config_dir / "plugins" / "known_marketplaces.json"
    live_mk = {}
    if km.exists():
        for name, v in json.loads(km.read_text(encoding="utf-8")).items():
            live_mk[name] = v.get("source", {}).get("repo")
    groups = [manifest["core"]] + list(manifest["extras"].values())
    for g in groups:
        for m in g.get("marketplaces", []):
            if live_mk.get(m["name"]) != m["repo"]:
                warnings.append(f"marketplace {m['name']}: manifest says {m['repo']}, live says {live_mk.get(m['name'])}")
    cj = live_claude_json(config_dir)
    live_mcp = json.loads(cj.read_text(encoding="utf-8")).get("mcpServers", {}) if cj.exists() else {}
    for g in groups:
        for s in g.get("mcp", []):
            if s.get("live") is False:
                continue
            live = live_mcp.get(s["name"])
            if not live:
                warnings.append(f"mcp {s['name']}: not in live config")
            elif s["transport"] == "http" and live.get("url") != s["url"]:
                warnings.append(f"mcp {s['name']}: url differs from live")
            elif s["transport"] == "stdio" and (live.get("command") != s["command"] or live.get("args") != s["args"]):
                warnings.append(f"mcp {s['name']}: command/args differ from live")
    block = (ROOT / "config" / "advisor-block.md").read_text(encoding="utf-8").strip()
    live_md = config_dir / "CLAUDE.md"
    if not live_md.exists() or block not in live_md.read_text(encoding="utf-8"):
        warnings.append("advisor block not found verbatim in the live CLAUDE.md")


def load_private_patterns():
    path = Path(os.environ.get("CLAUDE_SETUP_SCAN_PRIVATE", Path.home() / ".claude-code-setup-private" / "scan-patterns.txt"))
    pats = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head, sep, tail = line.partition("|")
            if sep and re.fullmatch(r"[\w*,-]+", head):
                scope, rx = head, tail
            else:
                scope, rx = "*", line
            pats.append(("private", scope, re.compile(rx, re.I)))
    return pats, path.exists()


def scan_tree(root, manifest, private=None):
    """Return a list of (relative path, line number, label). Never returns matched text."""
    generic = [(label, "*", re.compile(rx)) for label, rx in GENERIC_PATTERNS]
    private_pats, _ = (private, True) if private is not None else load_private_patterns()
    pats = generic + list(private_pats)
    ignore = set(manifest["scan"]["ignore_dirs"])
    allow = manifest["scan"].get("allow", [])
    hits = []
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            if d not in ignore and FORBIDDEN_DIRS.match(d):
                hits.append(((Path(dirpath) / d).relative_to(root).as_posix() + "/", 0, "forbidden-folder"))
        dirnames[:] = [d for d in dirnames if d not in ignore and not FORBIDDEN_DIRS.match(d)]
        for name in filenames:
            p = Path(dirpath) / name
            rel = p.relative_to(root).as_posix()
            if FORBIDDEN_NAMES.search(name):
                hits.append((rel, 0, "forbidden-file"))
                continue
            if name == "export.py" and Path(dirpath) == Path(root):
                continue  # holds the generic patterns themselves
            try:
                text = p.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            top = rel.split("/")[0] if "/" in rel else "root"
            for n, line in enumerate(text.splitlines(), 1):
                for label, scope, rx in pats:
                    if scope != "*" and top not in scope.split(","):
                        continue
                    if rx.search(line):
                        if any(a["label"] == label and re.fullmatch(a["file"], rel) for a in allow):
                            continue
                        hits.append((rel, n, label))
    return hits


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan-only", action="store_true", help="skip the export, just scan the repo")
    args = ap.parse_args()
    manifest = load_manifest()
    token = manifest["token"]
    warnings = []

    if not args.scan_only:
        cfg = live_config_dir()
        variants = path_variants(cfg)
        out = ROOT / "config"
        for sub in ("rules", "skills"):
            shutil.rmtree(out / sub, ignore_errors=True)
            (out / sub).mkdir(parents=True)
        for name in manifest["core"]["rules"]:
            src = cfg / "rules" / name
            (out / "rules" / name).write_bytes(rewrite_bytes(src.read_bytes(), variants, token))
        files = 0
        for name in manifest["core"]["skills"]:
            src = cfg / "skills" / name
            if not (src / "SKILL.md").exists():
                sys.exit(f"export: skill '{name}' has no SKILL.md in {src}")
            files += copy_tree(src, out / "skills" / name, variants, token)
        settings = json.loads((cfg / "settings.json").read_text(encoding="utf-8"))
        shareable = build_settings(manifest, settings)
        (out / "settings.shareable.json").write_text(json.dumps(shareable, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        check_drift(manifest, cfg, warnings)
        print(f"export: {len(manifest['core']['rules'])} rules, {len(manifest['core']['skills'])} skills ({files} files), settings.shareable.json")

    for w in warnings:
        print(f"export: WARNING {w}")
    private_pats, found = load_private_patterns()
    if not found:
        print("export: WARNING no private pattern file found; only generic checks ran")
    hits = scan_tree(ROOT, manifest, private_pats)
    for rel, n, label in hits:
        print(f"scan: HIT {rel}:{n} [{label}]")
    if hits:
        print(f"scan: FAILED with {len(hits)} hit(s)")
        sys.exit(1)
    print("scan: clean")


if __name__ == "__main__":
    main()
