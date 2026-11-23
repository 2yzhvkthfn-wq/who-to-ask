from typing import Dict, List

# The ranking rules of PROJECT.md, as a table: for each type of question, the kinds of evidence that count first.
# "wrote" and "decided" come from Confluence, "assigned" and "approved" from Jira
FIRST_KINDS = {
    "help": ["wrote", "decided"],  # "Who can help me with X?": Confluence counts first, and Jira second
    "did": ["assigned", "approved"],  # "Who fixed X?": Jira counts first, and Confluence second
    "decided": ["decided"],  # "Who decided X?": only a decision in meeting minutes counts
}
# For these types of question, nothing counts second: evidence of another kind counts for nobody
ONLY_FIRST_KINDS_COUNT = ["decided"]


class Ranker:
    """Finds the people behind the evidence, and orders them with the ranking rules."""

    def rank(self, pieces: List[Dict], question_type: str) -> List[Dict]:
        """Return one entry per person, best first. A piece says who did what, on which ticket or page, and when."""
        # 1) Keep the pieces that count for this type of question, and group them by person
        by_person: Dict[str, List[Dict]] = {}
        for piece in self.pieces_that_count(pieces, question_type):
            by_person.setdefault(piece["person"], []).append(piece)

        # 2) One entry per person, with what the rules compare
        first_kinds = FIRST_KINDS[question_type]
        entries = []
        for person_id, person_pieces in by_person.items():
            entries.append(
                {
                    "person": person_id,
                    "pieces": person_pieces,
                    "first": any(piece["kind"] in first_kinds for piece in person_pieces),
                    "count": len(person_pieces),
                    "latest": max(piece["date"] for piece in person_pieces),
                }
            )

        # 3) Sort from the last rule to the first: the lower id, the most recent piece, more pieces, the first source.
        #    Python keeps the earlier order when two entries are equal, so the last sort is the rule that counts most
        entries.sort(key=lambda entry: entry["person"])
        entries.sort(key=lambda entry: entry["latest"], reverse=True)
        entries.sort(key=lambda entry: entry["count"], reverse=True)
        entries.sort(key=lambda entry: not entry["first"])
        return entries

    def pieces_that_count(self, pieces: List[Dict], question_type: str) -> List[Dict]:
        """Return the pieces that count for this type of question, in the order they were given."""
        if question_type not in FIRST_KINDS:
            raise ValueError(f"Unknown question type: {question_type}")

        # "decided": only a decision counts. A ticket or a doc counts for nobody, even for the person who decided
        if question_type in ONLY_FIRST_KINDS_COUNT:
            return [piece for piece in pieces if piece["kind"] in FIRST_KINDS[question_type]]

        # "help" and "did": every piece counts. The type only changes which source comes first
        return list(pieces)
