"""API entry point: the same agent as app.py, behind two HTTP endpoints.

Start the server from the project folder, then open its /docs page in a browser:
    python -m uvicorn api.main:app
    http://127.0.0.1:8000/docs

The company data is read from MongoDB. Fill it once from the data folder, and again after a change to a file:
    python -m scripts.seed_mongodb
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Iterator, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.tracers.langchain import wait_for_all_tracers
from pydantic import BaseModel, ConfigDict, Field

from agents import AgentWorkflow
from config.constants import MAX_QUESTION_LENGTH, MAX_USER_TEXT_LENGTH, PAGE_ORIGINS
from utils.logging import logger

# What a caller reads when the agent fails. The details stay in the log: an error's own text can hold an address
ERROR_TEXT = "Sorry, something went wrong and I could not answer. The details are in the log of the API."

# What every request shares: the agent, under the name "workflow". It is empty until the server starts.
# It is a dict, as in FastAPI's own example: a function can fill a dict without the "global" keyword
shared: Dict[str, AgentWorkflow] = {}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """What the server does once when it starts (before the yield), and once when it stops (after the yield)."""
    # 1) Build the agent once, before the first request. Building it opens the memory (Postgres), reads MongoDB, and
    #    embeds every ticket and page (one OpenAI call), so it must not happen at each question.
    #    If it fails, the server does not start
    try:
        shared["workflow"] = AgentWorkflow()
    except Exception as e:
        logger.error(f"The agent could not be built: {e}")
        # The server prints the error that stops it. "from None" keeps it to this one, without the long chain behind it
        raise RuntimeError(
            "The API did not start, because the agent could not be built. The lines above say why"
        ) from None
    logger.info("API ready: the agent is built, and POST /ask and POST /ask/stream answer questions")

    # 2) The server now answers requests, until it is stopped
    yield

    # 3) The server is stopping. LangSmith sends its traces in the background: wait for the last ones.
    #    Then close the connections to Postgres, and let go of the agent
    wait_for_all_tracers()
    shared["workflow"].close()
    shared.clear()


app = FastAPI(
    title="Who To Ask",
    description=(
        'An internal "who should I ask?" assistant. Describe what you need help with, and the agent finds the right '
        "colleagues in fake Jira, Confluence, Teams, and HR data. All the data is fake, and nothing is ever sent."
    ),
    lifespan=lifespan,
)

# CORS: the page is served from another address than the API (another port of this computer). A browser refuses
# to let a page read the answer of another address, unless that address says that the page may. This middleware
# says so, for the page's address only, for POST requests, and for the one header that a JSON body needs
app.add_middleware(
    CORSMiddleware,
    allow_origins=PAGE_ORIGINS,
    allow_methods=["POST"],
    allow_headers=["Content-Type"],
)


class Question(BaseModel):
    """The body of a request to POST /ask and to POST /ask/stream."""

    model_config = ConfigDict(
        # The spaces around each text are removed before its length is checked
        str_strip_whitespace=True,
        # The body that the /docs page proposes: a first question, so it has no thread_id
        json_schema_extra={"examples": [{"question": "Who can help me get access to the Claims API?"}]},
    )

    question: str = Field(
        min_length=1,
        max_length=MAX_QUESTION_LENGTH,
        description=(
            "What you need help with, in English or in French. "
            "To answer a question of the agent: the `id` of the choice you pick, with `is_answer` set to true"
        ),
        examples=["Who can help me get access to the Claims API?"],
    )
    # The id of a conversation is made up by the API, as 32 letters and digits. The pattern keeps anything else out
    thread_id: Optional[str] = Field(
        default=None,
        pattern=r"^[A-Za-z0-9_-]{1,64}$",
        description=(
            "The id of the conversation. Leave it out for a first question: the answer gives one. "
            'Send it back with a follow-up such as "And who\'s her manager?", so the agent knows who "her" is'
        ),
    )
    # A click on a choice is an answer to the agent. What is typed in the question box is always a new question
    is_answer: bool = Field(
        default=False,
        description=(
            "True when `question` is your answer to a question of the agent (the status `needs_details`): "
            "the `id` of one of its `choices`, sent with the same `thread_id`"
        ),
    )
    # The two optional boxes of the page. They only fill the first sentence of the suggested messages
    user_name: Optional[str] = Field(
        default=None,
        max_length=MAX_USER_TEXT_LENGTH,
        description='Your name, for the first sentence of the suggested messages. Without it: "[your name]"',
    )
    user_team: Optional[str] = Field(
        default=None,
        max_length=MAX_USER_TEXT_LENGTH,
        description='Your team, for the first sentence of the suggested messages. Without it: "[your team]"',
    )


@app.post("/ask")
def ask(body: Question) -> Dict:
    """Ask one question, and get the colleagues who can help, or the work information of one colleague.

    The answer has a `status`:

    - `answered`: up to three `cards`, best first. A card has the person, a "why" sentence, the evidence,
      a suggested message, and two links (`teams_link` and `email_link`) that open your own Teams or email app.
    - `person`: the question was about one colleague. `message` is the sentence that answers it, and `person_card`
      has the colleague's work information from the directory, with two links that open with no message.
      For someone who left the company, the card only has the name, and `left` is true.
    - `needs_details`: the agent asks you one question before it answers, because a word of your question fits
      several systems ("the API"), or several people have the name. `message` is its question, and `choices`
      lists what you can pick. To answer, send the `id` of a choice as `question`, with the same `thread_id`
      and `"is_answer": true`. A new question sent instead simply starts again.
    - `nobody_found`: there is nobody to recommend, or nobody has that name, and `message` says so.
    - `off_topic`: the question is not about work, or it is a personal question about a colleague.
      `message` is the polite refusal, and `reason` says which of the two it is.

    `note` says who was removed from an expert answer: someone who left the company is named, and the people who
    opted out of being found are only counted. `steps` lists what the agent did, one short line per step.
    The answer is in the language of the question.

    Every answer has a `thread_id`: the id of its conversation. To ask a follow-up, such as "And who's her manager?",
    send the same `thread_id` with your next question. Without one, each question starts a new conversation.

    `user_name` and `user_team` are optional: they fill the first sentence of each suggested message
    ("Hi Sophie, I'm Alex from Pricing."). They are used for that, and for nothing else.
    """
    # This is a plain def, so FastAPI runs it in a worker thread: a question that takes a few seconds does not block
    # the server, and two questions can be answered at the same time
    try:
        # The agent that was built when the server started. It remembers each conversation under its thread_id
        return shared["workflow"].full_pipeline(
            body.question, body.thread_id, body.is_answer, body.user_name or "", body.user_team or ""
        )
    except Exception as e:
        # The caller gets a short fixed text. "Nobody found" would be wrong here: the agent did not finish looking
        logger.error(f"The agent could not answer: {e}")
        raise HTTPException(status_code=500, detail=ERROR_TEXT) from e


@app.post("/ask/stream")
def ask_stream(body: Question) -> Iterator[Dict]:
    """Ask one question, and read what the agent does while it works. The body is the same as for `POST /ask`.

    The response is a stream of lines, and each line is one JSON object (the "JSON Lines" format):

    - `{"type": "step", "text": "..."}`: one short line for each step the agent has finished.
    - `{"type": "answer", "answer": {...}}`: the last line. `answer` is exactly what `POST /ask` returns.
    - `{"type": "error", "message": "..."}`: the last line when the agent failed. The code 200 was already sent
      when the stream started, so an error can only arrive as a line.
    """
    # A function with "yield" is a generator. FastAPI sends each value it gives as one line of JSON, as soon as
    # it is given: that is what lets a page show a step while the next one is still running
    try:
        yield from shared["workflow"].stream_pipeline(
            body.question, body.thread_id, body.is_answer, body.user_name or "", body.user_team or ""
        )
    except Exception as e:
        logger.error(f"The agent could not answer: {e}")
        yield {"type": "error", "message": ERROR_TEXT}
