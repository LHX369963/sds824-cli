# Selection and recovery

The validated unit is `SDS824X HD`, USB `f4ec:1017`, with an `SDS08...` serial.
Prefer a known device or serial. An explicit device path is inspected directly
without scanning other USBTMC nodes.

Normal sessions do not issue USBTMC CLEAR. Screenshots retry once with CLEAR only
after a timeout. Invoke `recover` only when the transport remains unusable; it
opens cleared sessions and requires a complete `*IDN?` response.

Use `recover --usb-reset` only as explicit fault escalation. It performs Linux
`USBDEVFS_RESET` and may require the supplied udev rule. Do not turn recovery,
identity queries, or health checks into normal follow-up steps.
