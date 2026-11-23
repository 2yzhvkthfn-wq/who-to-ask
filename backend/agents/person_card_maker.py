from typing import Dict

from config.constants import MAX_WORK_ITEMS
from sources import EvidenceSource, HrSource, PeopleSource
from utils.logging import logger


class PersonCardMaker:
    """Decides what an answer may show about one colleague, with the limits of the person lookup. Plain code, never the LLM."""

    def __init__(self, evidence: EvidenceSource):
        # 1) The two readers of the limits. Nothing is read here: make() asks MongoDB at each question
        self.people_source = PeopleSource()
        self.hr_source = HrSource()
        # 2) The evidence items of the expert road: "What does she work on?" reads them from the person's side
        self.evidence = evidence

    def make(self, person_id: str, asks: str) -> Dict:
        """Return what the answer may show about this person, as ids and labels. The answer gets the names later.

        asks is what the question wants: "card", "manager", "work_phone", "work", or "out_of_office". The result holds:
        subject (who the question is about), person (whose card is shown: the subject, or the subject's manager),
        asks, left (True: only the name may be shown), manager (who the card names as manager, or ""),
        and work (for "work": the person's pieces of evidence, the most recent first).
        An empty dict means that the directory no longer knows this person.
        """
        # 1) Ask MongoDB now, for this person only: the profile, and the HR record (who left). Nothing is kept
        #    from one question to the next. If MongoDB does not answer, the error stops the answer
        subject = self._look_up(person_id)
        if not subject["profile"]:
            return {}
        card = {"subject": person_id, "person": person_id, "asks": asks, "left": False, "manager": "", "work": []}

        # 2) Someone who left: the answer only says so, whatever was asked. This is checked before everything else,
        #    so no later step can show a field, a manager, or a ticket of someone who left
        if not subject["employed"]:
            logger.info(f"Person card: {person_id} left the company, so the answer only says so")
            return {**card, "left": True}

        # 3) "Who is X's manager?": the card is the manager's. Without a manager, it stays the card of X.
        #    A manager who opted out of being found is named like any other, with their card:
        #    opting out hides someone's work, never their place in the directory
        profile = subject["profile"]
        if asks == "manager" and profile["manager"]:
            manager = self._look_up(profile["manager"])
            if manager["profile"] and not manager["employed"]:
                # The manager left: the answer names them and says so, with no card
                logger.info(f"Person card: the manager of {person_id} left the company, so the answer only says so")
                return {**card, "person": profile["manager"], "left": True}
            if manager["profile"]:
                card["person"] = profile["manager"]
                profile = manager["profile"]

        # 4) The manager line of the card: it only names someone who still works at the company
        if profile["manager"]:
            named = self._look_up(profile["manager"])
            if named["profile"] and named["employed"]:
                card["manager"] = profile["manager"]

        # 5) "What does X work on?": the tickets and pages that count for X, the most recent ones.
        #    Someone who opted out of being found only shows the directory fields: the list stays empty
        if asks == "work" and profile.get("discoverable") is True:
            card["work"] = self.evidence.list_pieces_of(person_id)[:MAX_WORK_ITEMS]

        logger.info(
            f"Person card: the card of {card['person']} answers a \"{asks}\" question about {person_id}"
            + (f", with {len(card['work'])} tickets and pages" if asks == "work" else "")
        )
        return card

    def _look_up(self, person_id: str) -> Dict:
        """Ask MongoDB about one person: the profile ({} if the directory doesn't know them), and whether they work here."""
        profiles = self.people_source.find_people([person_id])
        records = self.hr_source.find_records([person_id])
        return {
            "profile": profiles[0] if profiles else {},
            # Only the HR system says who still works at the company. No HR record means no
            "employed": bool(records) and records[0].get("employment_status") == "employed",
        }
