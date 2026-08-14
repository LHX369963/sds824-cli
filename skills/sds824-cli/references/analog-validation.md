# Analog validation

Check every measured channel independently against its scale, offset, probe
ratio, and displayed grid. Reacquire after any relevant stimulus, DUT, channel,
acquisition, timebase, coupling, impedance, probe, or bandwidth change.

For multi-channel physical acceptance, use the shortest bounded two-pass
procedure: take one conservative coarse acquisition per channel, calculate each
channel's 1-2-5 scale, apply the settings once, then take one verification
acquisition. Make at most one corrective range change when verification fails.
Do not add repeated statistical sampling, convergence loops, or worst-case
searches unless the task explicitly requires them or the signal is intermittent.
Never use one channel's result to range another.

Keep one USBTMC session open for the entire multi-step measurement and close it
once at the end. Request all needed measurements for one channel together and
group independent writes. Do not launch a new CLI process or reopen USBTMC for
every sample, setting, channel, stage, or readback. If the public subcommands
cannot express the workflow in one session, use a maintained persistent-session
helper rather than a subprocess loop.

For stable amplitude-bearing signals, target 2–6 vertical divisions peak to
peak. If below 1 division, choose a finer safe scale and recenter. If a peak is
within 0.5 division of an edge, crosses an edge, or uses over 80% of display
height, choose a coarser scale with more headroom and reacquire.

Do not save an acceptance screenshot or result until its range passes validation.
Treat clipped, off-screen, or severely under-ranged acquisitions as transient
diagnostics, exclude them from reported results, and remove them after a valid
replacement unless they are explicitly needed to troubleshoot the instrument.
Never infer a range from commanded amplitude.

For DC, noise, feedthrough, or near-zero results, center the mean and use the
finest scale that keeps all extrema at least 0.5 division from both edges. Record
scale, offset, bandwidth limit, and a same-range baseline; report an upper bound
when the result is not clearly above that baseline. Do not use Autoset.

Do not guess offset polarity. On the SDS824, the displayed center voltage is the
negative of `channel.n.offset`; center a positive DC level near `V` with an
offset near `-V`. First acquire at a coarse DC range, calculate the mean, apply
the centered offset, then validate on-screen before selecting the fine range.

Catalog `set` verification may reject a requested scale or offset when the
instrument quantizes it even though the write took effect. On such an error,
query only that setting and accept the actual readback when it safely centers the
trace. Do not chase the exact measured mean with repeated offset writes: offset
quantization depends on the vertical scale, and centering needs display headroom,
not numerical equality. Do not assume the failed process left the prior setting
intact.
