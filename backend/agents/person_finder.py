import re
import unicodedata
from typing import Dict, List

from sources import PeopleSource
from utils.logging import logger


class PersonFinder:
    """Finds who a question about a colleague means: it looks the name up in the directory. Plain code, never the LLM."""

    def __init__(self):
        # The reader of the directory. Nothing is read here: find() asks MongoDB at each question
        self.people_source = PeopleSource()

    def find(self, name: str, shown_people: List[str]) -> Dict:
        """Return the people a name can mean, as ids. One id: the person is found. None or several: the graph decides.

        name is what the user wrote, or "" when the question only says "her", "him", or "them".
        shown_people holds the ids of the people the conversation has already shown, the most recent first.
        """
        # 1) Ask MongoDB now for the directory, so a profile that changed a minute ago is the one that is read.
        #    If MongoDB does not answer, the error stops the answer: "no one by that name" must mean that we looked
        people = self.people_source.list_people()
        by_id = {person["id"]: person for person in people}
        # The people already shown, in their order. Someone the directory no longer knows is left out
        shown = [by_id[person_id] for person_id in shown_people if person_id in by_id]

        words = self._words(name)
        if not name.strip():
            # 2) No name at all: "her", "him", or "them" means the first person shown. The directory has no gender
            #    field, so the agent never guesses from a first name
            matches = shown[:1]
        elif not words:
            # 3) Something was written as a name, but no letter is in it ("42", "?"): it is nobody's name.
            #    It is never read as "her": the answer would then be about someone the user did not mean
            matches = []
        else:
            # 4) A name: the people already shown come first, and the first of them with this name is the one.
            #    After the cards, "Sophie" means the Sophie on the card, not every Sophie of the company
            matches = [person for person in shown if self._has_name(person, words)][:1]
            # 5) Nobody shown has this name: the whole directory. Several people can have it
            if not matches:
                matches = [person for person in people if self._has_name(person, words)]

        # The log holds ids and numbers only: the name is what the user typed, and it may be anyone's
        logger.info(
            f"Find person: {len(matches)} match(es) for {'a name' if name.strip() else 'a question with no name'}, "
            f"with {len(shown)} people already shown in the conversation"
        )
        return {"matches": [person["id"] for person in matches]}

    def _has_name(self, person: Dict, words: List[str]) -> bool:
        """True when every word the user wrote is a word of this person's name. "sophie" fits every Sophie."""
        name_words = self._words(f"{person['first_name']} {person['last_name']}")
        return all(word in name_words for word in words)

    def _words(self, text: str) -> List[str]:
        """The words of a name, in lower case and without accents: "Marc-André Gagnon's" gives marc, andre, gagnon."""
        decomposed = unicodedata.normalize("NFKD", text.lower())
        plain = "".join(letter for letter in decomposed if not unicodedata.combining(letter))
        # "Sophie's" is Sophie: the 's is dropped before the text is cut into words
        plain = re.sub(r"['’]s\b", "", plain)
        # A word is a run of letters, of any alphabet: [^\W\d_] means "a letter", where [a-z] would only know
        # the 26 of English. A name written in another alphabet then has words, and they are nobody's here
        return re.findall(r"[^\W\d_]+", plain)
