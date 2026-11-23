"""Free tests of understand: what happens around the LLM call. No OpenAI calls.

A small fake stands in for the model, so these tests check our own code: the safe default, and the tidy-up of a reply.
The tests of what the real model answers are in test_agent.py, and they are paid.
"""

from typing import List, Optional

from agents.request_reader import RequestReader, Understanding
from config.constants import MAX_SYSTEM_CHOICES
from sources import CompanySource, PeopleSource

SAFE_DEFAULT = {
    "road": "expert",
    "question_type": "help",
    "language": "en",
    "search_words": [],
    "unclear_systems": [],
    "named_systems": [],
    "no_topic": False,
    "person_name": "",
    "person_asks": "card",
}


class FakeLlm:
    """Stands in for the model. It gives back the reply it was built with, or fails like OpenAI on a bad day."""

    def __init__(self, reply: Optional[Understanding] = None, fails: bool = False):
        self.reply = reply
        self.fails = fails

    def invoke(self, prompt: str) -> Optional[Understanding]:
        if self.fails:
            raise RuntimeError("no connection")
        return self.reply


def reader_with(llm: FakeLlm) -> RequestReader:
    """A request reader that asks the fake instead of OpenAI."""
    reader = RequestReader()
    reader.llm = llm
    return reader


def test_a_failed_call_gives_the_safe_default():
    """OpenAI can't be reached: the request is treated as a "help" question for an expert, never refused by mistake."""
    reader = reader_with(FakeLlm(fails=True))
    assert reader.read("Who decided to buy new laptops?") == SAFE_DEFAULT


def test_a_missing_reply_gives_the_safe_default():
    """The model replied, but nothing usable came back: the same safe default."""
    reader = reader_with(FakeLlm(reply=None))
    assert reader.read("Who decided to buy new laptops?") == SAFE_DEFAULT


def test_a_good_reply_is_passed_on_and_tidied():
    """The labels are passed on as they are. The search words lose their extra spaces and their empty entries."""
    reply = Understanding(
        reason="The colleague asks who fixed the laptop order form.",
        road="expert",
        question_type="did",
        language="fr",
        search_words=["  laptop order form ", "", "   "],
        unclear_systems=[],
        named_systems=[],
        person_name="",
        person_asks="card",
    )
    assert reader_with(FakeLlm(reply=reply)).read("Qui a corrigé le laptop order form ?") == {
        "road": "expert",
        "question_type": "did",
        "language": "fr",
        "search_words": ["laptop order form"],
        "unclear_systems": [],
        "named_systems": [],
        "no_topic": False,
        "person_name": "",
        "person_asks": "card",
    }


def test_a_request_about_a_colleague_gives_the_name_and_what_is_asked():
    """The person road: the name comes back as the request writes it, on one line, with what is asked."""
    reply = Understanding(
        reason="The colleague asks who manages Maria Lopez.",
        road="person",
        question_type="help",
        language="en",
        search_words=[],
        unclear_systems=[],
        named_systems=[],
        person_name="  Maria \n Lopez ",
        person_asks="manager",
    )
    understood = reader_with(FakeLlm(reply=reply)).read("Who is Maria Lopez's manager?")

    assert understood["road"] == "person"
    assert understood["person_name"] == "Maria Lopez"
    assert understood["person_asks"] == "manager"


def test_a_request_about_an_absence_is_passed_on():
    """ "Is she away?": the fifth thing a request can ask about a colleague, passed on as it is, with no name here."""
    reply = Understanding(
        reason="The colleague asks whether someone is away.",
        road="person",
        question_type="help",
        language="en",
        search_words=[],
        unclear_systems=[],
        named_systems=[],
        person_name="",
        person_asks="out_of_office",
    )
    understood = reader_with(FakeLlm(reply=reply)).read("Is she away?")

    assert understood["road"] == "person"
    assert understood["person_name"] == ""
    assert understood["person_asks"] == "out_of_office"


def test_the_person_answers_are_only_kept_on_the_person_road():
    """The model filled in a name for a request that looks for an expert: the name is dropped, so no later step uses it."""
    reply = Understanding(
        reason="The colleague asks who approved a request.",
        road="expert",
        question_type="did",
        language="en",
        search_words=["access request"],
        unclear_systems=[],
        named_systems=[],
        person_name="Maria Lopez",
        person_asks="work",
    )
    understood = reader_with(FakeLlm(reply=reply)).read("Who approved Maria Lopez's access request?")

    assert understood["person_name"] == ""
    assert understood["person_asks"] == "card"


def test_the_name_in_a_question_stays_out_of_the_log_of_the_screen(screen_log):
    """The name in a question may be anyone's: the screen's log lines say that a name was given, and never which one."""
    reply = Understanding(
        reason="The colleague asks who manages Maria Lopez.",
        road="person",
        question_type="help",
        language="en",
        search_words=[],
        unclear_systems=[],
        named_systems=[],
        person_name="Maria Lopez",
        person_asks="manager",
    )
    reader_with(FakeLlm(reply=reply)).read("Who is Maria Lopez's manager?")
    shown = "\n".join(screen_log)

    assert 'road "person"' in shown and "with a name" in shown
    # The name, and the reason that repeats it, only go to app.log
    assert "Maria" not in shown and "Lopez" not in shown


# ----------------------------------------------------------------------
# The road "unclear": a general word that fits several systems. The choices must be real systems
# ----------------------------------------------------------------------


def unclear_reply(systems: List[str], road: str = "unclear") -> Understanding:
    """What the model replies for a request with a general word, with these systems to choose from."""
    return Understanding(
        reason="The colleague needs help with a tool, and the word fits several systems.",
        road=road,
        question_type="help",
        language="en",
        search_words=["tool"],
        unclear_systems=systems,
        named_systems=[],
        person_name="",
        person_asks="card",
    )


def test_a_general_word_gives_the_systems_to_choose_from():
    """The model says "unclear" and names two systems of the data: both come back, as ids, with the search words."""
    understood = reader_with(FakeLlm(reply=unclear_reply(["claims_api", "policy_api"]))).read("Who knows the tool?")

    assert understood["road"] == "unclear"
    assert understood["unclear_systems"] == ["claims_api", "policy_api"]
    assert understood["search_words"] == ["tool"]


def test_a_system_that_does_not_exist_is_never_a_choice():
    """The choices come from the data: an id that the model made up is dropped, and so is an id it gave twice."""
    reply = unclear_reply(["claims_api", "the_made_up_api", "policy_api", "claims_api", "Claims API"])
    understood = reader_with(FakeLlm(reply=reply)).read("Who knows the tool?")

    assert understood["road"] == "unclear"
    assert understood["unclear_systems"] == ["claims_api", "policy_api"]


def test_fewer_than_two_real_systems_means_no_question():
    """With one real system, or none, there is nothing to choose from: the request is searched as it is."""
    for systems in [["claims_api"], ["claims_api", "the_made_up_api"], ["the_made_up_api"], []]:
        understood = reader_with(FakeLlm(reply=unclear_reply(systems))).read("Who knows the tool?")
        assert understood["road"] == "expert"
        assert understood["unclear_systems"] == []
        # The search words are kept: the expert road needs them
        assert understood["search_words"] == ["tool"]


def test_a_word_that_fits_too_many_systems_means_no_question():
    """A word that fits more systems than the agent offers is too general to ask about: no question either."""
    every_system = [system["id"] for system in CompanySource().list_systems()]
    assert len(every_system) > MAX_SYSTEM_CHOICES

    at_the_limit = reader_with(FakeLlm(reply=unclear_reply(every_system[:MAX_SYSTEM_CHOICES]))).read("Who knows it?")
    over_the_limit = reader_with(FakeLlm(reply=unclear_reply(every_system[: MAX_SYSTEM_CHOICES + 1]))).read("Who knows it?")

    assert at_the_limit["road"] == "unclear" and len(at_the_limit["unclear_systems"]) == MAX_SYSTEM_CHOICES
    assert over_the_limit["road"] == "expert" and over_the_limit["unclear_systems"] == []


def test_the_systems_are_only_kept_on_the_unclear_road():
    """The model named systems for a request that it sends to the expert road: they are dropped, so nothing is asked."""
    reply = unclear_reply(["claims_api", "policy_api"], road="expert")
    understood = reader_with(FakeLlm(reply=reply)).read("Who knows the tool?")

    assert understood["road"] == "expert"
    assert understood["unclear_systems"] == []


# ----------------------------------------------------------------------
# The systems that a request names: the second level of an answer starts from them. They must be real systems
# ----------------------------------------------------------------------


def named_reply(systems: List[str], road: str = "expert") -> Understanding:
    """What the model replies for a request that names these systems."""
    return Understanding(
        reason="The colleague has a problem with a tool, and the request names its system.",
        road=road,
        question_type="help",
        language="en",
        search_words=["tool", "slow"],
        unclear_systems=[],
        named_systems=systems,
        person_name="",
        person_asks="card",
    )


def test_the_systems_that_a_request_names_are_passed_on():
    """The model names one system of the data, or several: they come back as ids, in the order given."""
    one = reader_with(FakeLlm(reply=named_reply(["claims_workbench"]))).read("The tool is slow. Who can help?")
    two = reader_with(FakeLlm(reply=named_reply(["customer_portal", "claims_intake"]))).read("The tool is slow. Who can help?")

    assert one["road"] == "expert" and one["named_systems"] == ["claims_workbench"]
    assert two["named_systems"] == ["customer_portal", "claims_intake"]


def test_a_named_system_that_does_not_exist_is_dropped():
    """The named systems come from the data: an id that the model made up is dropped, and so is an id it gave twice."""
    reply = named_reply(["claims_workbench", "the_mobile_app", "claims_workbench", "Claims Workbench"])
    understood = reader_with(FakeLlm(reply=reply)).read("The tool is slow. Who can help?")

    assert understood["named_systems"] == ["claims_workbench"]


def test_the_named_systems_are_only_kept_on_the_expert_road():
    """A request that is refused, or that is about a colleague, names no system for the next steps."""
    for road in ["person", "not_work", "personal"]:
        understood = reader_with(FakeLlm(reply=named_reply(["claims_workbench"], road=road))).read("The tool is slow.")
        assert understood["named_systems"] == []


def test_an_unclear_request_names_no_system():
    """A general word that fits several systems names none of them: the agent asks, and the user picks."""
    reply = unclear_reply(["claims_api", "policy_api"])
    reply.named_systems = ["claims_api"]
    understood = reader_with(FakeLlm(reply=reply)).read("Who knows the tool?")

    assert understood["road"] == "unclear"
    assert understood["named_systems"] == []


# ----------------------------------------------------------------------
# A request with no topic: no search word, and no system. Plain code decides it, from the answers of the model
# ----------------------------------------------------------------------


def topic_reply(search_words: List[str], systems: List[str], road: str = "expert") -> Understanding:
    """What the model replies for a request with these search words and these named systems."""
    return Understanding(
        reason="The colleague needs help.",
        road=road,
        question_type="help",
        language="en",
        search_words=search_words,
        unclear_systems=[],
        named_systems=systems,
        person_name="",
        person_asks="card",
    )


def test_no_search_word_and_no_system_means_no_topic():
    """ "I need help. Who should I ask?": the model finds no search word and names no system, so there is no topic."""
    understood = reader_with(FakeLlm(reply=topic_reply([], []))).read("I need help. Who should I ask?")

    assert understood["road"] == "expert"
    assert understood["no_topic"] is True
    # Words made of spaces are no words
    assert reader_with(FakeLlm(reply=topic_reply(["  ", ""], []))).read("I need help.")["no_topic"] is True


def test_a_search_word_or_a_named_system_is_a_topic():
    """One search word is a topic, and so is one system that the request names. Both are searched as before."""
    with_a_word = reader_with(FakeLlm(reply=topic_reply(["printer"], []))).read("The printer is down. Who can help?")
    with_a_system = reader_with(FakeLlm(reply=topic_reply([], ["claims_api"]))).read("Who can help me with the Claims API?")
    # A system that does not exist is dropped, and then nothing is left: no topic
    with_a_made_up_system = reader_with(FakeLlm(reply=topic_reply([], ["the_mobile_app"]))).read("Who can help?")

    assert with_a_word["no_topic"] is False
    assert with_a_system["no_topic"] is False and with_a_system["named_systems"] == ["claims_api"]
    assert with_a_made_up_system["no_topic"] is True


def test_only_a_request_for_an_expert_can_have_no_topic():
    """A refusal and a question about a colleague have no search words either: they are not "no topic"."""
    for road in ["person", "not_work", "personal"]:
        assert reader_with(FakeLlm(reply=topic_reply([], [], road=road))).read("A request")["no_topic"] is False
    # A general word that fits several systems is a question for the user, not a request with no topic
    assert reader_with(FakeLlm(reply=unclear_reply(["claims_api", "policy_api"]))).read("Who knows the tool?")["no_topic"] is False


def test_a_failed_call_is_not_a_request_with_no_topic():
    """OpenAI can't be reached: nothing is known about the request, so it is searched, and nothing is asked back."""
    assert reader_with(FakeLlm(fails=True)).read("Who decided to buy new laptops?")["no_topic"] is False
    assert reader_with(FakeLlm(reply=None)).read("Who decided to buy new laptops?")["no_topic"] is False


# ----------------------------------------------------------------------
# The prompt
# ----------------------------------------------------------------------


def test_the_prompt_asks_which_systems_the_request_names():
    """understand also says which systems the request names, and it must never add one that the request does not name."""
    prompt = RequestReader().generate_prompt("Who looks after the laptop order form?")

    assert "- named_systems:" in prompt
    assert "Never add a system that the request does not name" in prompt


def test_the_prompt_holds_the_request_and_no_test_question(scenarios):
    """The prompt shows the request. Its examples are made up: it never quotes a question of the demo scenarios."""
    prompt = RequestReader().generate_prompt("Who looks after the laptop order form?")
    assert "Who looks after the laptop order form?" in prompt
    for case in scenarios.values():
        for turn in case["turns"]:
            assert turn["question"] not in prompt


def test_the_prompt_lists_every_system_by_id_and_name():
    """understand gets the list of the systems, so it can spot a general word that fits several of them."""
    prompt = RequestReader().generate_prompt("Who looks after the laptop order form?")
    systems = CompanySource().list_systems()

    assert len(systems) == 16
    for system in systems:
        assert f"- {system['id']}: {system['name']}" in prompt


def test_the_prompt_names_nobody_of_the_company():
    """understand gets the systems, and never people: the names in its examples are made up, and nobody of the directory has them."""
    prompt = RequestReader().generate_prompt("Who looks after the laptop order form?")
    for person in PeopleSource().list_people():
        assert person["first_name"] not in prompt
        assert person["last_name"] not in prompt
