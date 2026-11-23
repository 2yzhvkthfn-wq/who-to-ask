"""Tests of the MCP server: what its two tools give back to a client. They are free (no OpenAI calls), except the
last one, which is marked.

The server is the real one, with its real start-up. In the free tests, a test talks to it with the library's own
client, inside this process: no program is started. The agent behind the server is the real graph with fake LLM
steps (the agent helper of conftest.py): a call still runs the routers, the HR check, and the answer for real.
"""

import inspect
import sys
from contextlib import contextmanager
from typing import Callable, Dict, Iterator, Tuple

import pytest
from anyio.from_thread import start_blocking_portal
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from config.constants import MAX_QUESTION_LENGTH
from config.settings import BACKEND_DIR
from config.texts import ASK_USER_TEXTS, FAILSAFE_TEXTS, NOBODY_FOUND_TEXTS, TOOL_TEXTS
from mcp_server import server
from mcp_server.answer_writer import AnswerWriter
from sources import PeopleSource

# A question for the tests where the fakes decide the answer, so the words of the question don't matter
QUESTION = "Who can help me order a laptop?"


# MCP has two generations, and a client opens its connection in one of two ways. The apps of before 2026 start with
# a "handshake" (the library calls this way "legacy"), and the version of the protocol of July 2026 has none
# ("auto" is the library's own choice: the new way when the server knows it). The server must answer both the same
# way, so the tests below run once with each kind of client
CLIENT_MODES = ["auto", "legacy"]
CLIENT_NAMES = ["a client of 2026", "a client that starts with a handshake"]


@contextmanager
def connected_to(target, mode: str = "auto") -> Iterator[Callable]:
    """Connect the library's client to an MCP server, and give a function that uses this client from plain code.

    target is the server itself (the client then talks to it inside this process), or the library's stdio_client,
    which starts the server as a program of its own. mode is how the client opens the connection (see above).
    The library's Client only exists in async form: its methods must be awaited. A "blocking portal" runs it
    in a second thread, and lets plain code call a method and wait for its result, so the tests stay plain
    functions. FastAPI's TestClient does the same for the API.
    Connecting starts the server, and leaving the "with" block stops it.
    """
    with start_blocking_portal() as portal:
        with portal.wrap_async_context_manager(Client(target, mode=mode)) as client:

            def use(method: str, *arguments):
                """Call one method of the client ("call_tool" or "list_tools"), and wait for the server's answer."""
                return portal.call(getattr(client, method), *arguments)

            yield use


@pytest.fixture(params=CLIENT_MODES, ids=CLIENT_NAMES)
def connection(request, agent, monkeypatch) -> Iterator[Tuple[Callable, object]]:
    """A client connected to the MCP server, and the fakes of the agent behind it. Once for each kind of client.

    The start-up of the server builds the agent: here it gets the agent with fake LLM steps.
    """
    workflow, fakes = agent
    monkeypatch.setattr(server, "AgentWorkflow", lambda: workflow)
    with connected_to(server.mcp, request.param) as use:
        yield use, fakes


@pytest.fixture(scope="module")
def people() -> Dict:
    """The directory, by person id."""
    return {person["id"]: person for person in PeopleSource().list_people()}


def ask(use: Callable, question: str, thread_id: str = None):
    """Call the tool ask, with a question and, for a follow-up, the id of its conversation."""
    arguments = {"question": question}
    if thread_id is not None:
        arguments["thread_id"] = thread_id
    return use("call_tool", "ask", arguments)


def pick(use: Callable, thread_id: str, choice_id: str):
    """Call the tool pick_choice: the answer to a question of the agent."""
    return use("call_tool", "pick_choice", {"thread_id": thread_id, "choice_id": choice_id})


def text_of(result) -> str:
    """The text that a tool gave back. A result is one block of text, and it sends no data next to it."""
    assert len(result.content) == 1 and result.content[0].type == "text"
    assert result.structured_content is None
    return result.content[0].text


def answer_of(result) -> str:
    """The text of a call that worked."""
    assert not result.is_error
    return text_of(result)


def thread_of(text: str) -> str:
    """The id of the conversation: the last line of every answer."""
    last_line = text.splitlines()[-1]
    assert last_line.startswith("thread_id: ")
    return last_line.removeprefix("thread_id: ")


def card_lines_of(text: str) -> list:
    """The first line of each expert card: its number, then the name, the job title, and the team."""
    return [line for line in text.splitlines() if line[:3] in ("1. ", "2. ", "3. ")]


def choices_of(text: str) -> Dict:
    """The choices of a question of the agent, as an assistant reads them: the id to send back, by the name of the choice."""
    choices = {}
    for line in text.splitlines():
        # "- Claims API (choice_id: claims_api): what the system does"
        if line.startswith("- "):
            name, rest = line[2:].split(" (choice_id: ")
            choices[name] = rest.split(")")[0]
    return choices


def ask_scenario_1(use: Callable, fakes, scenarios: Dict, thread_id: str = None):
    """Ask the question of scenario 1, with fakes that find and keep the evidence the scenario lists."""
    turn = scenarios["s01"]["turns"][0]
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    return ask(use, turn["question"], thread_id)


def ask_about_her_manager(use: Callable, fakes, scenarios: Dict, thread_id: str = None):
    """Ask "And who's her manager?", with a fake understand that reads it as the real one does."""
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": "en",
        "search_words": [],
        "person_name": "",
        "person_asks": "manager",
    }
    return ask(use, scenarios["s09b"]["turns"][1]["question"], thread_id)


def ask_about_the_api(use: Callable, fakes, scenarios: Dict):
    """Ask the vague question of scenario 8, with a fake understand that reads it as the real one does."""
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
    return ask(use, turn["question"])


def ask_about_sophie(use: Callable, fakes, question: str, asks: str = "card"):
    """Ask a question about "Sophie", a first name that two people have."""
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": "en",
        "search_words": [],
        "person_name": "Sophie",
        "person_asks": asks,
    }
    return ask(use, question)


# ----------------------------------------------------------------------
# What a client sees of the server: two tools, each with a description
# ----------------------------------------------------------------------


def test_a_client_sees_two_tools_with_their_arguments(connection):
    """The server offers ask and pick_choice. An assistant reads their arguments, and which ones are required."""
    use, _ = connection
    tools = {tool.name: tool for tool in use("list_tools").tools}

    assert list(tools) == ["ask", "pick_choice"]
    ask_arguments = tools["ask"].input_schema
    assert sorted(ask_arguments["properties"]) == ["question", "thread_id"]
    assert ask_arguments["required"] == ["question"]
    assert ask_arguments["properties"]["question"]["minLength"] == 1
    assert ask_arguments["properties"]["question"]["maxLength"] == MAX_QUESTION_LENGTH
    pick_arguments = tools["pick_choice"].input_schema
    assert sorted(pick_arguments["properties"]) == ["choice_id", "thread_id"]
    assert sorted(pick_arguments["required"]) == ["choice_id", "thread_id"]
    for arguments in [ask_arguments, pick_arguments]:
        # Every argument says what it is. And none of them is my name or my team: the tools don't take them
        assert all(argument["description"] for argument in arguments["properties"].values())
    # A tool gives back a text, and promises no data of a fixed shape
    assert tools["ask"].output_schema is None and tools["pick_choice"].output_schema is None


def test_the_description_of_a_tool_is_its_docstring(connection):
    """What an assistant reads about a tool is the docstring of its function, without the indentation of the code."""
    use, _ = connection
    tools = {tool.name: tool for tool in use("list_tools").tools}

    for name, tool in tools.items():
        assert tool.description == inspect.getdoc(getattr(server, name))
        # No line starts with the four spaces that a docstring has in the code, and nothing follows the last line
        assert not any(line.startswith("    ") for line in tool.description.splitlines())
        assert tool.description == tool.description.strip()
    # What an assistant has to know before it calls ask: the data is fake, the agent sends nothing, the question
    # goes as the user wrote it, the id comes back with a follow-up, and a question with choices goes to pick_choice
    for words in ["fictional company", "never sends anything", "as they wrote it", "thread_id", "pick_choice"]:
        assert words in tools["ask"].description
    assert "do not pick for them" in tools["pick_choice"].description


def test_the_server_says_what_it_is():
    """The name of the server, and the few sentences that a client gets about it when it connects."""
    assert server.mcp.name == "who-to-ask"
    assert server.mcp.instructions == server.INSTRUCTIONS
    assert "fictional company" in server.INSTRUCTIONS and "never sends anything" in server.INSTRUCTIONS
    # The library's own logging only shows warnings: at its usual level, every call to OpenAI would write a line
    assert server.mcp.settings.log_level == "WARNING"


# ----------------------------------------------------------------------
# An answer: the answer of the agent, written as text
# ----------------------------------------------------------------------


def test_scenario_1_through_mcp_with_fake_llm_steps(connection, scenarios, people, opted_out_names_in):
    """The question of scenario 1 comes back as text: three cards, the expert first, each with a suggested message."""
    use, fakes = connection
    expected = scenarios["s01"]["turns"][0]["expected"]
    text = answer_of(ask_scenario_1(use, fakes, scenarios))

    # The three expected people, each on the first line of a card, and the expert on the first card
    names = [people[person_id]["name"] for person_id in expected["people"]]
    card_lines = card_lines_of(text)
    assert sorted(line[3:].split(",")[0] for line in card_lines) == sorted(names)
    assert card_lines[0].startswith(f"1. {names[0]},")
    for label in ["   Email: ", "   Why: ", "   Evidence:", "   Suggested message: ", "   Email subject: "]:
        assert sum(line.startswith(label) for line in text.splitlines()) == 3

    # The note: one person who left is named, and one person who opted out is only counted
    assert f"{people[expected['removed_left'][0]]['name']} wrote" in text
    assert "no longer works at the company" in text
    assert "1 person opted out of being found." in text
    assert opted_out_names_in({"text": text}) == []
    # Nobody who must not be recommended has a card
    for person_id in expected["forbidden_people"]:
        assert people[person_id]["name"] not in "\n".join(card_lines)
    # An assistant gets no link: the email address and the message are enough to write to someone
    assert "https://" not in text and "mailto:" not in text


def test_a_tool_gives_back_the_answer_of_the_agent_as_text(connection, agent, scenarios):
    """What comes out of a tool is what full_pipeline returns, written by AnswerWriter. Nothing is added or changed."""
    use, fakes = connection
    workflow, _ = agent
    text = answer_of(ask_scenario_1(use, fakes, scenarios))

    # The same question, asked to the agent directly in the same conversation, gives the same answer
    answer = workflow.full_pipeline(scenarios["s01"]["turns"][0]["question"], thread_of(text))
    assert text == AnswerWriter().write(answer)


def test_a_refusal_is_a_normal_answer(connection):
    """A question that is not about work: the call works, and its text is the polite refusal."""
    use, fakes = connection
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    text = answer_of(ask(use, "What should I cook tonight?"))

    assert text.split("\n\n")[0] == FAILSAFE_TEXTS["not_work"]["en"]


def test_nobody_found_is_a_normal_answer(connection):
    """Nothing holds up: the call works, and its text says honestly that nobody was found. It is not an error."""
    use, fakes = connection
    # pg004 is the guide of another system, and the fake verify keeps nothing
    fakes.found = [["pg004"]]
    text = answer_of(ask(use, QUESTION))

    assert text.split("\n\n")[0] == NOBODY_FOUND_TEXTS["general"]["en"]
    assert card_lines_of(text) == []


def test_a_question_about_a_colleague_through_mcp(connection, scenarios, people):
    """Scenario 9 through MCP: the sentence that names both people, then the card of the manager."""
    use, fakes = connection
    turn = scenarios["s09a"]["turns"][0]
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": "en",
        "search_words": [],
        "person_name": "Sophie Martin",
        "person_asks": "manager",
    }
    lines = answer_of(ask(use, turn["question"])).splitlines()

    manager = people[turn["expected"]["card"]]
    assert lines[0] == f"Sophie Martin's manager is {manager['name']}."
    assert sum(line.startswith(f"{manager['name']}, {manager['job_title']}, ") for line in lines) == 1
    assert f"   Email: {manager['email']}" in lines


def test_a_french_answer_keeps_its_accents(connection):
    """A French question gets the French text, with its accents."""
    use, fakes = connection
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "fr", "search_words": []}
    text = answer_of(ask(use, "Quel temps fait-il à Montréal aujourd'hui ?"))

    assert text.split("\n\n")[0] == FAILSAFE_TEXTS["not_work"]["fr"]
    assert "é" in text
    # understand got the question as it was sent, with its accents
    assert fakes.questions == ["Quel temps fait-il à Montréal aujourd'hui ?"]


# ----------------------------------------------------------------------
# A conversation: the thread_id of an answer, sent back with the next question
# ----------------------------------------------------------------------


def test_a_follow_up_with_the_thread_id_knows_who_her_is(connection, scenarios, people):
    """Two calls, one conversation: the second one sends the thread_id of the first answer, and gets her manager."""
    use, fakes = connection
    first = answer_of(ask_scenario_1(use, fakes, scenarios))
    second = answer_of(ask_about_her_manager(use, fakes, scenarios, thread_of(first)))

    # The agent makes up the id: 32 letters and digits. The follow-up stays in the same conversation
    assert len(thread_of(first)) == 32 and thread_of(first).isalnum()
    assert thread_of(second) == thread_of(first)
    manager = people[scenarios["s09b"]["turns"][1]["expected"]["card"]]
    assert second.splitlines()[0] == f"Sophie Martin's manager is {manager['name']}."


@pytest.mark.parametrize("thread_id", [None, ""], ids=["no id", "an empty id"])
def test_a_follow_up_without_the_thread_id_is_a_new_conversation(connection, scenarios, thread_id):
    """The same follow-up with no thread_id, or with an empty one: a new conversation, where "her" means nobody."""
    use, fakes = connection
    first = answer_of(ask_scenario_1(use, fakes, scenarios))
    alone = answer_of(ask_about_her_manager(use, fakes, scenarios, thread_id))

    assert alone.split("\n\n")[0] == NOBODY_FOUND_TEXTS["no_one_meant"]["en"]
    assert thread_of(alone) != thread_of(first)


# ----------------------------------------------------------------------
# The pause: the agent asks a question, and the next call answers it
# ----------------------------------------------------------------------


def test_the_pause_through_mcp(connection, scenarios, people):
    """Scenario 8 in two calls: ask gives back a question with choices, and pick_choice sends the pick."""
    use, fakes = connection
    expected = scenarios["s08a"]["turns"][1]["expected"]
    first = answer_of(ask_about_the_api(use, fakes, scenarios))

    # The text tells the assistant to ask the user, shows each choice with its id, and names the tool to call
    assert first.startswith(f"{TOOL_TEXTS['ask_the_user']}\n\n{ASK_USER_TEXTS['system']['en']}\n\n")
    assert choices_of(first) == {"Claims API": "claims_api", "Policy API": "policy_api"}
    assert TOOL_TEXTS["how_to_pick"] in first
    # Nothing was searched yet: the agent waits for the pick
    assert fakes.searches == []

    # The pick: the id of the conversation, and the id of a choice. The same run goes on to the cards
    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    second = answer_of(pick(use, thread_of(first), "claims_api"))

    assert thread_of(second) == thread_of(first)
    names = [people[person_id]["name"] for person_id in expected["people"]]
    assert sorted(line[3:].split(",")[0] for line in card_lines_of(second)) == sorted(names)
    # understand read the question, then the question completed with the system that was picked
    question = scenarios["s08a"]["turns"][0]["question"]
    assert fakes.questions == [question, f"{question} I mean: Claims API."]


def test_picking_a_person_through_mcp(connection, people):
    """Scenario 12: "Who is Sophie's manager?", then the pick of one Sophie, gives the manager of that Sophie."""
    use, fakes = connection
    first = answer_of(ask_about_sophie(use, fakes, "Who is Sophie's manager?", asks="manager"))

    assert ASK_USER_TEXTS["person"]["en"] in first
    choices = choices_of(first)
    assert list(choices) == ["Sophie Martin", "Sophie Nguyen"]

    second = answer_of(pick(use, thread_of(first), choices["Sophie Nguyen"]))
    nguyen = people[choices["Sophie Nguyen"]]
    assert second.splitlines()[0] == f"Sophie Nguyen's manager is {people[nguyen['manager']]['name']}."


def test_a_pick_that_is_not_a_choice_gets_the_same_question_again(connection, scenarios):
    """pick_choice with an id that the agent did not offer: nothing runs, and the question comes back with its choices."""
    use, fakes = connection
    first = answer_of(ask_about_the_api(use, fakes, scenarios))
    again = answer_of(pick(use, thread_of(first), "billing_api"))

    assert again == first
    # understand was not asked a second time, and nothing was searched
    assert len(fakes.questions) == 1 and fakes.searches == []


def test_a_pick_that_nothing_waits_for_is_a_normal_answer(connection):
    """pick_choice in a conversation that asked nothing: a fixed text, no choice to pick, and the agent runs nothing."""
    use, fakes = connection
    text = answer_of(pick(use, "nothing-waits-here", "claims_api"))

    assert text == f"{ASK_USER_TEXTS['not_waiting']['en']}\n\nthread_id: nothing-waits-here"
    assert fakes.questions == []


def test_what_ask_sends_while_the_agent_waits_is_a_new_question(connection, scenarios):
    """ask is always a new question, even when it sends the id of a choice: only pick_choice answers the agent."""
    use, fakes = connection
    first = answer_of(ask_about_the_api(use, fakes, scenarios))
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    fakes.understood_next = []
    second = answer_of(ask(use, "claims_api", thread_of(first)))

    # understand read it as a question of its own
    assert fakes.questions[-1] == "claims_api"
    assert second.split("\n\n")[0] == FAILSAFE_TEXTS["not_work"]["en"]


# ----------------------------------------------------------------------
# The arguments are checked before the agent runs
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool, arguments, wrong",
    [
        ("ask", {}, "question"),
        ("ask", {"question": ""}, "question"),
        ("ask", {"question": "   "}, "question"),
        ("ask", {"question": "x" * (MAX_QUESTION_LENGTH + 1)}, "question"),
        ("ask", {"question": None}, "question"),
        ("ask", {"question": 42}, "question"),
        ("ask", {"text": QUESTION}, "question"),
        ("ask", {"question": QUESTION, "thread_id": "two words"}, "thread_id"),
        ("ask", {"question": QUESTION, "thread_id": "x" * 65}, "thread_id"),
        ("ask", {"question": QUESTION, "thread_id": "semi;colon"}, "thread_id"),
        ("ask", {"question": QUESTION, "thread_id": "accentué"}, "thread_id"),
        ("ask", {"question": QUESTION, "thread_id": 42}, "thread_id"),
        ("pick_choice", {"choice_id": "claims_api"}, "thread_id"),
        ("pick_choice", {"thread_id": "", "choice_id": "claims_api"}, "thread_id"),
        ("pick_choice", {"thread_id": "abc"}, "choice_id"),
        ("pick_choice", {"thread_id": "abc", "choice_id": ""}, "choice_id"),
        ("pick_choice", {"thread_id": "abc", "choice_id": "Claims API"}, "choice_id"),
        ("pick_choice", {"thread_id": "abc", "choice_id": "x" * 65}, "choice_id"),
    ],
    ids=[
        "no question", "empty", "only spaces", "too long", "null", "a number", "another argument name",
        "thread: a space", "thread: too long", "thread: a semicolon", "thread: an accent", "thread: a number",
        "pick: no thread", "pick: an empty thread", "pick: no choice", "pick: an empty choice",
        "pick: a name, not an id", "pick: too long",
    ],
)  # fmt: skip
def test_a_call_with_a_bad_argument_is_refused(connection, tool, arguments, wrong):
    """A missing, empty, or too long argument: the result is an error that names the argument, and the agent is never asked."""
    use, fakes = connection
    result = use("call_tool", tool, arguments)

    assert result.is_error
    # The error says which tool and which argument, so an assistant can correct its call
    assert text_of(result).startswith(f"Error executing tool {tool}: 1 validation error")
    assert f"\n{wrong}\n" in text_of(result)
    assert fakes.questions == []


def test_the_spaces_around_a_question_are_removed(connection):
    """The agent gets the question without the spaces and the line breaks around it."""
    use, fakes = connection
    answer_of(ask(use, f"  {QUESTION} \n"))

    assert fakes.questions == [QUESTION]


def test_the_longest_question_allowed_is_accepted(connection):
    """A question of exactly the longest length passes: the limit is the first length that is refused."""
    use, fakes = connection
    answer_of(ask(use, "x" * MAX_QUESTION_LENGTH))

    assert len(fakes.questions[0]) == MAX_QUESTION_LENGTH


# ----------------------------------------------------------------------
# When something breaks: an error with a fixed text, never a wrong answer
# ----------------------------------------------------------------------


def test_an_error_of_the_agent_is_an_error_with_a_fixed_text(connection, agent, monkeypatch, screen_log):
    """A step of the agent fails: the assistant gets one fixed sentence, marked as an error, and nothing of the error's own text."""
    use, fakes = connection
    workflow, _ = agent
    fakes.found = [["pg008"]]

    def broken_verify(question: str, items: list) -> Dict:
        raise RuntimeError("the secret detail of the error")

    monkeypatch.setattr(workflow.verifier, "verify", broken_verify)
    result = ask(use, QUESTION)

    assert result.is_error
    assert text_of(result) == f"Error executing tool ask: {server.ERROR_TEXT}"
    assert "secret detail" not in text_of(result)
    # The detail is in the log, where the fixed text says to look
    assert any("The agent could not answer: the secret detail of the error" in line for line in screen_log)


def test_a_failed_call_does_not_stop_the_server(connection, agent, monkeypatch):
    """After a call that failed, the next call is answered normally, by the same server."""
    use, fakes = connection
    workflow, _ = agent
    fakes.found = [["pg008"]]
    fakes.relevant = ["pg008"]
    verify = workflow.verifier.verify

    def broken_verify(question: str, items: list) -> Dict:
        raise RuntimeError("the secret detail of the error")

    monkeypatch.setattr(workflow.verifier, "verify", broken_verify)
    assert ask(use, QUESTION).is_error
    monkeypatch.setattr(workflow.verifier, "verify", verify)

    # pg008 is the access guide of the Claims API: its author gets the first card
    assert len(card_lines_of(answer_of(ask(use, QUESTION)))) == 1


def test_an_unknown_tool_is_an_error(connection):
    """A client that calls a tool the server does not have gets an error, and the agent is never asked."""
    use, fakes = connection
    result = use("call_tool", "send_message", {"to": "p012"})

    assert result.is_error and "Unknown tool" in text_of(result)
    assert fakes.questions == []


# ----------------------------------------------------------------------
# The server starts once, and stops once
# ----------------------------------------------------------------------


@pytest.mark.parametrize("mode", CLIENT_MODES, ids=CLIENT_NAMES)
def test_the_agent_is_built_once_when_the_server_starts(agent, monkeypatch, mode):
    """The agent is built during the start-up, before the first call, and it is closed when the server stops."""
    workflow, _ = agent
    built, closed = [], []

    def build():
        built.append("agent")
        return workflow

    monkeypatch.setattr(server, "AgentWorkflow", build)
    monkeypatch.setattr(workflow, "close", lambda: closed.append("agent"))
    with connected_to(server.mcp, mode) as use:
        assert built == ["agent"]
        answer_of(ask(use, QUESTION))
        answer_of(ask(use, QUESTION))
        assert closed == []
    assert built == ["agent"]
    # The server has stopped: it has closed the agent's connections to Postgres, once, and let go of the agent
    assert closed == ["agent"]
    assert server.shared == {}


@pytest.mark.parametrize("mode", CLIENT_MODES, ids=CLIENT_NAMES)
def test_the_server_does_not_start_when_the_agent_cannot_be_built(monkeypatch, screen_log, mode):
    """The agent can't be built (for example, MongoDB is stopped): the start-up fails, so no client can connect."""

    def no_agent():
        raise RuntimeError("MongoDB is stopped")

    monkeypatch.setattr(server, "AgentWorkflow", no_agent)
    with pytest.raises(Exception) as stop:
        with connected_to(server.mcp, mode):
            pass

    # The library runs a server in a group of tasks, so its error can arrive inside a group of errors
    error = stop.value
    while isinstance(error, BaseExceptionGroup) and error.exceptions:
        error = error.exceptions[0]
    # The reason is in the log, and the error itself only says where to look
    assert isinstance(error, RuntimeError) and str(error) == "the agent could not be built. The lines above say why"
    assert any("The agent could not be built: MongoDB is stopped" in line for line in screen_log)
    assert server.shared == {}


def test_the_program_talks_over_stdio(monkeypatch):
    """python -m mcp_server.server: main() runs the server with no argument, which is stdio, the usual way for a local tool."""
    runs = []
    monkeypatch.setattr(server.mcp, "run", lambda *arguments, **options: runs.append((arguments, options)))

    server.main()
    assert runs == [((), {})]


def test_a_program_that_cannot_start_ends_with_one_clear_line(monkeypatch, screen_log):
    """The server could not start: the program logs the real reason on one line, and its exit code says that it failed."""

    def no_start():
        # What the library raises when the start-up fails: the error, inside a group of errors
        raise ExceptionGroup("unhandled errors in a TaskGroup", [RuntimeError("the agent could not be built")])

    monkeypatch.setattr(server.mcp, "run", no_start)
    with pytest.raises(SystemExit) as stop:
        server.main()

    assert stop.value.code == 1
    assert screen_log[-1].strip() == "The MCP server stopped: the agent could not be built"


def test_ctrl_c_stops_the_program_without_a_trace(monkeypatch, screen_log):
    """The program was started by hand, and stopped with Ctrl+C: one line in the log, and no error."""

    def interrupted():
        raise KeyboardInterrupt

    monkeypatch.setattr(server.mcp, "run", interrupted)

    # main() returns normally: no exception leaves it, so Python prints no trace
    server.main()
    assert screen_log[-1].strip() == "MCP server stopped (Ctrl+C)"


# ----------------------------------------------------------------------
# The real server, started as a program of its own (paid)
# ----------------------------------------------------------------------


@pytest.mark.openai
@pytest.mark.parametrize("mode", CLIENT_MODES, ids=CLIENT_NAMES)
def test_the_real_server_as_a_program_of_its_own(scenarios, people, tmp_path, opted_out_names_in, mode):
    """The real server with the real agent, started the way a real client starts it, and spoken to over stdio.

    Scenario 1, the follow-up of scenario 9 with the thread_id of the first answer, and one French question.
    It calls OpenAI (about a quarter of a cent for each kind of client): the start-up builds the real search index,
    then three questions.
    """
    turn = scenarios["s01"]["turns"][0]
    expected = turn["expected"]
    follow_up = scenarios["s09b"]["turns"][1]
    program = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        # A client starts the server from its own folder, not from the project's: here, a folder of this test.
        # PYTHONPATH tells Python where the code is: the backend folder
        cwd=str(tmp_path),
        env={
            "PYTHONPATH": str(BACKEND_DIR),
            # A variable of the program wins over the same line of my settings file. A space switches Postgres
            # and LangSmith off for this program: its conversations stay in its own memory, and nothing is traced
            "POSTGRES_URI": " ",
            "LANGSMITH_API_KEY": " ",
            "LANGSMITH_TRACING": "false",
        },
    )

    # The program writes its log on its error output, and the client decides where that goes: here, into a file
    log_path = tmp_path / "server_log.txt"
    with open(log_path, "w", encoding="utf-8") as log_file:
        with connected_to(stdio_client(program, errlog=log_file), mode) as use:
            tools = [tool.name for tool in use("list_tools").tools]

            # Before the first question: the log of the start-up must say that this program uses no real store.
            # Otherwise the questions below would be saved in my real Postgres, or traced in my LangSmith account
            started = log_path.read_text(encoding="utf-8", errors="replace")
            assert "MCP server ready" in started
            assert "Memory: in this program only" in started
            assert "LangSmith tracing: off" in started

            first = answer_of(ask(use, turn["question"]))
            second = answer_of(ask(use, follow_up["question"], thread_of(first)))
            french = answer_of(ask(use, "Quel temps fait-il à Montréal aujourd'hui ?"))

    assert tools == ["ask", "pick_choice"]
    # Scenario 1: the expected people have a card, the expert first, each with a message
    card_lines = card_lines_of(first)
    for person_id in expected["people"]:
        assert sum(people[person_id]["name"] in line for line in card_lines) == 1
    assert card_lines[0].startswith(f"1. {people[expected['people'][0]]['name']},")
    for person_id in expected["forbidden_people"]:
        assert people[person_id]["name"] not in "\n".join(card_lines)
    assert first.count("   Suggested message: ") == len(card_lines)
    # The note names the colleague who left, and nobody who opted out is anywhere in the text
    assert f"{people[expected['removed_left'][0]]['name']} wrote" in first
    assert "1 person opted out of being found." in first
    assert opted_out_names_in({"text": first}) == []

    # The follow-up: her manager, in the same conversation
    manager = people[follow_up["expected"]["card"]]
    assert second.splitlines()[0] == f"Sophie Martin's manager is {manager['name']}."
    assert thread_of(second) == thread_of(first)

    # The French question is refused in French: the accents crossed the two pipes of the program in both directions
    assert french.split("\n\n")[0] == FAILSAFE_TEXTS["not_work"]["fr"]
