# Screenshots and waveforms

```bash
sds824 screenshot display.png
sds824 waveform c1.csv --source C1 --interval 100 --stop
```

Screenshots support BMP and PNG. Waveforms support BYTE or WORD transfer to BIN,
CSV, or JSON; prefer WORD for high-resolution samples.

Screenshots default to a 30 s timeout; other commands default to 10 s. A global
`--timeout` overrides either value.

The 346-byte `WAVEDESC` supplies byte order, representation, scale, offset,
codes/division, probe factor, timing, and decimation. Voltage conversion is:

```text
volts = code * (vertical_scale * probe_factor / codes_per_div)
        - vertical_offset * probe_factor
```

BYTE samples are additionally weighted by `2^(adc_bits-8)`. Connected
20,000-point BYTE and WORD tests reconstructed about 2.00–2.02 Vpp.

Capture manages transfer settings itself; do not ask the user to save or restore
scope state. Omit `--points` to accept the instrument record length. If the scope
adjusts an explicit request, output reports both requested and actual points.
