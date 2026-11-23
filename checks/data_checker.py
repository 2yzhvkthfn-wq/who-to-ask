import re
import unicodedata
from datetime import date
from typing import Dict, List

from config.constants import (
    EMPLOYMENT_STATUSES,
    PAGE_LANGUAGES,
    PAGE_TYPES,
    TICKET_DONE_STATUSES,
    TICKET_PRIORITIES,
    TICKET_STATUSES,
    TICKET_TYPES,
    WORK_LANGUAGES,
)
from config.settings import PROJECT_ROOT, settings
from sources import CompanySource, HrSource, PageSource, PeopleSource, TicketSource

# The fields each kind of record must have: no more, no fewer
TEAM_FIELDS = ["id", "name", "jira_key", "description"]
SYSTEM_FIELDS = ["id", "name", "team", "description"]
PERSON_FIELDS = [
    "id", "name", "first_name", "last_name", "email", "job_title", "team", "manager",
    "languages", "work_phone", "out_of_office_until", "discoverable",
]
HR_FIELDS = ["id", "person_id", "employment_status", "start_date", "end_date"]
TICKET_FIELDS = [
    "id", "type", "summary", "description", "team", "component", "status", "priority",
    "reporter", "assignee", "approver", "created", "updated", "resolved", "labels", "comments",
]
COMMENT_FIELDS = ["author", "date", "text"]
PAGE_FIELDS = ["id", "title", "space", "system", "type", "author", "created", "updated", "language"]
# Meeting pages have a few more header fields
MEETING_FIELDS = {
    "doc": [],
    "agenda": ["meeting_date", "organizer"],
    "minutes": ["meeting_date", "organizer", "attendees", "decision_owner"],
}
# Added when the page files are read (SeedFiles): they are not written in the header
PAGE_EXTRA_FIELDS = ["body", "file"]


class DataChecker:
    """Checks that the fake company data is complete and consistent."""

    def __init__(self):
        # 1) Read every kind of data once, through the same readers as the agent: since M4, they read MongoDB.
        #    A problem still names the file to fix (people.json, pages/...): the files are the seed source of MongoDB
        company = CompanySource()
        self.teams = company.list_teams()
        self.systems = company.list_systems()
        self.people = PeopleSource().list_people()
        self.hr_records = HrSource().list_records()
        self.tickets = TicketSource().list_tickets()
        self.pages = PageSource().list_pages()

        # 2) Quick lookups by id
        self.teams_by_id = {team.get("id"): team for team in self.teams}
        self.system_ids = {system.get("id") for system in self.systems}
        self.person_ids = {person.get("id") for person in self.people}
        self.hr_by_person = {record.get("person_id"): record for record in self.hr_records}

        # 3) The fixed fake "today", as text like every date in the data
        self.today = settings.TODAY.isoformat()
        self.problems: List[str] = []

    def check(self) -> Dict:
        """Run every check. Return the problems found and the number of records read."""
        self.problems = []
        self._check_company()
        self._check_summary()
        self._check_people()
        self._check_hr_records()
        self._check_tickets()
        self._check_pages()
        self._check_time()
        self._check_mentions()
        self._check_coverage()
        counts = {
            "teams": len(self.teams),
            "systems": len(self.systems),
            "people": len(self.people),
            "hr_records": len(self.hr_records),
            "tickets": len(self.tickets),
            "pages": len(self.pages),
        }
        return {"problems": self.problems, "counts": counts}

    # ------------------------------------------------------------------
    # The checks, one kind of data at a time
    # ------------------------------------------------------------------

    def _check_company(self) -> None:
        """Teams and systems: the right fields, no duplicates, and every system has a real team."""
        # Teams
        for team in self.teams:
            where = f"teams.json {team.get('id')}"
            if not self._has_fields(team, TEAM_FIELDS, where):
                continue
            if not re.fullmatch(r"[a-z]+(_[a-z]+)*", team["id"]):
                self._problem(where, "the id must be lower-case words joined by _")
            if not re.fullmatch(r"[A-Z]{3}", team["jira_key"]):
                self._problem(where, "the jira_key must be three capital letters")
        for field in ["id", "name", "jira_key"]:
            self._check_unique(self.teams, field, "teams.json")

        # Systems
        for system in self.systems:
            where = f"systems.json {system.get('id')}"
            if not self._has_fields(system, SYSTEM_FIELDS, where):
                continue
            if not re.fullmatch(r"[a-z]+(_[a-z]+)*", system["id"]):
                self._problem(where, "the id must be lower-case words joined by _")
            if system["team"] not in self.teams_by_id:
                self._problem(where, f"unknown team {system['team']}")
        for field in ["id", "name"]:
            self._check_unique(self.systems, field, "systems.json")

    def _check_summary(self) -> None:
        """The one-page summary says the same thing as teams.json and systems.json."""
        try:
            text = (PROJECT_ROOT / settings.DATA_DIR / "company_summary.md").read_text(encoding="utf-8")
        except OSError as e:
            self._problem("company_summary.md", f"could not be read: {e}")
            return

        # Cut the page into its sections: one "## Team name" section per team
        sections = {}
        for block in text.split("\n## ")[1:]:
            heading, _, body = block.partition("\n")
            sections[heading.strip()] = body

        for team in self.teams:
            where = f"company_summary.md {team.get('name')}"
            body = sections.get(team.get("name"))
            if body is None:
                self._problem(where, "the team has no section")
                continue
            if not body.startswith(f"\n{team.get('description')}\n"):
                self._problem(where, "the team's description differs from teams.json")
            expected = [
                f"- **{system.get('name')}:** {system.get('description')}"
                for system in self.systems
                if system.get("team") == team.get("id")
            ]
            found = [line for line in body.split("\n") if line.startswith("- ")]
            if expected != found:
                self._problem(where, "the systems listed differ from systems.json")

    def _check_people(self) -> None:
        """The directory: the right fields, real teams and managers, and emails and phones that reach nobody."""
        domains = set()
        for person in self.people:
            where = f"people.json {person.get('id')}"
            if not self._has_fields(person, PERSON_FIELDS, where):
                continue
            # Ids look like p007, so an id never contains a name
            if not re.fullmatch(r"p\d{3}", person["id"]):
                self._problem(where, "the id must look like p007")
            if person["name"] != f"{person['first_name']} {person['last_name']}":
                self._problem(where, "name must be first_name, a space, then last_name")
            if not person["job_title"].strip():
                self._problem(where, "the job title is empty")

            # Emails: built from the name, without accents, on a domain reserved for examples
            local, _, domain = person["email"].partition("@")
            domains.add(domain)
            expected_local = f"{self._plain(person['first_name'])}.{self._plain(person['last_name'])}"
            if not person["email"].isascii() or local != expected_local:
                self._problem(where, f"the email must start with {expected_local}")
            if not domain.endswith(".example"):
                self._problem(where, "the email must end in .example")

            # Team and manager must exist
            if person["team"] not in self.teams_by_id:
                self._problem(where, f"unknown team {person['team']}")
            if person["manager"] and person["manager"] not in self.person_ids:
                self._problem(where, f"unknown manager {person['manager']}")

            # Languages, phone, out of office, opt-out
            languages = person["languages"]
            if (
                not isinstance(languages, list)
                or not languages
                or len(set(languages)) != len(languages)
                or any(language not in WORK_LANGUAGES for language in languages)
            ):
                self._problem(where, f"languages must be a list taken from {WORK_LANGUAGES}")
            if person["work_phone"] and not re.fullmatch(r"(514|438)-555-01\d\d", person["work_phone"]):
                self._problem(where, "the work phone must be in the fiction range, like 514-555-0142")
            if person["out_of_office_until"] and not self._is_date(person["out_of_office_until"]):
                self._problem(where, "out_of_office_until must be empty or a date like 2026-11-10")
            if not isinstance(person["discoverable"], bool):
                self._problem(where, "discoverable must be true or false")
        for field in ["id", "name", "email", "work_phone"]:
            self._check_unique(self.people, field, "people.json")
        if len(domains) > 1:
            self._problem("people.json", f"the emails use more than one domain: {sorted(domains)}")

        # Managers: one head of the department, and no loops
        managers = {person.get("id"): person.get("manager") for person in self.people}
        heads = sorted(person_id for person_id, manager in managers.items() if not manager)
        if len(heads) != 1:
            self._problem("people.json", f"exactly one person must have no manager, found {heads}")
        for person_id in managers:
            seen, current = set(), person_id
            while current:
                if current in seen:
                    self._problem(f"people.json {person_id}", "the managers form a loop")
                    break
                seen.add(current)
                current = managers.get(current)

        # Nobody who still works here reports to someone who left
        for person in self.people:
            manager = person.get("manager")
            if manager and self._is_employed(person.get("id")) and not self._is_employed(manager):
                self._problem(f"people.json {person.get('id')}", f"the manager {manager} no longer works here")

    def _check_hr_records(self) -> None:
        """The HR file: one record per person, with a status and dates that agree."""
        for record in self.hr_records:
            where = f"hr_records.json {record.get('id')}"
            if not self._has_fields(record, HR_FIELDS, where):
                continue
            if not re.fullmatch(r"hr\d{3}", record["id"]):
                self._problem(where, "the id must look like hr007")
            if record["person_id"] not in self.person_ids:
                self._problem(where, f"unknown person {record['person_id']}")
            if record["employment_status"] not in EMPLOYMENT_STATUSES:
                self._problem(where, f"employment_status must be one of {EMPLOYMENT_STATUSES}")
            # Someone who still works here has no end date. Someone who left has one
            if record["employment_status"] == "employed" and record["end_date"]:
                self._problem(where, "an employed person must have an empty end_date")
            if record["employment_status"] == "left" and not record["end_date"]:
                self._problem(where, "a person who left must have an end_date")
        for field in ["id", "person_id"]:
            self._check_unique(self.hr_records, field, "hr_records.json")

        # Every person has an HR record
        for person_id in sorted(self.person_ids - set(self.hr_by_person)):
            self._problem(f"people.json {person_id}", "has no HR record")

        # Person ids follow the hiring order: p001 joined first
        starts = [
            self.hr_by_person[person_id].get("start_date", "")
            for person_id in sorted(self.person_ids & set(self.hr_by_person))
        ]
        if starts != sorted(starts):
            self._problem("hr_records.json", "the person ids don't follow the start dates")

    def _check_tickets(self) -> None:
        """Jira tickets: the right fields, allowed values, and ids that point to real records."""
        for ticket in self.tickets:
            where = f"tickets.json {ticket.get('id')}"
            if not self._has_fields(ticket, TICKET_FIELDS, where):
                continue

            # The id is a Jira key: the team's key, a dash, and a number (CLM-212)
            match = re.fullmatch(r"([A-Z]{3})-(\d+)", ticket["id"])
            team = self.teams_by_id.get(ticket["team"])
            if not match:
                self._problem(where, "the id must look like CLM-212")
            if team is None:
                self._problem(where, f"unknown team {ticket['team']}")
            elif match and match.group(1) != team.get("jira_key"):
                self._problem(where, f"the id must start with {team.get('jira_key')}, the key of its team")

            # Allowed values
            for field, allowed in [
                ("type", TICKET_TYPES),
                ("status", TICKET_STATUSES),
                ("priority", TICKET_PRIORITIES),
            ]:
                if ticket[field] not in allowed:
                    self._problem(where, f"{field} must be one of {allowed}")
            if ticket["component"] and ticket["component"] not in self.system_ids:
                self._problem(where, f"unknown component {ticket['component']}")
            if not ticket["summary"].strip() or not ticket["description"].strip():
                self._problem(where, "the summary and the description must not be empty")

            # People: always a reporter. An assignee and an approver only when there is one
            if ticket["reporter"] not in self.person_ids:
                self._problem(where, f"unknown reporter {ticket['reporter']}")
            for role in ["assignee", "approver"]:
                if ticket[role] and ticket[role] not in self.person_ids:
                    self._problem(where, f"unknown {role} {ticket[role]}")
            if ticket["approver"] and ticket["approver"] == ticket["assignee"]:
                self._problem(where, "nobody approves their own ticket")
            if ticket["status"] == "Waiting for Approval" and ticket["approver"]:
                self._problem(where, "a ticket that waits for approval has no approver yet")

            # A ticket has a resolved date when it is done, and only then
            if (ticket["status"] in TICKET_DONE_STATUSES) != bool(ticket["resolved"]):
                self._problem(where, "resolved must be set when the status is Resolved or Closed, and only then")

            # Labels and comments
            labels = ticket["labels"]
            if not isinstance(labels, list) or any(not re.fullmatch(r"[a-z0-9-]+", str(label)) for label in labels):
                self._problem(where, "labels must be a list of lower-case words")
            if not isinstance(ticket["comments"], list):
                self._problem(where, "comments must be a list")
                continue
            for comment in ticket["comments"]:
                if not self._has_fields(comment, COMMENT_FIELDS, f"{where} comment"):
                    continue
                if comment["author"] not in self.person_ids:
                    self._problem(where, f"unknown comment author {comment['author']}")
                if not comment["text"].strip():
                    self._problem(where, "a comment is empty")
        self._check_unique(self.tickets, "id", "tickets.json")

    def _check_pages(self) -> None:
        """Confluence pages: the right header fields, allowed values, and ids that point to real records."""
        for page in self.pages:
            where = f"pages/{page.get('file')}"
            page_type = page.get("type")
            if page_type not in PAGE_TYPES:
                self._problem(where, f"type must be one of {PAGE_TYPES}")
                continue
            if not self._has_fields(page, PAGE_FIELDS + MEETING_FIELDS[page_type] + PAGE_EXTRA_FIELDS, where):
                continue

            # Ids look like pg014, and the file name starts with the id
            if not re.fullmatch(r"pg\d{3}", page["id"]):
                self._problem(where, "the id must look like pg014")
            if not page["file"].startswith(f"{page['id']}_"):
                self._problem(where, "the file name must start with the page id and _")
            if not page["title"].strip():
                self._problem(where, "the title is empty")
            if len(page["body"]) < 200:
                self._problem(where, "the page has almost no text")

            # Space, system, author, language
            if page["space"] not in self.teams_by_id:
                self._problem(where, f"unknown space {page['space']} (a space is a team id)")
            if page["system"] and page["system"] not in self.system_ids:
                self._problem(where, f"unknown system {page['system']}")
            if page["author"] not in self.person_ids:
                self._problem(where, f"unknown author {page['author']}")
            if page["language"] not in PAGE_LANGUAGES:
                self._problem(where, f"language must be one of {PAGE_LANGUAGES}")

            # Meeting pages: an organizer, and for minutes the attendees and the decision owner
            if page_type in ["agenda", "minutes"] and page["organizer"] not in self.person_ids:
                self._problem(where, f"unknown organizer {page['organizer']}")
            if page_type == "minutes":
                attendees = page["attendees"]
                if not isinstance(attendees, list) or not attendees or len(set(attendees)) != len(attendees):
                    self._problem(where, "attendees must be a list of different people")
                    continue
                for attendee in attendees:
                    if attendee not in self.person_ids:
                        self._problem(where, f"unknown attendee {attendee}")
                # The person who wrote the minutes, the organizer, and the decision owner were in the room
                for role in ["author", "organizer", "decision_owner"]:
                    if page[role] and page[role] not in attendees:
                        self._problem(where, f"the {role} {page[role]} is not in the attendees")
        for field in ["id", "title"]:
            self._check_unique(self.pages, field, "pages")

    def _check_time(self) -> None:
        """Time makes sense: real dates, nothing after today, and everyone was at the company when they acted."""
        # 1) Collect every dated action as (where, what, day, person). The person is "" when nobody is tied to the date
        actions = []
        for record in self.hr_records:
            where = f"hr_records.json {record.get('id')}"
            actions.append((where, "start_date", record.get("start_date"), ""))
            if record.get("end_date"):
                actions.append((where, "end_date", record["end_date"], ""))
        for ticket in self.tickets:
            where = f"tickets.json {ticket.get('id')}"
            actions.append((where, "created (reporter)", ticket.get("created"), ticket.get("reporter")))
            actions.append((where, "updated", ticket.get("updated"), ""))
            if ticket.get("resolved"):
                actions.append((where, "resolved (assignee)", ticket["resolved"], ticket.get("assignee")))
                actions.append((where, "resolved (approver)", ticket["resolved"], ticket.get("approver")))
            for comment in ticket.get("comments") or []:
                actions.append((where, "comment", comment.get("date"), comment.get("author")))
        for page in self.pages:
            where = f"pages/{page.get('file')}"
            actions.append((where, "created (author)", page.get("created"), page.get("author")))
            actions.append((where, "updated (author)", page.get("updated"), page.get("author")))
            if "meeting_date" in page:
                attendees = page.get("attendees") if isinstance(page.get("attendees"), list) else []
                for person_id in dict.fromkeys([page.get("organizer")] + attendees):
                    actions.append((where, "meeting_date", page.get("meeting_date"), person_id))

        # 2) Check them all the same way
        for where, what, day, person_id in actions:
            if not self._is_date(day):
                self._problem(where, f"{what} must be a date like 2026-10-12, found {day!r}")
            elif day > self.today:
                self._problem(where, f"{what} is after today ({self.today}): {day}")
            elif person_id and not self._was_employed(person_id, day):
                self._problem(where, f"{person_id} was not at the company on {day} ({what})")

        # 3) HR: people leave after they join
        for record in self.hr_records:
            start, end = record.get("start_date"), record.get("end_date")
            if end and self._is_date(start) and self._is_date(end) and end < start:
                self._problem(f"hr_records.json {record.get('id')}", "end_date is before start_date")

        # 4) Tickets: they close after they open, and the last update comes last
        for ticket in self.tickets:
            where = f"tickets.json {ticket.get('id')}"
            created, updated, resolved = ticket.get("created"), ticket.get("updated"), ticket.get("resolved")
            if not self._is_date(created) or not self._is_date(updated) or (resolved and not self._is_date(resolved)):
                continue
            if updated < created:
                self._problem(where, "updated is before created")
            if resolved and not created <= resolved <= updated:
                self._problem(where, "resolved must fall between created and updated")
            for comment in ticket.get("comments") or []:
                if self._is_date(comment.get("date")) and not created <= comment["date"] <= updated:
                    self._problem(where, f"the comment of {comment['date']} must fall between created and updated")
            # An open ticket: its assignee had joined by the last update, and had not left before it was created
            record = self.hr_by_person.get(ticket.get("assignee"))
            if record and not resolved:
                if record.get("start_date", "") > updated or (record.get("end_date") and record["end_date"] < created):
                    self._problem(where, f"the assignee {ticket['assignee']} was not at the company for this ticket")

        # 5) Inside one team, a higher ticket number was created later (Jira numbers tickets in order)
        for team in self.teams:
            team_tickets = [ticket for ticket in self.tickets if ticket.get("team") == team.get("id")]
            team_tickets.sort(key=self._ticket_number)
            for earlier, later in zip(team_tickets, team_tickets[1:]):
                if str(later.get("created")) < str(earlier.get("created")):
                    self._problem(
                        f"tickets.json {later.get('id')}",
                        f"has a higher number than {earlier.get('id')} but was created before it",
                    )

        # 6) Pages: updated after created. Minutes are written after the meeting, agendas before it
        for page in self.pages:
            where = f"pages/{page.get('file')}"
            created, updated, meeting = page.get("created"), page.get("updated"), page.get("meeting_date")
            if not self._is_date(created) or not self._is_date(updated):
                continue
            if updated < created:
                self._problem(where, "updated is before created")
            if meeting is None or not self._is_date(meeting):
                continue
            if date.fromisoformat(meeting).weekday() >= 5:
                self._problem(where, f"the meeting of {meeting} falls on a weekend")
            if page.get("type") == "minutes" and created < meeting:
                self._problem(where, "the minutes were created before the meeting")
            if page.get("type") == "agenda" and created > meeting:
                self._problem(where, "the agenda was created after the meeting")

    def _check_mentions(self) -> None:
        """A ticket id written inside a text (like CLM-212) is a real ticket, and it existed when the text was written."""
        created_by_id = {ticket.get("id"): ticket.get("created", "") for ticket in self.tickets}

        # 1) Collect every text with the day it was written: (where, text, day)
        texts = []
        for ticket in self.tickets:
            where = f"tickets.json {ticket.get('id')}"
            opening = f"{ticket.get('summary', '')}\n{ticket.get('description', '')}"
            texts.append((where, opening, ticket.get("created", "")))
            for comment in ticket.get("comments") or []:
                texts.append((where, comment.get("text", ""), comment.get("date", "")))
        for page in self.pages:
            texts.append((f"pages/{page.get('file')}", page.get("body", ""), page.get("updated", "")))

        # 2) Look for ticket ids: one of the teams' Jira keys, a dash, and a number
        keys = "|".join(team.get("jira_key", "") for team in self.teams)
        for where, text, day in texts:
            for mention in sorted(set(re.findall(rf"\b(?:{keys})-\d+\b", str(text)))):
                if mention not in created_by_id:
                    self._problem(where, f"mentions the ticket {mention}, which does not exist")
                elif created_by_id[mention] > str(day):
                    self._problem(where, f"mentions the ticket {mention} on {day}, before that ticket was created")

    def _check_coverage(self) -> None:
        """Every system on the company summary has at least one ticket or page, so none is an empty shell."""
        used = {ticket.get("component") for ticket in self.tickets} | {page.get("system") for page in self.pages}
        for system in self.systems:
            if system.get("id") not in used:
                self._problem(f"systems.json {system.get('id')}", "no ticket and no page is about this system")

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _problem(self, where: str, message: str) -> None:
        """Note one problem, with the place where it was found."""
        self.problems.append(f"{where}: {message}")

    def _has_fields(self, record: Dict, fields: List[str], where: str) -> bool:
        """True if the record has exactly these fields. If not, the problem is noted."""
        missing = [name for name in fields if name not in record]
        unknown = [name for name in record if name not in fields]
        if missing:
            self._problem(where, f"missing fields: {', '.join(missing)}")
        if unknown:
            self._problem(where, f"unknown fields: {', '.join(unknown)}")
        return not missing and not unknown

    def _check_unique(self, records: List[Dict], field: str, where: str) -> None:
        """Note a problem for every value of this field that appears twice (empty values don't count)."""
        seen = set()
        for record in records:
            value = record.get(field)
            if value and value in seen:
                self._problem(where, f"{field} appears twice: {value}")
            seen.add(value)

    def _is_date(self, text) -> bool:
        """True for a real date written like 2026-10-12."""
        try:
            return isinstance(text, str) and date.fromisoformat(text).isoformat() == text
        except ValueError:
            return False

    def _is_employed(self, person_id: str) -> bool:
        """True if the HR file says the person still works at the company."""
        return self.hr_by_person.get(person_id, {}).get("employment_status") == "employed"

    def _was_employed(self, person_id: str, day: str) -> bool:
        """True if the person worked at the company on that day."""
        record = self.hr_by_person.get(person_id)
        if not record:
            return False
        start, end = record.get("start_date", ""), record.get("end_date", "")
        return start <= day and (not end or day <= end)

    def _plain(self, text: str) -> str:
        """Lower-case text without accents or spaces: "Côté" becomes "cote"."""
        decomposed = unicodedata.normalize("NFKD", text)
        return "".join(letter for letter in decomposed if letter.isascii() and not letter.isspace()).lower()

    def _ticket_number(self, ticket: Dict) -> int:
        """The number at the end of a ticket id: 212 for CLM-212."""
        number = str(ticket.get("id", "")).rpartition("-")[2]
        return int(number) if number.isdigit() else 0
