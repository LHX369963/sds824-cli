---
name: sds824-cli
description: Operate, inspect, test, or document one SIGLENT SDS824X HD oscilloscope with the dependency-free sds824 Linux USBTMC CLI, including discovery, SCPI catalog access, configuration, measurements, screenshots, waveform export, command coverage audits, and connected parameter matrices. Use for SDS824 hardware work, SDS800X HD protocol diagnosis, CLI development, or DG1022-to-SDS824 validation; exclude firmware upgrades and unguarded probing of absent licensed options.
---

# SDS824 CLI

Use the repository-local `.venv/bin/sds824` entry point when present, otherwise use `sds824` from `PATH`.

## Start safely

1. Run `sds824 list` and `sds824 info`; treat `*IDN?` as authoritative.
2. Expect USB `f4ec:1017`, model `SDS824X HD`, and an `SDS08...` serial.
3. Install `udev/99-siglent-sds824-usbtmc.rules` if access is denied. Never run routine captures with `sudo`.
4. Run `sds824 config` before changing state and preserve settings the task does not require changing.

The stable `/dev/sds824` symlink is convenient, but automatic discovery by USB identity and serial is preferred in reusable commands.

## Choose a workflow

- Inspect commands: `sds824 commands list`, `commands show NAME`, or `commands audit`.
- Read/write catalog entries: `get NAME`, `set NAME VALUE`, and `action NAME`; supply path indices such as `--n 2` or `--x 1`.
- Use `raw` only for a valid command that is not conveniently represented by the catalog. Do not use it to bypass confirmation gates.
- Measure: `sds824 measure freq --source C1 --json` or `measure all`.
- Capture display: `sds824 screenshot capture.png`.
- Capture waveform: `sds824 waveform c1.csv --source C1 --points 20000 --interval 100 --stop`.
- Batch known SCPI: `sds824 batch commands.scpi`.

Waveform capture restores source, width, byte order, start, interval, point count, and prior run state. Prefer `WORD` for the SDS824's high-resolution samples.

## Connected validation

Use `tools/parameter_matrix.py` for state-restoring enumeration matrices. Run one group at a time and inspect the JSON report before proceeding. Use `tools/live_audit.py` only with known feature context.

Do not blindly query licensed or absent protocol families. This firmware can stop servicing both USBTMC and socket SCPI after an unsupported query sequence, requiring an instrument power cycle. The matrix tool excludes optional FLEXray, CAN FD, IIS, SENT, MIL-STD-1553, and Manchester families until their options are confirmed.

For the fixed bench wiring, DG1022 CH1 feeds SDS824 C1 and DG1022 CH2 feeds SDS824 C2. Establish known generator outputs before analog acceptance, then verify frequency, amplitude, both channels, and exported waveform conversion.

## Guardrails

- Do not implement or invoke firmware update, bootloader, reflash, unlock, or option-cracking operations.
- Require explicit confirmation for reset, autoset, recall, and default-save operations.
- Prefer catalog commands because simple manual enums are validated before I/O.
- Treat a timeout as a failed test, then run `sds824 info`. Stop the sweep immediately if the health probe fails.
- Keep machine-readable reports under `validation/` and restore the final two-channel baseline.
