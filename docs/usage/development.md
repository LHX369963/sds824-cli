# Development and coverage

```bash
python -m pytest
python tools/extract_manual_catalog.py \
  docs/official/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf \
  sds824_cli/manual_catalog.json
python tools/catalog_audit.py
python tools/parameter_matrix.py core
python tools/validation_summary.py
```

These are development workflows, not normal-use prerequisites. Run connected
matrices one focused group at a time: `core`, `function`, `trigger-types`,
`trigger`, or `decode`.

Unknown FLEXray, CAN FD, IIS, SENT, MIL-STD-1553, and Manchester queries can
wedge firmware `4.8.12.1.1.6.5`; tools exclude them until options are confirmed.
See [connected evidence](../validation.md) for limitations and fixed wiring.

Keep README and Skill as short navigation; put feature examples in `docs/usage/`.
