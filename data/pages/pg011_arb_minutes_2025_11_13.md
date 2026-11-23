---
id: pg011
title: "Architecture Review Board: minutes, 13 November 2025"
space: technology_office
system: policy_database
type: minutes
author: p017
created: 2025-11-14
updated: 2025-11-14
language: en
meeting_date: 2025-11-13
organizer: p017
attendees: [p004, p002, p003, p013, p006, p022, p017]
decision_owner: p004
---

# Architecture Review Board: minutes, 13 November 2025

**Date:** Thursday 13 November 2025, 10:00 to 11:40
**Organizer and minutes:** Julie Bernard
**Present:** Isabelle Roy (chair), Robert Lefebvre, Daniel Morin, Wei Zhang, David Chen, Fatima Rahimi, Julie Bernard

## Topic

Hosting of the Policy Database after March 2027.

## Discussion

1. **Options paper.** Isabelle Roy presented the three options: new servers in the data centre (A), a managed database service in the cloud (B), and a move to the cloud with a new database engine (C).
2. **Database.** Wei Zhang confirmed that option B needs no change to the queries of Policy Admin. He asked for two dry runs before the real cutover, and for a way back to the old servers.
3. **Policy Admin.** Daniel Morin asked that the nightly renewal batch be part of every dry run, because it is the heaviest load of the day.
4. **Security.** David Chen had no objection to option B, on two conditions: a private network link, and customer data stored in Canada only.
5. **Network.** Fatima Rahimi estimated eight weeks to order and install a private link.
6. **Budget.** Robert Lefebvre confirmed that the budget for option B is available in 2026.

## Decisions

**The Policy Database moves to a managed database service in the cloud (option B).**

- Decision owner: Isabelle Roy
- Conditions: a private network link, data stored in Canada only, two dry runs, and the old servers kept as a way back for 30 days after the cutover
- Target: cutover in the third quarter of 2026

Option C (a new database engine) is not pursued.

## Action items

| Action | Owner | Due |
|---|---|---|
| Order the private network link | Fatima Rahimi | 31 January 2026 |
| Clean the data that blocks the migration tool | Wei Zhang | 28 February 2026 |
| Write the migration runbook | Wei Zhang | 30 June 2026 |
| Set up a steering committee, every two to three months | Julie Bernard | 15 December 2025 |

## Next meeting

Steering committee, date to be confirmed by Julie Bernard.
