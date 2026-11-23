"""Free tests of the HR check: who is removed from a ranking, and who is kept. No OpenAI calls.

The rules are tested on a tiny made-up company, so each test reads like the rule it checks.
The last tests use the throwaway MongoDB database: they show that the check asks MongoDB at each question.
"""

from typing import Dict, List, Sequence

import pytest
from pydantic import SecretStr
from pymongo.errors import PyMongoError

from agents.hr_checker import HrChecker
from config.constants import MAX_CARDS
from config.settings import settings
from sources import MongoStore

# The made-up company: six people, p001 to p006
EVERYONE = ["p001", "p002", "p003", "p004", "p005", "p006"]


class MadeUpCompany:
    """Stands in for the two readers of the HR check: it answers from a made-up company instead of MongoDB.

    Everyone works there and can be found, except the people listed. It also notes what the check asked for.
    """

    def __init__(self, left: Sequence[str], opted_out: Sequence[str], away: Sequence[str]):
        self.left, self.opted_out, self.away = left, opted_out, away
        # One list of person ids per question the check asked
        self.asked: List[List[str]] = []

    def find_people(self, person_ids: List[str]) -> List[Dict]:
        """The profiles of the people asked for. Someone the made-up company doesn't know gives nothing."""
        self.asked.append(list(person_ids))
        return [
            {
                "id": person_id,
                "discoverable": person_id not in self.opted_out,
                "out_of_office_until": "2026-11-10" if person_id in self.away else "",
            }
            for person_id in person_ids
            if person_id in EVERYONE
        ]

    def find_records(self, person_ids: List[str]) -> List[Dict]:
        """The HR records of the people asked for."""
        self.asked.append(list(person_ids))
        return [
            {"person_id": person_id, "employment_status": "left" if person_id in self.left else "employed"}
            for person_id in person_ids
            if person_id in EVERYONE
        ]


def checker_for(left: Sequence[str] = (), opted_out: Sequence[str] = (), away: Sequence[str] = ()) -> HrChecker:
    """An HR checker for the made-up company. Everyone works there and can be found, except the people listed."""
    checker = HrChecker()
    # Replace the two readers of MongoDB by the made-up company
    company = MadeUpCompany(left, opted_out, away)
    checker.people_source = company
    checker.hr_source = company
    return checker


def ranking_of(person_ids: List[str]) -> List[Dict]:
    """A ranking of these people, best first. The HR check only reads who each entry is about."""
    return [{"person": person_id} for person_id in person_ids]


def kept(result: Dict) -> List[str]:
    """The people the HR check recommends, in order."""
    return [entry["person"] for entry in result["recommended"]]


# ----------------------------------------------------------------------
# The rules, on the made-up company
# ----------------------------------------------------------------------


def test_someone_who_left_is_removed():
    """The HR file says that p002 left: p002 is not recommended, and is listed as someone who left."""
    result = checker_for(left=["p002"]).check(ranking_of(["p001", "p002", "p003"]))
    assert kept(result) == ["p001", "p003"]
    assert result["removed_left"] == ["p002"]
    assert result["removed_opted_out"] == []


def test_someone_who_opted_out_is_removed():
    """p002 opted out of being found: p002 is not recommended, and is listed apart from the people who left."""
    result = checker_for(opted_out=["p002"]).check(ranking_of(["p001", "p002", "p003"]))
    assert kept(result) == ["p001", "p003"]
    assert result["removed_opted_out"] == ["p002"]
    assert result["removed_left"] == []


def test_opted_out_is_checked_before_left():
    """Someone who opted out and later left is counted as opted out, so the answer never names them."""
    result = checker_for(left=["p002"], opted_out=["p002"]).check(ranking_of(["p001", "p002"]))
    assert result["removed_opted_out"] == ["p002"]
    assert result["removed_left"] == []


def test_only_three_people_are_kept():
    """Five people could be recommended: the answer keeps the first three, in the order of the ranking."""
    result = checker_for().check(ranking_of(["p005", "p003", "p001", "p002", "p004"]))
    assert MAX_CARDS == 3
    assert kept(result) == ["p005", "p003", "p001"]


def test_a_removed_person_does_not_take_a_place():
    """The three places go to the first three people who remain, not to the first three of the ranking."""
    checker = checker_for(left=["p001"], opted_out=["p003"])
    result = checker.check(ranking_of(["p001", "p002", "p003", "p004", "p005", "p006"]))
    assert kept(result) == ["p002", "p004", "p005"]


def test_everyone_removed_gives_nobody():
    """Nobody is left to recommend, and the result still says who was removed, for the note."""
    result = checker_for(left=["p001"], opted_out=["p002"]).check(ranking_of(["p001", "p002"]))
    assert kept(result) == []
    assert result["removed_left"] == ["p001"]
    assert result["removed_opted_out"] == ["p002"]


def test_being_out_of_office_changes_nothing():
    """Someone who is away keeps their place: the card will say so, but the ranking doesn't move."""
    result = checker_for(away=["p001"]).check(ranking_of(["p001", "p002"]))
    assert kept(result) == ["p001", "p002"]


def test_someone_the_data_does_not_know_is_never_recommended():
    """A person with no profile and no HR record can't be recommended: the check never trusts an unknown id."""
    result = checker_for().check(ranking_of(["p999", "p001"]))
    assert kept(result) == ["p001"]
    # The unknown person is counted with the people who opted out, so no answer can name them
    assert result["removed_opted_out"] == ["p999"]


def test_the_check_only_asks_about_the_people_of_the_ranking():
    """One question about the profiles and one about the HR records, both for the ranked people and nobody else."""
    checker = checker_for()
    checker.check(ranking_of(["p003", "p001"]))
    assert checker.people_source.asked == [["p003", "p001"], ["p003", "p001"]]


def test_an_empty_ranking_asks_nothing():
    """Nobody is ranked: nobody is recommended or removed, and MongoDB is not asked anything."""
    checker = checker_for()
    assert checker.check([]) == {"recommended": [], "removed_left": [], "removed_opted_out": []}
    assert checker.people_source.asked == []


# ----------------------------------------------------------------------
# The check asks MongoDB at each question (on the throwaway database)
# ----------------------------------------------------------------------


@pytest.fixture
def company_in_mongodb(store, monkeypatch) -> MongoStore:
    """The made-up company, saved in the throwaway database. The two readers of the HR check read it there."""
    store.replace_documents("people", [{"id": person_id, "discoverable": True} for person_id in EVERYONE])
    store.replace_documents(
        "hr_records",
        [{"id": f"hr-{person_id}", "person_id": person_id, "employment_status": "employed"} for person_id in EVERYONE],
    )
    # The readers use the shared store of their module: for this test, it is the throwaway one
    monkeypatch.setattr("sources.people.mongo_store", store)
    monkeypatch.setattr("sources.hr.mongo_store", store)
    return store


def test_someone_who_opts_out_is_removed_at_the_next_question(company_in_mongodb):
    """p002 opts out while the app runs: the same checker, with no restart, no longer recommends p002."""
    checker = HrChecker()
    ranking = ranking_of(["p001", "p002", "p003"])
    assert kept(checker.check(ranking)) == ["p001", "p002", "p003"]

    # One field of one document changes in MongoDB, as if p002 had ticked "don't show me" a minute ago
    company_in_mongodb.database["people"].update_one({"id": "p002"}, {"$set": {"discoverable": False}})

    result = checker.check(ranking)
    assert kept(result) == ["p001", "p003"]
    assert result["removed_opted_out"] == ["p002"]


def test_someone_who_leaves_is_removed_at_the_next_question(company_in_mongodb):
    """The HR system records that p001 left while the app runs: the next question no longer recommends p001."""
    checker = HrChecker()
    ranking = ranking_of(["p001", "p002", "p003"])
    assert kept(checker.check(ranking)) == ["p001", "p002", "p003"]

    company_in_mongodb.database["hr_records"].update_one({"person_id": "p001"}, {"$set": {"employment_status": "left"}})

    result = checker.check(ranking)
    assert kept(result) == ["p002", "p003"]
    assert result["removed_left"] == ["p001"]


def test_someone_who_opts_back_in_is_recommended_again(company_in_mongodb):
    """The check follows MongoDB in both directions: p002 opts out, then back in, and is recommended again."""
    checker = HrChecker()
    ranking = ranking_of(["p001", "p002"])
    people = company_in_mongodb.database["people"]

    people.update_one({"id": "p002"}, {"$set": {"discoverable": False}})
    assert kept(checker.check(ranking)) == ["p001"]

    people.update_one({"id": "p002"}, {"$set": {"discoverable": True}})
    assert kept(checker.check(ranking)) == ["p001", "p002"]


def test_mongodb_stopped_during_the_check_is_an_error(monkeypatch):
    """MongoDB does not answer at a question: the check raises an error.

    It never recommends from memory, and it never reads "no answer" as "everyone was removed".
    """
    # Port 1 of this computer: no MongoDB listens there. A short timeout keeps the test fast
    monkeypatch.setattr(settings, "MONGODB_URI", SecretStr("mongodb://localhost:1"))
    monkeypatch.setattr("sources.mongo_store.MONGODB_TIMEOUT_MS", 300)
    stopped = MongoStore()
    monkeypatch.setattr("sources.people.mongo_store", stopped)
    monkeypatch.setattr("sources.hr.mongo_store", stopped)

    with pytest.raises(PyMongoError):
        HrChecker().check(ranking_of(["p001", "p002"]))
    stopped.client.close()
