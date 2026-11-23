"""Copy the fake company files of the data folder into MongoDB. Free: no OpenAI calls.

Run it from the project folder, once at the start and after every change to a file of the data folder:
    python -m scripts.seed_mongodb
"""

import sys

from sources import SeedFiles
from sources.mongo_store import mongo_store
from utils.logging import logger

# The fields, besides id, that no two records of a collection may share: there is one HR record per person.
# MongoDB keeps a unique index on each of them. The HR check asks for HR records by person_id at each question:
# with the index, MongoDB goes straight to them instead of reading every record
UNIQUE_FIELDS = {"hr_records": ["person_id"]}


def main() -> None:
    """Read every file of the data folder, and make each MongoDB collection an exact copy of its file."""
    try:
        # 1) Read the seed files: one list of records per collection
        collections = SeedFiles().read()

        # 2) Replace each collection with the records of its file. Running this twice gives the same database
        for name, records in collections.items():
            saved = mongo_store.replace_documents(name, records, UNIQUE_FIELDS.get(name, []))
            logger.info(f"{name}: {saved} documents")
    except Exception:
        # The class that failed has already logged why. The screen gets one last clear line
        logger.error("MongoDB was NOT seeded: fix the problem above, then run this script again")
        sys.exit(1)
    logger.info(f"MongoDB seeded: the database {mongo_store.database.name} holds what the data folder holds")


if __name__ == "__main__":
    main()
