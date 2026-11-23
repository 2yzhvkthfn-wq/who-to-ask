from typing import Dict, List

from .mongo_store import mongo_store


class PageSource:
    """Reads the fake Confluence pages from MongoDB: one document per page, with its header fields and its text.

    It keeps no copy: each call asks MongoDB, and returns what the database holds at that moment.
    """

    def list_pages(self) -> List[Dict]:
        """Return every page: its header fields, plus "body" (the text) and "file" (the name of its seed file)."""
        return mongo_store.list_documents("pages")
