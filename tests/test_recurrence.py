from datetime import datetime, timezone

import pytest

from bot.recurrence import next_due_date


def test_every_days():
    base = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)
    assert next_due_date(base, every_days=3) == datetime(
        2026, 8, 4, 9, 0, tzinfo=timezone.utc
    )


def test_weekdays_picks_next_monday():
    base = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)  # Saturday
    assert next_due_date(base, weekdays=[0]) == datetime(
        2026, 8, 3, 9, 0, tzinfo=timezone.utc
    )


def test_weekdays_skips_today_even_if_selected():
    base = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)  # Monday
    assert next_due_date(base, weekdays=[0]) == datetime(
        2026, 8, 10, 9, 0, tzinfo=timezone.utc
    )


def test_weekdays_picks_nearest_of_several():
    base = datetime(2026, 8, 3, 9, 0, tzinfo=timezone.utc)  # Monday
    # next Wednesday (2) or Friday (4) after Monday -> Wednesday
    assert next_due_date(base, weekdays=[2, 4]) == datetime(
        2026, 8, 5, 9, 0, tzinfo=timezone.utc
    )


def test_requires_a_rule():
    with pytest.raises(ValueError):
        next_due_date(datetime.now(timezone.utc))
