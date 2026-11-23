---
id: pg019
title: "Policy Database migration: steering committee minutes, 18 March 2026"
space: technology_office
system: policy_database
type: minutes
author: p017
created: 2026-03-19
updated: 2026-03-19
language: en
meeting_date: 2026-03-18
organizer: p017
attendees: [p004, p003, p013, p022, p014, p017]
decision_owner: p004
---

# Policy Database migration: steering committee minutes, 18 March 2026

**Date:** Wednesday 18 March 2026, 14:00 to 15:00
**Organizer and minutes:** Julie Bernard
**Present:** Isabelle Roy (chair), Daniel Morin, Wei Zhang, Fatima Rahimi, Amira Khalil, Julie Bernard

## Topic

Progress of the migration, and the plan for the first dry run.

## Status

| Work | Owner | Status |
|---|---|---|
| Private network link (INF-204) | Fatima Rahimi | Done on 6 March. 870 Mbps measured |
| Data cleanup (POL-164) | Wei Zhang | Done on 20 February. No orphan rows left |
| Migration runbook | Wei Zhang | Not started. Planned for May and June |
| Checks of the Policy API after the cutover | Amira Khalil | A list of 40 checks is ready |

## Discussion

1. **Size of the managed service.** Wei Zhang compared two sizes. The larger one costs 18% more, and it handles the renewal batch with a margin.
2. **Way back.** Fatima Rahimi explained that keeping the old servers in sync for 30 days after the cutover needs the network link for one more month.
3. **Dates.** A first dry run in the week of 15 June is realistic. The cutover is planned for Saturday 26 September 2026.

## Decisions

- **The larger size of the managed service is chosen.** Decision owner: Isabelle Roy.
- **The old servers stay in sync for 30 days after the cutover**, as the way back. Decision owner: Isabelle Roy.

## Action items

| Action | Owner | Due |
|---|---|---|
| Dry run 1, with the timing of each step | Wei Zhang | Week of 15 June 2026 |
| Extend the contract of the network link by one month | Fatima Rahimi | 30 April 2026 |
| Create the tracking ticket for dry run 1 | Julie Bernard | 5 June 2026 |

## Next meeting

After dry run 1. Julie Bernard will send the invitation.
