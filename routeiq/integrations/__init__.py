from routeiq.integrations.jsonl import JsonlExport


def build_target(config):
    target = config.get("target") or {"type": "none"}
    kind = target["type"]
    if kind == "none":
        return None
    if kind == "jsonl":
        return JsonlExport(target["path"])
    raise ValueError(f"unknown target type: {kind}")