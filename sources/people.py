from typing import Dict, List

from .mongo_store import mongo_store


class PeopleSource:
    """Reads the fake Teams directory from MongoDB: one profile per person.

    It keeps no copy: each call asks MongoDB, and returns what the database holds at that moment.
    """

    def list_people(self) -> List[Dict]:
        """Return every profile, including people who left (their names stay in old tickets and pages)."""
        return mongo_store.list_documents("people")

    def find_people(self, person_ids: List[str]) -> List[Dict]:
        """Return the profiles of these people only. An id that the directory doesn't know gives no profile."""
        # A query with a filter: MongoDB returns the profiles whose id is in the list, and nothing else
        return mongo_store.find_documents("people", "id", person_ids)
