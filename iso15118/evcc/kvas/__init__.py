"""
K-VAS (Korea battery-data Value Added Service) — the EVCC-side "vehicle" half.

This package makes the Python EVCC behave like a real Korean EV once the SECC has
selected the value-added service in `ServiceDetailRes`: it TLV-encodes battery
records and pushes them over a plain TCP connection to the address/port/cadence the
SECC announced. See:

  Software/SmartyPluggerIotBoard/.claude/docs/kvas-vas-record-format.md   (wire format)
  Software/SmartyPluggerIotBoard/.claude/plans/2026-08-06-kvas-bench-bringup.md  §6
"""
