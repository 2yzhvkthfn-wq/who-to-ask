"""Free tests of person_card: what an answer may show about one colleague. No OpenAI calls.

The limits are tested on a tiny made-up company, so each test reads like the rule it checks.
The last tests use the throwaway MongoDB database: they show that the limits follow MongoDB at each question.
"""

from typing import Dict, List

import pytest

from agents.person_card_maker import PersonCardMaker
from config.constants import MAX_WORK_ITEMS

# The made-up company. p903 is the head: nobody manages p903
MANAGERS = {
    "p901": "p903",  # works here, and can be found
    "p902": "p903",  # works here, but opted out of being found
    "p903": "",  # the head of the company
    "p904": "p903",  # left the company
    "p905": "p904",  # works here. The directory still names p904, who left, as the manager
    "p906": "p903",  # opted out, then left
    "p907": "p999",  # works here. The directory names a manager that it doesn't know
    "p908": "p903",  # in the directory, but the HR system has no record of this person
    "p909": "p903",  # works here. The profile does not say whether this person can be found
    "p910": "p902",  # works here. The manager, p902, opted out of being found
    "p911": "p906",  # works here. The directory still names p906, who opted out and then left, as the manager
}
LEFT = ["p904", "p906"]
OPTED_OUT = ["p902", "p906"]
NO_HR_RECORD = ["p908"]
NO_DISCOVERABLE_FIELD = ["p909"]
# What the evidence says these people did: more pieces than a card may list, the most recent first
PIECES = {
    person_id: [
        {"person": person_id, "kind": "assigned", "item": f"TKT-{number}", "date": f"2026-10-{30 - number:02d}"}
        for number in range(MAX_WORK_ITEMS + 2)
    ]
    for person_id in ["p901", "p902", "p908", "p909"]
}


class MadeUpCompany:
    """Stands in for the readers of the directory and of the HR system, and for the evidence of the expert road."""

    def find_people(self, person_ids: List[str]) -> List[Dict]:
        profiles = []
        for person_id in person_ids:
            if person_id in MANAGERS:
                profile = {"id": person_id, "manager": MANAGERS[person_id], "discoverable": person_id not in OPTED_OUT}
                if person_id in NO_DISCOVERABLE_FIELD:
                    del profile["discoverable"]
                profiles.append(profile)
        return profiles

    def find_records(self, person_ids: List[str]) -> List[Dict]:
        return [
            {"person_id": person_id, "employment_status": "left" if person_id in LEFT else "employed"}
            for person_id in person_ids
            if person_id in MANAGERS and person_id not in NO_HR_RECORD
        ]

    def list_pieces_of(self, person_id: str) -> List[Dict]:
        return list(PIECES.get(person_id, []))


def make(person_id: str, asks: str = "card") -> Dict:
    """What person_card decides for one person of the made-up company."""
    company = MadeUpCompany()
    maker = PersonCardMaker(company)
    maker.people_source = company
    maker.hr_source = company
    return maker.make(person_id, asks)


# ----------------------------------------------------------------------
# The card of someone who works here
# ----------------------------------------------------------------------


def test_a_plain_card_is_the_card_of_the_person_asked_about():
    """Someone who works here: their own card, with their manager, and nothing they worked on."""
    assert make("p901") == {
        "subject": "p901",
        "person": "p901",
        "asks": "card",
        "left": False,
        "manager": "p903",
        "work": [],
    }


def test_someone_the_directory_does_not_know_gets_no_card():
    """No profile: an empty result, and the graph says that nobody has this name."""
    assert make("p999") == {}


# ----------------------------------------------------------------------
# Someone who left: the answer only says so
# ----------------------------------------------------------------------


@pytest.mark.parametrize("asks", ["card", "manager", "work_phone", "work"])
def test_someone_who_left_only_gets_their_name(asks):
    """Whatever is asked about someone who left: no manager, no ticket, no page. Only "left" is true."""
    card = make("p904", asks)
    assert card["left"] is True
    assert card["person"] == "p904"
    assert card["manager"] == ""
    assert card["work"] == []


def test_left_is_checked_before_opted_out():
    """Someone who opted out and then left is someone who left: the directory fields are not shown either."""
    assert make("p906")["left"] is True
    assert make("p906", "work")["work"] == []


def test_someone_the_hr_system_does_not_know_counts_as_someone_who_left():
    """A profile with no HR record: only the HR system says who works here, so nothing but the name is shown."""
    card = make("p908", "work")
    assert card["left"] is True
    assert card["manager"] == ""
    assert card["work"] == []
    # The evidence does hold tickets of p908: they are not listed
    assert PIECES["p908"]


# ----------------------------------------------------------------------
# "Who is X's manager?"
# ----------------------------------------------------------------------


def test_a_manager_question_shows_the_card_of_the_manager():
    """The question is about p901, and the card is the one of p903, the manager."""
    card = make("p901", "manager")
    assert card["subject"] == "p901"
    assert card["person"] == "p903"
    assert card["left"] is False
    # The card of the manager names the manager's own manager: p903 has none
    assert card["manager"] == ""


def test_someone_without_a_manager_keeps_their_own_card():
    """The head of the company has no manager: the card stays their own, and the answer says that none is listed."""
    card = make("p903", "manager")
    assert card["person"] == "p903" == card["subject"]
    assert card["left"] is False


def test_a_manager_the_directory_does_not_know_counts_as_no_manager():
    """The manager field points to nobody: the card stays the one of the person asked about."""
    card = make("p907", "manager")
    assert card["person"] == "p907"
    assert card["manager"] == ""


def test_a_manager_who_left_is_named_without_a_card():
    """The manager left the company: the answer names them and says so, and shows nothing else about them."""
    card = make("p905", "manager")
    assert card["subject"] == "p905"
    assert card["person"] == "p904"
    assert card["left"] is True


def test_a_manager_who_opted_out_keeps_their_place_in_the_directory():
    """Opting out hides someone's work, never their place in the directory: a manager who opted out is still the manager."""
    # "Who is p910's manager?": the card is the one of p902, who opted out, like the card of any other manager
    card = make("p910", "manager")
    assert card["subject"] == "p910"
    assert card["person"] == "p902"
    assert card["left"] is False
    # The card of p910 itself names p902 on its manager line too
    assert make("p910")["manager"] == "p902"
    # What stays hidden is the work of p902, even when it is asked for by name
    assert make("p902", "work")["work"] == []
    assert PIECES["p902"]


def test_a_manager_who_opted_out_and_then_left_is_someone_who_left():
    """ "Left" still comes first: the answer names the manager and says that they left, and shows nothing else."""
    card = make("p911", "manager")
    assert card["person"] == "p906"
    assert card["left"] is True
    # And the manager line of p911's own card stays empty, as for any manager who left
    assert make("p911")["manager"] == ""


def test_the_manager_line_never_names_someone_who_left():
    """The card of p905: the directory still names p904 as the manager, but p904 left, so the line stays empty."""
    card = make("p905")
    assert card["left"] is False
    assert card["manager"] == ""


# ----------------------------------------------------------------------
# "What does X work on?"
# ----------------------------------------------------------------------


def test_the_work_is_only_listed_when_it_is_asked_for():
    """A plain card, or a question about the phone, lists no ticket and no page."""
    assert make("p901", "card")["work"] == []
    assert make("p901", "work_phone")["work"] == []
    assert make("p901", "manager")["work"] == []


def test_the_work_is_the_most_recent_pieces_of_the_person():
    """The list is what the evidence says the person did, the most recent first, and it is short."""
    work = make("p901", "work")["work"]
    assert work == PIECES["p901"][:MAX_WORK_ITEMS]
    assert len(PIECES["p901"]) > MAX_WORK_ITEMS


def test_someone_who_opted_out_only_shows_the_directory_fields():
    """p902 opted out: the card is there with its directory fields, but no ticket and no page, even when asked."""
    card = make("p902", "work")
    assert card["left"] is False
    assert card["person"] == "p902"
    assert card["manager"] == "p903"
    assert card["work"] == []
    # The evidence does hold tickets of p902: the list is empty because of the opt-out, not for lack of work
    assert PIECES["p902"]


def test_a_profile_that_does_not_say_whether_the_person_can_be_found_lists_no_work():
    """The field is missing from the profile of p909: the safe reading is "can't be found", so no work is listed."""
    card = make("p909", "work")
    assert card["left"] is False
    assert card["person"] == "p909"
    assert card["work"] == []
    assert PIECES["p909"]


# ----------------------------------------------------------------------
# The limits follow MongoDB at each question (on the throwaway database)
# ----------------------------------------------------------------------


@pytest.fixture
def maker_on_mongodb(store, monkeypatch) -> PersonCardMaker:
    """A card maker whose two readers read the made-up company in the throwaway database."""
    company = MadeUpCompany()
    store.replace_documents("people", company.find_people(list(MANAGERS)))
    store.replace_documents(
        "hr_records", [{"id": f"hr-{record['person_id']}", **record} for record in company.find_records(list(MANAGERS))]
    )
    # The readers use the shared store of their module: for this test, it is the throwaway one
    monkeypatch.setattr("sources.people.mongo_store", store)
    monkeypatch.setattr("sources.hr.mongo_store", store)
    return PersonCardMaker(company)


def test_someone_who_leaves_only_gets_their_name_at_the_next_question(maker_on_mongodb, store):
    """The HR system records that p901 left while the app runs: the next card of p901 only says so."""
    assert maker_on_mongodb.make("p901", "work")["work"]

    store.database["hr_records"].update_one({"person_id": "p901"}, {"$set": {"employment_status": "left"}})

    card = maker_on_mongodb.make("p901", "work")
    assert card["left"] is True
    assert card["work"] == []


def test_someone_who_opts_out_hides_their_work_at_the_next_question(maker_on_mongodb, store):
    """p901 opts out while the app runs: the next "what does she work on?" lists nothing. No restart."""
    assert maker_on_mongodb.make("p901", "work")["work"]

    store.database["people"].update_one({"id": "p901"}, {"$set": {"discoverable": False}})

    card = maker_on_mongodb.make("p901", "work")
    assert card["left"] is False
    assert card["work"] == []
