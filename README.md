# SIGLENT SDS824 CLI

Linux USBTMC CLI for the SIGLENT SDS824X HD. It provides typed measurement,
screen capture, waveform export, and catalog-backed SCPI access without firmware
or option modification.

## Install

Requires Linux, Python 3.10+, and the kernel `usbtmc` driver.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
sudo install -m 0644 udev/99-siglent-sds824-usbtmc.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usbmisc
```

Reconnect USB only if access remains unavailable. The rule creates `/dev/sds824`;
normal CLI use does not require `sudo`.

## Quick use

```bash
sds824 measure freq --source C1
sds824 screenshot display.png
sds824 waveform c1.csv --source C1 --interval 100 --stop
```

Known devices may be selected directly. `list`, `info`, `config`, broad audits,
and recovery are only for uncertainty, development, or faults.

## Read only what the task needs

- [Catalog and configuration](docs/usage/catalog.md)
- [Measurements](docs/usage/measurements.md)
- [Screenshots and waveforms](docs/usage/captures.md)
- [Selection and recovery](docs/usage/recovery.md)
- [Development and coverage](docs/usage/development.md)
- [Connected evidence](docs/validation.md)

The Codex skill is in [`skills/sds824-cli`](skills/sds824-cli).
