"""Free tests of the text that an MCP tool gives back: what AnswerWriter writes for each kind of answer. No OpenAI calls.

The answers are built by the real graph with fake LLM steps (the agent helper of conftest.py), then written as text.
The text is what an AI assistant reads, so these tests check what it holds, and what it leaves out.
"""

from typing import Dict

import pytest

from config.texts import ASK_USER_TEXTS, FAILSAFE_TEXTS, NOBODY_FOUND_TEXTS, TOOL_TEXTS
from mcp_server.answer_writer import AnswerWriter

# A question for the tests where the fakes decide the answer, so the words of the question don't matter
QUESTION = "Who can help me order a laptop?"


@pytest.fixture(scope="module")
def writer() -> AnswerWriter:
    """The class that writes an answer as text. It keeps nothing, so one is enough for all the tests of this file."""
    return AnswerWriter()


def expert_answer(agent, scenarios: Dict, case_id: str, language: str = "en") -> Dict:
    """The answer to the first question of a scenario, with fakes that find and keep the evidence the scenario lists."""
    workflow, fakes = agent
    turn = scenarios[case_id]["turns"][0]
    fakes.understood = {"road": "expert", "question_type": "help", "language": language, "search_words": ["laptop"]}
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    return workflow.full_pipeline(turn["question"])


def person_answer(agent, name: str, asks: str, language: str = "en") -> Dict:
    """The answer to a question about a colleague, built by the real graph with a fake understand step."""
    workflow, fakes = agent
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": language,
        "search_words": [],
        "person_name": name,
        "person_asks": asks,
    }
    return workflow.full_pipeline("A question about a colleague")


def vague_answer(agent, scenarios: Dict) -> Dict:
    """The answer to the vague question of scenario 8: the agent asks which API."""
    workflow, fakes = agent
    turn = scenarios["s08a"]["turns"][0]
    fakes.understood = {
        "road": "unclear",
        "question_type": "help",
        "language": "en",
        "search_words": ["API"],
        "unclear_systems": turn["expected"]["choices_systems"],
    }
    return workflow.full_pipeline(turn["question"])


def thread_line(answer: Dict) -> str:
    """The last line of every text: the id of the conversation."""
    return TOOL_TEXTS["thread"].format(thread_id=answer["thread_id"])


# ----------------------------------------------------------------------
# An expert answer: the note, then the cards
# ----------------------------------------------------------------------


def test_scenario_1_as_text(agent, scenarios, writer):
    """Scenario 1: three cards, best first, each written once with its email, its reason, its evidence, and its message."""
    answer = expert_answer(agent, scenarios, "s01")
    text = writer.write(answer)
    lines = text.splitlines()

    assert len(answer["cards"]) == 3
    for position, card in enumerate(answer["cards"], start=1):
        assert lines.count(f"{position}. {card['name']}, {card['job_title']}, {card['team']}") == 1
        assert lines.count(f"   Email: {card['email']}") == 1
        # The fake LLM step writes the same reason and the same subject for everyone, so these two lines repeat
        assert f"   Why: {card['why']}" in lines
        # One line per ticket or page: what the person did, in words, and its date
        for item in card["evidence"]:
            assert f"   - {item['text']} ({item['date_text']})" in lines
        assert lines.count(f'   Suggested message: "{card["message"]}"') == 1
        assert f"   Email subject: {card['subject']}" in lines
    # The cards keep the order of the answer: the first card is the first person in the text
    positions = [text.index(f"{position}. {card['name']}") for position, card in enumerate(answer["cards"], start=1)]
    assert positions == sorted(positions)
    # Each card has each of its labels once
    for label in ["   Why: ", "   Evidence:", "   Suggested message: ", "   Email subject: "]:
        assert sum(line.startswith(label) for line in lines) == 3


def test_the_note_comes_before_the_first_card(agent, scenarios, writer, opted_out_names_in):
    """Scenario 1: the note names the colleague who left, and only counts the one who opted out, just before the cards."""
    answer = expert_answer(agent, scenarios, "s01")
    text = writer.write(answer)

    assert text.count(answer["note"]) == 1
    assert "no longer works at the company" in answer["note"] and "1 person opted out of being found." in answer["note"]
    assert text.index(answer["note"]) < text.index(f"1. {answer['cards'][0]['name']}")
    # The text is built from the answer, so it names nobody that the answer does not name
    assert opted_out_names_in({"text": text}) == []


def test_the_label_of_the_second_level_is_the_first_line_of_the_text(agent, writer):
    """Nothing is about the exact need: the text starts by saying so, before the people who work on the system."""
    workflow, fakes = agent
    fakes.understood = {
        "road": "expert",
        "question_type": "help",
        "language": "en",
        "search_words": ["laptop"],
        "named_systems": ["broker_portal"],
    }
    # Two searches, and verify keeps nothing
    fakes.found = [["pg004"], ["pg014"]]
    answer = workflow.full_pipeline(QUESTION)
    text = writer.write(answer)

    assert answer["level"] == "system" and len(answer["cards"]) == 1
    # An assistant reads the label first, so it can't present these people as the ones who solved the problem
    assert text.startswith("I found no ticket or page about this exact question. Here is who works on Broker Portal")
    assert text.index(answer["note"]) < text.index(f"1. {answer['cards'][0]['name']}")


def test_the_text_leaves_out_the_links_and_the_step_lines(agent, scenarios, writer):
    """An assistant can't click a link, and it does not wait in front of a screen: neither is in the text."""
    answer = expert_answer(agent, scenarios, "s01")
    text = writer.write(answer)

    for card in answer["cards"]:
        assert card["teams_link"] not in text and card["email_link"] not in text
    assert "https://" not in text and "mailto:" not in text
    assert "Send on Teams" not in text and "Send by email" not in text
    assert len(answer["steps"]) == 6
    for step in answer["steps"]:
        assert step not in text


def test_a_message_keeps_its_two_placeholders(agent, scenarios, writer):
    """The tools take no name and no team: each message keeps [your name] and [your team], for the assistant to fill in."""
    answer = expert_answer(agent, scenarios, "s01")
    text = writer.write(answer)

    assert text.count("I'm [your name] from [your team].") == 3


def test_someone_who_is_away_has_the_out_of_office_line(agent, scenarios, writer):
    """Scenario 1: the first person is out of office, and her card says until when. The two other cards have no such line."""
    answer = expert_answer(agent, scenarios, "s01")
    lines = writer.write(answer).splitlines()

    assert answer["cards"][0]["out_of_office_text"] == "Out of office until 10 November 2026"
    assert lines.count("   Out of office until 10 November 2026") == 1
    assert lines.index("   Out of office until 10 November 2026") < lines.index("   Evidence:")
    assert len([line for line in lines if "Out of office" in line]) == 1


def test_a_french_answer_has_french_labels(agent, scenarios, writer):
    """Scenario 4: the labels of a card and the dates are in French, like the rest of the answer."""
    answer = expert_answer(agent, scenarios, "s04", language="fr")
    text = writer.write(answer)

    for label in ["Courriel :", "Pourquoi :", "Références :", "Message suggéré :", "Objet du courriel :"]:
        assert label in text
    assert "Email:" not in text and "Why:" not in text
    assert "« Guide de traduction du portail client » (mise à jour le 25 août 2026)" in text
    # The few lines for the assistant are in English in every answer
    assert text.splitlines()[-1] == thread_line(answer)


def test_everyone_removed_is_the_fixed_text_then_the_note(agent, writer):
    """The only person behind the evidence left: "nobody found", then the note that still says who was removed."""
    workflow, fakes = agent
    # pg002 is the old access guide. Its author left the company
    fakes.found = [["pg002"]]
    fakes.relevant = ["pg002"]
    answer = workflow.full_pipeline(QUESTION)
    text = writer.write(answer)

    assert answer["status"] == "nobody_found" and answer["note"]
    assert text.split("\n\n") == [NOBODY_FOUND_TEXTS["general"]["en"], answer["note"], thread_line(answer)]


# ----------------------------------------------------------------------
# A refusal and "nobody found": a fixed text
# ----------------------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "fr"])
def test_a_refusal_is_its_fixed_text(agent, writer, language):
    """A question that is not about work: the polite refusal in the language of the question, and the id. Nothing else."""
    workflow, fakes = agent
    fakes.understood = {"road": "not_work", "question_type": "help", "language": language, "search_words": []}
    answer = workflow.full_pipeline("What should I cook tonight?")

    assert writer.write(answer) == f"{FAILSAFE_TEXTS['not_work'][language]}\n\n{thread_line(answer)}"


def test_nobody_found_is_its_fixed_text(agent, writer):
    """Nothing holds up: the "nobody found" text, and the id. No card, and no note."""
    workflow, fakes = agent
    # pg004 is the guide of another system, and the fake verify keeps nothing
    fakes.found = [["pg004"]]
    answer = workflow.full_pipeline(QUESTION)

    assert writer.write(answer) == f"{NOBODY_FOUND_TEXTS['general']['en']}\n\n{thread_line(answer)}"


# ----------------------------------------------------------------------
# A question about a colleague: the sentence, then the person card
# ----------------------------------------------------------------------


def test_a_person_card_as_text(agent, writer):
    """ "Who is Sophie Martin's manager?": the sentence that answers, then the card of the manager, from the directory."""
    answer = person_answer(agent, "Sophie Martin", "manager")
    card = answer["person_card"]
    text = writer.write(answer)
    lines = text.splitlines()

    assert lines[0] == answer["message"] == "Sophie Martin's manager is Hélène Dubois."
    assert lines.count(f"{card['name']}, {card['job_title']}, {card['team']}") == 1
    assert lines.count(f"   Manager: {card['manager']}") == 1
    assert lines.count(f"   Email: {card['email']}") == 1
    assert lines.count("   Languages: French, English") == 1
    # The work phone was not asked for, so the text has no such line. And a person card has no link either
    assert not any("Work phone:" in line for line in lines)
    assert "https://" not in text and "mailto:" not in text
    assert lines[-1] == thread_line(answer)


def test_the_work_phone_is_only_written_when_it_is_asked_for(agent, writer):
    """ "What's her work phone?": the fake number of the directory is in the sentence and on the card, in French here."""
    answer = person_answer(agent, "Hélène Dubois", "work_phone", language="fr")
    phone = answer["person_card"]["work_phone"]
    text = writer.write(answer)

    assert phone.startswith("514-555-01")
    assert f"   Téléphone au travail : {phone}" in text.splitlines()
    for label in ["Gestionnaire :", "Courriel :", "Langues :"]:
        assert label in text


def test_the_work_of_a_colleague_is_written_by_system(agent, writer):
    """ "What does she work on?": one group per system, and one line per ticket or page with its date."""
    answer = person_answer(agent, "Hélène Dubois", "work")
    text = writer.write(answer)
    lines = text.splitlines()

    groups = answer["person_card"]["work"]
    assert len(groups) >= 2
    for group in groups:
        assert lines.count(f"   {group['system']}") == 1
        for item in group["items"]:
            assert lines.count(f"   - {item['text']} ({item['date_text']})") == 1
    assert "(updated 26 October 2026)" in text and "(meeting of 10 September 2026)" in text


def test_is_she_away_writes_its_sentence_before_the_card(agent, writer):
    """ "Is she away?": the sentence says what the directory says, then the card. Never a reason."""
    answer = person_answer(agent, "Hélène Dubois", "out_of_office")
    text = writer.write(answer)

    assert text.startswith("Hélène Dubois is not marked as out of office.\n\nHélène Dubois, Team Lead, Claims Platform\n")
    assert "Out of office until" not in text


def test_someone_who_left_is_one_sentence_and_no_card(agent, writer):
    """Someone who left: the sentence, the id of the conversation, and nothing that looks like a card."""
    answer = person_answer(agent, "Tom Walsh", "card")

    assert writer.write(answer) == f"Tom Walsh no longer works at the company.\n\n{thread_line(answer)}"


# ----------------------------------------------------------------------
# A question of the agent: its choices, each with the id to send back
# ----------------------------------------------------------------------


def test_which_system_is_written_with_the_id_of_each_choice(agent, scenarios, writer):
    """Scenario 8: the text tells the assistant to ask the user, shows the two systems, and says how to send the pick."""
    answer = vague_answer(agent, scenarios)
    parts = writer.write(answer).split("\n\n")

    assert answer["status"] == "needs_details"
    claims, policy = answer["choices"]
    assert parts == [
        TOOL_TEXTS["ask_the_user"],
        ASK_USER_TEXTS["system"]["en"],
        f"- Claims API (choice_id: claims_api): {claims['detail']}\n- Policy API (choice_id: policy_api): {policy['detail']}",
        TOOL_TEXTS["how_to_pick"],
        thread_line(answer),
    ]
    # The two lines for the assistant name the tool to call, and say that the pick is the user's
    assert "pick_choice" in TOOL_TEXTS["how_to_pick"] and "Do not pick for the user" in TOOL_TEXTS["how_to_pick"]


def test_which_person_is_written_with_a_job_title_and_a_team(agent, writer):
    """Scenario 12: two people are called Sophie. Each choice shows the person id to send back, and what tells them apart."""
    answer = person_answer(agent, "Sophie", "card")
    lines = writer.write(answer).splitlines()

    assert ASK_USER_TEXTS["person"]["en"] in lines
    assert [line for line in lines if line.startswith("- ")] == [
        f"- {choice['name']} (choice_id: {choice['id']}): {choice['detail']}" for choice in answer["choices"]
    ]
    assert [choice["name"] for choice in answer["choices"]] == ["Sophie Martin", "Sophie Nguyen"]


def test_a_choice_with_no_detail_is_only_a_name_and_an_id(writer):
    """Someone who left only shows a name in the choices: the line then ends after the id."""
    assert writer._write_choice({"id": "p099", "name": "Someone Gone", "detail": ""}) == "- Someone Gone (choice_id: p099)"


def test_an_answer_that_nothing_waits_for_has_no_choice_to_pick(agent, writer):
    """A pick arrives and the agent asked nothing: the fixed text says so, and the text does not ask for a pick."""
    workflow, _ = agent
    answer = workflow.full_pipeline("claims_api", "nothing-waits-here", is_answer=True)
    text = writer.write(answer)

    assert text == f"{ASK_USER_TEXTS['not_waiting']['en']}\n\nthread_id: nothing-waits-here"
    assert "pick_choice" not in text


# ----------------------------------------------------------------------
# Every text ends with the id of its conversation
# ----------------------------------------------------------------------


def test_every_text_ends_with_the_id_of_its_conversation(agent, scenarios, writer):
    """Cards, a person card, a question of the agent: the last line is always the id, after a blank line."""
    answers = [
        expert_answer(agent, scenarios, "s01"),
        person_answer(agent, "Sophie Martin", "manager"),
        vague_answer(agent, scenarios),
    ]
    for answer in answers:
        lines = writer.write(answer).splitlines()
        assert len(answer["thread_id"]) == 32
        assert lines[-2:] == ["", f"thread_id: {answer['thread_id']}"]
        assert sum(line.startswith("thread_id:") for line in lines) == 1
