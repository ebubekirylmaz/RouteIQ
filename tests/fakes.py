from routeiq.models.base import Prediction


class Fake:
    def __init__(self, label, confidence, cost=0.0):
        self.label = label
        self.confidence = confidence
        self.cost = cost
        self.calls = 0

    def classify(self, text, labels):
        self.calls += 1
        return Prediction(self.label, self.confidence, self.cost)


class Boom:
    def __init__(self):
        self.calls = 0

    def classify(self, text, labels):
        self.calls += 1
        raise RuntimeError("boom")
