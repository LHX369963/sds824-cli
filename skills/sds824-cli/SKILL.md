---
name: sds824-cli
description: Control and measure SIGLENT SDS824X HD oscilloscopes with the sds824 CLI.
---

# SDS824 CLI

Use `sds824/.venv/bin/sds824` from the instrument-cli
workspace. Execute the requested operation
directly; do not inspect, preserve, restore, or clean up unrelated state.
Do not scan processes or query preliminary state. Omit device selectors unless
the CLI reports ambiguity.

Common forms:

```bash
sds824/.venv/bin/sds824 measure freq pkpk mean --source C1
sds824/.venv/bin/sds824 get channel.n.scale --n 1
sds824/.venv/bin/sds824 set channel.n.scale 200mV --n 1
```

Prefer `measure`, `screenshot`, `waveform`, and typed `get`/`set`/`action`.
Use `commands show <name>` only for an unfamiliar typed command and `raw` only
when no maintained command exists. Request only the values the task needs.
`measure` still returns data after trigger or stability warnings; report the
warning and let the user decide whether to investigate further.
Explicit `--vertical-scale` or `--time-scale` locks that axis; omission keeps it automatic.
