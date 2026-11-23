"""Free tests of find_person: who a name means. No OpenAI calls.

The rules are tested on a tiny made-up directory, so each test reads like the rule it checks.
The last tests use MongoDB: they show that the directory is read at each question.
"""

from typing import Dict, List

import pytest
from pydantic import SecretStr
from pymongo.errors import PyMongoError

from agents.person_finder import PersonFinder
from config.settings import settings
from sources import MongoStore


def profile(person_id: str, first_name: str, last_name: str) -> Dict:
    """One made-up profile, with the fields that find_person reads."""
    return {"id": person_id, "name": f"{first_name} {last_name}", "first_name": first_name, "last_name": last_name}


# The made-up directory: two people share a first name, one name has a hyphen and an accent, one has an apostrophe
DIRECTORY = [
    profile("p901", "Maria", "Lopez"),
    profile("p902", "Maria", "Chen"),
    profile("p903", "Jean-Luc", "Bédard"),
    profile("p904", "Zoé", "O'Neil"),
]


class MadeUpDirectory:
    """Stands in for the reader of the directory: it answers from the made-up profiles instead of MongoDB."""

    def list_people(self) -> List[Dict]:
        return list(DIRECTORY)


def found(name: str, shown_people: List[str] = ()) -> List[str]:
    """The ids that find_person returns for a name, with these people already shown in the conversation."""
    finder = PersonFinder()
    finder.people_source = MadeUpDirectory()
    return finder.find(name, list(shown_people))["matches"]


# ----------------------------------------------------------------------
# A name, looked up in the whole directory
# ----------------------------------------------------------------------


def test_a_full_name_finds_one_person():
    """The first name and the last name together mean one person."""
    assert found("Maria Lopez") == ["p901"]
    assert found("Maria Chen") == ["p902"]


def test_a_first_name_or_a_last_name_alone_is_enough():
    """One word of the name finds the person, when nobody else has it."""
    assert found("Lopez") == ["p901"]
    assert found("Zoé") == ["p904"]


@pytest.mark.parametrize(
    "name, person_id",
    [
        ("jean-luc bédard", "p903"),
        ("JEAN-LUC BEDARD", "p903"),
        ("Jean Luc Bedard", "p903"),
        ("bedard", "p903"),
        ("zoe o'neil", "p904"),
    ],
)
def test_capitals_accents_and_hyphens_do_not_matter(name, person_id):
    """A name typed in lower case, without its accents, or without its hyphen still finds the person."""
    assert found(name) == [person_id]


def test_the_s_of_a_possessive_is_dropped():
    """ "Maria Lopez's" is Maria Lopez, with a straight or a curly apostrophe."""
    assert found("Maria Lopez's") == ["p901"]
    assert found("Zoé’s") == ["p904"]


def test_a_shared_first_name_gives_several_people():
    """Two people are called Maria: both come back, in the order of the directory, and the graph asks which one."""
    assert found("Maria") == ["p901", "p902"]


def test_every_word_must_be_in_the_name():
    """A name with one word too many, or with the last name of someone else, finds nobody."""
    assert found("Maria Bédard") == []
    assert found("Maria Lopez Chen") == []
    assert found("Doctor Maria Lopez") == []


def test_an_unknown_name_finds_nobody():
    """Nobody has this name: an empty list, and the graph says so."""
    assert found("Nobody Atall") == []


# ----------------------------------------------------------------------
# The follow-up rule: the people already shown come first
# ----------------------------------------------------------------------


def test_a_name_means_the_person_already_shown():
    """After a card of Maria Chen, "Maria" means her, not every Maria of the company."""
    assert found("Maria", shown_people=["p902", "p903"]) == ["p902"]


def test_among_the_people_shown_the_most_recent_one_wins():
    """Both Marias were shown: the one shown last is the one. Nothing is asked."""
    assert found("Maria", shown_people=["p902", "p901"]) == ["p902"]
    assert found("Maria", shown_people=["p901", "p903", "p902"]) == ["p901"]


def test_a_name_that_nobody_shown_has_is_looked_up_in_the_directory():
    """The people shown don't have the name: the whole directory is searched, as for a first question."""
    assert found("Zoé", shown_people=["p901"]) == ["p904"]
    # A full name is never bent to fit someone shown: "Maria Chen" is not the Maria Lopez of the card
    assert found("Maria Chen", shown_people=["p901"]) == ["p902"]


def test_no_name_means_the_first_person_shown():
    """ "her", "him", or "them": the first person of the last answer. No guess from a first name."""
    assert found("", shown_people=["p903", "p901"]) == ["p903"]


def test_no_name_and_nobody_shown_finds_nobody():
    """A question that says "her" at the start of a conversation: there is nobody it can mean."""
    assert found("") == []


def test_only_spaces_count_as_no_name():
    """A name made of spaces is no name at all: the rule of "her" applies."""
    assert found("  ", shown_people=["p903"]) == ["p903"]
    assert found("  ") == []


@pytest.mark.parametrize("name", ["?", "42", "...", "Олег Иванов", "李雷", "Ελένη"])
def test_a_name_that_nobody_can_have_is_never_read_as_her(name):
    """Something was written as a name, with no letter in it, or in another alphabet: it is nobody's name.

    It must never fall back on the person already shown: the agent would then answer about someone the user
    did not mean, for example with the work phone of the wrong person.
    """
    assert found(name, shown_people=["p903", "p901"]) == []
    assert found(name) == []


def test_someone_the_directory_no_longer_knows_is_skipped():
    """A person who was shown earlier, and whose profile is gone, can't be meant: the next one is."""
    assert found("", shown_people=["p999", "p901"]) == ["p901"]
    assert found("Maria", shown_people=["p999"]) == ["p901", "p902"]


def test_the_log_of_the_screen_never_holds_the_name(screen_log):
    """The name the user typed may be anyone's: the screen's log line of find_person holds numbers only."""
    assert found("Maria Lopez", shown_people=["p903"]) == ["p901"]
    shown = "\n".join(screen_log)

    assert "Find person: 1 match(es) for a name" in shown
    assert "Maria" not in shown and "Lopez" not in shown


# ----------------------------------------------------------------------
# The directory is asked at each question
# ----------------------------------------------------------------------


def test_the_directory_is_read_at_each_question(store, monkeypatch):
    """A name changes in MongoDB while the app runs: the same finder, with no restart, finds the new name."""
    store.replace_documents("people", DIRECTORY)
    # The reader uses the shared store of its module: for this test, it is the throwaway one
    monkeypatch.setattr("sources.people.mongo_store", store)
    finder = PersonFinder()
    assert finder.find("Maria Lopez", [])["matches"] == ["p901"]

    # One field of one document changes, as if the directory had been edited a minute ago
    store.database["people"].update_one({"id": "p901"}, {"$set": {"last_name": "Garcia", "name": "Maria Garcia"}})

    assert finder.find("Maria Lopez", [])["matches"] == []
    assert finder.find("Maria Garcia", [])["matches"] == ["p901"]


def test_mongodb_stopped_is_an_error_and_never_no_one(monkeypatch):
    """MongoDB does not answer: an error. "No one by that name" must mean that the directory was read."""
    # Port 1 of this computer: no MongoDB listens there. A short timeout keeps the test fast
    monkeypatch.setattr(settings, "MONGODB_URI", SecretStr("mongodb://localhost:1"))
    monkeypatch.setattr("sources.mongo_store.MONGODB_TIMEOUT_MS", 300)
    stopped = MongoStore()
    monkeypatch.setattr("sources.people.mongo_store", stopped)

    with pytest.raises(PyMongoError):
        PersonFinder().find("Maria Lopez", [])
    stopped.client.close()
