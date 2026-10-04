import argparse
import pandas as pd
from routeiq.config import load_config, model_path, ROOT, MODELS_DIR
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, f1_score, classification_report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    config = load_config(args.config)

    data_dir = ROOT / "data"
    train = pd.read_csv(data_dir / "train.csv")
    val = pd.read_csv(data_dir / "val.csv")
    test = pd.read_csv(data_dir / "test.csv")

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

if __name__ == "__main__":
    main()