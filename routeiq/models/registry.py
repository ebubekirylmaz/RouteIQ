from routeiq.config import model_path
from routeiq.models.sklearn_baseline import SklearnTfidfLogreg
from routeiq.models.openrouter import OpenRouterClassifier

def build_classifier(config, tier):
    kind = tier["model"]
    if kind == "sklearn_tfidf_logreg":
        path = model_path(config, tier["name"])
        if not path.exists():
            raise FileNotFoundError(
                f"no trained model for tier '{tier['name']}' of domain '{config['domain']}' (expected {path}). "
                "Train it first: python -m routeiq.train --config <the config of this domain>"
            )
        return SklearnTfidfLogreg(path)
    if kind == "openrouter":
        return OpenRouterClassifier(
            tier["model_id"],
            tier["price_in_per_m"],
            tier["price_out_per_m"],
            timeout=tier.get("timeout", 30),
            max_attempts=tier.get("max_attempts", 6),
            task=config.get("task", "messages"),
            label_descriptions=config.get("label_descriptions"),
        )
    raise ValueError(f"unknown model type: {kind}")



def build_tiers(config):
    return [(tier, build_classifier(config, tier)) for tier in config["tiers"]]