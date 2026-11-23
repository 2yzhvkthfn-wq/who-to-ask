"""Free tests of the fake company data: they read MongoDB and the files of the data folder, with no OpenAI calls."""

import pytest

from checks import DatabaseChecker, DataChecker, ScenarioChecker
from config.constants import SEED_COMMAND
from config.settings import BACKEND_DIR, settings


def test_mongodb_holds_what_the_files_hold():
    """Each MongoDB collection is an exact copy of its file. If this fails, run: python -m scripts.seed_mongodb"""
    result = DatabaseChecker().check()
    assert result["problems"] == []
    assert sorted(result["counts"]) == ["hr_records", "pages", "people", "systems", "teams", "tickets"]


@pytest.mark.parametrize(
    "breakage, expected",
    [
        ("a record more in the file", "MongoDB people: 1 missing in MongoDB (p999)"),
        ("a record less in the file", "MongoDB people: 1 only in MongoDB (p001)"),
        ("another value in the file", "MongoDB people: 1 different (p001)"),
        ("another order in the file", "MongoDB people: the same records, in another order"),
    ],
)
def test_the_database_check_notices_a_difference(breakage, expected):
    """A test of the check itself: the file side is changed in memory, and the check must say how MongoDB differs."""
    checker = DatabaseChecker()
    people = checker.files["people"]
    if breakage == "a record more in the file":
        people.append({**people[0], "id": "p999"})
    elif breakage == "a record less in the file":
        people.pop(0)
    elif breakage == "another value in the file":
        people[0] = {**people[0], "job_title": "Another job title"}
    else:
        people.reverse()

    # One line says what differs, and the last line says which command fixes it
    problems = checker.check()["problems"]
    assert problems[0] == expected
    assert len(problems) == 2
    assert problems[-1].endswith(f"Run: {SEED_COMMAND}")


def test_data_is_consistent():
    """The data check finds no problem."""
    result = DataChecker().check()
    assert result["problems"] == []


def test_every_scenario_exists_in_the_data():
    """Applied to the evidence, the ranking rules and the HR check give the people each scenario expects."""
    result = ScenarioChecker().check()
    assert result["problems"] == []


def test_scenario_report_is_up_to_date():
    """The saved report matches the data. If this fails, run: python -m scripts.show_scenarios"""
    saved = (BACKEND_DIR / settings.DATA_DIR / "scenario_evidence.md").read_text(encoding="utf-8")
    assert saved == ScenarioChecker().check()["report"]
