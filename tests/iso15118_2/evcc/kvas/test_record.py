"""
Golden-vector and round-trip tests for iso15118.evcc.kvas.record.

The golden vector pins this encoder to a real EV's output - it is the single
highest-value test in the K-VAS EVCC work, see
Software/SmartyPluggerIotBoard/.claude/plans/2026-08-06-kvas-bench-bringup.md §6.6
and the source capture at
Software/SmartyPluggerIotBoard/_App/Kvas/tools/vas_reference_records.txt (record 1).
"""

import pytest

from iso15118.evcc.kvas.record import (
    RecordEncodeError,
    decode_record,
    encode_record,
)

GOLDEN_VIN = "KMHEM42APXA123456"
# Record 1 of the reference capture, laid out the way the format doc does
# (kvas-vas-record-format.md §5) so it can be diffed against it by eye.
GOLDEN_RECORD_HEX = (
    "a1"
    "04"
    "6900d923"
    "a2"
    "11"
    "4b4d48454d343241505841313233343536"
    "a3"
    "01"
    "64"
    "a4"
    "01"
    "61"
    "a5"
    "02"
    "011c"
    "a6"
    "02"
    "0eef"
    "b7"
    "02"
    "c0bd"
    "b8"
    "02"
    "3f3d"
)


def test_golden_vector_matches_reference_capture():
    """encode_record() reproduces record 1 of the real EV capture byte-for-byte."""
    record = encode_record(
        timestamp=0x6900D923,
        vin=GOLDEN_VIN,
        soc_pct=50.0,
        soh_pct=97,
        current_a=28.4,
        voltage_v=382.3,
        cell_v_max=3.84,
        cell_v_min=3.78,
        temp_c_max=23,
        temp_c_min=21,
    )
    assert record.hex() == GOLDEN_RECORD_HEX


def test_golden_vector_decodes_to_documented_values():
    record = bytes.fromhex(GOLDEN_RECORD_HEX)
    decoded = decode_record(record)

    assert decoded.timestamp == 0x6900D923
    assert decoded.vin == GOLDEN_VIN
    assert decoded.soc_pct == pytest.approx(50.0)
    assert decoded.soh_pct == pytest.approx(97.0)
    assert decoded.current_a == pytest.approx(28.4)
    assert decoded.voltage_v == pytest.approx(382.3)
    assert decoded.cell_v_max == pytest.approx(3.84)
    assert decoded.cell_v_min == pytest.approx(3.78)
    assert decoded.temp_c_max == 23
    assert decoded.temp_c_min == 21
    assert decoded.periodic is False


@pytest.mark.parametrize(
    "soc_pct,expected_byte",
    [
        (50.0, 0x64),
        (50.5, 0x65),  # scale-factor edge case: 50.5 / 0.5 = 101 = 0x65
        (0.0, 0x00),
        (100.0, 0xC8),
    ],
)
def test_soc_scale_factor_edge_cases(soc_pct, expected_byte):
    record = encode_record(
        timestamp=0,
        vin=GOLDEN_VIN,
        soc_pct=soc_pct,
        soh_pct=0,
        current_a=0,
        voltage_v=0,
        cell_v_max=0,
        cell_v_min=0,
        temp_c_max=-40,  # scale-factor edge case: -40 -> byte 0x00 (offset -40)
        temp_c_min=-40,
    )
    # [A1](6) + [A2](19) = 25 bytes before [A3]'s value byte
    assert record[25 + 2] == expected_byte
    decoded = decode_record(record)
    assert decoded.temp_c_max == -40
    assert decoded.temp_c_min == -40


def test_periodic_record_round_trip():
    """Case 2 Periodic: only groups A B C, nothing after."""
    record = encode_record(timestamp=1234, vin=GOLDEN_VIN, soc_pct=75.5, periodic=True)
    decoded = decode_record(record)

    assert decoded.periodic is True
    assert decoded.soc_pct == pytest.approx(75.5)
    assert decoded.soh_pct is None
    # No group D..H at all - exactly [A1][A2][A3], 6 + 19 + 3 = 28 bytes.
    assert len(record) == 28


def test_encode_rejects_wrong_length_vin():
    with pytest.raises(RecordEncodeError):
        encode_record(timestamp=0, vin="TOO_SHORT", soc_pct=50.0, periodic=True)


def test_encode_case1_requires_all_fields():
    with pytest.raises(RecordEncodeError):
        encode_record(timestamp=0, vin=GOLDEN_VIN, soc_pct=50.0, periodic=False)


def test_decode_rejects_truncated_record():
    record = encode_record(timestamp=0, vin=GOLDEN_VIN, soc_pct=50.0, periodic=True)
    with pytest.raises(RecordEncodeError):
        decode_record(record[: len(record) // 2])
