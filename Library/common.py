"""What the Library's tools share: windowless subprocesses, Task Scheduler jobs,
the personal config folder and the pinned clones.

Each tool used to carry its own copy of the Task Scheduler XML and of the
pythonw lookup, and each had to remember CREATE_NO_WINDOW on its own; under
pythonw a call that forgot it flashes a console (owner rule, 2026-09-30).
Standard library only, Python 3.9 or later, so it loads under every tool's
interpreter, laya's venv included.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import NamedTuple
from xml.sax.saxutils import escape

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PERSONAL_REPOS = "personal-repos.txt"


class Clone(NamedTuple):
    path: str
    url: str
    pin: str
    sparse: str
    where: str          # file:line, for messages
    personal: bool      # from the owner's personal-repos.txt, not from git


def config_dir(home=None) -> Path:
    """The owner's personal values, one device, never in git: ntfy-topic,
    identifiers.txt and personal-repos.txt."""
    return Path(home or Path.home()) / ".config" / "devarness"


def pinned_clones(root, home=None) -> list:
    """Every pinned clone: Library/repos.txt's rows, then personal-repos.txt's.

    Both use one format, path<TAB>url<TAB>pin[<TAB>sparse dirs]; blank and #
    lines are skipped. A missing personal file adds nothing; an unreadable
    Library/repos.txt raises OSError, as reading it did before."""
    sources = [(Path(root) / "Library" / "repos.txt", "Library/repos.txt", False)]
    personal = config_dir(home) / PERSONAL_REPOS
    if os.environ.get("DEVARNESS_ALLOW_PERSONAL_REPOS") == "1" and personal.is_file():
        sources.append((personal, PERSONAL_REPOS, True))
    clones = []
    for path, label, is_personal in sources:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip() or line.startswith("#"):
                continue
            fields = (line.split("\t") + ["", "", ""])[:4]
            clones.append(Clone(fields[0], fields[1], fields[2].strip(), fields[3].strip(),
                                "%s:%d" % (label, number), is_personal))
    return clones


def run(argv, **kwargs) -> subprocess.CompletedProcess:
    """subprocess.run that never opens a console window on Windows."""
    kwargs.setdefault("creationflags", NO_WINDOW)
    return subprocess.run(argv, **kwargs)


def windowless_python(python=None) -> str:
    """pythonw.exe beside the interpreter when there is one, so a task opens no console."""
    python = Path(python or sys.executable)
    windowless = python.with_name("pythonw.exe")
    return str(windowless if windowless.is_file() else python)


def task_user() -> str:
    return "%s\\%s" % (os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", ""))


def logon_trigger(user: str) -> str:
    return "<LogonTrigger><Enabled>true</Enabled><UserId>%s</UserId></LogonTrigger>" % escape(user)


def task_xml(*, description: str, trigger: str, user: str, python: str, tool: str, arguments: str,
             limit: str = "PT0S", hidden: bool = False, restart: bool = False, cwd=None) -> str:
    """A Task Scheduler job for the signed-in user. Power, waking and time limits are
    spelled out, never defaulted; a service sets restart to come back after a failure."""
    folder = "<WorkingDirectory>%s</WorkingDirectory>" % escape(str(cwd)) if cwd else ""
    again = "\n    <RestartOnFailure><Interval>PT1M</Interval><Count>999</Count></RestartOnFailure>" if restart else ""
    return """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>{description}</Description></RegistrationInfo>
  <Triggers>{trigger}</Triggers>
  <Principals><Principal id="Author"><UserId>{user}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>LeastPrivilege</RunLevel></Principal></Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>{hidden}</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>{limit}</ExecutionTimeLimit>
    <Priority>7</Priority>{again}
  </Settings>
  <Actions Context="Author"><Exec><Command>{python}</Command><Arguments>"{tool}" {arguments}</Arguments>{folder}</Exec></Actions>
</Task>
""".format(description=escape(description), trigger=trigger, user=escape(user),
           hidden="true" if hidden else "false", limit=escape(limit), again=again, python=escape(python),
           tool=escape(tool), arguments=escape(arguments), folder=folder)


def create_task(name: str, xml: str) -> subprocess.CompletedProcess:
    """Register (or replace) the task. schtasks answers in the console code page."""
    with tempfile.TemporaryDirectory() as folder:
        job = Path(folder) / (name + ".xml")
        job.write_bytes(xml.encode("utf-16"))
        return run(["schtasks", "/Create", "/TN", name, "/XML", str(job), "/F"],
                   capture_output=True, text=True, errors="replace")
