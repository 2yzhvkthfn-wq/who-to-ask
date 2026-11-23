// The shapes of what the API sends and receives. They describe the dicts that the Python code builds
// (backend/agents/answer_builder.py and backend/api/main.py): TypeScript then checks that the page reads them correctly.

/** The body of a request to POST /ask/stream. */
export interface Question {
  /** What I typed. Or, with is_answer, the id of the choice I clicked */
  question: string;
  /** The id of the conversation: the API gives one with its first answer, and the page sends it back */
  thread_id?: string;
  /** True when this request is my answer to a question of the agent */
  is_answer?: boolean;
  /** The two optional boxes: they fill the first sentence of the suggested messages */
  user_name?: string;
  user_team?: string;
}

/** One ticket or page that counts for a person: what the person did, and when. */
export interface Evidence {
  id: string;
  title: string;
  source: string;
  kind: string;
  /** What the person did, in words: wrote "a page", or handled CLM-212: its summary */
  text: string;
  /** "updated 14 October 2026", "resolved 2 October 2026", or "meeting of 13 November 2025" */
  date_text: string;
}

/** The card of a person that the agent recommends. */
export interface ExpertCard {
  id: string;
  name: string;
  job_title: string;
  team: string;
  email: string;
  /** "Out of office until 10 November 2026", or an empty text */
  out_of_office_text: string;
  why: string;
  evidence: Evidence[];
  subject: string;
  message: string;
  teams_link: string;
  email_link: string;
}

/** The tickets and pages of a colleague that are about one system. */
export interface WorkGroup {
  system: string;
  items: Evidence[];
}

/** The card of one colleague, for a question about a person. */
export interface PersonCard {
  id: string;
  name: string;
  /** True for someone who left the company: the card then only has the name */
  left: boolean;
  job_title: string;
  team: string;
  manager: string;
  email: string;
  languages: string[];
  work_phone: string;
  out_of_office_text: string;
  work: WorkGroup[];
  teams_link: string;
  email_link: string;
}

/** One choice of a question that the agent asks: a system, or a person. */
export interface Choice {
  id: string;
  name: string;
  /** One line that tells the choices apart: a description, or a job title and a team */
  detail: string;
}

/** The answer to one question. Its status says which kind of answer it is. */
export interface Answer {
  status: "answered" | "person" | "needs_details" | "nobody_found" | "off_topic";
  language: "en" | "fr";
  /** The agent's question, a sentence that answers, or the text of a refusal or of "nobody found" */
  message: string;
  cards: ExpertCard[];
  /** An empty object when the answer has no person card */
  person_card: PersonCard | Record<string, never>;
  choices: Choice[];
  /** Who was removed from the answer, and why */
  note: string;
  /** The labels of a card, in the language of the answer: "Evidence", "Suggested message", ... */
  labels: Record<string, string>;
  steps: string[];
  thread_id: string;
}

/** One line of the stream: a step the agent finished, the answer, or an error. */
export type StreamEvent =
  | { type: "step"; text: string }
  | { type: "answer"; answer: Answer }
  | { type: "error"; message: string };
