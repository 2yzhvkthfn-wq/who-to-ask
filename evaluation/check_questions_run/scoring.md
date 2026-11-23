# My check questions for the second level

Run on 2026-11-22, from 19:57:56 to 20:06:26. I wrote these 11 questions after the second level was built, so it could not be tuned to them. Scored by Claude with my rules, from the data (`scoring.json` has one line per answer). **I checked the scoring the same day, and I agree with it.**

**45 of 55 answers pass. 9 of the 11 questions pass in all five tries, and 2 fail in all five.**

## How this run was made

- Each question was asked five times through the real agent (`full_pipeline`), each time in a new conversation, with my real setup: 55 runs.
- The questions were asked in five rounds (every question once, then every question again), so the five tries of one question are spread over the eight and a half minutes of the run.
- Nothing changed before or during the run: commit `1ef4f4c`, and the same `git status` at the start and at the end (`run_info.json`).
- The runner is `runner.py.txt`. It uses the runner of the honest test (`evaluation/honest_run/runner.py.txt`) to ask a question and to save its answer.

## My rules

- **Questions 1 to 8** pass when the answer shows people with real evidence on the system I mean, with or without the label, in the language of the question, and nobody who left or opted out. "Nobody found" only passes if the data has no ticket or page on that system. (Each of the eight systems has some.)
- **Questions 9 to 11 are traps:** they only pass with "nobody found". Any person shown is a fail.

## The results

| # | The system I mean | What came out, in the five tries | Pass |
|---|---|---|---|
| 1 | Policy Database | The second level, with the label: Isabelle Roy, Wei Zhang, Fatima Rahimi | 5 of 5 |
| 2 | Fraud Scoring Model | An exact answer: Priya Patel | 5 of 5 |
| 3 | Pricing Engine, in French | An exact answer, in French: Karim Haddad | 5 of 5 |
| 4 | Policy Admin, written "Policy Admn" | Nobody found | **0 of 5** |
| 5 | Legacy Policy System | The second level, with the label: Daniel Morin | 5 of 5 |
| 6 | Policy API | An exact answer: Amira Khalil | 5 of 5 |
| 7 | Cloud Platform | The second level, with the label: Fatima Rahimi | 5 of 5 |
| 8 | Underwriting Rules, described and not named | Nobody found | **0 of 5** |
| 9 | A trap: a time-off request tool | Nobody found | 5 of 5 |
| 10 | A trap: a CRM | Nobody found | 5 of 5 |
| 11 | A trap, in French: a room booking system | Nobody found, in French | 5 of 5 |

## What Claude checked in the data for each pass

- **1:** the nine tickets and pages of the Policy Database lead to three people, and the answer shows these three, each with their own: Isabelle Roy (`pg009`, and the decisions of `pg011`, `pg019`, and `pg029`), Wei Zhang (`pg023`, `INF-219`, `POL-164`), and Fatima Rahimi (`INF-204`, `INF-231`).
- **2:** Priya Patel wrote `pg020`, the runbook of the model (one try also shows `DAT-67`). `verify` judged that it is about my exact problem. Tom Walsh, who left, is not recommended: the note names him. In one try of five, `understand` named no system, and the answer was the same.
- **3:** Karim Haddad handled `PRC-88`, a Pricing Engine ticket about quotes that fail (some tries add `pg005` and `PRC-95`). The cards and the messages are in French.
- **5:** the three items of the Legacy Policy System lead to two people. Daniel Morin owns the decision of `pg016`. Gérald Fontaine left: he is not recommended, and the note names him, with no date and no reason.
- **6:** Amira Khalil handled `POL-152`, a Policy API ticket about a search that times out.
- **7:** Fatima Rahimi wrote `pg007`, the one page of the Cloud Platform.
- **9, 10, and 11:** `understand` named no system in any of the 15 tries, and nobody was shown.
- **In all 55 answers:** no card shows a ticket or a page of another system than the one I mean, nobody who left or opted out is recommended, and the name of the colleague who opted out is nowhere.

## The two misses

- **4, "Policy Admn":** `understand` said each time that "Policy Admn" names no system of its list. So no system was named. The search did find the three tickets and pages of Policy Admin, and `verify` rejected them: none is about being logged out while cancelling a policy. With no named system, there is no second level.
- **8, "The automatic underwriting ... Who can check the rules?":** the question describes the Underwriting Rules without their name. `understand` said each time that "no system is named". It only gets the names of the systems, not what each one does. `verify` rejected the two items of the Underwriting Rules (a flood-zone rule), so the answer was "nobody found".

Both are the same limit: **the second level only starts when the question writes the name of the system.** A spelling mistake in the name can be enough to lose it (question 4), and so can a description in place of the name (question 8). In the same run, a name in lower case ("legacy policy system", "the cloud platform"), a French name ("le moteur de tarification"), and "the fraud model" were all understood.

**My decision about these two misses: they stay as a limit.** I prefer "nobody found" to a wrong name.

## What is saved

`answers/` has three files per try (`c04_r2.txt` is the second try of question 4, as the terminal shows it, `c04_r2.json` is the raw answer, and `c04_r2_log.txt` has the log lines). `questions.json` holds the questions as they were sent, with the system I mean for each. `summary.txt` has one line per try, in the order they were asked.
