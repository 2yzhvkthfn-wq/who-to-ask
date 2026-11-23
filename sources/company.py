from typing import Dict, List

from .mongo_store import mongo_store


class CompanySource:
    """Reads the teams and the systems of the fake company from MongoDB.

    It keeps no copy: each call asks MongoDB, and returns what the database holds at that moment.
    """

    def list_teams(self) -> List[Dict]:
        """Return every team."""
        return mongo_store.list_documents("teams")

    def list_systems(self) -> List[Dict]:
        """Return every system."""
        return mongo_store.list_documents("systems")
