# Connected parameter profile

All five state-restoring reports completed:

| Group | Matrices | Values | Direct/semantic acceptance |
|---|---:|---:|---:|
| Core | 57 | 172 | 164 |
| Function | 15 | 64 | 64 |
| Trigger types | 1 | 18 | 18 |
| Trigger parameters | 82 | 240 | 228 |
| Decode, both buses | 70 | 228 | 224 |
| **Total** | **225** | **722** | **698** |

The 24 rejected/clamped observations are preserved in raw JSON reports and all
are represented in the CLI profile:

- SDS824 rejects series-guide `200M` bandwidth and `50 ohm` impedance choices.
- Display transparency clamps to 20–80%.
- Histogram ON and remote menu OFF read back unchanged.
- Event-count holdoff is ignored for nine trigger families.
- Video field count accepts 1 but ignores 2, 4, and 8.
- SPI decode length accepts through 32 and ignores 64/96 on both buses.
- Trigger serial bit-order `LSM` reads back as canonical `LSB`; the CLI treats
  this firmware spelling normalization as equivalent.

`../../validation/device-profile.json` consolidates totals and proves every observed
rejection is covered by a pre-I/O rule or numeric range. Generic queryable
one-argument `set` operations additionally use readback verification.
