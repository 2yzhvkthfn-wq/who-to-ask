"""MCP entry point: the same agent as app.py and the API, as two tools that an AI assistant can call.

MCP (Model Context Protocol) is a standard way to plug tools into an AI assistant. An MCP client (Claude Code,
Cursor, Claude Desktop, the MCP Inspector) starts this program itself, and talks to it through the program's input
and output, which is called "stdio". Its command, from the backend folder:
    python -m mcp_server.server

So nothing here may print(): the output of this program is the channel. The log goes to the error output and to app.log.

The company data is read from MongoDB. Fill it once from the data folder, and again after a change to a file:
    python -m scripts.seed_mongodb
"""

import inspect
import sys
from contextlib import asynccontextmanager
from typing import Annotated, AsyncIterator, Dict, Optional

from langchain_core.tracers.langchain import wait_for_all_tracers
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field, StringConstraints

from agents import AgentWorkflow
from config.constants import MAX_QUESTION_LENGTH
from utils.logging import logger

from .answer_writer import AnswerWriter

# What the assistant reads when the agent fails. The details stay in the log: an error's own text can hold an address
ERROR_TEXT = "Sorry, something went wrong and I could not answer. The details are in app.log, in the backend folder."

# What a client is told about the server as a whole, when it connects. Each tool then has its own description
INSTRUCTIONS = (
    'Who To Ask is an internal "who should I ask?" assistant for Tamberly Insurance, a fictional company: all its '
    "data is fake. Call ask with a work question: who can help with a system or a topic, who did or decided "
    "something, or work information about one colleague. When an answer is a question with choices, ask the user, "
    "then call pick_choice. The agent suggests a message for each person, and it never sends anything."
)

# What every call of a tool shares: the agent, under the name "workflow". It is empty until the server starts
shared: Dict[str, AgentWorkflow] = {}
# The class that writes an answer of the agent as a short text: an assistant reads a text better than a long dict
writer = AnswerWriter()


@asynccontextmanager
async def lifespan(server: MCPServer) -> AsyncIterator[None]:
    """What the server does once when it starts (before the yield), and once when it stops (after the yield)."""
    # 1) Build the agent once, before the first call. Building it opens the memory (Postgres), reads MongoDB, and
    #    embeds every ticket and page (one OpenAI call), so it must not happen at each question.
    #    If it fails, the server does not start
    try:
        shared["workflow"] = AgentWorkflow()
    except Exception as e:
        logger.error(f"The agent could not be built: {e}")
        # "from None" keeps the error to this one sentence, without the long chain behind it
        raise RuntimeError("the agent could not be built. The lines above say why") from None
    logger.info("MCP server ready: the agent is built, and the tools ask and pick_choice answer questions")

    try:
        # 2) The server now answers its client, until the client closes the connection
        yield
    finally:
        # 3) The server is stopping. LangSmith sends its traces in the background: wait for the last ones.
        #    Then close the connections to Postgres, and let go of the agent
        wait_for_all_tracers()
        shared["workflow"].close()
        shared.clear()
        logger.info("MCP server stopped")


# The server. log_level: the library sets up Python's standard logging for the whole program, and at its usual level
# every call to OpenAI would write a line on the error output. WARNING keeps the warnings of the libraries,
# and this project's own lines go through loguru, as everywhere
mcp = MCPServer("who-to-ask", instructions=INSTRUCTIONS, lifespan=lifespan, log_level="WARNING")

# The arguments of the tools, with their limits. The library checks them before a tool runs, as FastAPI does for
# the body of a request: a call with a bad argument never reaches the agent, and its error names the argument.
# Each description is read by the assistant, next to the description of the tool
Question = Annotated[
    str,
    # The spaces around the question are removed before its length is checked
    StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_QUESTION_LENGTH),
    Field(description="The user's question, as they wrote it, in English or in French."),
]
# The id of a conversation is made up by the agent, as 32 letters and digits. The pattern keeps anything else out,
# as in the API. For a new conversation, an assistant may leave the id out, or send an empty one: both are accepted
OptionalThreadId = Annotated[
    Optional[str],
    Field(
        pattern=r"^[A-Za-z0-9_-]{0,64}$",
        description=(
            "The thread_id at the end of an earlier answer, to go on with that conversation. "
            "Leave it out to start a new conversation."
        ),
    ),
]
ThreadId = Annotated[
    str,
    Field(pattern=r"^[A-Za-z0-9_-]{1,64}$", description="The thread_id at the end of the answer that asked the question."),
]
# The id of a choice is the id of a system (claims_api) or of a person (p012): the same kind of text
ChoiceId = Annotated[
    str,
    Field(
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
        description="The choice_id of the choice that the user picked, exactly as the answer writes it.",
    ),
]


def ask(question: Question, thread_id: OptionalThreadId = None) -> str:
    """Ask the "Who To Ask" agent of Tamberly Insurance a work question, and get its answer as text.

    Tamberly Insurance is a fictional company: all its data is fake. The agent answers two kinds of question,
    in English or in French:

    - Who to ask: "Who can help me with X?", "Who fixed X?", "Who decided X?". It recommends up to three
      colleagues, best first, each with the reason, the evidence, and a suggested message. It never sends anything.
    - About one colleague: their job title, team, manager, email, or work phone, what they work on, or whether
      they are out of office. Work information only: a personal question is declined.

    How to use it:

    - Pass the user's question as they wrote it, in their language: the answer comes back in that language.
    - Every answer ends with a thread_id. Send it back with a follow-up such as "And who's her manager?":
      the agent then knows who "her" is.
    - When the agent needs a detail, its answer is a question with choices: ask the user, then call pick_choice.
    - Show the people, their contact details, and the reasons as the answer gives them. Do not add any of your own:
      everything in an answer comes from the company's data.
    """
    # What an assistant sends as a question is always a new question, in a new conversation or in a known one
    return answer_as_text(question, thread_id or None, is_answer=False)


def pick_choice(thread_id: ThreadId, choice_id: ChoiceId) -> str:
    """Answer a question of the agent: send the choice that the user picked.

    Call it only when the last answer was a question with choices. The agent then goes on with the same question,
    and gives its answer as text.

    Ask the user which choice they mean: do not pick for them. If the user asks something else instead,
    call ask with the new question.
    """
    # The paused run of this conversation goes on with the pick. A pick that is not one of the choices runs nothing:
    # the agent asks its question again
    return answer_as_text(choice_id, thread_id, is_answer=True)


# The two functions above become the tools of the server here. The description of a tool is the docstring of its
# function: the assistant reads it to decide when to call the tool, and how.
# The usual way is the decorator @mcp.tool() above each function. On Python 3.11 it would give the assistant the
# docstring with the indentation it has in the code, so the functions are added here, with inspect.getdoc, which
# removes that indentation.
# structured_output=False: a tool gives back its text once. Without it, the library would send the same text
# a second time, wrapped as data ({"result": "..."})
mcp.add_tool(ask, description=inspect.getdoc(ask), structured_output=False)
mcp.add_tool(pick_choice, description=inspect.getdoc(pick_choice), structured_output=False)


def answer_as_text(question: str, thread_id: Optional[str], is_answer: bool) -> str:
    """Run the agent on a question, or on a pick, and return its answer as text. If the agent fails: a fixed text."""
    # The tools are plain def functions, so the library runs each call in a worker thread: a question that takes
    # a few seconds does not block the server
    try:
        # The agent that was built when the server started. It remembers each conversation under its thread_id
        answer = shared["workflow"].full_pipeline(question, thread_id, is_answer)
        return writer.write(answer)
    except Exception as e:
        # The assistant gets a short fixed text, marked as an error. "Nobody found" would be wrong here:
        # the agent did not finish looking
        logger.error(f"The agent could not answer: {e}")
        raise ToolError(ERROR_TEXT) from e


def main() -> None:
    """Start the server, and answer the client that started this program until it closes the connection."""
    try:
        # With no argument, run() talks over stdio: it reads the client's requests on the input of this program,
        # and writes its answers on the output
        mcp.run()
    except KeyboardInterrupt:
        # Ctrl+C, when the program was started by hand in a terminal: a normal way to stop it, with no trace
        logger.info("MCP server stopped (Ctrl+C)")
    except Exception as e:
        # The server could not start, or it stopped on an error. The library runs the server in a group of tasks,
        # and wraps the error of a task in a group of errors: the real error is the one inside
        while isinstance(e, BaseExceptionGroup) and e.exceptions:
            e = e.exceptions[0]
        logger.error(f"The MCP server stopped: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
