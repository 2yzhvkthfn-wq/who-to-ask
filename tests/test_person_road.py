"""Free tests of the person road: a question about a colleague, from the graph to the answer. No OpenAI calls.

The graph is the real one, with fake LLM steps (the agent helper of conftest.py). Here the fake understand answers
what the real one answers for each question: the road "person", the name as the question writes it, and what is
asked. find_person, person_card, and the answer run for real, on the real data.
The tests of what the real model understands are in test_agent.py, and they are paid.
"""

import json
from typing import Dict

import pytest

from config.texts import ASK_USER_TEXTS, NOBODY_FOUND_TEXTS, PERSON_TEXTS
from sources import CompanySource, HrSource, PeopleSource, SeedFiles


@pytest.fixture(scope="module")
def people() -> Dict:
    """The directory, by person id."""
    return {person["id"]: person for person in PeopleSource().list_people()}


def ask(agent, question: str, name: str, asks: str = "card", language: str = "en") -> Dict:
    """Ask one question about a colleague. The fake understand gives the name and what is asked."""
    workflow, fakes = agent
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": language,
        "search_words": [],
        "person_name": name,
        "person_asks": asks,
    }
    return workflow.full_pipeline(question)


# ----------------------------------------------------------------------
# The scenarios of the person road
# ----------------------------------------------------------------------


def test_scenario_9_the_manager_of_a_colleague(agent, scenarios, people):
    """ "Who is Sophie Martin's manager?": the card of her manager, and a sentence that names both of them."""
    turn = scenarios["s09a"]["turns"][0]
    expected = turn["expected"]
    subject, manager = people[expected["subject"]], people[expected["card"]]
    answer = ask(agent, turn["question"], subject["name"], "manager")

    assert answer["status"] == "person"
    assert answer["person_card"]["id"] == expected["card"]
    # The answer names the person it understood the question to be about, so the user can see who was picked
    assert answer["message"] == f"{subject['name']}'s manager is {manager['name']}."
    # The manager is not one of the people recommended in scenario 1
    assert expected["card"] not in scenarios[expected["not_in_cards_of"]]["turns"][0]["expected"]["people"]
    assert answer["cards"] == []


def test_a_person_card_shows_what_the_directory_says(agent, scenarios, people):
    """The card of scenario 9: every value comes from the data, and the two links open with no message."""
    expected = scenarios["s09a"]["turns"][0]["expected"]
    person = people[expected["card"]]
    card = ask(agent, "Who is Sophie Martin's manager?", people[expected["subject"]]["name"], "manager")["person_card"]
    team_names = {team["id"]: team["name"] for team in CompanySource().list_teams()}

    assert card["name"] == person["name"]
    assert card["job_title"] == person["job_title"]
    assert card["team"] == team_names[person["team"]]
    assert card["manager"] == people[person["manager"]]["name"]
    assert card["email"] == person["email"] and card["email"].endswith(".example")
    assert card["languages"] == person["languages"]
    assert card["left"] is False
    assert card["teams_link"] == f"https://teams.microsoft.com/l/chat/0/0?users={person['email']}"
    assert card["email_link"] == f"mailto:{person['email']}"
    # Nothing that was not asked for
    assert card["work_phone"] == ""
    assert card["work"] == []


def test_scenario_10_the_work_phone_only_shows_when_it_is_asked_for(agent, scenarios, people):
    """ "What's Hélène Dubois's work phone?": the number of the directory. A plain card of her does not show it."""
    turn = scenarios["s10"]["turns"][0]
    person = people[turn["expected"]["card"]]
    asked = ask(agent, turn["question"], person["name"], "work_phone")

    assert asked["status"] == "person"
    assert asked["person_card"]["id"] == person["id"]
    assert asked["person_card"]["work_phone"] == person["work_phone"]
    assert asked["message"] == f"{person['name']}'s work phone is {person['work_phone']}."
    # The fake number is one of the numbers reserved for fiction
    assert "-555-01" in person["work_phone"]

    plain = ask(agent, f"Who is {person['name']}?", person["name"], "card")
    assert plain["person_card"]["work_phone"] == ""
    assert person["work_phone"] not in json.dumps(plain, ensure_ascii=False)


@pytest.mark.parametrize("asks", ["card", "manager", "work_phone", "work", "out_of_office"])
def test_scenario_11_someone_who_left_only_gets_one_sentence(agent, scenarios, people, asks):
    """ "Does Tom Walsh still work here?": only "no longer works at the company", whatever is asked about him."""
    turn = scenarios["s11a"]["turns"][0]
    person = people[turn["expected"]["card"]]
    answer = ask(agent, turn["question"], person["name"], asks)
    everything = json.dumps(answer, ensure_ascii=False)

    assert answer["status"] == "person"
    assert answer["message"] == f"{person['name']} no longer works at the company."
    assert answer["person_card"]["id"] == person["id"]
    assert answer["person_card"]["left"] is True

    # No contact details, no job title, no team, no manager, no link, and nothing he worked on
    for value in [person["email"], person["work_phone"], person["job_title"], people[person["manager"]]["name"]]:
        assert value not in everything
    assert "mailto:" not in everything and "teams.microsoft.com" not in everything
    assert answer["person_card"]["work"] == []
    # No date from the HR file: neither his first day nor his last day
    record = next(record for record in HrSource().list_records() if record["person_id"] == person["id"])
    assert record["employment_status"] == "left"
    assert record["start_date"] not in everything and record["end_date"] not in everything


@pytest.mark.parametrize("asks", ["card", "work"])
def test_scenario_11_someone_who_opted_out_only_shows_the_directory_fields(agent, scenarios, people, asks):
    """ "Who is Nadia Benali?": her directory fields. Her tickets are never listed, even when the question asks."""
    workflow, _ = agent
    turn = scenarios["s11b"]["turns"][0]
    person = people[turn["expected"]["card"]]
    answer = ask(agent, turn["question"], person["name"], asks)
    card = answer["person_card"]

    assert person["discoverable"] is False
    assert answer["status"] == "person"
    assert card["id"] == person["id"]
    assert card["job_title"] == person["job_title"] and card["email"] == person["email"]
    assert card["work"] == []

    # She does have tickets, and none of them is anywhere in the answer
    hidden = workflow.evidence.list_pieces_of(person["id"])
    assert hidden
    everything = json.dumps(answer, ensure_ascii=False)
    for piece in hidden:
        assert piece["item"] not in everything


def test_an_opt_out_reads_like_having_no_work(agent, people):
    """Asked what they work on, someone who opted out and someone with no ticket get the same sentence.

    So the answer does not reveal who opted out of being found.
    """
    workflow, _ = agent
    opted_out = next(person for person in people.values() if not person["discoverable"])
    # Someone who can be found, and for whom no ticket and no page counts
    no_work = next(
        person
        for person in people.values()
        if person["discoverable"] and not workflow.evidence.list_pieces_of(person["id"])
    )

    for person in [opted_out, no_work]:
        answer = ask(agent, f"What does {person['name']} work on?", person["name"], "work")
        assert answer["message"] == PERSON_TEXTS["no_work"]["en"].format(name=person["name"])
        assert answer["person_card"]["work"] == []


def test_scenario_13_what_a_colleague_works_on(agent, scenarios, people):
    """ "What does Hélène Dubois work on?": her tickets and pages, grouped by system. All of it comes from the data."""
    turn = scenarios["s13"]["turns"][0]
    expected = turn["expected"]
    person = people[expected["card"]]
    answer = ask(agent, turn["question"], person["name"], "work")
    system_names = {system["id"]: system["name"] for system in CompanySource().list_systems()}
    groups = answer["person_card"]["work"]

    assert answer["status"] == "person"
    assert answer["person_card"]["id"] == person["id"]
    assert answer["message"] == f"Here is what {person['name']} works on, by system."
    # At least two systems, each with a name from the data, and exactly the tickets and pages the scenario lists
    assert len(groups) >= 2
    assert sorted(group["system"] for group in groups) == sorted(system_names[system] for system in expected["systems"])
    assert sorted(item["id"] for group in groups for item in group["items"]) == sorted(expected["work"])
    for system_id in expected["no_work_on"]:
        assert system_names[system_id] not in [group["system"] for group in groups]
    # Each line says what it is, what she did, and when, in words
    for group in groups:
        for item in group["items"]:
            assert item["title"] and item["source"] in ["Jira", "Confluence"]
            assert item["kind"] in ["wrote", "decided", "assigned", "approved"]
            assert item["text"] and item["date_text"]
    by_id = {item["id"]: item for group in groups for item in group["items"]}
    # A ticket that is still open shows its last update, and minutes show the day of the meeting
    assert by_id["CLM-296"]["date_text"] == "updated 26 October 2026"
    assert by_id["pg027"]["date_text"] == "meeting of 10 September 2026"
    assert by_id["pg027"]["text"] == 'made the decision recorded in "Claims Platform team meeting: minutes, 10 September 2026"'


def test_opting_out_hides_the_work_and_never_the_place_in_the_directory(agent, store, monkeypatch, people):
    """My rule for someone who opted out, on the three roads that can meet them. Here, a manager opts out.

    Hélène Dubois manages Sophie Martin, and four tickets and pages count for her. No manager opted out in the
    data, so she opts out in a copy of the directory (the throwaway database), as if she had done it a minute ago.
    """
    workflow, fakes = agent
    files = SeedFiles().read()
    store.replace_documents("people", files["people"])
    store.replace_documents("hr_records", files["hr_records"])
    # The readers of the directory and of the HR system use the shared store of their module: here, the throwaway one
    monkeypatch.setattr("sources.people.mongo_store", store)
    monkeypatch.setattr("sources.hr.mongo_store", store)
    subject, manager = people["p012"], people["p007"]
    store.database["people"].update_one({"id": manager["id"]}, {"$set": {"discoverable": False}})
    her_work = [piece["item"] for piece in workflow.evidence.list_pieces_of(manager["id"])]
    assert len(her_work) == 4

    # 1) Her place in the directory is not hidden: she is named as Sophie Martin's manager, with her card
    answer = ask(agent, "Who is Sophie Martin's manager?", subject["name"], "manager")
    card = answer["person_card"]
    assert answer["status"] == "person"
    assert answer["message"] == f"{subject['name']}'s manager is {manager['name']}."
    assert card["id"] == manager["id"] and card["left"] is False
    assert card["job_title"] == manager["job_title"] and card["email"] == manager["email"]
    assert card["teams_link"] and card["email_link"]
    # And the card of Sophie Martin still names her on its manager line
    assert ask(agent, "Who is Sophie Martin?", subject["name"])["person_card"]["manager"] == manager["name"]

    # 2) Her work is hidden on the person road: asked for by name, it is not listed, as for someone with no ticket
    answer = ask(agent, "What does Hélène Dubois work on?", manager["name"], "work")
    assert answer["person_card"]["id"] == manager["id"]
    assert answer["person_card"]["work"] == []
    assert answer["message"] == PERSON_TEXTS["no_work"]["en"].format(name=manager["name"])
    for item_id in her_work:
        assert item_id not in json.dumps(answer, ensure_ascii=False)

    # 3) Her work is hidden on the expert road: her tickets and pages hold up, and she is counted, never named
    fakes.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": ["checklist"]}
    fakes.found = [her_work]
    fakes.relevant = her_work
    answer = workflow.full_pipeline("Who can help me with the release checklist?")
    assert manager["id"] not in [card["id"] for card in answer["cards"]]
    assert answer["removed_opted_out"] == 1
    assert "1 person opted out of being found." in answer["note"]
    everything = json.dumps(answer, ensure_ascii=False)
    assert manager["first_name"] not in everything and manager["last_name"] not in everything


# ----------------------------------------------------------------------
# The other ways out of find_person
# ----------------------------------------------------------------------


def test_nobody_has_the_name(agent):
    """A name that nobody has: the answer says so with a fixed text, and shows no card."""
    answer = ask(agent, "Who is Nobody Atall?", "Nobody Atall")

    assert answer["status"] == "nobody_found"
    assert answer["message"] == NOBODY_FOUND_TEXTS["no_person"]["en"]
    assert answer["person_card"] == {} and answer["choices"] == [] and answer["cards"] == []


def test_a_question_with_no_name_and_nobody_shown_yet(agent):
    """ "And who's her manager?" as a first question: there is nobody "her" can mean, and the answer says so."""
    answer = ask(agent, "And who's her manager?", "", "manager")

    assert answer["status"] == "nobody_found"
    assert answer["message"] == NOBODY_FOUND_TEXTS["no_one_meant"]["en"]
    assert answer["person_card"] == {}


def test_two_people_share_a_first_name_so_the_agent_asks_which_one(agent, scenarios, people):
    """ "Tell me about Sophie.": no guess. The answer asks which one, and its choices come from the directory.

    The pause itself, and what happens when the user picks one of them, is tested in test_pause.py.
    """
    turn = scenarios["s12"]["turns"][0]
    expected = turn["expected"]
    answer = ask(agent, turn["question"], expected["first_name"])

    assert answer["status"] == "needs_details"
    assert answer["message"] == ASK_USER_TEXTS["person"]["en"]
    assert [choice["id"] for choice in answer["choices"]] == expected["choices_people"]
    assert [choice["name"] for choice in answer["choices"]] == [people[p]["name"] for p in expected["choices_people"]]
    assert answer["person_card"] == {} and answer["cards"] == []


def test_the_full_name_of_one_of_them_gives_their_card(agent, scenarios, people):
    """The second question of scenario 12, asked as a new question: "Sophie Nguyen" means one person."""
    expected = scenarios["s12"]["turns"][1]["expected"]
    answer = ask(agent, scenarios["s12"]["turns"][1]["question"], people[expected["card"]]["name"])

    assert answer["status"] == "person"
    assert answer["person_card"]["id"] == expected["card"]


def test_someone_the_directory_lost_between_two_steps(agent, monkeypatch):
    """find_person found someone, and the profile is gone when person_card asks for it: nobody has this name any more."""
    workflow, _ = agent
    # An empty result is what person_card gets for a person that the directory no longer knows
    monkeypatch.setattr(workflow.person_card_maker, "make", lambda person_id, asks: {})
    answer = ask(agent, "Who is Sophie Martin?", "Sophie Martin")

    assert answer["status"] == "nobody_found"
    assert answer["message"] == NOBODY_FOUND_TEXTS["no_person"]["en"]
    assert answer["person_card"] == {} and answer["choices"] == []


# ----------------------------------------------------------------------
# The details of a card
# ----------------------------------------------------------------------


def test_the_head_of_the_department_has_no_manager(agent, people):
    """Nobody manages the head of the department: the answer says so, and shows their own card with no manager line."""
    head = next(person for person in people.values() if not person["manager"])
    answer = ask(agent, f"Who is {head['name']}'s manager?", head["name"], "manager")

    assert answer["status"] == "person"
    assert answer["message"] == f"The directory lists no manager for {head['name']}."
    assert answer["person_card"]["id"] == head["id"]
    assert answer["person_card"]["manager"] == ""


def test_a_page_about_no_system_goes_under_general(agent, people):
    """The head of the department wrote the general technology roadmap, which is about no system.

    Its group gets a fixed name, in the language of the question, so no group of the list is nameless.
    """
    head = next(person for person in people.values() if not person["manager"])
    english = ask(agent, f"What does {head['name']} work on?", head["name"], "work")
    french = ask(agent, f"Sur quoi travaille {head['name']} ?", head["name"], "work", language="fr")

    assert [group["system"] for group in english["person_card"]["work"]] == ["General"]
    assert [group["system"] for group in french["person_card"]["work"]] == ["Général"]
    assert english["person_card"]["work"][0]["items"]


def test_someone_without_a_work_phone(agent, people):
    """The directory has no work phone for one person: the answer says so instead of showing an empty number."""
    person = next(person for person in people.values() if not person["work_phone"])
    answer = ask(agent, f"What's {person['name']}'s work phone?", person["name"], "work_phone")

    assert answer["message"] == f"The directory has no work phone for {person['name']}."
    assert answer["person_card"]["work_phone"] == ""


def test_out_of_office_only_shows_when_the_date_is_today_or_later(agent, people):
    """Sophie Martin is away until a date after the fake today: her card says so. A date in the past is not shown."""
    workflow, _ = agent
    today = workflow.answer_builder.today
    away = next(person for person in people.values() if person["out_of_office_until"] >= today)
    back = next(person for person in people.values() if "" < person["out_of_office_until"] < today)

    assert ask(agent, "?", away["name"])["person_card"]["out_of_office_until"] == away["out_of_office_until"]
    assert ask(agent, "?", back["name"])["person_card"]["out_of_office_until"] == ""


# ----------------------------------------------------------------------
# "Is she away?": one sentence that answers, before the card
# ----------------------------------------------------------------------


def test_is_she_away_gets_a_sentence_with_the_date(agent, people):
    """Someone who is out of office: the answer says so before the card, with the date in words."""
    workflow, _ = agent
    away = next(person for person in people.values() if person["out_of_office_until"] >= workflow.answer_builder.today)
    answer = ask(agent, "Is Sophie Martin out of office?", away["name"], "out_of_office")

    assert away["name"] == "Sophie Martin" and away["out_of_office_until"] == "2026-11-10"
    assert answer["status"] == "person"
    assert answer["message"] == "Sophie Martin is out of office until 10 November 2026."
    # The card is the one of the person who was asked about, with the same date on it
    assert answer["person_card"]["id"] == away["id"]
    assert answer["person_card"]["out_of_office_text"] == "Out of office until 10 November 2026"


def test_someone_who_is_not_away_gets_a_sentence_too(agent, people):
    """No absence in the directory: the answer says that the person is not marked as out of office.

    Before this sentence existed, the answer was the card alone, with no line about an absence: nothing on the
    screen answered the question.
    """
    person = people["p007"]
    answer = ask(agent, "is she on vacation or available if i wanna call her now?", person["name"], "out_of_office")

    assert person["out_of_office_until"] == ""
    assert answer["status"] == "person"
    assert answer["message"] == "Hélène Dubois is not marked as out of office."
    assert answer["person_card"]["id"] == person["id"]
    assert answer["person_card"]["out_of_office_text"] == ""
    # The question spoke of calling her: the work phone is still only shown when it is asked for
    assert answer["person_card"]["work_phone"] == ""
    assert person["work_phone"] not in json.dumps(answer, ensure_ascii=False)


def test_an_absence_that_is_over_is_no_absence(agent, people):
    """The directory still holds a date in the past for someone who is back: the answer says "not marked"."""
    workflow, _ = agent
    back = next(person for person in people.values() if "" < person["out_of_office_until"] < workflow.answer_builder.today)
    answer = ask(agent, f"Is {back['name']} away?", back["name"], "out_of_office")

    assert answer["message"] == f"{back['name']} is not marked as out of office."
    # The old date is nowhere in the answer, as the data writes it or in words
    assert back["out_of_office_until"] not in json.dumps(answer, ensure_ascii=False)
    assert "until" not in answer["message"]


def test_the_sentence_about_an_absence_never_says_why_or_available(agent, people):
    """The agent has no calendar, and the reason of an absence is in no data: the sentence says neither."""
    for name in ["Sophie Martin", "Hélène Dubois"]:
        for language in ["en", "fr"]:
            message = ask(agent, "Is she on vacation?", name, "out_of_office", language=language)["message"].lower()
            for word in ["vacation", "vacances", "available", "disponible", "because", "parce que", "sick", "malade"]:
                assert word not in message


def test_is_she_away_in_french(agent):
    """The two sentences in French. Neither needs to know whether the person is a man or a woman."""
    away = ask(agent, "Est-ce que Sophie Martin est absente ?", "Sophie Martin", "out_of_office", language="fr")
    here = ask(agent, "Est-ce que Hélène Dubois est absente ?", "Hélène Dubois", "out_of_office", language="fr")

    assert away["message"] == "Sophie Martin est à l'extérieur du bureau jusqu'au 10 novembre 2026."
    assert away["person_card"]["out_of_office_text"] == "Absence du bureau jusqu'au 10 novembre 2026"
    assert here["message"] == "L'annuaire n'indique pas d'absence du bureau pour Hélène Dubois."


def test_someone_who_opted_out_shows_this_directory_field_too(agent, people):
    """Being out of office is a field of the directory, so it is answered for someone who opted out. Their work stays hidden."""
    opted_out = next(person for person in people.values() if not person["discoverable"])
    answer = ask(agent, f"Is {opted_out['name']} away?", opted_out["name"], "out_of_office")

    assert answer["status"] == "person"
    assert answer["message"] == f"{opted_out['name']} is not marked as out of office."
    assert answer["person_card"]["work"] == []


def test_is_she_away_as_a_follow_up(agent, scenarios, people):
    """After the cards of scenario 1, "Is she away?" is about the first person shown, and the answer names her."""
    workflow, fakes = agent
    turn = scenarios["s01"]["turns"][0]
    fakes.understood = {"road": "expert", "question_type": "help", "language": "en", "search_words": ["access"]}
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    first = workflow.full_pipeline(turn["question"])
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": "en",
        "search_words": [],
        "person_name": "",
        "person_asks": "out_of_office",
    }
    answer = workflow.full_pipeline("Is she away?", first["thread_id"])

    assert first["cards"][0]["id"] == "p012"
    assert answer["message"] == "Sophie Martin is out of office until 10 November 2026."


def test_a_french_question_gets_a_french_sentence(agent, people):
    """The sentence of a person card is a fixed text, in the language of the question."""
    answer = ask(agent, "Qui est la gestionnaire de Sophie Martin ?", "Sophie Martin", "manager", language="fr")
    assert answer["language"] == "fr"
    assert answer["message"] == "Sophie Martin a pour gestionnaire Hélène Dubois."

    left = ask(agent, "Est-ce que Tom Walsh travaille encore ici ?", "Tom Walsh", "card", language="fr")
    assert left["message"] == "Tom Walsh ne travaille plus dans l'entreprise."


def test_capitals_and_accents_in_the_name_do_not_matter(agent, scenarios):
    """The name typed in lower case and without accents finds the same person."""
    expected = scenarios["s13"]["turns"][0]["expected"]
    answer = ask(agent, "what does helene dubois work on", "helene dubois", "work")
    assert answer["person_card"]["id"] == expected["card"]


# ----------------------------------------------------------------------
# The person road is plain code after understand
# ----------------------------------------------------------------------


def test_the_person_road_never_searches_and_never_asks_the_llm_again(agent):
    """After understand, a question about a colleague is answered by plain code: no search, and no other LLM step."""
    _, fakes = agent
    ask(agent, "Who is Sophie Martin's manager?", "Sophie Martin", "manager")

    assert len(fakes.questions) == 1
    assert fakes.searches == [] and fakes.verified == []
    assert fakes.rewrites == 0 and fakes.card_people == []


def test_a_personal_question_is_still_refused(agent):
    """ "Why is Sophie Martin away?" takes the failsafe road: no lookup, and no card."""
    workflow, fakes = agent
    fakes.understood = {"road": "personal", "question_type": "help", "language": "en", "search_words": []}
    answer = workflow.full_pipeline("Why is Sophie Martin away?")

    assert answer["status"] == "off_topic"
    assert answer["reason"] == "personal"
    assert answer["person_card"] == {}
