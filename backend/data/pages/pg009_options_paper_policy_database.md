---
id: pg009
title: "Options paper: where should the Policy Database run after 2027?"
space: technology_office
system: policy_database
type: doc
author: p004
created: 2025-10-27
updated: 2025-11-10
language: en
---

# Options paper: where should the Policy Database run after 2027?

**Author:** Isabelle Roy, Chief Architect · **For:** Architecture Review Board, 13 November 2025 · **Status:** final

## Why now

The Policy Database runs on two servers in our Montreal data centre. Their support ends on 31 March 2027. After that date, we get no security fixes. Doing nothing is not an option.

The database holds 2.3 million policies and about 1.4 TB of data. Policy Admin, the Policy API, both portals, and the nightly renewal batch depend on it.

## Options

### A. Buy new servers and stay in the data centre

- Cost: about $1.9 M over five years, most of it in the first year.
- Risk: low. We know how to do it, and we did it in 2019.
- Limits: we keep running the hardware, the backups, and the failover ourselves, with one database administrator.

### B. Move to a managed database service in the cloud

- Cost: about $1.5 M over five years, spread evenly.
- Risk: medium. It is the first large database we move. The cutover needs a weekend, and a way back.
- Gains: backups, patching, and failover become the provider's job. We also get a copy in a second region for disaster recovery, which we do not have today.

### C. Move to the cloud and change the database engine at the same time

- Cost: unknown. Every query in Policy Admin would need a review.
- Risk: high. Two big changes at once.

## Comparison

| | A. New servers | B. Managed service | C. New engine |
|---|---|---|---|
| Five-year cost | $1.9 M | $1.5 M | Unknown |
| Risk of the move | Low | Medium | High |
| Disaster recovery | No change | Second region | Second region |
| Work for our team afterwards | Same as today | Less | Less, later |
| Ready before March 2027 | Yes | Yes, if we start in January | Not sure |

## Recommendation

**Option B.** It costs less, it gives us the disaster recovery we lack, and the risk can be managed with two dry runs and a 30-day way back to the old servers.

I do not recommend option C. Changing the engine can be a separate project later, when the database is already in the cloud.

## What I need from the board

A decision on 13 November, so that the network link can be ordered in January.
