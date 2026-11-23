import json
from typing import Dict, List

from agents.hr_checker import HrChecker
from agents.ranker import FIRST_KINDS, ONLY_FIRST_KINDS_COUNT, Ranker
from config.settings import PROJECT_ROOT, settings
from sources import CompanySource, EvidenceSource, HrSource, PageSource, PeopleSource, TicketSource
from utils.logging import logger

# How the report says each ranking rule in words. The rules themselves live in agents/ranker.py
RULE_IN_WORDS = {
    "help": "Confluence counts first, and Jira second",
    "did": "Jira counts first, and Confluence second",
    "decided": "only a decision in meeting minutes counts. Tickets and docs count for nobody",
}
# The kinds of evidence that go in the "Confluence" column of a table. The other kinds go in the "Jira" column
CONFLUENCE_KINDS = ["wrote", "decided"]
# The scenarios of PROJECT.md: each one needs at least one case
SCENARIO_NUMBERS = range(1, 16)


class ScenarioChecker:
    """Checks that every demo scenario exists in the data, and writes a report that shows why."""

    def __init__(self):
        # 1) Read the data through the same readers the agent will use, with quick lookups by id
        self.systems = {system["id"]: system for system in CompanySource().list_systems()}
        self.people = {person["id"]: person for person in PeopleSource().list_people()}
        self.hr_by_person = {record["person_id"]: record for record in HrSource().list_records()}
        self.tickets = {ticket["id"]: ticket for ticket in TicketSource().list_tickets()}
        self.pages = {page["id"]: page for page in PageSource().list_pages()}

        # 2) The agent's own classes: what counts as evidence, the ranking rules, and the HR check.
        #    The check calls them instead of copying them, so each rule is written in one place
        self.evidence = EvidenceSource()
        self.ranker = Ranker()
        self.hr_checker = HrChecker()

        # 3) Read the scenario cases
        self.cases = self._read_cases()

        # 4) The fixed fake "today", as text like every date in the data
        self.today = settings.TODAY.isoformat()
        self.problems: List[str] = []
        self.lines: List[str] = []
        self.expected_by_case: Dict[str, Dict] = {}
        self.cards_by_case: Dict[str, List[str]] = {}
        self.credited_by_case: Dict[str, List[str]] = {}

    def check(self) -> Dict:
        """Check every case in scenarios.json. Return the problems and a Markdown report, one section per case."""
        self.problems, self.lines = [], []
        self.expected_by_case, self.cards_by_case, self.credited_by_case = {}, {}, {}
        self._write_intro()
        for case in self.cases:
            self._check_case(case)

        # Every scenario of PROJECT.md must have at least one case
        covered = {case.get("scenario") for case in self.cases}
        for number in SCENARIO_NUMBERS:
            if number not in covered:
                self._problem("scenarios.json", f"scenario {number} has no case")
        return {"problems": self.problems, "report": "\n".join(self.lines).rstrip("\n") + "\n"}

    # ------------------------------------------------------------------
    # One case, one turn at a time
    # ------------------------------------------------------------------

    def _check_case(self, case: Dict) -> None:
        """Check each turn of one case, and write its section of the report."""
        case_id = case.get("id", "?")
        where = f"scenarios.json {case_id}"
        title = f"Scenario {case.get('scenario')}" if case.get("scenario") else "The demo video path"
        self._write(f"## {title} (case `{case_id}`, checked at {case.get('checked_at')})")
        self._write("")
        self._write(f"What it tests: {case.get('tests')}")
        self._write("")

        handlers = {
            "answered": self._check_answered,
            "nobody_found": self._check_nobody_found,
            "needs_details": self._check_needs_details,
            "person": self._check_person,
            "off_topic": self._check_off_topic,
        }
        for turn in case.get("turns", []):
            self._write(f"**Question:** \"{turn.get('question')}\"")
            self._write("")

            # "same_as" reuses what another case expects, so the long lists are written once
            expected = turn.get("expected", {})
            reused = expected.get("same_as")
            if reused:
                if reused not in self.expected_by_case:
                    self._problem(where, f"same_as points to an unknown or later case: {reused}")
                    continue
                expected = self.expected_by_case[reused]
                self._write(f"Expected: the same as in case `{reused}`.")

            handler = handlers.get(expected.get("status"))
            if handler is None:
                self._problem(where, f"unknown status {expected.get('status')}")
                continue
            handler(where, case_id, expected, bool(reused))
            self.expected_by_case[case_id] = expected
            self._write("")

    def _check_answered(self, where: str, case_id: str, expected: Dict, brief: bool) -> None:
        """An expert answer: the ranking rules, applied to the evidence, must give the expected cards."""
        question_type = expected.get("question_type")
        evidence = expected.get("evidence", [])
        optional = expected.get("optional_evidence", [])
        near_misses = expected.get("near_misses", [])
        if question_type not in FIRST_KINDS:
            self._problem(where, f"unknown question_type {question_type}")
            return

        # 1) Every id must be a real ticket or page, and every piece of evidence must lead to someone
        near_miss_ids = [near_miss.get("id") for near_miss in near_misses]
        no_person = expected.get("no_person", [])
        no_person_ids = [item.get("id") for item in no_person]
        unknown = [item for item in evidence + optional + near_miss_ids + no_person_ids if not self._exists(item)]
        if unknown:
            self._problem(where, f"unknown tickets or pages: {unknown}")
            return
        for item in evidence + optional:
            if not self._pieces_of(item):
                self._problem(where, f"{item} is listed as evidence, but it leads to nobody")
        # "no_person" items are about the question, but nobody on them counts: search drops them before verify
        for item in no_person_ids:
            if self._pieces_of(item):
                self._problem(where, f"{item} is listed as leading to nobody, but it counts for someone")
        for item in near_miss_ids:
            if item in evidence + optional:
                self._problem(where, f"{item} is both evidence and a near-miss")

        # 2) Rank the evidence, apply the HR check, and compare with what the scenario expects
        ranked = self._rank(evidence, question_type)
        result = self._apply_hr(ranked)
        cards = result["cards"]
        self.cards_by_case[case_id] = cards
        self.credited_by_case[case_id] = [entry["person"] for entry in ranked]
        self._compare(where, expected, result, strict=True)

        # 3) A French question needs at least one French page in its evidence
        if expected.get("language") == "fr" and not any(
            self.pages.get(item, {}).get("language") == "fr" for item in evidence
        ):
            self._problem(where, "a French scenario needs at least one French page in its evidence")

        # 4) The out-of-office line: shown on a card only when the date is today or later
        shown = {
            person_id: self.people[person_id]["out_of_office_until"]
            for person_id in cards
            if self.people[person_id]["out_of_office_until"] >= self.today
        }
        if "out_of_office" in expected and shown != expected["out_of_office"]:
            self._problem(where, f"out of office on the cards: expected {expected['out_of_office']}, found {shown}")

        # 5) The scenario must still hold if verify also keeps the optional evidence
        with_optional = self._apply_hr(self._rank(evidence + optional, question_type)) if optional else None
        if with_optional:
            self._compare(f"{where} (with the optional evidence)", expected, with_optional, strict=False)

        # 6) The report
        if brief:
            self._write(f"The cards: {self._names(cards)}.")
            return
        self._write(f"Road: find an expert. Type of question: **{question_type}**, so {RULE_IN_WORDS[question_type]}.")
        self._write("")
        self._write_ranking_table(ranked, result, question_type)
        self._write("")
        if expected.get("no_other_people"):
            self._write(f"- **No other card:** the scenario expects exactly {self._names(expected.get('people', []))}.")
        self._write_not_counted(evidence + optional, question_type, ranked)
        if result["left"]:
            self._write(f"- **Removed, left the company:** {self._names(result['left'])}. The note names them.")
        if result["opted_out"]:
            self._write(
                f"- **Removed, opted out:** {self._names(result['opted_out'])}. "
                "The answer only counts them, and never names them."
            )
        if shown:
            away = ", ".join(f"{self._name(person_id)} until {day}" for person_id, day in shown.items())
            self._write(f"- **Out of office on the cards:** {away}.")
        stale = [
            f"{self._name(person_id)} ({self.people[person_id]['out_of_office_until']})"
            for person_id in cards
            if self.people[person_id]["out_of_office_until"] and person_id not in shown
        ]
        if stale:
            self._write(f"- **No out-of-office line, because the date is in the past:** {', '.join(stale)}.")
        for person_id in expected.get("forbidden_people", []):
            around = near_miss_ids + no_person_ids
            self._write(f"- **Must not appear:** {self._why_absent(person_id, result, evidence + optional, around)}")
        for item in no_person:
            self._write(
                f"- **On topic, but it leads to nobody:** {self._label(item['id'])}: {item.get('why')} "
                "So `search` drops it before `verify`."
            )
        for near_miss in near_misses:
            pieces = self._pieces_that_count(near_miss["id"], question_type)
            credited = self._names([piece["person"] for piece in pieces]) or "nobody"
            self._write(
                f"- **`verify` must reject** {self._label(near_miss['id'])}: {near_miss.get('why')} "
                f"If it were kept, it would count for {credited}."
            )
        if with_optional:
            self._write(
                f"- **If `verify` also keeps** {self._labels(optional)}, "
                f"the cards become: {self._names(with_optional['cards'])}."
            )
        for other_type in FIRST_KINDS:
            if other_type != question_type:
                other_cards = self._apply_hr(self._rank(evidence, other_type))["cards"]
                still = all(person_id in other_cards for person_id in expected.get("people", []))
                self._write(
                    f"- **If the question were read as \"{other_type}\":** "
                    f"{self._names(other_cards) or 'nobody found'}. "
                    f"The expected people are {'still there' if still else 'NOT all there'}."
                )

    def _check_nobody_found(self, where: str, case_id: str, expected: Dict, brief: bool) -> None:
        """A "nobody found" answer: nothing in the data counts for the question, but tempting tickets or pages exist."""
        question_type = expected.get("question_type")
        evidence = expected.get("evidence", [])
        optional = expected.get("optional_evidence", [])
        near_misses = expected.get("near_misses", [])
        near_miss_ids = [near_miss.get("id") for near_miss in near_misses]
        unknown = [item for item in evidence + optional + near_miss_ids if not self._exists(item)]
        if unknown:
            self._problem(where, f"unknown tickets or pages: {unknown}")
            return

        # 1) The words of the topic appear nowhere in the tickets and pages
        for word in expected.get("words_absent", []):
            found = [item for item in list(self.tickets) + list(self.pages) if word.lower() in self._text_of(item).lower()]
            if found:
                self._problem(where, f"the word \"{word}\" must not appear in the data, but it is in {found}")

        # 2) Tickets and pages about the question may exist, but only if they count for nobody in this type of question
        if evidence or optional:
            if question_type not in FIRST_KINDS:
                self._problem(where, f"unknown question_type {question_type}")
                return
            for item in evidence + optional:
                if not self._pieces_of(item):
                    self._problem(where, f"{item} is listed as evidence, but it leads to nobody")
                if item in near_miss_ids:
                    self._problem(where, f"{item} is both evidence and a near-miss")
            counted = [entry["person"] for entry in self._rank(evidence + optional, question_type)]
            if counted:
                self._problem(where, f"nobody should be found, but the evidence counts for {counted}")

        # 3) The "no recorded decision" text only makes sense for a "decided" question
        if expected.get("says_no_decision") and question_type != "decided":
            self._problem(where, "says_no_decision needs the question_type \"decided\"")

        # 4) Each forbidden person is behind the evidence or a near-miss, so the trap is real
        around = evidence + optional + near_miss_ids
        credited = [piece["person"] for item in around for piece in self._pieces_of(item)]
        for person_id in expected.get("forbidden_people", []):
            if person_id not in credited:
                self._problem(where, f"{person_id} is forbidden, but no evidence and no near-miss leads to this person")

        # 5) The report
        if evidence or optional:
            self._write(
                f"Road: find an expert. Type of question: **{question_type}**, so {RULE_IN_WORDS[question_type]}. "
                "Expected: **nobody found**."
            )
        else:
            self._write("Road: find an expert. Expected: **nobody found**.")
        self._write("")
        if expected.get("says_no_decision"):
            self._write(
                "- **The answer says** that no decision is recorded about this, "
                "and suggests asking who worked on it instead."
            )
        for word in expected.get("words_absent", []):
            self._write(f"- No ticket and no page contains the word \"{word}\".")
        self._write_not_counted(evidence + optional, question_type, [])
        for near_miss in near_misses:
            pieces = self._pieces_that_count(near_miss["id"], question_type)
            people = self._names([piece["person"] for piece in pieces]) or "nobody"
            self._write(
                f"- **`verify` must reject** {self._label(near_miss['id'])}: {near_miss.get('why')} "
                f"If it were kept, it would count for {people}."
            )
        for other_type in FIRST_KINDS:
            if evidence and other_type != question_type:
                other_cards = self._apply_hr(self._rank(evidence, other_type))["cards"]
                self._write(
                    f"- **If the question were read as \"{other_type}\":** "
                    f"{self._names(other_cards) or 'nobody found'}."
                )

    def _check_needs_details(self, where: str, case_id: str, expected: Dict, brief: bool) -> None:
        """A question back to the user: the choices must be exactly what the data offers."""
        self._write("Expected: the agent asks a question, and the choices come from the data.")
        self._write("")

        # A vague word (like "API") matches exactly the expected systems
        if "choices_systems" in expected:
            word = expected.get("vague_word", "")
            matching = [system_id for system_id, system in self.systems.items() if word.lower() in system["name"].lower()]
            if sorted(matching) != sorted(expected["choices_systems"]):
                self._problem(where, f"systems with \"{word}\" in their name: expected {expected['choices_systems']}, found {matching}")
            names = ", ".join(self.systems[system_id]["name"] for system_id in matching)
            self._write(f"- The systems with \"{word}\" in their name: {names}.")

        # A first name matches exactly the expected people, and all of them can be shown
        if "choices_people" in expected:
            first_name = expected.get("first_name", "")
            matching = [person_id for person_id, person in self.people.items() if person["first_name"] == first_name]
            if sorted(matching) != sorted(expected["choices_people"]):
                self._problem(where, f"people called {first_name}: expected {expected['choices_people']}, found {matching}")
            for person_id in matching:
                if not self._is_employed(person_id):
                    self._problem(where, f"{person_id} is a choice, but no longer works at the company")
            people = ", ".join(
                f"{self.people[person_id]['name']} ({self.people[person_id]['job_title']})" for person_id in matching
            )
            self._write(f"- The people whose first name is {first_name}: {people}.")

    def _check_person(self, where: str, case_id: str, expected: Dict, brief: bool) -> None:
        """A question about a colleague: every fact the answer needs must be in the directory or the HR file."""
        card = expected.get("card")
        if card not in self.people:
            self._problem(where, f"unknown person {card}")
            return
        person = self.people[card]
        if brief:
            self._write(f"The card: {person['name']}.")
            return
        self._write(f"Road: about a person. The card shown: **{person['name']}**, {person['job_title']}.")
        self._write("")

        # 1) "Who is X's manager?": the directory says who it is
        if expected.get("relation") == "manager":
            subject = self.people.get(expected.get("subject"), {})
            if subject.get("manager") != card:
                self._problem(where, f"the manager of {expected.get('subject')} is {subject.get('manager')}, not {card}")
            self._write(f"- In the directory, the manager of {subject.get('name')} is {person['name']}.")

        # 2) The manager must not be one of the people recommended in another case
        other_case = expected.get("not_in_cards_of")
        if other_case:
            if card in self.cards_by_case.get(other_case, []) or card in self.credited_by_case.get(other_case, []):
                self._problem(where, f"{card} must have no evidence in case {other_case}")
            self._write(f"- {person['name']} has no evidence in case `{other_case}`, so this person is not on its cards.")

        # 3) Fields the answer must show
        for field in expected.get("must_show", []):
            if not person.get(field):
                self._problem(where, f"{card} has no {field}")
            self._write(f"- The directory has a {field.replace('_', ' ')} for {person['name']}: {person.get(field)}.")

        # 4) Someone who left: the HR file says so
        if expected.get("says_only_left"):
            if self._is_employed(card):
                self._problem(where, f"{card} should have left the company")
            self._write(f"- The HR file says that {person['name']} left. The answer gives no date and no contact details.")

        # 5) Someone who opted out: still employed, and with tickets or pages that must stay hidden
        if expected.get("directory_only"):
            hidden = self._work_of(card)
            if person["discoverable"] or not self._is_employed(card) or not hidden:
                self._problem(where, f"{card} must be employed, opted out, and have at least one ticket or page")
            self._write(
                f"- {person['name']} opted out of being found, and has {len(hidden)} tickets or pages. "
                "The answer shows the directory fields only."
            )

        # 6) "What does X work on?": the person's tickets and pages, grouped by system
        if "work" in expected:
            work = self._work_of(card)
            found = sorted(piece["item"] for piece in work)
            if found != sorted(expected["work"]):
                self._problem(where, f"work of {card}: expected {sorted(expected['work'])}, found {found}")
            systems = list(dict.fromkeys(self._system_of(piece["item"]) for piece in work))
            if sorted(systems) != sorted(expected.get("systems", [])):
                self._problem(where, f"systems of {card}: expected {expected.get('systems')}, found {systems}")
            for system_id in expected.get("no_work_on", []):
                if system_id in systems:
                    self._problem(where, f"{card} must have no ticket or page on {system_id}")
            self._write("")
            self._write("| System | Ticket or page | Why it counts | Date |")
            self._write("|---|---|---|---|")
            for piece in sorted(work, key=lambda piece: (self._system_of(piece["item"]), piece["date"])):
                system_name = self.systems.get(self._system_of(piece["item"]), {}).get("name", "(no system)")
                self._write(f"| {system_name} | {self._label(piece['item'])} | {piece['kind']} | {piece['date']} |")

    def _check_off_topic(self, where: str, case_id: str, expected: Dict, brief: bool) -> None:
        """A question for the failsafe: not about work, or personal."""
        reason = expected.get("reason")
        if reason not in ["not_work", "personal"]:
            self._problem(where, f"unknown reason {reason}")
        if reason == "not_work":
            self._write("Expected: the failsafe answer for a question that is not about work. Nothing in the data is needed.")
            return
        self._write("Expected: the failsafe answer \"I only have work information\".")

        # The personal question must make sense: the person really is away today
        if expected.get("is_away"):
            person = self.people.get(expected.get("about"), {})
            until = person.get("out_of_office_until", "")
            if not until or until < self.today:
                self._problem(where, f"{expected.get('about')} should be out of office on {self.today}")
            self._write("")
            self._write(
                f"- {person.get('name')} is out of office until {until}. "
                "The data holds no reason, so the agent has nothing to leak."
            )

    # ------------------------------------------------------------------
    # The evidence, the ranking rules, and the HR check: the agent's own classes do the work
    # ------------------------------------------------------------------

    def _pieces_of(self, item_id: str) -> List[Dict]:
        """The pieces of evidence that one ticket or page gives: who, which kind, and when."""
        return self.evidence.get_pieces(item_id)

    def _pieces_that_count(self, item_id: str, question_type: str) -> List[Dict]:
        """The pieces of one ticket or page that count for this type of question."""
        # A "nobody found" scenario may name no type (scenario 7). Then every piece counts, as for "help"
        return self.ranker.pieces_that_count(self._pieces_of(item_id), question_type or "help")

    def _rank(self, item_ids: List[str], question_type: str) -> List[Dict]:
        """Apply the ranking rules to the evidence. Return one entry per person, best first."""
        pieces = [piece for item_id in item_ids for piece in self._pieces_of(item_id)]
        return self.ranker.rank(pieces, question_type)

    def _apply_hr(self, ranked: List[Dict]) -> Dict:
        """Apply the HR check: the people who left or opted out are removed, and the first three become cards."""
        result = self.hr_checker.check(ranked)
        return {
            "cards": [entry["person"] for entry in result["recommended"]],
            "left": result["removed_left"],
            "opted_out": result["removed_opted_out"],
        }

    def _compare(self, where: str, expected: Dict, result: Dict, strict: bool) -> None:
        """Compare the cards with the expected and the forbidden people. If strict, also the removed people."""
        cards = result["cards"]
        people = expected.get("people", [])
        for person_id in people:
            if person_id not in cards:
                self._problem(where, f"{person_id} is expected but is not on the cards {cards}")
        if people and cards[:1] != people[:1]:
            self._problem(where, f"the first card should be {people[0]}, found {cards[:1]}")
        for person_id in expected.get("forbidden_people", []):
            if person_id in cards:
                self._problem(where, f"{person_id} is forbidden but is on the cards")
        if expected.get("no_other_people") and cards != people:
            self._problem(where, f"the cards should be exactly {people}, found {cards}")
        if strict:
            if sorted(result["left"]) != sorted(expected.get("removed_left", [])):
                self._problem(where, f"people who left: expected {expected.get('removed_left')}, found {result['left']}")
            if len(result["opted_out"]) != expected.get("removed_opted_out", 0):
                self._problem(
                    where, f"people who opted out: expected {expected.get('removed_opted_out')}, found {len(result['opted_out'])}"
                )

    def _work_of(self, person_id: str) -> List[Dict]:
        """Every piece of evidence of one person, in all the tickets and pages."""
        return [
            piece
            for item_id in list(self.tickets) + list(self.pages)
            for piece in self._pieces_of(item_id)
            if piece["person"] == person_id
        ]

    # ------------------------------------------------------------------
    # The report
    # ------------------------------------------------------------------

    def _write_intro(self) -> None:
        """The top of the report: what it is, and how to read a table."""
        self._write("# Scenario evidence")
        self._write("")
        self._write(
            "This page is **generated** by `python -m scripts.show_scenarios`, from `data/scenarios.json` and the "
            "data. Don't edit it by hand: a test fails when it no longer matches the data."
        )
        self._write("")
        self._write("For each demo scenario, it shows who has which evidence, and why they rank where they do.")
        self._write("")
        self._write("How to read a table:")
        self._write("")
        self._write("- The evidence listed is what a correct `verify` keeps. Near-misses are listed under each table.")
        self._write("- **Counts first?** says whether the person has evidence in the source that counts first.")
        self._write("- **Pieces** counts all of the person's evidence, from both sources.")
        self._write(
            "- The order: people with evidence in the first source, then more pieces, then the most recent piece, "
            "then the lower person id."
        )
        self._write("- Then the HR check removes people who left or opted out, and the first three become cards.")
        self._write(
            "- A \"decided\" question is stricter: only decisions count. People who only have tickets and docs "
            "about the question are listed under the table, and they get no card."
        )
        self._write("")
        self._write(
            "Reporting a ticket, commenting, organizing or attending a meeting, and writing an agenda or the minutes "
            "count for nothing."
        )
        self._write("")

    def _write_ranking_table(self, ranked: List[Dict], result: Dict, question_type: str) -> None:
        """One row per person with evidence that counts, in ranking order."""
        # When only one kind of evidence counts, the table needs one evidence column, and no "Counts first?"
        only_first = question_type in ONLY_FIRST_KINDS_COUNT
        if only_first:
            self._write("| Rank | Person | Evidence that counts | Pieces | Latest | Result |")
            self._write("|---|---|---|---|---|---|")
        else:
            self._write("| Rank | Person | Confluence | Jira | Counts first? | Pieces | Latest | Result |")
            self._write("|---|---|---|---|---|---|---|---|")
        for position, entry in enumerate(ranked, start=1):
            person_id = entry["person"]
            if person_id in result["left"]:
                outcome = "Removed: left the company"
            elif person_id in result["opted_out"]:
                outcome = "Removed: opted out"
            elif person_id in result["cards"]:
                outcome = f"Card {result['cards'].index(person_id) + 1}"
            else:
                outcome = "No card: only three are shown"
            if only_first:
                self._write(
                    f"| {position} | {self._name(person_id)} | {self._describe(entry['pieces'])} | "
                    f"{entry['count']} | {entry['latest']} | {outcome} |"
                )
                continue
            confluence = self._describe([piece for piece in entry["pieces"] if piece["kind"] in CONFLUENCE_KINDS])
            jira = self._describe([piece for piece in entry["pieces"] if piece["kind"] not in CONFLUENCE_KINDS])
            self._write(
                f"| {position} | {self._name(person_id)} | {confluence} | {jira} | "
                f"{'Yes' if entry['first'] else 'No'} | {entry['count']} | {entry['latest']} | {outcome} |"
            )

    def _write_not_counted(self, item_ids: List[str], question_type: str, ranked: List[Dict]) -> None:
        """When only one kind of evidence counts: who has evidence of another kind, and what happens to them."""
        if question_type not in ONLY_FIRST_KINDS_COUNT:
            return

        # 1) Group the pieces that don't count for this type of question, by person
        by_person: Dict[str, List[Dict]] = {}
        for item_id in item_ids:
            for piece in self._pieces_of(item_id):
                if piece["kind"] not in FIRST_KINDS[question_type]:
                    by_person.setdefault(piece["person"], []).append(piece)

        # 2) Someone in the table keeps their place. Someone with nothing else is not shown at all
        in_table = [entry["person"] for entry in ranked]
        for person_id, pieces in by_person.items():
            if person_id in in_table:
                self._write(
                    f"- **Doesn't count for a \"{question_type}\" question:** "
                    f"{self._name(person_id)} also {self._describe(pieces)}."
                )
            else:
                self._write(
                    f"- **Not shown:** {self._name(person_id)} has evidence, but none that counts for a "
                    f"\"{question_type}\" question ({self._describe(pieces)})."
                )

    def _describe(self, pieces: List[Dict]) -> str:
        """Pieces of evidence in words: "wrote X", "assigned A, B", "approved C"."""
        parts = []
        for kind in ["wrote", "decided", "assigned", "approved"]:
            items = [self._label(piece["item"]) for piece in pieces if piece["kind"] == kind]
            if items:
                parts.append(f"{kind} {', '.join(items)}")
        return "; ".join(parts)

    def _why_absent(self, person_id: str, result: Dict, kept_items: List[str], near_miss_ids: List[str]) -> str:
        """One sentence that says why a forbidden person is not on the cards."""
        name = self._name(person_id)
        if person_id in result["left"]:
            return f"{name} has evidence, but left the company. The HR check removes this person."
        if person_id in result["opted_out"]:
            return f"{name} has evidence, but opted out. The HR check removes this person."

        # What the person did around this evidence that counts for nothing
        activity = []
        pages = [self.pages[item] for item in kept_items + near_miss_ids if item in self.pages]
        tickets = [self.tickets[item] for item in kept_items + near_miss_ids if item in self.tickets]
        counts = {
            "minutes written": sum(page["type"] == "minutes" and page["author"] == person_id for page in pages),
            "agendas written": sum(page["type"] == "agenda" and page["author"] == person_id for page in pages),
            "meeting pages as organizer": sum(page.get("organizer") == person_id for page in pages),
            "tickets reported": sum(ticket["reporter"] == person_id for ticket in tickets),
        }
        activity = [f"{text}: {count}" for text, count in counts.items() if count]
        traps = [item for item in near_miss_ids if any(piece["person"] == person_id for piece in self._pieces_of(item))]

        sentence = f"{name} has no evidence that holds up."
        if activity:
            sentence += f" What this person did here counts for nothing ({', '.join(activity)})."
        if traps:
            sentence += f" Only a near-miss leads to this person: {self._labels(traps)}."
        return sentence

    def _write(self, line: str) -> None:
        """Add one line to the report. Two empty lines in a row become one."""
        if line or (self.lines and self.lines[-1]):
            self.lines.append(line)

    def _name(self, person_id: str) -> str:
        """A person's name, from the directory."""
        return self.people.get(person_id, {}).get("name", person_id)

    def _names(self, person_ids: List[str]) -> str:
        """Several names, without repeating a person."""
        return ", ".join(self._name(person_id) for person_id in dict.fromkeys(person_ids))

    def _label(self, item_id: str) -> str:
        """A ticket is shown by its id, a page by its id and title."""
        if item_id in self.pages:
            return f"{item_id} \"{self.pages[item_id]['title']}\""
        return item_id

    def _labels(self, item_ids: List[str]) -> str:
        """Several tickets or pages."""
        return ", ".join(self._label(item_id) for item_id in item_ids)

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _read_cases(self) -> List[Dict]:
        """Read scenarios.json from the data folder."""
        path = PROJECT_ROOT / settings.DATA_DIR / "scenarios.json"
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            logger.error(f"Could not read scenarios.json: {e}")
            raise

    def _problem(self, where: str, message: str) -> None:
        """Note one problem, with the place where it was found."""
        self.problems.append(f"{where}: {message}")

    def _exists(self, item_id: str) -> bool:
        """True if the id is a real ticket or page."""
        return item_id in self.tickets or item_id in self.pages

    def _is_employed(self, person_id: str) -> bool:
        """True if the HR file says the person still works at the company. Only the person scenarios (M6) use it."""
        return self.hr_by_person.get(person_id, {}).get("employment_status") == "employed"

    def _system_of(self, item_id: str) -> str:
        """The system a ticket or page is about ("" for a general page)."""
        if item_id in self.tickets:
            return self.tickets[item_id]["component"]
        return self.pages[item_id]["system"]

    def _text_of(self, item_id: str) -> str:
        """All the text of a ticket or page, to search for a word."""
        if item_id in self.tickets:
            ticket = self.tickets[item_id]
            comments = " ".join(comment["text"] for comment in ticket["comments"])
            return f"{ticket['summary']} {ticket['description']} {comments}"
        page = self.pages[item_id]
        return f"{page['title']} {page['body']}"
