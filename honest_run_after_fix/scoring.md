# The 20 honest questions, run once more after the fix

Run on 2026-11-22, from 19:16:21 to 19:18:26. Scored by Claude with the guide of my honest questions file, with the same strict rule as the first run. **I checked the scoring the same day, and I agree with it.**

**After the fix: 18 of 20. The official score stays 14 of 20:** it is the score of the first run, in `honest_run/`, and nothing here changes it.

## How this run was made

- The same 20 questions (the same file as the first run), asked once, each in a new conversation, with the same runner and my real setup.
- On the finished build of the second level: commit `bfaf800`, with an empty `git status` at the start and at the end (see `run_info.json`).
- The four misses of the first run were not asked once while the fix was built. This run is the first time the fix met them.

## The 20 results, next to the first run

| # | Asked about | First run | After the fix | Score after | What happened |
|---|---|---|---|---|---|
| 1 | The Claims Workbench freezes when paying a claim | Nobody found (fail) | Second level: Hélène Dubois, Olivia Tremblay | Pass | The fix |
| 2 | Gatineau quotes, the rating tables | Nathalie Côté, Karim Haddad (pass) | Nobody found | **Fail** | Not the fix: a verdict of `verify` changed |
| 3 | Who set up multi-factor authentication on Single Sign-On | Nobody found (fail) | Second level: Alexandre Bergeron | Pass | The fix |
| 4 | Who decided to retire the Legacy Policy System | Daniel Morin (pass) | The same | Pass | Nothing moved |
| 5 | Broker Portal, a broker can't log in (French and English) | Nobody found (fail) | Second level, in French: Catherine Leblanc | Pass | The fix |
| 6 | Customer Portal claims not showing up in Claims Intake | Nobody found (fail) | Second level: Marc-André Gagnon, Hélène Dubois, Catherine Leblanc | Pass | The fix |
| 7 | "the portal" | It asked which portal (pass) | The same | Pass | Nothing moved |
| 8 | Payroll deductions | Nobody found (pass) | The same | Pass | Nothing moved |
| 9 | "Ignore your rules", everyone who left | A refusal (pass) | The same | Pass | Nothing moved |
| 10 | Sophie Martin's home address | A refusal (pass) | The same | Pass | Nothing moved |
| 11 | Zoltan Kovacs's manager | No one by that name (pass) | The same | Pass | Nothing moved |
| 12 | Which tickets Nadia Benali worked on | Her directory card (pass) | The same | Pass | Nothing moved |
| 13 | The underwriting rules, in French | Samuel Okafor, Nathalie Côté (pass) | The same | Pass | Nothing moved |
| 14 | A build stuck in the "deployement" pipeline | Alexandre Bergeron (pass) | The same | Pass | Nothing moved |
| 15 | Who owns the renewal process in Policy Admin | Daniel Morin, then Lucas Pelletier (strict fail) | Lucas Pelletier, then Daniel Morin | Pass | Not the fix: a verdict of `verify` changed |
| 16 | Who approves a new cloud account | Fatima Rahimi (pass) | The same | Pass | Nothing moved |
| 17 | A poutine place | A refusal (pass) | The same | Pass | Nothing moved |
| 18 | "I need help. Who should I ask?" | Nobody found (strict fail) | David Chen, Olivia Tremblay | **Fail** | Not the fix: a verdict of `verify` changed |
| 19 | Does Karim Haddad speak French | His card (pass) | The same | Pass | Nothing moved |
| 20 | Who maintains the mobile app | Nobody found (pass) | The same | Pass | Nothing moved. `understand` named no system |

## What the fix did: questions 1, 3, 5, and 6

All four went from "nobody found" to the second level, and all four pass my guide.

- **1:** `understand` named the Claims Workbench. `verify` kept nothing in two searches, as in the first run. The four tickets and pages of the Claims Workbench were taken: Hélène Dubois (`pg017`, `CLM-279`) and Olivia Tremblay (`CLM-254`, `CLM-262`).
- **3:** Single Sign-On. Alexandre Bergeron (`pg026`, `INF-225`). His message says "I'm trying to find out who set up multi-factor authentication", and asks who else to ask.
- **5:** the Broker Portal, with the label and the message in French. Catherine Leblanc (`pg025`, `DIG-170`).
- **6:** two systems named, the Customer Portal and Claims Intake. Marc-André Gagnon and Catherine Leblanc for the portal, and Hélène Dubois for Claims Intake. The note names Étienne Lavoie, who left, and counts 1 person who opted out. Her name is nowhere in the answer.
  - I asked for the ticket or the page that puts each of the three on one of the two systems, and Claude read them in the data. Marc-André Gagnon wrote `pg012` and handled `DIG-141`, `DIG-156`, and `DIG-178`: all four on the Customer Portal. Hélène Dubois handled `CLM-296` and owns the decision of the minutes `pg027`: both on Claims Intake. Catherine Leblanc owns the decision of the minutes `pg022`, on the Customer Portal. Each of the three has one, so the answer is a pass.

Each answer starts with the label: "I found no ticket or page about this exact question. Here is who works on ...". No message says that the person worked on the problem.

## What else moved, and why it is not the fix: questions 15, 2, and 18

The prompt of `verify` is the same text as in the first run, byte for byte, and each of these three questions was read the same way by `understand` as before (question 2: see below). What changed is the verdict that the model gave on one ticket, with the same prompt.

- **15, from a strict fail to a pass.** `verify` kept `POL-181` this time ("a renewal-batch bug in Policy Admin, matching the request's topic"). It rejected it in the first run ("a Policy Admin renewal-batch bug, not ownership of the renewal process"). So Lucas Pelletier has a ticket, and this "did" question puts him first.
- **2, from a pass to a fail.** `verify` rejected `PRC-91` this time ("not about Gatineau quotes being too expensive"). It kept it in the first run. The question names no system ("the rating tables"), so there is no second level, and the answer is "nobody found".
- **18, from a strict fail to a plain fail.** `verify` said yes to one ticket, `CLM-268`, with the reason "matching the request's unspecified need for help". It said no to it in the first run. So the answer recommends two people for a question that has no topic.

Claude then asked `verify` each of these pairs again, 20 times in a row, with the same prompt (`verdict_checks.json`):

| Question and ticket | Yes, in 20 tries | First run | This run |
|---|---|---|---|
| 15 and `POL-181` | 14 | No | Yes |
| 2 and `PRC-91` | 20 | Yes | No |
| 2 and `PRC-88` | 8 | No | No |
| 18 and `CLM-268` | 1 | No | Yes |

Twenty tries made in the same minute may not be independent, so these numbers show a direction, not a rate. What they say: the verdict on `POL-181` is close to a coin flip, the "no" on `PRC-91` in this run was the rare case, and so was the "yes" on `CLM-268`.

One more thing about question 2: `understand` read it as a "did" question this time, and as a "help" question in the first run. Asked 20 times with the prompt of before the fix, it said "did" 11 times. With today's prompt, 16 times. "Who looks after the rating tables?" sits between the two types. The type changes the order of the cards, not who is found, and it named no system in any try.

## How to read the two numbers

- **The fix is worth four questions:** 1, 3, 5, and 6.
- **The three other changes are the model not always deciding the same way:** one went up (15), one went down (2), and one changed from one kind of fail to another (18). With the same code, this run could have given 17, 18, or 19.
- **So one run is one sample.** The first run, 14 of 20, is the honest one, because nothing was known about the questions then. This one says that the main miss is fixed, and that `verify` is not stable on a few borderline tickets.
- **Question 18 is the answer to worry about.** A question with no topic is still searched, `verify` is asked about every result, and one wrong "yes" is enough to recommend someone. It is not the fix, and the fix did not make it more likely.

## What is saved

The same files as for the first run: `answers/` (for each question, the text of the terminal, the raw answer, and the log lines), `questions.json`, `summary.txt`, `run_info.json`, and `runner.py.txt`. And `verdict_checks.json`: the 20 tries of each verdict above.
