"""Exercise the actual statusline with explicit sample data, without API calls."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

root = Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix="cship-preview-") as tmp:
    data = {
        "cwd": str(root),
        "workspace": {"current_dir": str(root), "project_dir": str(root)},
        "transcript_path": str(Path(tmp) / "preview.jsonl"),
        "model": {"id": "preview", "display_name": "DISPLAY TEST (sample data)"},
        "effort": {"level": "high"},
        "cost": {"total_cost_usd": 1.23},
        "context_window": {"context_window_size": 200000, "used_percentage": 25},
        "rate_limits": {
            "five_hour": {"used_percentage": 20, "resets_at": int(time.time()) + 7200},
            "seven_day": {"used_percentage": 35, "resets_at": int(time.time()) + 172800},
        },
    }
    print("CSHIP PREVIEW — synthetic sample values, not live session usage", flush=True)
    command = [str(root / "Harness/bin/statusline")]
    if os.name == "nt":
        # Windows cannot execute the bash wrapper directly (WinError 193); run it
        # through the Git Bash that `statusline --preview` was started from.
        command.insert(0, shutil.which("bash") or "bash")
    result = subprocess.run(command, input=json.dumps(data), text=True, timeout=10)
    sys.exit(result.returncode)
