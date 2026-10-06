import argparse
import pandas as pd
from routeiq.config import MODELS_DIR, data_path, load_config, model_path
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score, classification_report


def train_baseline(config):
    """Trains the baseline on the domain's train split and checks it on the validation split."""
    train = pd.read_csv(data_path(config, "train"))
    val = pd.read_csv(data_path(config, "val"))
    test = pd.read_csv(data_path(config, "test"))

    print(len(train), len(val), len(test))

    model = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2))),
        ("clf", LogisticRegression(max_iter=1000)),
    ])

    model.fit(train["text"], train["label"])

    val_pred = model.predict(val["text"])
    print("accuracy:", accuracy_score(val["label"], val_pred))
    print("macro-F1:", f1_score(val["label"], val_pred, average="macro"))
    print(classification_report(val["label"], val_pred))

    MODELS_DIR.mkdir(exist_ok=True)
    path = model_path(config, "baseline")
    joblib.dump(model, path)
    print("model saved to", path)
    return {
        "accuracy": accuracy_score(val["label"], val_pred),
        "macro_f1": f1_score(val["label"], val_pred, average="macro"),
        "path": path,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    train_baseline(load_config(args.config))


if __name__ == "__main__":
    main()