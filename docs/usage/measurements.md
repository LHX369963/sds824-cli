# Measurements

```bash
sds824 measure freq --source C1 --json
sds824 measure pkpk mean freq edges --source C1
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

Physical channels start from their current
range. The CLI moves directly toward five vertical divisions, keeps a 2–7
division hysteresis band, and permits at most two coarser corrections after a
clipped result. It never restarts from the maximum range. If requested frequency
or period is unavailable, it tries at most three successively coarser 1-2-5
timebase settings in the same session.

Explicit `--vertical-scale` and `--time-scale` values are locked for that
measurement and are never changed by autoranging. Omit either option to leave

Physical-channel measurement attempts edge triggering at the measured midpoint
and polls the transient trigger state for a bounded interval. `Arm`, `Ready`, or
`Auto` alone do not fail a measurement: stable valid timing results are accepted.
If neither status nor timing data confirms acquisition, the CLI prints
`warning: trigger unconfirmed` without suppressing the measurements.
Use `--trigger keep` to retain an existing manual trigger; final aggregate
sampling still occurs, but the CLI does not alter or judge the trigger state.

For a known stable stimulus, `--vertical-scale`, `--time-scale`, and
`--coupling` explicitly prepare C1..C4 and measure in the same USBTMC session.
Each changed setting is read back, and the JSON includes the effective setup.
scale, timebase, and centered offset internally, avoiding caller calculations.

C1 through C4 are accepted sources. On firmware `4.8.12.1.1.6.5`, series-guide
measurements `RISE20T80` and `FALL80T20` time out, so the CLI blocks them.
`measure all` returns the other 49 measurements.

The CLI uses at most one temporary simple-measurement item instead of leaving
all 49 active; this avoids slowing later screenshots.
