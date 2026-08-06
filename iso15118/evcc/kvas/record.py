"""
K-VAS "Battery Data Exchange" TLV record — encode (and decode, for tests/logging).

Wire format authority:
Software/SmartyPluggerIotBoard/.claude/docs/kvas-vas-record-format.md

This is a third independent implementation of the same tag table, alongside the
MCU's KvasVasChannel.c (parser) and the bench simulator's kvas_ev_sim.py (encoder +
parser). It is *not* imported from either — this package lives in a separate repo
from the MCU firmware, so sharing source across the two isn't practical. Keep the
three in sync by hand if the format ever changes; the checked-in reference records
(vas_reference_records.txt, mirrored in tests/evcc/kvas/test_record.py's golden
vector) are the cross-repo oracle that would catch a drift.

Rules (format doc §2-§4):
  tag(1) len(1) value        -- every tag except 0xA7
  tag(1) len(2) value        -- 0xA7 only, len is big-endian u16
  Groups A..H, in order, at most one tag per group. Two legal compositions:
    A B C D E F G H   -- Case 1 / Case 2 Start-Stop  ("full" record)
    A B C             -- Case 2 Periodic / Case 3     ("periodic" record)
  All multi-byte integers big-endian.
"""

import struct
from dataclasses import dataclass
from typing import Optional

TAG_A1_TIMESTAMP = 0xA1
TAG_A2_VIN = 0xA2
TAG_A3_SOC = 0xA3
TAG_A4_SOH = 0xA4
TAG_A5_PACK_CURRENT = 0xA5
TAG_A6_PACK_VOLTAGE = 0xA6
TAG_B7_CELL_VOLT_MAXMIN = 0xB7
TAG_B8_CELL_TEMP_MAXMIN = 0xB8

VIN_LENGTH = 17


class RecordEncodeError(ValueError):
    """Raised when the caller's values cannot be represented on the wire."""


def _tlv(tag: int, value: bytes) -> bytes:
    if len(value) > 255:
        raise RecordEncodeError(f"tag 0x{tag:02X} value too long for a 1-byte length")
    return struct.pack("!BB", tag, len(value)) + value


def encode_record(
    *,
    timestamp: int,
    vin: str,
    soc_pct: float,
    soh_pct: float = None,
    current_a: float = None,
    voltage_v: float = None,
    cell_v_max: float = None,
    cell_v_min: float = None,
    temp_c_max: int = None,
    temp_c_min: int = None,
    periodic: bool = False,
) -> bytes:
    """Encode one record. `periodic=True` emits Case 2 Periodic ("A B C" only) and
    ignores everything past soc_pct; `periodic=False` (default) requires all of
    soh_pct..temp_c_min and emits the full Case 1 frame ("A B C D E F G H").

    Scale factors (format doc §3): SoC x0.5, SoH x1, current x0.1, voltage x0.1,
    cell V x0.02, temperature x1 with a -40 degC offset.
    """
    vin_bytes = vin.encode("ascii")
    if len(vin_bytes) != VIN_LENGTH:
        raise RecordEncodeError(
            f"VIN must be exactly {VIN_LENGTH} ASCII chars, got {len(vin_bytes)}"
        )

    out = b""
    out += _tlv(TAG_A1_TIMESTAMP, struct.pack("!I", timestamp))
    out += _tlv(TAG_A2_VIN, vin_bytes)
    out += _tlv(TAG_A3_SOC, struct.pack("!B", round(soc_pct / 0.5)))

    if periodic:
        return out

    if None in (
        soh_pct,
        current_a,
        voltage_v,
        cell_v_max,
        cell_v_min,
        temp_c_max,
        temp_c_min,
    ):
        raise RecordEncodeError(
            "periodic=False (Case 1) needs soh_pct/current_a/voltage_v/cell_v_max/"
            "cell_v_min/temp_c_max/temp_c_min"
        )

    out += _tlv(TAG_A4_SOH, struct.pack("!B", round(soh_pct)))
    out += _tlv(TAG_A5_PACK_CURRENT, struct.pack("!H", round(current_a / 0.1)))
    out += _tlv(TAG_A6_PACK_VOLTAGE, struct.pack("!H", round(voltage_v / 0.1)))
    out += _tlv(
        TAG_B7_CELL_VOLT_MAXMIN,
        struct.pack("!BB", round(cell_v_max / 0.02), round(cell_v_min / 0.02)),
    )
    out += _tlv(
        TAG_B8_CELL_TEMP_MAXMIN, struct.pack("!BB", temp_c_max + 40, temp_c_min + 40)
    )
    return out


@dataclass
class DecodedRecord:
    timestamp: int
    vin: str
    soc_pct: float
    periodic: bool
    soh_pct: Optional[float] = None
    current_a: Optional[float] = None
    voltage_v: Optional[float] = None
    cell_v_max: Optional[float] = None
    cell_v_min: Optional[float] = None
    temp_c_max: Optional[int] = None
    temp_c_min: Optional[int] = None


def decode_record(data: bytes) -> DecodedRecord:
    """Decode one record, for tests and DEBUG logging only - never used to validate
    what we send, since that would just check the encoder against itself."""
    pos = 0

    def need(n):
        nonlocal pos
        if pos + n > len(data):
            raise RecordEncodeError(
                f"truncated record at offset {pos}, need {n} more bytes"
            )

    tag, length = data[pos], data[pos + 1]
    if tag != TAG_A1_TIMESTAMP or length != 4:
        raise RecordEncodeError(
            f"expected [A1] timestamp, got tag 0x{tag:02X} len {length}"
        )
    need(2 + 4)
    (timestamp,) = struct.unpack("!I", data[pos + 2 : pos + 6])
    pos += 6

    tag, length = data[pos], data[pos + 1]
    if tag != TAG_A2_VIN or length != VIN_LENGTH:
        raise RecordEncodeError(f"expected [A2] VIN, got tag 0x{tag:02X} len {length}")
    need(2 + VIN_LENGTH)
    vin = data[pos + 2 : pos + 2 + VIN_LENGTH].decode("ascii")
    pos += 2 + VIN_LENGTH

    tag, length = data[pos], data[pos + 1]
    if tag != TAG_A3_SOC or length != 1:
        raise RecordEncodeError(f"expected [A3] SoC, got tag 0x{tag:02X} len {length}")
    need(3)
    soc_pct = data[pos + 2] * 0.5
    pos += 3

    if pos == len(data):
        return DecodedRecord(
            timestamp=timestamp, vin=vin, soc_pct=soc_pct, periodic=True
        )

    tag, length = data[pos], data[pos + 1]
    if tag != TAG_A4_SOH or length != 1:
        raise RecordEncodeError(f"expected [A4] SoH, got tag 0x{tag:02X} len {length}")
    need(3)
    soh_pct = float(data[pos + 2])
    pos += 3

    tag, length = data[pos], data[pos + 1]
    if tag != TAG_A5_PACK_CURRENT or length != 2:
        raise RecordEncodeError(
            f"expected [A5] current, got tag 0x{tag:02X} len {length}"
        )
    need(4)
    (current_raw,) = struct.unpack("!H", data[pos + 2 : pos + 4])
    current_a = current_raw * 0.1
    pos += 4

    tag, length = data[pos], data[pos + 1]
    if tag != TAG_A6_PACK_VOLTAGE or length != 2:
        raise RecordEncodeError(
            f"expected [A6] voltage, got tag 0x{tag:02X} len {length}"
        )
    need(4)
    (voltage_raw,) = struct.unpack("!H", data[pos + 2 : pos + 4])
    voltage_v = voltage_raw * 0.1
    pos += 4

    tag, length = data[pos], data[pos + 1]
    if tag != TAG_B7_CELL_VOLT_MAXMIN or length != 2:
        raise RecordEncodeError(
            f"expected [B7] cell V, got tag 0x{tag:02X} len {length}"
        )
    need(4)
    cell_v_max = data[pos + 2] * 0.02
    cell_v_min = data[pos + 3] * 0.02
    pos += 4

    tag, length = data[pos], data[pos + 1]
    if tag != TAG_B8_CELL_TEMP_MAXMIN or length != 2:
        raise RecordEncodeError(
            f"expected [B8] cell T, got tag 0x{tag:02X} len {length}"
        )
    need(4)
    temp_c_max = data[pos + 2] - 40
    temp_c_min = data[pos + 3] - 40
    pos += 4

    return DecodedRecord(
        timestamp=timestamp,
        vin=vin,
        soc_pct=soc_pct,
        periodic=False,
        soh_pct=soh_pct,
        current_a=current_a,
        voltage_v=voltage_v,
        cell_v_max=cell_v_max,
        cell_v_min=cell_v_min,
        temp_c_max=temp_c_max,
        temp_c_min=temp_c_min,
    )
