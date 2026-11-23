---
id: pg007
title: "Cloud Platform: landing zone and naming rules"
space: infrastructure_security
system: cloud_platform
type: doc
author: p022
created: 2025-09-15
updated: 2026-04-21
language: en
---

# Cloud Platform: landing zone and naming rules

Owner: Fatima Rahimi. Short on purpose.

## Accounts

One account per environment, per team. Nothing is created by hand in production.

| Environment | Who can create resources | How |
|---|---|---|
| sandbox | Any developer | By hand. Deleted every Sunday night |
| staging | The pipeline | Infrastructure code only |
| production | The pipeline | Infrastructure code only, after review |

## Regions

Canada only. Primary region: Montreal. Second region: Toronto, for backups and disaster recovery. A resource outside Canada is deleted without warning.

## Names

    <team>-<system>-<environment>-<what>

Examples:

    pol-policydb-prod-db
    clm-workbench-stg-app
    dat-warehouse-prod-storage

Team codes are the Jira keys in lower case: clm, pol, prc, dig, dat, inf.

## Tags (required)

| Tag | Example |
|---|---|
| owner | policy_systems |
| system | policy_database |
| cost-centre | 4410 |
| data-class | customer, internal, or public |

A resource without the four tags shows up in the monthly cost report under "unknown". I will come and ask.

## Network

- No public address on a database, ever.
- Systems talk to each other through private addresses.
- The link to the data centre is private and encrypted (1 Gbps since March 2026).

## Asking for something

Open a ticket in the INF project, with the component "Cloud Platform". Say what you need, for which system, and until when.
