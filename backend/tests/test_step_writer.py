"""Free tests of the grey step lines: one short line per step, built in code from counts. No OpenAI calls.

The first part checks each line by itself. The second part runs the real graph with fake LLM steps (the agent
helper of conftest.py), and checks the lines of a whole question, and that no line ever names a person.
"""

import json
from typing import Dict, List

import pytest

from agents.step_writer import StepWriter
from config.constants import MAX_STEP_WORDS_LENGTH
from sources import PeopleSource


@pytest.fixture(scope="module")
def writer() -> StepWriter:
    """The class under test. It reads the names of the real directory, for the check on the search words."""
    return StepWriter()


@pytest.fixture(scope="module")
def people() -> List[Dict]:
    """Everyone in the directory."""
    return PeopleSource().list_people()


# ----------------------------------------------------------------------
# Each line by itself
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "facts, line",
    [
        ({"road": "expert", "question_type": "help"}, "Read your question: you are looking for someone who can help"),
        ({"road": "expert", "question_type": "did"}, "Read your question: you are looking for someone who did the work"),
        ({"road": "expert", "question_type": "decided"}, "Read your question: you are looking for the person who decided"),
        (
            {"road": "expert", "question_type": "help", "no_topic": True},
            "Read your question: it does not say what you need help with",
        ),
        ({"road": "not_work", "question_type": "help", "no_topic": True}, "Read your question: it is not about work"),
        ({"road": "person", "question_type": "help"}, "Read your question: it is about a colleague"),
        ({"road": "unclear", "question_type": "help", "systems": 2}, "Read your question: it could be about 2 systems"),
        ({"road": "not_work", "question_type": "help"}, "Read your question: it is not about work"),
        ({"road": "personal", "question_type": "help"}, "Read your question: it asks for personal information"),
    ],
)
def test_the_line_of_understand_says_what_the_request_is(writer, facts, line):
    """One line per road, and for an expert request, per type of question."""
    assert writer.write("understand", {"systems": 0, "answered": False, **facts}) == line


def test_the_line_of_understand_after_an_answer(writer):
    """After the user's pick, understand reads the request again, and its line says so."""
    facts = {"road": "expert", "question_type": "help", "systems": 0, "answered": True}
    assert writer.write("understand", facts) == (
        "Read your question again, with your answer: you are looking for someone who can help"
    )


@pytest.mark.parametrize(
    "facts, line",
    [
        ({"words": ["printer queue", "reset"], "found": 14, "retry": False}, 'Searched pages and tickets for "printer queue", "reset": 14 results'),
        ({"words": ["printer queue"], "found": 1, "retry": False}, 'Searched pages and tickets for "printer queue": 1 result'),
        ({"words": [], "found": 12, "retry": False}, "Searched pages and tickets: 12 results"),
        ({"words": ["print jobs"], "found": 0, "retry": True}, 'Searched again for "print jobs": 0 results'),
        ({"words": [], "found": 3, "retry": True}, "Searched again: 3 results"),
    ],
)
def test_the_line_of_search_counts_the_results(writer, facts, line):
    """The search line repeats the search words and counts the results. A retry says "again"."""
    assert writer.write("search", facts) == line


@pytest.mark.parametrize(
    "facts, line",
    [
        ({"checked": 15, "kept": 8}, "Checked 15 results: 8 are really about your question"),
        ({"checked": 15, "kept": 1}, "Checked 15 results: 1 is really about your question"),
        ({"checked": 1, "kept": 0}, "Checked 1 result: none is really about your question"),
        ({"checked": 0, "kept": 0}, "No new result to check"),
    ],
)
def test_the_line_of_verify_counts_what_holds_up(writer, facts, line):
    """How many results were read, and how many are about the question."""
    assert writer.write("verify", facts) == line


@pytest.mark.parametrize(
    "facts, line",
    [
        ({"left": 1, "opted_out": 1}, "Removed: 1 person who left the company, 1 person who opted out"),
        ({"left": 2, "opted_out": 0}, "Removed: 2 people who left the company"),
        ({"left": 0, "opted_out": 3}, "Removed: 3 people who opted out"),
        ({"left": 0, "opted_out": 0}, "Removed: nobody"),
    ],
)
def test_the_line_of_the_hr_check_only_counts(writer, facts, line):
    """Who was removed, as counts. The line never has a name: the note names who left, and nobody names who opted out."""
    assert writer.write("check_hr", facts) == line


@pytest.mark.parametrize(
    "step, facts, line",
    [
        ("failsafe", {}, "Declined the question"),
        ("ask_user", {}, "Noted your answer"),
        ("rewrite", {}, "Nothing was about your question: picked other search words"),
        (
            "same_system",
            {"systems": ["Claims Workbench"], "items": 4},
            "Nothing matched your exact question: took the 4 pages and tickets about Claims Workbench instead",
        ),
        (
            "same_system",
            {"systems": ["Cloud Platform"], "items": 1},
            "Nothing matched your exact question: took the 1 page or ticket about Cloud Platform instead",
        ),
        (
            "same_system",
            {"systems": ["Customer Portal", "Claims Intake"], "items": 10},
            "Nothing matched your exact question: took the 10 pages and tickets about Customer Portal, Claims Intake instead",
        ),
        ("rank", {"people": 4}, "Found 4 people behind these pages and tickets"),
        ("rank", {"people": 1}, "Found 1 person behind these pages and tickets"),
        ("write_cards", {"people": 3}, "Wrote the cards of 3 people"),
        ("write_cards", {"people": 1}, "Wrote the card of 1 person"),
        ("nobody_found", {"kind": "general"}, "Found nobody to recommend"),
        ("nobody_found", {"kind": "no_decision"}, "Found no recorded decision about this"),
        ("nobody_found", {"kind": "no_topic"}, "Searched nothing, and asked what you need"),
        ("nobody_found", {"kind": "no_person"}, "Could not tell which person you mean"),
        ("nobody_found", {"kind": "no_one_meant"}, "Could not tell which person you mean"),
        ("nobody_found", {"kind": "several_people"}, "Could not tell which person you mean"),
        ("find_person", {"matches": 1, "named": True, "picked": False}, "Looked in the directory: 1 person has that name"),
        ("find_person", {"matches": 2, "named": True, "picked": False}, "Looked in the directory: 2 people have that name"),
        ("find_person", {"matches": 0, "named": True, "picked": False}, "Looked in the directory: nobody has that name"),
        ("find_person", {"matches": 1, "named": False, "picked": False}, "Took the most recent person shown in this conversation"),
        ("find_person", {"matches": 0, "named": False, "picked": False}, "No person was shown yet in this conversation"),
        ("find_person", {"matches": 1, "named": True, "picked": True}, "Took the person you picked"),
        ("person_card", {}, "Prepared the card from the directory"),
    ],
)
def test_the_lines_of_the_other_steps(writer, step, facts, line):
    """Every other step has one line, with "1 person" or "3 people" as the count asks."""
    assert writer.write(step, facts) == line


# ----------------------------------------------------------------------
# A line never names a person
# ----------------------------------------------------------------------


def test_search_words_that_name_a_colleague_are_not_repeated(writer, people):
    """The search words are my own words. When one of them is a name of the directory, the line shows no word at all."""
    for person in people:
        for name in [person["name"], person["first_name"], person["last_name"].lower(), f"{person['first_name']}'s tickets"]:
            line = writer.write("search", {"words": ["access", name], "found": 5, "retry": False})
            assert line == "Searched pages and tickets: 5 results"


def test_a_name_without_its_accents_is_still_a_name(writer):
    """ "helene" and "Hélène" are the same first name: the check does not depend on capitals or accents."""
    for words in [["helene dubois"], ["HÉLÈNE"], ["marc andre"], ["Côté"]]:
        assert writer.write("search", {"words": words, "found": 2, "retry": False}) == "Searched pages and tickets: 2 results"


def test_search_words_that_are_too_long_are_not_repeated(writer):
    """A step line is a short line: very long search words are left out."""
    short = ["x" * (MAX_STEP_WORDS_LENGTH - 2)]
    long = ["x" * (MAX_STEP_WORDS_LENGTH - 1)]

    assert short[0] in writer.write("search", {"words": short, "found": 2, "retry": False})
    assert writer.write("search", {"words": long, "found": 2, "retry": False}) == "Searched pages and tickets: 2 results"


def test_someone_who_joins_while_the_app_runs_is_known_at_the_next_question(writer, store, monkeypatch):
    """The names are read from MongoDB at each search line, so a new colleague's name is never repeated either."""
    line = {"words": ["Zebulon"], "found": 1, "retry": False}
    assert writer.write("search", line) == 'Searched pages and tickets for "Zebulon": 1 result'

    # A copy of the directory with one more person, in the throwaway database
    newcomer = {"id": "p999", "name": "Zebulon Quokka", "first_name": "Zebulon", "last_name": "Quokka"}
    store.replace_documents("people", PeopleSource().list_people() + [newcomer])
    monkeypatch.setattr("sources.people.mongo_store", store)
    assert writer.write("search", line) == "Searched pages and tickets: 1 result"


# ----------------------------------------------------------------------
# The lines of a whole question, with the real graph and fake LLM steps
# ----------------------------------------------------------------------


def test_the_step_lines_of_scenario_1(agent, scenarios):
    """Scenario 1 from the question to the cards: six lines, in the order of the steps."""
    workflow, fakes = agent
    turn = scenarios["s01"]["turns"][0]
    fakes.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": ["Claims API", "access"]}
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]

    assert workflow.full_pipeline(turn["question"])["steps"] == [
        "Read your question: you are looking for someone who can help",
        'Searched pages and tickets for "Claims API", "access": 8 results',
        "Checked 8 results: 8 are really about your question",
        "Found 5 people behind these pages and tickets",
        "Removed: 1 person who left the company, 1 person who opted out",
        "Wrote the cards of 3 people",
    ]


def test_the_step_lines_of_a_retry_that_finds_nothing(agent):
    """Nothing holds up twice: the lines show the first search, the new words, the second search, and "nobody"."""
    workflow, fakes = agent
    fakes.found = [["pg004"], ["pg014"]]

    assert workflow.full_pipeline("Who can help me order a laptop?")["steps"] == [
        "Read your question: you are looking for someone who can help",
        'Searched pages and tickets for "laptop": 1 result',
        "Checked 1 result: none is really about your question",
        "Nothing was about your question: picked other search words",
        'Searched again for "computer": 1 result',
        "Checked 1 result: none is really about your question",
        "Found nobody to recommend",
    ]


def test_the_step_lines_of_the_second_level(agent, people):
    """Nothing is about the exact need, and the question names a system: one more line says what the agent took instead.

    The line names the system, which comes from the data. No line names a person: not the people who are shown,
    and not the two people of this system that the HR check removed.
    """
    workflow, fakes = agent
    fakes.understood = {
        "road": "expert",
        "question_type": "help",
        "language": "en",
        "search_words": ["phone line"],
        "named_systems": ["claims_intake"],
    }
    fakes.found = [["pg004"], ["pg014"]]
    steps = workflow.full_pipeline("Claims Intake drops the claims of the phone line. Who should I talk to?")["steps"]

    assert steps == [
        "Read your question: you are looking for someone who can help",
        'Searched pages and tickets for "phone line": 1 result',
        "Checked 1 result: none is really about your question",
        "Nothing was about your question: picked other search words",
        'Searched again for "computer": 1 result',
        "Checked 1 result: none is really about your question",
        "Nothing matched your exact question: took the 4 pages and tickets about Claims Intake instead",
        "Found 3 people behind these pages and tickets",
        "Removed: 1 person who left the company, 1 person who opted out",
        "Wrote the card of 1 person",
    ]
    lines = json.dumps(steps, ensure_ascii=False)
    for person in people:
        assert person["first_name"] not in lines and person["last_name"] not in lines


def test_the_step_lines_of_a_question_about_a_colleague(agent):
    """The person road: three lines, and none of them repeats the name that the question gave."""
    workflow, fakes = agent
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": "en",
        "search_words": [],
        "person_name": "Sophie Martin",
        "person_asks": "manager",
    }
    steps = workflow.full_pipeline("Who is Sophie Martin's manager?")["steps"]

    assert steps == [
        "Read your question: it is about a colleague",
        "Looked in the directory: 1 person has that name",
        "Prepared the card from the directory",
    ]


def test_the_step_lines_of_a_refusal(agent):
    """A refused question: two lines, and no search line."""
    workflow, fakes = agent
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "fr", "search_words": []}

    # The lines are in English whatever the language of the question
    assert workflow.full_pipeline("Quel temps fait-il ?")["steps"] == [
        "Read your question: it is not about work",
        "Declined the question",
    ]


def test_no_step_line_names_anyone_even_when_the_question_does(agent, scenarios, people):
    """The question names the colleague who opted out, and understand copies the name into the search words.

    The answer of scenario 1 follows. No step line holds a first name or a last name of anyone in the directory:
    not the name that was typed, and not the names of the people who were found or removed.
    """
    workflow, fakes = agent
    opted_out = next(person for person in people if not person["discoverable"])
    evidence = scenarios["s01"]["turns"][0]["expected"]["evidence"]
    fakes.understood = {
        "road": "expert",
        "question_type": "did",
        "language": "en",
        "search_words": [opted_out["name"], "access tickets"],
    }
    fakes.found = [evidence]
    fakes.relevant = evidence
    answer = workflow.full_pipeline(f"Who took over the access tickets of {opted_out['name']}?")

    assert answer["status"] == "answered" and answer["removed_opted_out"] == 1
    assert len(answer["steps"]) == 6
    assert "Searched pages and tickets: 8 results" in answer["steps"]
    lines = json.dumps(answer["steps"], ensure_ascii=False)
    for person in people:
        assert person["first_name"] not in lines and person["last_name"] not in lines
