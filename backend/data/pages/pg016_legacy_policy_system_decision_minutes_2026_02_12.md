---
id: pg016
title: "Legacy Policy System: minutes of the decision meeting, 12 February 2026"
space: technology_office
system: legacy_policy_system
type: minutes
author: p017
created: 2026-02-13
updated: 2026-02-13
language: en
meeting_date: 2026-02-12
organizer: p017
attendees: [p003, p004, p013, p014, p017]
decision_owner: p003
---

# Legacy Policy System: minutes of the decision meeting, 12 February 2026

**Date:** Thursday 12 February 2026, 13:30 to 14:30
**Organizer and minutes:** Julie Bernard
**Present:** Daniel Morin (chair), Isabelle Roy, Wei Zhang, Amira Khalil, Julie Bernard

## Topic

The future of the Legacy Policy System, now that nobody on the team knows it well.

## Discussion

1. **Situation.** Daniel Morin recalled that the system has been read-only since 2019. It still holds the policies issued before 2019, and the only copy of the history before 2015. Since December 2025, nobody in Policy Systems has run it day to day.
2. **Cost.** The mainframe contract costs $310,000 a year, and it renews on 1 July 2027.
3. **Data.** Wei Zhang estimated 9 million rows of history that were never copied. Copying them needs someone who can read the old formats.
4. **Architecture.** Isabelle Roy asked that the old history go into an archive area of the Policy Database, and only after the database has moved to the cloud, to avoid moving the data twice.
5. **Policy API.** Amira Khalil confirmed that the API can read an archive area with little work.

## Decisions

**The Legacy Policy System is retired by 30 June 2027.**

- Decision owner: Daniel Morin
- The history before 2019 moves to an archive area of the Policy Database, after the cloud cutover
- No new position is opened to replace the legacy analyst. A contractor who knows the old formats is hired for the copy, from January 2027

## Action items

| Action | Owner | Due |
|---|---|---|
| Find a contractor who knows the old formats | Daniel Morin | 30 September 2026 |
| Design the archive area | Wei Zhang | 31 December 2026 |
| Add the retirement to the follow-up of the technology roadmap | Julie Bernard | 27 February 2026 |
| Tell compliance that extractions will be slow until 2027 | Daniel Morin | 27 February 2026 |

## Next meeting

No regular meeting. Julie Bernard will call one when the contractor is found.
