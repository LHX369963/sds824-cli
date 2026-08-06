# Development and connected validation

If rendering, parsing, capability modelling, or transport handling may be wrong,
reproduce the smallest safe failure, fix the CLI, add an offline regression test,
and resume the requested task after verification. Do not use raw SCPI as a
permanent workaround.

Use `tools/parameter_matrix.py` and `tools/live_audit.py` only for explicit
coverage work. Never blindly query licensed or absent protocol families. The
fixed bench wiring is DG1022 CH1 to SDS824 C1 and CH2 to C2.

Run the relevant tests after changes. Commit and push only completed, verified,
related changes; report a push failure rather than claiming delivery.
