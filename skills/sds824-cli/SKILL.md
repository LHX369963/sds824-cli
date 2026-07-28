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

- Always use the mature task-level interfaces first: `config`, `measure`, `screenshot`,
  `waveform`, and the catalog-backed `get` / `set` / `action` commands. Do not translate a
  supported operation into raw SCPI or an ad-hoc script.
- Inspect one known catalog entry with `commands show NAME` only when its arguments are unclear.
  Avoid dumping or reading the full `commands list` during routine instrument work; use a narrow
  name filter only when the catalog name cannot otherwise be identified. Reserve `commands audit`
  for explicit CLI coverage work.
- Read/write catalog entries: `get NAME`, `set NAME VALUE`, and `action NAME`; supply path indices such as `--n 2` or `--x 1`.
- Use `raw` only when the requested operation truly has no mature helper or catalog entry. State
  that gap before use, and never use `raw` to bypass validation, state restoration, or confirmation
  gates.
- Measure: `sds824 measure freq --source C1 --json` or `measure all`.
- Capture display: `sds824 screenshot capture.png`.
- Capture waveform: `sds824 waveform c1.csv --source C1 --points 20000 --interval 100 --stop`.
- Batch known SCPI: `sds824 batch commands.scpi`.

Waveform capture restores source, width, byte order, start, interval, point count, and prior run state. Prefer `WORD` for the SDS824's high-resolution samples.

## Validate the displayed range

Do not accept a numeric measurement merely because the CLI returned it. Compare the measured
maximum, minimum, and peak-to-peak value with the channel scale, offset, probe ratio, and actual
vertical grid. Apply this independently to every measured analog channel, including each channel
in a multi-channel test; a well-ranged channel does not validate any other channel.

For a stable periodic or otherwise amplitude-bearing waveform, target 2 to 6 vertical divisions
peak-to-peak. If it occupies less than 1 division, automatically select the next practical finer
scale, recenter with channel offset when necessary, and repeat until it occupies at least 2
divisions or the finest safe scale is reached. If it remains below 2 divisions, retain the
finest-range evidence and label the result resolution- or noise-limited. Do not infer a finer
scale from another channel, commanded amplitude, or an expected DUT gain: use that channel's
measured extrema.

If either peak is within 0.5 division of a screen edge, the waveform crosses an edge, or the
peak-to-peak value occupies more than 80% of the displayed height, automatically repeat at the
next practical coarser scale, normally with at least 2× more headroom. After changing scale or
offset, reacquire before measuring; never reuse measurements from the previous acquisition.
Keep both the original and reranged evidence, and use the valid finer- or wider-range result for
acceptance. Treat clipped, partly off-screen, or severely under-ranged results as diagnostic only.

For DC, noise, feedthrough, and near-zero measurements, do not blindly chase the peak-to-peak
target. First use offset to place the mean safely on screen, then choose the finest scale that
keeps all observed extrema at least 0.5 division from both edges. Record the scale, offset,
bandwidth limit, and a same-range baseline or noise floor; report an upper bound when the result
is not sufficiently above that baseline. Do not use Autoset for this process.

Re-evaluate every measured channel after any stimulus frequency, amplitude, offset, waveform,
DUT state, channel enablement, acquisition mode, timebase, probe ratio, coupling, impedance, or
bandwidth-limit change. Shared acquisition resources can change sample rate or record length in
multi-channel operation, but they never waive the per-channel vertical-range checks.

## Fix the CLI before continuing

Stop the DUT workflow immediately when an observed failure can come from CLI command rendering,
response parsing, capability modeling, timeout recovery, or state restoration. Reproduce the
fault with the smallest safe command, fix the CLI, add an offline regression test, and verify the
fix on the connected instrument. Restore instrument state and confirm `sds824 info` before
resuming DUT measurements. Use raw SCPI only to diagnose or establish ground truth; never treat a
raw workaround as completion of the CLI repair.

## Deliver repository changes

Every completed, sufficiently verified CLI, test, documentation, or Skill change must be committed
and pushed to the current branch's configured remote before reporting completion. Do not leave
finished work only in the local worktree, and do not include unrelated pre-existing changes. If
pushing fails, report the exact failure rather than presenting the change as fully delivered.

## Connected validation

Use `tools/parameter_matrix.py` for state-restoring enumeration matrices. Run one group at a time and inspect the JSON report before proceeding. Use `tools/live_audit.py` only with known feature context.

Do not blindly query licensed or absent protocol families. This firmware can stop servicing both USBTMC and socket SCPI after an unsupported query sequence, requiring an instrument power cycle. The matrix tool excludes optional FLEXray, CAN FD, IIS, SENT, MIL-STD-1553, and Manchester families until their options are confirmed.

For the fixed bench wiring, DG1022 CH1 feeds SDS824 C1 and DG1022 CH2 feeds SDS824 C2. Establish known generator outputs before analog acceptance, then verify frequency, amplitude, both channels, and exported waveform conversion.

## Guardrails

- Do not implement or invoke firmware update, bootloader, reflash, unlock, or option-cracking operations.
- Require explicit confirmation for reset, autoset, recall, and default-save operations.
- Prefer catalog commands because simple manual enums are validated before I/O.
- Treat a timeout as a failed test, then run `sds824 info`. Stop the sweep if the
  health probe fails and run `sds824 recover`; escalate to
  `sds824 recover --usb-reset` if CLEAR retries fail. Power-cycle only if both
  software recovery paths fail.
- Keep machine-readable reports under `validation/` and restore the final two-channel baseline.
