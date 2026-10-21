#!/usr/bin/env python3
"""Retired ECC-only profile command; no longer mutates user configuration.

Migration restores its old managed block before this replacement is deployed.
The original implementation remains in the old workspace's history and its
config backup is outside dev. Current discovery and rollback are documented in
Library/setup/LIBRARY_SETUP.md.
"""
raise SystemExit('Retired: use library search TASK; see Library/setup/LIBRARY_SETUP.md for rollback.')
