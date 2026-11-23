import os
from typing import Dict, Iterator, List, Optional, TypedDict
from uuid import uuid4

import psycopg
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config.constants import MAX_RETRIES, POSTGRES_POOL_SIZE, POSTGRES_TIMEOUT_SECONDS
from config.settings import settings
from config.texts import FAILSAFE_TEXTS, NOBODY_FOUND_TEXTS, PICKED_SYSTEM
from sources import EvidenceSource
from utils.logging import logger

from .answer_builder import AnswerBuilder
from .card_writer import CardWriter
from .evidence_searcher import EvidenceSearcher
from .evidence_verifier import EvidenceVerifier
from .hr_checker import HrChecker
from .person_card_maker import PersonCardMaker
from .person_finder import PersonFinder
from .ranker import Ranker
from .request_reader import RequestReader
from .search_rewriter import SearchRewriter
from .step_writer import StepWriter


class AgentState(TypedDict):
    """What the graph knows about one question. Plain data only: labels, ids, and the short texts the agent wrote itself.

    It never holds the text of a ticket or a page, and it holds people as ids: the answer gets their names at the end.
    The memory saves this state under the id of its conversation. Every key starts fresh at each question,
    except the last one, shown_people, which is what a conversation remembers.
    """

    question: str  # what the user asked. After the agent's question, ask_user adds the system the user picked
    road: str  # understand: "expert", "person", or "unclear", or the reason for a refusal: "not_work" or "personal"
    question_type: str  # understand: "help", "did", or "decided". It decides which evidence counts first
    language: str  # understand: the language of the question, "en" or "fr"
    search_words: List[str]  # understand: the words that name the topic of the question. rewrite replaces them
    unclear_systems: List[str]  # understand: the systems that a general word of the question fits ("the API")
    named_systems: List[str]  # understand: the systems that the question names. After the user's pick: the system picked
    no_topic: bool  # understand: the question looks for an expert and names no topic: no search word, and no system
    person_name: str  # understand: the name of the colleague, as the question writes it ("" for "her" or "him")
    person_asks: str  # understand: what is asked about the colleague ("card", "manager", "work_phone", "work", "out_of_office")
    asked: str  # ask_user: what the agent asked the user: "system" or "person" ("" when it asked nothing)
    picked: str  # ask_user: the choice the user picked, as the id of a system or of a person
    attempts: int  # rewrite: how many times the search was tried again with new words (at most once)
    message: str  # failsafe and nobody_found: the fixed text of the answer
    found_ids: List[str]  # search: the tickets and pages found
    checked_ids: List[str]  # verify: every ticket and page it has judged, so a retry never judges one twice
    evidence_ids: List[str]  # verify: the ones that are really about the question. same_system: the ones of the system
    level: str  # "exact": the evidence is about the exact need. same_system sets "system": it is only about the system
    ranking: List[Dict]  # rank: one entry per person, best first
    recommended: List[Dict]  # check_hr: the people to recommend, up to three
    removed_left: List[str]  # check_hr: the people removed because they left the company
    removed_opted_out: List[str]  # check_hr: the people removed because they opted out
    cards: List[Dict]  # write_cards: for each recommended person, the three texts the LLM wrote (empty if unusable)
    person_matches: List[str]  # find_person: the people the name can mean
    person_card: Dict  # person_card: what the answer may show about the colleague, as ids and labels
    step: str  # every node: one short line that says what it just did, for the grey step lines
    shown_people: List[str]  # write_cards and person_card: the people shown so far, the most recent first


class AgentWorkflow:
    """The agent as a LangGraph graph: understand reads the request and picks its road.

    The expert road: search, verify (with one retry through rewrite), rank, check_hr, then write_cards or nobody_found.
    When nothing is about the exact need and the request names a system, same_system takes the tickets and pages
    of that system before rank: a second level of answer, which the answer labels as such.
    A request for an expert that names no topic at all is not searched: nobody_found asks what the user needs.
    The person road: find_person, then person_card or nobody_found. failsafe refuses the other requests.
    ask_user pauses the run to ask the user one question, and the answer goes back to understand.
    """

    def __init__(self):
        # 1) Tracing first, so that everything after it is traced
        self._setup_tracing()

        # 2) The memory of the conversations: Postgres when POSTGRES_URI is set, the program's own memory otherwise.
        #    It comes before the search index: if Postgres does not answer, the app stops before any OpenAI call
        self.pool: Optional[ConnectionPool] = None
        self.checkpointer = self._build_checkpointer()

        try:
            # 3) The classes behind the nodes, built once. The search indexes the same evidence items the nodes read
            self.reader = RequestReader()
            self.evidence = EvidenceSource()
            self.searcher = EvidenceSearcher(self.evidence.list_items())
            self.verifier = EvidenceVerifier()
            self.rewriter = SearchRewriter()
            self.ranker = Ranker()
            self.hr_checker = HrChecker()
            self.card_writer = CardWriter()
            self.person_finder = PersonFinder()
            self.person_card_maker = PersonCardMaker(self.evidence)

            # 4) The class that writes the grey step lines, and the class that turns the ids of the final state
            #    into the answer: names, emails, links, and the note
            self.step_writer = StepWriter()
            self.answer_builder = AnswerBuilder(self.evidence)

            # 5) The graph, compiled once, with its memory
            self.compiled_workflow = self.build_workflow()
        except Exception:
            # The agent can't be built (MongoDB or OpenAI did not answer): nobody will call close() on it,
            # so the connections to Postgres that were just opened are closed here. The error goes on as it is
            self.close()
            raise

    def build_workflow(self):
        """Declare the nodes and the arrows between them, then compile the graph."""
        workflow = StateGraph(AgentState)

        # The nodes: each one is a thin method below
        workflow.add_node("understand", self._understand_step)
        workflow.add_node("failsafe", self._failsafe_step)
        workflow.add_node("search", self._search_step)
        workflow.add_node("verify", self._verify_step)
        workflow.add_node("rewrite", self._rewrite_step)
        workflow.add_node("same_system", self._same_system_step)
        workflow.add_node("rank", self._rank_step)
        workflow.add_node("check_hr", self._check_hr_step)
        workflow.add_node("write_cards", self._write_cards_step)
        workflow.add_node("nobody_found", self._nobody_found_step)
        workflow.add_node("find_person", self._find_person_step)
        workflow.add_node("person_card", self._person_card_step)
        workflow.add_node("ask_user", self._ask_user_step)

        # The arrows. After understand, verify, check_hr, and find_person, a router picks the road
        workflow.add_edge(START, "understand")
        workflow.add_conditional_edges(
            "understand",
            self._decide_after_understand,
            {
                "expert": "search",
                "person": "find_person",
                "unclear": "ask_user",
                "off_topic": "failsafe",
                # A request with no topic: nothing is searched, and nobody_found asks what the user needs
                "no_topic": "nobody_found",
            },
        )
        workflow.add_edge("failsafe", END)
        workflow.add_edge("search", "verify")
        workflow.add_conditional_edges(
            "verify",
            self._decide_after_verify,
            {"evidence_holds": "rank", "retry": "rewrite", "same_system": "same_system", "nothing_holds": "nobody_found"},
        )
        # The retry is a loop: rewrite gives new words, and the search runs again
        workflow.add_edge("rewrite", "search")
        # The second level: the tickets and pages of the system that the request names go to the same ranking
        workflow.add_edge("same_system", "rank")
        workflow.add_edge("rank", "check_hr")
        workflow.add_conditional_edges(
            "check_hr",
            self._decide_after_check_hr,
            {"people_left": "write_cards", "everyone_removed": "nobody_found"},
        )
        workflow.add_edge("write_cards", END)
        workflow.add_edge("nobody_found", END)
        # The person road: one person has the name, several have it, or nobody has it
        workflow.add_conditional_edges(
            "find_person",
            self._decide_after_find_person,
            {"one_match": "person_card", "several_matches": "ask_user", "no_match": "nobody_found"},
        )
        workflow.add_edge("person_card", END)
        # The question to the user is a loop too: the run pauses in ask_user, and the user's answer goes back
        # to understand, which reads the request again
        workflow.add_edge("ask_user", "understand")
        # The checkpointer is the memory: it saves the state after each step, under the id of the conversation.
        # It is also what makes the pause possible: a paused run waits there for the user's answer
        return workflow.compile(checkpointer=self.checkpointer)

    def full_pipeline(
        self,
        question: str,
        thread_id: Optional[str] = None,
        is_answer: bool = False,
        user_name: str = "",
        user_team: str = "",
    ) -> Dict:
        """Run the graph on one question. Return the answer: its status, the cards or the fixed text, and the note.

        thread_id is the id of the conversation. Give the thread_id of an earlier answer to ask a follow-up:
        the agent then knows who "her" is. Without one, a new conversation starts, and the answer says its id.
        When the answer has the status "needs_details", the run is paused: the agent asks one question.
        To answer it, call again with the id of a choice as the question, the same thread_id, and is_answer=True.
        user_name and user_team are optional: they fill the first sentence of the suggested messages.
        """
        # The same run as stream_pipeline, for a caller that only wants the end: the steps are in the answer too
        answer: Dict = {}
        for event in self.stream_pipeline(question, thread_id, is_answer, user_name, user_team):
            if event["type"] == "answer":
                answer = event["answer"]
        return answer

    def stream_pipeline(
        self,
        question: str,
        thread_id: Optional[str] = None,
        is_answer: bool = False,
        user_name: str = "",
        user_team: str = "",
    ) -> Iterator[Dict]:
        """Run the graph on one question, and give what happens while it happens.

        It gives one event per finished step, {"type": "step", "text": ...}, then one last event with the answer,
        {"type": "answer", "answer": ...}. The arguments are the ones of full_pipeline.
        """
        # 1) The conversation of this question. A new one gets a random id, which nobody can guess
        thread_id = thread_id or uuid4().hex
        #    Postgres can't store the NUL character inside a text, and no question needs it: it is removed here,
        #    for every way into the agent. With it, the memory would refuse the question like an outage
        question = question.replace("\x00", "")
        #    "configurable" is where LangGraph reads the id of the conversation,
        #    and run_name is the name of this run in LangSmith
        config = {"configurable": {"thread_id": thread_id}, "run_name": "who_to_ask"}
        steps: List[str] = []

        try:
            # 2) What the graph is given. A question: the starting value of every key that belongs to one question.
            #    An answer to the agent's question: a Command that continues the paused run of this conversation
            run_input, waiting = self._question_state(question), None
            if is_answer:
                # get_state reads what the memory holds. A paused run keeps its question there, in "interrupts"
                saved = self.compiled_workflow.get_state(config)
                waiting = saved.interrupts[0].value if saved.interrupts else None
                # The answer must be one of the choices that the agent offered: only then does the run go on
                picked_a_choice = bool(waiting) and question in waiting["choices"]
                run_input = Command(resume=question) if picked_a_choice else None

            if run_input is None and waiting:
                # The run is paused, and the answer is not one of its choices: nothing runs, and the same
                # question is asked again
                logger.info("An answer arrived that is not one of the choices: the agent asks its question again")
                state, ask = saved.values, waiting
            elif run_input is None:
                # Nothing is waiting for an answer (the app was restarted without Postgres, for example):
                # nothing runs, and the answer says so
                logger.info("An answer arrived, and no question of the agent is waiting for it: nothing runs")
                state = {**self._question_state(""), "language": saved.values.get("language", "en")}
                ask = {"asks": "not_waiting", "choices": []}
            else:
                # 3) Run the graph. stream() gives one update per finished node: the keys that the node changed.
                #    Each node writes its step line in "step". A pause arrives as an update named "__interrupt__"
                for update in self.compiled_workflow.stream(run_input, config=config, stream_mode="updates"):
                    for node, changed in update.items():
                        if node != "__interrupt__" and changed and changed.get("step"):
                            steps.append(changed["step"])
                            yield {"type": "step", "text": changed["step"]}

                # 4) The run has ended, or it is paused in ask_user. The memory says which: a paused run
                #    holds the question that interrupt() was given, with its choices
                saved = self.compiled_workflow.get_state(config)
                state = saved.values
                ask = saved.interrupts[0].value if saved.interrupts else None
        except psycopg.Error as e:
            # Postgres stopped answering while the app runs. The question fails: it is never answered without
            # its memory. Only the kind of error is shown, as when the memory is opened
            logger.error(f"The memory in Postgres did not answer ({type(e).__name__}). Is the PostgreSQL service running?")
            raise RuntimeError("The memory in Postgres did not answer") from None

        # 5) The graph only handled ids. The answer gets its names, emails, links, and note from the data.
        #    What the user typed in the two boxes goes to the answer builder only: it is never in the state,
        #    so the LLM never reads it, and the memory never saves it
        answer = self.answer_builder.build(state, ask, user_name, user_team)
        answer["steps"] = steps
        answer["thread_id"] = thread_id
        if ask:
            details = f", the agent asks one question ({ask['asks']}, {len(ask['choices'])} choices)"
        else:
            details = f", {len(answer['cards'])} people recommended" if answer["cards"] else ""
        logger.info(f"Answer: {answer['status']}{details}")
        yield {"type": "answer", "answer": answer}

    def close(self) -> None:
        """Close the connections to Postgres. Call it once, when the program stops."""
        if self.pool is not None:
            self.pool.close()
            self.pool = None

    # ------------------------------------------------------------------
    # The nodes: each one calls a class, and returns only the keys it changed
    # ------------------------------------------------------------------

    def _understand_step(self, state: AgentState) -> Dict:
        """Ask the LLM what the request is: its road, and what the next steps need to know about it."""
        understood = self.reader.read(state["question"])
        road, systems, words = understood["road"], understood["unclear_systems"], understood["search_words"]
        named = understood["named_systems"]
        if state["asked"] == "system" and state["picked"]:
            # The user has just said which system is meant, so nothing is unclear any more, whatever the LLM says.
            # And the name of that system is always one of the search words
            if road == "unclear":
                road, systems = "expert", []
            name = self.evidence.system_names[state["picked"]]
            if not any(name.lower() in entry.lower() for entry in words):
                words = [name] + words
            # The system that the user picked is the one that the question names: the code knows it for sure
            named = [state["picked"]]
        # A request with no topic has no search word and names no system, also after the user's pick
        no_topic = understood["no_topic"] and not words and not named
        facts = {
            "road": road,
            "question_type": understood["question_type"],
            "systems": len(systems),
            "answered": bool(state["asked"]),
            "no_topic": no_topic,
        }
        return {
            "road": road,
            "question_type": understood["question_type"],
            "language": understood["language"],
            "search_words": words,
            "unclear_systems": systems,
            "named_systems": named,
            "no_topic": no_topic,
            "person_name": understood["person_name"],
            "person_asks": understood["person_asks"],
            "step": self.step_writer.write("understand", facts),
        }

    def _failsafe_step(self, state: AgentState) -> Dict:
        """Refuse politely, with a fixed text in the language of the question. Nothing is searched."""
        logger.info(f"Failsafe: the request is refused ({state['road']})")
        return {
            "message": FAILSAFE_TEXTS[state["road"]][state["language"]],
            "step": self.step_writer.write("failsafe", {}),
        }

    def _search_step(self, state: AgentState) -> Dict:
        """Search the tickets and the pages that can count for this type of question."""
        retry = state["attempts"] > 0
        found_ids = self.searcher.search(state["question"], state["search_words"], state["question_type"], retry=retry)
        facts = {"words": state["search_words"], "found": len(found_ids), "retry": retry}
        return {"found_ids": found_ids, "step": self.step_writer.write("search", facts)}

    def _verify_step(self, state: AgentState) -> Dict:
        """Ask the LLM which of the tickets and pages found are really about the question."""
        # On a retry, what was already judged is skipped: the question is the same, so the verdict would be too
        new_ids = [item_id for item_id in state["found_ids"] if item_id not in state["checked_ids"]]
        items = [self.evidence.get_item(item_id) for item_id in new_ids]
        result = self.verifier.verify(state["question"], items)
        facts = {"checked": len(new_ids), "kept": len(result["kept_ids"])}
        return {
            "evidence_ids": result["kept_ids"],
            "checked_ids": state["checked_ids"] + new_ids,
            "step": self.step_writer.write("verify", facts),
        }

    def _rewrite_step(self, state: AgentState) -> Dict:
        """Nothing held up: ask the LLM for other search words, and count the retry."""
        result = self.rewriter.rewrite(state["question"], state["search_words"])
        return {
            "search_words": result["search_words"],
            "attempts": state["attempts"] + 1,
            "step": self.step_writer.write("rewrite", {}),
        }

    def _same_system_step(self, state: AgentState) -> Dict:
        """Nothing is about the exact need, and the request names a system: take every ticket and page of that system.

        It is a second level of answer. The people behind these tickets and pages work on the system: nothing says
        that they worked on this need. So the level is written in the state, and the answer says it before the cards.
        The same ranking and the same HR check follow, so nobody who left or opted out can come out of it.
        """
        item_ids = self.evidence.list_ids_of_systems(state["named_systems"])
        logger.info(
            f"Same system: nothing is about the exact need, so the {len(item_ids)} tickets and pages "
            f"about {', '.join(state['named_systems'])} are taken"
        )
        # The step line shows the names of the systems: they come from the data, and they name no person
        names = [self.evidence.system_names[system_id] for system_id in state["named_systems"]]
        return {
            "evidence_ids": item_ids,
            "level": "system",
            "step": self.step_writer.write("same_system", {"systems": names, "items": len(item_ids)}),
        }

    def _rank_step(self, state: AgentState) -> Dict:
        """Find the people behind the evidence that held up, and order them with the ranking rules."""
        pieces = [piece for item_id in state["evidence_ids"] for piece in self.evidence.get_pieces(item_id)]
        ranking = self.ranker.rank(pieces, state["question_type"])
        logger.info(f"Rank: {len(ranking)} people are behind the evidence")
        return {"ranking": ranking, "step": self.step_writer.write("rank", {"people": len(ranking)})}

    def _check_hr_step(self, state: AgentState) -> Dict:
        """Remove the people who left or opted out, and keep up to three."""
        result = self.hr_checker.check(state["ranking"])
        logger.info(
            f"HR check: {len(result['recommended'])} people kept, {len(result['removed_left'])} who left "
            f"and {len(result['removed_opted_out'])} who opted out removed"
        )
        # The step line only counts the people who were removed: it never names anyone
        facts = {"left": len(result["removed_left"]), "opted_out": len(result["removed_opted_out"])}
        return {
            "recommended": result["recommended"],
            "removed_left": result["removed_left"],
            "removed_opted_out": result["removed_opted_out"],
            "step": self.step_writer.write("check_hr", facts),
        }

    def _write_cards_step(self, state: AgentState) -> Dict:
        """Ask the LLM for the three texts of each person's card. The rest of a card comes from the data."""
        # The LLM only gets the evidence of the people who are recommended: ids, titles, and what each person did
        people = [
            {"person": entry["person"], "evidence": self.evidence.label_pieces(entry["pieces"])}
            for entry in state["recommended"]
        ]
        # The level tells the LLM what the evidence proves: that this person worked on the exact need, or only
        # that they work on the system. A conversation saved before the second level existed has no such key
        result = self.card_writer.write(state["question"], state["language"], people, state.get("level", "exact"))
        # The people of the cards are now the most recent people shown: a follow-up can say "her" or "Sophie"
        shown = self._remember(state, [entry["person"] for entry in state["recommended"]])
        return {
            "cards": result["cards"],
            "shown_people": shown,
            "step": self.step_writer.write("write_cards", {"people": len(people)}),
        }

    def _nobody_found_step(self, state: AgentState) -> Dict:
        """Say honestly that nobody was found, with a fixed text in the language of the question.

        For a request that names no topic at all, nothing was searched: the fixed text asks what the user needs.
        """
        if state["road"] == "person" and len(state["person_matches"]) > 1:
            # Several people have the name, and the agent has already asked its one question for this request
            kind = "several_people"
        elif state["road"] == "person":
            # Nobody has the name that was given. Or the question gave no name ("her"), and nobody was shown yet
            kind = "no_person" if state["person_name"] else "no_one_meant"
        elif state.get("no_topic"):
            # The request names no topic at all, so nothing was searched: the text asks what the user needs.
            # A conversation saved before this key existed has none: its requests all had a topic
            kind = "no_topic"
        else:
            # "No recorded decision" is only true when no decision held up. When a decision held up and the HR check
            # removed its owner, a decision is recorded: the general text is the right one
            no_decision = state["question_type"] == "decided" and not state["evidence_ids"]
            kind = "no_decision" if no_decision else "general"
        logger.info(f"Nobody found: the answer is the \"{kind}\" text")
        return {
            "message": NOBODY_FOUND_TEXTS[kind][state["language"]],
            "step": self.step_writer.write("nobody_found", {"kind": kind}),
        }

    def _find_person_step(self, state: AgentState) -> Dict:
        """Look the colleague up in the directory: the people already shown first, then everyone."""
        # The user has just picked one of the people that the agent offered: that person is the one.
        # The pick is an id, so it also decides between two people who would have the same full name
        picked = state["asked"] == "person" and state["picked"] in state["person_matches"]
        if picked:
            logger.info("Find person: the user picked one of the people the agent offered")
            matches = [state["picked"]]
        else:
            matches = self.person_finder.find(state["person_name"], self._shown_people(state))["matches"]
        facts = {"matches": len(matches), "named": bool(state["person_name"].strip()), "picked": picked}
        return {"person_matches": matches, "step": self.step_writer.write("find_person", facts)}

    def _person_card_step(self, state: AgentState) -> Dict:
        """Decide what the answer may show about the colleague: the directory fields, and what was asked for."""
        card = self.person_card_maker.make(state["person_matches"][0], state["person_asks"])
        if not card:
            # The directory lost this person between two steps: the honest answer is that nobody has this name
            return {
                "message": NOBODY_FOUND_TEXTS["no_person"][state["language"]],
                "step": self.step_writer.write("nobody_found", {"kind": "no_person"}),
            }
        # The person of the card is now the most recent person shown: the next "her" means this person
        return {
            "person_card": card,
            "shown_people": self._remember(state, [card["person"]]),
            "step": self.step_writer.write("person_card", {}),
        }

    def _ask_user_step(self, state: AgentState) -> Dict:
        """Pause the run, and ask the user one question: which system, or which person. The choices are ids from the data."""
        # 1) What to ask. After understand: a general word fits several systems. After find_person: several
        #    people have the name. Nothing here may have an effect outside this node: see step 2
        if state["road"] == "unclear":
            asks, choices = "system", state["unclear_systems"]
        else:
            asks, choices = "person", state["person_matches"]

        # 2) interrupt() pauses the run here: LangGraph saves the state, and gives the question to the caller.
        #    When the user answers, the run is resumed: this node runs again from its first line, and this time
        #    interrupt() returns the answer. It pauses by raising an exception that LangGraph must receive,
        #    so this node has no try/except
        picked = interrupt({"asks": asks, "choices": choices})

        # 3) From here on, the user has answered. Never trust what comes in: the answer must be one of the choices
        if picked not in choices:
            picked = ""
        logger.info(f"Ask user: the user picked one of the {len(choices)} choices ({asks})")
        answered = {"asked": asks, "picked": picked, "step": self.step_writer.write("ask_user", {})}
        if asks == "system" and picked:
            # The system is added to the question, in a fixed sentence: the next steps read the completed question,
            # as if the user had typed it. A person is not added: find_person takes the id that was picked
            name = self.evidence.system_names[picked]
            answered["question"] = PICKED_SYSTEM[state["language"]].format(question=state["question"], name=name)
        return answered

    # ------------------------------------------------------------------
    # The routers: each one reads the state and returns a label. The graph maps each label to a node
    # ------------------------------------------------------------------

    def _decide_after_understand(self, state: AgentState) -> str:
        """A request for an expert goes to the search, and a request about a colleague to the directory.

        A request with a general word that fits several systems goes to ask_user, once.
        A request for an expert that names no topic at all is not searched: the agent asks what the user needs.
        A request that is not about work, or that is personal, is refused.
        """
        if state["road"] == "unclear":
            # One question per request: the second time, the agent goes on with what it has
            return "unclear" if not state["asked"] else "expert"
        if state["road"] == "expert" and state["no_topic"]:
            # No search word and no system: a search would compare every ticket with a request that asks for nothing,
            # and one wrong "yes" of verify would recommend someone
            return "no_topic"
        if state["road"] in ["expert", "person"]:
            return state["road"]
        return "off_topic"

    def _decide_after_verify(self, state: AgentState) -> str:
        """Evidence held up: rank the people behind it. Nothing held up: search once more.

        Still nothing: when the request names a system, take the people who work on that system, as a second level.
        Otherwise, say that nobody was found.
        """
        if state["evidence_ids"]:
            return "evidence_holds"
        # The attempts counter stops the loop: without it, the graph could search again forever
        if state["attempts"] < MAX_RETRIES:
            return "retry"
        # Never for a "decided" question: working on a system is not deciding, so only a recorded decision answers it
        if state["named_systems"] and state["question_type"] != "decided":
            return "same_system"
        return "nothing_holds"

    def _decide_after_check_hr(self, state: AgentState) -> str:
        """People are left to recommend: write their cards. Everyone was removed: nobody is found."""
        return "people_left" if state["recommended"] else "everyone_removed"

    def _decide_after_find_person(self, state: AgentState) -> str:
        """One person has the name: show their card. Several have it: ask which one, once. Nobody has it: say so."""
        matches = len(state["person_matches"])
        if matches == 1:
            return "one_match"
        # One question per request: when the agent has already asked, it says that it can't tell who is meant
        return "several_matches" if matches > 1 and not state["asked"] else "no_match"

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _question_state(self, question: str) -> Dict:
        """The starting value of every key that belongs to one question. understand replaces the first ten.

        shown_people is not here, on purpose. The graph starts from the saved state of the conversation,
        and a key that is not given keeps its saved value: that is how the people shown are remembered.
        """
        return {
            "question": question,
            "road": "expert",
            "question_type": "help",
            "language": "en",
            "search_words": [],
            "unclear_systems": [],
            "named_systems": [],
            "no_topic": False,
            "person_name": "",
            "person_asks": "card",
            "asked": "",
            "picked": "",
            "attempts": 0,
            "message": "",
            "found_ids": [],
            "checked_ids": [],
            "evidence_ids": [],
            "level": "exact",
            "ranking": [],
            "recommended": [],
            "removed_left": [],
            "removed_opted_out": [],
            "cards": [],
            "person_matches": [],
            "person_card": {},
            "step": "",
        }

    def _shown_people(self, state: AgentState) -> List[str]:
        """The people the conversation has shown so far, the most recent first. Nobody yet: an empty list."""
        # shown_people is the one key that a question does not fill at its start, so it can be missing
        return state.get("shown_people", [])

    def _remember(self, state: AgentState, person_ids: List[str]) -> List[str]:
        """The new list of the people shown: the people of this answer first, then the ones shown before."""
        earlier = [person_id for person_id in self._shown_people(state) if person_id not in person_ids]
        return list(person_ids) + earlier

    def _build_checkpointer(self) -> BaseCheckpointSaver:
        """Build the memory of the conversations: Postgres when POSTGRES_URI is set, the program's own memory otherwise."""
        # The state is plain data (texts, numbers, lists, dicts). This strict setting makes the memory refuse to load
        # anything else, as the README of LangGraph's Postgres saver asks
        serde = JsonPlusSerializer(allowed_msgpack_modules=None)

        uri = settings.POSTGRES_URI.get_secret_value().strip() if settings.POSTGRES_URI else ""
        if not uri:
            # No Postgres: LangGraph's in-memory saver. The app works the same way, and it forgets when it stops
            logger.info("Memory: in this program only (no POSTGRES_URI), so conversations are forgotten when it stops")
            return InMemorySaver(serde=serde)

        # 1) The address holds a password, so no message ever repeats it. It is checked here because psycopg quotes
        #    a part of a text that is not an address in its error
        if not uri.startswith(("postgresql://", "postgres://")):
            logger.error("POSTGRES_URI must start with postgresql://")
            raise RuntimeError("POSTGRES_URI must start with postgresql://")

        try:
            # 2) One connection first, to see that Postgres answers. If it does not, the app stops here
            with psycopg.connect(uri, connect_timeout=POSTGRES_TIMEOUT_SECONDS):
                pass
            # 3) The pool: a few connections that stay open and are shared, like the client of MongoDB.
            #    The three kwargs are what LangGraph's saver asks of its connections
            self.pool = ConnectionPool(
                uri,
                min_size=1,
                max_size=POSTGRES_POOL_SIZE,
                timeout=POSTGRES_TIMEOUT_SECONDS,
                open=False,
                kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
            )
            self.pool.open(wait=True, timeout=POSTGRES_TIMEOUT_SECONDS)
            # 4) The saver, and its tables: setup() creates them the first time, and changes nothing afterwards
            checkpointer = PostgresSaver(self.pool, serde=serde)
            checkpointer.setup()
        except Exception as e:
            self.close()
            # Only the kind of error and a hint are shown: psycopg's own text can repeat a part of the address
            hint = self._postgres_hint(str(e))
            logger.error(f"Could not open the memory in Postgres ({type(e).__name__}). {hint}")
            raise RuntimeError(f"Could not open the memory in Postgres. {hint}") from None
        logger.info("Memory: conversations are saved in Postgres")
        return checkpointer

    def _postgres_hint(self, error_text: str) -> str:
        """What to check when Postgres can't be opened, from the words of its error."""
        if "password authentication failed" in error_text or 'role "' in error_text:
            return "PostgreSQL refused the user name or the password of POSTGRES_URI"
        if 'database "' in error_text and "does not exist" in error_text:
            return "The database named at the end of POSTGRES_URI does not exist: create it in pgAdmin"
        return "Is the PostgreSQL service running, and is the address in POSTGRES_URI right?"

    def _setup_tracing(self) -> None:
        """Switch LangSmith tracing on when a key is set. Without a key, nothing changes."""
        key = settings.LANGSMITH_API_KEY.get_secret_value().strip() if settings.LANGSMITH_API_KEY else ""
        if not key:
            logger.info("LangSmith tracing: off (no LANGSMITH_API_KEY)")
            return

        # LangSmith reads its settings from the environment, and pydantic-settings does not copy .env there
        os.environ["LANGSMITH_TRACING"] = "true"
        os.environ["LANGSMITH_API_KEY"] = key
        os.environ["LANGSMITH_PROJECT"] = settings.LANGSMITH_PROJECT
        if settings.LANGSMITH_ENDPOINT:
            os.environ["LANGSMITH_ENDPOINT"] = settings.LANGSMITH_ENDPOINT
        logger.info(f"LangSmith tracing: on (project {settings.LANGSMITH_PROJECT})")
