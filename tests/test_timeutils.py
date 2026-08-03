from datetime import datetime, timezone

from bot.timeutils import parse_utc_offset, to_local, to_utc, user_offset


def test_parse_utc_offset_positive_hours_only():
    assert parse_utc_offset("+3") == 180


def test_parse_utc_offset_negative_hours_only():
    assert parse_utc_offset("-5") == -300


def test_parse_utc_offset_with_minutes():
    assert parse_utc_offset("+5:30") == 330


def test_parse_utc_offset_strips_whitespace():
    assert parse_utc_offset("  +3  ") == 180


def test_parse_utc_offset_rejects_garbage():
    assert parse_utc_offset("не число") is None


def test_parse_utc_offset_rejects_missing_sign():
    assert parse_utc_offset("3") is None


def test_parse_utc_offset_accepts_boundary_values():
    assert parse_utc_offset("-12") == -12 * 60
    assert parse_utc_offset("+14") == 14 * 60


def test_parse_utc_offset_rejects_out_of_range():
    assert parse_utc_offset("-13") is None
    assert parse_utc_offset("+15") is None


def test_to_utc_and_back_round_trip():
    local_dt = datetime(2026, 8, 2, 15, 0)
    dt_utc = to_utc(local_dt, 180)
    assert dt_utc == datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc)
    local_again = to_local(dt_utc, 180)
    assert local_again == datetime(2026, 8, 2, 15, 0, tzinfo=timezone.utc)


def test_to_utc_negative_offset():
    local_dt = datetime(2026, 8, 2, 9, 0)
    assert to_utc(local_dt, -300) == datetime(
        2026, 8, 2, 14, 0, tzinfo=timezone.utc
    )


def test_user_offset_none_defaults_to_zero():
    assert user_offset(None) == 0


def test_user_offset_zero_stays_zero():
    assert user_offset(0) == 0


def test_user_offset_passes_through_value():
    assert user_offset(180) == 180
