from routeiq.schemas import ConfigResponse, LabelInfo, TierInfo


def describe_config(config=None, labels=None, tiers=None):
    if config is not None:
        descriptions = config.get("label_descriptions") or {}
        return ConfigResponse(
            domain=config["domain"],
            task=config.get("task"),
            labels=[LabelInfo(name=name, description=descriptions.get(name)) for name in config["labels"]],
            tiers=[
                TierInfo(
                    name=tier["name"],
                    model=tier["model"],
                    model_id=tier.get("model_id"),
                    accept_threshold=tier["accept_threshold"],
                )
                for tier in config["tiers"]
            ],
            target_type=(config.get("target") or {}).get("type"),
        )
    return ConfigResponse(
        domain=None,
        task=None,
        labels=[LabelInfo(name=name, description=None) for name in labels or []],
        tiers=[
            TierInfo(name=tier["name"], model=tier.get("model"), model_id=None,
                     accept_threshold=tier["accept_threshold"])
            for tier, _ in tiers or []
        ],
        target_type=None,
    )