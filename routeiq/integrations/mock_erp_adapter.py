from routeiq.integrations.webhook import WebhookIntegration

MAX_DESCRIPTION = 5000


def to_ticket(record):
    return {
        "ExternalID": str(record["request_id"]),
        "Category": record["label"],
        "Description": record["text"][:MAX_DESCRIPTION],
        "Confidence": record["confidence"],
        "Source": record["source"],
    }


class MockErpIntegration:
    def __init__(self, url, timeout=5, max_attempts=3):
        self._poster = WebhookIntegration(url, timeout=timeout, max_attempts=max_attempts)

    def send(self, record):
        self._poster.send(to_ticket(record))