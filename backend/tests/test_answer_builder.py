"""Free tests of the answer: the cards, the suggested message, the two links, and the note. No OpenAI calls.

The answer is built in plain code, from the real data. Each test prepares the state the graph would end with:
the agent's own ranking and HR check, applied to the evidence that data/scenarios.json lists for a scenario.
Nothing is searched, and no model is called.
"""

import json
import re
from typing import Dict, List, Optional
from urllib.parse import parse_qs, quote

import pytest

from agents.answer_builder import AnswerBuilder
from agents.hr_checker import HrChecker
from agents.ranker import Ranker
from config.constants import MAX_USER_TEXT_LENGTH
from config.texts import ASK_USER_TEXTS, FAILSAFE_TEXTS, MESSAGE_TEXTS, NOBODY_FOUND_TEXTS, NOTE_TEXTS
from sources import CompanySource, EvidenceSource, HrSource, PeopleSource


@pytest.fixture(scope="module")
def evidence() -> EvidenceSource:
    """The evidence items of the real data. Read once for all the tests of this file."""
    return EvidenceSource()


@pytest.fixture(scope="module")
def builder(evidence) -> AnswerBuilder:
    """The class under test."""
    return AnswerBuilder(evidence)


@pytest.fixture(scope="module")
def people() -> Dict:
    """The directory, by person id."""
    return {person["id"]: person for person in PeopleSource().list_people()}


def state_from(
    evidence: EvidenceSource, item_ids: List[str], question: str, question_type: str = "help", language: str = "en"
) -> Dict:
    """The state the graph ends with when verify keeps these tickets and pages. Only the keys the answer reads."""
    pieces = [piece for item_id in item_ids for piece in evidence.get_pieces(item_id)]
    ranking = Ranker().rank(pieces, question_type)
    checked = HrChecker().check(ranking)
    return {
        "question": question,
        "road": "expert",
        "language": language,
        "message": "",
        "ranking": ranking,
        "recommended": checked["recommended"],
        "removed_left": checked["removed_left"],
        "removed_opted_out": checked["removed_opted_out"],
        # No text from the LLM, unless a test adds some
        "cards": [],
        # Nothing from the person road
        "person_matches": [],
        "person_card": {},
    }


def state_for(evidence: EvidenceSource, scenarios: Dict, case_id: str, language: Optional[str] = None) -> Dict:
    """The same, for the first question of a demo scenario and the evidence the scenario lists."""
    turn = scenarios[case_id]["turns"][0]
    expected = turn["expected"]
    return state_from(
        evidence, expected["evidence"], turn["question"], expected["question_type"], language or expected["language"]
    )


# ----------------------------------------------------------------------
# The cards
# ----------------------------------------------------------------------


def test_a_card_shows_what_the_data_says(builder, evidence, scenarios, people):
    """Scenario 1: the cards are the expected people, and each one shows the directory's values."""
    expected = scenarios["s01"]["turns"][0]["expected"]
    result = builder.build(state_for(evidence, scenarios, "s01"))
    team_names = {team["id"]: team["name"] for team in CompanySource().list_teams()}

    assert result["status"] == "answered"
    assert sorted(card["id"] for card in result["cards"]) == sorted(expected["people"])
    for card in result["cards"]:
        person = people[card["id"]]
        assert card["name"] == person["name"]
        assert card["job_title"] == person["job_title"]
        assert card["team"] == team_names[person["team"]]
        assert card["email"] == person["email"] and card["email"].endswith(".example")
        assert card["evidence"]


def test_the_evidence_of_a_card_lists_pages_first_then_tickets(builder, evidence, scenarios):
    """Scenario 1, first card: the page she wrote, then the three tickets she handled."""
    card = builder.build(state_for(evidence, scenarios, "s01"))["cards"][0]
    assert [(label["id"], label["kind"]) for label in card["evidence"]] == [
        ("pg008", "wrote"),
        ("CLM-212", "assigned"),
        ("CLM-245", "assigned"),
        ("CLM-301", "assigned"),
    ]
    assert card["evidence"][0]["title"] == "Claims API: Access Guide"
    assert card["evidence"][0]["source"] == "Confluence"


def test_each_piece_of_evidence_says_what_the_person_did_and_when(builder, evidence, scenarios):
    """Scenario 1, first card: one line per page or ticket, in words, with a date in words like the out-of-office date."""
    card = builder.build(state_for(evidence, scenarios, "s01"))["cards"][0]
    page, ticket = card["evidence"][0], card["evidence"][1]

    assert page["text"] == 'wrote "Claims API: Access Guide"'
    assert ticket["text"] == f"handled CLM-212: {evidence.get_item('CLM-212')['title']}"
    # The date of a doc is its last update, and the date of a resolved ticket is the day it was resolved
    assert page["date_text"] == "updated " + builder._date_in_words(evidence.get_item("pg008")["date"], "en")
    assert ticket["date_text"] == "resolved " + builder._date_in_words(evidence.get_item("CLM-212")["date"], "en")
    for label in card["evidence"]:
        assert re.fullmatch(r"(updated|resolved) \d{1,2} [A-Z][a-z]+ \d{4}", label["date_text"])


def test_the_evidence_of_a_french_answer_is_in_french(builder, evidence, scenarios):
    """Scenario 4: the lines of the evidence and their dates are in the language of the question."""
    card = builder.build(state_for(evidence, scenarios, "s04"))["cards"][0]
    texts = [label["text"] for label in card["evidence"]]

    assert texts[0] == "a rédigé « Guide de traduction du portail client »"
    assert texts[1].startswith("a traité DIG-141 : ")
    assert re.fullmatch(r"mise à jour le \d{1,2}(er)? [a-zéû]+ \d{4}", card["evidence"][0]["date_text"])
    assert re.fullmatch(r"(résolu|mise à jour) le \d{1,2}(er)? [a-zéû]+ \d{4}", card["evidence"][1]["date_text"])


def test_an_answer_shows_no_date_as_the_data_writes_it(builder, evidence, scenarios):
    """Every date of an answer is in words, except the out-of-office date, which stays next to its text as data."""
    result = builder.build(state_for(evidence, scenarios, "s01"))
    for card in result["cards"]:
        assert not re.search(r"\d{4}-\d{2}-\d{2}", json.dumps(card["evidence"]))
        # A piece of evidence shows these six values, and nothing else
        for label in card["evidence"]:
            assert sorted(label) == ["date_text", "id", "kind", "source", "text", "title"]


@pytest.mark.parametrize(
    "language, labels",
    [
        ("en", {"evidence": "Evidence", "message": "Suggested message", "teams": "Send on Teams", "email": "Email"}),
        ("fr", {"evidence": "Références", "message": "Message suggéré", "teams": "Envoyer sur Teams", "email": "Courriel"}),
    ],
)
def test_an_answer_carries_the_labels_of_a_card_in_its_language(builder, evidence, scenarios, language, labels):
    """The page shows the same words as the terminal: every answer has the labels of a card, without their colon."""
    result = builder.build(state_for(evidence, scenarios, "s01", language=language))

    for name, text in labels.items():
        assert result["labels"][name] == text
    # A label is a word or two: no colon, and no placeholder to fill
    for text in result["labels"].values():
        assert text and ":" not in text and "{" not in text
    assert "out_of_office" not in result["labels"]


@pytest.mark.parametrize("case_id", ["s01", "s02", "s14"])
def test_out_of_office_only_shows_when_the_date_is_today_or_later(builder, evidence, scenarios, case_id):
    """Scenario 1 shows one date. In scenarios 2 and 14, the first card has a date in the past: it is not shown."""
    result = builder.build(state_for(evidence, scenarios, case_id))
    shown = {card["id"]: card["out_of_office_until"] for card in result["cards"] if card["out_of_office_until"]}
    assert shown == scenarios[case_id]["turns"][0]["expected"]["out_of_office"]


# ----------------------------------------------------------------------
# The suggested message and the two links
# ----------------------------------------------------------------------


def test_the_message_is_the_llm_middle_between_two_sentences_of_the_code(builder, evidence, scenarios, people):
    """The first name comes from the directory. The LLM only wrote the middle, and its "why" sentence is shown as it is."""
    state = state_for(evidence, scenarios, "s01")
    # The second person of scenario 1 is not out of office, so the message is the three plain parts
    second = state["recommended"][1]["person"]
    state["cards"] = [{"person": second, "why": "approved the requests", "message": "I need access. Could you help me?"}]
    card = builder.build(state)["cards"][1]

    assert card["why"] == "approved the requests"
    assert card["message"] == (
        f"Hi {people[second]['first_name']}, I'm [your name] from [your team]. "
        "I need access. Could you help me? Thank you!"
    )


# ----------------------------------------------------------------------
# The two optional boxes: my name and my team
# ----------------------------------------------------------------------


def test_my_name_and_my_team_fill_the_first_sentence(builder, evidence, scenarios, people):
    """What I typed in the two boxes takes the place of [your name] and [your team], in every card of the answer."""
    state = state_for(evidence, scenarios, "s01")
    cards = builder.build(state, user_name="Alex", user_team="Pricing")["cards"]

    assert len(cards) == 3
    for card in cards:
        assert card["message"].startswith(f"Hi {people[card['id']]['first_name']}, I'm Alex from Pricing. ")
        assert "[your name]" not in card["message"] and "[your team]" not in card["message"]


@pytest.mark.parametrize(
    "boxes, opening",
    [
        ({}, "I'm [your name] from [your team]."),
        ({"user_name": "Alex"}, "I'm Alex from [your team]."),
        ({"user_team": "Pricing"}, "I'm [your name] from Pricing."),
        ({"user_name": "   ", "user_team": ""}, "I'm [your name] from [your team]."),
    ],
    ids=["both empty", "the name only", "the team only", "only spaces"],
)
def test_an_empty_box_keeps_its_placeholder(builder, evidence, scenarios, boxes, opening):
    """A box that I left empty keeps its placeholder, so I still see what to fill in before I send the message."""
    card = builder.build(state_for(evidence, scenarios, "s01"), **boxes)["cards"][0]
    assert opening in card["message"]


def test_both_links_hold_my_name_and_my_team(builder, evidence, scenarios):
    """The two links are built from the filled message: Teams and the email app open with my name and my team in it."""
    card = builder.build(state_for(evidence, scenarios, "s01"), user_name="Alex Élie", user_team="Pricing & Data")["cards"][0]

    assert "I'm Alex Élie from Pricing & Data." in card["message"]
    assert parse_qs(card["teams_link"].split("?", 1)[1])["message"] == [card["message"]]
    assert parse_qs(card["email_link"].split("?", 1)[1])["body"] == [card["message"]]


def test_what_i_type_in_a_box_stays_on_one_line_and_short(builder, evidence, scenarios):
    """A line break or a very long text in a box can't break the message: one line, and no longer than a box accepts."""
    cards = builder.build(state_for(evidence, scenarios, "s01"), user_name="Alex\n\n  Tremblay", user_team="x" * 500)["cards"]

    assert "I'm Alex Tremblay from " in cards[0]["message"]
    assert "x" * (MAX_USER_TEXT_LENGTH + 1) not in cards[0]["message"]
    assert "x" * MAX_USER_TEXT_LENGTH in cards[0]["message"]


def test_the_two_boxes_work_in_french(builder, evidence, scenarios):
    """Scenario 4: the French first sentence, with my name and my team, or with the French placeholders."""
    filled = builder.build(state_for(evidence, scenarios, "s04"), user_name="Alex", user_team="Tarification")["cards"][0]
    empty = builder.build(state_for(evidence, scenarios, "s04"))["cards"][0]

    assert filled["message"].startswith("Bonjour Marc-André, je suis Alex, de l'équipe Tarification. ")
    assert empty["message"].startswith("Bonjour Marc-André, je suis [votre nom], de l'équipe [votre équipe]. ")


def test_my_name_and_my_team_are_nowhere_else_in_the_answer(builder, evidence, scenarios):
    """The two boxes only change the messages and their links: every other part of the answer is the same without them."""
    state = state_for(evidence, scenarios, "s01")
    plain = builder.build(state)
    filled = builder.build(state, user_name="Zebulon", user_team="Quokka")

    for card in filled["cards"]:
        # The three parts that hold the message say the name. No other part of a card does
        for key, value in card.items():
            holds_it = "Zebulon" in json.dumps(value) and "Quokka" in json.dumps(value)
            assert holds_it == (key in ["message", "teams_link", "email_link"])
    # And nothing outside the cards changed
    for key in ["status", "message", "note", "choices", "person_card", "removed_left", "removed_opted_out"]:
        assert filled[key] == plain[key]


# ----------------------------------------------------------------------
# Out of office: a date in words, and one more sentence in the message
# ----------------------------------------------------------------------


def test_out_of_office_is_a_date_in_words(builder, evidence, scenarios):
    """Scenario 1: the first card says "Out of office until 10 November 2026", and the date stays as data next to it."""
    english = builder.build(state_for(evidence, scenarios, "s01"))["cards"]
    french = builder.build(state_for(evidence, scenarios, "s01", language="fr"))["cards"]

    assert english[0]["out_of_office_until"] == "2026-11-10"
    assert english[0]["out_of_office_text"] == "Out of office until 10 November 2026"
    assert french[0]["out_of_office_text"] == "Absence du bureau jusqu'au 10 novembre 2026"
    # Someone who is not away has no such line
    assert english[1]["out_of_office_until"] == "" and english[1]["out_of_office_text"] == ""


@pytest.mark.parametrize(
    "day, language, words",
    [
        ("2026-11-10", "en", "10 November 2026"),
        ("2026-11-10", "fr", "10 novembre 2026"),
        ("2027-01-01", "en", "1 January 2027"),
        ("2027-01-01", "fr", "1er janvier 2027"),
        ("2026-08-09", "fr", "9 août 2026"),
        ("2026-12-31", "en", "31 December 2026"),
    ],
)
def test_a_date_is_written_in_words_with_the_day_first(builder, day, language, words):
    """Dates are written like the titles of the company's own pages. French writes the first day of a month "1er"."""
    assert builder._date_in_words(day, language) == words
    # Without the year, for a sentence of a message: "10 November"
    assert builder._date_in_words(day, language, with_year=False) == words.rsplit(" ", 1)[0]


def test_the_message_to_someone_who_is_away_says_so(builder, evidence, scenarios):
    """Scenario 1: the message to the first person has one more sentence of the code, just before the last one."""
    english = builder.build(state_for(evidence, scenarios, "s01"))["cards"]
    french = builder.build(state_for(evidence, scenarios, "s01", language="fr"))["cards"]

    assert english[0]["message"].endswith(" I see you're away until 10 November, so no rush. Thank you!")
    assert french[0]["message"].endswith(
        " Je vois que vous êtes à l'extérieur du bureau jusqu'au 10 novembre, alors rien ne presse. Merci !"
    )
    # The others are not away: their message has no such sentence, and no date at all
    for card in english[1:] + french[1:]:
        assert "away until" not in card["message"] and "jusqu'au" not in card["message"]
        assert not re.search(r"\d{4}", card["message"])


def test_someone_whose_absence_is_over_gets_no_away_sentence(builder, evidence, scenarios):
    """Scenario 2: the first person was away until a date in the past, so the message says nothing about it."""
    card = builder.build(state_for(evidence, scenarios, "s02"))["cards"][0]

    assert card["out_of_office_text"] == ""
    assert "away" not in card["message"]


# ----------------------------------------------------------------------
# The subject of the email
# ----------------------------------------------------------------------


def test_the_subject_of_the_llm_is_the_subject_of_the_email(builder, evidence, scenarios):
    """The LLM wrote a subject that passed the checks: the card shows it, and the email link carries it."""
    state = state_for(evidence, scenarios, "s01")
    first = state["recommended"][0]["person"]
    state["cards"] = [{"person": first, "why": "", "message": "", "subject": "Access to the claims data"}]
    card = builder.build(state)["cards"][0]

    assert card["subject"] == "Access to the claims data"
    assert parse_qs(card["email_link"].split("?", 1)[1])["subject"] == ["Access to the claims data"]


@pytest.mark.parametrize(
    "case_id, subject",
    [("s01", "Claims API: a question"), ("s04", "Customer Portal : une question"), ("s02", "Pricing Engine: a question")],
)
def test_without_a_subject_of_the_llm_the_code_builds_one_from_the_system(builder, evidence, scenarios, case_id, subject):
    """The LLM's subject is missing or was thrown away: the subject names the system of the person's evidence."""
    state = state_for(evidence, scenarios, case_id)
    state["cards"] = [{"person": state["recommended"][0]["person"], "why": "", "message": "", "subject": ""}]
    card = builder.build(state)["cards"][0]

    assert card["subject"] == subject
    assert parse_qs(card["email_link"].split("?", 1)[1])["subject"] == [subject]


def test_evidence_about_no_system_gets_the_general_subject(builder, evidence):
    """A general page is about no system, so there is nothing to build a subject from: the fixed one is used."""
    # pg014 is the general technology roadmap: its header names no system
    assert evidence.get_item("pg014")["system"] == ""
    result = builder.build(state_from(evidence, ["pg014"], "Who wrote the technology roadmap?"))

    assert len(result["cards"]) == 1
    assert result["cards"][0]["subject"] == MESSAGE_TEXTS["subject"]["en"]


def test_the_subject_is_the_system_with_the_most_evidence(builder, evidence):
    """Evidence on two systems: the subject names the one that most of this person's evidence is about."""
    # p007 has two pieces about Claims Intake and two about Claims Workbench. One more piece decides
    pieces = evidence.list_pieces_of("p007")
    by_system = {}
    for piece in pieces:
        by_system.setdefault(evidence.get_item(piece["item"])["system"], []).append(piece)
    assert len(by_system) == 2
    (first_system, first_pieces), (second_system, second_pieces) = by_system.items()

    more_of_the_second = first_pieces[:1] + second_pieces
    assert builder._plain_subject(more_of_the_second, "en") == f"{evidence.system_names[second_system]}: a question"
    # As many of each: the first one in the order of the evidence
    one_of_each = first_pieces[:1] + second_pieces[:1]
    assert builder._plain_subject(one_of_each, "en") == f"{evidence.system_names[first_system]}: a question"


def test_without_llm_texts_a_card_gets_plain_texts_built_from_the_data(builder, evidence, scenarios):
    """The LLM's texts are missing or were thrown away: the card still has a "why" sentence and a message."""
    state = state_for(evidence, scenarios, "s01")
    state["cards"] = [{"person": state["recommended"][0]["person"], "why": "", "message": ""}]
    card = builder.build(state)["cards"][0]

    assert card["why"] == 'wrote "Claims API: Access Guide" and handled CLM-212, CLM-245 and CLM-301'
    assert state["question"] in card["message"]
    assert card["message"].endswith("Thank you!")


def test_a_french_question_gets_french_texts(builder, evidence, scenarios):
    """Scenario 4: the sentences of the code are in French, and the first name keeps its hyphen and its accent."""
    card = builder.build(state_for(evidence, scenarios, "s04"))["cards"][0]

    assert card["message"].startswith("Bonjour Marc-André, je suis [votre nom], de l'équipe [votre équipe].")
    assert card["message"].endswith("Merci !")
    assert card["why"] == "a rédigé « Guide de traduction du portail client » et a traité DIG-141 et DIG-156"


@pytest.mark.parametrize("case_id", ["s01", "s04"])
def test_both_links_hold_the_email_and_the_whole_message(builder, evidence, scenarios, case_id):
    """Every card has two links, built for its person, and the message comes back whole from each of them."""
    result = builder.build(state_for(evidence, scenarios, case_id))
    assert result["cards"]
    for card in result["cards"]:
        assert card["teams_link"].startswith(f"https://teams.microsoft.com/l/chat/0/0?users={card['email']}&message=")
        assert parse_qs(card["teams_link"].split("?", 1)[1])["message"] == [card["message"]]

        address, query = card["email_link"].removeprefix("mailto:").split("?", 1)
        assert address == card["email"]
        assert card["subject"]
        assert parse_qs(query) == {"subject": [card["subject"]], "body": [card["message"]]}


# ----------------------------------------------------------------------
# The note about the people the HR check removed
# ----------------------------------------------------------------------


def test_the_note_names_who_left_and_only_counts_who_opted_out(builder, evidence, scenarios, people):
    """Scenario 1: the former colleague is named, with what he did. The colleague who opted out is only counted."""
    state = state_for(evidence, scenarios, "s01")
    result = builder.build(state)
    left = people[state["removed_left"][0]]

    assert result["note"] == (
        f'{left["name"]} wrote "Claims API - how to get an API key", but no longer works at the company. '
        "1 person opted out of being found."
    )
    assert result["removed_left"] == [left["id"]]
    assert result["removed_opted_out"] == 1


def test_the_note_is_in_the_language_of_the_question(builder, evidence, scenarios, people):
    """The same note for the same evidence, when the question was asked in French."""
    state = state_for(evidence, scenarios, "s01", language="fr")
    left = people[state["removed_left"][0]]

    assert builder.build(state)["note"] == (
        f'{left["name"]} a rédigé « Claims API - how to get an API key », mais ne travaille plus dans l\'entreprise. '
        "1 personne a choisi de ne pas être trouvée."
    )


@pytest.mark.parametrize("case_id", ["s01", "s05"])
def test_the_answer_never_gives_a_date_from_the_hr_file(builder, evidence, scenarios, case_id):
    """Someone left: the answer says so, but neither their first day nor their last day is anywhere in it."""
    state = state_for(evidence, scenarios, case_id)
    result = builder.build(state)
    everything = json.dumps(result, ensure_ascii=False)

    assert state["removed_left"]
    for record in HrSource().list_records():
        if record["person_id"] in state["removed_left"]:
            assert record["start_date"] not in everything
            assert record["end_date"] not in everything
    # The note holds no date at all
    assert not re.search(r"\d{4}-\d{2}-\d{2}", result["note"])


def test_the_name_of_someone_who_opted_out_is_nowhere_in_the_answer(builder, evidence, scenarios, opted_out_names_in):
    """Scenario 1: a colleague who opted out is behind two tickets, and no part of the answer names this person."""
    state = state_for(evidence, scenarios, "s01")
    assert state["removed_opted_out"]
    assert opted_out_names_in(builder.build(state)) == []


def test_the_check_for_opted_out_names_really_finds_them(opted_out_names_in):
    """A test of the check itself: it sees a name in a text, in lower case, and inside a link."""
    someone = next(person for person in PeopleSource().list_people() if not person["discoverable"])
    both_names = [someone["first_name"], someone["last_name"]]

    assert opted_out_names_in({"note": f"{someone['name']} worked on it."}) == both_names
    assert opted_out_names_in({"cards": [{"why": f"asked {someone['first_name'].lower()} about it"}]}) == both_names[:1]
    assert opted_out_names_in({"link": f"mailto:a@b.example?body=Ask%20{quote(someone['last_name'])}"}) == both_names[1:]
    assert opted_out_names_in({"note": "Nobody is named here."}) == []


def test_nobody_is_removed_means_no_note(builder, evidence, scenarios):
    """Scenario 2: nobody left and nobody opted out, so the note is empty."""
    assert builder.build(state_for(evidence, scenarios, "s02"))["note"] == ""


# ----------------------------------------------------------------------
# The person road: a case that the real data can't produce
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "language, sentence",
    [
        ("en", "{name}'s manager in the directory is {manager}, who no longer works at the company."),
        ("fr", "{name} a pour gestionnaire dans l'annuaire {manager}, qui ne travaille plus dans l'entreprise."),
    ],
)
def test_a_manager_who_left_is_named_and_the_sentence_says_so(builder, people, language, sentence):
    """No manager left the company in the data, so the result of person_card is made by hand here.

    The question was about p012, whose manager, p007, would have left. The sentence names both and says that
    the manager left. It does not say that p012 left, and the manager gets no card: only the name.
    """
    subject, manager = people["p012"], people["p007"]
    state = {
        "question": "Who is her manager?",
        "road": "person",
        "language": language,
        "message": "",
        "ranking": [],
        "recommended": [],
        "removed_left": [],
        "removed_opted_out": [],
        "cards": [],
        "person_matches": ["p012"],
        "person_card": {"subject": "p012", "person": "p007", "asks": "manager", "left": True, "manager": "", "work": []},
    }
    result = builder.build(state)

    assert result["status"] == "person"
    assert result["message"] == sentence.format(name=subject["name"], manager=manager["name"])
    card = result["person_card"]
    assert card["id"] == "p007" and card["name"] == manager["name"] and card["left"] is True
    # Nothing of the directory about someone who left: no contact details, no job title, and no link
    everything = json.dumps(result, ensure_ascii=False)
    for value in [manager["email"], manager["work_phone"], manager["job_title"], subject["email"]]:
        assert value not in everything
    assert "mailto:" not in everything and "teams.microsoft.com" not in everything


# ----------------------------------------------------------------------
# The question of the agent: its text and its choices
# ----------------------------------------------------------------------


def paused_state(road: str, language: str = "en") -> Dict:
    """The state of a run that is paused in ask_user: nothing is found yet. Only the keys the answer reads."""
    return {
        "question": "Who knows the tool?",
        "road": road,
        "language": language,
        "message": "",
        "ranking": [],
        "recommended": [],
        "removed_left": [],
        "removed_opted_out": [],
        "cards": [],
        "person_matches": [],
        "person_card": {},
    }


@pytest.mark.parametrize("language", ["en", "fr"])
def test_the_choices_of_a_question_about_a_system_come_from_the_data(builder, language):
    """ "Which system?": each choice has the id, the name, and the one-line description of a system of the data."""
    systems = {system["id"]: system for system in CompanySource().list_systems()}
    ask = {"asks": "system", "choices": ["claims_api", "policy_api"]}
    result = builder.build(paused_state("unclear", language), ask=ask)

    assert result["status"] == "needs_details"
    assert result["message"] == ASK_USER_TEXTS["system"][language]
    assert result["choices"] == [
        {"id": system_id, "name": systems[system_id]["name"], "detail": systems[system_id]["description"]}
        for system_id in ask["choices"]
    ]
    assert result["cards"] == [] and result["person_card"] == {} and result["note"] == ""


def test_the_choices_of_a_question_about_a_person_show_the_job_title_and_the_team(builder, people):
    """ "Which Sophie?": each choice has the id, the name, and the job title and team of the directory."""
    team_names = {team["id"]: team["name"] for team in CompanySource().list_teams()}
    ask = {"asks": "person", "choices": ["p012", "p026"]}
    result = builder.build(paused_state("person"), ask=ask)

    assert result["status"] == "needs_details"
    assert result["message"] == ASK_USER_TEXTS["person"]["en"]
    assert result["choices"] == [
        {
            "id": person_id,
            "name": people[person_id]["name"],
            "detail": f"{people[person_id]['job_title']}, {team_names[people[person_id]['team']]}",
        }
        for person_id in ask["choices"]
    ]
    # A choice is who the person is, never how to reach them
    everything = json.dumps(result, ensure_ascii=False)
    assert "@" not in everything and "555-01" not in everything


def test_a_choice_who_left_the_company_only_shows_a_name(builder, people):
    """Someone who left can be one of the choices, with the name only: no job title and no team, as on their card."""
    left = next(record["person_id"] for record in HrSource().list_records() if record["employment_status"] == "left")
    ask = {"asks": "person", "choices": [left, "p012"]}
    choices = builder.build(paused_state("person"), ask=ask)["choices"]

    assert choices[0] == {"id": left, "name": people[left]["name"], "detail": ""}
    assert choices[1]["detail"]
    assert people[left]["job_title"] not in json.dumps(choices[0])


@pytest.mark.parametrize("language", ["en", "fr"])
def test_an_answer_that_nothing_waits_for_gets_a_fixed_text(builder, language):
    """An answer arrived and no question was waiting for it: the status asks for details, with a text and no choice."""
    result = builder.build(paused_state("expert", language), ask={"asks": "not_waiting", "choices": []})

    assert result["status"] == "needs_details"
    assert result["message"] == ASK_USER_TEXTS["not_waiting"][language]
    assert result["choices"] == [] and result["cards"] == [] and result["note"] == ""


@pytest.mark.parametrize("language", ["en", "fr"])
def test_the_note_says_when_the_system_stayed_unclear(builder, evidence, scenarios, language):
    """The agent went on without knowing the system (it had already asked its one question): the note says so first."""
    state = state_for(evidence, scenarios, "s01", language=language)
    clear = builder.build(state)["note"]
    state["road"] = "unclear"
    unclear = builder.build(state)

    assert unclear["status"] == "answered"
    assert unclear["note"] == f"{NOTE_TEXTS['unclear_system'][language]} {clear}"
    # While the run is still paused on that question, nothing was searched yet, so the note says nothing
    assert builder.build(paused_state("unclear", language), ask={"asks": "system", "choices": ["claims_api", "policy_api"]})["note"] == ""


# ----------------------------------------------------------------------
# The second level: the people who work on the system that the request names, when nothing is about the exact need
# ----------------------------------------------------------------------


def second_level_state(evidence: EvidenceSource, system_ids: List[str], question: str, language: str = "en") -> Dict:
    """The state the graph ends with after same_system: the tickets and pages of these systems, ranked and checked."""
    state = state_from(evidence, evidence.list_ids_of_systems(system_ids), question, language=language)
    return {**state, "level": "system", "named_systems": system_ids}


def test_the_second_level_is_labelled_before_the_cards(builder, evidence):
    """The note says that nothing is about the exact question, and names the system that the people work on."""
    result = builder.build(second_level_state(evidence, ["broker_portal"], "A broker can't log in. Who can help?"))

    assert result["status"] == "answered"
    assert result["level"] == "system"
    # p008 wrote the page of the Broker Portal and handled its ticket
    assert [card["id"] for card in result["cards"]] == ["p008"]
    assert result["note"] == NOTE_TEXTS["same_system"]["en"].format(systems="Broker Portal")
    assert result["note"] == (
        "I found no ticket or page about this exact question. Here is who works on Broker Portal: a good place to start."
    )


def test_the_label_comes_before_the_people_who_were_removed(builder, evidence, people, opted_out_names_in):
    """Claims Intake: the label first, then the person who left, by name, then a count for the person who opted out."""
    result = builder.build(second_level_state(evidence, ["claims_intake"], "Claims Intake is slow. Who can help?"))
    label = NOTE_TEXTS["same_system"]["en"].format(systems="Claims Intake")

    assert [card["id"] for card in result["cards"]] == ["p007"]
    assert result["note"].startswith(f"{label} {people['p009']['name']} ")
    assert result["note"].endswith("1 person opted out of being found.")
    assert opted_out_names_in(result) == []


def test_the_label_names_several_systems_in_the_language_of_the_question(builder, evidence):
    """Two systems, and a French question: "Customer Portal et Claims Intake", in the French sentence."""
    state = second_level_state(evidence, ["customer_portal", "claims_intake"], "Qui peut m'aider ?", language="fr")
    result = builder.build(state)

    assert result["note"].startswith(NOTE_TEXTS["same_system"]["fr"].format(systems="Customer Portal et Claims Intake"))
    assert "Voici qui travaille sur Customer Portal et Claims Intake" in result["note"]


def test_an_answer_about_the_exact_need_says_so_and_has_no_label(builder, evidence, scenarios):
    """Scenario 1: its level is "exact". The state here has no "level" key, like a conversation saved before it existed."""
    state = state_for(evidence, scenarios, "s01")
    result = builder.build(state)

    assert "level" not in state
    assert result["level"] == "exact"
    assert "exact question" not in result["note"]
    assert builder.build({**state, "level": "exact", "named_systems": ["claims_api"]})["note"] == result["note"]


def test_the_second_level_with_no_card_has_no_label_and_no_level(builder, evidence, people):
    """The HR check removed everyone of the system: there is no card to label, and the note only says who was removed."""
    state = second_level_state(evidence, ["claims_intake"], "Claims Intake is slow. Who can help?")
    state.update({"recommended": [], "message": NOBODY_FOUND_TEXTS["general"]["en"]})
    result = builder.build(state)

    assert result["status"] == "nobody_found"
    assert result["level"] == ""
    assert "exact question" not in result["note"]
    assert result["note"].startswith(people["p009"]["name"])


def test_only_an_answer_with_cards_has_a_level(builder, evidence):
    """A refusal has no card, so it has no level."""
    state = state_from(evidence, [], "What's for lunch?")
    state.update({"road": "not_work", "message": FAILSAFE_TEXTS["not_work"]["en"]})

    assert builder.build(state)["level"] == ""


def test_the_plain_message_of_the_second_level_never_says_worked_on_this_topic(builder, evidence):
    """Without a text of the LLM, the plain message of the second level says "you work on this system", and no more."""
    question = "A broker can't log in. Who can help?"
    second = builder.build(second_level_state(evidence, ["broker_portal"], question))["cards"][0]
    first = builder.build(state_from(evidence, ["pg025"], question))["cards"][0]

    assert "I saw that you work on this system." in second["message"]
    assert "worked on this topic" not in second["message"]
    assert question in second["message"]
    # The first level keeps its own plain message
    assert "I saw that you worked on this topic." in first["message"]
    # And the French one
    french = builder.build(second_level_state(evidence, ["broker_portal"], "Qui peut m'aider ?", language="fr"))["cards"][0]
    assert "J'ai vu que vous travaillez sur ce système." in french["message"]


# ----------------------------------------------------------------------
# The other kinds of answer
# ----------------------------------------------------------------------


def test_nobody_found_keeps_the_note(builder, evidence, people):
    """Everyone behind the evidence was removed: no card, the fixed text, and the note still says who was removed."""
    # pg002 is the old access guide. Its author left the company
    state = state_from(evidence, ["pg002"], "Who wrote the old access guide?")
    state["message"] = NOBODY_FOUND_TEXTS["general"]["en"]
    result = builder.build(state)

    assert result["status"] == "nobody_found"
    assert result["cards"] == []
    assert result["message"] == NOBODY_FOUND_TEXTS["general"]["en"]
    assert result["note"].startswith(people[state["removed_left"][0]]["name"])


def test_a_refusal_has_its_reason_and_no_card(builder, evidence):
    """A refused request: the status, the reason, and the fixed text. No card and no note."""
    state = state_from(evidence, [], "What's for lunch?")
    state["road"] = "not_work"
    state["message"] = FAILSAFE_TEXTS["not_work"]["en"]
    result = builder.build(state)

    assert result["status"] == "off_topic"
    assert result["reason"] == "not_work"
    assert result["message"] == FAILSAFE_TEXTS["not_work"]["en"]
    assert result["cards"] == []
    assert result["note"] == ""
