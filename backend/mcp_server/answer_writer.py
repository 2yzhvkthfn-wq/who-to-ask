from typing import Dict, List

from config.texts import CARD_LABELS, EMAIL_SUBJECT_LABEL, TOOL_TEXTS


class AnswerWriter:
    """Writes an answer of the agent as one short text, for the AI assistant that called a tool. Plain code, never the LLM.

    The text shows what the terminal shows: the fixed text or the sentence, the note, then the cards, the card of
    a colleague, or the choices. Every name, email, and date in it comes from the answer, which got them from the data.
    It leaves out what an assistant can't use: the two links of a card, and the grey step lines.
    """

    def write(self, answer: Dict) -> str:
        """Return the answer as text. Its last line is the id of the conversation, for a follow-up or a pick."""
        labels = {name: texts[answer["language"]] for name, texts in CARD_LABELS.items()}
        labels["email_subject"] = EMAIL_SUBJECT_LABEL[answer["language"]]
        # The parts of the text, from top to bottom. A blank line goes between two parts
        parts: List[str] = []

        # 1) The agent asks a question: one line first tells the assistant that the user has to pick
        if answer["choices"]:
            parts.append(TOOL_TEXTS["ask_the_user"])

        # 2) The fixed text of a refusal or of "nobody found", the question of the agent, or the sentence that
        #    answers a question about a colleague. All are already in the language of the question
        if answer["message"]:
            parts.append(answer["message"])

        # 3) The note says who the HR check removed. It comes just before the cards, and also when nobody is left
        if answer["note"]:
            parts.append(answer["note"])

        # 4) The expert cards, best first, each with its number
        for position, card in enumerate(answer["cards"], start=1):
            parts.append(self._write_card(position, card, labels))

        # 5) A question about a colleague: their card. Someone who left has none: the sentence says all there is to say
        if answer["person_card"] and not answer["person_card"]["left"]:
            parts.append(self._write_person_card(answer["person_card"], labels))

        # 6) The choices of the agent's question, each with the id to send back, then how to send it
        if answer["choices"]:
            parts.append("\n".join(self._write_choice(choice) for choice in answer["choices"]))
            parts.append(TOOL_TEXTS["how_to_pick"])

        # 7) The id of the conversation, always last
        parts.append(TOOL_TEXTS["thread"].format(thread_id=answer["thread_id"]))
        return "\n\n".join(parts)

    def _write_card(self, position: int, card: Dict, labels: Dict) -> str:
        """One expert card: who the person is, why they can help, the evidence, and the suggested message."""
        lines = [
            f"{position}. {card['name']}, {card['job_title']}, {card['team']}",
            f"   {labels['email']} {card['email']}",
        ]
        # "Out of office until 10 November 2026": the line is already written, in the language of the answer
        if card["out_of_office_text"]:
            lines.append(f"   {card['out_of_office_text']}")
        lines.append(f"   {labels['why']} {card['why']}")
        lines.append(f"   {labels['evidence']}")
        lines += self._write_evidence(card["evidence"])
        # The message keeps its two placeholders, [your name] and [your team]: the assistant can fill them in
        lines.append(f'   {labels["message"]} "{card["message"]}"')
        lines.append(f"   {labels['email_subject']} {card['subject']}")
        return "\n".join(lines)

    def _write_person_card(self, card: Dict, labels: Dict) -> str:
        """The card of one colleague: the directory fields, and what was asked for."""
        lines = [f"{card['name']}, {card['job_title']}, {card['team']}"]
        # The head of the department has no manager, and a line with no value is not written
        if card["manager"]:
            lines.append(f"   {labels['manager']} {card['manager']}")
        lines.append(f"   {labels['email']} {card['email']}")
        lines.append(f"   {labels['languages']} {', '.join(card['languages'])}")
        # The work phone is only in the card when the question asked for it
        if card["work_phone"]:
            lines.append(f"   {labels['work_phone']} {card['work_phone']}")
        if card["out_of_office_text"]:
            lines.append(f"   {card['out_of_office_text']}")

        # "What does she work on?": her tickets and pages, one group per system
        for group in card["work"]:
            lines.append("")
            lines.append(f"   {group['system']}")
            lines += self._write_evidence(group["items"])
        return "\n".join(lines)

    def _write_evidence(self, items: List[Dict]) -> List[str]:
        """One line per ticket or page: what the person did, in words, and its date."""
        # 'wrote "Claims API: Access Guide" (updated 15 September 2026)'
        return [f"   - {item['text']} ({item['date_text']})" for item in items]

    def _write_choice(self, choice: Dict) -> str:
        """One choice of the agent's question: its name, its id, and the line that tells it apart."""
        line = TOOL_TEXTS["choice"].format(name=choice["name"], id=choice["id"])
        # Someone who left only shows a name, so a choice can have no detail
        return f"{line}: {choice['detail']}" if choice["detail"] else line
