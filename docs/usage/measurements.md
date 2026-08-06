# Measurements

```bash
sds824 measure freq --source C1 --json
sds824 measure pkpk mean freq edges --source C1 --json
sds824 measure all --source C2 --json                 # full diagnostics only
sds824 measure all --source C2 --include-unavailable --pretty
```

Multiple measurements and `all` produce compact one-line JSON by default.
Unavailable `****` values are omitted and counted; the two explicit options
restore the complete indented diagnostic output.

C1 through C4 are accepted sources. On firmware `4.8.12.1.1.6.5`, series-guide
measurements `RISE20T80` and `FALL80T20` time out, so the CLI blocks them.
`measure all` returns the other 49 measurements.

The CLI uses at most one temporary simple-measurement item instead of leaving
all 49 active; this avoids slowing later screenshots. A returned number is not
physical acceptance by itself. For range and clipping checks, use the Skill's
`references/analog-validation.md` only when analog validation is requested.
