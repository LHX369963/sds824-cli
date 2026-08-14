# Analog validation

Check every measured channel independently against its scale, offset, probe
ratio, and displayed grid. Reacquire after any relevant stimulus, DUT, channel,
acquisition, timebase, coupling, impedance, probe, or bandwidth change.

For multi-channel physical acceptance, use a scripted closed loop rather than
manually guessing or walking the ranges. Start each channel at a conservative
safe range, acquire extrema, calculate a 1-2-5 scale that satisfies the limits
below, apply it once, and reacquire to verify it. Repeat only when the verification
observes a new larger extreme. Never use one channel's result to range another.

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
query only that setting, use the actual readback for subsequent calculations,
and continue only if it is safe; do not blindly retry the same value or assume
the failed process left the prior setting intact.
