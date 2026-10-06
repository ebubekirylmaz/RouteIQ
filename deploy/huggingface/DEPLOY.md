# Publishing the demo on Hugging Face Spaces

This puts a live copy of RouteIQ, with its dashboard, on a Hugging Face Space. It runs in *demo mode*:
the service has no login, so the demo protects itself with limits and a daily reset (see below).

You need two accounts: Hugging Face (to host it) and OpenRouter (the language model the cascade calls).
Nothing here asks you to put a key into a file or into the repository.

## 1. A key for the demo only, with a spending limit

Create a new OpenRouter API key just for the demo and give it a **credit limit** (the key creation form
has the option; a dollar or two is plenty: a request that reaches the language model costs about
two thousandths of a cent). If you cannot find the option, put only a few dollars of credit on the
account instead. Do not reuse your everyday key: this one will sit in a public demo's settings.

## 2. Create the Space

On huggingface.co: **New Space**, choose **Docker** as the SDK and the **Blank** template, visibility
**Public**, the free **CPU basic** hardware. Name it, for example, `routeiq`.

## 3. Give the Space the key

In the Space: **Settings → Variables and secrets → New secret**. Name `OPENROUTER_API_KEY`, value the
key from step 1. A secret is not shown again and is not part of the image.

## 4. Publish

Make sure everything you want published is committed on your machine (only committed files are sent),
then, from the repository root:

```bash
scripts/publish_space.sh https://huggingface.co/spaces/<your-user>/routeiq
```

Git asks for a user name and a password: use your Hugging Face user name, and as the password an
**access token with write permission** (Settings → Access Tokens). The script sends the committed files
of the repository to the Space, with two changes made on the way: the Space's own `README.md`
(`deploy/huggingface/README.md`) replaces the project README, and a line is added to the Dockerfile that
switches demo mode on, so it cannot be forgotten. Your working copy is not changed.

To see what would be sent without sending anything:

```bash
scripts/publish_space.sh --dry-run /tmp/space-preview
```

## 5. Wait for the build, then look

The Space builds the image (a few minutes: it installs the packages, downloads CLINC150 and trains the
baseline) and then starts it. The **Logs** tab shows the build. When it runs, open the Space and check:

- the dashboard opens, with a **Public demo** note at the top;
- *Overview* shows 300 requests and *Review queue* has requests waiting;
- *Try it* answers a text, and *Evaluation* shows the results of the README.

## Updating

Commit your changes, then run the publish command again. The Space is rebuilt from what you sent.
Hugging Face keeps the Space's own history, and the script replaces it each time (it is a copy, not the
place the project lives).

## What demo mode does

Switched on by `ROUTEIQ_DEMO=1` (the publish script adds it). Everything has a default and needs no setting.

| Protection | Default | Setting |
|---|---|---|
| Texts a single address can send | 10 a minute | `ROUTEIQ_DEMO_ROUTES_PER_MINUTE` |
| Texts everybody together can send | 500 a day | `ROUTEIQ_DEMO_ROUTES_PER_DAY` |
| Other writes (review decisions) for one address | 30 a minute | `ROUTEIQ_DEMO_WRITES_PER_MINUTE` |
| Longest text | 500 characters | `ROUTEIQ_DEMO_MAX_TEXT` |
| Delete everything and start again | every 24 hours | `ROUTEIQ_DEMO_RESET_HOURS` |
| Where the demo keeps its data | a temporary file | `ROUTEIQ_DEMO_DB` |

- The daily total is what caps spending, whatever anybody does about addresses: 500 texts cost
  a few cents at most.
- A request larger than 8 KB is refused.
- The demo never opens the database of `ROUTEIQ_DB`: it has a temporary one of its own, so switching
  demo mode on by mistake cannot wipe real data.
- The address of a visitor is taken from the proxy's `X-Forwarded-For` header (its last entry, which
  the nearest proxy adds). If the platform puts more than one proxy in front, the per-address limits
  become coarser, and the daily total still holds.
- These limits make a public demo reasonable. They are **not authentication**, and they do not make the
  service fit for real data.

## Taking it down

Delete the Space in its settings, and delete or rotate the OpenRouter key.

## If something goes wrong

- *The build fails*: read the build log in the **Logs** tab. The Dockerfile in the Space is the one of
  the repository; building it locally with `docker build .` shows the same error.
- *"OPENROUTER_API_KEY is not set" in the runtime log*: the secret of step 3 is missing or misspelled.
- *Everything answers with "limit"*: the daily total was reached; it starts again after the next reset
  (restart the Space to reset at once).
- *The language model never answers*: the credit of the key is used up. The cascade still works, and
  sends what the baseline is unsure about to the review queue.
