# Who To Ask: the details

The long parts of the [README](../README.md): one real answer, what each node does, the details of "Run it", the full honest test, all the limits, and the next steps.

## One real answer

One real answer, in the terminal. The two other cards and the links are left out here:

```text
Question: Who can help me get access to the Claims API?

Steps:
   Read your question: you are looking for someone who can help
   Searched pages and tickets for "Claims API", "get access": 13 results
   Checked 13 results: 8 are really about your question
   Found 5 people behind these pages and tickets
   Removed: 1 person who left the company, 1 person who opted out
   Wrote the cards of 3 people

Étienne Lavoie wrote "Claims API - how to get an API key", but no longer works at the company. 1
person opted out of being found.

1. Sophie Martin, Senior Developer, Claims Platform
   Email: sophie.martin@tamberly.example
   Out of office until 10 November 2026
   Why: Wrote the Claims API access guide and handled several access requests.
   Evidence: "Claims API: Access Guide" (Confluence), CLM-212, CLM-245, CLM-301 (Jira)

   Suggested message:
   "Hi Sophie, I'm [your name] from [your team]. I'm trying to get access to the Claims API. I saw
    you wrote the access guide and handled requests for it. Where should I start? I see you're away
    until 10 November, so no rush. Thank you!"
```

## The nodes

The diagram of the graph is in the [README](../README.md#how-it-works).

To draw it again from the code:

```powershell
python -c "from agents import AgentWorkflow; agent = AgentWorkflow(); print(agent.compiled_workflow.get_graph().draw_mermaid(with_styles=False)); agent.close()"
```

| Node | Who decides | What it does |
|---|---|---|
| `understand` | LLM | Reads the request and picks its road: find an expert, a question about a colleague, unclear, or not about work |
| `ask_user` | The user | Pauses the run and asks one question, with choices from the data. The answer goes back to `understand` |
| `search` | Code | Searches the tickets and the pages, with keywords and embeddings together |
| `verify` | LLM | Reads each ticket and page found, one at a time: is it really about the question? |
| `rewrite` | LLM | Nothing held up: writes other search words, for one retry |
| `same_system` | Code | Still nothing, and the question names a system: takes the people who work on that system. The answer says so |
| `rank` | Code | Finds the people behind the evidence, and orders them with simple rules |
| `check_hr` | Code | Removes the people who left or opted out, and keeps up to 3 |
| `write_cards` | LLM | Writes the "why" sentence and the middle of the suggested message. Plain code writes the rest of the card from the data |
| `find_person`, `person_card` | Code | Look a colleague up in the directory, and decide what the answer may show |
| `nobody_found`, `failsafe` | Code | Fixed texts: nobody was found, "What do you need help with?" for a request with no topic, or a polite refusal |

## Run it: the details

The setup commands and the four doors are in the [README](../README.md#run-it).

### More settings

- **MongoDB somewhere else:** put its address in `MONGODB_URI`, in `.env`. A cloud cluster should work the same way: not tried.
- **Postgres (optional):** create a database called `who_to_ask`. Then, in `.env`, remove the `#` in front of the `POSTGRES_URI` line and put your password in it. Without Postgres, the app runs the same way, and it forgets its conversations when it stops.
- **LangSmith (optional):** put a key after `LANGSMITH_API_KEY=`, and every run is traced in the project `who-to-ask`.

### The API, the page, and the MCP server

- **The API** has two endpoints. `POST /ask` takes `{"question": "..."}` and returns the answer as JSON: a `status` (`answered`, `person`, `needs_details`, `nobody_found`, or `off_topic`), the cards, the note, and the step lines. `POST /ask/stream` sends each step line while the agent works, then the same answer.
  - Every answer has a `thread_id`. Send it back with a follow-up, and the agent knows who "her" is.
  - When the agent asks a question (`needs_details`), answer with the `id` of a choice as `question`, the same `thread_id`, and `"is_answer": true`.
  - `user_name` and `user_team` are optional. They fill the first sentence of the suggested messages, and they go nowhere else: not to the LLM, not to the memory, and not to the log.
- **The page** uses six packages, and no more: React (two packages), TypeScript, the build tool Vite, and TypeScript's two descriptions of React.
- **The MCP server.** MCP is a standard way to plug tools into an AI assistant. The app of the assistant starts the server itself and talks to it through the program's input and output, so nothing listens on a port. An app needs three things to connect: the command (the Python of the venv), its two arguments (`-m mcp_server.server`), and `PYTHONPATH` set to the project folder. For example, with Claude Code:

  ```powershell
  claude mcp add --env "PYTHONPATH=C:\path\to\who-to-ask" --transport stdio who-to-ask -- "C:\path\to\who-to-ask\venv\Scripts\python.exe" -m mcp_server.server
  ```

  The server has two tools: `ask(question, thread_id)` for a question or a follow-up, and `pick_choice(thread_id, choice_id)` to answer a question of the agent. A tool gives the answer back as one short text, built in code: what the terminal shows, without the links and the step lines. I tried it with Claude Code. Cursor, Claude Desktop, and the MCP Inspector are not tried.

## The honest test

The kinds of tests and their numbers are in the [README](../README.md#how-it-was-tested).

The demo scenarios were written together with the data, so they can look rigged. So on 2026-11-20 I wrote 20 questions of my own from a one-page summary of the company (`data/company_summary.md`), with a scoring guide. I kept them closed for Claude Code, the AI assistant that wrote the data and most of the code, until the day of the test. The official test is one run, on the code and the data as they were, scored strictly: in doubt, the lower score.

- **The first run, the official score: 14 of 20.** Nobody wrong was recommended, nobody who left or opted out appeared, and what had to be refused was refused. Four of the six misses were one kind of question, "X is broken, who do I talk to?": no ticket describes a new problem, so the answer was "nobody found", although people work on that system. The two others were strict calls of my guide.
- **After two fixes: 19 of 20,** which can move by one from run to run (see the second limit). The fixes: when nothing is about the exact problem and the question names a system, the agent now shows the people who work on that system, under a clear label. And a question with no topic ("I need help. Who should I ask?") is no longer searched: the agent asks what I need.
- **What Git can't prove.** This repository was published with a fresh history, so Git no longer shows the order of events: it can't prove that I wrote my questions before the data. The log files and the commit ids that the scoring files and the `run_info.json` files name are not in this repository.
- **The record:** the questions and the guide (`evaluation/honest_questions.md`), every answer of the first run with its scoring (`evaluation/honest_run/`), and the three runs side by side (`evaluation/honest_run_after_fixes/scoring.md`).

## The limits

- **The second level needs the name of the system, written right.** With a spelling mistake ("Policy Admn") or a description in place of the name, the answer can still be "nobody found". I checked the fix with 11 more questions of my own, five tries each: 45 of 55 answers pass (`evaluation/check_questions_run/`). I prefer "nobody found" to a wrong name: in 135 tries on nine trap questions, about things that are none of the 16 systems, no system was named.
- **`verify` does not always give the same verdict on the same ticket,** so an answer that depends on one borderline ticket can change from one run to the next.
- **A request with one empty word can still get people.** "Something is broken. Who should I call?" got three people in 3 tries of 3: a wrong answer.
- **It is a prototype.** No login and no limit on the number of questions: the API only listens on the computer that runs it. Old conversations are never deleted, whoever has the id of a conversation can continue it, and the memory keeps the text of the questions.
- **Smaller ones.** The agent asks one question per request, and it only spots a vague system name. A follow-up knows the people of the earlier answers, not their topic. The page forgets the conversation when it is reloaded, except my name and my team. Through MCP, what an assistant says with the text of a tool is the assistant's own.

## Next steps

- **Ask `verify` three times** for each ticket or page, and keep the majority. It triples the calls of the most expensive step, so it has to be measured first.
- **Help the second level with names:** give `understand` the one-line description of each system, give each system a French name in the data, and say that a misspelled name is still a name. It makes a wrong name more likely, so the trap questions have to be measured again.
- **Close the gap of the empty words:** a short list in plain code ("problem", "issue", "broken"), or a "no topic" road in `understand`.
- **Follow the links between tickets,** so that a ticket that only says "follows X" is not missed when it is read alone.
- **The other direction of MCP:** the agent itself uses MCP tools, for example a real Jira or Confluence server, through LangChain's MCP adapters.
- **Wait for replies, and rank again from them.** Today the app never sends anything, on purpose.
- **For real use:** real connectors in place of the fake data, a login, and a rule that deletes old conversations.

## More to read

- `data/scenario_evidence.md`: for each demo scenario, who has which evidence, and why they rank where they do.
- `docs/page_mockup.html`: my drawing of the page.
