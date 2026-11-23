"""Free tests of the ranking rules of PROJECT.md, and of what counts as evidence. No OpenAI calls.

The first tests use tiny made-up evidence, so each one reads like the rule it checks.
The last ones run the same rules on the real data of the scenarios.
"""

from typing import Dict, List

import pytest

from agents.hr_checker import HrChecker
from agents.ranker import Ranker
from sources import EvidenceSource, PageSource, TicketSource


def piece(person: str, kind: str, item: str, date: str = "2026-01-15") -> Dict:
    """One made-up piece of evidence: who, what they did ("wrote", "decided", "assigned", "approved"), where, and when."""
    return {"person": person, "kind": kind, "item": item, "date": date}


def order(pieces: List[Dict], question_type: str) -> List[str]:
    """The people the ranker finds behind the pieces, best first."""
    return [entry["person"] for entry in Ranker().rank(pieces, question_type)]


# One doc for p001, three tickets for p002, and one decision for p003
MIXED_EVIDENCE = [
    piece("p001", "wrote", "page-1"),
    piece("p002", "assigned", "T-1"),
    piece("p002", "assigned", "T-2"),
    piece("p002", "approved", "T-3"),
    piece("p003", "decided", "minutes-1"),
]


# ----------------------------------------------------------------------
# The type of question decides which source counts first
# ----------------------------------------------------------------------


def test_help_puts_confluence_first():
    """ "Who can help me with X?": one doc or one decision beats three tickets, because Confluence counts first."""
    assert order(MIXED_EVIDENCE, "help") == ["p001", "p003", "p002"]


def test_did_puts_jira_first():
    """ "Who fixed X?": the same evidence in the other order, because Jira counts first."""
    assert order(MIXED_EVIDENCE, "did") == ["p002", "p001", "p003"]


def test_approving_a_ticket_is_jira_evidence():
    """ "Who approved X?" is a "did" question: an approval counts first, like an assignment."""
    pieces = [piece("p001", "wrote", "page-1"), piece("p002", "approved", "T-1")]
    assert order(pieces, "did") == ["p002", "p001"]
    assert order(pieces, "help") == ["p001", "p002"]


def test_decided_only_shows_decision_owners():
    """ "Who decided X?": only the decision counts. The people who did the work get no entry."""
    # p003 decided, and also wrote a doc: for this type of question, the doc doesn't count either
    pieces = MIXED_EVIDENCE + [piece("p003", "wrote", "page-2")]
    ranking = Ranker().rank(pieces, "decided")
    assert [entry["person"] for entry in ranking] == ["p003"]
    assert [found["item"] for found in ranking[0]["pieces"]] == ["minutes-1"]


def test_decided_with_no_decision_finds_nobody():
    """Tickets and docs about the topic, but no recorded decision: nobody decided, so nobody is found."""
    pieces = [piece("p001", "wrote", "page-1"), piece("p002", "assigned", "T-1"), piece("p002", "approved", "T-2")]
    assert Ranker().rank(pieces, "decided") == []


def test_an_unknown_question_type_is_refused():
    """The ranker never guesses a type: an unknown one is an error."""
    with pytest.raises(ValueError):
        Ranker().rank(MIXED_EVIDENCE, "guess")


# ----------------------------------------------------------------------
# Inside the same group: more pieces, then the most recent, then the person id
# ----------------------------------------------------------------------


def test_more_pieces_come_first():
    """Both people have a doc. p002 also has a ticket, and the pieces of both sources are counted."""
    pieces = [piece("p001", "wrote", "page-1"), piece("p002", "wrote", "page-2"), piece("p002", "assigned", "T-1")]
    assert order(pieces, "help") == ["p002", "p001"]


def test_the_most_recent_evidence_breaks_a_tie():
    """The same number of pieces: the person whose latest piece is the most recent comes first."""
    pieces = [piece("p001", "wrote", "page-1", "2026-03-01"), piece("p002", "wrote", "page-2", "2026-09-01")]
    assert order(pieces, "help") == ["p002", "p001"]


def test_the_person_id_is_the_last_tie_break():
    """Everything is equal: the lower person id comes first, so the order is never left to chance."""
    pieces = [piece("p002", "wrote", "page-2"), piece("p001", "wrote", "page-1")]
    assert order(pieces, "help") == ["p001", "p002"]


def test_the_same_evidence_always_gives_the_same_order():
    """Nothing is random: giving the pieces in another order doesn't change the ranking."""
    backwards = list(reversed(MIXED_EVIDENCE))
    for question_type in ["help", "did", "decided"]:
        assert order(backwards, question_type) == order(MIXED_EVIDENCE, question_type)


# ----------------------------------------------------------------------
# What counts as evidence, on the real data
# ----------------------------------------------------------------------


def test_only_four_things_count_as_evidence():
    """Writing a doc, owning a decision, being assigned a ticket, and approving one. Nothing else leads to a person."""
    tickets = {ticket["id"]: ticket for ticket in TicketSource().list_tickets()}
    pages = {page["id"]: page for page in PageSource().list_pages()}
    for item in EvidenceSource().list_items():
        for found in item["pieces"]:
            if found["kind"] == "assigned":
                assert found["person"] == tickets[item["id"]]["assignee"]
            elif found["kind"] == "approved":
                assert found["person"] == tickets[item["id"]]["approver"]
            elif found["kind"] == "wrote":
                assert pages[item["id"]]["type"] == "doc" and found["person"] == pages[item["id"]]["author"]
            else:
                # The last kind is a decision, in meeting minutes. Reporting a ticket, commenting, writing an agenda
                # or the minutes, and organizing or attending a meeting are not kinds at all
                assert found["kind"] == "decided"
                assert pages[item["id"]]["type"] == "minutes"
                assert found["person"] == pages[item["id"]]["decision_owner"]


def test_a_decided_question_only_reads_minutes_with_a_decision():
    """On the real data, the only texts that count for a "decided" question are the minutes with a decision owner."""
    ranker = Ranker()
    counting = [
        item["id"] for item in EvidenceSource().list_items() if ranker.pieces_that_count(item["pieces"], "decided")
    ]
    minutes = [
        page["id"] for page in PageSource().list_pages() if page["type"] == "minutes" and page["decision_owner"]
    ]
    assert minutes
    assert sorted(counting) == sorted(minutes)


def test_items_that_lead_to_nobody_are_not_evidence(scenarios):
    """A ticket with no assignee and no approver, or an agenda, can't be searched: it would lead to nobody."""
    evidence = EvidenceSource()
    evidence_ids = [item["id"] for item in evidence.list_items()]
    for case in scenarios.values():
        for turn in case["turns"]:
            for item in turn["expected"].get("no_person", []):
                assert item["id"] not in evidence_ids
                assert evidence.get_pieces(item["id"]) == []
            for item_id in turn["expected"].get("evidence", []):
                assert item_id in evidence_ids


# ----------------------------------------------------------------------
# The rules on the real evidence of scenario 1
# ----------------------------------------------------------------------


def test_scenario_1_ranking_and_hr_check(scenarios):
    """From the evidence a correct verify keeps, the rules give Sophie Martin, David Chen, and Olivia Tremblay."""
    expected = scenarios["s01"]["turns"][0]["expected"]
    evidence = EvidenceSource()

    # The same steps as the graph, after verify: the pieces of the evidence, the ranking, the HR check
    pieces = [found for item_id in expected["evidence"] for found in evidence.get_pieces(item_id)]
    ranking = Ranker().rank(pieces, expected["question_type"])
    result = HrChecker().check(ranking)

    recommended = [entry["person"] for entry in result["recommended"]]
    assert recommended == expected["people"]
    assert result["removed_left"] == expected["removed_left"]
    assert len(result["removed_opted_out"]) == expected["removed_opted_out"]
    for person_id in expected["forbidden_people"]:
        assert person_id not in recommended


def test_the_question_type_changes_the_answer_of_scenario_1(scenarios):
    """The same evidence, read as each type of question: the type really decides who comes first."""
    expected = scenarios["s01"]["turns"][0]["expected"]
    evidence = EvidenceSource()
    pieces = [found for item_id in expected["evidence"] for found in evidence.get_pieces(item_id)]

    # "help": Sophie Martin (p012) wrote the access guide, so she comes first
    assert order(pieces, "help")[0] == "p012"
    # "did": David Chen (p006) approved the six access requests, so he comes first
    assert order(pieces, "did")[0] == "p006"
    # "decided": no meeting minutes record a decision about access to the Claims API
    assert order(pieces, "decided") == []
