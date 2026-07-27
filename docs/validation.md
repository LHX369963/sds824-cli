# SDS824 Validation

Validation date: 2026-07-27

## Instrument and wiring

```text
Siglent Technologies,SDS824X HD,SDS08A0XA08269,4.8.12.1.1.6.5
/dev/usbtmc3 (stable symlink /dev/sds824)
USB f4ec:1017
DG1022 CH1 -> SDS824 C1: 1 kHz, 2 Vpp
DG1022 CH2 -> SDS824 C2: 2 kHz, 2 Vpp
```

The installed udev rule gives the USBTMC node `root:plugdev 0660` permissions.
Discovery uses USB identity and serial rather than the changing node number.
Routine operation, captures, and validation run as the desktop user without sudo.

## Complete programming-guide catalog

`tools/catalog_audit.py` independently re-extracts the CN11G PDF, compares it
with the packaged catalog, and renders every path template. The completed report
in `validation/catalog-audit.json` records:

- 712/712 unique command blocks rendered
- 650 query-capable and 670 write-capable blocks
- 582 SDS824 paths, 101 optional/licensed paths, and 29 other-model paths
- all sections 5.1–5.25, including six nonstandard WGEN blocks and SHS-only
  `MMETer`

Catalog coverage means every documented block can be inspected and addressed.
It does not claim unavailable hardware or licenses. Optional and other-model
paths require `--allow-unsupported`; firmware update/reflash functionality is
intentionally absent.

## Connected parameter profile

All five state-restoring reports completed:

| Group | Matrices | Values | Direct/semantic acceptance |
|---|---:|---:|---:|
| Core | 57 | 172 | 164 |
| Function | 15 | 64 | 64 |
| Trigger types | 1 | 18 | 18 |
| Trigger parameters | 82 | 240 | 228 |
| Decode, both buses | 70 | 228 | 224 |
| **Total** | **225** | **722** | **698** |

The 24 rejected/clamped observations are preserved in the raw JSON reports and
all are represented in the CLI profile:

- SDS824 rejects series-guide `200M` bandwidth and `50 ohm` impedance choices.
- Display transparency clamps to 20–80%.
- Histogram ON and remote menu OFF read back unchanged.
- Event-count holdoff is ignored for nine trigger families.
- Video field count accepts 1 but ignores 2, 4, and 8.
- SPI decode length accepts through 32 and ignores 64/96 on both buses.
- Trigger serial bit-order token `LSM` reads back as canonical `LSB`; the CLI
  treats that firmware spelling normalization as equivalent.

`validation/device-profile.json` consolidates totals and proves every observed
rejection is covered by a pre-I/O rule or numeric range. Generic queryable
one-argument `set` operations additionally use readback verification.

## Analog, measurement, and waveform evidence

Both fixed DG1022 paths were exercised. `measure all` returned 49 values per
channel. Representative readings were:

- C1: about 999.84 Hz, 2.016 Vpp, 0.707 V RMS
- C2: about 2000.09 Hz, 2.024 Vpp, 0.709 V RMS

The CN11G measurement names `RISE20T80` and `FALL80T20` time out on this firmware,
while a following `*IDN?` remains healthy. They are blocked explicitly and are
omitted from `measure all`.

The connected waveform matrix captured 20,000 samples for C1/C2 in BYTE and WORD
widths and exercised BIN, CSV, and JSON writers. Reconstructed peak-to-peak
values were 2.00–2.02 V in all four source/width combinations. This exposed and
fixed a BYTE conversion detail: WAVEDESC retains the 16-bit codes/div field, so
BYTE codes require a `2^(adc_bits-8)` weight. See
`validation/waveform-matrix.json`.

Screenshots in `validation/baseline.png`, `validation/measure-on.png`, and
`validation/final-baseline.png` are 1024x600 RGB PNG evidence. The final image
shows the restored two-channel 1 kHz/2 kHz bench baseline with measurement
display disabled.

## Screenshot timeout and unattended recovery

The original `measure all` implementation enabled all 49 supported simple
measurement items and left them active. A screenshot issued immediately after
two such measurements took 11.45 s, exceeding the former global 10 s timeout;
the same screenshot took about 1.3 s after clearing the measurement items.
The corrected implementation queries all values with at most one temporary item,
restores the source/display state, and completed C1/C2 `measure all` plus a
screenshot in 0.38 s, 0.42 s, and 1.34 s respectively. C3/C4 frequency queries
and the four-channel configuration snapshot also passed.
Ten unattended regression cycles then ran C1/C2 `measure all`, PNG capture, and
an identity health probe without a failure. Measurements took 0.39–0.46 s,
screenshots 1.34–1.39 s, and health probes 0.05–0.06 s.

An empty `*IDN?` response is now an error rather than a successful JSON object
with blank fields. Screenshot queries default to 30 s and retry once after
USBTMC CLEAR. A forced 100 ms read timeout made the immediate health probe fail;
`sds824 recover` cleared the session, survived one failed probe, and restored a
valid identity without power cycling. Linux `USBDEVFS_RESET` was also exercised
as the optional escalation path, after which the same serial and firmware were
read successfully.

## Multi-argument catalog rendering

The generic CLI originally joined positional values with spaces. The SDS824
silently ignored the second value in `:FORMat:DATA CUSTom 3`, returned success
at the transport layer, and remained at `CUSTOM,14`; the manual requires
`:FORMat:DATA CUSTom,3`. Catalog rendering now derives the separator from the
documented syntax, preserves WGEN `LOAD`/`PLRT` literals, and compares
comma-separated readback fields. Connected regression changed the digit from 3
to 14 and back to 3 with verified readback, enabled and disabled the `FREQ`
simple-measurement item using `FREQ,ON/OFF`, and finished with a valid identity
probe on serial `SDS08A0XA08269`.

## Safety finding

An early unconstrained sweep of inactive and absent licensed families caused the
embedded SCPI service to stop responding over both USB and Ethernet until the
scope was power-cycled. Therefore connected validation uses feature contexts,
restores readable state, stops after a failed health probe, and never blindly
queries unconfirmed FLEXray, CAN FD, IIS, SENT, MIL-STD-1553, or Manchester paths.
Static full-catalog auditing is used for paths that cannot safely be asserted
present.
