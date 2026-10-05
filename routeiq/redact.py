import re

_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://[^\s'\"<>]+")


def redact_urls(text):
    if text is None:
        return None
    return _URL.sub("<url>", text)