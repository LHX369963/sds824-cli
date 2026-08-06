# Catalog and configuration

The catalog models all 712 command blocks in CN11G sections 5.1–5.25, including
650 query-capable and 670 write-capable entries. SHS-only, WGEN, and optional
entries remain catalogued without implying SDS824 availability.

```bash
sds824 commands show channel.n.scale
sds824 commands show channel.n.scale --verbose        # complete manual metadata
sds824 commands show channel.n.scale --json           # compact core fields
sds824 get channel.n.scale --n 1
sds824 set channel.n.scale 0.5 --n 1
sds824 set trigger.edge.source C1
sds824 batch commands.scpi
```

`commands show` prints one summary line by default. Add `--verbose` only when
manual descriptions and source metadata are needed; add `--pretty` to indent JSON.

Use the manual placeholder flags (`--n`, `--x`, `--m`, `--r`, `--d`, or WGEN
`--channel`). `commands show` gives the exact syntax and source location.

Queryable writes are read back. Simple invalid or firmware-rejected enums are
blocked before I/O. Use `--no-verify` only when intentional normalization is
understood, and `--allow-unsupported` only when the required module or licence
is known to be present.

Use `raw` only when no typed or catalog entry exists. Reset, autoset, recall,
and default save require `--yes`.
