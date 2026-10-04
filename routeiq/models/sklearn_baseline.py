import joblib

from routeiq.models.base import Prediction


class SklearnTfidfLogreg:
    def __init__(self, model_path):
        self.pipeline = joblib.load(model_path)

    def classify(self, text, labels):
        proba = self.pipeline.predict_proba([text])[0]
        idx = proba.argmax()
        return Prediction(
            label=str(self.pipeline.classes_[idx]),
            confidence=float(proba[idx]),
        )