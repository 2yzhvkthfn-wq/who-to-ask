"""Terminal entry point: ask a question, and see who can help, or what the directory says about a colleague.

Run it from the backend folder, with one question:
    python app.py "Who can help me get access to the Claims API?"
    python app.py "Who decided to move the policy database to the cloud?"
    python app.py "Qui peut m'aider avec la traduction du portail client ?"
    python app.py "Who is Sophie Martin's manager?"
    python app.py "What's the weather in Montreal today?"

Or with no question, for a conversation: it asks, answers, and asks again, and a follow-up can say "her".
When the agent asks a question back ("Which one do you mean?"), type the number of a choice:
    python app.py

The company data is read from MongoDB. Fill it once from the data folder, and again after a change to a file:
    python -m scripts.seed_mongodb
"""

import sys
import textwrap
from typing import Dict, List, Optional

from langchain_core.tracers.langchain import wait_for_all_tracers

from agents import AgentWorkflow
from config.texts import CARD_LABELS, TITLE_QUOTES
from utils.logging import logger


# What the screen shows when the agent fails. The details of the error go to the log
ERROR_TEXT = "Sorry, something went wrong and I could not answer. The details are in app.log."
# What the screen says after the agent's question when the program was given one question: it can't wait for a pick
PICK_HINT = "(To pick one: run python app.py with no question, ask again, and type the number of your choice.)"


def main() -> None:
    """Answer the question of the command line. With no question: hold a conversation, until an empty line."""
    # 0) Accents must also come out right when the answer is sent to a file instead of the screen
    sys.stdout.reconfigure(encoding="utf-8")

    # 1) A question on the command line means one answer. No question means a conversation
    only_question = " ".join(sys.argv[1:]).strip()

    # 2) Build the agent once. The details of an error go to the log, and the screen gets a friendly line
    try:
        workflow = AgentWorkflow()
    except Exception as e:
        logger.error(f"The agent could not be built: {e}")
        print(ERROR_TEXT)
        sys.exit(1)

    # 3) Ask, answer, and ask again. Every question of this run belongs to one conversation: the first answer
    #    gives its id (thread_id), and the next questions send it back, so a follow-up can say "her".
    #    choices holds the choices of the agent's question, when the last answer was one
    thread_id, failed, choices = None, False, []
    if not only_question:
        print('Ask a question, for example: "Who can help me get access to the Claims API?"')
    try:
        while True:
            question = only_question or read_question(waiting_for_a_pick=bool(choices))
            if not question:
                break
            # The number of a choice is the answer to the agent's question: the run that is paused goes on.
            # Anything else is a new question
            picked = pick_choice(question, choices)
            try:
                if picked:
                    result = workflow.full_pipeline(picked["id"], thread_id, is_answer=True)
                else:
                    result = workflow.full_pipeline(question, thread_id)
            except Exception as e:
                logger.error(f"The agent could not answer: {e}")
                print(ERROR_TEXT)
                failed, choices = True, []
            else:
                thread_id, choices = result["thread_id"], result["choices"]
                # print() is this program's screen: the answer is not a log line
                show_answer(picked["name"] if picked else question, result, is_pick=bool(picked))
            if only_question:
                if choices:
                    print()
                    print(PICK_HINT)
                break
    finally:
        # LangSmith sends its traces in the background: wait for them before the program ends.
        # Then close the connections to Postgres, where the conversations are saved
        wait_for_all_tracers()
        workflow.close()

    # 4) A program that was given one question says with its exit code whether it could answer
    if only_question and failed:
        sys.exit(1)


def read_question(waiting_for_a_pick: bool = False) -> str:
    """Read the next question of a conversation from the keyboard. An empty line, Ctrl+Z, or Ctrl+C ends it."""
    prompt = "Your choice (its number), or a new question" if waiting_for_a_pick else "Your question"
    try:
        return input(f"\n{prompt} (Enter to stop): ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""


def pick_choice(typed: str, choices: List[Dict]) -> Optional[Dict]:
    """The choice that a typed number names: "2" is the second choice. Anything else names no choice."""
    if typed.isdecimal() and 1 <= int(typed) <= len(choices):
        return choices[int(typed) - 1]
    return None


def show_answer(question: str, result: Dict, is_pick: bool = False) -> None:
    """Print the steps, the text of the answer, the note, then the cards, the card of a colleague, or the choices."""
    print()
    # is_pick: the user did not type a question, but picked one of the agent's choices
    print(f"{'Your choice' if is_pick else 'Question'}: {question}")

    # What the agent did, one short line per step: the same lines as the grey step lines of the page
    if result["steps"]:
        print()
        print("Steps:")
        for step in result["steps"]:
            print(f"   {step}")

    # A refusal, "nobody found", and a question back to the user are fixed texts. For a question about a colleague,
    # it is the sentence that answers it. All are already in the language of the question
    if result["message"]:
        print()
        print(result["message"])

    # The note says who the HR check removed. It comes just before the cards, and it is also shown when nobody is left
    if result["note"]:
        print()
        print(textwrap.fill(result["note"], width=100))

    for position, card in enumerate(result["cards"], start=1):
        print()
        show_card(position, card, result["language"])

    # A question about a colleague: their card. Someone who left has none: the sentence above says all there is to say
    if result["person_card"] and not result["person_card"]["left"]:
        print()
        show_person_card(result["person_card"], result["language"])

    # The agent asks a question: its choices, each with a number to type and one line that tells it apart
    for number, choice in enumerate(result["choices"], start=1):
        detail = f" ({choice['detail']})" if choice["detail"] else ""
        print(textwrap.fill(f"{number}. {choice['name']}{detail}", width=100, initial_indent="   ", subsequent_indent="      "))


def show_card(position: int, card: Dict, language: str) -> None:
    """Print one card: who the person is, why they can help, the evidence, the suggested message, and the two links."""
    labels = {name: texts[language] for name, texts in CARD_LABELS.items()}

    print(f"{position}. {card['name']}, {card['job_title']}, {card['team']}")
    print(f"   {labels['email']} {card['email']}")
    # "Out of office until 10 November 2026": the line is already written, in the language of the question
    if card["out_of_office_text"]:
        print(f"   {card['out_of_office_text']}")
    print(textwrap.fill(f"{labels['why']} {card['why']}", width=100, initial_indent="   ", subsequent_indent="   "))
    print(f"   {labels['evidence']} {describe_evidence(card, language)}")
    print()

    # The message is plain text, so it can be copied even where a link does not open
    print(f"   {labels['message']}")
    print(textwrap.fill(f'"{card["message"]}"', width=100, initial_indent="   ", subsequent_indent="    "))
    print()
    show_links(labels["teams"], card["teams_link"], labels["send_email"], card["email_link"])


def show_person_card(card: Dict, language: str) -> None:
    """Print the card of one colleague: the directory fields, what was asked for, and the two links."""
    labels = {name: texts[language] for name, texts in CARD_LABELS.items()}

    print(f"{card['name']}, {card['job_title']}, {card['team']}")
    # The head of the department has no manager, and a line with no value is not printed
    if card["manager"]:
        print(f"   {labels['manager']} {card['manager']}")
    print(f"   {labels['email']} {card['email']}")
    print(f"   {labels['languages']} {', '.join(card['languages'])}")
    # The work phone is only in the card when the question asked for it
    if card["work_phone"]:
        print(f"   {labels['work_phone']} {card['work_phone']}")
    if card["out_of_office_text"]:
        print(f"   {card['out_of_office_text']}")

    # "What does she work on?": her tickets and pages, one group per system
    for group in card["work"]:
        print()
        print(f"   {group['system']}")
        for item in group["items"]:
            # One ticket or page, in words, with its date: wrote "a page" (updated 14 October 2026)
            line = f"{item['text']} ({item['date_text']})"
            print(textwrap.fill(line, width=100, initial_indent="   - ", subsequent_indent="     "))
    print()
    show_links(labels["open_teams"], card["teams_link"], labels["write_email"], card["email_link"])


def describe_evidence(card: Dict, language: str) -> str:
    """The evidence of a card on one line: "a page" (Confluence), CLM-212, CLM-245 (Jira)."""
    # A page is shown by its title, and a ticket by its id. dict.fromkeys drops a ticket that is there twice
    pages = [
        TITLE_QUOTES[language].format(title=label["title"])
        for label in card["evidence"]
        if label["source"] == "Confluence"
    ]
    tickets = list(dict.fromkeys(label["id"] for label in card["evidence"] if label["source"] == "Jira"))
    parts = []
    if pages:
        parts.append(f"{', '.join(pages)} (Confluence)")
    if tickets:
        parts.append(f"{', '.join(tickets)} (Jira)")
    return ", ".join(parts)


def show_links(teams_label: str, teams_link: str, email_label: str, email_link: str) -> None:
    """Print the two links of a card. The agent sends nothing: a link only opens the user's own Teams or email app."""
    # The addresses are written in full, as plain text, on the screen and in a file alike.
    # A first version hid each address behind its label with a terminal escape code for links (OSC 8).
    # In Cursor's terminal, the lines around these codes were then shown several times, so no such code is written
    print(f"   [{teams_label}] {teams_link}")
    print(f"   [{email_label}] {email_link}")


if __name__ == "__main__":
    main()
