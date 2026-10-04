from routeiq.config import model_path
from routeiq.models.sklearn_baseline import SklearnTfidfLogreg
from routeiq.models.openrouter import OpenRouterClassifier

def build_classifier(config, tier):
    kind = tier["model"]
    if kind == "sklearn_tfidf_logreg":
        return SklearnTfidfLogreg(model_path(config, tier["name"]))
    if kind == "openrouter":
        return OpenRouterClassifier(
            tier["model_id"], tier["price_in_per_m"], tier["price_out_per_m"]
    )
    raise ValueError(f"unknown model type: {kind}")



def build_tiers(config):
    return [(tier, build_classifier(config, tier)) for tier in config["tiers"]]