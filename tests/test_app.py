"""Free tests of the terminal answer: what app.py prints for an answer. No OpenAI calls.

The answer is built in plain code from the evidence that data/scenarios.json lists for a scenario (see answer_for
in conftest.py), then printed the way app.py prints it.

Why these tests exist: a first version hid the two links of a card behind their labels, with a terminal escape code
for links. In Cursor's terminal, the lines around these codes were shown several times. So the answer is plain text.
"""

import sys

import pytest

import app

# The character that starts every terminal escape code, and the one that can end a link code
ESCAPE, BELL = "\x1b", "\x07"


def printed(capsys, monkeypatch, question: str, answer: dict) -> str:
    """What app.py prints for an answer when the screen is a real terminal."""
    # The test runner catches the output, so the program would see "not a terminal". Tell it that it is one:
    # if the answer ever depends on that again, these tests still check what a person sees on the screen
    monkeypatch.setattr(type(sys.stdout), "isatty", lambda self: True)
    app.show_answer(question, answer)
    return capsys.readouterr().out


def test_the_terminal_answer_holds_no_escape_code(capsys, monkeypatch, scenarios, answer_for):
    """Scenario 1 on a terminal: plain text only. No escape code hides an address behind a label."""
    text = printed(capsys, monkeypatch, scenarios["s01"]["turns"][0]["question"], answer_for("s01"))

    assert ESCAPE not in text
    assert BELL not in text


def test_each_card_is_printed_once_with_its_two_links_in_full(capsys, monkeypatch, scenarios, answer_for):
    """Scenario 1: three cards, each printed once, each with its Teams link and its email link written in full."""
    answer = answer_for("s01")
    text = printed(capsys, monkeypatch, scenarios["s01"]["turns"][0]["question"], answer)
    lines = text.splitlines()

    assert len(answer["cards"]) == 3
    assert text.count("Suggested message:") == 3
    for position, card in enumerate(answer["cards"], start=1):
        assert lines.count(f"{position}. {card['name']}, {card['job_title']}, {card['team']}") == 1
        # Each link has its own line, and the whole address is on it
        assert lines.count(f"   [Send on Teams] {card['teams_link']}") == 1
        assert lines.count(f"   [Send by email] {card['email_link']}") == 1


def test_the_note_comes_before_the_first_card(capsys, monkeypatch, scenarios, answer_for):
    """Scenario 1: the note about the people who were removed is shown once, just before the cards."""
    answer = answer_for("s01")
    text = printed(capsys, monkeypatch, scenarios["s01"]["turns"][0]["question"], answer)

    assert text.count("no longer works at the company") == 1
    assert text.index("no longer works at the company") < text.index(f"1. {answer['cards'][0]['name']}")


def test_a_french_answer_has_french_labels(capsys, monkeypatch, scenarios, answer_for):
    """Scenario 4: the labels of a card are in French, like the rest of the answer."""
    text = printed(capsys, monkeypatch, scenarios["s04"]["turns"][0]["question"], answer_for("s04"))

    for label in ["Courriel :", "Pourquoi :", "Références :", "Message suggéré :", "[Envoyer sur Teams]", "[Envoyer par courriel]"]:
        assert label in text
    assert ESCAPE not in text


# ----------------------------------------------------------------------
# A question about a colleague: the person card
# ----------------------------------------------------------------------


def person_answer(agent, name: str, asks: str, language: str = "en") -> dict:
    """The answer to a question about a colleague, built by the real graph with a fake understand step."""
    workflow, fakes = agent
    fakes.understood = {
        "road": "person",
        "question_type": "help",
        "language": language,
        "search_words": [],
        "person_name": name,
        "person_asks": asks,
    }
    return workflow.full_pipeline("A question about a colleague")


def test_a_person_card_is_printed_once_with_its_two_links(capsys, monkeypatch, agent):
    """The card of a colleague: the sentence, the directory fields, and two links with no message, each printed once."""
    answer = person_answer(agent, "Sophie Martin", "manager")
    card = answer["person_card"]
    lines = printed(capsys, monkeypatch, "Who is Sophie Martin's manager?", answer).splitlines()

    assert lines.count(answer["message"]) == 1
    assert lines.count(f"{card['name']}, {card['job_title']}, {card['team']}") == 1
    assert lines.count(f"   Manager: {card['manager']}") == 1
    assert lines.count(f"   Email: {card['email']}") == 1
    assert lines.count("   Languages: French, English") == 1
    assert lines.count(f"   [Open a Teams chat] {card['teams_link']}") == 1
    assert lines.count(f"   [Write an email] {card['email_link']}") == 1
    # The work phone was not asked for, so the card has no such line
    assert not any("Work phone:" in line for line in lines)


def test_the_work_of_a_colleague_is_printed_by_system(capsys, monkeypatch, agent):
    """ "What does she work on?": one group per system, and one line per ticket or page that says what she did."""
    answer = person_answer(agent, "Hélène Dubois", "work")
    text = printed(capsys, monkeypatch, "What does Hélène Dubois work on?", answer)
    lines = text.splitlines()

    for group in answer["person_card"]["work"]:
        assert lines.count(f"   {group['system']}") == 1
        for item in group["items"]:
            # A ticket shows its id, and a page its title
            assert text.count(item["id"] if item["source"] == "Jira" else item["title"]) == 1
    assert "   - wrote " in text and "   - handled " in text
    # Each line ends with its date, in words. A long line is folded, so the text is read as one line here
    one_line = " ".join(text.split())
    assert "(updated 26 October 2026)" in one_line and "(meeting of 10 September 2026)" in one_line
    assert ESCAPE not in text


def test_is_she_away_prints_its_sentence_before_the_card(capsys, monkeypatch, agent):
    """ "Is she away?": the terminal shows the sentence that answers, then the card."""
    answer = person_answer(agent, "Hélène Dubois", "out_of_office")
    text = printed(capsys, monkeypatch, "Is Hélène Dubois away?", answer)
    lines = text.splitlines()

    assert lines.count("Hélène Dubois is not marked as out of office.") == 1
    assert text.index("is not marked as out of office.") < text.index("Hélène Dubois, Team Lead, Claims Platform")
    assert not any(line.startswith("   Out of office") for line in lines)


def test_someone_who_left_is_one_sentence_and_no_card(capsys, monkeypatch, agent):
    """Someone who left: the terminal shows the sentence, and nothing that looks like a card."""
    answer = person_answer(agent, "Tom Walsh", "card")
    text = printed(capsys, monkeypatch, "Does Tom Walsh still work here?", answer)

    assert text.count("Tom Walsh no longer works at the company.") == 1
    assert "Email:" not in text and "[Open a Teams chat]" not in text and "mailto:" not in text


def test_the_choices_are_printed_when_several_people_have_the_name(capsys, monkeypatch, agent):
    """Two people are called Sophie: the terminal shows the question of the agent, then one numbered line per person."""
    answer = person_answer(agent, "Sophie", "card")
    lines = printed(capsys, monkeypatch, "Tell me about Sophie.", answer).splitlines()

    assert lines.count(answer["message"]) == 1
    # Each choice has the number to type, the name, and the job title and team that tell the two apart
    assert [choice["name"] for choice in answer["choices"]] == ["Sophie Martin", "Sophie Nguyen"]
    assert all(choice["detail"] for choice in answer["choices"])
    assert [line for line in lines if line.startswith(("   1. ", "   2. "))] == [
        f"   {number}. {choice['name']} ({choice['detail']})"
        for number, choice in enumerate(answer["choices"], start=1)
    ]


def test_the_steps_are_printed_before_the_answer(capsys, monkeypatch, agent):
    """The terminal shows what the agent did, one line per step, between the question and the answer."""
    answer = person_answer(agent, "Sophie Martin", "manager")
    text = printed(capsys, monkeypatch, "Who is Sophie Martin's manager?", answer)
    lines = text.splitlines()

    assert len(answer["steps"]) == 3
    assert lines.count("Steps:") == 1
    for step in answer["steps"]:
        assert lines.count(f"   {step}") == 1
    assert text.index("Question:") < text.index("Steps:") < text.index(answer["message"])


def test_a_french_person_card_has_french_labels(capsys, monkeypatch, agent):
    """The labels of a person card are in the language of the question."""
    answer = person_answer(agent, "Hélène Dubois", "work_phone", language="fr")
    text = printed(capsys, monkeypatch, "Quel est le téléphone de Hélène Dubois ?", answer)

    for label in ["Gestionnaire :", "Courriel :", "Langues :", "Téléphone au travail :", "[Ouvrir une conversation Teams]", "[Écrire un courriel]"]:
        assert label in text


# ----------------------------------------------------------------------
# The program itself: one question, or a conversation
# ----------------------------------------------------------------------


@pytest.fixture
def program(agent, monkeypatch):
    """app.py, ready to run in a test: it gets the agent with fake LLM steps, and the test types on its keyboard.

    Returns the fakes, and two lists: what the test will type, and how many times the agent was closed.
    """
    workflow, fakes = agent
    typed, closed = [], []
    monkeypatch.setattr(app, "AgentWorkflow", lambda: workflow)
    monkeypatch.setattr(workflow, "close", lambda: closed.append("agent"))

    def keyboard(prompt: str = "") -> str:
        # Nothing left to type is what Ctrl+Z does: the conversation ends
        if not typed:
            raise EOFError
        question = typed.pop(0)
        # The fake understand reads a question about "her" as the real one does
        if "her manager" in question:
            fakes.understood = {**fakes.understood, "road": "person", "person_name": "", "person_asks": "manager"}
        return question

    monkeypatch.setattr("builtins.input", keyboard)
    return fakes, typed, closed


def test_a_conversation_in_the_terminal(capsys, monkeypatch, program, scenarios):
    """python app.py with no question: it asks again after each answer, and the follow-up knows who "her" is."""
    fakes, typed, closed = program
    turn = scenarios["s01"]["turns"][0]
    fakes.found = [turn["expected"]["evidence"]]
    fakes.relevant = turn["expected"]["evidence"]
    typed += [turn["question"], "And who's her manager?", ""]
    monkeypatch.setattr(sys, "argv", ["app.py"])

    app.main()
    text = capsys.readouterr().out

    # The first answer has its three cards, and the second one names the person of the first card
    assert text.count("Suggested message:") == 3
    assert "Sophie Martin's manager is Hélène Dubois." in text
    # The empty line stopped the conversation, and the program closed the agent once
    assert typed == [] and closed == ["agent"]


def make_the_api_vague(fakes, scenarios) -> str:
    """Prepare the fake understand for the vague question of scenario 8, and return that question.

    It reads "the API" as the real one does (two systems fit), then the completed question as a plain request.
    """
    turn = scenarios["s08a"]["turns"][0]
    fakes.understood = {
        "road": "unclear",
        "question_type": "help",
        "language": "en",
        "search_words": ["API"],
        "unclear_systems": turn["expected"]["choices_systems"],
    }
    fakes.understood_next = [{"road": "expert", "question_type": "help", "language": "en", "search_words": ["Claims API"]}]
    return turn["question"]


def test_the_pause_in_the_terminal(capsys, monkeypatch, program, scenarios):
    """python app.py: the agent asks which system, I type the number of a choice, and the same question goes on."""
    fakes, typed, closed = program
    expected = scenarios["s08a"]["turns"][1]["expected"]
    fakes.found = [expected["evidence"]]
    fakes.relevant = expected["evidence"]
    question = make_the_api_vague(fakes, scenarios)
    typed += [question, "1", ""]
    monkeypatch.setattr(sys, "argv", ["app.py"])

    app.main()
    text = capsys.readouterr().out
    lines = text.splitlines()

    # The question of the agent, with one numbered line per choice
    assert lines.count("Several systems fit your question. Which one do you mean?") == 1
    assert [line[:17] for line in lines if line.startswith(("   1. ", "   2. "))] == ["   1. Claims API ", "   2. Policy API "]
    # My pick is shown by its name, and the run went on to the three cards of the Claims API
    assert lines.count("Your choice: Claims API") == 1
    assert text.count("Suggested message:") == 3
    assert text.index("Your choice: Claims API") < text.index("Noted your answer") < text.index("Suggested message:")
    # understand read the question, then the question with my pick. The number itself was never a question
    assert fakes.questions == [question, f"{question} I mean: Claims API."]
    assert typed == [] and closed == ["agent"]


def test_a_new_question_instead_of_a_number_is_a_new_question(capsys, monkeypatch, program, scenarios):
    """The agent waits for a number, and I type a question instead: it is answered as a new question."""
    fakes, typed, closed = program
    question = make_the_api_vague(fakes, scenarios)
    fakes.understood_next = [{"road": "not_work", "question_type": "help", "language": "en", "search_words": []}]
    # "7" is not the number of a choice (there are two), so it is a question too
    typed += [question, "What should I cook tonight?", "7", ""]
    monkeypatch.setattr(sys, "argv", ["app.py"])

    app.main()
    text = capsys.readouterr().out

    assert fakes.questions == [question, "What should I cook tonight?", "7"]
    assert "Question: What should I cook tonight?" in text and "Question: 7" in text
    assert "Your choice:" not in text


def test_one_vague_question_on_the_command_line_shows_the_choices_and_stops(capsys, monkeypatch, program, scenarios):
    """python app.py "a vague question": the choices are shown, with a line that says how to pick one, and it stops."""
    fakes, typed, closed = program
    question = make_the_api_vague(fakes, scenarios)
    # Something is waiting on the keyboard, and the program must not read it
    typed += ["1"]
    monkeypatch.setattr(sys, "argv", ["app.py"] + question.split())

    app.main()
    text = capsys.readouterr().out

    assert "   1. Claims API" in text and "   2. Policy API" in text
    assert app.PICK_HINT in text
    assert fakes.questions == [question]
    assert typed == ["1"] and closed == ["agent"]


def test_one_question_on_the_command_line_is_answered_once(capsys, monkeypatch, program):
    """python app.py "a question": one answer, and the program stops without asking for another question."""
    fakes, typed, closed = program
    fakes.understood = {"road": "not_work", "question_type": "help", "language": "en", "search_words": []}
    # Something is waiting on the keyboard, and the program must not read it
    typed += ["a question that must not be read"]
    monkeypatch.setattr(sys, "argv", ["app.py", "What", "should", "I", "cook", "tonight?"])

    app.main()
    text = capsys.readouterr().out

    assert "Question: What should I cook tonight?" in text
    assert fakes.questions == ["What should I cook tonight?"]
    assert typed == ["a question that must not be read"] and closed == ["agent"]


def test_a_failed_question_shows_one_friendly_line(capsys, monkeypatch, program):
    """The agent fails on the one question it was given: one fixed line on the screen, and an exit code that says so."""
    fakes, typed, closed = program
    fakes.found = [["pg008"]]

    def broken_verify(question: str, items: list) -> dict:
        raise RuntimeError("the secret detail of the error")

    monkeypatch.setattr(app.AgentWorkflow().verifier, "verify", broken_verify)
    monkeypatch.setattr(sys, "argv", ["app.py", "Who can help me order a laptop?"])

    with pytest.raises(SystemExit) as stop:
        app.main()
    text = capsys.readouterr().out

    assert stop.value.code == 1
    assert app.ERROR_TEXT in text and "secret detail" not in text
    assert closed == ["agent"]


def test_an_agent_that_cannot_be_built_stops_the_program(capsys, monkeypatch):
    """The agent can't be built (MongoDB or Postgres is stopped): one friendly line, and nothing is asked."""

    def no_agent():
        raise RuntimeError("Postgres is stopped")

    monkeypatch.setattr(app, "AgentWorkflow", no_agent)
    monkeypatch.setattr(sys, "argv", ["app.py"])

    with pytest.raises(SystemExit) as stop:
        app.main()
    assert stop.value.code == 1
    assert app.ERROR_TEXT in capsys.readouterr().out
