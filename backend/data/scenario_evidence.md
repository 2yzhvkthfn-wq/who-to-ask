# Scenario evidence

This page is **generated** by `python -m scripts.show_scenarios`, from `data/scenarios.json` and the data. Don't edit it by hand: a test fails when it no longer matches the data.

For each demo scenario, it shows who has which evidence, and why they rank where they do.

How to read a table:

- The evidence listed is what a correct `verify` keeps. Near-misses are listed under each table.
- **Counts first?** says whether the person has evidence in the source that counts first.
- **Pieces** counts all of the person's evidence, from both sources.
- The order: people with evidence in the first source, then more pieces, then the most recent piece, then the lower person id.
- Then the HR check removes people who left or opted out, and the first three become cards.
- A "decided" question is stricter: only decisions count. People who only have tickets and docs about the question are listed under the table, and they get no card.

Reporting a ticket, commenting, organizing or attending a meeting, and writing an agenda or the minutes count for nothing.

## Scenario 1 (case `s01`, checked at M3b)

What it tests: A colleague who opted out never appears anywhere. A colleague who left is not recommended, and the note names him.

**Question:** "Who can help me get access to the Claims API?"

Road: find an expert. Type of question: **help**, so Confluence counts first, and Jira second.

| Rank | Person | Confluence | Jira | Counts first? | Pieces | Latest | Result |
|---|---|---|---|---|---|---|---|
| 1 | Sophie Martin | wrote pg008 "Claims API: Access Guide" | assigned CLM-212, CLM-245, CLM-301 | Yes | 4 | 2026-09-25 | Card 1 |
| 2 | Étienne Lavoie | wrote pg002 "Claims API - how to get an API key" |  | Yes | 1 | 2024-02-06 | Removed: left the company |
| 3 | David Chen |  | approved CLM-212, CLM-226, CLM-239, CLM-245, CLM-268, CLM-301 | No | 6 | 2026-09-25 | Card 2 |
| 4 | Nadia Benali |  | assigned CLM-226, CLM-239 | No | 2 | 2026-04-24 | Removed: opted out |
| 5 | Olivia Tremblay |  | assigned CLM-268 | No | 1 | 2026-07-10 | Card 3 |

- **Removed, left the company:** Étienne Lavoie. The note names them.
- **Removed, opted out:** Nadia Benali. The answer only counts them, and never names them.
- **Out of office on the cards:** Sophie Martin until 2026-11-10.
- **Must not appear:** Nadia Benali has evidence, but opted out. The HR check removes this person.
- **Must not appear:** Étienne Lavoie has evidence, but left the company. The HR check removes this person.
- **Must not appear:** Hélène Dubois has no evidence that holds up. What this person did here counts for nothing (meeting pages as organizer: 1). Only a near-miss leads to this person: pg027 "Claims Platform team meeting: minutes, 10 September 2026".
- **On topic, but it leads to nobody:** CLM-318: It is a Claims API access request, but it has no assignee and no approver yet. So `search` drops it before `verify`.
- **`verify` must reject** pg004 "Policy API: developer guide": It explains how to get access to the Policy API, not to the Claims API. If it were kept, it would count for Amira Khalil.
- **`verify` must reject** POL-176: It is an access request for the Policy API. If it were kept, it would count for Lucas Pelletier, David Chen.
- **`verify` must reject** pg027 "Claims Platform team meeting: minutes, 10 September 2026": It is a meeting of the team that owns the Claims API, but it is about Claims Intake. If it were kept, it would count for Hélène Dubois.
- **`verify` must reject** pg020 "Fraud Scoring Model: overview and runbook": It is about the fraud model. It only says that its nightly job reads the Claims API. If it were kept, it would count for Priya Patel.
- **`verify` must reject** CLM-233: It is a bug in the Claims API, not about getting access. If it were kept, it would count for Olivia Tremblay.
- **`verify` must reject** pg026 "Login problems": It is about signing in. Its last lines only say to ask the team that owns a system. If it were kept, it would count for Alexandre Bergeron.
- **If the question were read as "did":** David Chen, Sophie Martin, Olivia Tremblay. The expected people are still there.
- **If the question were read as "decided":** nobody found. The expected people are NOT all there.

## Scenario 2 (case `s02`, checked at M3b)

What it tests: Jira and Confluence working together.

**Question:** "Our pricing engine rejects some new Quebec postal codes. Who should I talk to?"

Road: find an expert. Type of question: **help**, so Confluence counts first, and Jira second.

| Rank | Person | Confluence | Jira | Counts first? | Pieces | Latest | Result |
|---|---|---|---|---|---|---|---|
| 1 | Karim Haddad | wrote pg005 "Territory mapping: from postal code to rating territory" | assigned PRC-88, PRC-91, PRC-95 | Yes | 4 | 2026-10-29 | Card 1 |
| 2 | Nathalie Côté |  | approved PRC-91 | No | 1 | 2026-09-11 | Card 2 |

- **No out-of-office line, because the date is in the past:** Karim Haddad (2026-10-23).
- **`verify` must reject** pg021 "Underwriting Rules: flood-zone postal codes": It is the underwriting rule that declines known postal codes in flood zones, not the Pricing Engine. If it were kept, it would count for Samuel Okafor.
- **`verify` must reject** PRC-74: It updates the flood-zone rule. Nothing is rejected by the Pricing Engine. If it were kept, it would count for Samuel Okafor, Nathalie Côté.
- **`verify` must reject** DIG-178: The portal's address form refused a postal code with a space. The Pricing Engine never saw it. If it were kept, it would count for Marc-André Gagnon.
- **`verify` must reject** pg018 "Data Warehouse: table catalogue": It lists the tables of the Data Warehouse. It only says that rejected quotes are not stored. If it were kept, it would count for Yuki Tanaka.
- **`verify` must reject** pg013 "Weekly notes": They are running notes of the data team. The new postal code areas are one line in them. If it were kept, it would count for Rachel Goldberg.
- **`verify` must reject** CLM-212: The Pricing Engine asks for access to the Claims API. Nothing is about postal codes. If it were kept, it would count for Sophie Martin, David Chen.
- **If the question were read as "did":** Karim Haddad, Nathalie Côté. The expected people are still there.
- **If the question were read as "decided":** nobody found. The expected people are NOT all there.

## Scenario 3 (case `s03`, checked at M3b)

What it tests: Only the person who decided is shown. The coordinator who organized every meeting and wrote the agendas must not appear, and neither do the people who did the work.

**Question:** "Who decided to move the policy database to the cloud?"

Road: find an expert. Type of question: **decided**, so only a decision in meeting minutes counts. Tickets and docs count for nobody.

| Rank | Person | Evidence that counts | Pieces | Latest | Result |
|---|---|---|---|---|---|
| 1 | Isabelle Roy | decided pg011 "Architecture Review Board: minutes, 13 November 2025" | 1 | 2025-11-13 | Card 1 |

- **No other card:** the scenario expects exactly Isabelle Roy.
- **Doesn't count for a "decided" question:** Isabelle Roy also wrote pg009 "Options paper: where should the Policy Database run after 2027?".
- **Not shown:** Wei Zhang has evidence, but none that counts for a "decided" question (wrote pg023 "Policy Database migration runbook (draft)"; assigned POL-164, INF-219).
- **Not shown:** Fatima Rahimi has evidence, but none that counts for a "decided" question (assigned INF-204, INF-231).
- **Must not appear:** Julie Bernard has no evidence that holds up. What this person did here counts for nothing (minutes written: 4, agendas written: 2, meeting pages as organizer: 6, tickets reported: 1).
- **On topic, but it leads to nobody:** pg010 "Architecture Review Board: agenda, 13 November 2025": It is the agenda of the meeting where the decision was made. Writing an agenda counts for nothing. So `search` drops it before `verify`.
- **On topic, but it leads to nobody:** pg028 "Policy Database migration: steering committee agenda, 23 September 2026": It is an agenda. It lists options for a date, but it decides nothing. So `search` drops it before `verify`.
- **`verify` must reject** pg016 "Legacy Policy System: minutes of the decision meeting, 12 February 2026": It is another decision, by another person: retiring the Legacy Policy System. If it were kept, it would count for Daniel Morin.
- **If `verify` also keeps** pg019 "Policy Database migration: steering committee minutes, 18 March 2026", pg029 "Policy Database migration: steering committee minutes, 23 September 2026", the cards become: Isabelle Roy.
- **If the question were read as "help":** Wei Zhang, Isabelle Roy, Fatima Rahimi. The expected people are still there.
- **If the question were read as "did":** Wei Zhang, Fatima Rahimi, Isabelle Roy. The expected people are still there.

## Scenario 4 (case `s04`, checked at M3b)

What it tests: A French question, French pages, and an answer in French.

**Question:** "Qui peut m'aider avec la traduction du portail client ?"

Road: find an expert. Type of question: **help**, so Confluence counts first, and Jira second.

| Rank | Person | Confluence | Jira | Counts first? | Pieces | Latest | Result |
|---|---|---|---|---|---|---|---|
| 1 | Marc-André Gagnon | wrote pg012 "Guide de traduction du portail client" | assigned DIG-141, DIG-156 | Yes | 3 | 2026-08-25 | Card 1 |
| 2 | Sophie Nguyen |  | assigned DIG-163 | No | 1 | 2026-06-10 | Card 2 |

- **`verify` must reject** DIG-170: It is about the language switch of the Broker Portal, not the Customer Portal. If it were kept, it would count for Catherine Leblanc.
- **`verify` must reject** DIG-178: It is a bug in the address form, not a translation problem. If it were kept, it would count for Marc-André Gagnon.
- **`verify` must reject** CLM-226: It is written in French and names the Customer Portal, but it is an access request to the Claims API. If it were kept, it would count for Nadia Benali, David Chen.
- **`verify` must reject** POL-176: It is written in French and names the Customer Portal, but it is an access request to the Policy API. If it were kept, it would count for Lucas Pelletier, David Chen.
- **`verify` must reject** pg025 "Broker Portal: onboarding a new brokerage": It is about the Broker Portal. It only mentions a language bug that was fixed. If it were kept, it would count for Catherine Leblanc.
- **If `verify` also keeps** pg022 "Réunion d'équipe Canaux numériques : compte rendu du 4 juin 2026", the cards become: Marc-André Gagnon, Catherine Leblanc, Sophie Nguyen.
- **If the question were read as "did":** Marc-André Gagnon, Sophie Nguyen. The expected people are still there.
- **If the question were read as "decided":** nobody found. The expected people are NOT all there.

## Scenario 5 (case `s05`, checked at M3b)

What it tests: The former owner left the company (the HR file says so) and must not be recommended.

**Question:** "Who knows the fraud scoring model?"

Road: find an expert. Type of question: **help**, so Confluence counts first, and Jira second.

| Rank | Person | Confluence | Jira | Counts first? | Pieces | Latest | Result |
|---|---|---|---|---|---|---|---|
| 1 | Priya Patel | wrote pg020 "Fraud Scoring Model: overview and runbook" | assigned DAT-67, DAT-73 | Yes | 3 | 2026-10-06 | Card 1 |
| 2 | Tom Walsh | wrote pg003 "Fraud Scoring Model v2 - design notes" | assigned DAT-52, DAT-60 | Yes | 3 | 2026-03-20 | Removed: left the company |
| 3 | Yuki Tanaka |  | assigned DAT-70 | No | 1 | 2026-05-22 | Card 2 |

- **Removed, left the company:** Tom Walsh. The note names them.
- **Must not appear:** Tom Walsh has evidence, but left the company. The HR check removes this person.
- **`verify` must reject** CLM-245: It is an access request to the Claims API for the fraud job. It says nothing about the model. If it were kept, it would count for Sophie Martin, David Chen.
- **If `verify` also keeps** pg013 "Weekly notes", CLM-254, the cards become: Priya Patel, Rachel Goldberg, Olivia Tremblay.
- **If the question were read as "did":** Priya Patel, Yuki Tanaka. The expected people are still there.
- **If the question were read as "decided":** nobody found. The expected people are NOT all there.

## Scenario 6 (case `s06`, checked at M3b)

What it tests: A question that is not about work gets the failsafe answer.

**Question:** "What's the weather in Montreal today?"

Expected: the failsafe answer for a question that is not about work. Nothing in the data is needed.

## Scenario 7 (case `s07`, checked at M3b)

What it tests: A generic roadmap page exists, and its author must not be suggested.

**Question:** "Who can help with our quantum computing roadmap?"

Road: find an expert. Expected: **nobody found**.

- No ticket and no page contains the word "quantum".
- **`verify` must reject** pg014 "Technology Roadmap 2026-2028": It is the general technology roadmap. It says nothing about quantum computing. If it were kept, it would count for Robert Lefebvre.
- **`verify` must reject** pg016 "Legacy Policy System: minutes of the decision meeting, 12 February 2026": It only mentions the technology roadmap in one action item. It is about the Legacy Policy System. If it were kept, it would count for Daniel Morin.

## Scenario 8 (case `s08a`, checked at M7)

What it tests: The agent asks which API instead of guessing. Here the user picks the Claims API.

**Question:** "Who can help me with the API?"

Expected: the agent asks a question, and the choices come from the data.

- The systems with "API" in their name: Claims API, Policy API.

**Question:** "The Claims API"

Road: find an expert. Type of question: **help**, so Confluence counts first, and Jira second.

| Rank | Person | Confluence | Jira | Counts first? | Pieces | Latest | Result |
|---|---|---|---|---|---|---|---|
| 1 | Sophie Martin | wrote pg008 "Claims API: Access Guide" | assigned CLM-212, CLM-245, CLM-301 | Yes | 4 | 2026-09-25 | Card 1 |
| 2 | Étienne Lavoie | wrote pg002 "Claims API - how to get an API key" |  | Yes | 1 | 2024-02-06 | Removed: left the company |
| 3 | David Chen |  | approved CLM-212, CLM-226, CLM-239, CLM-245, CLM-268, CLM-301 | No | 6 | 2026-09-25 | Card 2 |
| 4 | Olivia Tremblay |  | assigned CLM-233, CLM-268 | No | 2 | 2026-07-10 | Card 3 |
| 5 | Nadia Benali |  | assigned CLM-226, CLM-239 | No | 2 | 2026-04-24 | Removed: opted out |

- **Removed, left the company:** Étienne Lavoie. The note names them.
- **Removed, opted out:** Nadia Benali. The answer only counts them, and never names them.
- **Out of office on the cards:** Sophie Martin until 2026-11-10.
- **Must not appear:** Nadia Benali has evidence, but opted out. The HR check removes this person.
- **Must not appear:** Étienne Lavoie has evidence, but left the company. The HR check removes this person.
- **Must not appear:** Hélène Dubois has no evidence that holds up. What this person did here counts for nothing (meeting pages as organizer: 1). Only a near-miss leads to this person: pg027 "Claims Platform team meeting: minutes, 10 September 2026".
- **On topic, but it leads to nobody:** CLM-318: It is a Claims API access request, but it has no assignee and no approver yet. So `search` drops it before `verify`.
- **`verify` must reject** pg004 "Policy API: developer guide": It is the guide of the Policy API. If it were kept, it would count for Amira Khalil.
- **`verify` must reject** POL-176: It is an access request for the Policy API. If it were kept, it would count for Lucas Pelletier, David Chen.
- **`verify` must reject** pg027 "Claims Platform team meeting: minutes, 10 September 2026": It is a meeting of the team that owns the Claims API, but it is about Claims Intake. If it were kept, it would count for Hélène Dubois.
- **`verify` must reject** pg020 "Fraud Scoring Model: overview and runbook": It is about the fraud model. It only says that its nightly job reads the Claims API. If it were kept, it would count for Priya Patel.
- **`verify` must reject** DAT-70: It is a bug in the fraud job. The Claims API is only where the job now reads its data. If it were kept, it would count for Yuki Tanaka.
- **`verify` must reject** pg026 "Login problems": It is about signing in. Its last lines only say to ask the team that owns a system. If it were kept, it would count for Alexandre Bergeron.
- **If the question were read as "did":** David Chen, Sophie Martin, Olivia Tremblay. The expected people are still there.
- **If the question were read as "decided":** nobody found. The expected people are NOT all there.

## Scenario 8 (case `s08b`, checked at M7)

What it tests: The same vague question, when the user picks the Policy API: it has its own people.

**Question:** "Who can help me with the API?"

Expected: the agent asks a question, and the choices come from the data.

- The systems with "API" in their name: Claims API, Policy API.

**Question:** "The Policy API"

Road: find an expert. Type of question: **help**, so Confluence counts first, and Jira second.

| Rank | Person | Confluence | Jira | Counts first? | Pieces | Latest | Result |
|---|---|---|---|---|---|---|---|
| 1 | Amira Khalil | wrote pg004 "Policy API: developer guide" | assigned POL-152 | Yes | 2 | 2026-07-14 | Card 1 |
| 2 | David Chen |  | approved POL-176 | No | 1 | 2026-03-27 | Card 2 |
| 3 | Lucas Pelletier |  | assigned POL-176 | No | 1 | 2026-03-27 | Card 3 |
| 4 | Yuki Tanaka |  | assigned POL-131 | No | 1 | 2025-07-18 | No card: only three are shown |

- **`verify` must reject** pg008 "Claims API: Access Guide": It is the access guide of the Claims API. If it were kept, it would count for Sophie Martin.
- **`verify` must reject** pg023 "Policy Database migration runbook (draft)": It is the migration runbook of the Policy Database. The Policy API is only checked at the end. If it were kept, it would count for Wei Zhang.
- **`verify` must reject** INF-219: It is a dry run of the Policy Database cutover. The Policy API is only named for its checks. If it were kept, it would count for Wei Zhang.
- **If `verify` also keeps** pg015 "Notes", the cards become: Amira Khalil, Lucas Pelletier, David Chen.
- **If the question were read as "did":** Amira Khalil, David Chen, Lucas Pelletier. The expected people are still there.
- **If the question were read as "decided":** nobody found. The expected people are NOT all there.

## Scenario 9 (case `s09a`, checked at M6)

What it tests: The person lookup: the manager comes from the directory, and she is not one of the people recommended in scenario 1.

**Question:** "Who is Sophie Martin's manager?"

Road: about a person. The card shown: **Hélène Dubois**, Team Lead.

- In the directory, the manager of Sophie Martin is Hélène Dubois.
- Hélène Dubois has no evidence in case `s01`, so this person is not on its cards.

## Scenario 9 (case `s09b`, checked at M6)

What it tests: Memory for follow-ups: "her" is the first person shown in the last answer.

**Question:** "Who can help me get access to the Claims API?"

Expected: the same as in case `s01`.
The cards: Sophie Martin, David Chen, Olivia Tremblay.

**Question:** "And who's her manager?"

Road: about a person. The card shown: **Hélène Dubois**, Team Lead.

- In the directory, the manager of Sophie Martin is Hélène Dubois.
- Hélène Dubois has no evidence in case `s01`, so this person is not on its cards.

## Scenario 10 (case `s10`, checked at M6)

What it tests: Work information is answered from the data, and a personal question is refused.

**Question:** "What's Hélène Dubois's work phone?"

Road: about a person. The card shown: **Hélène Dubois**, Team Lead.

- The directory has a work phone for Hélène Dubois: 514-555-0142.

**Question:** "Why is Sophie Martin away?"

Expected: the failsafe answer "I only have work information".

- Sophie Martin is out of office until 2026-11-10. The data holds no reason, so the agent has nothing to leak.

## Scenario 11 (case `s11a`, checked at M6)

What it tests: Someone who left: only "no longer works at the company", with no date and no contact details.

**Question:** "Does Tom Walsh still work here?"

Road: about a person. The card shown: **Tom Walsh**, Senior Data Scientist.

- The HR file says that Tom Walsh left. The answer gives no date and no contact details.

## Scenario 11 (case `s11b`, checked at M6)

What it tests: Someone who opted out: the directory fields only, never their tickets or pages.

**Question:** "Who is Nadia Benali?"

Road: about a person. The card shown: **Nadia Benali**, Developer.

- Nadia Benali opted out of being found, and has 3 tickets or pages. The answer shows the directory fields only.

## Scenario 12 (case `s12`, checked at M7)

What it tests: Two people share a first name, so the agent asks which one instead of guessing.

**Question:** "Tell me about Sophie."

Expected: the agent asks a question, and the choices come from the data.

- The people whose first name is Sophie: Sophie Martin (Senior Developer), Sophie Nguyen (UX Designer).

**Question:** "Sophie Nguyen"

Road: about a person. The card shown: **Sophie Nguyen**, UX Designer.

## Scenario 13 (case `s13`, checked at M6)

What it tests: "What does she work on?": the same evidence as the expert road, read from the person to their tickets and pages, grouped by system.

**Question:** "What does Hélène Dubois work on?"

Road: about a person. The card shown: **Hélène Dubois**, Team Lead.

| System | Ticket or page | Why it counts | Date |
|---|---|---|---|
| Claims Intake | pg027 "Claims Platform team meeting: minutes, 10 September 2026" | decided | 2026-09-10 |
| Claims Intake | CLM-296 | assigned | 2026-10-26 |
| Claims Workbench | CLM-279 | assigned | 2026-08-18 |
| Claims Workbench | pg017 "Claims Workbench: release checklist" | wrote | 2026-09-08 |

## Scenario 14 (case `s14`, checked at M3b)

What it tests: A "did" question: Jira counts first. The team lead who reported the bug and reopened it must not appear. A second postal code bug, in the Customer Portal, may be kept by `verify` without changing the first card. The task that fixed the bug (`PRC-91`) only says that it follows the bug's ticket: `verify` reads each ticket alone, so it may miss it.

**Question:** "Who fixed the postal code bug?"

Road: find an expert. Type of question: **did**, so Jira counts first, and Confluence second.

| Rank | Person | Confluence | Jira | Counts first? | Pieces | Latest | Result |
|---|---|---|---|---|---|---|---|
| 1 | Karim Haddad |  | assigned PRC-88 | Yes | 1 | 2026-10-28 | Card 1 |

- **No out-of-office line, because the date is in the past:** Karim Haddad (2026-10-23).
- **Must not appear:** Catherine Leblanc has no evidence that holds up. What this person did here counts for nothing (tickets reported: 1).
- **`verify` must reject** PRC-74: It updates the flood-zone rule of underwriting. It is a planned change, not a bug. If it were kept, it would count for Samuel Okafor, Nathalie Côté.
- **`verify` must reject** pg021 "Underwriting Rules: flood-zone postal codes": It explains the rule that declines known postal codes in flood zones. Nothing was broken, and nothing was fixed. If it were kept, it would count for Samuel Okafor.
- **`verify` must reject** CLM-245: It is an access request to the Claims API. The postal code is only one of the fields the fraud job reads. If it were kept, it would count for Sophie Martin, David Chen.
- **`verify` must reject** pg013 "Weekly notes": They are running notes of the data team. The new postal code areas are one line in them. If it were kept, it would count for Rachel Goldberg.
- **`verify` must reject** pg018 "Data Warehouse: table catalogue": It lists the tables of the Data Warehouse. It only says how postal codes are stored. If it were kept, it would count for Yuki Tanaka.
- **If `verify` also keeps** PRC-91, PRC-95, pg005 "Territory mapping: from postal code to rating territory", DIG-178, the cards become: Karim Haddad, Marc-André Gagnon, Nathalie Côté.
- **If the question were read as "help":** Karim Haddad. The expected people are still there.
- **If the question were read as "decided":** nobody found. The expected people are NOT all there.

## Scenario 15 (case `s15`, checked at M3b)

What it tests: A "decided" question with no recorded decision gets "nobody found". The developer who did the work must not appear: doing the work is not deciding it.

**Question:** "Who decided to show the fraud score in the Claims Workbench?"

Road: find an expert. Type of question: **decided**, so only a decision in meeting minutes counts. Tickets and docs count for nobody. Expected: **nobody found**.

- **The answer says** that no decision is recorded about this, and suggests asking who worked on it instead.
- **Not shown:** Olivia Tremblay has evidence, but none that counts for a "decided" question (assigned CLM-254).
- **Not shown:** Priya Patel has evidence, but none that counts for a "decided" question (wrote pg020 "Fraud Scoring Model: overview and runbook").
- **Not shown:** Rachel Goldberg has evidence, but none that counts for a "decided" question (wrote pg013 "Weekly notes").
- **`verify` must reject** pg027 "Claims Platform team meeting: minutes, 10 September 2026": It is a meeting of the team that owns the Claims Workbench. Its decision is about the Claims Intake backlog, and the fraud score is never mentioned. If it were kept, it would count for Hélène Dubois.
- **If the question were read as "help":** Olivia Tremblay.
- **If the question were read as "did":** Olivia Tremblay.

## The demo video path (case `demo`, checked at M7)

What it tests: The path of the demo video, from the vague question to the personal question.

**Question:** "Who can help me get access to the API?"

Expected: the agent asks a question, and the choices come from the data.

- The systems with "API" in their name: Claims API, Policy API.

**Question:** "The Claims API"

Expected: the same as in case `s08a`.
The cards: Sophie Martin, David Chen, Olivia Tremblay.

**Question:** "Sophie is away. Who's her manager?"

Road: about a person. The card shown: **Hélène Dubois**, Team Lead.

- In the directory, the manager of Sophie Martin is Hélène Dubois.
- Hélène Dubois has no evidence in case `s08a`, so this person is not on its cards.

**Question:** "What does she work on?"

Expected: the same as in case `s13`.
The card: Hélène Dubois.

**Question:** "What's Hélène's work phone?"

Road: about a person. The card shown: **Hélène Dubois**, Team Lead.

- The directory has a work phone for Hélène Dubois: 514-555-0142.

**Question:** "Why is Sophie away?"

Expected: the failsafe answer "I only have work information".

- Sophie Martin is out of office until 2026-11-10. The data holds no reason, so the agent has nothing to leak.
