import re
import unicodedata
from typing import Dict, List, Tuple

from config.constants import MAX_STEP_WORDS_LENGTH
from config.texts import STEP_NOUNS, STEP_TEXTS
from sources import PeopleSource


class StepWriter:
    """Writes the grey step lines: one short line per step of the graph, built from counts. Plain code, never the LLM.

    A line never names a person. The only words of the user that a line can repeat are the search words,
    and it leaves them out when one of them is the name of someone in the directory.
    """

    def __init__(self):
        # The reader of the directory. Nothing is read here: a search line asks MongoDB for the names at each question
        self.people_source = PeopleSource()
        # The method that writes the line of each step, by the name of its node
        self.writers = {
            "understand": self._understand,
            "failsafe": self._failsafe,
            "ask_user": self._ask_user,
            "search": self._search,
            "verify": self._verify,
            "rewrite": self._rewrite,
            "same_system": self._same_system,
            "rank": self._rank,
            "check_hr": self._check_hr,
            "write_cards": self._write_cards,
            "nobody_found": self._nobody_found,
            "find_person": self._find_person,
            "person_card": self._person_card,
        }

    def write(self, step: str, facts: Dict) -> str:
        """Return the line of one step. step is the name of the node, and facts holds the counts and labels of its run."""
        return self.writers[step](facts)

    # ------------------------------------------------------------------
    # One method per step. Each one says which facts it reads
    # ------------------------------------------------------------------

    def _understand(self, facts: Dict) -> str:
        """facts: road, question_type, systems (how many a general word fits), answered (the user just picked a choice).

        And no_topic, when the request looks for an expert and names no topic at all.
        """
        if facts["road"] == "expert" and facts.get("no_topic"):
            what = STEP_TEXTS["understand_no_topic"]
        elif facts["road"] == "expert":
            what = STEP_TEXTS[f"understand_{facts['question_type']}"]
        elif facts["road"] == "unclear":
            what = STEP_TEXTS["understand_unclear"].format(count=facts["systems"])
        else:
            what = STEP_TEXTS[f"understand_{facts['road']}"]
        return STEP_TEXTS["read_again" if facts["answered"] else "read"].format(what=what)

    def _failsafe(self, facts: Dict) -> str:
        """facts: nothing."""
        return STEP_TEXTS["failsafe"]

    def _ask_user(self, facts: Dict) -> str:
        """facts: nothing. The line is written when the user has answered, and the run goes on."""
        return STEP_TEXTS["ask_user"]

    def _search(self, facts: Dict) -> str:
        """facts: words (the search words), found (how many results), retry (the second search of a question)."""
        shown = self._words_to_show(facts["words"])
        words = STEP_TEXTS["search_words"].format(words=shown) if shown else ""
        text = STEP_TEXTS["search_again" if facts["retry"] else "search"]
        return text.format(words=words, results=self._count("result", facts["found"]))

    def _verify(self, facts: Dict) -> str:
        """facts: checked (how many results were read), kept (how many are about the question)."""
        if not facts["checked"]:
            return STEP_TEXTS["verify_nothing_new"]
        kept = self._count("kept", facts["kept"]) if facts["kept"] else STEP_NOUNS["kept_none"]
        return STEP_TEXTS["verify"].format(results=self._count("result", facts["checked"]), kept=kept)

    def _rewrite(self, facts: Dict) -> str:
        """facts: nothing."""
        return STEP_TEXTS["rewrite"]

    def _same_system(self, facts: Dict) -> str:
        """facts: systems (the names of the systems that the question names), items (how many tickets and pages they have).

        The names are names of systems, from the data: a step line never names a person.
        """
        return STEP_TEXTS["same_system"].format(
            items=self._count("item", facts["items"]), systems=", ".join(facts["systems"])
        )

    def _rank(self, facts: Dict) -> str:
        """facts: people (how many people are behind the evidence)."""
        return STEP_TEXTS["rank"].format(people=self._count("person", facts["people"]))

    def _check_hr(self, facts: Dict) -> str:
        """facts: left and opted_out (how many people were removed for each reason). Counts only: never a name."""
        removed = []
        if facts["left"]:
            removed.append(STEP_TEXTS["removed_left"].format(people=self._count("person", facts["left"])))
        if facts["opted_out"]:
            removed.append(STEP_TEXTS["removed_opted_out"].format(people=self._count("person", facts["opted_out"])))
        return STEP_TEXTS["check_hr"].format(removed=", ".join(removed) or STEP_TEXTS["removed_nobody"])

    def _write_cards(self, facts: Dict) -> str:
        """facts: people (how many cards were written)."""
        return STEP_TEXTS["write_cards"].format(cards=self._count("card", facts["people"]))

    def _nobody_found(self, facts: Dict) -> str:
        """facts: kind (which "nobody found" text the answer gets)."""
        if facts["kind"] == "no_decision":
            return STEP_TEXTS["nobody_found_decision"]
        if facts["kind"] == "no_topic":
            return STEP_TEXTS["nobody_found_no_topic"]
        if facts["kind"] in ["no_person", "no_one_meant", "several_people"]:
            return STEP_TEXTS["nobody_found_person"]
        return STEP_TEXTS["nobody_found"]

    def _find_person(self, facts: Dict) -> str:
        """facts: matches (how many people), named (the question gave a name), picked (the user just picked someone)."""
        if facts["picked"]:
            return STEP_TEXTS["find_person_picked"]
        if not facts["named"]:
            # "her", "him", or "them": the most recent person shown, when there is one
            return STEP_TEXTS["find_person_shown" if facts["matches"] else "find_person_nobody_shown"]
        matches = self._count("match", facts["matches"]) if facts["matches"] else STEP_NOUNS["match_none"]
        return STEP_TEXTS["find_person"].format(matches=matches)

    def _person_card(self, facts: Dict) -> str:
        """facts: nothing."""
        return STEP_TEXTS["person_card"]

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _count(self, noun: str, count: int) -> str:
        """A count with its noun: "1 result", or "14 results"."""
        forms: Tuple[str, str] = STEP_NOUNS[noun]
        return forms[0] if count == 1 else forms[1].format(count=count)

    def _words_to_show(self, search_words: List[str]) -> str:
        """The search words as a line may show them: "Claims API", "access". Or nothing, when they are not safe to show.

        The search words are the user's own words, so one of them can be the name of a colleague. A step line
        never names a person: when a word is the first name or the last name of anyone in the directory,
        the line shows no word at all.
        """
        shown = ", ".join(f'"{words}"' for words in search_words)
        if not shown or len(shown) > MAX_STEP_WORDS_LENGTH:
            return ""
        # Ask MongoDB now for the names of the directory, so someone who joined a minute ago is known too
        names = {
            part
            for person in self.people_source.list_people()
            for name in (person["first_name"], person["last_name"])
            for part in self._words(name)
        }
        if any(word in names for word in self._words(" ".join(search_words))):
            return ""
        return shown

    def _words(self, text: str) -> List[str]:
        """The words of a text, in lower case and without accents: "Marc-André" gives marc and andre."""
        decomposed = unicodedata.normalize("NFKD", text.lower())
        plain = "".join(letter for letter in decomposed if not unicodedata.combining(letter))
        # A word is a run of letters, of any alphabet
        return re.findall(r"[^\W\d_]+", plain)
