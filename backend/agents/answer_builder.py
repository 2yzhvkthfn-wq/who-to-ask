from typing import Dict, List, Optional

from config.constants import MAX_USER_TEXT_LENGTH
from config.settings import settings
from config.texts import (
    ASK_USER_TEXTS,
    CARD_LABELS,
    EVIDENCE_DATE_TEXTS,
    EVIDENCE_TEXTS,
    FIRST_DAY,
    LIST_AND,
    MESSAGE_TEXTS,
    MONTHS,
    NO_SYSTEM,
    NOTE_TEXTS,
    PERSON_TEXTS,
    TITLE_QUOTES,
    WORK_TICKET,
)
from sources import CompanySource, EvidenceSource, HrSource, PeopleSource

from .link_builder import LinkBuilder

# The order in which a sentence says what a person did
KINDS_IN_ORDER = ["wrote", "decided", "assigned", "approved"]


class AnswerBuilder:
    """Turns the final state of the graph into the answer the user sees. Every name, email, and link comes from the data."""

    def __init__(self, evidence: EvidenceSource):
        # 1) The evidence items the graph used: they give the titles of the tickets and pages
        self.evidence = evidence
        # 2) The readers of the directory and of the HR system. Nothing is read here: build() asks MongoDB for
        #    the people of each answer, so a card shows what the directory says at the moment of the question
        self.people_source = PeopleSource()
        self.hr_source = HrSource()
        # 3) The names of the teams, and the systems, read once: both are frozen lists
        company = CompanySource()
        self.team_names = {team["id"]: team["name"] for team in company.list_teams()}
        self.systems = {system["id"]: system for system in company.list_systems()}
        # 4) The two links of a card
        self.link_builder = LinkBuilder()
        # 5) The fixed fake "today", as text like every date in the data
        self.today = settings.TODAY.isoformat()

    def build(self, state: Dict, ask: Optional[Dict] = None, user_name: str = "", user_team: str = "") -> Dict:
        """Return the answer to one question: its status, then the cards, the person card, or the fixed text, and the note.

        ask is the question of a paused run: what the agent asks ("system" or "person") and its choices, as ids.
        user_name and user_team are what the user typed in the two optional boxes: they only go into the
        suggested messages and their links.
        """
        language = state["language"]
        # 1) Ask MongoDB now for the profiles of the people this answer names: one small query
        people = self._read_people(state, ask)

        # 2) The expert road: one card per recommended person. The texts the LLM wrote are found by person.
        #    A missing or an empty text is replaced by a plain one, built from the data
        written = {card["person"]: card for card in state["cards"]}
        sender = {"name": self._one_line(user_name), "team": self._one_line(user_team)}
        # The level of the answer: "exact" when the evidence is about the exact need, and "system" when the people
        # shown only work on the system that the request names. A conversation that was saved before the second
        # level existed has no such key: its answers were all "exact"
        level = state.get("level", "exact")
        cards = [
            self._build_card(entry, written.get(entry["person"], {}), state["question"], language, people, sender, level)
            for entry in state["recommended"]
        ]

        # 3) The person road: the card of one colleague, with the sentence that answers the question
        person_card, sentence = {}, ""
        if state["person_card"]:
            person_card = self._build_person_card(state["person_card"], language, people)
            sentence = self._build_person_sentence(state["person_card"], language, people)

        # 4) A paused run: the agent asks one question, and the user picks one of the choices
        choices = self._build_choices(ask, people) if ask else []

        # 5) The status says which kind of answer this is
        if ask:
            status = "needs_details"
        elif state["road"] in ["not_work", "personal"]:
            status = "off_topic"
        elif cards:
            status = "answered"
        elif person_card:
            status = "person"
        else:
            status = "nobody_found"
        return {
            "status": status,
            # For a refusal: which one it is ("not_work" or "personal")
            "reason": state["road"] if status == "off_topic" else "",
            "language": language,
            # The question of the agent, or the fixed text of a refusal or of "nobody found".
            # For a person card: the sentence that answers the question
            "message": ASK_USER_TEXTS[ask["asks"]][language] if ask else state["message"] or sentence,
            "cards": cards,
            # Only for an answer with cards: "exact", or "system" for the second level (the people who work on the
            # system that the request names, when nothing is about the exact need). The note says it in words
            "level": level if cards else "",
            "person_card": person_card,
            "choices": choices,
            "note": self._build_note(state, people, ask),
            # The same facts as the note, as data. A person who opted out is only counted, never named
            "removed_left": state["removed_left"],
            "removed_opted_out": len(state["removed_opted_out"]),
            # The labels of a card, in the language of the answer and without their colon: the page shows the
            # same words as the terminal, and has no list of its own to keep in step
            "labels": {name: texts[language].rstrip(" :") for name, texts in CARD_LABELS.items() if "{" not in texts["en"]},
        }

    def _read_people(self, state: Dict, ask: Optional[Dict]) -> Dict:
        """Ask MongoDB for the profile of everyone the answer names. Return them by person id."""
        person_ids = [entry["person"] for entry in state["recommended"]] + state["removed_left"]
        card = state["person_card"]
        if card:
            person_ids += [card["subject"], card["person"], card["manager"]]
        if ask and ask["asks"] == "person":
            person_ids += ask["choices"]
        # No empty id, and nobody twice. An answer that names nobody asks MongoDB nothing
        person_ids = [person_id for person_id in dict.fromkeys(person_ids) if person_id]
        if not person_ids:
            return {}
        return {person["id"]: person for person in self.people_source.find_people(person_ids)}

    # ------------------------------------------------------------------
    # The expert road: the cards, and the note about removed people
    # ------------------------------------------------------------------

    def _build_card(
        self, entry: Dict, written: Dict, question: str, language: str, people: Dict, sender: Dict, level: str = "exact"
    ) -> Dict:
        """One card. The LLM's three texts are used when they passed the checks. Everything else comes from the data."""
        person = people[entry["person"]]
        labels = self.evidence.label_pieces(entry["pieces"])
        away_until = self._away_until(person)

        # The suggested message. The code writes its first sentence, with the first name from the directory and
        # what the user typed in the two boxes (an empty box keeps its placeholder). The LLM wrote the middle.
        # The plain middle of the second level never says that the person worked on the topic of the question
        plain_middle = MESSAGE_TEXTS["plain_middle_system" if level == "system" else "plain_middle"][language]
        sentences = [
            MESSAGE_TEXTS["opening"][language].format(
                first_name=person["first_name"],
                user_name=sender["name"] or MESSAGE_TEXTS["your_name"][language],
                user_team=sender["team"] or MESSAGE_TEXTS["your_team"][language],
            ),
            written.get("message") or plain_middle.format(question=question),
        ]
        # Someone who is out of office: one more sentence of the code says that the user has seen it
        if away_until:
            day = self._date_in_words(away_until, language, with_year=False)
            sentences.append(MESSAGE_TEXTS["away"][language].format(date=day))
        sentences.append(MESSAGE_TEXTS["closing"][language])
        message = " ".join(sentences)

        # The subject of the email: the LLM's, or one built from the system that this person's evidence is about
        subject = written.get("subject") or self._plain_subject(entry["pieces"], language)
        links = self.link_builder.build(person["email"], subject, message)

        return {
            "id": person["id"],
            "name": person["name"],
            "job_title": person["job_title"],
            "team": self.team_names.get(person["team"], person["team"]),
            "email": person["email"],
            "out_of_office_until": away_until,
            "out_of_office_text": self._away_text(away_until, language),
            "why": written.get("why") or self._describe(labels, language),
            "evidence": self._show_evidence(labels, language),
            "subject": subject,
            "message": message,
            "teams_link": links["teams"],
            "email_link": links["email"],
        }

    def _plain_subject(self, pieces: List[Dict], language: str) -> str:
        """The subject of the email when the LLM's can't be used: the system of the evidence, then "a question"."""
        # How many pieces of this person's evidence are about each system. A general page is about no system
        counts: Dict[str, int] = {}
        for piece in pieces:
            system_id = self.evidence.get_item(piece["item"])["system"]
            if system_id:
                counts[system_id] = counts.get(system_id, 0) + 1
        if not counts:
            return MESSAGE_TEXTS["subject"][language]
        # The system with the most pieces. Two systems with as many: the first one in the order of the evidence
        system_id = max(counts, key=lambda system: counts[system])
        name = self.systems[system_id]["name"] if system_id in self.systems else system_id
        return MESSAGE_TEXTS["subject_system"][language].format(system=name)

    def _build_note(self, state: Dict, people: Dict, ask: Optional[Dict]) -> str:
        """The note before the cards: what level of answer this is, and who the HR check removed.

        It is built here, in code, so the LLM can't change it.
        """
        language = state["language"]
        pieces_by_person = {entry["person"]: entry["pieces"] for entry in state["ranking"]}
        sentences = []

        # The second level: nothing is about the exact need, and the cards show the people who work on the system
        # that the request names. The note says so first, with the name of the system from the data.
        # Without a card there is nothing to label: the "nobody found" text stands alone
        if state.get("level") == "system" and state["recommended"]:
            names = [self.systems[system_id]["name"] for system_id in state["named_systems"] if system_id in self.systems]
            sentences.append(NOTE_TEXTS["same_system"][language].format(systems=self._join(names, language)))

        # The agent went on without knowing which system was meant (it asks one question per request, and it had
        # already asked one): the note says what was unclear
        if state["road"] == "unclear" and not ask:
            sentences.append(NOTE_TEXTS["unclear_system"][language])

        # Someone who left is named, with what they did. Never a date and never a reason: this note uses neither
        for person_id in state["removed_left"]:
            labels = self.evidence.label_pieces(pieces_by_person.get(person_id, []))
            sentences.append(
                NOTE_TEXTS["left"][language].format(name=people[person_id]["name"], did=self._describe(labels, language))
            )

        # Someone who opted out is never named: the note only counts them
        count = len(state["removed_opted_out"])
        if count == 1:
            sentences.append(NOTE_TEXTS["opted_out_one"][language])
        elif count > 1:
            sentences.append(NOTE_TEXTS["opted_out_many"][language].format(count=count))
        return " ".join(sentences)

    # ------------------------------------------------------------------
    # The person road: the card of one colleague, and the sentence that answers the question
    # ------------------------------------------------------------------

    def _build_person_card(self, card: Dict, language: str, people: Dict) -> Dict:
        """The card of one colleague. What it may show was decided before, in plain code: here it gets its values."""
        person = people[card["person"]]
        # Every person card has the same fields. For someone who left, all of them stay empty except the name:
        # no job title, no contact details, no link, and nothing they worked on
        shown = {
            "id": person["id"],
            "name": person["name"],
            "left": card["left"],
            "job_title": "",
            "team": "",
            "manager": "",
            "email": "",
            "languages": [],
            "work_phone": "",
            "out_of_office_until": "",
            "out_of_office_text": "",
            "work": [],
            "teams_link": "",
            "email_link": "",
        }
        if card["left"]:
            return shown

        # The two links open Teams or the email app for this person, with no message filled in
        links = self.link_builder.build(person["email"])
        # "What does she work on?": her tickets and pages, grouped by system. A general page is about no system
        work = [
            {"system": group["system"] or NO_SYSTEM[language], "items": self._show_evidence(group["items"], language)}
            for group in self.evidence.group_by_system(card["work"])
        ]
        away_until = self._away_until(person)
        shown.update(
            {
                "job_title": person["job_title"],
                "team": self.team_names.get(person["team"], person["team"]),
                "manager": people[card["manager"]]["name"] if card["manager"] else "",
                "email": person["email"],
                "languages": person["languages"],
                # The work phone only shows when the question asks for it
                "work_phone": person["work_phone"] if card["asks"] == "work_phone" else "",
                "out_of_office_until": away_until,
                "out_of_office_text": self._away_text(away_until, language),
                "work": work,
                "teams_link": links["teams"],
                "email_link": links["email"],
            }
        )
        return shown

    def _build_person_sentence(self, card: Dict, language: str, people: Dict) -> str:
        """The sentence that answers a question about a colleague. It names who the question was understood to be about."""
        person = people[card["person"]]
        # The card is someone else's than the person asked about: it is the manager's
        is_manager = card["person"] != card["subject"]
        # The date of "out of office until ...", or "" when the directory marks no absence today or later
        away_until = self._away_until(person)
        if card["left"]:
            # Checked first: someone who left only gets this sentence, whatever was asked
            kind = "manager_left" if is_manager else "left"
        elif card["asks"] == "manager":
            kind = "manager" if is_manager else "no_manager"
        elif card["asks"] == "work_phone":
            kind = "work_phone" if person["work_phone"] else "no_work_phone"
        elif card["asks"] == "work":
            kind = "work" if card["work"] else "no_work"
        elif card["asks"] == "out_of_office":
            # What the directory says, and nothing more: never a reason, and never "available"
            kind = "away" if away_until else "not_away"
        else:
            # A plain card needs no sentence: the card itself names the person
            return ""
        return PERSON_TEXTS[kind][language].format(
            name=people[card["subject"]]["name"],
            manager=person["name"],
            phone=person["work_phone"],
            date=self._date_in_words(away_until, language) if away_until else "",
        )

    # ------------------------------------------------------------------
    # The question of the agent: its choices
    # ------------------------------------------------------------------

    def _build_choices(self, ask: Dict, people: Dict) -> List[Dict]:
        """The choices of the agent's question: for each one its id, its name, and one line that tells it apart."""
        # A question with nothing to choose from (the agent was not waiting for an answer): no choice
        if not ask["choices"]:
            return []
        # Which system: its name, and its one-line description from the data
        if ask["asks"] == "system":
            return [
                {"id": system_id, "name": self.systems[system_id]["name"], "detail": self.systems[system_id]["description"]}
                for system_id in ask["choices"]
            ]

        # Which person: the name, with the job title and the team. Someone who left only shows a name:
        # it is the limit of the person lookup, and only the HR system says who still works at the company
        records = self.hr_source.find_records(ask["choices"])
        employed = {record["person_id"] for record in records if record.get("employment_status") == "employed"}
        choices = []
        for person_id in ask["choices"]:
            person = people[person_id]
            team = self.team_names.get(person["team"], person["team"])
            detail = f"{person['job_title']}, {team}" if person_id in employed else ""
            choices.append({"id": person_id, "name": person["name"], "detail": detail})
        return choices

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _away_until(self, person: Dict) -> str:
        """The date of "Out of office until ...", or "" when the person is not away. The reason is in no data."""
        # The line only shows when the date is today or later
        away_until = person["out_of_office_until"]
        return away_until if away_until >= self.today else ""

    def _away_text(self, away_until: str, language: str) -> str:
        """The line a card shows for someone who is away: "Out of office until 10 November 2026". Not away: no line."""
        if not away_until:
            return ""
        return CARD_LABELS["out_of_office"][language].format(date=self._date_in_words(away_until, language))

    def _date_in_words(self, day: str, language: str, with_year: bool = True) -> str:
        """A date of the data ("2026-11-10") in words, with the day first: "10 November 2026", "10 novembre 2026"."""
        year, month, number = day.split("-")
        # French writes the first day of a month "1er"
        first = FIRST_DAY[language] if int(number) == 1 else str(int(number))
        words = f"{first} {MONTHS[language][int(month) - 1]}"
        return f"{words} {year}" if with_year else words

    def _show_evidence(self, labels: List[Dict], language: str) -> List[Dict]:
        """What an answer shows for each piece of evidence: what the person did, in words, and a date, in words."""
        shown = []
        for label in labels:
            # A page is shown by its title, and a ticket by its id and its summary
            if label["source"] == "Confluence":
                name = TITLE_QUOTES[language].format(title=label["title"])
            else:
                name = WORK_TICKET[language].format(id=label["id"], title=label["title"])
            day = self._date_in_words(label["date"], language)
            shown.append(
                {
                    "id": label["id"],
                    "title": label["title"],
                    "source": label["source"],
                    "kind": label["kind"],
                    # 'wrote "Claims API: Access Guide"', or "handled CLM-212: its summary"
                    "text": EVIDENCE_TEXTS[label["kind"]][language].format(items=name),
                    # "updated 14 October 2026", "resolved 2 October 2026", or "meeting of 13 November 2025"
                    "date_text": EVIDENCE_DATE_TEXTS[label["date_is"]][language].format(date=day),
                }
            )
        return shown

    def _one_line(self, text: str) -> str:
        """What the user typed in a box, on one line with single spaces, and no longer than a box accepts."""
        return " ".join(str(text or "").split())[:MAX_USER_TEXT_LENGTH]

    def _describe(self, labels: List[Dict], language: str) -> str:
        """What a person did, in words: wrote "a page" and handled CLM-212, CLM-245 and CLM-301."""
        parts = []
        for kind in KINDS_IN_ORDER:
            # A page is shown by its title, and a ticket by its id
            names = [
                TITLE_QUOTES[language].format(title=label["title"]) if label["source"] == "Confluence" else label["id"]
                for label in labels
                if label["kind"] == kind
            ]
            if names:
                parts.append(EVIDENCE_TEXTS[kind][language].format(items=self._join(names, language)))
        return self._join(parts, language)

    def _join(self, entries: List[str], language: str) -> str:
        """A list in words: "A", "A and B", or "A, B and C"."""
        if len(entries) <= 1:
            return "".join(entries)
        return f"{', '.join(entries[:-1])} {LIST_AND[language]} {entries[-1]}"
