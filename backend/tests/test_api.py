"""Tests of the API: what POST /ask answers. They are free (no OpenAI calls), except the last one, which is marked.

The API is the real one, with its real start-up. In the free tests, the agent behind it is the real graph with fake
LLM steps (the agent helper of conftest.py): a request still runs the routers, the HR check, and the answer for real.
"""

import json
from typing import Dict, Iterator, Tuple

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api import main
from config.constants import MAX_QUESTION_LENGTH, MAX_USER_TEXT_LENGTH, PAGE_ORIGINS
from config.settings import settings
from config.texts import FAILSAFE_TEXTS, NOBODY_FOUND_TEXTS
from sources import MongoStore, SeedFiles

# A question for the tests where the fakes decide the answer, so the words of the question don't matter
QUESTION = "Who can help me order a laptop?"


@pytest.fixture
def api(agent, monkeypatch) -> Iterator[Tuple[TestClient, object]]:
    """A test client of the API, and the fakes of the agent behind it.

    TestClient calls the app directly, inside this process: no server is started, and no port is used.
    Its "with" block runs the start-up of the API, which builds the agent: here it gets the agent with fake LLM steps.
    """
    workflow, fakes = agent
    monkeypatch.setattr(main, "AgentWorkflow", lambda: workflow)
    with TestClient(main.app) as client:
        yield client, fakes


def ask_scenario_1(client: TestClient, fakes, scenarios: Dict):
    """Send the question of scenario 1, with fakes that find and keep the evidence the scenario lists."""
    turn = scenarios["s01"]["turns"][0]
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    return client.post("/ask", json={"question": turn["question"]})


# ----------------------------------------------------------------------
# An answer: the result of the agent, as JSON
# ----------------------------------------------------------------------


def test_scenario_1_through_the_api_with_fake_llm_steps(api, scenarios, opted_out_names_in):
    """The question of scenario 1 comes back with its three cards, each with a message and two link fields."""
    client, fakes = api
    expected = scenarios["s01"]["turns"][0]["expected"]
    response = ask_scenario_1(client, fakes, scenarios)

    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "answered"
    cards = [card["id"] for card in answer["cards"]]
    assert sorted(cards) == sorted(expected["people"])
    assert cards[0] == expected["people"][0]

    # In the API, the two buttons of a card are two link fields
    for card in answer["cards"]:
        assert card["why"] and card["message"] and card["evidence"]
        assert card["teams_link"].startswith("https://teams.microsoft.com/l/chat/0/0?users=")
        assert card["email_link"].startswith(f"mailto:{card['email']}?subject=")

    # The note: one person who left is named, and one person who opted out is only counted
    assert answer["removed_left"] == expected["removed_left"]
    assert answer["removed_opted_out"] == expected["removed_opted_out"]
    assert "no longer works at the company" in answer["note"]
    assert opted_out_names_in(answer) == []


def test_the_api_returns_the_answer_of_the_agent_unchanged(api, agent, scenarios):
    """What comes out of the API is what full_pipeline returns: the same keys and the same values, written as JSON."""
    client, fakes = api
    workflow, _ = agent
    response = ask_scenario_1(client, fakes, scenarios)

    assert response.headers["content-type"] == "application/json"
    # The same question, asked to the agent directly in the same conversation, gives the same answer
    answer = response.json()
    assert answer == workflow.full_pipeline(scenarios["s01"]["turns"][0]["question"], answer["thread_id"])


def test_a_refusal_is_a_normal_answer(api):
    """A question that is not about work is answered with 200: the agent worked, and the status says what it decided."""
    client, fakes = api
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    response = client.post("/ask", json={"question": "What should I cook tonight?"})

    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "off_topic"
    assert answer["reason"] == "not_work"
    assert answer["message"] == FAILSAFE_TEXTS["not_work"]["en"]
    assert answer["cards"] == []


def test_nobody_found_is_a_normal_answer(api):
    """Nothing holds up: the answer is 200 with the status "nobody_found", not an HTTP error."""
    client, fakes = api
    # pg004 is the guide of another system, and the fake verify keeps nothing
    fakes.found = [["pg004"]]
    response = client.post("/ask", json={"question": QUESTION})

    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "nobody_found"
    assert answer["message"] == NOBODY_FOUND_TEXTS["general"]["en"]
    assert answer["cards"] == []


def test_a_question_about_a_colleague_through_the_api(api, scenarios):
    """Scenario 9 through the API: the status "person", the sentence, and a person card with two link fields."""
    client, fakes = api
    turn = scenarios["s09a"]["turns"][0]
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": "en",
        "search_words": [],
        "person_name": "Sophie Martin",
        "person_asks": "manager",
    }
    response = client.post("/ask", json={"question": turn["question"]})

    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "person"
    assert answer["message"] == "Sophie Martin's manager is Hélène Dubois."
    card = answer["person_card"]
    assert card["id"] == turn["expected"]["card"]
    assert card["teams_link"].startswith("https://teams.microsoft.com/l/chat/0/0?users=")
    assert card["email_link"] == f"mailto:{card['email']}"
    # An answer about a colleague has no expert card, and an expert answer has no person card
    assert answer["cards"] == [] and answer["choices"] == []


def test_a_french_answer_keeps_its_accents(api):
    """The JSON of the API is UTF-8: a French text arrives with its accents."""
    client, fakes = api
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "fr", "search_words": []}
    response = client.post("/ask", json={"question": "Quel temps fait-il à Montréal aujourd'hui ?"})

    assert response.status_code == 200
    assert response.json()["message"] == FAILSAFE_TEXTS["not_work"]["fr"]
    assert "é" in response.json()["message"]


# ----------------------------------------------------------------------
# A conversation: the thread_id of an answer, sent back with the next question
# ----------------------------------------------------------------------


def test_the_second_level_through_the_api(api, scenarios):
    """Nothing is about the exact need, and the request names a system: the answer says its level, and its note says why."""
    client, fakes = api
    fakes.understood = {
        "road": "expert",
        "question_type": "help",
        "language": "en",
        "search_words": ["freeze"],
        "named_systems": ["claims_workbench"],
    }
    # Two searches, and verify keeps nothing
    fakes.found = [["pg004"], ["pg014"]]
    response = client.post("/ask", json={"question": "The Claims Workbench freezes at lunch time. Who should I talk to?"})

    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "answered"
    assert answer["level"] == "system"
    assert [card["id"] for card in answer["cards"]] == ["p007", "p024"]
    assert answer["note"].startswith("I found no ticket or page about this exact question.")
    assert "Claims Workbench" in answer["note"]
    # An answer about the exact need says so too, and a refusal has no level
    assert ask_scenario_1(client, fakes, scenarios).json()["level"] == "exact"
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    assert client.post("/ask", json={"question": "What's for lunch?"}).json()["level"] == ""


def test_a_request_with_no_topic_through_the_api(api):
    """ "I need help. Who should I ask?": a normal answer (200), with the text that asks what the user needs."""
    client, fakes = api
    fakes.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": [], "no_topic": True}
    response = client.post("/ask", json={"question": "I need help. Who should I ask?"})

    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "nobody_found"
    assert answer["message"].startswith("What do you need help with?")
    assert answer["cards"] == [] and answer["choices"] == []
    assert len(answer["steps"]) == 2
    assert fakes.searches == []


def ask_the_follow_up(client: TestClient, fakes, scenarios: Dict, thread_id=None):
    """Send "And who's her manager?", with a fake understand that reads it as the real one does."""
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": "en",
        "search_words": [],
        "person_name": "",
        "person_asks": "manager",
    }
    body = {"question": scenarios["s09b"]["turns"][1]["question"]}
    if thread_id:
        body["thread_id"] = thread_id
    return client.post("/ask", json=body)


def test_a_follow_up_with_the_thread_id_knows_who_her_is(api, scenarios):
    """Two requests, one conversation: the second one sends the thread_id of the first answer, and gets her manager."""
    client, fakes = api
    first = ask_scenario_1(client, fakes, scenarios).json()
    second = ask_the_follow_up(client, fakes, scenarios, first["thread_id"]).json()

    # The API makes up the id: 32 letters and digits
    assert len(first["thread_id"]) == 32 and first["thread_id"].isalnum()
    assert second["thread_id"] == first["thread_id"]
    assert second["status"] == "person"
    assert second["person_card"]["id"] == scenarios["s09b"]["turns"][1]["expected"]["card"]


def test_a_follow_up_without_the_thread_id_is_a_new_conversation(api, scenarios):
    """The same follow-up with no thread_id, or with null: a new conversation, where "her" means nobody."""
    client, fakes = api
    first = ask_scenario_1(client, fakes, scenarios).json()
    alone = ask_the_follow_up(client, fakes, scenarios).json()
    with_null = client.post("/ask", json={"question": "And who's her manager?", "thread_id": None}).json()

    for answer in [alone, with_null]:
        assert answer["status"] == "nobody_found"
        assert answer["thread_id"] != first["thread_id"]
    assert alone["thread_id"] != with_null["thread_id"]


@pytest.mark.parametrize(
    "thread_id",
    ["", "two words", "x" * 65, "semi;colon", "accentué", 42],
    ids=["empty", "a space", "too long", "a semicolon", "an accent", "a number"],
)
def test_a_thread_id_that_is_not_an_id_is_refused(api, thread_id):
    """An id is 1 to 64 letters, digits, hyphens, and underscores. Anything else gets a 422, and the agent is not asked."""
    client, fakes = api
    response = client.post("/ask", json={"question": QUESTION, "thread_id": thread_id})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "thread_id"]
    assert fakes.questions == []


# ----------------------------------------------------------------------
# POST /ask/stream: the steps while the agent works, then the answer
# ----------------------------------------------------------------------


def read_lines(response) -> list:
    """The lines of a streamed response, each one read as JSON."""
    return [json.loads(line) for line in response.text.splitlines()]


def test_the_stream_gives_one_line_per_step_then_the_answer(api, scenarios):
    """Scenario 1 through POST /ask/stream: six lines of steps, then one line with the same answer as POST /ask."""
    client, fakes = api
    turn = scenarios["s01"]["turns"][0]
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    response = client.post("/ask/stream", json={"question": turn["question"]})

    assert response.status_code == 200
    # JSON Lines: one JSON object per line
    assert response.headers["content-type"] == "application/jsonl"
    lines = read_lines(response)
    assert [line["type"] for line in lines] == ["step"] * 6 + ["answer"]
    assert all(set(line) == {"type", "text"} and line["text"] for line in lines[:-1])
    assert lines[0]["text"] == "Read your question: you are looking for someone who can help"
    assert lines[4]["text"] == "Removed: 1 person who left the company, 1 person who opted out"

    # The last line is the answer of POST /ask: the same question in the same conversation gives the same one
    answer = lines[-1]["answer"]
    assert answer["status"] == "answered" and len(answer["cards"]) == 3
    assert answer["steps"] == [line["text"] for line in lines[:-1]]
    assert answer == client.post("/ask", json={"question": turn["question"], "thread_id": answer["thread_id"]}).json()


def test_a_french_stream_keeps_its_accents(api):
    """Each line of the stream is UTF-8, like the answer of POST /ask."""
    client, fakes = api
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "fr", "search_words": []}
    response = client.post("/ask/stream", json={"question": "Quel temps fait-il à Montréal aujourd'hui ?"})

    lines = read_lines(response)
    assert [line["type"] for line in lines] == ["step", "step", "answer"]
    assert lines[-1]["answer"]["message"] == FAILSAFE_TEXTS["not_work"]["fr"]


def test_an_error_in_the_middle_of_a_stream_is_its_last_line(api, agent, monkeypatch):
    """A step fails after the stream started: the code 200 is already sent, so the error arrives as the last line."""
    client, fakes = api
    workflow, _ = agent
    fakes.found = [["pg008"]]

    def broken_verify(question: str, items: list) -> Dict:
        raise RuntimeError("the secret detail of the error")

    monkeypatch.setattr(workflow.verifier, "verify", broken_verify)
    response = client.post("/ask/stream", json={"question": QUESTION})

    assert response.status_code == 200
    lines = read_lines(response)
    # The two steps that finished, then one fixed sentence. Nothing of the error's own text, and no answer
    assert [line["type"] for line in lines] == ["step", "step", "error"]
    assert lines[-1] == {"type": "error", "message": main.ERROR_TEXT}
    assert "secret detail" not in response.text


def test_the_stream_checks_the_question_like_ask(api):
    """Both endpoints take the same body: an empty question gets a 422 before any line is sent."""
    client, fakes = api
    response = client.post("/ask/stream", json={"question": "   "})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "question"]
    assert fakes.questions == []


# ----------------------------------------------------------------------
# The pause: the agent asks a question, and the next request answers it
# ----------------------------------------------------------------------


def ask_about_the_api(client: TestClient, fakes, scenarios: Dict, endpoint: str = "/ask"):
    """Send the vague question of scenario 8, with a fake understand that reads it as the real one does."""
    turn = scenarios["s08a"]["turns"][0]
    fakes.understood = {
        "road": "unclear",
        "question_type": "help",
        "language": "en",
        "search_words": ["API"],
        "unclear_systems": turn["expected"]["choices_systems"],
    }
    # Once the user has picked, understand reads the completed question as a plain request for an expert
    fakes.understood_next = [{"road": "expert", "question_type": "help", "language": "en", "search_words": ["Claims API"]}]
    return client.post(endpoint, json={"question": turn["question"]})


def test_the_pause_through_the_api(api, scenarios):
    """Scenario 8 in two requests: the first answer is a question with choices, and the second request picks one."""
    client, fakes = api
    expected = scenarios["s08a"]["turns"][1]["expected"]
    first = ask_about_the_api(client, fakes, scenarios).json()

    assert first["status"] == "needs_details"
    assert [choice["id"] for choice in first["choices"]] == ["claims_api", "policy_api"]
    assert all(choice["name"] and choice["detail"] for choice in first["choices"])

    # The answer: the id of a choice as the question, the id of the conversation, and is_answer
    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    body = {"question": first["choices"][0]["id"], "thread_id": first["thread_id"], "is_answer": True}
    second = client.post("/ask", json=body).json()

    assert second["status"] == "answered"
    assert second["thread_id"] == first["thread_id"]
    assert sorted(card["id"] for card in second["cards"]) == sorted(expected["people"])


def test_the_pause_through_the_stream(api, scenarios):
    """The same two requests through POST /ask/stream: the question arrives as the answer line of the first stream."""
    client, fakes = api
    expected = scenarios["s08a"]["turns"][1]["expected"]
    first = read_lines(ask_about_the_api(client, fakes, scenarios, endpoint="/ask/stream"))

    assert [line["type"] for line in first] == ["step", "answer"]
    question = first[-1]["answer"]
    assert question["status"] == "needs_details" and len(question["choices"]) == 2

    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    body = {"question": "claims_api", "thread_id": question["thread_id"], "is_answer": True}
    second = read_lines(client.post("/ask/stream", json=body))

    assert [line["type"] for line in second] == ["step"] * 7 + ["answer"]
    assert second[0]["text"] == "Noted your answer"
    assert second[-1]["answer"]["status"] == "answered"


def test_what_is_typed_while_the_agent_waits_is_a_new_question(api, scenarios):
    """Without is_answer, a request is always a new question, even when it is the id of a choice."""
    client, fakes = api
    first = ask_about_the_api(client, fakes, scenarios).json()
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    fakes.understood_next = []
    second = client.post("/ask", json={"question": "claims_api", "thread_id": first["thread_id"]}).json()

    # understand read it as a question of its own
    assert fakes.questions[-1] == "claims_api"
    assert second["status"] == "off_topic"


def test_an_answer_that_nothing_waits_for_is_a_normal_answer(api):
    """is_answer in a conversation that asked nothing: a 200 with a fixed text, and the agent runs nothing."""
    client, fakes = api
    response = client.post("/ask", json={"question": "claims_api", "thread_id": "nothing-waits-here", "is_answer": True})

    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "needs_details" and answer["choices"] == []
    assert answer["message"].startswith("I'm no longer waiting")
    assert fakes.questions == []


# ----------------------------------------------------------------------
# The two optional boxes: my name and my team
# ----------------------------------------------------------------------


def test_my_name_and_my_team_fill_the_messages(api, scenarios):
    """Two optional fields of the request fill the first sentence of every suggested message, and its two links."""
    client, fakes = api
    turn = scenarios["s01"]["turns"][0]
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    body = {"question": turn["question"], "user_name": "  Alex ", "user_team": "Pricing"}
    for endpoint in ["/ask", "/ask/stream"]:
        response = client.post(endpoint, json=body)
        answer = response.json() if endpoint == "/ask" else read_lines(response)[-1]["answer"]

        assert len(answer["cards"]) == 3
        for card in answer["cards"]:
            first_name = card["name"].split()[0]
            assert card["message"].startswith(f"Hi {first_name}, I'm Alex from Pricing. ")
            assert "Alex%20from%20Pricing" in card["teams_link"] and "Alex%20from%20Pricing" in card["email_link"]


def test_without_the_two_fields_the_placeholders_stay(api, scenarios):
    """No name and no team, or null: the message keeps [your name] and [your team], as before."""
    client, fakes = api
    for boxes in [{}, {"user_name": None, "user_team": None}, {"user_name": "", "user_team": "  "}]:
        answer = ask_scenario_1(client, fakes, scenarios).json() if not boxes else client.post(
            "/ask", json={"question": scenarios["s01"]["turns"][0]["question"], **boxes}
        ).json()
        assert "I'm [your name] from [your team]." in answer["cards"][0]["message"]


@pytest.mark.parametrize("field", ["user_name", "user_team"])
@pytest.mark.parametrize("value", ["x" * (MAX_USER_TEXT_LENGTH + 1), 42, ["Alex"]], ids=["too long", "a number", "a list"])
def test_a_box_that_is_too_long_or_not_a_text_is_refused(api, field, value):
    """A box holds a short text. Anything else gets a 422, and the agent is not asked."""
    client, fakes = api
    response = client.post("/ask", json={"question": QUESTION, field: value})

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert fakes.questions == []


def test_my_name_and_my_team_go_into_the_messages_and_nowhere_else(api, agent, scenarios, whole_log):
    """The two boxes are for the messages only: no LLM step gets them, the memory does not save them, and no log line has them."""
    client, fakes = api
    workflow, _ = agent
    turn = scenarios["s01"]["turns"][0]
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    body = {"question": turn["question"], "user_name": "Zebulon", "user_team": "Quokka"}
    answer = client.post("/ask", json=body).json()
    lines = read_lines(client.post("/ask/stream", json={**body, "thread_id": answer["thread_id"]}))

    # 1) They are in the messages, and in the two links of each card
    assert all("I'm Zebulon from Quokka." in card["message"] for card in answer["cards"])

    # 2) No LLM step was given them: not understand, not the search, not verify, and not write_cards
    assert fakes.given and fakes.card_people
    assert "Zebulon" not in " ".join(fakes.given) and "Quokka" not in " ".join(fakes.given)

    # 3) The memory did not save them: no state of this conversation holds them, at any step of the two runs
    config = {"configurable": {"thread_id": answer["thread_id"]}}
    saved = json.dumps([snapshot.values for snapshot in workflow.compiled_workflow.get_state_history(config)])
    assert "p012" in saved
    assert "Zebulon" not in saved and "Quokka" not in saved

    # 4) No log line has them, on the screen or in app.log, and no step line either
    assert whole_log
    assert "Zebulon" not in "\n".join(whole_log) and "Quokka" not in "\n".join(whole_log)
    assert "Zebulon" not in json.dumps([line for line in lines if line["type"] == "step"])


# ----------------------------------------------------------------------
# CORS: the page is served from another address, and the API says that this page may call it
# ----------------------------------------------------------------------


@pytest.mark.parametrize("origin", PAGE_ORIGINS)
@pytest.mark.parametrize("endpoint", ["/ask", "/ask/stream"])
def test_the_page_may_call_the_api(api, origin, endpoint):
    """Before a POST with a JSON body, a browser asks the API whether the page may send it: the API says yes."""
    client, fakes = api
    # This first request is the browser's own question (a "preflight"). The page's code never writes it
    asked = {"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    preflight = client.options(endpoint, headers=asked)

    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == origin
    assert "POST" in preflight.headers["access-control-allow-methods"]
    # The real request then gets the same line in its answer, so the browser lets the page read it
    response = client.post(endpoint, json={"question": QUESTION}, headers={"Origin": origin})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_another_page_may_not_call_the_api(api):
    """A page served from any other address gets no such line: its browser will not let it read the answer."""
    client, fakes = api
    elsewhere = "http://localhost:3000"
    asked = {"Origin": elsewhere, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"}
    preflight = client.options("/ask", headers=asked)

    assert preflight.status_code == 400
    assert "access-control-allow-origin" not in preflight.headers
    assert "access-control-allow-origin" not in client.post("/ask", json={"question": QUESTION}, headers={"Origin": elsewhere}).headers


# ----------------------------------------------------------------------
# The question is checked before the agent runs
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"question": ""},
        {"question": "   "},
        {"question": "x" * (MAX_QUESTION_LENGTH + 1)},
        {"question": None},
        {"question": 42},
        {"text": QUESTION},
    ],
    ids=["no question", "empty", "only spaces", "too long", "null", "a number", "another field name"],
)
def test_a_request_without_a_usable_question_is_refused(api, body):
    """A missing, empty, or too long question gets a 422 from FastAPI, and the agent is never asked."""
    client, fakes = api
    response = client.post("/ask", json=body)

    assert response.status_code == 422
    # FastAPI says which field is wrong
    assert response.json()["detail"][0]["loc"] == ["body", "question"]
    assert fakes.questions == []


def test_the_spaces_around_a_question_are_removed(api):
    """The agent gets the question without the spaces and the line breaks around it."""
    client, fakes = api
    response = client.post("/ask", json={"question": f"  {QUESTION} \n"})

    assert response.status_code == 200
    assert fakes.questions == [QUESTION]


def test_the_longest_question_allowed_is_accepted(api):
    """A question of exactly the longest length passes: the limit is the first length that is refused."""
    client, fakes = api
    response = client.post("/ask", json={"question": "x" * MAX_QUESTION_LENGTH})

    assert response.status_code == 200
    assert len(fakes.questions[0]) == MAX_QUESTION_LENGTH


# ----------------------------------------------------------------------
# When something breaks: an HTTP error, never a wrong answer
# ----------------------------------------------------------------------


def test_an_error_of_the_agent_is_a_500_with_a_fixed_text(api, agent, monkeypatch):
    """A step of the agent fails: the caller gets one fixed sentence, and nothing of the error's own text."""
    client, fakes = api
    workflow, _ = agent
    fakes.found = [["pg008"]]

    def broken_verify(question: str, items: list) -> Dict:
        raise RuntimeError("the secret detail of the error")

    monkeypatch.setattr(workflow.verifier, "verify", broken_verify)
    response = client.post("/ask", json={"question": QUESTION})

    assert response.status_code == 500
    assert response.json() == {"detail": main.ERROR_TEXT}
    assert "secret detail" not in response.text


def test_mongodb_stopped_during_a_question_is_an_error(api, monkeypatch):
    """MongoDB does not answer when the HR check asks it: a 500, never cards from memory and never "nobody found"."""
    client, fakes = api
    # pg008 is the access guide of the Claims API: its author would be recommended
    fakes.found = [["pg008"]]
    fakes.relevant = ["pg008"]
    assert client.post("/ask", json={"question": QUESTION}).json()["status"] == "answered"

    # From now on, the two readers of the HR check talk to an address where no MongoDB listens (port 1)
    monkeypatch.setattr(settings, "MONGODB_URI", SecretStr("mongodb://localhost:1"))
    monkeypatch.setattr("sources.mongo_store.MONGODB_TIMEOUT_MS", 300)
    stopped = MongoStore()
    monkeypatch.setattr("sources.people.mongo_store", stopped)
    monkeypatch.setattr("sources.hr.mongo_store", stopped)
    response = client.post("/ask", json={"question": QUESTION})
    stopped.client.close()

    assert response.status_code == 500
    assert response.json() == {"detail": main.ERROR_TEXT}


def test_the_api_does_not_start_when_the_agent_cannot_be_built(monkeypatch):
    """The agent can't be built (for example, MongoDB is stopped): the start-up fails, so the server never runs."""

    def no_agent():
        raise RuntimeError("MongoDB is stopped")

    monkeypatch.setattr(main, "AgentWorkflow", no_agent)
    with pytest.raises(RuntimeError, match="The API did not start"):
        with TestClient(main.app):
            pass


# ----------------------------------------------------------------------
# The agent is built once, and the HR check still follows MongoDB
# ----------------------------------------------------------------------


def test_the_agent_is_built_once_when_the_api_starts(agent, monkeypatch):
    """The agent is built during the start-up, before the first request, and never again."""
    workflow, _ = agent
    built, closed = [], []

    def build():
        built.append("agent")
        return workflow

    monkeypatch.setattr(main, "AgentWorkflow", build)
    monkeypatch.setattr(workflow, "close", lambda: closed.append("agent"))
    with TestClient(main.app) as client:
        assert built == ["agent"]
        client.post("/ask", json={"question": QUESTION})
        client.post("/ask", json={"question": QUESTION})
        assert closed == []
    assert built == ["agent"]
    # The server has stopped: it has closed the agent's connections to Postgres, once, and let go of the agent
    assert closed == ["agent"]
    assert main.shared == {}


def test_someone_who_opts_out_while_the_api_runs_is_removed_at_the_next_question(api, store, monkeypatch, scenarios):
    """The API keeps running, a colleague opts out in MongoDB, and the next answer no longer shows this colleague."""
    client, fakes = api
    # A copy of the directory and of the HR records in the throwaway database, so the test can change them.
    # The two readers of the HR check read them there
    files = SeedFiles().read()
    store.replace_documents("people", files["people"])
    store.replace_documents("hr_records", files["hr_records"])
    monkeypatch.setattr("sources.people.mongo_store", store)
    monkeypatch.setattr("sources.hr.mongo_store", store)

    # 1) The first question: three cards
    first = ask_scenario_1(client, fakes, scenarios).json()
    assert len(first["cards"]) == 3
    gone = first["cards"][-1]

    # 2) The colleague of the last card opts out: one field of one document changes, and nothing is restarted
    store.database["people"].update_one({"id": gone["id"]}, {"$set": {"discoverable": False}})

    # 3) The same question again: this colleague has no card, is counted in the note, and is named nowhere
    second = ask_scenario_1(client, fakes, scenarios).json()
    assert [card["id"] for card in second["cards"]] == [card["id"] for card in first["cards"][:-1]]
    assert second["removed_opted_out"] == first["removed_opted_out"] + 1
    assert "2 people opted out of being found." in second["note"]
    assert gone["name"] not in json.dumps(second, ensure_ascii=False)


# ----------------------------------------------------------------------
# The /docs page
# ----------------------------------------------------------------------


def test_the_docs_page_is_served(api):
    """FastAPI builds the /docs page by itself: it is there, and it reads the description of the API."""
    client, _ = api
    page = client.get("/docs")

    assert page.status_code == 200
    assert "swagger-ui" in page.text
    assert "/openapi.json" in page.text


def test_the_docs_page_proposes_the_question_of_scenario_1(api, scenarios):
    """The description of the API has two endpoints, POST /ask and POST /ask/stream, with the same body.

    The example of the body is the question of scenario 1.
    """
    client, _ = api
    description = client.get("/openapi.json").json()

    assert list(description["paths"]) == ["/ask", "/ask/stream"]
    assert list(description["paths"]["/ask"]) == ["post"]
    assert list(description["paths"]["/ask/stream"]) == ["post"]
    schema = description["components"]["schemas"]["Question"]
    question = schema["properties"]["question"]
    assert question["examples"] == [scenarios["s01"]["turns"][0]["question"]]
    assert question["maxLength"] == MAX_QUESTION_LENGTH
    # The body that "Try it out" proposes is a first question: it has no thread_id, so it starts a new conversation
    assert schema["examples"] == [{"question": scenarios["s01"]["turns"][0]["question"]}]
    # Only the question is required: the id of the conversation, the answer flag, and the two boxes are optional
    assert sorted(schema["properties"]) == ["is_answer", "question", "thread_id", "user_name", "user_team"]
    assert schema["required"] == ["question"]


# ----------------------------------------------------------------------
# The real agent behind the API (paid)
# ----------------------------------------------------------------------


@pytest.mark.openai
def test_the_demo_video_path_through_the_stream(scenarios, monkeypatch, opted_out_names_in):
    """The real agent, asked the six turns of the demo video the way the page asks them: through POST /ask/stream.

    The vague question, the pick of the Claims API, then four follow-ups in the same conversation.
    It calls OpenAI (about half a cent): the start-up builds the real search index, then six requests.
    """
    # The conversation of this test stays in the memory of the program: nothing is written to Postgres
    monkeypatch.setattr(settings, "POSTGRES_URI", None)
    turns = scenarios["demo"]["turns"]
    cards_of_scenario_8 = scenarios["s08a"]["turns"][1]["expected"]
    work_of_scenario_13 = scenarios["s13"]["turns"][0]["expected"]
    answers = []

    with TestClient(main.app) as client:

        def send(body: Dict) -> Dict:
            """One request of the page: every line of the stream is read, and the last one is the answer."""
            if answers:
                body["thread_id"] = answers[0]["thread_id"]
            lines = read_lines(client.post("/ask/stream", json=body))
            # At least one grey line arrives before each answer, and no line is an error
            assert [line["type"] for line in lines[:-1]] == ["step"] * (len(lines) - 1) and len(lines) >= 2
            assert lines[-1]["type"] == "answer"
            answers.append(lines[-1]["answer"])
            return lines[-1]["answer"]

        # 1) The vague question: the agent asks which API
        first = send({"question": turns[0]["question"]})
        assert first["status"] == "needs_details"
        assert sorted(choice["id"] for choice in first["choices"]) == sorted(turns[0]["expected"]["choices_systems"])

        # 2) A click on the Claims API: the id of the choice, sent as an answer
        picked = next(choice["id"] for choice in first["choices"] if choice["name"] in turns[1]["question"])
        cards = send({"question": picked, "is_answer": True})
        # 3) to 6) The four follow-ups, typed in the question box
        manager, work, phone, refusal = [send({"question": turn["question"]}) for turn in turns[2:]]

    # 2) The three cards of the Claims API, the expert first, with the note, and nobody who opted out
    assert cards["status"] == "answered"
    shown = [card["id"] for card in cards["cards"]]
    assert shown[0] == cards_of_scenario_8["people"][0]
    assert sorted(shown) == sorted(cards_of_scenario_8["people"])
    assert cards["removed_left"] == cards_of_scenario_8["removed_left"]
    assert "no longer works at the company" in cards["note"]
    assert opted_out_names_in(cards) == []
    assert cards["cards"][0]["out_of_office_text"] == "Out of office until 10 November 2026"
    for card in cards["cards"]:
        assert card["message"] and card["teams_link"] and card["email_link"].startswith(f"mailto:{card['email']}?subject=")
        assert all(label["text"] and label["date_text"] for label in card["evidence"])

    # 3) "Sophie is away. Who's her manager?": Sophie is the Sophie of the cards, and her manager is not one of them
    expected = turns[2]["expected"]
    assert manager["status"] == "person"
    assert manager["person_card"]["id"] == expected["card"]
    assert manager["message"] == "Sophie Martin's manager is Hélène Dubois."
    assert expected["card"] not in shown

    # 4) "What does she work on?": "she" is now the manager. Her tickets and pages, by system
    assert work["status"] == "person"
    assert work["person_card"]["id"] == work_of_scenario_13["card"]
    assert sorted(item["id"] for group in work["person_card"]["work"] for item in group["items"]) == sorted(
        work_of_scenario_13["work"]
    )
    assert len(work["person_card"]["work"]) >= 2

    # 5) "What's Hélène's work phone?": the fake number of the directory
    assert phone["status"] == "person"
    assert phone["person_card"]["id"] == turns[4]["expected"]["card"]
    assert phone["person_card"]["work_phone"] and phone["person_card"]["work_phone"] in phone["message"]

    # 6) "Why is Sophie away?": the polite "work information only" answer
    assert refusal["status"] == "off_topic" and refusal["reason"] == "personal"
    assert refusal["message"] == FAILSAFE_TEXTS["personal"]["en"]
    # One conversation from start to end
    assert len({answer["thread_id"] for answer in answers}) == 1


@pytest.mark.openai
def test_scenario_1_through_the_api(scenarios, monkeypatch):
    """The real agent, asked through the API: scenario 1 gives the expected people, each with a message and two links.

    Then the follow-up of scenario 9, sent with the thread_id of the first answer: her manager.
    It calls OpenAI (about a quarter of a cent): the start-up builds the real search index, then two questions.
    """
    # The conversation of this test stays in the memory of the program: nothing is written to Postgres
    monkeypatch.setattr(settings, "POSTGRES_URI", None)
    turn = scenarios["s01"]["turns"][0]
    expected = turn["expected"]
    follow_up = scenarios["s09b"]["turns"][1]
    with TestClient(main.app) as client:
        response = client.post("/ask", json={"question": turn["question"]})
        second = client.post("/ask", json={"question": follow_up["question"], "thread_id": response.json()["thread_id"]})

    # The follow-up: the card of the manager of the first person shown
    assert second.status_code == 200
    assert second.json()["status"] == "person"
    assert second.json()["person_card"]["id"] == follow_up["expected"]["card"]

    assert response.status_code == 200
    answer = response.json()
    assert answer["status"] == "answered"
    assert answer["language"] == expected["language"]
    cards = [card["id"] for card in answer["cards"]]
    for person_id in expected["people"]:
        assert person_id in cards
    assert cards[0] == expected["people"][0]
    for person_id in expected["forbidden_people"]:
        assert person_id not in cards
    for card in answer["cards"]:
        assert card["why"] and card["message"]
        assert card["teams_link"].startswith("https://teams.microsoft.com/l/chat/0/0?users=")
        assert card["email_link"].startswith(f"mailto:{card['email']}?subject=")
    assert sorted(answer["removed_left"]) == sorted(expected["removed_left"])
    assert answer["removed_opted_out"] == expected["removed_opted_out"]
