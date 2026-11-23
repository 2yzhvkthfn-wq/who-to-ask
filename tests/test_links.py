"""Free tests of the two links of a card: the Teams link and the email link. No OpenAI calls.

With fake ".example" addresses, Teams can't find the person, so a "working" Teams button means a correctly built link.
These tests check the exact text of the links.
"""

from urllib.parse import parse_qs, unquote, urlsplit

from agents.link_builder import LinkBuilder

EMAIL = "marc-andre.gagnon@tamberly.example"
# A message with what breaks a link when it is not encoded: spaces, accents, an apostrophe, and the signs & ? # % +
MESSAGE = "Bonjour Marc-André, j'ai une question : 50 % des cas & plus ? Voir #12 (a+b). Merci !"


def test_the_links_without_a_message_only_name_the_person():
    """The person card (M6) uses the same two links with no message: they only open a chat or an email to the person."""
    links = LinkBuilder().build(EMAIL)
    assert links == {
        "teams": "https://teams.microsoft.com/l/chat/0/0?users=marc-andre.gagnon@tamberly.example",
        "email": "mailto:marc-andre.gagnon@tamberly.example",
    }


def test_a_simple_message_is_encoded_in_both_links():
    """A space becomes %20, an accent becomes two %XX codes, and a comma, a "!" and an apostrophe are encoded too."""
    links = LinkBuilder().build("sophie.martin@tamberly.example", "A question", "Hi Sophie, it's me. Ça va ?")
    encoded = "Hi%20Sophie%2C%20it%27s%20me.%20%C3%87a%20va%20%3F"
    assert links["teams"] == (
        f"https://teams.microsoft.com/l/chat/0/0?users=sophie.martin@tamberly.example&message={encoded}"
    )
    assert links["email"] == f"mailto:sophie.martin@tamberly.example?subject=A%20question&body={encoded}"


def test_the_message_comes_back_whole_from_the_teams_link():
    """Reading the link the way a browser does gives back the exact message, with its special signs."""
    link = LinkBuilder().build(EMAIL, "Une question pour vous", MESSAGE)["teams"]
    parts = urlsplit(link)

    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == "https://teams.microsoft.com/l/chat/0/0"
    assert parse_qs(parts.query) == {"users": [EMAIL], "message": [MESSAGE]}


def test_the_subject_and_the_message_come_back_whole_from_the_email_link():
    """The email link holds the address, the subject, and the message, and none of them is cut by a special sign."""
    link = LinkBuilder().build(EMAIL, "Une question pour vous", MESSAGE)["email"]
    address, query = link.removeprefix("mailto:").split("?", 1)

    assert address == EMAIL
    assert parse_qs(query) == {"subject": ["Une question pour vous"], "body": [MESSAGE]}


def test_no_special_sign_of_the_message_is_left_as_it_is():
    """After the address, a link holds no space and no raw sign from the message: each one is written as %XX."""
    links = LinkBuilder().build(EMAIL, "Une question pour vous", MESSAGE)
    for link, expected_ampersands in [(links["teams"], 1), (links["email"], 1)]:
        query = link.split("?", 1)[1]
        assert " " not in query and "#" not in query and "+" not in query
        # The only "&" left is the one between the two parts of the link
        assert query.count("&") == expected_ampersands


def test_a_line_break_is_written_the_way_email_apps_expect():
    """A line break in the message becomes %0D%0A in the email link, and the message still comes back whole."""
    link = LinkBuilder().build(EMAIL, "Hello", "First line\nSecond line")["email"]
    assert "body=First%20line%0D%0ASecond%20line" in link
    assert unquote(link.split("body=")[1]) == "First line\r\nSecond line"
