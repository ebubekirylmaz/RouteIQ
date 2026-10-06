---
title: RouteIQ
emoji: 🧭
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8000
pinned: false
license: mit
short_description: Confidence-based cascade routing, with a live dashboard
---

# RouteIQ: public demo

RouteIQ classifies incoming text with a cascade: a free baseline model answers when it is sure,
a language model answers when the baseline is not, and a person decides when neither is sure.
This is a live copy of the service with its dashboard.

Source code, results and documentation: https://github.com/ebubekirylmaz/routeiq

## About this demo

- **The data** is the CLINC150 test set (bank customer messages, CC BY 3.0). The history you see on
  start was replayed from decisions recorded when the models were evaluated.
- **What you type is stored and can be seen by everyone using this demo.** Please do not enter
  personal data. Everything is deleted when the demo resets, about once a day.
- **Sending texts is limited** (a few a minute for each visitor, and a daily total for everybody),
  and texts are limited to 500 characters.
- **The language model is paid for with a small, capped credit.** When it runs out, the cascade keeps
  working: requests the baseline is not sure about go to the review queue.
- The service has no login. That is acceptable for a demo like this one, and the reason for the limits.
