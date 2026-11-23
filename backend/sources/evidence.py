from typing import Dict, List

from utils.logging import logger

from .company import CompanySource
from .pages import PageSource
from .tickets import TicketSource


class EvidenceSource:
    """Reads tickets and pages as evidence: what each one says, and the people it counts for."""

    def __init__(self):
        # 1) The names of the systems, to write "Claims API" in a text instead of "claims_api"
        self.system_names = {system["id"]: system["name"] for system in CompanySource().list_systems()}

        # 2) One item per ticket and per page
        items = [self._ticket_item(ticket) for ticket in TicketSource().list_tickets()]
        items += [self._page_item(page) for page in PageSource().list_pages()]

        # 3) Keep the items that count for at least one person: the others can't lead to anyone
        self.items = {item["id"]: item for item in items if item["pieces"]}
        logger.info(f"Evidence: {len(self.items)} of {len(items)} tickets and pages count for someone")

    def list_items(self) -> List[Dict]:
        """Return every evidence item: a ticket or a page that counts for at least one person."""
        return list(self.items.values())

    def get_item(self, item_id: str) -> Dict:
        """Return one evidence item by its id (a Jira key like CLM-212, or a page id like pg014)."""
        return self.items[item_id]

    def get_pieces(self, item_id: str) -> List[Dict]:
        """Return who a ticket or page counts for: one piece per person. It is empty when it counts for nobody."""
        item = self.items.get(item_id)
        return item["pieces"] if item else []

    def list_ids_of_systems(self, system_ids: List[str]) -> List[str]:
        """Return the ids of every evidence item that is about one of these systems, in the order of the data.

        It is the second level of an answer. When nothing is about the exact need of a request, the people behind
        the tickets and pages of the system it names are still the people who work on that system.
        A general page is about no system, so it is never in the list.
        """
        return [item["id"] for item in self.items.values() if item["system"] and item["system"] in system_ids]

    def label_pieces(self, pieces: List[Dict]) -> List[Dict]:
        """Return what a card shows for each piece of evidence: the id, the title, the source, and what the person did."""
        labels = [self._label(piece) for piece in pieces]
        # Pages first, then tickets, each in the order of the ids: the same answer always reads the same way
        return sorted(labels, key=lambda label: (label["source"] != "Confluence", label["id"]))

    def list_pieces_of(self, person_id: str) -> List[Dict]:
        """Return every piece of evidence of one person, the most recent first.

        It is the expert road's evidence, read in the other direction: from a person to the docs they wrote,
        the decisions they own, and the tickets they were assigned to or approved. Nothing is searched.
        """
        pieces = [piece for item in self.items.values() for piece in item["pieces"] if piece["person"] == person_id]
        # The most recent first. Two pieces of the same day keep the order of their ids, so nothing is random
        pieces.sort(key=lambda piece: piece["item"])
        pieces.sort(key=lambda piece: piece["date"], reverse=True)
        return pieces

    def group_by_system(self, pieces: List[Dict]) -> List[Dict]:
        """Return the pieces as labels, grouped by the system they are about. The groups and their labels keep the order given.

        A group has the name of its system ("" for a general page, which is about no system) and its labels.
        """
        groups: Dict[str, List[Dict]] = {}
        for piece in pieces:
            system_id = self.items[piece["item"]]["system"]
            groups.setdefault(self.system_names.get(system_id, system_id), []).append(self._label(piece))
        return [{"system": system_name, "items": labels} for system_name, labels in groups.items()]

    def _label(self, piece: Dict) -> Dict:
        """What an answer shows for one piece of evidence: the id, the title, the source, what the person did, and a date."""
        item = self.items[piece["item"]]
        return {
            "id": item["id"],
            "title": item["title"],
            "source": item["source"],
            "kind": piece["kind"],
            # The day of the ticket or the page, and what happened that day: "resolved", "updated", or "meeting"
            "date": item["date"],
            "date_is": item["date_is"],
        }

    # ------------------------------------------------------------------
    # What counts as evidence (the rules are in PROJECT.md, "Ranking rules")
    # ------------------------------------------------------------------

    def _ticket_item(self, ticket: Dict) -> Dict:
        """A Jira ticket counts for its assignee and for its approver. Its reporter and its comments count for nobody."""
        # The day the work was done: the day the ticket was resolved, or its last update while it is open
        day = ticket["resolved"] or ticket["updated"]
        pieces = []
        if ticket["assignee"]:
            pieces.append({"person": ticket["assignee"], "kind": "assigned", "item": ticket["id"], "date": day})
        if ticket["approver"]:
            pieces.append({"person": ticket["approver"], "kind": "approved", "item": ticket["id"], "date": day})
        return {
            "id": ticket["id"],
            "source": "Jira",
            "type": "ticket",
            "title": ticket["summary"],
            # The system the ticket is about (a system id)
            "system": ticket["component"],
            # The date a card shows next to the ticket, and what it is: the day it was resolved,
            # or its last update while it is open
            "date": day,
            "date_is": "resolved" if ticket["resolved"] else "updated",
            "text": self._ticket_text(ticket),
            "pieces": pieces,
        }

    def _page_item(self, page: Dict) -> Dict:
        """A doc counts for its author, and minutes count for the decision owner. An agenda counts for nobody."""
        pieces = []
        # The date a card shows next to the page, and what it is: the day of the meeting for minutes and agendas,
        # and the last update for a doc
        is_meeting = page["type"] in ["minutes", "agenda"]
        day = page["meeting_date"] if is_meeting else page["updated"]
        if page["type"] == "doc":
            pieces.append({"person": page["author"], "kind": "wrote", "item": page["id"], "date": day})
        elif page["type"] == "minutes" and page["decision_owner"]:
            # Writing the minutes, organizing the meeting, and attending it count for nothing
            pieces.append({"person": page["decision_owner"], "kind": "decided", "item": page["id"], "date": day})
        return {
            "id": page["id"],
            "source": "Confluence",
            # "doc", "minutes", or "agenda": verify reads minutes with one more rule
            "type": page["type"],
            "title": page["title"],
            # The system the page is about (a system id), or "" for a general page
            "system": page["system"],
            "date": day,
            "date_is": "meeting" if is_meeting else "updated",
            "text": self._page_text(page),
            "pieces": pieces,
        }

    # ------------------------------------------------------------------
    # The text of an item: what the search indexes, and what verify reads
    # ------------------------------------------------------------------

    def _ticket_text(self, ticket: Dict) -> str:
        """A ticket as one text: a first line that says what it is, then its summary, description, and comments."""
        details = [ticket["type"]] + self._system_detail(ticket["component"])
        lines = [f"Jira ticket {ticket['id']} ({', '.join(details)})", f"Summary: {ticket['summary']}"]
        if ticket["labels"]:
            lines.append(f"Labels: {', '.join(ticket['labels'])}")
        lines += ["", ticket["description"]]
        if ticket["comments"]:
            # Who wrote a comment is left out: the text is judged, not the people
            lines += ["", "Comments:"] + [f"- {comment['text']}" for comment in ticket["comments"]]
        return "\n".join(lines)

    def _page_text(self, page: Dict) -> str:
        """A page as one text: a first line that says what it is, then its title and its body."""
        kind = "meeting minutes" if page["type"] == "minutes" else page["type"]
        details = [kind] + self._system_detail(page["system"])
        return "\n".join([f"Confluence page {page['id']} ({', '.join(details)})", f"Title: {page['title']}", "", page["body"]])

    def _system_detail(self, system_id: str) -> List[str]:
        """The words "system: Claims API" for the first line of a text, or nothing for a general page."""
        return [f"system: {self.system_names.get(system_id, system_id)}"] if system_id else []
