"""Free tests of the pause: the agent asks the user one question, waits, and goes on with the answer. No OpenAI calls.

The graph is the real one, with fake LLM steps (the helpers of conftest.py). Here the fake understand answers what
the real one answers: "unclear" with two systems for the question of scenario 8, and the road "person" with a first
name that two people have for scenario 12. ask_user, the routers, find_person, and the answer run for real.
The conversations are kept in the memory of the program, with LangGraph's in-memory saver.
The tests of what the real model answers are in test_agent.py, and they are paid.
"""

import json
from typing import Dict, List

import pytest

from config.texts import ASK_USER_TEXTS, NOBODY_FOUND_TEXTS, NOTE_TEXTS, PERSON_TEXTS
from sources import CompanySource, PeopleSource


@pytest.fixture(scope="module")
def people() -> Dict:
    """The directory, by person id."""
    return {person["id"]: person for person in PeopleSource().list_people()}


@pytest.fixture(scope="module")
def systems() -> Dict:
    """The systems of the company, by id."""
    return {system["id"]: system for system in CompanySource().list_systems()}


def expert_reading(words: List[str], language: str = "en") -> Dict:
    """What understand answers for a plain request for an expert."""
    return {"road": "expert", "question_type": "help", "language": language, "search_words": words}


def ask_about_the_api(agent, scenarios: Dict, thread_id: str = None, language: str = "en") -> Dict:
    """Ask the vague question of scenario 8. The fake understand reads it as the real one does: "the API" fits two systems.

    Once the user has picked, the fake reads the completed question as a plain request for an expert.
    """
    workflow, fakes = agent
    turn = scenarios["s08a"]["turns"][0]
    fakes.understood = {
        "road": "unclear",
        "question_type": "help",
        "language": language,
        "search_words": ["API"],
        "unclear_systems": turn["expected"]["choices_systems"],
    }
    fakes.understood_next = [expert_reading(["Claims API"], language)]
    return workflow.full_pipeline(turn["question"], thread_id)


def ask_about_sophie(agent, question: str, asks: str = "card", thread_id: str = None) -> Dict:
    """Ask a question about "Sophie". The fake understand gives the first name, which two people have."""
    workflow, fakes = agent
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": "en",
        "search_words": [],
        "person_name": "Sophie",
        "person_asks": asks,
    }
    return workflow.full_pipeline(question, thread_id)


def pick(agent, choice_id: str, thread_id: str) -> Dict:
    """Answer the agent's question: the id of a choice, sent as an answer in the same conversation."""
    workflow, _ = agent
    return workflow.full_pipeline(choice_id, thread_id, is_answer=True)


def saved(agent, thread_id: str):
    """What the memory holds for one conversation."""
    workflow, _ = agent
    return workflow.compiled_workflow.get_state({"configurable": {"thread_id": thread_id}})


# ----------------------------------------------------------------------
# Scenario 8: a general word fits several systems, so the agent asks which one
# ----------------------------------------------------------------------


def test_a_general_word_pauses_the_run_and_asks_which_system(agent, scenarios, systems):
    """ "Who can help me with the API?": no guess and no search. The answer is a question, with two systems to pick."""
    _, fakes = agent
    expected = scenarios["s08a"]["turns"][0]["expected"]
    answer = ask_about_the_api(agent, scenarios)

    assert answer["status"] == expected["status"] == "needs_details"
    assert answer["message"] == ASK_USER_TEXTS["system"]["en"]
    # The choices come from the data: the id, the name, and the one-line description of each system
    assert answer["choices"] == [
        {"id": system_id, "name": systems[system_id]["name"], "detail": systems[system_id]["description"]}
        for system_id in expected["choices_systems"]
    ]
    assert expected["vague_word"] in " ".join(choice["name"] for choice in answer["choices"])
    assert answer["cards"] == [] and answer["person_card"] == {} and answer["note"] == ""
    # Nothing was searched, judged, or written: the agent waits for the answer first
    assert fakes.searches == [] and fakes.verified == [] and fakes.card_people == []


def test_a_paused_run_waits_in_the_memory(agent, scenarios):
    """The run stopped inside ask_user. The memory holds it, with the question it asks: ids, and nothing else."""
    answer = ask_about_the_api(agent, scenarios)
    snapshot = saved(agent, answer["thread_id"])

    # "next" names the node where the run will go on, and "interrupts" holds what interrupt() was given
    assert snapshot.next == ("ask_user",)
    assert len(snapshot.interrupts) == 1
    assert snapshot.interrupts[0].value == {"asks": "system", "choices": ["claims_api", "policy_api"]}
    # ask_user has not finished, so the state still says that nothing was asked
    assert snapshot.values["asked"] == "" and snapshot.values["picked"] == ""


def test_picking_a_system_continues_the_same_run(agent, scenarios, opted_out_names_in):
    """Scenario 8, when the user picks the Claims API: the run goes on, and the people of that system get a card."""
    _, fakes = agent
    question = scenarios["s08a"]["turns"][0]["question"]
    expected = scenarios["s08a"]["turns"][1]["expected"]
    first = ask_about_the_api(agent, scenarios)
    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    answer = pick(agent, "claims_api", first["thread_id"])

    assert answer["status"] == "answered"
    assert answer["thread_id"] == first["thread_id"]
    cards = [card["id"] for card in answer["cards"]]
    assert sorted(cards) == sorted(expected["people"])
    assert cards[0] == expected["people"][0]
    assert answer["choices"] == []
    # The note of scenario 1: one person who left is named, and one person who opted out is only counted
    assert answer["removed_left"] == expected["removed_left"]
    assert answer["removed_opted_out"] == expected["removed_opted_out"]
    assert opted_out_names_in(answer) == []

    # The answer went back to understand: it read the question twice, the second time with the system that was picked
    completed = f"{question} I mean: Claims API."
    assert fakes.questions == [question, completed]
    # And every step after it read the completed question, as if the user had typed it
    assert fakes.requests == {"search": [completed], "verify": [completed], "rewrite": [], "write_cards": [completed]}
    # The run is over: nothing is waiting any more
    snapshot = saved(agent, first["thread_id"])
    assert snapshot.next == () and snapshot.interrupts == ()
    assert snapshot.values["asked"] == "system" and snapshot.values["picked"] == "claims_api"


def test_the_system_that_was_picked_is_the_one_of_the_second_level(agent, scenarios):
    """After a pick, the code knows the system for sure. When nothing is about the exact need, its people are shown.

    The fake understand names no system here: the system of the second level is the one the user picked.
    """
    _, fakes = agent
    first = ask_about_the_api(agent, scenarios)
    # Two searches, and verify keeps nothing
    fakes.found = [["pg014"], ["pg013"]]
    answer = pick(agent, "policy_api", first["thread_id"])

    assert answer["status"] == "answered"
    assert answer["level"] == "system"
    assert answer["note"].startswith(NOTE_TEXTS["same_system"]["en"].format(systems="Policy API"))
    # p014 wrote the developer guide of the Policy API and handled one of its tickets
    assert answer["cards"][0]["id"] == "p014"
    # Every card only shows work on the Policy API
    shown = {label["id"] for card in answer["cards"] for label in card["evidence"]}
    assert shown <= {"pg004", "POL-131", "POL-152", "POL-176"}
    assert saved(agent, first["thread_id"]).values["named_systems"] == ["policy_api"]


def test_a_system_that_was_picked_is_a_topic(agent, scenarios):
    """After a pick, the request names a system for sure: it is never read as a request with no topic.

    The fake understand finds no search word here, and says "no topic". The system that the user picked
    is added to the search words, so the request is searched.
    """
    _, fakes = agent
    expected = scenarios["s08a"]["turns"][1]["expected"]
    first = ask_about_the_api(agent, scenarios)
    # What the fake understand answers at its next call, when it reads the question again with the pick
    fakes.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": [], "no_topic": True}
    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    answer = pick(agent, "claims_api", first["thread_id"])

    assert answer["status"] == "answered"
    assert sorted(card["id"] for card in answer["cards"]) == sorted(expected["people"])
    assert fakes.searches == [{"words": ["Claims API"], "retry": False}]
    assert saved(agent, first["thread_id"]).values["no_topic"] is False


def test_the_other_system_gets_its_own_people(agent, scenarios):
    """Scenario 8, when the user picks the Policy API: other evidence holds up, and another person comes first."""
    _, fakes = agent
    question = scenarios["s08b"]["turns"][0]["question"]
    expected = scenarios["s08b"]["turns"][1]["expected"]
    first = ask_about_the_api(agent, scenarios)
    fakes.understood = expert_reading(["Policy API"])
    fakes.understood_next = []
    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    answer = pick(agent, "policy_api", first["thread_id"])

    assert answer["status"] == "answered"
    assert answer["cards"][0]["id"] == expected["people"][0]
    assert fakes.questions[-1] == f"{question} I mean: Policy API."


def test_the_picked_system_is_always_a_search_word(agent, scenarios):
    """understand may leave the name of the picked system out of its search words: the code adds it, once."""
    _, fakes = agent
    # Evidence holds up at the first search, so each question searches once
    fakes.found = [["pg008"]]
    fakes.relevant = ["pg008"]
    first = ask_about_the_api(agent, scenarios)
    # The model only repeats the general word
    fakes.understood = expert_reading(["API", "access"])
    fakes.understood_next = []
    pick(agent, "claims_api", first["thread_id"])
    assert fakes.searches[-1]["words"] == ["Claims API", "API", "access"]

    # The model already wrote the name, inside a longer entry and in lower case: nothing is added
    second = ask_about_the_api(agent, scenarios)
    fakes.understood = expert_reading(["claims api tokens"])
    fakes.understood_next = []
    pick(agent, "claims_api", second["thread_id"])
    assert fakes.searches[-1]["words"] == ["claims api tokens"]


def test_a_french_question_is_asked_and_completed_in_french(agent, scenarios):
    """The question of the agent, and the sentence that adds the user's pick, are in the language of the question."""
    _, fakes = agent
    first = ask_about_the_api(agent, scenarios, language="fr")
    pick(agent, "policy_api", first["thread_id"])

    assert first["message"] == ASK_USER_TEXTS["system"]["fr"]
    assert fakes.questions[-1] == f"{scenarios['s08a']['turns'][0]['question']} Je veux dire : Policy API."


# ----------------------------------------------------------------------
# Scenario 12: several people have the name, so the agent asks which one
# ----------------------------------------------------------------------


def test_scenario_12_with_the_pause(agent, scenarios, people):
    """ "Tell me about Sophie.": the agent asks which Sophie, the user picks one, and that person's card is shown."""
    _, fakes = agent
    first_turn, second_turn = scenarios["s12"]["turns"]
    first = ask_about_sophie(agent, first_turn["question"])
    wanted = second_turn["expected"]["card"]

    assert first["status"] == "needs_details"
    assert first["message"] == ASK_USER_TEXTS["person"]["en"]
    assert [choice["id"] for choice in first["choices"]] == first_turn["expected"]["choices_people"]
    assert [choice["name"] for choice in first["choices"]] == ["Sophie Martin", "Sophie Nguyen"]
    assert saved(agent, first["thread_id"]).interrupts[0].value == {"asks": "person", "choices": ["p012", "p026"]}

    answer = pick(agent, wanted, first["thread_id"])
    assert answer["status"] == second_turn["expected"]["status"] == "person"
    assert answer["person_card"]["id"] == wanted
    assert answer["person_card"]["name"] == people[wanted]["name"]
    # understand read the same question twice. The person is not added to it: find_person takes the id that was picked
    assert fakes.questions == [first_turn["question"], first_turn["question"]]


def test_the_pick_continues_the_first_question(agent, people):
    """ "Who is Sophie's manager?", then a pick: the answer is the manager of that Sophie, not her own card.

    This is what the pause adds to M6, where the user had to ask again with the full name.
    The fake understand gives the name "Sophie" both times, so the pick is what decides between the two people.
    """
    for wanted in ["p012", "p026"]:
        first = ask_about_sophie(agent, "Who is Sophie's manager?", asks="manager")
        answer = pick(agent, wanted, first["thread_id"])
        manager = people[people[wanted]["manager"]]

        assert answer["status"] == "person"
        assert answer["person_card"]["id"] == manager["id"]
        assert answer["message"] == PERSON_TEXTS["manager"]["en"].format(name=people[wanted]["name"], manager=manager["name"])


def test_after_the_pick_her_is_the_person_of_the_card(agent, people):
    """The person shown after a pick is remembered like any other: the next "her" means this person."""
    workflow, fakes = agent
    first = ask_about_sophie(agent, "Tell me about Sophie.")
    pick(agent, "p026", first["thread_id"])
    fakes.understood = {**fakes.understood, "person_name": "", "person_asks": "manager"}
    answer = workflow.full_pipeline("And who's her manager?", first["thread_id"])

    assert answer["status"] == "person"
    assert answer["person_card"]["id"] == people["p026"]["manager"]


# ----------------------------------------------------------------------
# One question per request
# ----------------------------------------------------------------------


def test_the_agent_does_not_ask_about_the_system_twice(agent, scenarios):
    """The user picked a system, and the model still says "unclear": nothing is unclear any more, so the search runs."""
    _, fakes = agent
    expected = scenarios["s08a"]["turns"][1]["expected"]
    first = ask_about_the_api(agent, scenarios)
    # The second reading is "unclear" again, with the same two systems
    fakes.understood_next = []
    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    answer = pick(agent, "claims_api", first["thread_id"])

    assert answer["status"] == "answered"
    assert len(fakes.questions) == 2 and len(fakes.searches) == 1
    # The system is known, so the note does not say that it was unclear
    assert NOTE_TEXTS["unclear_system"]["en"] not in answer["note"]
    assert saved(agent, first["thread_id"]).interrupts == ()


def test_after_a_question_about_a_person_the_agent_does_not_ask_about_a_system(agent, scenarios):
    """The agent asked which Sophie. If a general word then fits several systems, it goes on, and says what was unclear."""
    _, fakes = agent
    evidence = scenarios["s01"]["turns"][0]["expected"]["evidence"]
    first = ask_about_sophie(agent, "Can Sophie help me with the tool?")
    # After the pick, understand reads the request as "unclear": a second question would be needed
    fakes.understood = {**expert_reading(["tool"]), "road": "unclear", "unclear_systems": ["claims_api", "policy_api"]}
    fakes.found = [evidence]
    fakes.relevant = evidence
    answer = pick(agent, "p026", first["thread_id"])

    # No second question: the search ran with what the agent had, and the note says what was unclear
    assert answer["status"] == "answered"
    assert answer["choices"] == []
    assert len(fakes.searches) == 1
    assert answer["note"].startswith(NOTE_TEXTS["unclear_system"]["en"])
    assert saved(agent, first["thread_id"]).interrupts == ()


def test_after_a_question_about_a_system_the_agent_does_not_ask_about_a_person(agent, scenarios):
    """The agent asked which system. If a name then fits several people, it does not ask again: it says so."""
    _, fakes = agent
    first = ask_about_the_api(agent, scenarios)
    # After the pick, understand reads the request as a question about "Sophie", and two people have that name
    fakes.understood = {**expert_reading([]), "road": "person", "person_name": "Sophie", "person_asks": "card"}
    fakes.understood_next = []
    answer = pick(agent, "claims_api", first["thread_id"])

    assert answer["status"] == "nobody_found"
    assert answer["message"] == NOBODY_FOUND_TEXTS["several_people"]["en"]
    assert answer["choices"] == [] and answer["person_card"] == {}
    assert saved(agent, first["thread_id"]).interrupts == ()


def test_the_next_question_can_ask_again(agent, scenarios):
    """ "One question per request" is per request: the next question of the conversation starts fresh, and can pause."""
    first = ask_about_the_api(agent, scenarios)
    pick(agent, "claims_api", first["thread_id"])
    again = ask_about_the_api(agent, scenarios, thread_id=first["thread_id"])

    assert again["status"] == "needs_details"
    assert len(again["choices"]) == 2
    assert saved(agent, first["thread_id"]).values["asked"] == ""


# ----------------------------------------------------------------------
# What is typed is a new question, and only a real choice is an answer
# ----------------------------------------------------------------------


def test_a_new_question_instead_of_a_pick_starts_again(agent, scenarios):
    """The agent waits for a pick, and the user asks something else: the new question is answered, and the pause is gone."""
    workflow, fakes = agent
    first = ask_about_the_api(agent, scenarios)
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    fakes.understood_next = []
    second = workflow.full_pipeline("What should I cook tonight?", first["thread_id"])

    assert second["status"] == "off_topic"
    assert saved(agent, first["thread_id"]).interrupts == ()

    # A late click on a choice of the first question: nothing is waiting for it, and nothing runs
    asked_so_far = len(fakes.questions)
    late = pick(agent, "claims_api", first["thread_id"])
    assert late["status"] == "needs_details"
    assert late["message"] == ASK_USER_TEXTS["not_waiting"]["en"]
    assert late["choices"] == [] and late["cards"] == [] and late["steps"] == []
    assert len(fakes.questions) == asked_so_far


def test_an_answer_that_is_not_a_choice_asks_the_question_again(agent, scenarios):
    """Only one of the choices is an answer. Anything else changes nothing: the same question comes back, and waits."""
    _, fakes = agent
    first = ask_about_the_api(agent, scenarios)
    for not_a_choice in ["pricing_engine", "Claims API", "p012", "1"]:
        again = pick(agent, not_a_choice, first["thread_id"])
        assert again["status"] == "needs_details"
        assert again["message"] == first["message"] and again["choices"] == first["choices"]
    assert len(fakes.questions) == 1 and fakes.searches == []
    assert saved(agent, first["thread_id"]).next == ("ask_user",)

    # The real choice still works afterwards
    assert pick(agent, "policy_api", first["thread_id"])["status"] != "needs_details"


def test_an_answer_in_a_conversation_that_is_not_waiting(agent):
    """An answer with the id of a conversation that does not exist, or that never asked anything: a fixed text."""
    workflow, fakes = agent
    unknown = pick(agent, "claims_api", "a-conversation-that-does-not-exist")
    assert unknown["status"] == "needs_details"
    assert unknown["message"] == ASK_USER_TEXTS["not_waiting"]["en"]
    assert fakes.questions == []

    # A French conversation that is not paused gets the French text
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "fr", "search_words": []}
    french = workflow.full_pipeline("Quel temps fait-il ?")
    answer = pick(agent, "claims_api", french["thread_id"])
    assert answer["message"] == ASK_USER_TEXTS["not_waiting"]["fr"]
    assert answer["thread_id"] == french["thread_id"]


# ----------------------------------------------------------------------
# The memory around a pause
# ----------------------------------------------------------------------


def test_a_pause_does_not_change_the_people_shown(agent, scenarios):
    """Scenario 1, then the vague question in the same conversation: while the agent waits, "her" is still the first card."""
    workflow, fakes = agent
    turn = scenarios["s01"]["turns"][0]
    fakes.understood = expert_reading(["access"])
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    first = workflow.full_pipeline(turn["question"])
    shown = [card["id"] for card in first["cards"]]

    paused = ask_about_the_api(agent, scenarios, thread_id=first["thread_id"])
    assert paused["status"] == "needs_details"
    assert saved(agent, first["thread_id"]).values["shown_people"] == shown


def test_the_memory_of_a_pause_holds_ids_and_no_name(agent, people):
    """The question and the pick of a pause are saved as ids: the names of the choices are never in the memory."""
    workflow, _ = agent
    first = ask_about_sophie(agent, "Tell me about Sophie.")
    pick(agent, "p026", first["thread_id"])
    config = {"configurable": {"thread_id": first["thread_id"]}}
    history = list(workflow.compiled_workflow.get_state_history(config))
    everything = json.dumps(
        [[snapshot.values, [interrupt.value for interrupt in snapshot.interrupts]] for snapshot in history],
        ensure_ascii=False,
    )

    # The ids of the two people, and the pick. The first name is there because the user typed it in the question
    assert "p012" in everything and "p026" in everything
    for person_id in ["p012", "p026"]:
        assert people[person_id]["last_name"] not in everything
        assert people[person_id]["email"] not in everything
        assert people[person_id]["job_title"] not in everything


# ----------------------------------------------------------------------
# The step lines around a pause, and the events of a run
# ----------------------------------------------------------------------


def test_the_step_lines_of_a_question_with_a_pause(agent, scenarios):
    """Before the pause: one line. After the pick: the lines of the rest of the run, from "Noted your answer" on."""
    _, fakes = agent
    expected = scenarios["s08a"]["turns"][1]["expected"]
    first = ask_about_the_api(agent, scenarios)
    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    answer = pick(agent, "claims_api", first["thread_id"])

    assert first["steps"] == ["Read your question: it could be about 2 systems"]
    assert answer["steps"] == [
        "Noted your answer",
        "Read your question again, with your answer: you are looking for someone who can help",
        'Searched pages and tickets for "Claims API": 9 results',
        "Checked 9 results: 9 are really about your question",
        "Found 5 people behind these pages and tickets",
        "Removed: 1 person who left the company, 1 person who opted out",
        "Wrote the cards of 3 people",
    ]


def test_a_run_gives_its_steps_one_by_one_and_then_the_answer(agent, scenarios):
    """stream_pipeline gives one event per finished step, in order, and the answer as its last event."""
    workflow, fakes = agent
    turn = scenarios["s01"]["turns"][0]
    fakes.understood = expert_reading(["access"])
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    events = list(workflow.stream_pipeline(turn["question"]))

    assert [event["type"] for event in events] == ["step"] * 6 + ["answer"]
    answer = events[-1]["answer"]
    assert answer["status"] == "answered"
    # The lines that arrived one by one are also in the answer, for a caller that only reads the end
    assert [event["text"] for event in events[:-1]] == answer["steps"]
    assert answer["steps"][0] == "Read your question: you are looking for someone who can help"
    assert answer["steps"][-1] == "Wrote the cards of 3 people"


def test_a_paused_run_ends_its_events_with_the_question(agent, scenarios):
    """A run that pauses gives the steps it finished, then an answer that is the question of the agent."""
    workflow, fakes = agent
    turn = scenarios["s08a"]["turns"][0]
    fakes.understood = {**expert_reading(["API"]), "road": "unclear", "unclear_systems": ["claims_api", "policy_api"]}
    events = list(workflow.stream_pipeline(turn["question"]))

    assert [event["type"] for event in events] == ["step", "answer"]
    assert events[-1]["answer"]["status"] == "needs_details"
    assert len(events[-1]["answer"]["choices"]) == 2
