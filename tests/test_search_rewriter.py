"""Free tests of rewrite: what happens around the LLM call. No OpenAI calls.

A small fake stands in for the model, so these tests check our own code: the tidy-up of the new words, and the safe
default when the call fails. What the real model answers is checked in test_agent.py, and that is paid.
"""

from typing import Optional

from agents.search_rewriter import NewWords, SearchRewriter
from config.constants import MAX_SEARCH_WORDS


class FakeLlm:
    """Stands in for the model. It gives back the reply it was built with, or fails like OpenAI on a bad day."""

    def __init__(self, reply: Optional[NewWords] = None, fails: bool = False):
        self.reply = reply
        self.fails = fails

    def invoke(self, prompt: str) -> Optional[NewWords]:
        if self.fails:
            raise RuntimeError("no connection")
        return self.reply


def rewriter_with(llm: FakeLlm) -> SearchRewriter:
    """A rewriter that asks the fake instead of OpenAI."""
    rewriter = SearchRewriter()
    rewriter.llm = llm
    return rewriter


def test_the_new_words_are_tidied():
    """No spaces around the words, no empty entry, nothing that was already tried, and nothing twice."""
    reply = NewWords(
        reason="The texts could say laptop request.",
        search_words=["  laptop request ", "", "Order Form", "computer order", "Computer order"],
    )
    result = rewriter_with(FakeLlm(reply=reply)).rewrite("Who looks after the laptop order form?", ["order form"])
    assert result == {"search_words": ["laptop request", "computer order"]}


def test_too_many_words_are_cut():
    """The model is asked for a few words. If it gives more, only the first ones are kept."""
    reply = NewWords(reason="Many names.", search_words=[f"word {number}" for number in range(20)])
    result = rewriter_with(FakeLlm(reply=reply)).rewrite("Who looks after the laptop order form?", [])
    assert len(result["search_words"]) == MAX_SEARCH_WORDS


def test_a_failed_call_gives_no_new_words():
    """OpenAI can't be reached: no new words, so the second search uses the whole question."""
    assert rewriter_with(FakeLlm(fails=True)).rewrite("Who looks after the laptop order form?", ["order form"]) == {
        "search_words": []
    }


def test_a_missing_reply_gives_no_new_words():
    """The model replied, but nothing usable came back: the same safe default."""
    assert rewriter_with(FakeLlm(reply=None)).rewrite("Who looks after the laptop order form?", ["order form"]) == {
        "search_words": []
    }


def test_the_prompt_holds_the_request_the_tried_words_and_no_test_question(scenarios):
    """The prompt shows the request and the words already tried. Its example is made up: it quotes no demo question."""
    prompt = SearchRewriter().generate_prompt("Who looks after the laptop order form?", ["laptop order form"])
    assert "Who looks after the laptop order form?" in prompt
    assert "**Words already tried:** laptop order form" in prompt
    for case in scenarios.values():
        for turn in case["turns"]:
            assert turn["question"] not in prompt
