"""Free tests of verify: what happens around the LLM calls. No OpenAI calls.

A small fake stands in for the model, so these tests check our own code: one call per text, the order of the answer,
and what happens when a reply is missing or when OpenAI fails.
The tests of what the real model answers are in test_agent.py, and they are paid.
"""

from typing import Dict, List, Optional

import pytest

from agents.evidence_verifier import EvidenceVerifier, Verdict


class FakeLlm:
    """Stands in for the model. It answers each prompt with the next prepared verdict, or fails like OpenAI on a bad day."""

    def __init__(self, replies: Optional[List[Optional[Verdict]]] = None, fails: bool = False):
        self.replies = replies or []
        self.fails = fails
        self.prompts: List[str] = []

    def batch(self, prompts: List[str], config: Optional[Dict] = None) -> List[Optional[Verdict]]:
        if self.fails:
            raise RuntimeError("no connection")
        self.prompts += prompts
        return self.replies


def verifier_with(llm: FakeLlm) -> EvidenceVerifier:
    """A verifier that asks the fake instead of OpenAI."""
    verifier = EvidenceVerifier()
    verifier.llm = llm
    return verifier


def item(item_id: str, text: str, item_type: str = "ticket") -> Dict:
    """A made-up ticket or page, with only what verify reads."""
    return {"id": item_id, "type": item_type, "text": text}


YES = Verdict(reason="It is about the laptop order form.", relevant=True)
NO = Verdict(reason="It is about the parking list.", relevant=False)
ITEMS = [
    item("LAP-1", "The laptop order form loses the delivery address."),
    item("LAP-2", "Update the parking list for the new building."),
    item("pg901", "How the laptop order form works.", "doc"),
]


def test_each_item_is_judged_in_its_own_call():
    """One prompt per item, and a prompt holds one item only: no item can change the verdict on another."""
    llm = FakeLlm(replies=[YES, NO, YES])
    verifier_with(llm).verify("Who looks after the laptop order form?", ITEMS)

    assert len(llm.prompts) == len(ITEMS)
    for position, prompt in enumerate(llm.prompts):
        for other_position, other in enumerate(ITEMS):
            assert (other["text"] in prompt) == (position == other_position)


def test_the_items_that_hold_up_come_back_in_the_order_given():
    """The verdicts are matched to the items by their order, and only a "yes" keeps an item."""
    result = verifier_with(FakeLlm(replies=[YES, NO, YES])).verify("Who looks after the laptop order form?", ITEMS)
    assert result == {"kept_ids": ["LAP-1", "pg901"]}


def test_a_missing_verdict_counts_as_no():
    """Never trust the reply: an item without a usable verdict is not kept."""
    result = verifier_with(FakeLlm(replies=[None, YES, None])).verify("Who looks after the laptop order form?", ITEMS)
    assert result == {"kept_ids": ["LAP-2"]}


def test_nothing_to_judge_means_no_call():
    """With no item, the model is not called at all."""
    llm = FakeLlm(fails=True)
    assert verifier_with(llm).verify("Who looks after the laptop order form?", []) == {"kept_ids": []}


def test_a_failed_call_is_an_error_not_a_nobody_found():
    """OpenAI can't be reached: verify stops with an error. "Nobody found" must mean that the agent looked."""
    with pytest.raises(RuntimeError):
        verifier_with(FakeLlm(fails=True)).verify("Who looks after the laptop order form?", ITEMS)


def test_only_minutes_get_the_rule_about_decisions():
    """Minutes count for the decision they record, so only their prompt asks for a decision about the request."""
    verifier = EvidenceVerifier()
    minutes = item("pg902", "Team meeting. Decision: we replace the laptop order form in March.", "minutes")

    assert "record a decision" in verifier.generate_prompt("Who decided to replace the laptop order form?", minutes)
    assert "record a decision" not in verifier.generate_prompt("Who decided to replace the laptop order form?", ITEMS[0])


def test_the_prompt_holds_the_request_and_no_test_question(scenarios):
    """The prompt shows the request and the item. Its examples are made up: it never quotes a demo question."""
    prompt = EvidenceVerifier().generate_prompt("Who looks after the laptop order form?", ITEMS[0])
    assert "Who looks after the laptop order form?" in prompt
    assert ITEMS[0]["text"] in prompt
    for case in scenarios.values():
        for turn in case["turns"]:
            assert turn["question"] not in prompt
