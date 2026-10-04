import os
from routeiq.integrations.jsonl import JsonlExport
from routeiq.integrations.webhook import WebhookIntegration
from routeiq.integrations.mock_erp_adapter import MockErpIntegration

def build_target(config):
    target = config.get("target") or {"type": "none"}
    kind = target["type"]
    if kind == "none":
        return None
    if kind == "jsonl":
        return JsonlExport(target["path"])
    if kind == "webhook":
        secret_env = target.get("secret_env")
        secret = os.getenv(secret_env) if secret_env else None
        return WebhookIntegration(
            target["url"], secret=secret,
        )
    if kind == "mock_erp":
        return MockErpIntegration(target["url"])
    raise ValueError(f"unknown target type: {kind}")