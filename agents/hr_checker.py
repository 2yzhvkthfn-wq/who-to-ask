from typing import Dict, List

from config.constants import MAX_CARDS
from sources import HrSource, PeopleSource


class HrChecker:
    """Removes the people who left the company or opted out of being found. Plain code, never the LLM."""

    def __init__(self):
        # The two readers of the check. Nothing is read here: check() asks MongoDB at each question
        self.people_source = PeopleSource()
        self.hr_source = HrSource()

    def check(self, ranking: List[Dict]) -> Dict:
        """Split a ranking into the people to recommend (up to three), and the people removed, by reason."""
        if not ranking:
            return {"recommended": [], "removed_left": [], "removed_opted_out": []}

        # 1) Ask MongoDB now, for the people of this ranking only: their profile (who opted out) and their HR record
        #    (who left). Nothing is kept from one question to the next, so someone who opts out or leaves is removed
        #    at the next question, even when the app has been running for hours.
        #    If MongoDB does not answer, the error stops the answer: this check never works from an older copy
        person_ids = [entry["person"] for entry in ranking]
        profiles = {person["id"]: person for person in self.people_source.find_people(person_ids)}
        records = {record["person_id"]: record for record in self.hr_source.find_records(person_ids)}

        # 2) Sort the people of the ranking, in its order
        recommended, removed_left, removed_opted_out = [], [], []
        for entry in ranking:
            person_id = entry["person"]
            if not self._is_discoverable(profiles.get(person_id, {})):
                # Opt-out is checked first: someone who opted out is never named, even after they left
                removed_opted_out.append(person_id)
            elif not self._is_employed(records.get(person_id, {})):
                removed_left.append(person_id)
            else:
                recommended.append(entry)
        return {
            "recommended": recommended[:MAX_CARDS],
            "removed_left": removed_left,
            "removed_opted_out": removed_opted_out,
        }

    def _is_employed(self, record: Dict) -> bool:
        """True if the HR file says the person still works at the company. No HR record means no."""
        return record.get("employment_status") == "employed"

    def _is_discoverable(self, profile: Dict) -> bool:
        """True if the directory says the person can be found. Someone the directory doesn't know can't."""
        return profile.get("discoverable") is True
