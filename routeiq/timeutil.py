from datetime import timedelta, timezone

BUCKET_STEPS = {"hour": timedelta(hours=1), "day": timedelta(days=1)}


def as_utc(moment):
    """A datetime without a time zone is taken to be UTC."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def floor_to_bucket(moment, bucket):
    """Start of the hour or day (UTC) that contains the moment."""
    moment = as_utc(moment)
    if bucket == "hour":
        return moment.replace(minute=0, second=0, microsecond=0)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)
