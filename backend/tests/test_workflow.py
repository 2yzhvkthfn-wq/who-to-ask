"""Free tests of the graph: its routers, its retry loop, and its ways out. No OpenAI calls.

The graph is the real one. Fakes stand in for the steps that call OpenAI (understand, search, verify, rewrite,
and write_cards). The plain-code steps (rank, check_hr, nobody_found) and the answer run for real, on the real data.
The graph with its fakes is the agent helper of conftest.py: the free tests of the API use it too.
The tests of what the real model answers are in test_agent.py, and they are paid.
"""

from typing import Dict, List

import pytest

from config.texts import FAILSAFE_TEXTS, NOBODY_FOUND_TEXTS, NOTE_TEXTS
from sources import PeopleSource

# ----------------------------------------------------------------------
# The retry: one more search with new words, and only one
# ----------------------------------------------------------------------


def test_evidence_at_the_first_try_means_no_retry(agent):
    """Evidence holds up at once: one search, no new words, and the people behind the evidence are recommended."""
    workflow, fakes = agent
    # pg008 is the access guide of the Claims API, written by p012. pg004 is another system's guide
    fakes.found = [["pg008", "pg004"]]
    fakes.relevant = ["pg008"]
    result = workflow.full_pipeline("Who can help me order a laptop?")

    assert result["status"] == "answered"
    assert [card["id"] for card in result["cards"]] == ["p012"]
    assert len(fakes.searches) == 1
    assert fakes.rewrites == 0


def test_nothing_holds_up_so_the_search_runs_again_with_new_words(agent):
    """Nothing holds up at the first try: rewrite gives new words, the search runs again, and it finds the evidence."""
    workflow, fakes = agent
    fakes.found = [["pg004"], ["pg008"]]
    fakes.relevant = ["pg008"]
    result = workflow.full_pipeline("Who can help me order a laptop?")

    assert result["status"] == "answered"
    assert [card["id"] for card in result["cards"]] == ["p012"]
    assert fakes.rewrites == 1
    # The first search used the words of understand. The second one is marked as a retry, with the new words
    assert fakes.searches == [{"words": ["laptop"], "retry": False}, {"words": ["computer"], "retry": True}]


def test_the_retry_happens_only_once(agent):
    """Nothing holds up twice: the agent does not search a third time. It says that nobody was found."""
    workflow, fakes = agent
    fakes.found = [["pg004"], ["pg014"]]
    result = workflow.full_pipeline("Who can help me order a laptop?")

    assert result["status"] == "nobody_found"
    assert result["message"] == NOBODY_FOUND_TEXTS["general"]["en"]
    assert result["cards"] == []
    assert len(fakes.searches) == 2
    assert fakes.rewrites == 1


def test_a_retry_never_judges_the_same_text_twice(agent):
    """The second search finds a text again: verify only gets the new one, because its verdict would not change."""
    workflow, fakes = agent
    fakes.found = [["pg004", "pg014"], ["pg014", "pg008"]]
    workflow.full_pipeline("Who can help me order a laptop?")

    assert fakes.verified == [["pg004", "pg014"], ["pg008"]]


# ----------------------------------------------------------------------
# nobody_found: which fixed text, and in which language
# ----------------------------------------------------------------------


@pytest.mark.parametrize("language", ["en", "fr"])
def test_a_decided_question_with_no_decision_says_so(agent, language):
    """A "decided" question where no minutes hold up gets the "no recorded decision" text, in its language."""
    workflow, fakes = agent
    fakes.understood = {"road": "expert", "question_type": "decided", "language": language, "search_words": ["laptop"]}
    # pg016 is the minutes of a decision about something else
    fakes.found = [["pg016"]]
    result = workflow.full_pipeline("Who decided to order new laptops?")

    assert result["status"] == "nobody_found"
    assert result["message"] == NOBODY_FOUND_TEXTS["no_decision"][language]


def test_everyone_removed_means_nobody_found(agent):
    """The only person behind the evidence left the company: nobody is found, and the answer still says who was removed."""
    workflow, fakes = agent
    # pg002 is the old access guide. Its author, p009, left the company
    fakes.found = [["pg002"]]
    fakes.relevant = ["pg002"]
    result = workflow.full_pipeline("Who can help me order a laptop?")

    assert result["status"] == "nobody_found"
    assert result["message"] == NOBODY_FOUND_TEXTS["general"]["en"]
    assert result["cards"] == []
    assert result["removed_left"] == ["p009"]
    # Evidence held up, so this is not a case for the retry
    assert fakes.rewrites == 0


def test_a_decision_whose_owner_was_removed_gets_the_general_text(agent, monkeypatch):
    """A decision held up, but the HR check removed its owner: "no recorded decision" would be false here."""
    workflow, fakes = agent
    fakes.understood = {"road": "expert", "question_type": "decided", "language": "en", "search_words": ["laptop"]}
    # pg011 is the minutes of a real decision. Nobody behind it left, so the HR check is replaced for this test
    fakes.found = [["pg011"]]
    fakes.relevant = ["pg011"]

    def everyone_left(ranking: List[Dict]) -> Dict:
        return {"recommended": [], "removed_left": [entry["person"] for entry in ranking], "removed_opted_out": []}

    monkeypatch.setattr(workflow.hr_checker, "check", everyone_left)
    result = workflow.full_pipeline("Who decided to order new laptops?")

    assert result["status"] == "nobody_found"
    assert result["message"] == NOBODY_FOUND_TEXTS["general"]["en"]


# ----------------------------------------------------------------------
# failsafe: a refused request stops before the search
# ----------------------------------------------------------------------


def test_a_refused_request_is_never_searched(agent):
    """A request that is not about work gets the fixed refusal, and no search runs."""
    workflow, fakes = agent
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    result = workflow.full_pipeline("What should I cook tonight?")

    assert result["status"] == "off_topic"
    assert result["reason"] == "not_work"
    assert result["message"] == FAILSAFE_TEXTS["not_work"]["en"]
    assert fakes.searches == []


# ----------------------------------------------------------------------
# write_cards and the answer: one card per person, and nobody who was removed
# ----------------------------------------------------------------------


def test_the_answer_of_scenario_1_with_fake_llm_steps(agent, scenarios, opted_out_names_in):
    """The evidence of scenario 1 holds up: three cards with a message and two links, and a note about two people."""
    workflow, fakes = agent
    expected = scenarios["s01"]["turns"][0]["expected"]
    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    result = workflow.full_pipeline(scenarios["s01"]["turns"][0]["question"])

    # The expected people, with the expert first
    assert result["status"] == "answered"
    cards = [card["id"] for card in result["cards"]]
    assert sorted(cards) == sorted(expected["people"])
    assert cards[0] == expected["people"][0]

    # The LLM step only got the people who are recommended, never the two who were removed
    assert fakes.card_people == cards

    # Every card has its two texts, its message, and its two links
    for card in result["cards"]:
        assert card["why"] == fakes.card_text["why"]
        assert fakes.card_text["message"] in card["message"]
        assert card["teams_link"].startswith("https://teams.microsoft.com/l/chat/0/0?users=")
        assert card["email_link"].startswith(f"mailto:{card['email']}?subject=")

    # The note: one person who left is named, and one person who opted out is only counted
    assert result["removed_left"] == expected["removed_left"]
    assert result["removed_opted_out"] == expected["removed_opted_out"]
    assert "no longer works at the company" in result["note"]
    assert "1 person opted out of being found." in result["note"]
    assert opted_out_names_in(result) == []


def test_a_text_the_llm_could_not_give_is_replaced_by_a_plain_one(agent):
    """write_cards comes back with empty texts: the card still says why, in words built from the data."""
    workflow, fakes = agent
    fakes.found = [["pg008"]]
    fakes.relevant = ["pg008"]
    fakes.card_text = {"why": "", "message": ""}
    card = workflow.full_pipeline("Who can help me order a laptop?")["cards"][0]

    assert card["why"] == 'wrote "Claims API: Access Guide"'
    assert "Who can help me order a laptop?" in card["message"]


def test_nobody_found_writes_no_card(agent):
    """When everyone was removed, the LLM is not asked to write anything."""
    workflow, fakes = agent
    fakes.found = [["pg002"]]
    fakes.relevant = ["pg002"]
    result = workflow.full_pipeline("Who can help me order a laptop?")

    assert result["status"] == "nobody_found"
    assert fakes.card_people == []
    assert "no longer works at the company" in result["note"]


# ----------------------------------------------------------------------
# A request with no topic: no search word and no system. Nothing is searched, and the agent asks what the user needs
# ----------------------------------------------------------------------


def no_topic_reading(language: str = "en") -> Dict:
    """What understand answers for "I need help. Who should I ask?": a request for an expert, with nothing to search for."""
    return {"road": "expert", "question_type": "help", "language": language, "search_words": [], "no_topic": True}


@pytest.mark.parametrize("language", ["en", "fr"])
def test_a_request_with_no_topic_is_not_searched(agent, language):
    """No search, no check, and no card: one fixed text asks what the user needs, in the language of the request."""
    workflow, fakes = agent
    fakes.understood = no_topic_reading(language)
    # Even if a search would find something, and verify would say yes to it, nobody may be recommended
    fakes.found = [["pg008"]]
    fakes.relevant = ["pg008"]
    result = workflow.full_pipeline("I need help. Who should I ask?")

    assert result["status"] == "nobody_found"
    assert result["message"] == NOBODY_FOUND_TEXTS["no_topic"][language]
    assert result["cards"] == [] and result["note"] == "" and result["level"] == ""
    # Nothing ran after understand: no search, no verdict, no new words, and no card
    assert fakes.searches == [] and fakes.verified == [] and fakes.rewrites == 0 and fakes.card_people == []
    assert result["steps"] == [
        "Read your question: it does not say what you need help with",
        "Searched nothing, and asked what you need",
    ]


def test_the_text_for_no_topic_is_a_question(agent):
    """The answer asks what the user needs: it does not say that nobody was found."""
    workflow, fakes = agent
    fakes.understood = no_topic_reading()
    message = workflow.full_pipeline("I need help. Who should I ask?")["message"]

    assert message.startswith("What do you need help with?")
    assert "nobody" not in message.lower()


def test_a_request_with_a_topic_is_searched_as_before(agent):
    """One search word is a topic: the request takes the usual road, and it can end as the usual "nobody found"."""
    workflow, fakes = agent
    fakes.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": ["laptop"], "no_topic": False}
    fakes.found = [["pg004"], ["pg014"]]
    result = workflow.full_pipeline("Who can help me order a laptop?")

    assert result["status"] == "nobody_found"
    assert result["message"] == NOBODY_FOUND_TEXTS["general"]["en"]
    assert len(fakes.searches) == 2 and fakes.rewrites == 1


def test_no_topic_belongs_to_one_question(agent):
    """After a request with no topic, the next question of the conversation is searched like any other."""
    workflow, fakes = agent
    fakes.understood = no_topic_reading()
    first = workflow.full_pipeline("I need help. Who should I ask?")

    fakes.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": ["key"]}
    fakes.found = [["pg008"]]
    fakes.relevant = ["pg008"]
    second = workflow.full_pipeline("Who can help me get a key for the Claims API?", first["thread_id"])

    assert first["status"] == "nobody_found" and first["message"] == NOBODY_FOUND_TEXTS["no_topic"]["en"]
    assert second["status"] == "answered" and [card["id"] for card in second["cards"]] == ["p012"]
    assert len(fakes.searches) == 1


def test_a_refusal_is_never_read_as_no_topic(agent):
    """A request that is not about work has no search words either: it is refused, with its own text."""
    workflow, fakes = agent
    # The reader never says "no topic" for a refusal. Even if it did, the road decides
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": [], "no_topic": True}
    result = workflow.full_pipeline("What's for lunch?")

    assert result["status"] == "off_topic"
    assert result["message"] == FAILSAFE_TEXTS["not_work"]["en"]


# ----------------------------------------------------------------------
# The second level: nothing is about the exact need, and the request names a system.
# The people who work on that system are shown, and the answer says that this is what they are
# ----------------------------------------------------------------------


def naming(systems: List[str], question_type: str = "help", language: str = "en") -> Dict:
    """What understand answers for a request for an expert that names these systems."""
    return {
        "road": "expert",
        "question_type": question_type,
        "language": language,
        "search_words": ["freeze"],
        "named_systems": systems,
    }


def test_nothing_exact_and_a_named_system_gives_the_people_of_that_system(agent):
    """ "X is broken, who do I talk to?": no ticket is about this problem, so the people who work on X are shown."""
    workflow, fakes = agent
    fakes.understood = naming(["claims_workbench"])
    # Two searches, and verify keeps nothing: no text is about this exact problem
    fakes.found = [["pg004"], ["pg014"]]
    result = workflow.full_pipeline("The Claims Workbench freezes at lunch time. Who should I talk to?")

    # Everyone with a ticket or a page on the Claims Workbench: p007 wrote its release checklist and handled a ticket,
    # and p024 handled two tickets. A "help" question puts the person with a page first
    assert result["status"] == "answered"
    assert [card["id"] for card in result["cards"]] == ["p007", "p024"]
    assert result["level"] == "system"
    # The answer says what these cards are, before anything else, with the name of the system from the data
    assert result["note"] == NOTE_TEXTS["same_system"]["en"].format(systems="Claims Workbench")
    assert "exact question" in result["note"]
    # The evidence of a card is the person's work on that system, and nothing else
    shown = {label["id"] for card in result["cards"] for label in card["evidence"]}
    assert shown == {"pg017", "CLM-279", "CLM-254", "CLM-262"}
    # The LLM that writes the cards is told that this is the second level
    assert fakes.card_levels == ["system"]


def test_the_second_level_comes_after_the_retry_and_never_before(agent):
    """The agent first looks for the exact need, twice. Only then does it take the people of the system."""
    workflow, fakes = agent
    fakes.understood = naming(["claims_workbench"])
    fakes.found = [["pg004"], ["pg014"]]
    result = workflow.full_pipeline("The Claims Workbench freezes at lunch time. Who should I talk to?")

    assert len(fakes.searches) == 2 and fakes.rewrites == 1
    # The steps say it in order: two checks that kept nothing, then the second level, then the usual steps
    assert result["steps"][-4:] == [
        "Nothing matched your exact question: took the 4 pages and tickets about Claims Workbench instead",
        "Found 2 people behind these pages and tickets",
        "Removed: nobody",
        "Wrote the cards of 2 people",
    ]


def test_exact_evidence_wins_over_the_second_level(agent):
    """The request names a system, and a text is about its exact need: the answer is the usual one, with no label."""
    workflow, fakes = agent
    fakes.understood = naming(["claims_api"])
    fakes.found = [["pg008", "pg004"]]
    fakes.relevant = ["pg008"]
    result = workflow.full_pipeline("Who can help me get a key for the Claims API?")

    assert [card["id"] for card in result["cards"]] == ["p012"]
    assert result["level"] == "exact"
    assert result["note"] == ""
    assert fakes.card_levels == ["exact"]
    assert not any("exact question" in step for step in result["steps"])


def test_exact_evidence_at_the_retry_wins_too(agent):
    """The second search finds a text about the exact need: no second level, even though a system is named."""
    workflow, fakes = agent
    fakes.understood = naming(["claims_api"])
    fakes.found = [["pg004"], ["pg008"]]
    fakes.relevant = ["pg008"]
    result = workflow.full_pipeline("Who can help me get a key for the Claims API?")

    assert [card["id"] for card in result["cards"]] == ["p012"]
    assert result["level"] == "exact" and result["note"] == ""


def test_without_a_named_system_nobody_is_found_as_before(agent):
    """The request names no system: there is no second level, and the answer is "nobody found"."""
    workflow, fakes = agent
    fakes.understood = naming([])
    fakes.found = [["pg004"], ["pg014"]]
    result = workflow.full_pipeline("Who can help me set up the coffee machine?")

    assert result["status"] == "nobody_found"
    assert result["message"] == NOBODY_FOUND_TEXTS["general"]["en"]
    assert result["cards"] == [] and result["level"] == "" and result["note"] == ""
    assert fakes.card_people == []


@pytest.mark.parametrize("language", ["en", "fr"])
def test_a_decided_question_never_gets_the_second_level(agent, language):
    """Working on a system is not deciding: a "decided" question with no recorded decision still finds nobody."""
    workflow, fakes = agent
    fakes.understood = naming(["claims_workbench"], question_type="decided", language=language)
    fakes.found = [["pg016"], ["pg011"]]
    result = workflow.full_pipeline("Who decided to repaint the Claims Workbench?")

    assert result["status"] == "nobody_found"
    assert result["message"] == NOBODY_FOUND_TEXTS["no_decision"][language]
    assert result["cards"] == [] and result["level"] == ""
    assert fakes.card_people == []


def test_the_second_level_never_shows_someone_who_left_or_opted_out(agent, opted_out_names_in):
    """The same HR check runs after the second level: one person is left, one is named in the note, one is only counted."""
    workflow, fakes = agent
    people_by_id = {person["id"]: person for person in PeopleSource().list_people()}
    fakes.understood = naming(["claims_intake"])
    fakes.found = [["pg004"], ["pg014"]]
    result = workflow.full_pipeline("Claims Intake drops the claims of the phone line. Who should I talk to?")

    # Claims Intake: p007 handled a ticket and owns a decision. p009 handled a ticket and left the company.
    # p018 handled a ticket and opted out of being found
    assert [card["id"] for card in result["cards"]] == ["p007"]
    assert result["removed_left"] == ["p009"]
    assert result["removed_opted_out"] == 1
    # The note: the label first, then the person who left, by name, then a count for the person who opted out
    label = NOTE_TEXTS["same_system"]["en"].format(systems="Claims Intake")
    assert result["note"].startswith(label)
    assert people_by_id["p009"]["name"] in result["note"]
    assert result["note"].endswith("1 person opted out of being found.")
    assert opted_out_names_in(result) == []
    # The LLM step only got the person who is recommended
    assert fakes.card_people == ["p007"]


def test_two_named_systems_give_the_people_of_both(agent):
    """A request that names two systems: the people of both are ranked together, and the note names both systems."""
    workflow, fakes = agent
    fakes.understood = naming(["customer_portal", "claims_intake"])
    fakes.found = [["pg004"], ["pg014"]]
    result = workflow.full_pipeline("Claims from the Customer Portal get lost before Claims Intake. Who can help?")

    # p016 wrote the Customer Portal's guide and handled three of its tickets. p007 owns a decision on Claims Intake
    # and handled one of its tickets. p008 owns a decision on the Customer Portal
    assert [card["id"] for card in result["cards"]] == ["p016", "p007", "p008"]
    assert result["note"].startswith(NOTE_TEXTS["same_system"]["en"].format(systems="Customer Portal and Claims Intake"))


def test_the_second_level_is_labelled_in_the_language_of_the_question(agent):
    """A French question gets the French label, and the level is given to write_cards with the language."""
    workflow, fakes = agent
    fakes.understood = naming(["single_sign_on"], question_type="did", language="fr")
    fakes.found = [["pg004"], ["pg014"]]
    result = workflow.full_pipeline("Qui a configuré la connexion sans mot de passe sur Single Sign-On ?")

    # p019 handled the one ticket of Single Sign-On and wrote its one page
    assert [card["id"] for card in result["cards"]] == ["p019"]
    assert result["level"] == "system"
    assert result["note"] == NOTE_TEXTS["same_system"]["fr"].format(systems="Single Sign-On")
    assert "question précise" in result["note"]


def test_the_second_level_with_everyone_removed_says_nobody_found(agent, monkeypatch):
    """The people of the system were all removed by the HR check: "nobody found", with no label, and no card."""
    workflow, fakes = agent
    fakes.understood = naming(["claims_workbench"])
    fakes.found = [["pg004"], ["pg014"]]

    def everyone_left(ranking: List[Dict]) -> Dict:
        return {"recommended": [], "removed_left": [entry["person"] for entry in ranking], "removed_opted_out": []}

    monkeypatch.setattr(workflow.hr_checker, "check", everyone_left)
    result = workflow.full_pipeline("The Claims Workbench freezes at lunch time. Who should I talk to?")

    assert result["status"] == "nobody_found"
    assert result["message"] == NOBODY_FOUND_TEXTS["general"]["en"]
    assert result["cards"] == [] and result["level"] == ""
    # The note still says who was removed, and it does not call nobody "the people who work on the system"
    assert "no longer works at the company" in result["note"]
    assert "exact question" not in result["note"]
    assert fakes.card_people == []


def test_a_new_question_starts_at_the_first_level_again(agent):
    """The level belongs to one question: after a second-level answer, the next answer of the conversation is exact."""
    workflow, fakes = agent
    fakes.understood = naming(["claims_workbench"])
    fakes.found = [["pg004"], ["pg014"]]
    first = workflow.full_pipeline("The Claims Workbench freezes at lunch time. Who should I talk to?")

    fakes.understood = naming([])
    fakes.found = [["pg008"]]
    fakes.relevant = ["pg008"]
    second = workflow.full_pipeline("Who can help me get a key for the Claims API?", first["thread_id"])

    assert first["level"] == "system"
    assert second["level"] == "exact" and second["note"] == ""
    assert fakes.card_levels == ["system", "exact"]
