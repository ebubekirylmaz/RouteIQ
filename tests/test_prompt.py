from routeiq.config import ROOT, load_config
from routeiq.models.openrouter import build_system_prompt

# The system prompt that produced every number in the README results. Moving the label
# descriptions into the config must not change a single character of it.
REPORTED_PROMPT = (
    "You classify bank customer support messages into exactly one category.\n"
    "Categories: report_lost_card, damaged_card, card_declined, report_fraud, freeze_account, out_of_scope.\n"
    "- report_lost_card: the customer lost their card or cannot find it.\n"
    "- damaged_card: the card is physically damaged (cracked, burned, bent).\n"
    "- card_declined: a payment was refused or the card was not accepted.\n"
    "- report_fraud: unauthorized or suspicious charges on the account.\n"
    "- freeze_account: the customer wants the account blocked or locked.\n"
    "- out_of_scope: anything else, including messages unrelated to banking.\n"
    "Answer with the single best category."
)


def test_shipped_config_produces_the_prompt_the_results_were_measured_with():
    config = load_config(ROOT / "configs" / "clinc150.yaml")
    prompt = build_system_prompt(config["labels"], config["label_descriptions"], config["task"])
    assert prompt == REPORTED_PROMPT


def test_prompt_with_descriptions():
    prompt = build_system_prompt(["a", "b"], {"a": "first one.", "b": "second one."}, "tickets")
    assert prompt == (
        "You classify tickets into exactly one category.\n"
        "Categories: a, b.\n"
        "- a: first one.\n"
        "- b: second one.\n"
        "Answer with the single best category."
    )


def test_prompt_without_descriptions_lists_only_the_labels():
    prompt = build_system_prompt(["a", "b"])
    assert prompt == (
        "You classify messages into exactly one category.\n"
        "Categories: a, b.\n"
        "Answer with the single best category."
    )


def test_labels_without_a_description_are_listed_but_not_described():
    prompt = build_system_prompt(["a", "b"], {"a": "first one."})
    assert "Categories: a, b." in prompt
    assert "- a: first one." in prompt
    assert "- b:" not in prompt


def test_descriptions_follow_the_order_of_the_labels():
    prompt = build_system_prompt(["b", "a"], {"a": "first.", "b": "second."})
    assert prompt.index("- b: second.") < prompt.index("- a: first.")


def test_descriptions_for_labels_not_asked_for_are_ignored():
    prompt = build_system_prompt(["a"], {"a": "first.", "zzz": "unused."})
    assert "zzz" not in prompt


def test_empty_description_is_treated_as_missing():
    prompt = build_system_prompt(["a", "b"], {"a": "first.", "b": ""})
    assert "- b:" not in prompt


def test_custom_task_appears_in_the_first_line():
    first_line = build_system_prompt(["a"], None, "supplier emails").splitlines()[0]
    assert first_line == "You classify supplier emails into exactly one category."
