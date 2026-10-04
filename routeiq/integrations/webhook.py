import hashlib
import hmac
import json
import time

import httpx

RETRY_STATUS = (429, 500, 502, 503, 504)


class WebhookIntegration:
    def __init__(self, url, secret=None, timeout=5, max_attempts=3):
        self.url = url
        self.secret = secret
        self.timeout = timeout
        self.max_attempts = max_attempts

    def send(self, record):
        body = json.dumps(record, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.secret:
            digest = hmac.new(self.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
            headers["X-RouteIQ-Signature"] = "sha256=" + digest

        for attempt in range(self.max_attempts):
            try:
                r = httpx.post(self.url, content=body, headers=headers, timeout=self.timeout)
            except httpx.TransportError:
                time.sleep(2 ** attempt)
                continue
            if r.status_code in RETRY_STATUS:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return
        raise RuntimeError("webhook delivery failed after retries")