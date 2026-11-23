# Tamberly Insurance: the story behind the data

**Tamberly Insurance is a fictional company.** Nobody on this page exists.

This page is for people who read the project. It was written first, and every person, ticket, and page in the data comes from it. The agent never reads this file: it only sees the directory, the HR records, the tickets, and the pages.

The data stops on a fixed fake "today": **1 November 2026**. The story covers the 18 months before it.

## The company

Tamberly Insurance sells home and car insurance in Quebec and Ontario, from its head office in Montreal. About half of its policies are sold by brokers and the rest directly to customers. Adjusters work in a claims centre in Laval. The company works in French and English: most technical pages are in English, the Digital Channels team writes mostly in French, and some older pages exist only in French.

The data holds 26 people from the technology department, in 7 teams. Three of them have left the company.

## Who owns which system

| System | Main person today | Also, or before |
|---|---|---|
| Claims API | Sophie Martin | Étienne Lavoie until June 2025. Nadia Benali and Olivia Tremblay also handle access requests |
| Claims Workbench | Hélène Dubois (team lead) | Olivia Tremblay does most of the bug fixing |
| Claims Intake | Nadia Benali | Hélène Dubois runs the backlog. Étienne Lavoie fixed one bug in 2025 |
| Policy API | Amira Khalil | Yuki Tanaka until January 2026, Lucas Pelletier since |
| Policy Database | Wei Zhang | |
| Policy Admin | Daniel Morin (team lead) | Lucas Pelletier |
| Legacy Policy System | Nobody since December 2025 | Gérald Fontaine, for 27 years |
| Pricing Engine | Karim Haddad | Nathalie Côté approves every change to a rating table |
| Underwriting Rules | Samuel Okafor | |
| Customer Portal | Marc-André Gagnon | Sophie Nguyen designs the screens |
| Broker Portal | Catherine Leblanc (team lead) | |
| Fraud Scoring Model | Priya Patel | Tom Walsh until March 2026 |
| Data Warehouse | Yuki Tanaka | |
| Cloud Platform | Fatima Rahimi | |
| Deployment Pipeline | Alexandre Bergeron | |
| Single Sign-On | Alexandre Bergeron | David Chen approves access to production systems |

Robert Lefebvre (Vice President, Technology) leads the department. Isabelle Roy (Chief Architect) chairs the Architecture Review Board. Julie Bernard (Project Coordinator) organizes the cross-team meetings and writes their agendas and minutes. Rachel Goldberg leads Data & Analytics.

## Who joined, moved, or left

| Date | What happened |
|---|---|
| 27 June 2025 | Étienne Lavoie leaves. Sophie Martin takes over the Claims API |
| 8 September 2025 | Olivia Tremblay joins Claims Platform as a developer |
| 19 December 2025 | Gérald Fontaine retires. He is not replaced, and nobody else knows the Legacy Policy System well |
| 5 January 2026 | Yuki Tanaka moves from Policy Systems (developer on the Policy API) to Data & Analytics (data engineer) |
| 12 January 2026 | Lucas Pelletier joins Policy Systems as a developer, on the Policy API and Policy Admin |
| 27 March 2026 | Tom Walsh leaves. Priya Patel takes over the Fraud Scoring Model |
| 7 April 2026 | Sophie Nguyen joins Digital Channels as a UX designer |

Person ids follow the hiring order: `p001` joined first, `p026` last.

## Four projects

### 1. Claims API version 2 and the new way to get access (May 2025 to January 2026)

Version 1 of the Claims API used shared keys. Étienne Lavoie handed them out by email, and his 2023 page explains that old process. Version 2 gives each client system its own credentials through Single Sign-On.

- July to October 2025: Sophie Martin builds the new credentials.
- 20 October 2025: she publishes "Claims API: Access Guide". Access is now requested with an "Access request" ticket. David Chen approves it for security, then a Claims Platform developer creates the credentials.
- 30 January 2026: the old keys are switched off. Étienne's old page is still there, and nobody marked it as outdated.
- Since February 2026: seven access requests. Sophie handled three, Nadia two, and Olivia one. David approved all six. The seventh, from late October 2026, is still waiting for approval and has no assignee.

### 2. Moving the Policy Database to the cloud (October 2025, still running)

The servers under the Policy Database reach the end of their support in March 2027.

- October 2025: Isabelle Roy writes an options paper.
- 13 November 2025: at the Architecture Review Board, **Isabelle Roy decides to move the Policy Database to a managed database service in the cloud**.
- 2026: Wei Zhang prepares the data and writes the migration runbook. Fatima Rahimi builds the network link. Dry run 1 (June) works. Dry run 2 (September) fails because the copy to the cloud falls 40 minutes behind.
- 23 September 2026: Isabelle moves the cutover from 26 September to the weekend of 21 November 2026. A third dry run is planned for 3 November.

Julie Bernard organized every meeting of this project and wrote every agenda and every set of minutes. She appears on more of its pages than anyone, and she decided nothing. That is on purpose.

### 3. The Customer Portal in French and English, "Portail 2026" (December 2025 to June 2026)

The portal was relaunched on 15 June 2026 with every page in both languages.

- Marc-André Gagnon wrote the translation guide and fixed the translation tickets, all in French.
- Sophie Nguyen reviewed the French wording of the new claim form, once.
- 4 June 2026: Catherine Leblanc decides that no page ships in one language only.

### 4. Version 3 of the Fraud Scoring Model, and a handover (September 2025 to April 2026)

- Tom Walsh built versions 1 and 2. In autumn 2025, version 2 flags too many honest claims, and he recalibrates it.
- February and March 2026: Tom hands the model over to Priya Patel before he leaves.
- 20 April 2026: Priya's version 3, retrained on the claims of 2022 to 2025, goes live. She writes the new overview and runbook. Tom's design notes for version 2 are still there, and they are out of date.
- June 2026: Olivia Tremblay adds the fraud score to the Claims Workbench.

## Smaller events

- **New postal codes (September and October 2026).** The postal service adds new postal code areas in Quebec. The Pricing Engine doesn't know them and rejects the quotes. Karim Haddad fixes it on 11 September. The bug is reopened on 19 October when two more areas appear.
- **The Legacy Policy System (February 2026).** Daniel Morin decides to retire it by June 2027. A request to extract old policies has had no assignee since May 2026.
- **Spring floods (May 2026).** Samuel Okafor updates the rule that declines new home policies in flood zones. It also works with postal codes, which makes it easy to confuse with the pricing bug.
- **Claims Intake backlog (September 2026).** Claims from the phone line arrive without a policy number. Hélène Dubois decides on a weekly triage rota.

## The mess, on purpose

Real company data is never clean, so this data isn't either.

- **Outdated pages:** Étienne's page on API keys (last updated in 2024), Tom's design notes for version 2 (last updated in 2025), and Gérald's notes on the legacy system (last updated in 2022).
- **Vague titles:** "Notes", "Login problems", and "Weekly notes".
- **Unassigned tickets:** the legacy extraction, and the newest access request.
- **Reopened tickets:** the postal code bug (still open) and a Claims Workbench freeze (fixed the second time).
- **People who touch a system once:** Sophie Nguyen on a translation ticket, Fatima on the Deployment Pipeline, Yuki on the fraud model's nightly job, and Étienne on Claims Intake. Olivia handled a single Claims API access request.
- **Stale directory data:** one out-of-office date is in the past, and the newest employee has no work phone yet.
- **Names inside texts:** some tickets and pages mention colleagues by name, including the colleague who opted out of being found and two who left.

## How people write

| Person | Style |
|---|---|
| Sophie Martin | Clear steps, numbered lists, friendly |
| Étienne Lavoie | Short, lower-case, few explanations |
| Karim Haddad | Technical and exact, with error messages and table extracts |
| Marc-André Gagnon | French, relaxed, technical words in English |
| Olivia Tremblay | Careful and complete, says what she tried |
| Hélène Dubois | Short bullets, owners, and dates |
| Julie Bernard | The same formal template every time |
| Isabelle Roy | Options, trade-offs, and a clear recommendation |
| Wei Zhang | Checklists and exact numbers |
| Alexandre Bergeron | Casual, with a short summary at the top |
| Tom Walsh | Dense, with jargon and unfinished "TODO" lines |
| Priya Patel | Tidy, with tables and careful limits |
| Gérald Fontaine | French, long sentences, old vocabulary |
| Lucas Pelletier | A new employee's rough notes |
