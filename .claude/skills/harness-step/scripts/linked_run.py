"""Run a command in a worktree with the main checkout's clones and runtime linked in.

usage: linked_run.py WORKTREE CMD [ARGS...]
e.g.   linked_run.py . python3 Library/bin/dev-check --only library-check

A worktree holds tracked files only, so dev-check there fails on missing or stale
git-ignored state that says nothing about the branch. This moves the worktree's own
generated runtime aside, links the main checkout's folders in and copies its library
index (probe.link_clones), runs the command with its output captured, then unlinks and
restores both. The index is a copy so that `library refresh` here never writes main's.
"""
import os
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402

ASIDE = ".wt-aside"
# os.path.isjunction arrived in Python 3.12; before it, no folder is a junction to us.
is_junction = getattr(os.path, "isjunction", lambda _path: False)


def move_runtime_aside(tree):
    """Rename each real (not linked) runtime folder and seeded file, so link_clones can bring main's in."""
    moved = []
    for relative in probe.RUNTIME_DIRS + probe.SEEDED_FILES:
        path = tree / relative
        if not path.exists() or os.path.islink(path) or is_junction(path):
            continue
        path.rename(path.with_name(path.name + ASIDE))
        moved.append(path)
    return moved


def restore_runtime(moved):
    for path in moved:
        path.with_name(path.name + ASIDE).rename(path)


def relink_folder_links(tree):
    """Remake as folder links the tracked links Git for Windows made as file links.

    Git makes a link whose target is not checked out yet as a file link, which never
    reads as a folder even once the target exists. Git sees no change in the remade link.
    """
    if os.name != "nt":
        return  # elsewhere a symlink has no file or folder kind
    for row in probe.git("ls-files", "-s", cwd=tree).splitlines():
        mode, _, rest = row.partition(" ")
        if mode != "120000":
            continue
        link = tree / rest.split("\t", 1)[1]
        if not link.is_symlink() or os.lstat(link).st_file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY:
            continue
        target = os.readlink(link)
        if not (link.parent / target).is_dir():
            continue  # a link to a file, or to a clone this machine lacks
        link.unlink()
        os.symlink(target, link, target_is_directory=True)


def run(tree, command):
    moved = move_runtime_aside(tree)
    linked = []
    try:
        linked = probe.link_clones(tree)
        relink_folder_links(tree)
        # Capture explicitly: under CREATE_NO_WINDOW an inherited stdout can come back empty.
        done = subprocess.run(command, cwd=tree, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", creationflags=probe.NO_WINDOW)
    finally:
        probe.unlink_clones(tree, linked)
        restore_runtime(moved)
    return done.returncode, done.stdout + done.stderr


def main(argv):
    tree = Path(argv[0]).resolve()
    probe.ROOT = tree
    code, output = run(tree, argv[1:])
    print(output, flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
