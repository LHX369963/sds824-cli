# SIGLENT SDS824 CLI

A dependency-free Linux USBTMC command-line client for the SIGLENT SDS824X HD.
It follows the practical structure of the adjacent DS1152E CLI while using the
new SDS programming model, 16-bit waveform preamble, stable udev naming, and a
machine-auditable catalog generated from the official CN11G programming guide.

Test instrument:

```text
Siglent Technologies,SDS824X HD,SDS08A0XA08269,4.8.12.1.1.6.5
USB f4ec:1017
```

## Coverage

- All **712 command blocks** in sections 5.1–5.25 of the CN11G guide
- 650 query-capable and 670 write-capable catalog entries
- Includes the six non-SCPI-style WGEN commands and SHS-only `MMETer` command
  for complete guide auditing; availability is not falsely implied on the SDS824
- `list`, `info`, `config`, `commands`, `get`, `set`, `action`, `raw`, `batch`,
  `measure`, `screenshot`, and `waveform` workflows
- BMP/PNG screenshots and BYTE/WORD waveform export to BIN, CSV, or JSON
- Reproducible catalog extraction, connected query auditing, and more than 500
  planned state-restoring parameter/readback matrix values
- No firmware upgrade, bootloader, reflash, unlock, or option-cracking support

## Install

Linux, Python 3.10+, and the kernel `usbtmc` driver are required.

```bash
git clone https://github.com/LHX369963/sds824-cli.git
cd sds824-cli
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test]'
```

Install the udev rule once:

```bash
sudo install -m 0644 udev/99-siglent-sds824-usbtmc.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usbmisc
```

Reconnect USB if necessary. The rule grants `plugdev`/desktop access and creates
`/dev/sds824`; the CLI still discovers the instrument by USB identity and serial
rather than relying on a changing `/dev/usbtmcN` number.

## Use

```bash
sds824 list
sds824 info
sds824 config

sds824 commands audit
sds824 commands list --section 5.22
sds824 commands show channel.n.scale

sds824 get channel.n.scale --n 1
sds824 set channel.n.scale 0.5 --n 1
sds824 get trigger.edge.source
sds824 set trigger.edge.source C1

sds824 measure freq --source C1 --json
sds824 measure all --source C2 --json
sds824 screenshot display.png
sds824 waveform c1.csv --source C1 --points 20000 --interval 100 --stop

sds824 raw ':TRIGger:STATus?'
sds824 batch commands.scpi
```

Path placeholders use the manual's names: `--n`, `--x`, `--m`, `--r`, `--d`,
and WGEN `--channel`. `commands show` displays exact syntax, parameter prose,
manual section, support class, and PDF/text location. Simple unambiguous enum values
are rejected before I/O when they are not declared by the guide. SHS-only and
optional/licensed paths are blocked by default; `--allow-unsupported` is required
when the corresponding external module or license is actually present.

Broad state-changing actions such as reset, autoset, recall, and default save
require `--yes`.

## Waveforms

The SDS824 returns a 346-byte `WAVEDESC` preamble. The CLI parses byte order,
8/16-bit representation, scale, offset, code words per division, probe factor,
sample interval, start, decimation interval, and horizontal delay. CSV/JSON
voltages use:

```text
volts = code * (vertical_scale * probe_factor / codes_per_div)
        - vertical_offset * probe_factor
```

A connected 20,000-point decimated capture of the DG1022 2 Vpp signal measured
approximately -1.010 V to +1.000 V, confirming the conversion path. Capture
restores waveform transfer settings and the previous acquisition run state.

## Verification

```bash
python -m pytest
python tools/extract_manual_catalog.py \
  docs/official/SDS800XHD_Series_ProgrammingGuide_CN11G.pdf \
  sds824_cli/manual_catalog.json
python tools/parameter_matrix.py core
```

Run connected matrices one group at a time (`core`, `function`, `trigger-types`,
`trigger`, `decode`). Unsupported licensed-option query sequences can wedge this
firmware's remote-control service; the tools exclude unknown FLEXray, CAN FD, IIS,
SENT, MIL-STD-1553, and Manchester options and stop after a failed health probe.
See [`docs/validation.md`](docs/validation.md) for evidence and limitations.

The fixed analog validation wiring is DG1022 CH1 → SDS824 C1 and DG1022 CH2 →
SDS824 C2.

The repository skill is in `skills/sds824-cli`. Install its discovery link with:

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
ln -sfn "$(pwd)/skills/sds824-cli" "${CODEX_HOME:-$HOME/.codex}/skills/sds824-cli"
```
