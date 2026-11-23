---
id: pg027
title: "Claims Platform team meeting: minutes, 10 September 2026"
space: claims_platform
system: claims_intake
type: minutes
author: p024
created: 2026-09-10
updated: 2026-09-11
language: en
meeting_date: 2026-09-10
organizer: p007
attendees: [p007, p012, p018, p024]
decision_owner: p007
---

# Claims Platform team meeting: minutes, 10 September 2026

**Date:** Thursday 10 September 2026, 09:30 to 10:15
**Organizer:** Hélène Dubois
**Notes:** Olivia Tremblay (my first time taking the notes, so tell me if something is missing)
**Present:** Hélène Dubois, Sophie Martin, Nadia Benali, Olivia Tremblay

## 1. Claims Intake backlog

- Hélène: 198 intake items are waiting for a manual check. Normal is under 20. Two people in the claims centre do nothing else.
- Nadia: almost all of them are claims from the phone line that arrived without a policy number (CLM-290). The fix went to production yesterday, so new claims are fine. The claims created between 24 August and 9 September still have to be repaired.
- Sophie asked whether the other systems are affected. Nadia: no, they only read a claim after intake has created it.
- I asked whether the claims centre could fill in the policy number themselves, once they have found the policy. Hélène: no, the Workbench doesn't let anyone change that field after the claim file is created.

**Decision (Hélène):** we start a weekly triage rota. One developer, one hour a day, checks the intake backlog with the claims centre, until the backlog is back under 20. The rota starts on 21 September, and we review it at the end of October.

## 2. Workbench release of 15 September

- Hélène: the release checklist has a new line: two adjusters test before the release.
- Olivia (me): the fix for the document freeze (CLM-262) is in this release. I tested it with a claim of 450 documents.

## 3. Round table

- Sophie: away from 26 October to 10 November.
- Nadia: nothing to add.

## Action items

| Action | Owner | Due |
|---|---|---|
| Create the ticket for the triage rota | Hélène | 14 September |
| First week of the rota | Olivia | 21 September |
| Script to repair the phone claims without a policy number | Nadia | End of October |
