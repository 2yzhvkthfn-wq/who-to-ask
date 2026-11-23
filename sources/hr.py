from typing import Dict, List

from .mongo_store import mongo_store


class HrSource:
    """Reads the fake HR system from MongoDB: the only place that says who still works at the company.

    It keeps no copy: each call asks MongoDB, and returns what the database holds at that moment.
    """

    def list_records(self) -> List[Dict]:
        """Return every HR record (one per person)."""
        return mongo_store.list_documents("hr_records")

    def find_records(self, person_ids: List[str]) -> List[Dict]:
        """Return the HR records of these people only. A person that the HR system doesn't know gives no record."""
        # A query with a filter: MongoDB returns the records whose person_id is in the list, and nothing else
        return mongo_store.find_documents("hr_records", "person_id", person_ids)
