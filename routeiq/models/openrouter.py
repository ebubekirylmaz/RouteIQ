import os
import json
import time
import httpx
import math
from dotenv import load_dotenv

from routeiq.models.base import Prediction

API_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterClassifier:
    def __init__(self, model_id, price_in_per_m, price_out_per_m, timeout=30):
        load_dotenv()
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self.model_id = model_id
        self.price_in = price_in_per_m
        self.price_out = price_out_per_m
        self.timeout = timeout

    def _request(self, text, labels):
        payload = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": (
                    "You classify bank customer support messages into exactly one category.\n"
                    f"Categories: {', '.join(labels)}.\n"
                    "- report_lost_card: the customer lost their card or cannot find it.\n"
                    "- damaged_card: the card is physically damaged (cracked, burned, bent).\n"
                    "- card_declined: a payment was refused or the card was not accepted.\n"
                    "- report_fraud: unauthorized or suspicious charges on the account.\n"
                    "- freeze_account: the customer wants the account blocked or locked.\n"
                    "- out_of_scope: anything else, including messages unrelated to banking.\n"
                    "Answer with the single best category."
                )},
                {"role": "user", "content": text},
            ],
            "temperature": 0,
            "max_tokens": 30,
            "logprobs": True,
            "top_logprobs": 5,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "classification",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {"label": {"type": "string", "enum": labels}},
                        "required": ["label"],
                        "additionalProperties": False,
                    },
                },
            },
            "provider": {"require_parameters": True},
        }
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(4):
            r = httpx.post(API_URL, json=payload, headers=headers, timeout=self.timeout)
            if r.status_code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r.json()
        r.raise_for_status()
    
    def classify(self, text, labels):
        data = self._request(text, labels)
        choice = data["choices"][0]
        label = json.loads(choice["message"]["content"])["label"]
        usage = data["usage"]
        cost = usage.get("cost")
        if cost is None:
            cost = (
                usage["prompt_tokens"] * self.price_in
                + usage["completion_tokens"] * self.price_out
            ) / 1_000_000
        return Prediction(label=label, confidence=self._label_confidence(choice, label), cost_usd=cost)
    
    def _label_confidence(self, choice, label):
        content = choice["message"]["content"]
        tokens = choice["logprobs"]["content"]
        start = content.index(label, content.index(":"))
        end = start + len(label)

        pos = 0
        total = 0.0
        for t in tokens:
            tok_start = pos
            tok_end = pos + len(t["token"])
            if tok_end > start and tok_start < end:
                total += t["logprob"]
            pos = tok_end
        return math.exp(total)