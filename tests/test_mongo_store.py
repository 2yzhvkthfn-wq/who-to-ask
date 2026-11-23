"""Free tests of MongoStore (the class that talks to MongoDB), of the seed script, and of the readers. No OpenAI calls.

They write to a throwaway database, who_to_ask_test, which is dropped after each test (the store helper of conftest.py).
The real database is never written here: only the seed script does that.
"""

import pytest
from pydantic import SecretStr
from pymongo.errors import BulkWriteError, PyMongoError

from config.settings import settings
from scripts import seed_mongodb
from sources import HrSource, MongoStore, PeopleSource, SeedFiles

# Tiny made-up records. They are not sorted by id on purpose: the order of the list is what must be kept
RECORDS = [
    {"id": "b2", "name": "Second by id, first in the list", "labels": ["x", "y"], "open": True},
    {"id": "a1", "name": "First by id, second in the list", "labels": [], "open": False},
    {"id": "c3", "name": "Third", "comments": [{"author": "p001", "text": "Ça marche à Montréal"}]},
]


# ----------------------------------------------------------------------
# Saving and reading: the same records, in the same order
# ----------------------------------------------------------------------


def test_records_come_back_as_they_were_saved(store):
    """What is saved is what is read: the same fields, the same values, and the order of the list, not the order of the ids."""
    saved = store.replace_documents("things", RECORDS)

    assert saved == 3
    assert store.list_documents("things") == RECORDS
    # MongoDB's own _id is not in what the readers get, and saving did not add it to the records either
    assert all("_id" not in record for record in store.list_documents("things"))
    assert all("_id" not in record for record in RECORDS)


def test_the_id_of_mongodb_is_the_position_in_the_list(store):
    """Inside MongoDB, _id is 1, 2, 3...: it is what lets a reader ask for the records in the order of the file."""
    store.replace_documents("things", RECORDS)
    stored = list(store.database["things"].find().sort("_id", 1))

    assert [document["_id"] for document in stored] == [1, 2, 3]
    assert [document["id"] for document in stored] == ["b2", "a1", "c3"]


def test_saving_twice_gives_the_same_collection(store):
    """The seed can run as often as needed: the second run leaves exactly what the first one left."""
    store.replace_documents("things", RECORDS)
    store.replace_documents("things", RECORDS)

    assert store.list_documents("things") == RECORDS
    assert store.database["things"].count_documents({}) == 3


def test_saving_removes_what_is_no_longer_in_the_list(store):
    """A record that left the file leaves the collection too: the collection is a copy, not a pile."""
    store.replace_documents("things", RECORDS)
    store.replace_documents("things", RECORDS[:1])

    assert store.list_documents("things") == RECORDS[:1]


def test_two_records_with_the_same_id_are_refused(store):
    """The unique index on id: MongoDB itself refuses a second record with an id it already holds."""
    twice = [RECORDS[0], {**RECORDS[1], "id": RECORDS[0]["id"]}]
    with pytest.raises(PyMongoError, match="duplicate key") as error:
        store.replace_documents("things", twice)

    # The error that leaves the store is a short one: it names the id that is there twice, and it holds no record.
    # PyMongo's own error (a BulkWriteError) writes the whole refused record in its text
    assert not isinstance(error.value, BulkWriteError)
    assert 'id: "b2"' in str(error.value)
    assert RECORDS[1]["name"] not in str(error.value)


def test_another_field_can_be_unique_too(store):
    """A second unique index, on a field that the caller names: two HR records for one person are refused."""
    records = [{"id": "hr901", "person_id": "p901"}, {"id": "hr902", "person_id": "p901"}]

    # Without the index, MongoDB accepts them: their ids differ, and MongoDB knows nothing about person_id
    assert store.replace_documents("records_without_index", records) == 2
    # With the index, the second record is refused, and the error names the person who is there twice
    with pytest.raises(PyMongoError, match="duplicate key") as error:
        store.replace_documents("records_with_index", records, unique_fields=["person_id"])
    assert 'person_id: "p901"' in str(error.value)


def test_saving_nothing_is_refused(store):
    """An empty list is a mistake, not a way to empty a collection."""
    with pytest.raises(ValueError):
        store.replace_documents("things", [])


# ----------------------------------------------------------------------
# Reading some records only: a query with a filter
# ----------------------------------------------------------------------


def test_a_filter_returns_only_the_records_asked_for(store):
    """find_documents returns the records whose field holds one of the values, without MongoDB's own _id."""
    store.replace_documents("things", RECORDS)

    # The values are given in another order than the list: the answer keeps the order of the list (b2, then a1)
    assert store.find_documents("things", "id", ["a1", "b2"]) == [RECORDS[0], RECORDS[1]]
    # Any field can be the filter, not only the id
    assert store.find_documents("things", "name", ["Third"]) == [RECORDS[2]]


def test_a_filter_that_matches_nothing_gives_an_empty_list(store):
    """A value that no record holds is not an error: the caller decides what a missing record means."""
    store.replace_documents("things", RECORDS)

    assert store.find_documents("things", "id", ["zz9"]) == []
    assert store.find_documents("things", "id", ["zz9", "c3"]) == [RECORDS[2]]
    assert store.find_documents("things", "id", []) == []


# ----------------------------------------------------------------------
# When MongoDB can't answer: an error, never an empty list
# ----------------------------------------------------------------------


def test_an_empty_collection_is_an_error(store):
    """A collection with nothing in it means that the seed has not run. The error says which command to run."""
    with pytest.raises(RuntimeError, match="scripts.seed_mongodb"):
        store.list_documents("never_filled")


def test_mongodb_stopped_is_an_error(monkeypatch):
    """Nothing answers at the address: reading raises an error after the timeout, instead of returning nothing."""
    # Port 1 of this computer: no MongoDB listens there. A short timeout keeps the test fast
    monkeypatch.setattr(settings, "MONGODB_URI", SecretStr("mongodb://localhost:1"))
    monkeypatch.setattr("sources.mongo_store.MONGODB_TIMEOUT_MS", 300)
    store = MongoStore()
    with pytest.raises(PyMongoError) as error:
        store.list_documents("people")
    # The error that leaves the store is one short sentence. PyMongo's own text is several hundred characters long:
    # it is in app.log only, so that app.py and the API never show it
    assert str(error.value) == "Could not read the MongoDB collection people (ServerSelectionTimeoutError)"

    # A query with a filter fails in the same way: "no answer" is never read as "no such record"
    with pytest.raises(PyMongoError) as error:
        store.find_documents("people", "id", ["p001"])
    assert str(error.value) == "Could not read the MongoDB collection people (ServerSelectionTimeoutError)"

    # And so does a write
    with pytest.raises(PyMongoError) as error:
        store.replace_documents("people", RECORDS)
    assert str(error.value) == "Could not write the MongoDB collection people (ServerSelectionTimeoutError)"
    store.client.close()


@pytest.mark.parametrize(
    "address",
    [
        # No mongodb:// at the start: PyMongo would take it as the name of a computer
        "my-secret-password-is-not-an-address",
        # A password with an @ that is not written as %40: PyMongo refuses the address
        "mongodb://someone:my-secret-p@ssword@localhost:27017",
    ],
)
def test_a_wrong_address_never_shows_its_value(monkeypatch, address):
    """An address that is not a MongoDB address stops the program, and the error does not repeat it."""
    monkeypatch.setattr(settings, "MONGODB_URI", SecretStr(address))
    with pytest.raises(RuntimeError) as error:
        MongoStore()
    assert "my-secret" not in str(error.value)


# ----------------------------------------------------------------------
# The seed script, and the readers
# ----------------------------------------------------------------------


def test_the_seed_copies_every_file_of_the_data_folder(store, monkeypatch):
    """The seed script, run on the throwaway database: each collection holds exactly what its file holds."""
    monkeypatch.setattr(seed_mongodb, "mongo_store", store)
    seed_mongodb.main()

    files = SeedFiles().read()
    assert sorted(files) == ["hr_records", "pages", "people", "systems", "teams", "tickets"]
    for name, records in files.items():
        assert store.list_documents(name) == records


def test_the_seed_gives_the_hr_records_a_unique_index_on_person_id(store, monkeypatch):
    """After the seed, MongoDB keeps two unique indexes for the HR records: on id, and on person_id.

    The HR check asks for the records of a few people by person_id: with this index, MongoDB goes straight to them.
    And MongoDB itself now refuses two HR records for one person.
    """
    monkeypatch.setattr(seed_mongodb, "mongo_store", store)
    seed_mongodb.main()

    def unique_fields(collection: str) -> list:
        # index_information() describes each index of a collection: the field it sorts, and whether it is unique
        indexes = store.database[collection].index_information().values()
        return sorted(index["key"][0][0] for index in indexes if index.get("unique"))

    assert unique_fields("hr_records") == ["id", "person_id"]
    # The other collections keep their one unique index, on id
    for collection in ["teams", "systems", "people", "tickets", "pages"]:
        assert unique_fields(collection) == ["id"]


def test_a_reader_returns_what_mongodb_holds(store, monkeypatch):
    """The readers really read MongoDB: a made-up directory in the throwaway database is what PeopleSource returns."""
    made_up = [{"id": "p902", "name": "Made Up"}, {"id": "p901", "name": "Also Made Up"}]
    store.replace_documents("people", made_up)
    # PeopleSource uses the shared store of its module: for this test, it is the throwaway one
    monkeypatch.setattr("sources.people.mongo_store", store)

    assert PeopleSource().list_people() == made_up


def test_a_reader_asks_mongodb_at_each_call(store, monkeypatch):
    """A reader keeps no copy: after a change in MongoDB, the same reader returns the new value."""
    store.replace_documents("people", [{"id": "p901", "name": "Made Up", "job_title": "Developer"}])
    monkeypatch.setattr("sources.people.mongo_store", store)
    reader = PeopleSource()
    assert reader.list_people()[0]["job_title"] == "Developer"

    # One field of one document changes, as if someone had edited it in Compass
    store.database["people"].update_one({"id": "p901"}, {"$set": {"job_title": "Team Lead"}})

    assert reader.list_people()[0]["job_title"] == "Team Lead"


def test_the_readers_find_the_records_of_some_people_only(store, monkeypatch):
    """find_people and find_records return what MongoDB holds about the people asked for, and nothing about the others."""
    profiles = [{"id": "p901", "name": "Made Up"}, {"id": "p902", "name": "Also Made Up"}]
    hr_records = [
        {"id": "hr901", "person_id": "p901", "employment_status": "employed"},
        {"id": "hr902", "person_id": "p902", "employment_status": "left"},
    ]
    store.replace_documents("people", profiles)
    store.replace_documents("hr_records", hr_records)
    monkeypatch.setattr("sources.people.mongo_store", store)
    monkeypatch.setattr("sources.hr.mongo_store", store)

    # p999 is in neither collection: it gives no profile and no record, and no error
    assert PeopleSource().find_people(["p902", "p999"]) == [profiles[1]]
    assert HrSource().find_records(["p902", "p999"]) == [hr_records[1]]
