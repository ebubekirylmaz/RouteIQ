from pathlib import Path
import yaml
import pandas as pd
from datasets import load_dataset

CONFIG_PATH = Path(__file__).parent.parent / "configs" / "clinc150.yaml"

with open(CONFIG_PATH) as f:
    config = yaml.safe_load(f)

wanted_labels = set(config["labels"])
OUT_DIR = Path(__file__).parent / config["domain"]
OUT_DIR.mkdir(exist_ok=True)

ds = load_dataset("clinc/clinc_oos", "plus")
names = ds["train"].features["intent"].names

def build_split(split):
    rows = []
    for ex in split:
        label = names[ex["intent"]]
        if label == "oos":
            label = "out_of_scope"
        if label in wanted_labels:
            rows.append({"text": ex["text"], "label": label})
    return pd.DataFrame(rows)

train_df = build_split(ds["train"])
val_df = build_split(ds["validation"])
test_df = build_split(ds["test"])
oos_df = test_df[test_df["label"] == "out_of_scope"]
rest_df = test_df[test_df["label"] != "out_of_scope"]
oos_sample = oos_df.sample(n=150, random_state=42)
test_df = pd.concat([rest_df, oos_sample])

train_df.to_csv(OUT_DIR / "train.csv", index=False)
val_df.to_csv(OUT_DIR / "val.csv", index=False)
test_df.to_csv(OUT_DIR / "test.csv", index=False)

print("--- train")
print(train_df["label"].value_counts())
print("--- val")
print(val_df["label"].value_counts())
print("--- test")
print(test_df["label"].value_counts())