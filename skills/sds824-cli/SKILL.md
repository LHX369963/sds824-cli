---
name: sds824-cli
description: Operate, inspect, test, or develop the SIGLENT SDS824X HD through the sds824 Linux USBTMC CLI, including measurements, screenshots, waveform export, catalog access, and connected validation; exclude firmware changes and unguarded licensed-option probing.
---

# SDS824 CLI

Use the repository-local `.venv/bin/sds824` when present. Resolve the repository
two levels above this Skill before opening linked files.

## Core workflow

- Select known hardware directly; use `list`, `info`, or `config` only when the
  device or configuration is uncertain.
- Prefer `measure`, `screenshot`, `waveform`, and catalog-backed
  `get`/`set`/`action`. Use `raw` only when no maintained interface exists.
- For targeted checks, request only measurements that can affect the next
  action; reserve `measure all` for full diagnostics and summarize normal output.
- Read only the relevant guide: [catalog](../../docs/usage/catalog.md),
  [measurements](../../docs/usage/measurements.md),
  [captures](../../docs/usage/captures.md), or
  [recovery](../../docs/usage/recovery.md).
- For physical analog acceptance, read
  [analog-validation.md](references/analog-validation.md).
- For CLI changes or connected coverage, read
  [development.md](references/development.md).

## Guardrails

- Do not request routine state snapshots, restoration, post-checks, discovery,
  CLEAR, recovery, or USB reset.
- Require confirmation for reset, autoset, recall, and default-save operations.
- Do not bypass catalog safety checks or probe absent licensed options.
- Do not implement firmware, bootloader, unlock, reflash, or option-cracking.
- Disable only stimuli enabled by the task; do not restore unrelated state.
