---
id: pg029
title: "Policy Database migration: steering committee minutes, 23 September 2026"
space: technology_office
system: policy_database
type: minutes
author: p017
created: 2026-09-24
updated: 2026-09-24
language: en
meeting_date: 2026-09-23
organizer: p017
attendees: [p004, p002, p003, p013, p022, p017]
decision_owner: p004
---

# Policy Database migration: steering committee minutes, 23 September 2026

**Date:** Wednesday 23 September 2026, 14:00 to 15:10
**Organizer and minutes:** Julie Bernard
**Present:** Isabelle Roy (chair), Robert Lefebvre, Daniel Morin, Wei Zhang, Fatima Rahimi, Julie Bernard

## Topic

The date of the cutover, after dry run 2 was stopped.

## Discussion

1. **Dry run 2.** Wei Zhang explained why he stopped it: at 22:00 the copy in the cloud was 41 minutes behind, and the runbook allows 5 minutes.
2. **Cause.** Fatima Rahimi showed that the network link is not the cause. The cloud side applies the changes too slowly when the renewal batch runs. A fix exists, but it needs at least three nights of testing.
3. **Dates.** Julie Bernard presented three possible dates. Daniel Morin ruled out 24 October: the renewal volume is at its highest, and month-end closing starts two days later.
4. **Risk.** Robert Lefebvre asked what happens if the delay comes back in November. Wei Zhang answered that the cutover is then stopped at step 2, with no effect on users, as on 15 September.

## Decisions

**The cutover moves from 26 September to the weekend of 21 November 2026.**

- Decision owner: Isabelle Roy
- Condition: three nights in a row with a delay under 5 minutes while the renewal batch runs, before 16 October

## Action items

| Action | Owner | Due |
|---|---|---|
| Fix the delay and test it for three nights (INF-231) | Fatima Rahimi | 16 October 2026 |
| Update the runbook with the new timings | Wei Zhang | 16 October 2026 |
| Tell the business teams about the new date | Daniel Morin | 30 September 2026 |
| Book the weekend of 21 November, with every team on call | Julie Bernard | 9 October 2026 |
| Repeat the dry run with the fix, before the go or no-go | Wei Zhang | 3 November 2026 |

## Next meeting

Wednesday 4 November 2026: go or no-go. Julie Bernard will send the invitation.
