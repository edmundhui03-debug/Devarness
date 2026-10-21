"""publish-check fails on a personal value in a file dev would publish, and never prints it.

Run: python3 Library/tests/test_publish_check.py

Each test builds a small git repository and a scratch home, plants one value,
and runs Library/publish-check.py against them. Every planted value is built
at run time, so this file carries none of the things it looks for.
"""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "Library" / "publish-check.py"
AT = chr(64)
SLASH = chr(92)
PERSONAL_EMAIL = "a.person" + AT + "gmail.com"
IDENTIFIER = "Zq-Planted-Name-7"
TOPIC = "topic-" + "q7x9k2m4"
BOOKS = "Some-" + "Many-" + "Books"
USER = "alice"


def check(files, identifiers=None, topic=None, untracked=()):
    """Run publish-check on a fresh repository holding files; return (code, output)."""
    with tempfile.TemporaryDirectory() as tmp:
        repo, home = Path(tmp) / "repo", Path(tmp) / "home"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=60)
        for rel, text in {**files, **dict(untracked)}.items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "--", *files], check=True, timeout=60)
        config = home / ".config" / "devarness"
        config.mkdir(parents=True)
        if identifiers is not None:
            (config / "identifiers.txt").write_text("\n".join(identifiers) + "\n", encoding="utf-8")
        if topic is not None:
            (config / "ntfy-topic").write_text(topic + "\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "DEVARNESS_NTFY_TOPIC"}
        env.update(HOME=str(home), USERPROFILE=str(home), PYTHONIOENCODING="utf-8")
        done = subprocess.run([sys.executable, str(CHECK), str(repo)], capture_output=True, text=True,
                              encoding="utf-8", env=env, timeout=120)
        return done.returncode, done.stdout + done.stderr


class Fails(unittest.TestCase):
    def assertFails(self, text, secret, **config):
        code, output = check({"notes/a.md": "fine\n" + text + "\n"}, **config)
        self.assertEqual(code, 1, output)
        self.assertIn("notes/a.md:2", output)
        self.assertNotIn(secret, output)
        return output

    def test_a_planted_email_fails_and_is_never_printed(self):
        self.assertFails("write to " + PERSONAL_EMAIL, PERSONAL_EMAIL, identifiers=[])

    def test_a_planted_identifier_from_the_config_fails_and_is_never_printed(self):
        output = self.assertFails("by " + IDENTIFIER.lower() + " on Monday", IDENTIFIER.lower(),
                                  identifiers=[IDENTIFIER])
        self.assertNotIn(IDENTIFIER, output)

    def test_the_ntfy_topic_fails_and_is_never_printed(self):
        self.assertFails("topic = " + TOPIC, TOPIC, identifiers=[], topic=TOPIC)

    def test_a_home_path_naming_a_user_fails(self):
        for path in ("C:" + SLASH + "Users" + SLASH + USER + SLASH + "dev", "C:/Users/" + USER + "/dev",
                     "/c/Users/" + USER + "/dev", "/Users/" + USER + "/dev", "/home/" + USER + "/dev"):
            with self.subTest(path=path):
                self.assertFails("cd " + path, USER, identifiers=[])

    def test_the_book_repository_name_fails(self):
        self.assertFails("clone " + BOOKS, BOOKS, identifiers=[])

    def test_without_an_identifiers_file_the_generic_checks_still_run_and_say_so(self):
        output = self.assertFails(PERSONAL_EMAIL, PERSONAL_EMAIL)
        self.assertIn("identifiers.txt", output)
        self.assertIn("generic checks only", output)

    def test_an_untracked_file_about_to_be_added_is_checked_too(self):
        code, output = check({"a.md": "fine\n"}, identifiers=[], untracked={"new.md": PERSONAL_EMAIL + "\n"})
        self.assertEqual(code, 1, output)
        self.assertIn("new.md:1", output)


class Passes(unittest.TestCase):
    def assertPasses(self, text, **config):
        code, output = check({"notes/a.md": text + "\n"}, **dict({"identifiers": [IDENTIFIER]}, **config))
        self.assertEqual(code, 0, output)
        return output

    def test_example_and_noreply_addresses_pass(self):
        self.assertPasses("owner" + AT + "example.com, Co-Authored-By: x <noreply" + AT + "anthropic.com>, "
                          "1+me" + AT + "users.noreply.github.com, git" + AT + "github.com:owner/dev.git")

    def test_placeholder_home_paths_pass(self):
        self.assertPasses("C:" + SLASH + "Users" + SLASH + "<user>" + SLASH + "dev, %USERPROFILE%" + SLASH +
                          "dev, /home/$USER/dev, /Users/you/dev, ~/.config/devarness, grep '/home/[a-z]' | grep -v /home/node")

    def test_a_build_record_is_a_warning_not_a_failure(self):
        code, output = check({"Setup/superpowers/specs/x.md": "by " + PERSONAL_EMAIL + "\n",
                              "Setup/AGENT_LEDGER.md": "at /home/" + USER + "/x\n"}, identifiers=[])
        self.assertEqual(code, 0, output)
        self.assertIn("warning", output)
        self.assertIn("Setup/superpowers/specs/x.md:1", output)
        self.assertIn("Setup/AGENT_LEDGER.md:1", output)
        self.assertNotIn(PERSONAL_EMAIL, output)

    def test_a_projects_evidence_folder_is_a_build_record(self):
        code, output = check({"PRDs and Specs/003 Tool/evidence/run.json": "at /home/" + USER + "/x\n"},
                             identifiers=[])
        self.assertEqual(code, 0, output)
        self.assertIn("warning", output)
        code, output = check({"PRDs and Specs/003 Tool/SPEC.html": "at /home/" + USER + "/x\n"}, identifiers=[])
        self.assertEqual(code, 1, output)

    def test_the_history_files_may_cite_commit_hashes(self):
        self.assertPasses("made from the old workspace at ab9a8c1 (`c45c24b`)")
        code, output = check({"LESSONS.md": "by " + PERSONAL_EMAIL + "\n"}, identifiers=[])
        self.assertEqual(code, 1, output)        # a hash may be cited there; a personal value may not


if __name__ == "__main__":
    unittest.main()
