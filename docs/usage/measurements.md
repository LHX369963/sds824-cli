# Measurements

```bash
sds824 measure freq --source C1 --json
sds824 measure pkpk mean freq edges --source C1
sds824 measure freq pkpk mean --source C1 --expect-frequency 2kHz --expect-pkpk 1.5Vpp --expect-offset 0.2V
sds824 measure freq pkpk --source C1 --vertical-scale 200mV --time-scale 200us --coupling DC
sds824 measure all --source C2 --json                 # full diagnostics only
sds824 measure all --source C2 --include-unavailable --pretty
```

Multiple requested measurements print space-separated values in request order.
`all` and explicit `--json` use compact one-line JSON; `--pretty` indents it.

Range finding uses short internal groups. Final values are the median of five
groups separated by randomized 0.12–0.38 s intervals, so changing displays are
sampled rather than queried repeatedly from one frame. A concise warning names
metrics whose span exceeds the built-in stability threshold.

Without expectation/setup options, physical channels start from their current
range. The CLI moves directly toward five vertical divisions, keeps a 2–7
division hysteresis band, and permits at most two coarser corrections after a
clipped result. It never restarts from the maximum range. If requested frequency
or period is unavailable, it tries at most three successively coarser 1-2-5
timebase settings in the same session.

Physical-channel measurement also attempts edge triggering at the measured
midpoint. Failure prints `warning: trigger <status>` but does not suppress or
invalidate the returned measurements.

For a known stable stimulus, `--vertical-scale`, `--time-scale`, and
`--coupling` explicitly prepare C1..C4 and measure in the same USBTMC session.
Each changed setting is read back, and the JSON includes the effective setup.
Choose roughly 5 vertical divisions peak-to-peak and 1–3 displayed periods.
`--expect-frequency`, `--expect-pkpk`, and `--expect-offset` choose the 1-2-5
scale, timebase, and centered offset internally, avoiding caller calculations.

C1 through C4 are accepted sources. On firmware `4.8.12.1.1.6.5`, series-guide
measurements `RISE20T80` and `FALL80T20` time out, so the CLI blocks them.
`measure all` returns the other 49 measurements.

The CLI uses at most one temporary simple-measurement item instead of leaving
all 49 active; this avoids slowing later screenshots. A returned number is not
physical acceptance by itself. For range and clipping checks, use the Skill's
`references/analog-validation.md` only when analog validation is requested.
