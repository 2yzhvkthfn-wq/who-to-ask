// The page: two optional boxes, the conversation, and the question box.
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";

import { AnswerView } from "./AnswerView";
import { askStream } from "./api";
import type { Answer, Choice, Question } from "./types";

/** The questions that the empty page offers. One click asks one. */
const EXAMPLES = [
  "Who can help me get access to the API?",
  "Who is Sophie Martin's manager?",
  "Qui peut m'aider avec la traduction du portail client ?",
];
/** What the page says when it can't reach the API at all. */
const NO_API = "The page could not reach the API. Is it running? Start it with: python -m uvicorn api.main:app";
/** The names under which the browser remembers the two boxes. */
const NAME_KEY = "who-to-ask.name";
const TEAM_KEY = "who-to-ask.team";

/** One question of the conversation, and everything that came back for it. */
interface Turn {
  id: number;
  question: string;
  /** The grey lines that arrived before the agent's own question, or before the answer */
  steps: string[];
  /** The agent's own question, when the run paused: "Which one do you mean?", with its choices */
  asked?: Answer;
  /** True while the agent waits for my pick */
  waiting: boolean;
  /** The id of the choice I clicked */
  picked?: string;
  /** The grey lines that arrived after my pick */
  stepsAfter: string[];
  answer?: Answer;
  error?: string;
}

/** Read a value that the browser remembers. Some browsers refuse: the box then just starts empty. */
function recall(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return "";
  }
}

/** Ask the browser to remember a value. Nothing is sent anywhere: it stays in this browser. */
function remember(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // The page works the same without it
  }
}

export function App() {
  const [userName, setUserName] = useState(() => recall(NAME_KEY));
  const [userTeam, setUserTeam] = useState(() => recall(TEAM_KEY));
  const [question, setQuestion] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  // True while the agent works: the page sends one question at a time
  const [busy, setBusy] = useState(false);
  // The id of the conversation. The first answer gives it, and every later request sends it back,
  // so the agent knows who "her" is in a follow-up
  const threadId = useRef<string | undefined>(undefined);
  const nextId = useRef(1);
  const end = useRef<HTMLDivElement>(null);

  // The two boxes are remembered in this browser, so I don't type them again next time.
  // (An effect is code that React runs after it has drawn the page. It must return nothing, hence the braces:
  // in a recent browser, scrollIntoView() returns a value)
  useEffect(() => {
    remember(NAME_KEY, userName);
  }, [userName]);
  useEffect(() => {
    remember(TEAM_KEY, userTeam);
  }, [userTeam]);
  // Each new line moves the view down, so the newest step or card is on the screen
  useEffect(() => {
    end.current?.scrollIntoView();
  }, [turns]);

  /** Change one turn of the conversation, and leave the others as they are. */
  function change(id: number, update: (turn: Turn) => Turn): void {
    setTurns((all) => all.map((turn) => (turn.id === id ? update(turn) : turn)));
  }

  /** Send one request for a turn, and put each line of the stream where it belongs. */
  async function run(id: number, body: Question, afterPick: boolean): Promise<void> {
    setBusy(true);
    const request: Question = {
      ...body,
      thread_id: threadId.current,
      // The boxes are read now, when the question is sent. An empty box is not sent at all
      user_name: userName.trim() || undefined,
      user_team: userTeam.trim() || undefined,
    };
    try {
      await askStream(request, (event) => {
        if (event.type === "step") {
          // A step the agent just finished: one more grey line
          change(id, (turn) =>
            afterPick
              ? { ...turn, stepsAfter: [...turn.stepsAfter, event.text] }
              : { ...turn, steps: [...turn.steps, event.text] },
          );
        } else if (event.type === "answer") {
          threadId.current = event.answer.thread_id;
          // An answer with choices is the agent's own question: the run is paused until I pick one
          const pauses = !afterPick && event.answer.status === "needs_details" && event.answer.choices.length > 0;
          change(id, (turn) =>
            pauses
              ? { ...turn, asked: event.answer, waiting: true }
              : { ...turn, answer: event.answer, waiting: false },
          );
        } else {
          // The agent failed in the middle: the API sends one fixed sentence
          change(id, (turn) => ({ ...turn, error: event.message, waiting: false }));
        }
      });
    } catch {
      change(id, (turn) => ({ ...turn, error: NO_API, waiting: false }));
    } finally {
      setBusy(false);
    }
  }

  /** Ask a new question: what I typed, or an example I clicked. */
  function ask(text: string): void {
    const asked = text.trim();
    if (!asked || busy) {
      return;
    }
    const id = nextId.current++;
    // What I type is always a new question. If the agent was waiting for a pick, its question is dropped:
    // the API does the same on its side
    setTurns((all) => [
      ...all.map((turn) => ({ ...turn, waiting: false })),
      { id, question: asked, steps: [], stepsAfter: [], waiting: false },
    ]);
    setQuestion("");
    void run(id, { question: asked }, false);
  }

  /** Answer the agent's question: a click on a choice sends its id, as an answer. */
  function pick(turn: Turn, choice: Choice): void {
    if (busy || !turn.waiting) {
      return;
    }
    change(turn.id, (current) => ({ ...current, picked: choice.id, waiting: false }));
    void run(turn.id, { question: choice.id, is_answer: true }, true);
  }

  function submit(event: FormEvent): void {
    event.preventDefault();
    ask(question);
  }

  const lastId = turns.length > 0 ? turns[turns.length - 1].id : 0;
  return (
    <main className="page">
      <header>
        <h1>Who to ask</h1>
        <p className="intro">
          Ask who can help you with a work topic, or ask about a colleague. Tamberly Insurance is a made-up
          company, and all its data is fake.
        </p>
      </header>

      <div className="boxes">
        <div className="field">
          <label htmlFor="user-name">
            Your name <span className="optional">(optional)</span>
          </label>
          <input
            id="user-name"
            type="text"
            maxLength={60}
            autoComplete="off"
            value={userName}
            onChange={(event) => setUserName(event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="user-team">
            Your team <span className="optional">(optional)</span>
          </label>
          <input
            id="user-team"
            type="text"
            maxLength={60}
            autoComplete="off"
            value={userTeam}
            onChange={(event) => setUserTeam(event.target.value)}
          />
        </div>
        <p className="hint">They fill the first sentence of the suggested messages, and are used for nothing else.</p>
      </div>

      {turns.length > 0 && (
        <div className="conversation" aria-live="polite">
          {turns.map((turn) => (
            <TurnView
              key={turn.id}
              turn={turn}
              working={busy && turn.id === lastId}
              canPick={!busy && turn.waiting}
              onPick={(choice) => pick(turn, choice)}
            />
          ))}
        </div>
      )}

      {turns.length === 0 && (
        <div className="examples">
          <span className="examples-title">Or try one of these</span>
          {EXAMPLES.map((example) => (
            <button key={example} type="button" className="example" disabled={busy} onClick={() => ask(example)}>
              {example}
            </button>
          ))}
        </div>
      )}

      <form className="ask" onSubmit={submit}>
        <div className="field">
          <label htmlFor="question">Your question</label>
          <input
            id="question"
            type="text"
            maxLength={1000}
            autoComplete="off"
            placeholder={
              turns.length === 0
                ? "Ask a question, in English or in French"
                : "Ask another question, or a follow-up like “And who’s her manager?”"
            }
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
          />
        </div>
        <button type="submit" className="btn primary" disabled={busy || !question.trim()}>
          Ask
        </button>
      </form>
      <div ref={end} />
    </main>
  );
}

interface TurnViewProps {
  turn: Turn;
  /** True while the agent works on this turn */
  working: boolean;
  /** True while a click on a choice of this turn is an answer */
  canPick: boolean;
  onPick: (choice: Choice) => void;
}

/** One turn: my question, the grey steps, the agent's own question if it asked one, and the answer. */
function TurnView({ turn, working, canPick, onPick }: TurnViewProps) {
  return (
    <section className="turn">
      <div className="you">
        <span className="who">You</span>
        <p>{turn.question}</p>
      </div>

      <Steps lines={turn.steps} working={working && !turn.asked} />

      {turn.asked && (
        <div className="agent-question">
          <span className="who">Agent</span>
          <p>{turn.asked.message}</p>
          <div className="choices">
            {turn.asked.choices.map((choice) => {
              const chosen = turn.picked === choice.id;
              return (
                <button
                  key={choice.id}
                  type="button"
                  className={chosen ? "choice chosen" : "choice"}
                  aria-pressed={chosen}
                  disabled={!canPick}
                  onClick={() => onPick(choice)}
                >
                  <span className="name">
                    {choice.name}
                    {chosen && <span className="mark"> · your choice</span>}
                  </span>
                  {choice.detail && <span className="about">{choice.detail}</span>}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {turn.asked && <Steps lines={turn.stepsAfter} working={working} />}

      {/* I typed another question instead of picking: the agent dropped this one, and the page says so */}
      {turn.asked && !turn.waiting && !turn.picked && !turn.error && (
        <ul className="steps">
          <li>· Not answered: you asked another question instead</li>
        </ul>
      )}

      {turn.error && (
        <p className="error" role="alert">
          {turn.error}
        </p>
      )}

      {turn.answer && <AnswerView answer={turn.answer} />}
    </section>
  );
}

/** The small grey lines: what the agent has done so far, one line per step. */
function Steps({ lines, working }: { lines: string[]; working: boolean }) {
  if (lines.length === 0 && !working) {
    return null;
  }
  return (
    <ul className="steps">
      {lines.map((line, index) => (
        <li key={index}>· {line}</li>
      ))}
      {working && <li>· Working…</li>}
    </ul>
  );
}
