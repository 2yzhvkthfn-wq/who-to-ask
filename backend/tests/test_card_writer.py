"""Free tests of write_cards: what happens around the LLM calls. No OpenAI calls.

A small fake stands in for the model, so these tests check our own code: one call per person, and the checks that
keep a name, an address, or a link out of the texts the LLM writes.
The tests of what the real model writes are in test_agent.py, and they are paid.
"""

from typing import Dict, List, Optional

import pytest

from agents.card_writer import CardText, CardWriter
from config.constants import MAX_MESSAGE_LENGTH, MAX_SUBJECT_LENGTH


class FakeLlm:
    """Stands in for the model. It answers each prompt with the next prepared reply, or fails like OpenAI on a bad day.

    replies are the answers to the first calls, one per person, all sent together (batch).
    again are the answers when a message is asked for again, one call at a time (invoke): None means that call fails.
    """

    def __init__(
        self,
        replies: Optional[List[Optional[CardText]]] = None,
        fails: bool = False,
        again: Optional[List[Optional[CardText]]] = None,
    ):
        self.replies = replies or []
        self.fails = fails
        self.again = list(again or [])
        self.prompts: List[str] = []
        self.again_prompts: List[str] = []

    def batch(self, prompts: List[str], config: Optional[Dict] = None) -> List[Optional[CardText]]:
        if self.fails:
            raise RuntimeError("no connection")
        self.prompts += prompts
        return self.replies

    def invoke(self, prompt: str) -> CardText:
        self.again_prompts.append(prompt)
        reply = self.again.pop(0) if self.again else None
        if reply is None:
            raise RuntimeError("no connection")
        return reply


def writer_with(llm: FakeLlm) -> CardWriter:
    """A card writer that asks the fake instead of OpenAI, with a small made-up directory."""
    writer = CardWriter()
    writer.llm = llm
    # The names the checks look for: lower case, no accents
    writer.names = {"nadia", "benali", "nathalie", "cote", "marc", "andre"}
    return writer


QUESTION = "Who looks after the laptop order form?"
PERSON_1 = {
    "person": "p901",
    "evidence": [
        {"id": "pg901", "title": "Laptop order form: guide", "source": "Confluence", "kind": "wrote"},
        {"id": "LAP-1", "title": "The form loses the delivery address", "source": "Jira", "kind": "assigned"},
    ],
}
PERSON_2 = {
    "person": "p902",
    "evidence": [{"id": "LAP-7", "title": "New laptops for the sales team", "source": "Jira", "kind": "approved"}],
}
GOOD = CardText(
    why="wrote the guide of the laptop order form and handled 1 ticket about it",
    message="I need to order a laptop, and I saw you wrote the guide of the order form. Could you help me?",
    subject="Help with the laptop order form",
)
EMPTY = {"person": "p901", "why": "", "message": "", "subject": ""}
# The texts for a second person: its message ends with another question than GOOD
OTHER = CardText(
    why="approved the new laptops of the sales team",
    message="I need to order a laptop. I saw you approved the last order. What do you need to approve mine?",
    subject="Approval of a laptop order",
)


def test_good_texts_are_passed_on():
    """A reply with nothing forbidden in it is passed on as it is, with the id of its person."""
    result = writer_with(FakeLlm(replies=[GOOD])).write(QUESTION, "en", [PERSON_1])
    assert result == {
        "cards": [{"person": "p901", "why": GOOD.why, "message": GOOD.message, "subject": GOOD.subject}]
    }


def test_each_person_gets_their_own_call():
    """One prompt per person, with this person's evidence only: a card can't borrow what another person did."""
    llm = FakeLlm(replies=[GOOD, OTHER])
    result = writer_with(llm).write(QUESTION, "en", [PERSON_1, PERSON_2])

    assert [card["person"] for card in result["cards"]] == ["p901", "p902"]
    assert [card["message"] for card in result["cards"]] == [GOOD.message, OTHER.message]
    # Two calls, sent together. The two messages end with different questions, so nothing is asked again
    assert len(llm.prompts) == 2 and llm.again_prompts == []
    assert "Laptop order form: guide" in llm.prompts[0] and "New laptops for the sales team" not in llm.prompts[0]
    assert "New laptops for the sales team" in llm.prompts[1] and "Laptop order form: guide" not in llm.prompts[1]


def test_a_text_is_put_on_one_line():
    """Line breaks and double spaces become single spaces, so the message fits in a link and on a card."""
    reply = CardText(
        why="  wrote the guide\nof the form ",
        message="I need a laptop.\n\nCould you  help me?",
        subject=" Help with\nthe order form ",
    )
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card["why"] == "wrote the guide of the form"
    assert card["message"] == "I need a laptop. Could you help me?"
    assert card["subject"] == "Help with the order form"


def test_a_curly_apostrophe_becomes_a_straight_one():
    """The model writes I’m, and the sentences of the code around its text write I'm: a message has one kind only."""
    reply = CardText(
        why="wrote the form’s guide",
        message="I’m trying to order a laptop. J’ai vu que vous l’avez fait.",
        subject="The form’s guide",
    )
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card["why"] == "wrote the form's guide"
    assert card["message"] == "I'm trying to order a laptop. J'ai vu que vous l'avez fait."
    assert card["subject"] == "The form's guide"


# ----------------------------------------------------------------------
# Short, separate sentences: no long dash and no semicolon
# ----------------------------------------------------------------------


def test_a_long_dash_in_a_message_becomes_a_full_stop():
    """The model likes to join two sentences with a long dash. A message has short, separate sentences instead."""
    reply = CardText(
        why=GOOD.why,
        message="I need a laptop. I saw you wrote the guide and handled a few orders—could you point me to the form?",
        subject=GOOD.subject,
    )
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card["message"] == (
        "I need a laptop. I saw you wrote the guide and handled a few orders. Could you point me to the form?"
    )


@pytest.mark.parametrize(
    "written, shown",
    [
        ("I saw your guide — could you help me?", "I saw your guide. Could you help me?"),
        ("I saw your guide – could you help me?", "I saw your guide. Could you help me?"),
        ("I saw your guide; could you help me?", "I saw your guide. Could you help me?"),
        ("J'ai vu votre guide ; pourriez-vous m'aider ?", "J'ai vu votre guide. Pourriez-vous m'aider ?"),
        ("I need a laptop—soon—for a new colleague.", "I need a laptop. Soon. For a new colleague."),
        ("Is it done?—I hope so.", "Is it done? I hope so."),
    ],
    ids=["a long dash with spaces", "a short dash with spaces", "a semicolon", "a French semicolon", "two dashes", "after a question mark"],
)
def test_every_mark_that_joins_two_sentences_becomes_a_full_stop(written, shown):
    """A long dash, a dash between two spaces, and a semicolon: each one ends a sentence, and the next one gets its capital."""
    reply = CardText(why=GOOD.why, message=written, subject=GOOD.subject)
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card["message"] == shown


def test_a_hyphen_inside_a_word_or_a_title_is_left_alone():
    """Only the marks that join sentences are replaced: a hyphen of a word, of a name of a page, or of a range stays."""
    message = 'I saw you wrote "Laptops - how to order one" for the sign-on of new colleagues. Is step 2-3 up to date?'
    reply = CardText(why=GOOD.why, message=message, subject=GOOD.subject)
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card["message"] == message


def test_a_long_dash_in_the_other_two_texts_becomes_a_comma():
    """The "why" sentence and the subject are one line each: a long dash becomes a comma there."""
    reply = CardText(why="wrote the guide—and handled 1 ticket", message=GOOD.message, subject="Laptop order — help")
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card["why"] == "wrote the guide, and handled 1 ticket"
    assert card["subject"] == "Laptop order, help"


# ----------------------------------------------------------------------
# The messages of one answer do not end with the same question
# ----------------------------------------------------------------------

PERSON_3 = {
    "person": "p903",
    "evidence": [{"id": "LAP-9", "title": "The form refuses a second screen", "source": "Jira", "kind": "assigned"}],
}
# Three replies of the first calls that end with the same question, as the model wrote them at first
SAME_1 = CardText(why="wrote the guide", message="I need a laptop. I saw you wrote the guide. Could you help me?", subject="Laptop order")
SAME_2 = CardText(why="approved an order", message="I need a laptop. I saw you approved an order. Could you help me?", subject="Laptop order")
SAME_3 = CardText(why="handled a ticket", message="I need a laptop. I saw you handled a ticket. could you help me ?", subject="Laptop order")


def test_a_message_that_ends_like_an_earlier_one_is_asked_for_again():
    """Two messages end with the same question: the second one is asked for again, with the question that is taken."""
    new = CardText(why="x", message="I need a laptop. I saw you approved an order. What do you need to approve mine?", subject="x")
    llm = FakeLlm(replies=[SAME_1, SAME_2], again=[new])
    cards = writer_with(llm).write(QUESTION, "en", [PERSON_1, PERSON_2])["cards"]

    # The first message stays, and the second one is the new one. Its two other texts are still the first ones
    assert cards[0]["message"] == SAME_1.message
    assert cards[1] == {"person": "p902", "why": SAME_2.why, "message": new.message, "subject": SAME_2.subject}
    # One more call, for the second person only, with this person's evidence and the question to avoid
    assert len(llm.again_prompts) == 1
    assert "New laptops for the sales team" in llm.again_prompts[0] and "Laptop order form: guide" not in llm.again_prompts[0]
    assert 'already end with these questions: "Could you help me?"' in llm.again_prompts[0]
    # The first prompts say nothing about other messages: each call only knows its own person
    assert all("already end with" not in prompt for prompt in llm.prompts)


def test_three_messages_with_the_same_question_get_three_different_ones():
    """Capitals and spaces do not make a question different. The third call knows the new question of the second one."""
    new_2 = CardText(why="x", message="I need a laptop. What do you need to approve mine?", subject="x")
    new_3 = CardText(why="x", message="I need a laptop. How did you solve it?", subject="x")
    llm = FakeLlm(replies=[SAME_1, SAME_2, SAME_3], again=[new_2, new_3])
    cards = writer_with(llm).write(QUESTION, "en", [PERSON_1, PERSON_2, PERSON_3])["cards"]

    assert [card["message"] for card in cards] == [SAME_1.message, new_2.message, new_3.message]
    assert len(llm.again_prompts) == 2
    assert '"Could you help me?", "What do you need to approve mine?"' in llm.again_prompts[1]


def test_a_new_message_that_repeats_a_question_again_is_not_used():
    """The second try ends with a question that is already taken: the first message stays. There is no third try."""
    still_the_same = CardText(why="x", message="I need a laptop. Could you help me?", subject="x")
    llm = FakeLlm(replies=[SAME_1, SAME_2], again=[still_the_same])
    cards = writer_with(llm).write(QUESTION, "en", [PERSON_1, PERSON_2])["cards"]

    assert [card["message"] for card in cards] == [SAME_1.message, SAME_2.message]
    assert len(llm.again_prompts) == 1


def test_a_new_message_that_is_not_safe_or_that_failed_is_not_used():
    """The second try names a person, or the call fails: the first message stays, because it was safe to show."""
    names_someone = CardText(why="x", message="Nathalie told me to ask you. What do you need to approve mine?", subject="x")
    for again in [[names_someone], [None]]:
        llm = FakeLlm(replies=[SAME_1, SAME_2], again=again)
        cards = writer_with(llm).write(QUESTION, "en", [PERSON_1, PERSON_2])["cards"]
        assert [card["message"] for card in cards] == [SAME_1.message, SAME_2.message]


def test_a_message_that_was_thrown_away_is_not_compared():
    """An empty message has no last question: nothing is asked again for it, or because of it."""
    unsafe = CardText(why="x", message="Write to someone@tamberly.example. Could you help me?", subject="x")
    llm = FakeLlm(replies=[unsafe, SAME_2])
    cards = writer_with(llm).write(QUESTION, "en", [PERSON_1, PERSON_2])["cards"]

    assert [card["message"] for card in cards] == ["", SAME_2.message]
    assert llm.again_prompts == []


def test_a_text_that_names_a_person_comes_back_empty():
    """Names come from the data, never from the LLM: a text with a first name or a last name is thrown away."""
    reply = CardText(
        why="handled the ticket that Nadia Benali opened",
        message="I saw you worked on this with Marc-André. Could you help me?",
        subject="A question from Nathalie",
    )
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card == EMPTY


def test_only_the_text_with_the_name_is_thrown_away():
    """The three texts are checked one by one: a good "why" sentence and a good subject stay when the message names someone."""
    reply = CardText(why=GOOD.why, message="Nathalie told me to ask you. Could you help me?", subject=GOOD.subject)
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card["why"] == GOOD.why
    assert card["message"] == ""
    assert card["subject"] == GOOD.subject


def test_a_common_word_is_not_taken_for_a_name():
    """The French word "côté" is not the last name "Côté": only a word with a capital letter can be a name."""
    reply = CardText(
        why="a rédigé le guide du formulaire",
        message="De mon côté, j'ai besoin d'un portable. Pourriez-vous m'aider ?",
        subject="Aide pour le formulaire",
    )
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "fr", [PERSON_1])["cards"][0]
    assert card["message"] == "De mon côté, j'ai besoin d'un portable. Pourriez-vous m'aider ?"

    # With its capital letter, the same word is a last name of the directory
    reply = CardText(
        why="a rédigé le guide du formulaire", message="Madame Côté m'a parlé de vous.", subject="Aide pour le formulaire"
    )
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "fr", [PERSON_1])["cards"][0]
    assert card["message"] == ""


def test_a_text_with_an_address_or_a_link_comes_back_empty():
    """Emails and links come from the data too: the LLM's text may hold none."""
    reply = CardText(
        why="wrote the guide, see https://example.com/guide",
        message="Write to me at someone@tamberly.example when you can.",
        subject="See www.example.com",
    )
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card == EMPTY


def test_a_text_that_is_too_long_comes_back_empty():
    """A message far longer than asked would not fit in a link, and a subject is a few words: both are thrown away."""
    reply = CardText(
        why=GOOD.why,
        message="Could you help me? " * (MAX_MESSAGE_LENGTH // 10),
        subject="Help with the laptop order form " * (MAX_SUBJECT_LENGTH // 10),
    )
    card = writer_with(FakeLlm(replies=[reply])).write(QUESTION, "en", [PERSON_1])["cards"][0]
    assert card["why"] == GOOD.why
    assert card["message"] == ""
    assert card["subject"] == ""


def test_a_failed_call_gives_empty_texts_not_an_error():
    """OpenAI can't be reached: the people are already found, so each card comes back with empty texts."""
    result = writer_with(FakeLlm(fails=True)).write(QUESTION, "en", [PERSON_1, PERSON_2])
    assert result == {"cards": [EMPTY, {**EMPTY, "person": "p902"}]}


def test_nobody_to_write_for_means_no_call():
    """With no person, the model is not called at all."""
    assert writer_with(FakeLlm(fails=True)).write(QUESTION, "en", []) == {"cards": []}


def test_the_prompt_holds_the_request_the_evidence_and_the_language(scenarios):
    """The prompt shows the request and what the person did, and asks for the language of the question."""
    writer = CardWriter()
    prompt = writer.generate_prompt(QUESTION, "fr", PERSON_1["evidence"])

    assert QUESTION in prompt
    assert 'wrote the Confluence page "Laptop order form: guide"' in prompt
    assert 'handled the Jira ticket "The form loses the delivery address"' in prompt
    assert "in French" in prompt
    assert "in English" in writer.generate_prompt(QUESTION, "en", PERSON_1["evidence"])
    # Its examples are made up: it never quotes a question of the demo scenarios
    for case in scenarios.values():
        for turn in case["turns"]:
            assert turn["question"] not in prompt


def test_the_prompt_of_the_second_level_never_says_that_the_person_worked_on_the_request():
    """The second level: the person works on the system that the request names, and the prompt says that nothing more is known."""
    writer = CardWriter()
    exact = writer.generate_prompt(QUESTION, "en", PERSON_1["evidence"])
    system = writer.generate_prompt(QUESTION, "en", PERSON_1["evidence"], level="system")

    # The first level: the evidence is about the request, so the person is the one who did the work
    assert "The tool found a person who can help" in exact
    assert "this person is the one who did it" in exact
    # The second level: six lines say what the evidence proves, and what it does not
    assert "The tool found nobody who worked on this exact request" in system
    assert "a person who works on the same system" in system
    assert "Never say or suggest that this person worked on the request itself" in system
    assert "this person may not be the one" in system
    assert "never says or suggests that this person did, fixed, decided, or knows what the request asks about" in system
    # And the lines of the first level are not in it
    assert "The tool found a person who can help" not in system
    assert "this person is the one who did it" not in system
    assert "The tool has already found this person" not in system
    # The request, the evidence, and the other rules are the same at both levels
    for prompt in (exact, system):
        assert QUESTION in prompt
        assert 'wrote the Confluence page "Laptop order form: guide"' in prompt
        assert "Never write the name of a person" in prompt


def test_the_level_reaches_every_call_of_the_model():
    """The first calls, and the call that asks again for a message, all get the prompt of the level of the answer."""
    # The two messages end with the same question, so the second one is asked for again
    same_ending = CardText(why=OTHER.why, message="I need to order a laptop. Could you help me?", subject=OTHER.subject)

    second_level = FakeLlm(replies=[GOOD, same_ending], again=[OTHER])
    writer_with(second_level).write(QUESTION, "en", [PERSON_1, PERSON_2], "system")
    first_level = FakeLlm(replies=[GOOD, same_ending], again=[OTHER])
    writer_with(first_level).write(QUESTION, "en", [PERSON_1, PERSON_2])

    marker = "The tool found nobody who worked on this exact request"
    assert len(second_level.prompts) == 2 and len(second_level.again_prompts) == 1
    assert all(marker in prompt for prompt in second_level.prompts + second_level.again_prompts)
    assert len(first_level.prompts) == 2 and len(first_level.again_prompts) == 1
    assert not any(marker in prompt for prompt in first_level.prompts + first_level.again_prompts)


def test_the_prompt_shows_a_ticket_by_its_summary_never_by_its_number():
    """The LLM gets no ticket number, so a message can't turn into a list of ticket numbers."""
    prompt = CardWriter().generate_prompt(QUESTION, "en", PERSON_1["evidence"] + PERSON_2["evidence"])

    assert "The form loses the delivery address" in prompt and "New laptops for the sales team" in prompt
    for number in ["LAP-1", "LAP-7", "pg901"]:
        assert number not in prompt
