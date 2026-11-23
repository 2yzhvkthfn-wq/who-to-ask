// What the page shows for one answer: a sentence, the note, the cards of the people, or the card of one colleague.
// Every text comes from the API. React writes it as text, never as HTML, so nothing in it can change the page.
import type { Answer, Evidence, ExpertCard, PersonCard } from "./types";

type Labels = Record<string, string>;

/** True when the answer has a person card: without one, the API sends an empty object. */
function isPersonCard(card: Answer["person_card"]): card is PersonCard {
  return "id" in card;
}

export function AnswerView({ answer }: { answer: Answer }) {
  const person = isPersonCard(answer.person_card) ? answer.person_card : undefined;
  return (
    <>
      {/* A sentence of the agent: the answer about a colleague, a refusal, or "nobody found" */}
      {answer.message && (
        <div className="agent-says">
          <span className="who">Agent</span>
          <p>{answer.message}</p>
        </div>
      )}

      {/* The note comes just before the cards: who was removed from the answer, and why */}
      {answer.note && <p className="note">{answer.note}</p>}

      {answer.cards.map((card, index) => (
        <ExpertCardView key={card.id} position={index + 1} card={card} labels={answer.labels} />
      ))}

      {/* Someone who left the company has no card: the sentence above says all there is to say */}
      {person && !person.left && <PersonCardView card={person} labels={answer.labels} />}
    </>
  );
}

/** The card of one recommended person: who, why, the evidence, the suggested message, and the two buttons. */
function ExpertCardView({ position, card, labels }: { position: number; card: ExpertCard; labels: Labels }) {
  return (
    <article className="card">
      <div className="card-top">
        <div className="who-it-is">
          <h2>
            {position}. {card.name}
          </h2>
          <span className="role">
            {card.job_title} · {card.team}
          </span>
          <span className="email">{card.email}</span>
        </div>
        {card.out_of_office_text && <span className="away">{card.out_of_office_text}</span>}
      </div>

      <p className="why">{card.why}</p>

      <div className="part">
        <span className="part-title">{labels.evidence}</span>
        <EvidenceList items={card.evidence} />
      </div>

      <div className="part">
        <span className="part-title">{labels.message}</span>
        <p className="message">{card.message}</p>
      </div>

      {/* The two buttons are links. They open my own Teams or email app, with the message filled in:
          the page itself sends nothing */}
      <div className="actions">
        <a className="btn primary" href={card.teams_link} target="_blank" rel="noreferrer">
          {labels.teams}
        </a>
        <a className="btn secondary" href={card.email_link}>
          {labels.send_email}
        </a>
      </div>
    </article>
  );
}

/** The card of one colleague: the directory fields, what was asked for, and two buttons with no message. */
function PersonCardView({ card, labels }: { card: PersonCard; labels: Labels }) {
  return (
    <article className="card">
      <div className="card-top">
        <div className="who-it-is">
          <h2>{card.name}</h2>
          <span className="role">
            {card.job_title} · {card.team}
          </span>
          <span className="email">{card.email}</span>
        </div>
        {card.out_of_office_text && <span className="away">{card.out_of_office_text}</span>}
      </div>

      {/* A line with no value is not shown: the head of the department has no manager,
          and the work phone is only there when the question asked for it */}
      <dl className="facts">
        {card.manager && <Fact label={labels.manager} value={card.manager} />}
        <Fact label={labels.languages} value={card.languages.join(", ")} />
        {card.work_phone && <Fact label={labels.work_phone} value={card.work_phone} />}
      </dl>

      {/* "What does she work on?": her tickets and pages, one group per system */}
      {card.work.map((group) => (
        <div className="part" key={group.system}>
          <span className="part-title">{group.system}</span>
          <EvidenceList items={group.items} />
        </div>
      ))}

      <div className="actions">
        <a className="btn primary" href={card.teams_link} target="_blank" rel="noreferrer">
          {labels.open_teams}
        </a>
        <a className="btn secondary" href={card.email_link}>
          {labels.write_email}
        </a>
      </div>
    </article>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="fact">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}

/** One line per ticket or page: what the person did, then the date in softer text. */
function EvidenceList({ items }: { items: Evidence[] }) {
  return (
    <ul className="evidence">
      {items.map((item) => (
        <li key={`${item.id}-${item.kind}`}>
          <span className="what">{item.text}</span>
          <span className="when">{item.date_text}</span>
        </li>
      ))}
    </ul>
  );
}
