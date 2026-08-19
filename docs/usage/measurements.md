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

Range finding uses one compound-query group per decision. Final values are the
median of five groups separated by randomized 0.12–0.38 s intervals. A concise
warning identifies unstable requested metrics.

Physical channels start from their current range. The CLI targets five vertical
divisions and keeps a 2–7 division hysteresis band. A clipped waveform causes
continued upward expansion until clipping clears or the maximum range is
reached. For requested frequency or period, the hardware frequency counter—not
the simple period measurement—sets the timebase to roughly four displayed
cycles. The current timebase is retained inside a 2.5–6 cycle hysteresis band.

Explicit `--vertical-scale` and `--time-scale` values are locked for that
measurement and are never changed by autoranging. Omit either option to leave
that axis automatic.

Physical-channel measurement attempts edge triggering at the measured midpoint
and polls the transient trigger state for a bounded interval. `Arm`, `Ready`, or
`Auto` alone do not fail a measurement: stable valid timing results are accepted.
If neither status nor timing data confirms acquisition, the CLI prints
`warning: trigger unconfirmed` without suppressing the measurements.
Use `--trigger keep` to retain an existing manual trigger; final aggregate
sampling still occurs, but the CLI does not alter or judge the trigger state.

`--coupling` explicitly sets channel coupling for the measurement.

C1 through C4 are accepted sources. On firmware `4.8.12.1.1.6.5`, series-guide
measurements `RISE20T80` and `FALL80T20` time out, so the CLI blocks them.
`measure all` returns the other 49 measurements.

The CLI uses at most one temporary simple-measurement item instead of leaving
all 49 active; this avoids slowing later screenshots.
