# Timeout recovery and safety boundary

The original `measure all` enabled all 49 simple measurement items. A screenshot
after two such runs took 11.45 s, beyond the former 10 s timeout; after clearing
items it took about 1.3 s. The corrected implementation uses at most one
temporary item, restores source/display state, and completed C1/C2 `measure all`
plus screenshot in 0.38 s, 0.42 s, and 1.34 s. C3/C4 queries and four-channel
configuration snapshot also passed.

Ten unattended cycles of C1/C2 `measure all`, PNG capture, and identity probe
had no failure: measurements 0.39–0.46 s, screenshots 1.34–1.39 s, probes
0.05–0.06 s. Empty `*IDN?` is an error. Screenshot queries default to 30 s and
retry once after USBTMC CLEAR. A forced 100 ms timeout made the immediate probe
fail; `sds824 recover` cleared the session, survived one failed probe, and
restored valid identity without power cycling. Optional `USBDEVFS_RESET` also
restored the same serial and firmware.

Generic catalog rendering now derives documented separators: `:FORMat:DATA
CUSTom,3` instead of space-separated values. Connected regression changed 3 to
14 then back to 3 with readback, toggled `FREQ,ON/OFF`, and finished with valid
identity on `SDS08A0XA08269`.

An early unconstrained sweep of inactive/absent licensed families made SCPI stop
over USB and Ethernet until a power cycle. Therefore acceptance uses feature
contexts, restores readable state, stops after failed health probe, and never
blindly queries unconfirmed FLEXray, CAN FD, IIS, SENT, MIL-STD-1553, or
Manchester paths. Static catalog auditing covers paths unsafe to assert present.
