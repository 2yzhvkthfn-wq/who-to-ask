from typing import Dict, List, Sequence

from pymongo import MongoClient
from pymongo.errors import BulkWriteError, PyMongoError

from config.constants import MONGODB_TIMEOUT_MS, SEED_COMMAND
from config.settings import settings
from utils.logging import logger


class MongoStore:
    """Opens MongoDB once. It reads a whole collection of the fake company data or some of its records, or replaces it."""

    def __init__(self):
        # 1) The address of MongoDB. It can hold a password, so no message ever repeats it.
        #    It is checked here because PyMongo takes anything without mongodb:// as the name of a computer,
        #    and would then write that name in its errors
        address = settings.MONGODB_URI.get_secret_value()
        if not address.startswith(("mongodb://", "mongodb+srv://")):
            logger.error("MONGODB_URI must start with mongodb:// (or mongodb+srv:// for a cloud cluster)")
            raise RuntimeError("MONGODB_URI must start with mongodb:// (or mongodb+srv:// for a cloud cluster)")

        # 2) One client for the whole program. Creating it does not wait for MongoDB: a problem only shows at the
        #    first read or write, which then waits a few seconds (PyMongo's default is thirty)
        try:
            self.client = MongoClient(address, serverSelectionTimeoutMS=MONGODB_TIMEOUT_MS)
        except PyMongoError as e:
            # PyMongo's message could repeat a part of the address: only the kind of error is shown
            logger.error(f"MONGODB_URI is not a valid MongoDB address ({type(e).__name__})")
            raise RuntimeError("MONGODB_URI is not a valid MongoDB address") from None

        # 3) The database of the project. MongoDB creates it by itself at the first write
        self.database = self.client[settings.MONGODB_DATABASE]
        # 4) The first read says once, in the log, where the data comes from
        self.announced = False

    def list_documents(self, collection: str) -> List[Dict]:
        """Return every record of a collection, in the order of its seed file, without MongoDB's own _id."""
        try:
            # find({}) asks for every document. {"_id": 0} is a projection: it leaves the _id field out.
            # The sort is needed: MongoDB only promises an order when the query asks for one
            documents = list(self.database[collection].find({}, {"_id": 0}).sort("_id", 1))
        except PyMongoError as e:
            # A short error takes the place of PyMongo's own. "from None" leaves PyMongo's long text out of
            # whatever is printed afterwards: it is in app.log
            raise self._short_error("read", collection, e) from None

        # An empty collection means that the seed has not run. It is an error, never an empty answer:
        # with no data, the agent would say "nobody found" as if it had looked
        if not documents:
            raise RuntimeError(f"The MongoDB collection {collection} is empty. Run: {SEED_COMMAND}")

        if not self.announced:
            logger.info(f"MongoDB: reading the company data from the database {self.database.name}")
            self.announced = True
        logger.debug(f"MongoDB: {len(documents)} documents read from {collection}")
        return documents

    def find_documents(self, collection: str, field: str, values: List[str]) -> List[Dict]:
        """Return the records whose field holds one of these values, in the order of the seed file, without _id.

        A value that no record holds gives nothing. Here an empty list is an answer, not an error:
        the caller decides what a missing record means.
        """
        try:
            # {field: {"$in": values}} is a filter: MongoDB only returns the documents whose field is one of the values.
            # $in is one of MongoDB's query operators. list_documents uses the empty filter {}, which matches everything
            query = {field: {"$in": list(values)}}
            documents = list(self.database[collection].find(query, {"_id": 0}).sort("_id", 1))
        except PyMongoError as e:
            raise self._short_error("read", collection, e) from None
        logger.debug(f"MongoDB: {len(documents)} documents found in {collection} for {len(values)} values of {field}")
        return documents

    def replace_documents(self, collection: str, records: List[Dict], unique_fields: Sequence[str] = ()) -> int:
        """Make a collection hold exactly these records, in this order. Return how many were saved.

        unique_fields names the fields, besides id, that no two records may share (the person_id of an HR record).
        """
        # An empty list is a mistake (a seed file with nothing in it), not a way to empty a collection
        if not records:
            logger.error(f"There is nothing to save in the collection {collection}")
            raise ValueError(f"There is nothing to save in the collection {collection}")
        target = self.database[collection]
        try:
            # 1) A unique index on our own id, and on each other field that must be unique. An index is a sorted
            #    list that MongoDB keeps for one field: it finds a value there without reading every document,
            #    and a unique index also refuses two records with the same value.
            #    Creating an index that already exists changes nothing
            for field in ["id", *unique_fields]:
                target.create_index(field, unique=True)
            # 2) Empty the collection: {} is a filter that matches every document
            target.delete_many({})
            # 3) Insert every record. MongoDB wants an _id in each document: here it is the record's position
            #    (1, 2, 3...), so that list_documents can give the records back in this order
            target.insert_many([{"_id": position, **record} for position, record in enumerate(records, start=1)])
        except BulkWriteError as e:
            # The usual cause: two records with the same id. PyMongo's own message holds the whole refused record,
            # so only MongoDB's one-line reason is logged, and it is also the text of the short error
            errors = e.details.get("writeErrors") or [{}]
            text = f"Could not write the MongoDB collection {collection}: {errors[0].get('errmsg', 'no detail')}"
            logger.error(text)
            raise PyMongoError(text) from None
        except PyMongoError as e:
            raise self._short_error("write", collection, e) from None
        return len(records)

    def _short_error(self, action: str, collection: str, error: PyMongoError) -> PyMongoError:
        """Log a MongoDB failure, and return the short error to raise in its place.

        PyMongo's own message is several hundred characters long: it goes to app.log only. The error that leaves this
        class is of the same family (a PyMongoError) and holds one short sentence, so whoever shows the error
        (app.py, the API) shows that sentence.
        """
        text = f"Could not {action} the MongoDB collection {collection} ({type(error).__name__})"
        logger.error(f"{text}. Is the MongoDB service running? The details are in app.log")
        logger.debug(f"MongoDB's own message: {error}")
        return PyMongoError(text)


# The one shared store: every reader imports this, so the whole program uses one MongoDB client
mongo_store = MongoStore()
