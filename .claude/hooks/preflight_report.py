"""Start preflight report: turns the shell probes into the banner and context.

Called by preflight.sh with its probe results as arguments. It was a
here-document until 2026-09-14; macOS /bin/bash 3.2 writes those to a
temporary file, so a read-only sandbox gave python3 no program and the
preflight printed nothing. Keep it a file.
"""
import json, os, stat, sys, shutil
from pathlib import Path

docker, root, node_v, markitdown, prompt_master, page_skill, cship, codex = sys.argv[1:9]


def here(rel):
    """rel under the dev root, absolute and with forward slashes: a hint that works from any folder and shell."""
    return (Path(root) / rel).as_posix()

enabled = {}
for p in ("~/.claude/settings.json",
          os.path.join(root, ".claude/settings.json"),
          os.path.join(root, ".claude/settings.local.json")):
    try:
        enabled.update(json.load(open(os.path.expanduser(p))).get("enabledPlugins") or {})
    except Exception:
        pass

def on(short):
    return any(name.split("@")[0] == short and val for name, val in enabled.items())

# Off by the owner's choice on 2026-10-07, so neither is listed: the n8n
# skills were removed and Matt Pocock's plugin is off, its three kept skills
# linked from Harness/skills. A plugin listed here degrades the banner when off.
PLUGINS = [
    ("superpowers",       "process gates"),
    ("codex",             "codex from claude"),
]

lines, degraded = ["START ready", "Claude plugin configuration (not Codex tool availability):"], []
if on('ecc'):
    degraded.append('ECC remains enabled in Claude settings — remove the overriding enable flag; specialists are library-only')
for short, role in PLUGINS:
    ok = on(short)
    if not ok:
        degraded.append(f"{short} not loaded")
    lines.append(f"  {short:<18}{'enabled' if ok else 'MISSING':<12}{role}")

# File inventory only: cache presence does not establish MCP or hook readiness.
# Every row here pairs with degraded.append like the rest of the file — a
# MISSING that never degrades reads as READY. And the whole block is guarded:
# Path.home() raises with HOME unset and .glob() raises on an unreadable
# ~/.codex, either of which used to kill the heredoc and leave preflight
# exiting 0 with empty stdout — the silent success the start check forbids.
lines.append("Codex files (restart to load; hook trust and MCP connection are separate):")
try:
    codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
    for package, market in (("superpowers", "superpowers-dev"),):
        manifests = list((codex_home / "plugins/cache" / market / package).glob("*/.codex-plugin/plugin.json"))
        if not manifests:
            degraded.append(f"Codex plugin {package} not cached — run python3 {here('Harness/codex-setup.py')}")
        lines.append(f"  {package:<18}{'cached' if manifests else 'MISSING':<12}native Codex plugin")
    skills = list((Path(root) / ".agents/skills").glob("*/SKILL.md"))
    if not skills:
        degraded.append(f"no Codex skills in .agents/skills — run python3 {here('Harness/codex-setup.py')}")
    lines.append(f"  {'dev skills':<18}{len(skills):<12}Codex .agents/skills entries")
    # Glob counts hide orphaned links and partial installs. Name each unusable
    # entry without following vendor trees or changing the installation.
    def skill_problem(entry):
        """Why a skill entry is unusable, or '' when it is fine or not a skill at all."""
        if entry.is_symlink():
            if not (entry / 'SKILL.md').is_file():
                return 'missing (link target not restored)'
            # On Windows a link made before its target existed is a file link;
            # Python 3.12's is_dir() raises PermissionError on it, and a client
            # listing folders may skip it.
            if os.name == "nt" and not os.lstat(entry).st_file_attributes & stat.FILE_ATTRIBUTE_DIRECTORY:
                return 'a file link to a folder, made before its target existed: recreate it'
            return ''
        return 'no SKILL.md' if entry.is_dir() and not (entry / 'SKILL.md').is_file() else ''
    for base in ('.agents/skills', '.claude/skills'):
        directory = Path(root) / base
        if directory.is_dir():
            for entry in sorted(directory.iterdir()):
                problem = skill_problem(entry)
                if problem:
                    degraded.append(f"Incomplete dev skill: {base}/{entry.name} — {problem}; "
                                    "repair its source/link or request approval to retire it")
    # update-tools's last run on this device, read from its state file so the
    # read-only Codex path sees what is pending without a fetch (owner, 2026-09-24).
    state_file = Path(root) / ".claude/hooks/update-tools.state"
    if state_file.is_file():
        try:
            last = json.loads(state_file.read_text(encoding="utf-8")).get("last_run", {})
            when = (last.get("at") or "never")[:16]
            # The same two states session_start.py degrades on: a rollback that
            # restored the old pin is a note, not a fault.
            stuck = [r for r in last.get("results", []) if r.get("state") in ("stuck", "rollback failed")]
            if stuck:
                degraded.append("update-tools left %d tool(s) stuck or not restored — run update-tools status" % len(stuck))
            lines.append(f"  {'update-tools':<18}{('ATTENTION' if stuck else 'ran ' + when):<12}"
                         "clones to their newest: daily, or update-tools apply")
        except (OSError, ValueError, AttributeError):
            lines.append(f"  {'update-tools':<18}{'UNREADABLE':<12}state file")
    else:
        lines.append(f"  {'update-tools':<18}{'never run':<12}clones to their newest: daily, or update-tools apply")
except Exception as exc:
    degraded.append(f"Codex inventory could not be read: {type(exc).__name__}: {exc}")
    lines.append(f"  {'codex files':<18}{'UNREADABLE':<12}{type(exc).__name__}")
lines.append("  Verify loaded skills in the client; configured plugins are not session exposure.")
library_files = ('Harness/library.py', 'Harness/bin/library', 'Harness/library-sources.json',
                 'Harness/library-policy.json',
                 '.claude/skills/library/SKILL.md', '.agents/skills/library/SKILL.md')
library_ready = all((Path(root) / name).is_file() for name in library_files)
# The index, not the files: without it every prompt's picks are silently empty.
library_state, library_note = 'MISSING', 'offline discovery and per-prompt picks'
if not library_ready:
    degraded.append(f"Library files missing — run python3 {here('Harness/setup-library.py')} --install")
else:
    try:
        import importlib.util
        library_spec = importlib.util.spec_from_file_location('dev_library', here('Harness/library.py'))
        library_module = importlib.util.module_from_spec(library_spec)
        library_spec.loader.exec_module(library_module)
        index = library_module._load_index(Path(root) / '.claude/hooks/library/index.json')
        if index['diagnostics']:
            library_state = 'DEGRADED'
            degraded.append("the library index has %d diagnostic(s): search refuses it — library check, "
                            "then library refresh" % len(index['diagnostics']))
        elif library_module._stale(index):
            library_state, library_note = 'stale', 'sources changed since it was built: library refresh'
        else:
            library_state = 'ready'
    except Exception as exc:
        degraded.append(f"no usable library index ({type(exc).__name__}): per-prompt picks are empty — "
                        "run library refresh")
lines.append(f"  {'library':<18}{library_state:<12}{library_note}")
vercel_ready = (Path(root) / 'Harness/.runtime/vercel-skills/node_modules/skills/bin/cli.mjs').is_file()
lines.append(f"  {'vercel-find':<18}{'installed' if vercel_ready else 'MISSING':<12}approved keyword search per prompt; no auto-install")
if not vercel_ready:
    degraded.append(f"Vercel discovery runtime missing: python3 {here('Harness/setup-vercel-skills.py')} --install")

lines.append(f"  {'docker':<18}{docker:<12}{'local inventory; daemon health not verified' if docker != 'absent' else ''}")

for source in ('reverse-skill', 'rea'):
    present = (Path(root) / 'Harness' / source / 'README.md').is_file()
    lines.append(f"  {source:<18}{'present' if present else 'MISSING':<12}"
                 "pinned reverse-tool source; owner-named targets only, see its library entry")
    if not present:
        degraded.append(f"{source} pinned source missing — run {here('Harness/bootstrap.sh')}")

# Clone-installed tools. Neither is a plugin, so neither shows in the block
# above; both are checked by presence rather than by asking them their version.
lines.append(f"  {'markitdown':<18}{markitdown:<12}doc to markdown, md-pages for page marks")
lines.append(f"  {'prompt-master':<18}{prompt_master:<12}prompt authoring")
lines.append(f"  {'bilingual-page':<18}{page_skill:<12}bilingual EN/\u7cb5 html")
md_skill = sys.argv[10] if len(sys.argv) > 10 else "absent"
lines.append(f"  {'md-format':<18}{md_skill:<12}markdown house format; md-format check")
# Pinned Archify inventory only: no renderer, browser or network on startup.
try:
    import runpy
    archify = runpy.run_path(str(Path(root) / 'Harness/bin/archify'))
    archify_issues = archify['problems'](Path(root))
    for rel in ('.claude/skills/archify/SKILL.md', '.agents/skills/archify/SKILL.md'):
        if not (Path(root) / rel).is_file():
            archify_issues.append('missing agent adapter')
except Exception as exc:
    archify_issues = [type(exc).__name__ + ': Archify inventory unavailable']
lines.append(f"  {'archify':<18}{'MISSING' if archify_issues else 'ready':<12}pinned technical diagrams; archify")
if archify_issues:
    degraded.append('Archify: ' + '; '.join(archify_issues))

# Ponytail uses the existing instruction path; no extra hooks or idle worker.
try:
    ponytail = runpy.run_path(str(Path(root) / 'Harness/ponytail-check.py'))
    ponytail_issues = ponytail['problems'](Path(root))
except Exception as exc:
    ponytail_issues = [type(exc).__name__ + ': Ponytail inventory unavailable']
lines.append(f"  {'ponytail':<18}{'MISSING' if ponytail_issues else 'ready':<12}full; instruction-based coding and diff review")
if ponytail_issues:
    degraded.append('Ponytail: ' + '; '.join(ponytail_issues))

# TieItUp loads Ponytail first; with a file missing, agents fall back to Ponytail.
# Changed Ponytail skills or a harness past the benchmark is stale, shown but never DEGRADED (owner, 2026-10-15).
try:
    tieitup = runpy.run_path(str(Path(root) / 'Harness/tieitup-check.py'))
    tieitup_issues = tieitup['problems'](Path(root))
    tieitup_stale = [] if tieitup_issues else tieitup['stale'](Path(root))
    tieitup_open = 0 if tieitup_issues else tieitup['proposals'](Path(root))
except Exception as exc:
    tieitup_issues, tieitup_stale, tieitup_open = [type(exc).__name__ + ': TieItUp inventory unavailable'], [], 0
tieitup_note = '; '.join(tieitup_stale) or 'Ponytail first, then the book rules; tieitup check'
if tieitup_open:
    tieitup_note += ' · %d proposals (tieitup learn)' % tieitup_open
lines.append(f"  {'tieitup':<18}{'MISSING' if tieitup_issues else 'stale' if tieitup_stale else 'ready':<12}{tieitup_note}")
if tieitup_issues:
    degraded.append('TieItUp: ' + '; '.join(tieitup_issues)
                    + '; agents fall back to Ponytail (.claude/skills/ponytail/SKILL.md)')

for name, relative in (
    ('Docling OCR', 'docling/.venv/lib'),
    ('browser CLI', 'playwright-cli/node_modules/@playwright/cli/playwright-cli.js'),
):
    runtime = Path(root) / 'Harness/.runtime' / relative
    present = runtime.exists()
    if name == 'Docling OCR':
        env_root = Path(root) / 'Harness/.runtime/docling/.venv'
        present = (any(env_root.glob('lib/python*/site-packages/docling/__init__.py')) or
                   (env_root / 'Lib/site-packages/docling/__init__.py').is_file())
    shared = all((Path(root) / base / 'browser-docs/SKILL.md').is_file()
                 for base in ('.claude/skills', '.agents/skills'))
    ok = present and shared
    lines.append(f"  {name:<18}{'installed' if ok else 'MISSING':<12}shared Peter/Aster; task-driven, see {here('Harness/SHARED_BROWSER_DOCS.md')}")
    if not ok:
        degraded.append(name + f" incomplete — run python3 {here('Harness/setup-browser-docs.py')} --install")
try:
    ua_pin = next(line.split('\t')[2] for line in (Path(root) / 'Harness/repos.txt').read_text().splitlines()
                  if line.startswith('Harness/Understand-Anything\t'))
    ua_root = Path(root) / 'Harness/.runtime/understand-anything' / ua_pin / 'understand-anything-plugin'
    ua_policy_path = Path(root) / 'Harness/library-policy.json'
    ua_policy = json.loads(ua_policy_path.read_text()) if ua_policy_path.is_file() else {}
    ua_library_only = (ua_policy.get('entries', {}).get('dev:skill:understand', {})
                       .get('mode') == 'library-only')
    ua_instructions = ((Path(root) / 'Harness/Understand-Anything/understand-anything-plugin'
                        / 'skills/understand/SKILL.md').is_file() if ua_library_only else
                       all((Path(root) / c / 'skills/understand/SKILL.md').is_file()
                           for c in ('.claude', '.agents')))
    ua_ok = ((ua_root / 'packages/core/dist/index.js').is_file()
             and (ua_root / 'packages/viewer/dist/index.html').is_file()
             and ua_instructions)
except (OSError, StopIteration, IndexError, ValueError, AttributeError, TypeError):
    ua_ok = False
diagram_ok = (all((Path(root) / c / 'skills/diagram-design/SKILL.md').is_file() for c in ('.claude', '.agents'))
              and (Path.home() / '.diagram-design/profiles/house.md').is_file()
              and any((Path(root) / 'Harness/.runtime/diagram-tools' / p).is_file()
                      for p in ('bin/python', 'Scripts/python.exe'))
              and (Path(root) / 'Harness/bin/diagram').is_file())
lines.append(f"  {'understand':<18}{'prepared' if ua_ok else 'MISSING':<12}pinned instructions + local viewer; analyze on request")
lines.append(f"  {'diagram-design':<18}{'prepared' if diagram_ok else 'MISSING':<12}shared skill + house profile; diagram doctor")
anthropic_design_ok = all((Path(root) / 'Harness/anthropic-design/skills' / name / 'SKILL.md').is_file()
                          for name in ('canvas-design', 'theme-factory'))
lines.append(f"  {'anthropic-design':<18}{'source only' if anthropic_design_ok else 'absent':<12}library-only static art and theme references; no Canva integration")
ngspice = shutil.which('ngspice')
lines.append(f"  {'ngspice':<18}{'installed' if ngspice else 'unavailable':<12}PCB simulation binary; ngspice-setup --check for circuit proof")
fds = shutil.which('fds')
if os.name == 'nt':
    # fds-setup installs NIST's macOS build only; on Windows FDS is the one PyroSim bundles.
    bundled = sorted(Path(os.environ.get('ProgramFiles', r'C:\Program Files')).glob('PyroSim*/fds/fds.exe'))
    fds_state = 'installed' if fds else 'via PyroSim' if bundled else 'n/a'
    fds_note = ("PyroSim's bundled FDS; put its fds folder on PATH (pyrosim skill)" if bundled and not fds
                else "FDS comes with PyroSim (licensed), installed by hand" if not fds
                else 'NIST FDS for PyroSim cases')
else:
    fds_state = 'installed' if fds else 'unavailable'
    fds_note = 'NIST FDS/Smokeview 6.10.1 for PyroSim cases; fds-setup --check runs a tiny fire'
lines.append(f"  {'fds':<18}{fds_state:<12}{fds_note}")
pyrosim_ok = all((Path(root) / c / 'skills/pyrosim/SKILL.md').is_file() for c in ('.claude', '.agents'))
lines.append(f"  {'pyrosim':<18}{'prepared' if pyrosim_ok else 'MISSING':<12}shared skill; PyroSim itself is Windows-only")
if not pyrosim_ok:
    degraded.append(f"pyrosim skill link missing — see {here('Harness/INSTALL.md')}")
# Cheap local inventory; these lines do not execute lessons, models or servers.
def learning_runtime(repo):
    try:
        pin = next(line.split('\t')[2] for line in (Path(root) / 'Harness/repos.txt').read_text().splitlines()
                   if line.startswith('Harness/' + repo + '\t'))
        return Path(root) / 'Harness/.runtime' / repo / pin
    except (OSError, StopIteration, IndexError):
        return None
def has_interpreter(venv):
    # A venv built inside WSL keeps bin/python as a Linux symlink that Windows
    # cannot open; is_file() raises on it, so count it as absent instead.
    for p in ('bin/python', 'Scripts/python.exe'):
        try:
            if (venv / p).is_file():
                return True
        except OSError:
            pass
    return False
learn_root = learning_runtime('learn-claude-code')
learn_ok = bool(learn_root and all((learn_root / p).is_file() for p in
    ('installation.json', 'source/s01_agent_loop/code.py', 'source/s17_goal_loop/code.py'))
    and has_interpreter(learn_root / '.venv')
    and (Path(root) / 'Harness/bin/learn-claude').is_file())
support_ok = all((Path(root) / c / 'skills/task-support/SKILL.md').is_file() for c in ('.claude', '.agents'))
# Harness/setup-learn-claude.py refuses anything but POSIX (upstream imports fcntl),
# so elsewhere the lab is not applicable rather than missing, as new-device says.
learn_applicable = os.name == 'posix'
if learn_applicable or learn_ok:
    lines.append(f"  {'learn-claude-code':<18}{'prepared' if learn_ok else 'MISSING':<12}local lessons; live API not probed")
else:
    lines.append(f"  {'learn-claude-code':<18}{'n/a':<12}local lessons need POSIX; use WSL on Windows")
# laya's MCP server starts with each agent session; without the runtime it
# only fails to start, so a device that has not installed it is not DEGRADED.
laya_root = Path(root) / 'Harness/.runtime/laya'
laya_ok = (laya_root / 'install.json').is_file() and has_interpreter(laya_root / '.venv')
lines.append(f"  {'laya':<18}{'prepared' if laya_ok else 'not set up':<12}"
             f"{'typed decisions for both agents over MCP' if laya_ok else 'python3 ' + here('Harness/setup-laya.py') + ' --install'}")
# notify's phone alerts need the ntfy topic, kept per device outside git. Without
# it an agent's work is unaffected, so the device is not DEGRADED.
ntfy_ok = bool(os.environ.get('DEVARNESS_NTFY_TOPIC')) or (Path.home() / '.config/dev/ntfy-topic').is_file()
lines.append(f"  {'notify':<18}{'prepared' if ntfy_ok else 'not set up':<12}"
             f"{'phone alerts when Peter, Aster or May finishes' if ntfy_ok else 'write the topic to ~/.config/devarness/ntfy-topic'}")
# May's client. Its login is the owner's, so a device without it is not DEGRADED.
pi_ok = bool(shutil.which('pi')) or any((Path.home() / '.pi/agent/bin' / name).is_file()
                                        for name in ('pi', 'pi.exe', 'pi.cmd'))
lines.append(f"  {'pi':<18}{'installed' if pi_ok else 'absent':<12}May's client (Pi); its own login is the owner's")
# books' Markdown of the library, built on each device and never synced. A
# device without it is not DEGRADED: it has the PDFs, or no library at all.
try:
    import importlib.util
    books_spec = importlib.util.spec_from_file_location('books_engine', str(Path(root) / 'Harness/books.py'))
    books_engine = importlib.util.module_from_spec(books_spec)
    books_spec.loader.exec_module(books_engine)
    shelf = books_engine.summary(books_engine.LIBRARY, books_engine.OUT)
    if not shelf['library']:
        books_row = ('n/a', 'no library clone on this device')
    elif shelf['converted'] == shelf['readable'] and not shelf['building']:
        books_row = ('ready', '%d books as Markdown in Books/text; never synced' % shelf['converted'])
    elif shelf['converted'] or shelf['building']:
        books_row = ('building', '%d of %d books; books status' % (shelf['converted'], shelf['readable']))
    else:
        books_row = ('not built', 'books install && books start')
except Exception as error:
    books_row = ('UNREADABLE', 'books state: %s' % type(error).__name__)
lines.append(f"  {'books':<18}{books_row[0]:<12}{books_row[1]}")
lines.append(f"  {'task-support':<18}{'prepared' if support_ok else 'MISSING':<12}shared explicit-use skill; no hooks")
# Informational only: video-study needs system binaries, so it may not turn
# another device's banner DEGRADED.
watch_ok = bool(all(shutil.which(t) for t in ('yt-dlp', 'ffmpeg', 'ffprobe'))
    and (Path(root) / 'Harness/bin/video-study').is_file())
lines.append(f"  {'video-study':<18}{'ready' if watch_ok else 'unavailable':<12}video study: transcript, contact sheets, exact frames")
if not all((learn_ok or not learn_applicable, support_ok)):
    degraded.append(f"agent learning setup incomplete — see {here('Harness/AGENT_LEARNING_TOOLS.md')}")
if not ua_ok or not diagram_ok:
    degraded.append(f"knowledge/diagram setup incomplete — run python3 {here('Harness/knowledge-tools-sync.py')} --install")
statusline = sys.argv[9] if len(sys.argv) > 9 else "missing"
lines.append(f"  {'statusline':<18}{('ready' if statusline == 'on PATH' else 'MISSING'):<12}the statusLine command; bare name via ~/.local/bin")
if statusline != "on PATH":
    degraded.append(f"statusline is not on PATH — the statusline will be blank; run {here('Harness/bootstrap.sh')}")
lines.append(f"  {'cship':<18}{cship:<12}statusline, cship.toml at the root")
lines.append(f"  {'codex cli':<18}{codex:<12}" + ("/codex:review, /codex:rescue" if codex == "ready" else "run: codex login"))
if markitdown != "ready":
    degraded.append(f"markitdown: {markitdown} — install the uv tool by hand, see {here('Harness/INSTALL.md')}")
if prompt_master != "ready":
    degraded.append(f"prompt-master missing — run python3 {here('Harness/setup-prompt-master.py')} --install")
if page_skill != "ready":
    degraded.append(f"bilingual-page: {page_skill} — new HTML cannot get its EN/Cantonese toggle")
if md_skill != "ready":
    degraded.append(f"md-format: {md_skill} — new Markdown cannot be checked against the house format")
if cship != "ready":
    degraded.append(f"cship: {cship} — the statusline will render short or not at all")
if codex == "no login":
    degraded.append("codex is installed but not logged in — run `codex login`; the /codex: commands fail without it")
elif codex == "absent":
    degraded.append("codex CLI missing — npm install -g @openai/codex")

def too_old(v):
    try:
        maj, minor = (int(x) for x in v.split(".")[:2])
    except Exception:
        return False
    return (maj, minor) < (20, 19)

if node_v:
    stale = too_old(node_v)
    lines.append(f"  {'node':<18}{('TOO OLD' if stale else 'ok'):<12}{node_v}")
    if stale:
        degraded.append(f"node {node_v} is below 20.19, some MCP servers will not start")

# The 05:00 dev-check on the Windows PC (dev-check --install-daily, owner decision
# 2026-09-24) leaves its verdict here; a device that never ran it has no row.
daily = Path(root) / ".claude/hooks/dev-check-daily/latest.json"
if daily.is_file():
    try:
        last = json.loads(daily.read_text(encoding="utf-8"))
        passed = last.get("exit") == 0
        where = ".claude/hooks/dev-check-daily/" + str(last.get("log", ""))
        lines.append(f"  {'dev-check daily':<18}{'passed' if passed else 'FAILED':<12}"
                     f"{last.get('finished_at', '?')}; {where}")
        if not passed:
            degraded.append("the last daily dev-check failed: "
                            + (", ".join(last.get("failed") or []) or "see its log") + " — " + where)
    except (OSError, ValueError, AttributeError) as exc:
        degraded.append(f"the daily dev-check verdict is unreadable: {type(exc).__name__}")

# Forty-odd rows saying "ready" cost ~600 est. tokens in every session and tell
# the reader nothing they can act on. When nothing is wrong the banner is a
# count and a pointer; the moment anything is, every row comes back so the
# problem is never hidden behind a summary. Silence is still not allowed —
# the banner must prove the start check ran — so the healthy
# form still states how many tools were checked. `start-check --check --text`, which
# the count points at, sets DEVARNESS_START_ALL and gets every row.
if not degraded and not os.environ.get("DEVARNESS_START_ALL"):
    checked = sum(1 for line in lines if line.startswith("  ") and line.strip())
    # Keep the first line: session_start.py rejects a banner that does not open
    # with it, which is how this condensation broke the gate when first written.
    lines = [lines[0], "%d inventory rows checked; runtime health and client tool exposure are separate — start-check --check --text lists them" % checked]
lines.append("")
lines.append("Router: CLAUDE.md")
if degraded:
    lines.append("Degraded: " + "; ".join(degraded))
    lines.append("See .claude/hooks/README.md")

# What every session pays for, so it carries only what the routers cannot.
# Claude loads CLAUDE.md automatically and Codex loads AGENTS.md, so restating
# the Markdown, bilingual and tool-ownership rules here charged every session
# twice for the same sentences (~2,000 chars). What stays is what AGENTS.md
# does NOT carry — it has no grill rule and no ownership table, and an
# instruction to "go and read CLAUDE.md" is not a guarantee that Codex did.
ctx = ("The start check is active for this workspace. Read CLAUDE.md (Claude), "
       "AGENTS.md then CLAUDE.md (Codex), or .pi/APPEND_SYSTEM.md then CLAUDE.md (Pi) "
       "before working: the router holds "
       "the tool-ownership table, the house format for Markdown and HTML, and "
       "the rule that superpowers owns process gates. Find a tool through "
       "library rather than doing the work by hand, and convert a binary document "
       "with md-pages before reading it. "
       "PETER is the Claude agent, ASTER the Codex agent and MAY the Pi agent. Follow "
       "the active client's identity rather than assuming this banner names "
       "its caller. Aster may be dispatched unasked for "
       "review and verification, but never take a finding on trust, Aster's or any agent's — "
       "verify each one against the repository and say which did not hold. "
       "GRILL FIRST, ALWAYS: before any non-trivial design, implementation or "
       "change, run the grill-first interview — every open question at once, "
       "numbered, with a recommended answer — and do not act until the owner "
       "confirms. Exempt: trivial edits, direct questions, work already grilled "
       "this session. "
       + ("For every coding task, load .claude/skills/ponytail/SKILL.md "
          "and apply full mode through the final diff review; correctness gates remain authoritative."
          if tieitup_issues else
          "For every coding task, load .claude/skills/tieitup/SKILL.md, which loads Ponytail first, "
          "apply full mode and run tieitup check in the final diff review; correctness gates remain authoritative.")
)

print(json.dumps({"systemMessage": "\n".join(lines), "additionalContext": ctx}))
