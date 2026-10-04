from routeiq.config import model_path
from routeiq.models.sklearn_baseline import SklearnTfidfLogreg


def build_classifier(config, tier):
    kind = tier["model"]
    if kind == "sklearn_tfidf_logreg":
        return SklearnTfidfLogreg(model_path(config, tier["name"]))
    raise ValueError(f"unknown model type: {kind}")


def build_tiers(config):
    return [(tier, build_classifier(config, tier)) for tier in config["tiers"]]