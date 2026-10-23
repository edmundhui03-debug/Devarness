#!/usr/bin/env python3
"""Tests for i18n: the language toggle it injects, and the selftest that guards its check.

The toggle script runs in node against a small page fixture. On a Chinese-language
browser, an explicit English choice must survive reload rather than being treated
as an unset default.

The selftest is run as it ships, and again from copies of the tool with one rule of check
switched off. Each copy must exit 1 and name exactly the cases that rule guards, so no case is
dead weight and no rule goes unguarded.
"""
import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "bin" / "i18n"
BASH = (str(Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe")
        if os.name == "nt" else shutil.which("bash"))
if BASH and not Path(BASH).is_file():
    BASH = None
I18N_ENV = dict(os.environ)
I18N_ENV.setdefault("DEVARNESS_I18N_PYTHON", sys.executable)


@unittest.skipUnless(BASH, "Git Bash on Windows or bash runs i18n")
class LauncherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="i18n-launcher-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "empty-home"
        self.home.mkdir()
        self.capture = self.root / "arguments"

    def interpreter(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'#!/usr/bin/env bash\nprintf "%s\\n" "$@" > "$CAPTURE"\nexit "${FAKE_EXIT:-0}"\n')
        path.chmod(0o755)
        return path

    def launch(self, **changes):
        env = dict(os.environ, HOME=self.home.as_posix(), CAPTURE=self.capture.as_posix(),
                   DEVARNESS_I18N_PYTHON="")
        env.update(changes)
        return subprocess.run([BASH, str(TOOL), "argument with spaces", "$literal"], cwd=self.root,
                              env=env, capture_output=True, text=True, timeout=30,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))

    def test_explicit_interpreter_path_is_literal_and_failure_propagates(self):
        python = self.interpreter("fake interpreter $(touch SENTINEL)/python")
        done = self.launch(DEVARNESS_I18N_PYTHON=python.as_posix(), FAKE_EXIT="37")
        self.assertEqual(done.returncode, 37, done.stdout + done.stderr)
        self.assertEqual(self.capture.read_text().splitlines(), ["-", "argument with spaces", "$literal"])
        self.assertFalse((self.root / "SENTINEL").exists())

    def test_clean_home_uses_python3_on_path(self):
        python = self.interpreter("path-bin/python3")
        done = self.launch(PATH=str(python.parent) + os.pathsep + os.environ.get("PATH", ""))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.capture.read_text().splitlines(), ["-", "argument with spaces", "$literal"])

HARNESS = r"""
const [script, language, saved, click] = process.argv.slice(2);
const store = new Map(saved ? [['page-lang', saved]] : []);
const node = { key: 'hello', innerHTML: 'Hello', getAttribute() { return this.key; } };
const button = () => ({ handlers: [], setAttribute() {}, addEventListener(name, handler) { this.handlers.push(handler); } });
const buttons = { 'page-lang-en': button(), 'page-lang-zh': button() };
const root = { lang: null, setAttribute(name, value) { this.lang = value; } };
// Recent node has a navigator of its own, read-only, that reports the machine's language.
Object.defineProperty(globalThis, 'navigator', { value: { language }, configurable: true });
global.localStorage = { getItem: (k) => (store.has(k) ? store.get(k) : null), setItem: (k, v) => store.set(k, v) };
global.document = { title: 'Page', documentElement: root, querySelectorAll: () => [node],
  getElementById: (id) => (id === 'i18n-zh' ? { textContent: JSON.stringify({ hello: '你好' }) } : buttons[id]) };
eval(require('fs').readFileSync(script, 'utf8'));
if (click) buttons['page-lang-' + click].handlers.forEach((handler) => handler());
console.log(JSON.stringify({ lang: root.lang, text: node.innerHTML, saved: store.get('page-lang') || null }));
"""


def toggle_js():
    # i18n is a shell wrapper around a Python heredoc, so it cannot be imported; read the literal.
    source = TOOL.read_text(encoding="utf-8")
    literal = re.search(r'^TOGGLE_JS = (""".*?""")', source, re.S | re.M).group(1)
    return ast.literal_eval(literal)


@unittest.skipUnless(shutil.which("node"), "node runs the toggle script")
class ToggleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="i18n-toggle-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.script = Path(cls.tmp.name) / "toggle.js"
        cls.script.write_text(toggle_js(), encoding="utf-8")
        cls.harness = Path(cls.tmp.name) / "harness.js"
        cls.harness.write_text(HARNESS, encoding="utf-8")

    def page(self, language, saved="", click=""):
        done = subprocess.run(["node", str(self.harness), str(self.script), language, saved, click],
                              capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout)

    def test_english_is_the_default(self):
        self.assertEqual(self.page("en-GB")["lang"], "en")
        self.assertEqual(self.page("fr-FR")["lang"], "en")

    def test_a_chinese_browser_opens_in_cantonese(self):
        opened = self.page("zh-TW")
        self.assertEqual((opened["lang"], opened["text"]), ("zh-HK", "你好"))

    def test_a_saved_choice_of_english_outlasts_a_chinese_browser(self):
        opened = self.page("zh-TW", saved="en")
        self.assertEqual((opened["lang"], opened["text"], opened["saved"]), ("en", "Hello", "en"))

    def test_a_saved_choice_of_cantonese_outlasts_an_english_browser(self):
        self.assertEqual(self.page("en-GB", saved="zh")["lang"], "zh-HK")

    def test_only_a_click_is_remembered_never_a_guess(self):
        self.assertIsNone(self.page("zh-TW")["saved"])
        self.assertEqual(self.page("zh-TW", click="en"), {"lang": "en", "text": "Hello", "saved": "en"})


# Each rule check enforces, switched off in a copy of the tool, and the selftest cases that must
# then fail. `check page.html` and the no-argument workspace check carry separate copies of the
# rules, so each copy is switched off on its own. Every anchor must occur once in the tool.
PAGE_EXIT = "sys.exit(1 if (miss or not keys or not soup.select_one('.page-lang')) else 0)"
WORKSPACE_BAD = "bad = bool(miss) or not toggle or not keys"
WEAKENINGS = (
    ("page check ignores the toggle", PAGE_EXIT, "sys.exit(1 if (miss or not keys) else 0)",
     ["page check fails a page with no toggle"]),
    ("page check ignores untranslated strings", PAGE_EXIT,
     "sys.exit(1 if (not keys or not soup.select_one('.page-lang')) else 0)",
     ["page check fails a page with one untranslated string",
      "page check fails a page with no dictionary",
      "page check fails a page with a broken dictionary",
      "page check fails a page whose translations are blank",
      "page check fails a page whose dictionary only lists its keys"]),
    ("page check passes a page with nothing tagged", PAGE_EXIT,
     "sys.exit(1 if (miss or not soup.select_one('.page-lang')) else 0)",
     ["page check fails a page injected without extract"]),
    ("page check counts a missing dictionary as translated",
     "        have = len(keys & done);",
     "        done = done if box else set(keys)\n        have = len(keys & done);",
     ["page check fails a page with no dictionary"]),
    ("page check counts a broken dictionary as translated",
     "except Exception: pass\n        done = translated(zh)\n",
     "except Exception: zh = dict.fromkeys(keys, 'x')\n        done = translated(zh)\n",
     ["page check fails a page with a broken dictionary"]),
    ("both checks count blank or key-only dictionaries as translated",
     "    if not isinstance(zh, dict):\n        return set()\n"
     "    return {k for k, v in zh.items() if isinstance(v, str) and v.strip()}\n",
     "    return set(zh)\n",
     ["page check fails a page whose translations are blank",
      "page check fails a page whose dictionary only lists its keys",
      "workspace check fails a page whose translations are blank",
      "workspace check fails a page whose dictionary only lists its keys"]),
    # The edited pre-import page is the page with no toggle, changed after its hash was taken.
    ("workspace check ignores the toggle", WORKSPACE_BAD, "bad = bool(miss) or not keys",
     ["workspace check fails a page with no toggle",
      "workspace check fails a listed page once it is edited"]),
    ("workspace check ignores untranslated strings", WORKSPACE_BAD, "bad = not toggle or not keys",
     ["workspace check fails a page with one untranslated string",
      "workspace check fails a page with no dictionary",
      "workspace check fails a page with a broken dictionary",
      "workspace check fails a page whose translations are blank",
      "workspace check fails a page whose dictionary only lists its keys"]),
    ("workspace check passes a page with nothing tagged", WORKSPACE_BAD,
     "bad = bool(miss) or not toggle",
     ["workspace check fails a page injected without extract"]),
    ("workspace check skips a page it cannot read",
     'print(f"{page}: unreadable ({exc})"); failed += 1; continue', "continue",
     ["workspace check fails a tracked page it cannot read"]),
    ("workspace check counts a missing dictionary as translated",
     "        miss = sorted(keys - translated(zh))\n        toggle = ",
     "        zh = zh if box else dict.fromkeys(keys, 'x')\n        miss = sorted(keys - translated(zh))\n"
     "        toggle = ",
     ["workspace check fails a page with no dictionary"]),
    ("workspace check counts a broken dictionary as translated",
     "except Exception: pass\n        miss = ",
     "except Exception: zh = dict.fromkeys(keys, 'x')\n        miss = ",
     ["workspace check fails a page with a broken dictionary"]),
    # A page saved in another encoding raises UnicodeDecodeError, which is a
    # ValueError and so escaped the `except OSError` that guards the read. It
    # aborted the whole scan and still exited 1, which reads like a verdict.
    ("workspace check lets a non-UTF-8 page abort the scan",
     '        except UnicodeDecodeError:\n'
     '            # not UTF-8. Reported like any other failing page: the scan must not\n'
     '            # abandon the pages after it, and an unhandled traceback also exits\n'
     '            # 1, which is indistinguishable from an ordinary verdict.\n'
     '            print(f"{page}: undecodable (not UTF-8)"); failed += 1; continue\n',
     "        except UnicodeDecodeError:\n            raise\n",
     ["workspace check fails a page that is not UTF-8"]),
    # A page imported on 2026-09-21 is history only while its content is unchanged.
    ("workspace check keeps an edited pre-import page exempt",
     "if content_hash(path) == legacy[rel]:", "if True:",
     ["workspace check fails a listed page once it is edited"]),
    ("page check crashes on a non-UTF-8 page",
     '    try:\n        html = open(path, encoding="utf-8").read()\n'
     '    except UnicodeDecodeError:\n'
     '        print(f"{path}: undecodable (not UTF-8)"); sys.exit(1)',
     '    html = open(path, encoding="utf-8").read()',
     ["page check fails a page that is not UTF-8"]),
)


def lines_marked(output, mark):
    """The case labels selftest printed as `ok` or `FAIL`, without any reason."""
    prefix = "  {:<4}  ".format(mark)
    return sorted(line[len(prefix):].split(" -- ", 1)[0]
                  for line in output.splitlines() if line.startswith(prefix))


@unittest.skipUnless(BASH, "bash runs i18n")
class SelftestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe = subprocess.run([BASH, str(TOOL), "--help"], capture_output=True, text=True,
                               encoding="utf-8", timeout=60, env=I18N_ENV)
        if probe.returncode and "No module named 'bs4'" in probe.stderr:
            raise unittest.SkipTest(probe.stderr.strip())
        cls.tmp = tempfile.TemporaryDirectory(prefix="i18n-selftest-test-")
        cls.addClassCleanup(cls.tmp.cleanup)
        # Bytes, not text: on Windows a text write would turn the copies' LF endings into CRLF.
        cls.source = TOOL.read_bytes().decode("utf-8")

    def selftest(self, tool, **kwargs):
        kwargs.setdefault("env", I18N_ENV)
        return subprocess.run([BASH, str(tool), "selftest"], capture_output=True, text=True,
                              encoding="utf-8", timeout=300, **kwargs)

    def test_selftest_passes_every_case_on_the_tool_as_shipped(self):
        done = self.selftest(TOOL)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(lines_marked(done.stdout, "FAIL"), [])
        passed = lines_marked(done.stdout, "ok")
        self.assertRegex(done.stdout, r"\n{} checks, 0 failed\n".format(len(passed)))
        # Every page check should fail is proved load-bearing by a weakening below, and every
        # case a weakening names really runs.
        guarded = {case for _, _, _, cases in WEAKENINGS for case in cases}
        self.assertEqual({label for label in passed if " fails " in label}, guarded)

    def test_selftest_fails_naming_its_cases_when_a_rule_of_check_is_switched_off(self):
        for number, (rule, anchor, weaker, cases) in enumerate(WEAKENINGS):
            with self.subTest(rule):
                self.assertEqual(self.source.count(anchor), 1, "the anchor moved: " + anchor)
                copy = Path(self.tmp.name) / "weakened-{}".format(number) / "i18n"
                copy.parent.mkdir()
                copy.write_bytes(self.source.replace(anchor, weaker).encode("utf-8"))
                done = self.selftest(copy)
                self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
                self.assertEqual(lines_marked(done.stdout, "FAIL"), sorted(cases), done.stdout)

    def test_selftest_never_stages_into_the_repository_git_dir_names(self):
        # A git hook exports GIT_DIR. Inherited, the selftest's throwaway repositories would be
        # this one, and its fixture page would be staged into it.
        caller = Path(self.tmp.name) / "caller"
        subprocess.run(["git", "init", "-q", str(caller)], capture_output=True, check=True)
        done = self.selftest(TOOL, env=dict(I18N_ENV, GIT_DIR=str(caller / ".git")))
        staged = subprocess.run(["git", "-C", str(caller), "ls-files"], capture_output=True,
                                text=True, check=True).stdout
        self.assertEqual(staged, "")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

    def test_selftest_ignores_the_callers_git_configuration(self):
        # A global excludesFile that ignores pages would make `git add` refuse every fixture.
        config = Path(self.tmp.name) / "config-home"
        (config / "git").mkdir(parents=True)
        ignore = config / "ignore"
        ignore.write_text("*.html\n", encoding="utf-8")
        (config / "git" / "config").write_text(
            "[core]\n\texcludesFile = {}\n".format(ignore.as_posix()), encoding="utf-8")
        env = dict(I18N_ENV, XDG_CONFIG_HOME=str(config))
        probe = config / "probe"
        subprocess.run(["git", "init", "-q", str(probe)], capture_output=True, check=True, env=env)
        (probe / "page.html").write_text("<p>x</p>\n", encoding="utf-8")
        refused = subprocess.run(["git", "-C", str(probe), "add", "page.html"],
                                 capture_output=True, env=env).returncode
        if not refused:
            self.skipTest("this machine's ~/.gitconfig overrides core.excludesFile")
        done = self.selftest(TOOL, env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)


@unittest.skipUnless(BASH, "bash runs i18n")
class WorkspaceCheckTests(unittest.TestCase):
    def test_a_half_made_clone_is_not_checked_as_ours(self):
        # update-tools clones into <path>.partial and renames it only
        # when whole. Until then its pages are upstream's, not dev deliverables.
        with tempfile.TemporaryDirectory(prefix="i18n-partial-") as tmp:
            nested = Path(tmp) / "Harness" / "docling.partial"
            for repo in (Path(tmp), nested):
                subprocess.run(["git", "init", "-q", str(repo)], capture_output=True, check=True)
            (nested / "page.html").write_text("<p>Upstream's page, with no toggle.</p>\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(nested), "add", "page.html"], capture_output=True, check=True)
            done = subprocess.run([BASH, str(TOOL), "check"], cwd=tmp, capture_output=True, text=True,
                                  encoding="utf-8", timeout=120, env=I18N_ENV)
        if done.returncode and "No module named 'bs4'" in done.stderr:
            self.skipTest(done.stderr.strip())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("docling.partial", done.stdout)

    def test_a_datasheet_vendor_page_is_not_checked_as_ours(self):
        # A vendor's saved documentation is evidence, not an authored page.
        with tempfile.TemporaryDirectory(prefix="i18n-vendor-") as tmp:
            subprocess.run(["git", "init", "-q", tmp], capture_output=True, check=True)
            rel = "example-project/datasheets/vendor-manual.html"
            (Path(tmp) / rel).parent.mkdir(parents=True)
            (Path(tmp) / rel).write_text("<p>The vendor's page, with no toggle.</p>\n", encoding="utf-8")
            subprocess.run(["git", "-C", tmp, "add", rel], capture_output=True, check=True)
            done = subprocess.run([BASH, str(TOOL), "check"], cwd=tmp, capture_output=True, text=True,
                                  encoding="utf-8", timeout=120, env=I18N_ENV)
        if done.returncode and "No module named 'bs4'" in done.stderr:
            self.skipTest(done.stderr.strip())
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertNotIn("vendor-manual.html", done.stdout)

    def test_personal_exclusions_are_opt_in_and_namespaced(self):
        with tempfile.TemporaryDirectory(prefix="i18n-config-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            home = Path(tmp) / "home"
            page = root / "example-project" / "page.html"
            page.parent.mkdir()
            page.write_text("<p>A page with no toggle.</p>\n", encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], capture_output=True, check=True)
            subprocess.run(["git", "-C", str(root), "add", "."], capture_output=True, check=True)
            for namespace in ("dev", "devarness"):
                config = home / ".config" / namespace
                config.mkdir(parents=True)
                (config / "personal-repos.txt").write_text("example-project\n", encoding="utf-8")
            env = dict(I18N_ENV, HOME=str(home), USERPROFILE=str(home),
                       DEVARNESS_ALLOW_PERSONAL_REPOS="0")
            for enabled, expected in (("0", 1), ("1", 0)):
                env["DEVARNESS_ALLOW_PERSONAL_REPOS"] = enabled
                done = subprocess.run([BASH, str(TOOL), "check"], cwd=root,
                                      capture_output=True, text=True, encoding="utf-8",
                                      timeout=120, env=env)
                self.assertEqual(done.returncode, expected, done.stdout + done.stderr)
            (home / ".config" / "devarness" / "personal-repos.txt").unlink()
            done = subprocess.run([BASH, str(TOOL), "check"], cwd=root,
                                  capture_output=True, text=True, encoding="utf-8",
                                  timeout=120, env=env)
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)

    def test_all_source_pages_require_a_toggle(self):
        with tempfile.TemporaryDirectory(prefix="i18n-pages-") as tmp:
            subprocess.run(["git", "init", "-q", tmp], capture_output=True, check=True)
            for rel in ("app/index.html", "example-project/page.html"):
                path = Path(tmp) / rel
                path.parent.mkdir(parents=True)
                path.write_text("<p>A page with no toggle.</p>\n", encoding="utf-8")
                subprocess.run(["git", "-C", tmp, "add", rel], capture_output=True, check=True)
            done = subprocess.run([BASH, str(TOOL), "check"], cwd=tmp,
                                  capture_output=True, text=True, encoding="utf-8",
                                  timeout=120, env=I18N_ENV)
        if done.returncode and "No module named 'bs4'" in done.stderr:
            self.skipTest(done.stderr.strip())
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("index.html: no toggle", done.stdout)
        self.assertIn("page.html: no toggle", done.stdout)
        self.assertIn("2 deliverable page", done.stdout)

    def test_explicit_source_page_check_requires_a_toggle(self):
        with tempfile.TemporaryDirectory(prefix="i18n-page-") as tmp:
            path = Path(tmp) / "Harness/dashboard/index.html"
            path.parent.mkdir(parents=True)
            path.write_text("<p>A page with no toggle.</p>\n", encoding="utf-8")
            done = subprocess.run([BASH, str(TOOL), "check", str(path)], cwd=tmp,
                                  capture_output=True, text=True, encoding="utf-8",
                                  timeout=120, env=I18N_ENV)
        if done.returncode and "No module named 'bs4'" in done.stderr:
            self.skipTest(done.stderr.strip())
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("toggle=NO", done.stdout)


class LegacyListTests(unittest.TestCase):
    """Public pages must not inherit another workspace's bilingual exemptions."""

    def test_export_has_no_legacy_project_exemptions(self):
        listed = TOOL.parents[1] / "i18n-legacy.txt"
        rows = [line.split("\t") for line in listed.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")]
        self.assertEqual(rows, [], "the portable export must not inherit private project exemptions")


if __name__ == "__main__":
    unittest.main()
