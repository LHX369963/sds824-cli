# Analog validation

Check every measured channel independently against its scale, offset, probe
ratio, and displayed grid. Reacquire after any relevant stimulus, DUT, channel,
acquisition, timebase, coupling, impedance, probe, or bandwidth change.

For stable amplitude-bearing signals, target 2–6 vertical divisions peak to
peak. If below 1 division, choose a finer safe scale and recenter. If a peak is
within 0.5 division of an edge, crosses an edge, or uses over 80% of display
height, choose a coarser scale with more headroom and reacquire.

Keep the original and reranged evidence. Treat clipped, off-screen, or severely
under-ranged results as diagnostic only. Never infer one channel's range from
another channel or from commanded amplitude.

For DC, noise, feedthrough, or near-zero results, center the mean and use the
finest scale that keeps all extrema at least 0.5 division from both edges. Record
scale, offset, bandwidth limit, and a same-range baseline; report an upper bound
when the result is not clearly above that baseline. Do not use Autoset.
