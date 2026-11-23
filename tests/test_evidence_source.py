"""Free tests of the evidence, read from the side of a person: what "What does she work on?" lists. No OpenAI calls.

The expert road reads the evidence from a ticket or a page to its people. These tests read it the other way,
on the real data.
"""

import pytest

from sources import EvidenceSource


@pytest.fixture(scope="module")
def evidence() -> EvidenceSource:
    """The evidence items of the real data. Read once for all the tests of this file."""
    return EvidenceSource()


def test_the_pieces_of_a_person_are_what_the_expert_road_counts_for_them(evidence):
    """Read from the person or from the tickets and pages, the evidence is the same: no piece more, no piece less."""
    by_person = {}
    for item in evidence.list_items():
        for piece in item["pieces"]:
            by_person.setdefault(piece["person"], []).append(piece)

    assert by_person
    for person_id, pieces in by_person.items():
        found = evidence.list_pieces_of(person_id)
        assert sorted(piece["item"] for piece in found) == sorted(piece["item"] for piece in pieces)
        assert all(piece["person"] == person_id for piece in found)


def test_the_pieces_of_a_person_come_most_recent_first(evidence):
    """Scenario 13: the four tickets and pages of the team lead, from the newest to the oldest."""
    pieces = evidence.list_pieces_of("p007")

    assert [piece["item"] for piece in pieces] == ["CLM-296", "pg027", "pg017", "CLM-279"]
    assert [piece["date"] for piece in pieces] == sorted((piece["date"] for piece in pieces), reverse=True)


def test_someone_with_no_ticket_and_no_page_has_no_piece(evidence):
    """A person the evidence never counts for, or an id that nobody has: an empty list."""
    assert evidence.list_pieces_of("p017") == []
    assert evidence.list_pieces_of("p999") == []


def test_the_pieces_are_grouped_by_system_in_the_order_given(evidence):
    """Scenario 13: two groups, named by their system. The newest work comes first, in each group and between them."""
    groups = evidence.group_by_system(evidence.list_pieces_of("p007"))

    assert [group["system"] for group in groups] == ["Claims Intake", "Claims Workbench"]
    assert [[item["id"] for item in group["items"]] for group in groups] == [["CLM-296", "pg027"], ["pg017", "CLM-279"]]
    # A label says what a card needs: the id, the title, the source, what the person did, and a date
    assert groups[0]["items"][1] == {
        "id": "pg027",
        "title": "Claims Platform team meeting: minutes, 10 September 2026",
        "source": "Confluence",
        "kind": "decided",
        "date": "2026-09-10",
        "date_is": "meeting",
    }


def test_a_label_says_what_its_date_is(evidence):
    """The date of a label is the day a ticket was resolved, its last update while it is open, the last update
    of a doc, or the day of the meeting for minutes."""
    labels = {label["id"]: label for label in evidence.label_pieces(evidence.list_pieces_of("p007"))}

    # CLM-279 is resolved, and CLM-296 is still in progress
    assert (labels["CLM-279"]["date_is"], labels["CLM-296"]["date_is"]) == ("resolved", "updated")
    # pg017 is a doc, and pg027 is the minutes of a meeting
    assert (labels["pg017"]["date_is"], labels["pg027"]["date_is"]) == ("updated", "meeting")
    # The date of a label is the date that the ranking uses for this piece of evidence
    for piece in evidence.list_pieces_of("p007"):
        assert labels[piece["item"]]["date"] == piece["date"]


def test_a_general_page_is_in_a_group_with_no_system(evidence):
    """A page that is about no system: its group has an empty name, and the answer gives it a fixed one."""
    # p002 wrote the general technology roadmap, which is about no system
    groups = evidence.group_by_system(evidence.list_pieces_of("p002"))
    assert [group["system"] for group in groups] == [""]


# ----------------------------------------------------------------------
# The evidence, read from the side of a system: the second level of an answer
# ----------------------------------------------------------------------


def test_the_items_of_a_system_are_the_ones_the_data_puts_on_it(evidence):
    """Every ticket and page of the system that counts for someone, and no other one."""
    item_ids = evidence.list_ids_of_systems(["claims_workbench"])

    assert sorted(item_ids) == ["CLM-254", "CLM-262", "CLM-279", "pg017"]
    assert all(evidence.get_item(item_id)["system"] == "claims_workbench" for item_id in item_ids)


def test_the_items_of_several_systems_come_together(evidence):
    """Two systems: the items of both. No system, or a system that does not exist: no item."""
    assert sorted(evidence.list_ids_of_systems(["single_sign_on", "broker_portal"])) == ["DIG-170", "INF-225", "pg025", "pg026"]
    assert evidence.list_ids_of_systems([]) == []
    assert evidence.list_ids_of_systems(["the_mobile_app"]) == []


def test_an_access_request_belongs_to_the_system_that_gives_the_access(evidence):
    """CLM-239 asks for access to the Claims API for the Broker Portal: it is an item of the Claims API only."""
    assert "CLM-239" in evidence.list_ids_of_systems(["claims_api"])
    assert "CLM-239" not in evidence.list_ids_of_systems(["broker_portal"])


def test_a_general_page_is_never_an_item_of_a_system(evidence):
    """A page about no system has an empty system. An empty id in the list must not bring these pages back."""
    assert evidence.list_ids_of_systems([""]) == []
    assert "pg014" not in evidence.list_ids_of_systems(list(evidence.system_names))


def test_every_system_has_someone_behind_it(evidence):
    """Each of the 16 systems has at least one ticket or page that counts for someone: the second level has people to rank."""
    assert len(evidence.system_names) == 16
    for system_id in evidence.system_names:
        assert evidence.list_ids_of_systems([system_id]), system_id
