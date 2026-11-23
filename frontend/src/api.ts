// The one place where the page talks to the API.
import type { Question, StreamEvent } from "./types";

/** Where the API listens: the address that "python -m uvicorn api.main:app" prints when it starts. */
const API_URL = "http://127.0.0.1:8000";

/**
 * Send one question to POST /ask/stream, and call onEvent for each line of the answer, as soon as it arrives.
 *
 * The API answers with JSON Lines: one JSON object per line. First one line per step that the agent finished,
 * then one last line with the answer (or with an error).
 */
export async function askStream(body: Question, onEvent: (event: StreamEvent) => void): Promise<void> {
  const response = await fetch(`${API_URL}/ask/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok || !response.body) {
    throw new Error(`The API answered with the code ${response.status}`);
  }

  // The body arrives in pieces, and a piece can end in the middle of a line. So the text is collected,
  // every complete line is read, and the unfinished end waits for the next piece
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let waiting = "";
  for (;;) {
    const { done, value } = await reader.read();
    if (done) {
      break;
    }
    waiting += decoder.decode(value, { stream: true });
    const lines = waiting.split("\n");
    waiting = lines.pop() ?? "";
    for (const line of lines) {
      if (line.trim()) {
        onEvent(JSON.parse(line) as StreamEvent);
      }
    }
  }
  if (waiting.trim()) {
    onEvent(JSON.parse(waiting) as StreamEvent);
  }
}
