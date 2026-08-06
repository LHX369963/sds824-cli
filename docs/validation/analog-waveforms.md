# Analog, measurement, and waveform evidence

Fixed validation wiring:

```text
Siglent Technologies,SDS824X HD,SDS08A0XA08269,4.8.12.1.1.6.5
/dev/usbtmc3 (stable symlink /dev/sds824); USB f4ec:1017
DG1022 CH1 -> SDS824 C1: 1 kHz, 2 Vpp
DG1022 CH2 -> SDS824 C2: 2 kHz, 2 Vpp
```

The udev rule gives the node `root:plugdev 0660`. Discovery uses USB identity
and serial, not changing node numbers; ordinary use runs as the desktop user.

Both fixed DG1022 paths were exercised. `measure all` returned 49 values per
channel: C1 about 999.84 Hz, 2.016 Vpp, 0.707 V RMS; C2 about 2000.09 Hz,
2.024 Vpp, 0.709 V RMS. CN11G `RISE20T80`/`FALL80T20` time out on this firmware
but a following `*IDN?` remains healthy, so they are blocked and omitted.

The waveform matrix captured 20,000 C1/C2 samples in BYTE/WORD and BIN/CSV/JSON.
Reconstructed peak-to-peak values were 2.00–2.02 V in every combination. BYTE
conversion uses the WAVEDESC 16-bit codes/div field with `2^(adc_bits-8)` weight;
see `../../validation/waveform-matrix.json`.

`../../validation/baseline.png`, `../../validation/measure-on.png`, and
`../../validation/final-baseline.png` are 1024x600 RGB PNG evidence. The final
image shows restored 1 kHz/2 kHz channels with measurement display disabled.
