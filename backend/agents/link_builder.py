from typing import Dict
from urllib.parse import quote

from config.constants import TEAMS_CHAT_URL


class LinkBuilder:
    """Builds the two links of a card. A link only opens the user's own Teams or email app: the agent never sends anything."""

    def build(self, email: str, subject: str = "", message: str = "") -> Dict:
        """Return the Teams link and the email link for one person, with the message already filled in if there is one."""
        # quote() writes every special character as %XX (a space becomes %20, "é" becomes %C3%A9),
        # so a message with spaces, accents, or a "&" can't break the link
        address = quote(email, safe="@")
        teams_link = f"{TEAMS_CHAT_URL}?users={address}"
        email_link = f"mailto:{address}"
        if message:
            teams_link += f"&message={quote(message, safe='')}"
            # An email app expects a line break as %0D%0A
            body = message.replace("\r\n", "\n").replace("\n", "\r\n")
            email_link += f"?subject={quote(subject, safe='')}&body={quote(body, safe='')}"
        return {"teams": teams_link, "email": email_link}
