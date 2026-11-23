from typing import Dict, List

from pymongo.errors import PyMongoError

from config.constants import SEED_COMMAND
from sources import SeedFiles
from sources.mongo_store import mongo_store

# A problem names at most this many ids
MAX_IDS_SHOWN = 5


class DatabaseChecker:
    """Checks that MongoDB holds exactly what the files of the data folder hold: the same records, in the same order."""

    def __init__(self):
        # What the files say: one list of records per collection. The files are the seed source of MongoDB
        self.files = SeedFiles().read()

    def check(self) -> Dict:
        """Compare each collection with its file. Return the problems found and the number of documents read."""
        problems, counts = [], {}
        for collection, records in self.files.items():
            # 1) Read the collection
            try:
                documents = mongo_store.list_documents(collection)
            except PyMongoError:
                # MongoDB did not answer. The other collections would only wait for the same error, so it stops here
                problems.append("MongoDB did not answer, so nothing was checked. Start the MongoDB service, then try again")
                return {"problems": problems, "counts": counts}
            except RuntimeError:
                # An empty collection: the seed has not run
                documents = []

            # 2) Compare it with its file: the same records, with the same values, in the same order
            counts[collection] = len(documents)
            if documents != records:
                problems.append(f"MongoDB {collection}: {self._describe(records, documents)}")

        # 3) One last line says what to do
        if problems:
            problems.append(f"MongoDB does not hold what the data folder holds. Run: {SEED_COMMAND}")
        return {"problems": problems, "counts": counts}

    def _describe(self, records: List[Dict], documents: List[Dict]) -> str:
        """Say in a few words how a collection differs from its file."""
        if not documents:
            return "the collection is empty"
        in_file = {record.get("id"): record for record in records}
        in_mongodb = {document.get("id"): document for document in documents}
        differences = [
            ("missing in MongoDB", [key for key in in_file if key not in in_mongodb]),
            ("only in MongoDB", [key for key in in_mongodb if key not in in_file]),
            ("different", [key for key in in_file if key in in_mongodb and in_file[key] != in_mongodb[key]]),
        ]
        parts = [f"{len(ids)} {words} ({self._some(ids)})" for words, ids in differences if ids]
        # The same records on both sides: then only their order differs
        return ", ".join(parts) or "the same records, in another order"

    def _some(self, ids: List[str]) -> str:
        """The first ids of a list, and "..." when there are more."""
        shown = ", ".join(str(key) for key in ids[:MAX_IDS_SHOWN])
        return f"{shown}, ..." if len(ids) > MAX_IDS_SHOWN else shown
