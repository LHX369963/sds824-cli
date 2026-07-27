# SDS824 Validation

Validation date: 2026-07-27

## Instrument and wiring

```text
Siglent Technologies,SDS824X HD,SDS08A0XA08269,4.8.12.1.1.6.5
/dev/usbtmc2 (stable symlink /dev/sds824)
USB f4ec:1017
Firmware 4.8.12.1.1.6.5
DG1022 CH1 -> SDS824 C1
DG1022 CH2 -> SDS824 C2
```

The installed udev rule produced `root:plugdev 0660` on the USBTMC node and the
stable symlink without reconnecting the cable. Ordinary `sds824 info`, config,
measurements, screenshots, and waveform captures worked without sudo.

## Manual catalog audit

The reproducible Poppler extraction tool identifies 712 unique command blocks:

- 705 colon/IEEE/SENSE/CONFIGURE/MEASURE/READ/FETCH command blocks
- six WGEN commands whose syntax differs from SCPI
- one `MMETer` command for the SHS-only meter section

The first extraction incorrectly stopped at 705 because WGEN and `MMETer` use
unusual roots. An independent section/TOC review found the omission; the extractor
now asserts exactly 712 unique blocks and includes section 5.24. The packaged
catalog reports 650 query-capable and 670 write-capable entries.

Catalog inclusion means the guide command is addressable and auditable. It does
not claim that model-specific or licensed-option commands are installed on this
SDS824.

## Connected core evidence

- `*IDN?`, `*OPC?`, practical acquisition/channel/timebase/trigger snapshots,
  both channel configuration, PNG and BMP transfer responded over USBTMC.
- DG1022 outputs were configured to 1 kHz/2 Vpp on CH1 and 2 kHz/2 Vpp on CH2.
- The screenshot in `validation/baseline.png` shows both signals at 500 mV/div
  and 200 us/div.
- Simple frequency on C1 read approximately 1.000 kHz after the CLI correctly
  enabled the measurement display. C2 peak-to-peak read approximately 2.023 V.
- A WORD waveform transfer with 20,000 points and interval 100 covered 2 ms.
  Reconstructed C1 extrema were about -1.0104 V and +1.0000 V (2.0104 Vpp).
- Screenshot files validate as 1024x600 RGB PNG.

Unit suite status at this stage: 18 passed.

## Query sweep incident and safety correction

An early unconstrained sweep queried inactive cursor families and absent licensed
protocol families with a 750 ms timeout. After repeated unsupported queries the
instrument stopped servicing both USBTMC and socket SCPI; host USB authorization
cycling and USBDEVFS_RESET did not restore the embedded SCPI service. This requires
an instrument power cycle before remaining connected tests.

The incident produced two design changes:

1. `tools/live_audit.py` now halts after the first failed post-error `*IDN?` health
   probe instead of cascading failures.
2. `tools/parameter_matrix.py` uses feature context, restores original readback,
   and excludes unconfirmed licensed protocols.

The interrupted sweep is not presented as full command validation. Final connected
reports must show `complete: true` before they can support a completion claim.

## Parameter matrix plan

The state-restoring runner currently derives approximately:

- 181 core acquisition/channel/display/measurement/system/timebase values
- 66 math/function values
- 18 trigger-type values
- 240 contextual trigger parameter values
- 18 base IIC/SPI/UART/CAN/LIN decode values

Numeric scale, offset, skew, timebase, display intensity, and trigger-level grids
augment manual enums. Each record stores requested value, readback, acceptance,
timing, path indices, and completion state. Remaining matrices will be executed
after the instrument remote-control service is power-cycled.
