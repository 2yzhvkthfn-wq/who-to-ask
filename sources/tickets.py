from typing import Dict, List

from .mongo_store import mongo_store


class TicketSource:
    """Reads the fake Jira tickets from MongoDB. A ticket's comments are inside the ticket: one document holds both.

    It keeps no copy: each call asks MongoDB, and returns what the database holds at that moment.
    """

    def list_tickets(self) -> List[Dict]:
        """Return every ticket. A ticket's id is its Jira key, like CLM-212."""
        return mongo_store.list_documents("tickets")
