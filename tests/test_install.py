"""Integration tests: run install.py and export.scan_tree against throwaway folders.

    python -m unittest discover -s tests -v

None of these touch your real ~/.claude (every run uses a temp --config-dir and --skip-cli).
"""
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import export  # noqa: E402

MANIFEST = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))


def snapshot(folder, skip_backups=True):
    """{relative path: sha256} of every file under folder."""
    out = {}
    for p in sorted(Path(folder).rglob("*")):
        rel = p.relative_to(folder).as_posix()
        if skip_backups and rel.startswith("backups"):
            continue
        if p.is_file():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "cfg"
        self.cfg.mkdir()
        self.fake_sl = Path(self.tmp.name) / "sl.ps1"
        self.fake_sl.write_text("# fake status line\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_install(self, *extra):
        cmd = [sys.executable, str(ROOT / "install.py"), "--config-dir", str(self.cfg), "--skip-cli",
               "--statusline-source", str(self.fake_sl), *extra]
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    def seed(self):
        (self.cfg / "settings.json").write_text(json.dumps(
            {"theme": "dark", "model": "opus", "enabledPlugins": {"mine@somewhere": True}}, indent=2), encoding="utf-8")
        (self.cfg / "CLAUDE.md").write_text("My own notes.\n\nAlways be kind.\n", encoding="utf-8")

    def test_dry_run_changes_nothing(self):
        self.seed()
        before = snapshot(self.cfg, skip_backups=False)
        r = self.run_install("--with", "all")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("DRY RUN", r.stdout)
        self.assertEqual(before, snapshot(self.cfg, skip_backups=False))
        self.assertFalse((self.cfg / "backups").exists())

    def test_apply_keeps_what_the_user_has(self):
        self.seed()
        r = self.run_install("--with", "all", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        settings = json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["theme"], "dark")  # yours wins
        self.assertEqual(settings["model"], "opus")  # yours wins
        self.assertTrue(settings["enabledPlugins"]["mine@somewhere"])
        self.assertTrue(settings["enabledPlugins"]["cc-plugin-you-should-know@builtin"])
        self.assertEqual(settings["advisorModel"], "fable")
        self.assertEqual(settings["askUserQuestionTimeout"], "never")  # questions wait for an answer
        md = (self.cfg / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertTrue(md.startswith("My own notes.\n\nAlways be kind.\n"))
        self.assertIn("claude-code-setup:begin", md)
        for name in MANIFEST["core"]["skills"]:
            self.assertTrue((self.cfg / "skills" / name / "SKILL.md").exists(), name)
        for name in MANIFEST["core"]["rules"]:
            self.assertTrue((self.cfg / "rules" / name).exists(), name)
        backups = list((self.cfg / "backups").glob("claude-code-setup-*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads((backups[0] / "settings.json").read_text(encoding="utf-8"))["model"], "opus")

    def test_home_token_is_filled_in(self):
        self.run_install("--apply")
        skill = (self.cfg / "skills" / "ui-ux-pro-max" / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn(MANIFEST["token"], skill)
        self.assertIn(self.cfg.as_posix() + "/skills/ui-ux-pro-max/scripts/search.py", skill)

    def test_second_apply_changes_nothing(self):
        self.seed()
        self.run_install("--with", "all", "--apply")
        first = snapshot(self.cfg)
        r = self.run_install("--with", "all", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("0 to add", r.stdout)
        self.assertEqual(first, snapshot(self.cfg))
        self.assertEqual(len(list((self.cfg / "backups").glob("claude-code-setup-*"))), 1)

    def test_invalid_json_is_refused_and_nothing_written(self):
        (self.cfg / "settings.json").write_text("{ not json", encoding="utf-8")
        before = snapshot(self.cfg, skip_backups=False)
        r = self.run_install("--with", "all", "--apply")
        self.assertEqual(r.returncode, 2)
        self.assertIn("REFUSED", r.stderr)
        self.assertEqual(before, snapshot(self.cfg, skip_backups=False))

    def test_conflicting_skill_is_kept_unless_overwrite(self):
        mine = self.cfg / "skills" / "animate"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("my own animate skill\n", encoding="utf-8")
        r = self.run_install("--apply")
        self.assertIn("kept yours", r.stdout)
        self.assertEqual((mine / "SKILL.md").read_text(encoding="utf-8"), "my own animate skill\n")
        r = self.run_install("--apply", "--on-conflict", "overwrite")
        self.assertNotEqual((mine / "SKILL.md").read_text(encoding="utf-8"), "my own animate skill\n")
        saved = list((self.cfg / "backups").glob("claude-code-setup-*/skills/animate/SKILL.md"))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(encoding="utf-8"), "my own animate skill\n")

    def test_all_never_includes_fast_jev_but_naming_it_does(self):
        r = self.run_install("--with", "all", "--apply")
        self.assertIn("Compaction: Claude Code's default", r.stdout)
        settings = json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("CLAUDE_CODE_ENABLE_FUNCTION_HOOKS", settings.get("env", {}))
        self.assertNotIn("pluginConfigs", settings)
        r = self.run_install("--with", "fast-jev", "--apply")
        self.assertIn("Compaction: fast-jev-compaction", r.stdout)
        settings = json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["env"]["CLAUDE_CODE_ENABLE_FUNCTION_HOOKS"], "1")
        r = self.run_install("--with", "all,fast-jev")
        self.assertIn("Compaction: fast-jev-compaction", r.stdout)

    def test_unknown_extra_is_rejected(self):
        r = self.run_install("--with", "nope")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(snapshot(self.cfg, skip_backups=False), {})

    @unittest.skipUnless(platform.system() == "Windows", "status line is Windows-only")
    def test_statusline_sets_command_and_keeps_existing(self):
        r = self.run_install("--with", "statusline", "--apply")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        settings = json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))
        self.assertIn(self.cfg.as_posix() + "/statusline.ps1", settings["statusLine"]["command"])
        (self.cfg / "settings.json").write_text(json.dumps({"statusLine": {"type": "command", "command": "mine"}}), encoding="utf-8")
        self.run_install("--with", "statusline", "--apply")
        settings = json.loads((self.cfg / "settings.json").read_text(encoding="utf-8"))
        self.assertEqual(settings["statusLine"]["command"], "mine")


class RepoHygieneTests(unittest.TestCase):
    def test_no_local_claude_folder_is_tracked(self):
        r = subprocess.run(["git", "ls-files", ".claude"], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "")


class ScanTests(unittest.TestCase):
    def scan(self, files):
        with tempfile.TemporaryDirectory() as d:
            for rel, body in files.items():
                p = Path(d) / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(body, encoding="utf-8")
            return export.scan_tree(d, MANIFEST, private=[])

    def test_the_repo_itself_is_clean_of_generic_patterns(self):
        self.assertEqual(export.scan_tree(ROOT, MANIFEST, private=[]), [])

    def test_planted_secret_is_caught(self):
        fake = "ctx7sk-" + "0123456789abcdef"
        hits = self.scan({"config/rules/x.md": f"key = {fake}\n"})
        self.assertTrue(any(label == "api-key-ctx7" for _, _, label in hits))

    def test_planted_token_assignment_and_private_ip_and_path(self):
        # Built at run time so this file doesn't contain the patterns it tests for.
        body = "api_" + "key: " + "abcdefghijklmnopqrstuvwx\n" + "host 192." + "168.1.20\n" + "C:/Us" + "ers/someone/.claude\n"
        hits = self.scan({"a.md": body})
        labels = {label for _, _, label in hits}
        self.assertTrue({"secret-assignment", "private-ip", "windows-user-path"} <= labels, labels)

    def test_memory_and_credential_files_are_forbidden(self):
        hits = self.scan({"x/claude-mem.db": "", "x/history.jsonl": "", ".credentials.json": "{}",
                          "settings.json": "{}", ".claude-" + "mem/notes.md": "hi"})
        labels = [label for _, _, label in hits]
        self.assertGreaterEqual(labels.count("forbidden-file"), 4)
        self.assertIn("forbidden-folder", labels)

    def test_private_pattern_scope(self):
        import re
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "skills").mkdir()
            word = "web" + "hook"  # built at run time so this file doesn't contain it
            (Path(d) / "skills" / "a.md").write_text(word + "\n", encoding="utf-8")
            (Path(d) / "README.md").write_text(word + "\n", encoding="utf-8")
            hits = export.scan_tree(d, MANIFEST, private=[("private", "root", re.compile(word))])
        self.assertEqual([h[0] for h in hits], ["README.md"])


if __name__ == "__main__":
    unittest.main()
