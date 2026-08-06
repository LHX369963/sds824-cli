# Catalog coverage

`tools/catalog_audit.py` independently re-extracts the CN11G PDF, compares it
with the packaged catalog, and renders every path template. The completed report
in `../../validation/catalog-audit.json` records:

- 712/712 unique command blocks rendered
- 650 query-capable and 670 write-capable blocks
- 582 SDS824 paths, 101 optional/licensed paths, and 29 other-model paths
- all sections 5.1–5.25, including six nonstandard WGEN blocks and SHS-only
  `MMETer`

Catalog coverage means every documented block can be inspected and addressed.
It does not claim unavailable hardware or licenses. Optional and other-model
paths require `--allow-unsupported`; firmware update/reflash functionality is
intentionally absent.
