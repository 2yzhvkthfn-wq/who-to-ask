"""Shared helpers for the tests. pytest reads this file by itself: a test gets a helper by naming it as an argument."""

import json
import unicodedata
from typing import Callable, Dict, Iterator, List, Tuple
from urllib.parse import unquote

import pytest

from agents import AgentWorkflow
from agents.answer_builder import AnswerBuilder
from agents.evidence_searcher import EvidenceSearcher
from agents.hr_checker import HrChecker
from agents.ranker import Ranker
from checks import DatabaseChecker
from config.settings import PROJECT_ROOT, settings
from sources import EvidenceSource, MongoStore, PeopleSource
from utils.logging import logger

# The throwaway database of the tests that write to MongoDB. The real database is only written by the seed script
TEST_DATABASE = "who_to_ask_test"


@pytest.fixture(scope="session", autouse=True)
def database_ready() -> None:
    """Before the first test: MongoDB must answer, and hold exactly what the files of the data folder hold.

    The tests read the company data from MongoDB. If it is stopped or out of date, pytest stops at once with one
    message that says what to do, instead of failing test after test. autouse: no test has to ask for this check.
    """
    problems = DatabaseChecker().check()["problems"]
    if problems:
        pytest.exit("\n".join(problems), returncode=1)


@pytest.fixture
def store(monkeypatch):
    """A MongoStore on the throwaway database, for a test that writes to MongoDB. The database is dropped at the end."""
    # The real database must never be the one that is dropped
    assert settings.MONGODB_DATABASE != TEST_DATABASE
    monkeypatch.setattr(settings, "MONGODB_DATABASE", TEST_DATABASE)
    store = MongoStore()
    assert store.database.name == TEST_DATABASE
    yield store
    store.client.drop_database(TEST_DATABASE)
    store.client.close()


@pytest.fixture
def screen_log() -> Iterator[List[str]]:
    """The log lines that the screen shows (INFO and above), collected for one test.

    app.log also gets the DEBUG lines, which is where the words that a user typed may go. A test uses this helper
    to check that a line of the screen holds ids and numbers, and never a name.
    """
    lines: List[str] = []
    handler = logger.add(lambda message: lines.append(str(message)), level="INFO", format="{message}")
    yield lines
    logger.remove(handler)


@pytest.fixture
def whole_log() -> Iterator[List[str]]:
    """Every log line of one test, the DEBUG lines too: all that goes to the screen and to app.log.

    A test uses this helper to check that something never reaches the log at all, in either place.
    """
    lines: List[str] = []
    handler = logger.add(lambda message: lines.append(str(message)), level="DEBUG", format="{message}")
    yield lines
    logger.remove(handler)


class Fakes:
    """What the fake LLM steps answer, and what they were asked. A test fills it in before it runs the graph."""

    def __init__(self):
        # What understand answers. A test of the person road adds "person_name" and "person_asks",
        # a test of the pause adds "unclear_systems", and a test of the second level adds "named_systems"
        self.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": ["laptop"]}
        # What understand answers at its next calls, one entry per call: a test of the pause says here what
        # understand reads once the user has picked a choice. When the list is empty, understood stays as it is
        self.understood_next: List[Dict] = []
        # What each search returns: one list of ids per call. The last list is used again if there are more calls
        self.found: List[List[str]] = [[]]
        # The tickets and pages that verify keeps
        self.relevant: List[str] = []
        # What rewrite answers
        self.new_words = ["computer"]
        # What write_cards answers for every person: the three texts the LLM would write
        self.card_text = {
            "why": "wrote the guide",
            "message": "I need a laptop. Could you help me?",
            "subject": "Help to order a laptop",
        }
        # What the fakes were asked
        self.questions: List[str] = []
        self.searches: List[Dict] = []
        self.verified: List[List[str]] = []
        self.rewrites = 0
        self.card_people: List[str] = []
        # The level that write_cards was given at each call: "exact", or "system" for the second level
        self.card_levels: List[str] = []
        # The question that each fake step was given, by the name of its node: after the user's pick,
        # every step must read the completed question
        self.requests: Dict[str, List[str]] = {"search": [], "verify": [], "rewrite": [], "write_cards": []}
        # Everything the fakes were given, as text: all that a real LLM step could have sent to OpenAI
        self.given: List[str] = []


@pytest.fixture
def build_agent(monkeypatch) -> Iterator[Callable[..., Tuple[AgentWorkflow, Fakes]]]:
    """A function that builds the real graph with fake LLM steps. It returns the workflow and its fakes.

    Fakes stand in for the steps that call OpenAI (understand, search, verify, rewrite, and write_cards).
    The plain-code steps (rank, check_hr, find_person, person_card, nobody_found) and the answer run for real,
    on the real data. Most tests take the agent helper below, which calls this function once.
    A test calls it itself when it needs two agents (the app before and after a restart), or the memory in Postgres.
    """
    # What the setting says before any test changes it
    postgres_uri = settings.POSTGRES_URI
    built: List[AgentWorkflow] = []

    def build(postgres: bool = False) -> Tuple[AgentWorkflow, Fakes]:
        # Nothing may call the internet: no tracing, and no search index (building it embeds every text)
        monkeypatch.setattr(settings, "LANGSMITH_API_KEY", None)
        monkeypatch.setenv("LANGSMITH_TRACING", "false")
        monkeypatch.setattr(EvidenceSearcher, "__init__", lambda self, items: None)
        # The conversations of the tests stay in the memory of the program: nothing is written to Postgres.
        # Only the tests of test_memory.py that ask for it use the real Postgres, and they delete what they wrote
        monkeypatch.setattr(settings, "POSTGRES_URI", postgres_uri if postgres else None)
        workflow = AgentWorkflow()
        built.append(workflow)
        fakes = Fakes()

        def given(*values) -> None:
            fakes.given.append(json.dumps(values, ensure_ascii=False))

        def read(question: str) -> Dict:
            fakes.questions.append(question)
            given(question)
            # A test that says nothing about a person or about a general word gets what understand answers
            # for every other road
            understood = {
                "person_name": "",
                "person_asks": "card",
                "unclear_systems": [],
                "named_systems": [],
                "no_topic": False,
                **fakes.understood,
            }
            # The next call of understand answers the next entry, when a test prepared one
            if fakes.understood_next:
                fakes.understood = fakes.understood_next.pop(0)
            return understood

        def search(question: str, search_words: List[str], question_type: str, retry: bool = False) -> List[str]:
            fakes.searches.append({"words": list(search_words), "retry": retry})
            fakes.requests["search"].append(question)
            given(question, search_words)
            return fakes.found[min(len(fakes.searches), len(fakes.found)) - 1]

        def verify(question: str, items: List[Dict]) -> Dict:
            ids = [item["id"] for item in items]
            fakes.verified.append(ids)
            fakes.requests["verify"].append(question)
            given(question, items)
            return {"kept_ids": [item_id for item_id in ids if item_id in fakes.relevant]}

        def rewrite(question: str, tried_words: List[str]) -> Dict:
            fakes.rewrites += 1
            fakes.requests["rewrite"].append(question)
            given(question, tried_words)
            return {"search_words": list(fakes.new_words)}

        def write(question: str, language: str, people: List[Dict], level: str = "exact") -> Dict:
            fakes.card_people += [person["person"] for person in people]
            fakes.card_levels.append(level)
            fakes.requests["write_cards"].append(question)
            given(question, language, people)
            return {"cards": [{"person": person["person"], **fakes.card_text} for person in people]}

        monkeypatch.setattr(workflow.reader, "read", read)
        monkeypatch.setattr(workflow.searcher, "search", search, raising=False)
        monkeypatch.setattr(workflow.verifier, "verify", verify)
        monkeypatch.setattr(workflow.rewriter, "rewrite", rewrite)
        monkeypatch.setattr(workflow.card_writer, "write", write)
        return workflow, fakes

    yield build
    # After the test: close the connections to Postgres of every agent that has some
    for workflow in built:
        workflow.close()


@pytest.fixture
def agent(build_agent) -> Tuple[AgentWorkflow, Fakes]:
    """The real graph with fake LLM steps, for the free tests of the graph and of the API. Returns the workflow and its fakes.

    Its conversations are kept in the memory of the program, so these tests don't need Postgres.
    """
    return build_agent()


@pytest.fixture(scope="session")
def scenarios() -> Dict:
    """The demo scenarios of data/scenarios.json, by case id (like "s01"). Read once for all the tests."""
    cases = json.loads((PROJECT_ROOT / settings.DATA_DIR / "scenarios.json").read_text(encoding="utf-8"))
    return {case["id"]: case for case in cases}


@pytest.fixture(scope="session")
def answer_for(scenarios) -> Callable[[str], Dict]:
    """A function that builds the answer to the first question of a scenario, with no model call.

    The agent's own ranking, HR check, and answer builder are applied to the evidence the scenario lists.
    The LLM's two texts are missing, so each card gets its plain texts built from the data.
    """
    evidence = EvidenceSource()
    builder = AnswerBuilder(evidence)

    def build(case_id: str) -> Dict:
        turn = scenarios[case_id]["turns"][0]
        expected = turn["expected"]
        pieces = [piece for item_id in expected["evidence"] for piece in evidence.get_pieces(item_id)]
        ranking = Ranker().rank(pieces, expected["question_type"])
        checked = HrChecker().check(ranking)
        answer = builder.build(
            {
                "question": turn["question"],
                "road": "expert",
                "language": expected["language"],
                "message": "",
                "ranking": ranking,
                "recommended": checked["recommended"],
                "removed_left": checked["removed_left"],
                "removed_opted_out": checked["removed_opted_out"],
                "cards": [],
                "person_matches": [],
                "person_card": {},
            }
        )
        # The graph did not run, so there is no step line: the agent adds them to the answer after a real run
        answer["steps"] = []
        return answer

    return build


@pytest.fixture(scope="session")
def opted_out_names_in() -> Callable[[Dict], List[str]]:
    """A function that reads a whole answer, and returns the names of opted-out people found anywhere in it.

    It looks at every value of the answer (the cards, the note, the messages, and the links once they are decoded),
    for the first name and the last name of each person who opted out. No capital letters and no accents are needed.
    """

    def plain(text: str) -> str:
        decomposed = unicodedata.normalize("NFKD", text.lower())
        return "".join(letter for letter in decomposed if not unicodedata.combining(letter))

    opted_out = [person for person in PeopleSource().list_people() if not person["discoverable"]]

    def find(answer: Dict) -> List[str]:
        # The answer as one text, once as it is, and once with the %XX codes of the links turned back into letters
        text = json.dumps(answer, ensure_ascii=False)
        everything = plain(text) + " " + plain(unquote(text))
        return [
            name
            for person in opted_out
            for name in (person["first_name"], person["last_name"])
            if plain(name) in everything
        ]

    return find
