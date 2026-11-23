"""Free tests of the memory: what a conversation remembers from one question to the next. No OpenAI calls.

The graph is the real one, with fake LLM steps (the helpers of conftest.py). In the first part, the conversations
are kept in the memory of the program, with LangGraph's in-memory saver: these tests don't need Postgres.
The last part uses the real Postgres, the one of POSTGRES_URI. It is skipped when the setting is missing,
and each test deletes the conversations it wrote.
"""

import json
from typing import Callable, Dict, Iterator, List, Tuple
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import psycopg
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from psycopg_pool import ConnectionPool
from pydantic import SecretStr

from agents import AgentWorkflow
from agents.evidence_searcher import EvidenceSearcher
from agents.request_reader import Understanding
from config.settings import settings
from config.texts import ASK_USER_TEXTS, NOBODY_FOUND_TEXTS
from sources import EvidenceSource, PeopleSource

# The follow-up of scenario 9: it names nobody
FOLLOW_UP = "And who's her manager?"


@pytest.fixture(scope="module")
def people() -> Dict:
    """The directory, by person id."""
    return {person["id"]: person for person in PeopleSource().list_people()}


def ask_scenario_1(agent, scenarios: Dict, thread_id: str = None) -> Dict:
    """Ask the question of scenario 1, with fakes that find and keep the evidence the scenario lists: three cards."""
    workflow, fakes = agent
    turn = scenarios["s01"]["turns"][0]
    fakes.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": ["access"]}
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    return workflow.full_pipeline(turn["question"], thread_id)


def ask_about(agent, question: str, name: str, asks: str, thread_id: str = None) -> Dict:
    """Ask one question about a colleague. The fake understand gives the name ("" for "her") and what is asked."""
    workflow, fakes = agent
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": "en",
        "search_words": [],
        "person_name": name,
        "person_asks": asks,
    }
    return workflow.full_pipeline(question, thread_id)


# ----------------------------------------------------------------------
# The id of a conversation
# ----------------------------------------------------------------------


def test_every_answer_gives_the_id_of_its_conversation(agent, scenarios):
    """A first question starts a conversation with a random id. A question that sends the id stays in it."""
    first = ask_scenario_1(agent, scenarios)
    second = ask_about(agent, FOLLOW_UP, "", "manager", first["thread_id"])
    other = ask_scenario_1(agent, scenarios)

    # 32 letters and digits: nobody can guess the id of someone else's conversation
    assert len(first["thread_id"]) == 32 and first["thread_id"].isalnum()
    assert second["thread_id"] == first["thread_id"]
    assert other["thread_id"] != first["thread_id"]


def test_without_postgres_the_memory_is_in_the_program(agent):
    """No POSTGRES_URI: the app runs normally, with LangGraph's in-memory saver and no connection to Postgres."""
    workflow, _ = agent
    assert isinstance(workflow.checkpointer, InMemorySaver)
    assert workflow.pool is None
    # close() has nothing to close, and it can be called anyway
    workflow.close()


def loads_plain_data_only(workflow: AgentWorkflow) -> bool:
    """True if the memory of this agent refuses to rebuild anything but plain data when it loads a saved state."""
    # A Pydantic object is not plain data. The serializer is what turns a state into bytes, and back
    serializer = workflow.checkpointer.serde
    something = Understanding(
        reason="r",
        road="expert",
        question_type="help",
        language="en",
        search_words=[],
        unclear_systems=[],
        named_systems=[],
        person_name="",
        person_asks="card",
    )
    plain = {"question": "Who?", "attempts": 0, "shown_people": ["p012"], "ranking": [{"person": "p012", "first": True}]}
    plain_is_kept = serializer.loads_typed(serializer.dumps_typed(plain)) == plain
    # In the strict mode the object comes back as a plain dict. In the default mode, it would be rebuilt
    object_is_rebuilt = isinstance(serializer.loads_typed(serializer.dumps_typed(something)), Understanding)
    return plain_is_kept and not object_is_rebuilt


def test_the_memory_only_loads_plain_data(agent):
    """The strict mode that the README of LangGraph's Postgres saver asks for: plain data comes back, and nothing else."""
    workflow, _ = agent
    assert loads_plain_data_only(workflow)


def test_the_nul_character_is_removed_from_a_question(agent):
    """A question with a NUL character in it: the agent reads it without that character, whatever the memory is."""
    workflow, fakes = agent
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    answer = workflow.full_pipeline("What should I cook\u0000 tonight?")

    assert answer["status"] == "off_topic"
    assert fakes.questions == ["What should I cook tonight?"]


# ----------------------------------------------------------------------
# A follow-up knows the people of the earlier answers
# ----------------------------------------------------------------------


def test_scenario_9_as_a_follow_up(agent, scenarios, people):
    """Scenario 1, then "And who's her manager?": "her" is the first person shown, and the answer names her."""
    expected = scenarios["s09b"]["turns"][1]["expected"]
    first = ask_scenario_1(agent, scenarios)
    answer = ask_about(agent, FOLLOW_UP, "", "manager", first["thread_id"])

    assert first["cards"][0]["id"] == expected["subject"]
    assert answer["status"] == "person"
    assert answer["person_card"]["id"] == expected["card"]
    assert answer["message"] == (
        f"{people[expected['subject']]['name']}'s manager is {people[expected['card']]['name']}."
    )
    # The manager is not one of the three people of the first answer
    assert expected["card"] not in [card["id"] for card in first["cards"]]


def test_the_same_follow_up_in_another_conversation_knows_nobody(agent, scenarios):
    """The follow-up without the id of the conversation, or with another id: "her" means nobody, and the agent says so."""
    ask_scenario_1(agent, scenarios)

    for thread_id in [None, "another-conversation"]:
        answer = ask_about(agent, FOLLOW_UP, "", "manager", thread_id)
        assert answer["status"] == "nobody_found"
        assert answer["message"] == NOBODY_FOUND_TEXTS["no_one_meant"]["en"]


def test_a_first_name_means_the_person_on_the_cards(agent, scenarios, people):
    """After the cards, "Sophie" is the Sophie of the first card. In a new conversation, the agent asks which Sophie."""
    first = ask_scenario_1(agent, scenarios)
    after_the_cards = ask_about(agent, "Tell me about Sophie.", "Sophie", "card", first["thread_id"])
    new_conversation = ask_about(agent, "Tell me about Sophie.", "Sophie", "card")

    assert after_the_cards["status"] == "person"
    assert after_the_cards["person_card"]["id"] == first["cards"][0]["id"]
    assert new_conversation["status"] == "needs_details"
    assert new_conversation["message"] == ASK_USER_TEXTS["person"]["en"]


def test_the_person_questions_of_the_demo_video(agent, scenarios, people):
    """The demo path after the cards: Sophie's manager, then "she" is that manager, then the manager by first name."""
    workflow, _ = agent
    demo = scenarios["demo"]["turns"]
    manager = people[demo[2]["expected"]["card"]]
    first = ask_scenario_1(agent, scenarios)
    thread_id = first["thread_id"]

    # "Sophie is away. Who's her manager?": Sophie is the Sophie of the cards
    answer = ask_about(agent, demo[2]["question"], "Sophie", "manager", thread_id)
    assert answer["person_card"]["id"] == manager["id"]
    assert people[demo[2]["expected"]["subject"]]["name"] in answer["message"]

    # "What does she work on?": "she" is now the manager, the last person shown
    answer = ask_about(agent, demo[3]["question"], "", "work", thread_id)
    assert answer["person_card"]["id"] == manager["id"]
    assert manager["name"] in answer["message"]
    assert len(answer["person_card"]["work"]) >= 2

    # "What's Hélène's work phone?": a first name that someone already shown has
    answer = ask_about(agent, demo[4]["question"], manager["first_name"], "work_phone", thread_id)
    assert answer["person_card"]["id"] == manager["id"]
    assert answer["person_card"]["work_phone"] == manager["work_phone"]

    # And "Sophie" still means the Sophie of the first cards, three answers later
    answer = ask_about(agent, "And what is Sophie's job title?", "Sophie", "card", thread_id)
    sophie = demo[2]["expected"]["subject"]
    assert answer["person_card"]["id"] == sophie

    # What the conversation remembers after these five answers: the people shown, the most recent first.
    # The manager was shown three times and Sophie twice, and each of them is in the list once
    remembered = workflow.compiled_workflow.get_state({"configurable": {"thread_id": thread_id}}).values["shown_people"]
    others = [card["id"] for card in first["cards"] if card["id"] != sophie]
    assert remembered == [sophie, manager["id"]] + others
    assert len(remembered) == len(set(remembered))


def test_two_conversations_do_not_mix(agent, scenarios, people):
    """Each conversation has its own people: "her" in one never means someone shown in the other."""
    first = ask_scenario_1(agent, scenarios)
    # Another conversation, about someone else: a developer of another team
    other_person = people["p010"]
    second = ask_about(agent, f"Who is {other_person['name']}?", other_person["name"], "card")

    in_first = ask_about(agent, FOLLOW_UP, "", "manager", first["thread_id"])
    in_second = ask_about(agent, FOLLOW_UP, "", "manager", second["thread_id"])

    assert in_first["person_card"]["id"] == people[first["cards"][0]["id"]]["manager"]
    assert in_second["person_card"]["id"] == other_person["manager"]
    assert in_first["person_card"]["id"] != in_second["person_card"]["id"]


# ----------------------------------------------------------------------
# What a conversation keeps, and what starts fresh at each question
# ----------------------------------------------------------------------


def test_each_question_starts_fresh(agent):
    """The retry counter and the texts already judged belong to one question: the next one starts from zero."""
    workflow, fakes = agent
    # The first question searches twice and finds nobody. The third search belongs to the second question
    fakes.found = [["pg004"], ["pg014"], ["pg004", "pg008"]]
    fakes.relevant = ["pg008"]
    first = workflow.full_pipeline("Who can help me order a laptop?")
    second = workflow.full_pipeline("Who can help me order a desk?", first["thread_id"])

    assert first["status"] == "nobody_found" and fakes.rewrites == 1
    assert second["status"] == "answered"
    # The second question had its own first search, not a retry, and verify judged pg004 again
    assert [search["retry"] for search in fakes.searches] == [False, True, False]
    assert fakes.verified[-1] == ["pg004", "pg008"]
    assert fakes.rewrites == 1


def test_nothing_of_an_answer_leaks_into_the_next_one(agent, scenarios):
    """Scenario 1 shows three cards and a note. A refused question after it has no card, no note, and nobody removed."""
    workflow, fakes = agent
    first = ask_scenario_1(agent, scenarios)
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    second = workflow.full_pipeline("What should I cook tonight?", first["thread_id"])

    assert first["cards"] and first["note"] and first["removed_left"]
    assert second["status"] == "off_topic"
    assert second["cards"] == [] and second["note"] == ""
    assert second["removed_left"] == [] and second["removed_opted_out"] == 0
    assert second["person_card"] == {} and second["choices"] == []


def test_a_question_that_shows_nobody_does_not_erase_the_people_shown(agent, scenarios):
    """A refusal between two questions: "her" still means the first person of the last answer that showed someone."""
    workflow, fakes = agent
    first = ask_scenario_1(agent, scenarios)
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    workflow.full_pipeline("What should I cook tonight?", first["thread_id"])

    answer = ask_about(agent, FOLLOW_UP, "", "manager", first["thread_id"])
    assert answer["status"] == "person"


def test_a_failed_question_does_not_block_its_conversation(agent, scenarios, monkeypatch):
    """A step fails in the middle of a question: the next question of the conversation is answered normally."""
    workflow, fakes = agent
    first = ask_scenario_1(agent, scenarios)

    def broken_verify(question: str, items: list) -> Dict:
        raise RuntimeError("OpenAI did not answer")

    with monkeypatch.context() as patch:
        patch.setattr(workflow.verifier, "verify", broken_verify)
        with pytest.raises(RuntimeError):
            ask_scenario_1(agent, scenarios, first["thread_id"])

    # The people of the first answer are still remembered, and the follow-up works
    answer = ask_about(agent, FOLLOW_UP, "", "manager", first["thread_id"])
    assert answer["status"] == "person"
    assert answer["person_card"]["id"] == scenarios["s09b"]["turns"][1]["expected"]["card"]


def test_the_memory_keeps_people_as_ids(agent, scenarios, people):
    """What a conversation remembers about people is a list of ids, the most recent first. No name, email, or phone."""
    workflow, _ = agent
    first = ask_scenario_1(agent, scenarios)
    ask_about(agent, FOLLOW_UP, "", "manager", first["thread_id"])
    config = {"configurable": {"thread_id": first["thread_id"]}}

    # get_state reads what the memory holds for one conversation
    saved = workflow.compiled_workflow.get_state(config).values
    manager = scenarios["s09b"]["turns"][1]["expected"]["card"]
    assert saved["shown_people"] == [manager] + [card["id"] for card in first["cards"]]

    # Every state that was saved for this conversation, step after step. The questions named nobody,
    # so nothing in it is a name, an email, or a phone number of the directory
    everything = json.dumps(
        [snapshot.values for snapshot in workflow.compiled_workflow.get_state_history(config)], ensure_ascii=False
    )
    assert first["thread_id"] not in everything and "p012" in everything
    for person in people.values():
        assert person["email"] not in everything
        assert person["last_name"] not in everything
        assert not person["work_phone"] or person["work_phone"] not in everything


# ----------------------------------------------------------------------
# The memory in Postgres (the real one). Skipped when POSTGRES_URI is not set
# ----------------------------------------------------------------------

postgres_is_set = settings.POSTGRES_URI is not None and bool(settings.POSTGRES_URI.get_secret_value().strip())
needs_postgres = pytest.mark.skipif(
    not postgres_is_set, reason="POSTGRES_URI is not set, so the tests of the memory in Postgres are skipped"
)


@pytest.fixture
def conversations() -> Iterator[List[str]]:
    """The ids of the conversations that a test writes to Postgres. They are deleted when the test ends."""
    thread_ids: List[str] = []
    yield thread_ids
    # A saver of its own for the clean-up, so it works whatever the test did to its agents
    with PostgresSaver.from_conn_string(settings.POSTGRES_URI.get_secret_value().strip()) as saver:
        for thread_id in thread_ids:
            saver.delete_thread(thread_id)


def rows_of(thread_id: str) -> bytes:
    """Everything Postgres holds for one conversation, as raw bytes: the three tables of the saver."""
    queries = [
        "select convert_to(checkpoint::text, 'UTF8') || convert_to(metadata::text, 'UTF8') from checkpoints where thread_id = %s",
        "select blob from checkpoint_blobs where thread_id = %s and blob is not null",
        "select blob from checkpoint_writes where thread_id = %s",
    ]
    with psycopg.connect(settings.POSTGRES_URI.get_secret_value().strip()) as connection:
        return b" ".join(bytes(row[0]) for query in queries for row in connection.execute(query, (thread_id,)))


@needs_postgres
def test_a_conversation_in_postgres_survives_a_restart(build_agent, scenarios, conversations):
    """The app answers scenario 1, stops, and starts again: the follow-up still knows who "her" is."""
    # 1) The app before the restart: one question, then its connections to Postgres are closed
    before = build_agent(postgres=True)
    assert isinstance(before[0].checkpointer, PostgresSaver)
    # The saver for Postgres has the same strict loading as the one in the program
    assert loads_plain_data_only(before[0])
    first = ask_scenario_1(before, scenarios)
    conversations.append(first["thread_id"])
    before[0].close()

    # 2) A new agent, as after a restart: nothing of the first one is left in the program
    after = build_agent(postgres=True)
    answer = ask_about(after, FOLLOW_UP, "", "manager", first["thread_id"])

    assert answer["status"] == "person"
    assert answer["person_card"]["id"] == scenarios["s09b"]["turns"][1]["expected"]["card"]


@needs_postgres
def test_what_postgres_holds_for_a_conversation(build_agent, scenarios, conversations, people):
    """The rows of one conversation: ids from the data and the text of the questions, but nothing of the directory."""
    agent = build_agent(postgres=True)
    first = ask_scenario_1(agent, scenarios)
    conversations.append(first["thread_id"])
    ask_about(agent, FOLLOW_UP, "", "manager", first["thread_id"])
    saved = rows_of(first["thread_id"])

    # 1) My own words: the text of both questions, the first one too, although a second one came after it
    assert scenarios["s01"]["turns"][0]["question"].encode() in saved
    assert FOLLOW_UP.encode() in saved
    # 2) Ids from the data: the people shown, the tickets and pages found, and the people the HR check removed
    #    (who left, and who opted out). Ids, never names
    assert b"p012" in saved and b"p007" in saved
    assert b"pg008" in saved and b"CLM-212" in saved
    removed = first["removed_left"] + [person["id"] for person in people.values() if not person["discoverable"]]
    assert len(removed) == 2
    for person_id in removed:
        assert person_id.encode() in saved
    # 3) The three short texts the LLM wrote for each card (here, the ones of the fake step)
    assert agent[1].card_text["why"].encode() in saved
    assert agent[1].card_text["message"].encode() in saved
    assert agent[1].card_text["subject"].encode() in saved
    # 4) Nothing of the directory: the answer got its names, emails, and phones after the graph, and they are not saved
    for person in people.values():
        assert person["email"].encode() not in saved
        assert person["last_name"].encode() not in saved
        assert not person["work_phone"] or person["work_phone"].encode() not in saved


@needs_postgres
def test_a_paused_run_in_postgres_survives_a_restart(build_agent, scenarios, conversations):
    """The agent asks which system, the app stops and starts again, and the pick still continues the same question.

    The paused run waits in Postgres: its state, and the question it asks, with its choices as ids.
    """
    # 1) The app before the restart: the vague question of scenario 8, read as the real understand reads it
    turn = scenarios["s08a"]["turns"][0]
    before = build_agent(postgres=True)
    before[1].understood = {
        "road": "unclear",
        "question_type": "help",
        "language": "en",
        "search_words": ["API"],
        "unclear_systems": turn["expected"]["choices_systems"],
    }
    first = before[0].full_pipeline(turn["question"])
    conversations.append(first["thread_id"])
    assert first["status"] == "needs_details"
    before[0].close()

    # 2) What Postgres holds for the paused run: the ids of the two choices, and no name of a system or a person
    waiting = rows_of(first["thread_id"])
    assert b"claims_api" in waiting and b"policy_api" in waiting
    assert turn["question"].encode() in waiting

    # 3) A new agent, as after a restart. The pick goes on with the question, and its completed text is searched
    evidence = scenarios["s08a"]["turns"][1]["expected"]["evidence"]
    workflow, fakes = build_agent(postgres=True)
    fakes.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": ["Claims API"]}
    fakes.found = [evidence]
    fakes.relevant = evidence
    answer = workflow.full_pipeline("claims_api", first["thread_id"], is_answer=True)

    assert answer["status"] == "answered"
    assert fakes.questions == [f"{turn['question']} I mean: Claims API."]
    assert [card["id"] for card in answer["cards"]][0] == scenarios["s08a"]["turns"][1]["expected"]["people"][0]


@needs_postgres
def test_my_name_and_my_team_are_never_in_postgres(build_agent, scenarios, conversations):
    """What I type in the two boxes fills the messages of the answer, and Postgres holds nothing of it."""
    agent = build_agent(postgres=True)
    workflow, fakes = agent
    turn = scenarios["s01"]["turns"][0]
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    answer = workflow.full_pipeline(turn["question"], user_name="Zebulon", user_team="Quokka")
    conversations.append(answer["thread_id"])

    assert "I'm Zebulon from Quokka." in answer["cards"][0]["message"]
    saved = rows_of(answer["thread_id"])
    assert turn["question"].encode() in saved
    assert b"Zebulon" not in saved and b"Quokka" not in saved


@needs_postgres
def test_deleting_a_conversation_removes_its_rows(build_agent, scenarios, conversations):
    """The clean-up of these tests really cleans: after delete_thread, Postgres holds nothing for the conversation."""
    agent = build_agent(postgres=True)
    first = ask_scenario_1(agent, scenarios)
    conversations.append(first["thread_id"])
    assert rows_of(first["thread_id"])

    agent[0].checkpointer.delete_thread(first["thread_id"])
    assert rows_of(first["thread_id"]) == b""


@needs_postgres
def test_a_question_with_a_nul_character_is_answered_with_postgres(build_agent, conversations):
    """Postgres can't store the NUL character in a text. The agent removes it, so the question is answered.

    Without this, the question failed like a Postgres outage, although nothing was wrong with Postgres.
    """
    workflow, fakes = build_agent(postgres=True)
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    # The id is made here, so the conversation is deleted at the end even if the question fails
    thread_id = uuid4().hex
    conversations.append(thread_id)
    answer = workflow.full_pipeline("What should I cook\u0000 tonight?", thread_id)

    assert answer["status"] == "off_topic"
    assert fakes.questions == ["What should I cook tonight?"]


@needs_postgres
def test_an_agent_that_cannot_be_built_leaves_no_connection_open(monkeypatch):
    """Postgres opens, then another step of the start fails: the connections to Postgres are closed before the error."""
    opened = []
    open_pool = ConnectionPool.open

    def remember_the_pool(self, *args, **kwargs):
        opened.append(self)
        return open_pool(self, *args, **kwargs)

    def no_evidence(self):
        raise RuntimeError("MongoDB did not answer")

    monkeypatch.setattr(ConnectionPool, "open", remember_the_pool)
    monkeypatch.setattr(EvidenceSource, "__init__", no_evidence)
    monkeypatch.setattr(settings, "LANGSMITH_API_KEY", None)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")

    with pytest.raises(RuntimeError, match="MongoDB did not answer"):
        AgentWorkflow()
    # One pool was opened, and it is closed again
    assert len(opened) == 1 and opened[0].closed


@needs_postgres
def test_postgres_closed_during_a_question_is_an_error(build_agent, scenarios):
    """The connections to Postgres are gone while the app runs: the question fails. It is never answered without memory."""
    agent = build_agent(postgres=True)
    agent[0].pool.close()

    # A short error of our own takes the place of the one of the Postgres driver
    with pytest.raises(RuntimeError, match="The memory in Postgres did not answer"):
        ask_scenario_1(agent, scenarios)


# ----------------------------------------------------------------------
# When Postgres can't be opened: the app stops at the start, and the address is never shown
# ----------------------------------------------------------------------


def start_with(monkeypatch, address: str) -> Callable[[], AgentWorkflow]:
    """Prepare an agent whose POSTGRES_URI is this address. Nothing may call the internet while it is built."""
    monkeypatch.setattr(settings, "POSTGRES_URI", SecretStr(address))
    monkeypatch.setattr(settings, "LANGSMITH_API_KEY", None)
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    monkeypatch.setattr(EvidenceSearcher, "__init__", lambda self, items: None)
    return AgentWorkflow


def changed(address_part: Tuple[str, str]) -> str:
    """The real address of POSTGRES_URI, with one part replaced: the password, or the name of the database."""
    part, value = address_part
    parts = urlsplit(settings.POSTGRES_URI.get_secret_value().strip())
    host = parts.hostname + (f":{parts.port}" if parts.port else "")
    if part == "password":
        return urlunsplit(parts._replace(netloc=f"{parts.username}:{value}@{host}"))
    return urlunsplit(parts._replace(path=f"/{value}"))


def test_an_address_that_is_not_a_postgres_address_stops_the_start(monkeypatch):
    """A POSTGRES_URI that does not start with postgresql://: the app stops, and the error does not repeat the value."""
    build = start_with(monkeypatch, "my-secret-password-is-not-an-address")
    with pytest.raises(RuntimeError, match="POSTGRES_URI must start with postgresql://") as error:
        build()
    assert "my-secret" not in str(error.value)


def test_postgres_not_answering_stops_the_start(monkeypatch):
    """Nothing answers at the address: the app stops with a short error, before any OpenAI call, and shows no password."""
    # Port 1 of this computer: no Postgres listens there. A short wait keeps the test fast
    monkeypatch.setattr("agents.workflow.POSTGRES_TIMEOUT_SECONDS", 2)
    build = start_with(monkeypatch, "postgresql://someone:my-secret-password@127.0.0.1:1/who_to_ask")
    with pytest.raises(RuntimeError, match="Could not open the memory in Postgres") as error:
        build()
    assert "Is the PostgreSQL service running" in str(error.value)
    assert "my-secret" not in str(error.value) and "someone" not in str(error.value)


@needs_postgres
@pytest.mark.parametrize(
    "address_part, hint",
    [
        (("password", "not-the-password"), "refused the user name or the password"),
        (("database", "no_such_database_x"), "does not exist: create it in pgAdmin"),
    ],
    ids=["a wrong password", "a database that does not exist"],
)
def test_the_error_says_what_to_check(monkeypatch, address_part, hint):
    """A wrong password, or a database that was never created: the error names the cause, and never the address."""
    build = start_with(monkeypatch, changed(address_part))
    with pytest.raises(RuntimeError, match="Could not open the memory in Postgres") as error:
        build()
    assert hint in str(error.value)
    assert address_part[1] not in str(error.value)
