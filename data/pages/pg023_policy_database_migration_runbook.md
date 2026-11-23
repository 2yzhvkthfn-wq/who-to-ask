---
id: pg023
title: "Policy Database migration runbook (draft)"
space: policy_systems
system: policy_database
type: doc
author: p013
created: 2026-06-08
updated: 2026-10-14
language: en
---

# Policy Database migration runbook (draft)

**Owner:** Wei Zhang · **Version:** 0.7, 14 October 2026 · **Cutover:** weekend of 21 November 2026

This is the step-by-step plan for the night we move the Policy Database to the cloud. It stays a draft until the go or no-go meeting.

## Before the weekend

- [x] Copy in the cloud less than 5 minutes behind, three nights in a row (done on 6, 7, and 8 October)
- [ ] Policy Admin, Policy API, both portals: connection settings ready, not yet switched
- [ ] Renewal batch of Saturday night moved to Sunday night
- [ ] Everyone on the call list has confirmed
- [ ] Dry run 3 on 3 November: the full cutover on a copy, with the new sync

## The night: steps and timings

The timings come from dry run 1 (17 June) and from the tests of October. Dry run 3 has to confirm them.

| Step | What | Planned | Stop if |
|---|---|---|---|
| 1 | Put Policy Admin and the portals in read-only mode | 0:10 | |
| 2 | Wait until the cloud copy has caught up | 0:20 | The delay is still over 5 minutes after 30 minutes |
| 3 | Final check: row counts of the 40 biggest tables | 0:30 | Any count differs |
| 4 | Switch the connections to the cloud database | 0:25 | |
| 5 | Run the 40 Policy API checks | 0:40 | More than 2 checks fail |
| 6 | Remove the read-only mode | 0:05 | |
| | **Total** | **2:10** | |

## When to stop

Up to step 3, stopping costs nothing: remove the read-only mode, and everything runs on the old servers as before. Dry run 2 was stopped this way on 15 September.

After step 4, going back means the way-back procedure below.

## Way back (30 days)

The old servers keep receiving every change for 30 days. To go back: read-only mode, wait for the old side to catch up, switch the connections back. Tested once, in dry run 1: 55 minutes.

## What changed in this version

- 0.7 (14 October): the sync now uses 8 workers (INF-231). Step 2 is planned at 0:20 instead of 0:45.
- 0.5 (19 June): timings of dry run 1 added. The final sync took 1:32 instead of 0:45.
- 0.1 (8 June): first draft.

## Not in this runbook

Who decided what, and why: see the minutes of the Architecture Review Board (13 November 2025) and of the steering committee.
