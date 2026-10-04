from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
MODELS_DIR = ROOT / "models"


def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)


def model_path(config, tier_name):
    return MODELS_DIR / f"{config['domain']}_{tier_name}.joblib"