from datetime import datetime, timedelta, timezone

import pytest

from routeiq.timeutil import BUCKET_STEPS, as_utc, floor_to_bucket

UTC = timezone.utc


def test_naive_datetime_is_taken_as_utc():
    assert as_utc(datetime(2026, 10, 5, 10, 0)) == datetime(2026, 10, 5, 10, 0, tzinfo=UTC)


def test_aware_datetime_is_converted_to_utc():
    plus_three = timezone(timedelta(hours=3))
    result = as_utc(datetime(2026, 10, 5, 13, 0, tzinfo=plus_three))
    assert result == datetime(2026, 10, 5, 10, 0, tzinfo=UTC)
    assert result.utcoffset() == timedelta(0)


def test_naive_and_aware_results_can_be_compared():
    assert as_utc(datetime(2026, 10, 5)) < as_utc(datetime(2026, 10, 6, tzinfo=UTC))


@pytest.mark.parametrize("moment, expected", [
    (datetime(2026, 10, 5, 10, 37, 12, 345, tzinfo=UTC), datetime(2026, 10, 5, 10, 0, tzinfo=UTC)),
    (datetime(2026, 10, 5, 10, 0, tzinfo=UTC), datetime(2026, 10, 5, 10, 0, tzinfo=UTC)),
    (datetime(2026, 10, 5, 23, 59, 59, tzinfo=UTC), datetime(2026, 10, 5, 23, 0, tzinfo=UTC)),
])
def test_floor_to_the_hour(moment, expected):
    assert floor_to_bucket(moment, "hour") == expected


def test_floor_to_the_day():
    moment = datetime(2026, 10, 5, 23, 59, 59, tzinfo=UTC)
    assert floor_to_bucket(moment, "day") == datetime(2026, 10, 5, tzinfo=UTC)


def test_floor_uses_utc_boundaries_for_other_time_zones():
    plus_three = timezone(timedelta(hours=3))
    moment = datetime(2026, 10, 5, 1, 30, tzinfo=plus_three)   # 22:30 UTC on the 4th
    assert floor_to_bucket(moment, "day") == datetime(2026, 10, 4, tzinfo=UTC)
    assert floor_to_bucket(moment, "hour") == datetime(2026, 10, 4, 22, 0, tzinfo=UTC)


def test_floor_accepts_naive_datetimes():
    assert floor_to_bucket(datetime(2026, 10, 5, 10, 37), "hour") == datetime(2026, 10, 5, 10, 0, tzinfo=UTC)


def test_bucket_steps():
    assert BUCKET_STEPS == {"hour": timedelta(hours=1), "day": timedelta(days=1)}
