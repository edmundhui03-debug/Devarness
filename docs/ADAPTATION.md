# Devarness exports the harness without personal workspace content

> **2026-10-21** · Aster · `current`
>
> This is the current implementation and verification record. The
> owner requested a Claude Code centred harness combining Harness² and
> selected Codex/Pi capabilities, with MIT original code and no credentials
> or personal project folders.

## Scope keeps source while excluding private records

The export uses an explicit set of committed harness sources. It carries
Library tools, local skills, templates, deterministic tests and public
upstream pins. It excludes projects, books and personal notes, working
folders, task ledgers, review records, device state, runtimes, personal
Git configuration and source Git history. No home folder is an export
input. Original private evidence references in skills are replaced with
this scope record; bibliographic rule summaries keep their book titles
and page references without distributing the underlying collection.

## Neutral entry points prevent cross-installation leakage

The bootstrap reads the public manifest and checks the local core by
default. Explicit fetch downloads source only. Startup and client hooks
derive their own checkout; phone hooks and external discovery are off.
Optional local settings use the Devarness namespace. Personal clone
discovery requires an explicit opt-in. The old publishing helper cannot
rewrite a remote or publish inherited history. Client accounts, models
and credentials are absent.

## The release criteria are independently checkable

- Fresh Git history contains only this curated repository.
- The release scanner rejects synthetic credential and history controls.
- Tracked files and history contain no detected credentials.
- Private identifiers and original personal folders are absent.
- Bootstrap and hook controls run with an empty temporary user profile.
- Public manifest paths, URLs, pins and skill links pass containment checks.
- Portable core and deterministic tool checks pass.
- Third-party notices remain separate from the original-code MIT license.
- Windows, macOS and Linux CI results are recorded before broad claims.
- GitHub contents, commit and visibility match the reviewed local version.

## Local verification passed and hosted checks follow the private push

`partial` · local release gate passed; hosted checks and remote verification
follow the initial private push

Windows validation passed all 17 commands in `tools/check.py`, including
13 portable controls and the deterministic tool suites. Dashboard masking
tests passed separately: 46 Codex and 23 Claude tests. The local catalogue
contains 126 entries with zero diagnostics. Optional full-catalogue and
unavailable shell/runtime cases retain explicit test skips.

The staged-content scanner and Gitleaks 8.30.1 reported no findings. An
additional scan rejected the original user's private identifiers and
project-root names as forbidden content, and found none. The independent
review exposed index, metadata and symlink-text gaps; real Git negative
controls now prove those rejection paths. Historical credentials removed
from the current tree are tested too. No inherited Git history is used.

The review inspected 20 source/configuration files. Parent verification
closed its final symlink finding. This is a same-model independent read,
with no model-diversity claim. The portable edits remove private session
anecdotes and global launcher lookup; no paid behavioral comparison of
the adapted skills was run.

The first content scan correctly rejected existing synthetic credential
literals in masking tests. Those fixtures now construct the same values
at runtime, preserving the negative controls. No real credential is
intentionally included. Scanners supplement manual review and cannot
prove the absence of every possible secret. Optional client logins,
paid Harness² probes, MCP services and specialist applications have not
been run as part of the portable core checks. No measured improvement
over an upstream harness is claimed.
