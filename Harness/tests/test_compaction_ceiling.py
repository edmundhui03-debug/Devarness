"""Every agent in dev compacts at or below the router's 300K ceiling.

The router's rule "Sessions compact at 300K active context tokens" lives in
each client's settings, and a setting drifts when a model's window grows: Pi
1.3.0 widened openai-codex/gpt-6.1-sol from 272K to 500K, and with no override
May compacted near 484K (found 2026-10-17). Pi compacts once the context passes
the window minus reserveTokens (Pi 1.3.0 docs/compaction.md). The windows come
from Pi's own model store when this device has Pi, so a later widening fails
here, and from KNOWN_WINDOWS where it does not.
"""
from pathlib import Path
import json
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CEILING = 300_000
PI_DEFAULT_RESERVE = 16_384  # Pi 1.3.0 docs/settings.md, compaction.reserveTokens
# Read from Pi 1.3.0's model store on 2026-10-21, for devices without Pi.
KNOWN_WINDOWS = {"openai-codex/gpt-6.1-sol": 500_000}
PI_STORE = Path.home() / ".pi" / "agent" / "models-store.json"
CODEX_PROFILES = [ROOT / ".codex" / "config.toml", ROOT / ".codex" / "astra-low.config.toml"]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def pi_models_dev_runs():
    """May's default model and every provider/model a Pi worker line names."""
    settings = read_json(ROOT / ".pi" / "settings.json")
    models = {settings["defaultProvider"] + "/" + settings["defaultModel"]}
    brief = (ROOT / ".pi" / "APPEND_SYSTEM.md").read_text(encoding="utf-8")
    models.update(re.findall(r"--model ([\w.-]+/[\w.-]+)", brief))
    return models


def pi_window(model):
    """The window Pi itself uses, else the one recorded here, else None."""
    if PI_STORE.exists():
        provider, _, name = model.partition("/")
        for entry in read_json(PI_STORE).get(provider, {}).get("models", []):
            if entry.get("id") == name:
                return entry["contextWindow"]
    return KNOWN_WINDOWS.get(model)


def pi_trigger(settings, model, window):
    """Where Pi compacts: a model override, else the ordinary reserve, else Pi's default."""
    compaction = settings.get("compaction", {})
    override = compaction.get("modelOverrides", {}).get(model, {})
    reserve = override.get("reserveTokens", compaction.get("reserveTokens", PI_DEFAULT_RESERVE))
    return window - reserve


class EveryClientCompactsAtTheCeiling(unittest.TestCase):
    def test_claude_compacts_at_the_ceiling(self):
        window = read_json(ROOT / ".claude" / "settings.json").get("autoCompactWindow")
        self.assertIsNotNone(window, ".claude/settings.json sets no autoCompactWindow")
        self.assertLessEqual(window, CEILING)

    def test_every_codex_profile_compacts_at_the_ceiling(self):
        for profile in CODEX_PROFILES:
            found = re.search(r"^model_auto_compact_token_limit\s*=\s*(\d+)",
                              profile.read_text(encoding="utf-8"), re.MULTILINE)
            self.assertIsNotNone(found, f"{profile.name} sets no model_auto_compact_token_limit")
            self.assertLessEqual(int(found.group(1)), CEILING, profile.name)

    def test_pi_compaction_is_on(self):
        settings = read_json(ROOT / ".pi" / "settings.json")
        self.assertIsNot(settings.get("compaction", {}).get("enabled", True), False)

    def test_every_pi_model_dev_runs_compacts_at_the_ceiling(self):
        settings = read_json(ROOT / ".pi" / "settings.json")
        for model in sorted(pi_models_dev_runs()):
            window = pi_window(model)
            self.assertIsNotNone(window, f"{model}: look up its window and add it to KNOWN_WINDOWS")
            self.assertLessEqual(
                pi_trigger(settings, model, window), CEILING,
                f"{model} has a {window} window: set compaction.modelOverrides"
                f' "{model}".reserveTokens to {window - CEILING} in .pi/settings.json')


class TheCheckCatchesTheSettingThatBrokeIt(unittest.TestCase):
    def test_no_override_on_a_500k_window_fails(self):
        self.assertGreater(pi_trigger({"compaction": {"enabled": True}}, "p/m", 500_000), CEILING)

    def test_an_override_wins_over_the_ordinary_reserve(self):
        settings = {"compaction": {"reserveTokens": 16_384,
                                   "modelOverrides": {"p/m": {"reserveTokens": 200_000}}}}
        self.assertEqual(pi_trigger(settings, "p/m", 500_000), CEILING)


if __name__ == "__main__":
    unittest.main()
