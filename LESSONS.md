# Portable evidence prevents recurring harness failures

> **2026-10-21** · Aster · `current`
>
> These reusable lessons are principles for new projects. Personal
> incidents and project history were deliberately excluded. Verify each
> rule against the tool and client actually in use.

## Explicit sequencing prevents hook races

Matching hooks may run concurrently. Put dependent work in one
orchestrator and set explicit timeouts for bounded hooks.

## Fresh history and scoped commits protect private work

Export allowed source paths into a new repository. Exclude project
records, state and credentials; never push an old workspace's history
as a template. A nested Git repository is a dependency, not a gitlink.

## A passing checker needs a known bad control

Show that a security or acceptance check rejects the failure it claims
to detect. A command error and an untested integration are not passes.

## Neutral onboarding cannot reuse another installation

Resolve tools from this checkout and use a distinct local namespace.
Make downloads, home-folder links, global configuration and services
explicit. Source availability and runtime readiness are separate.
