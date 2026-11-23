---
id: pg018
title: "Data Warehouse: table catalogue"
space: data_analytics
system: data_warehouse
type: doc
author: p020
created: 2026-03-09
updated: 2026-08-27
language: en
---

# Data Warehouse: table catalogue

**Owner:** Yuki Tanaka (Data & Analytics) · **Updated:** 27 August 2026

The tables that people ask about most. If a table is not here, it is probably a temporary one: don't build a report on it.

## How fresh is the data

Everything is loaded once a night. A report shows yesterday at best. The load ends around 03:00, so don't refresh a dashboard before then.

## Main tables

| Table | One row is | Loaded from | Rows |
|---|---|---|---|
| `policy_snapshot` | One policy on one day | Policy Systems | 2.3 million a day |
| `policy_endorsement` | One change to a policy | Policy Systems | About 900 a day |
| `claim` | One claim, in its latest state | Claims Platform | 310,000 a year |
| `claim_payment` | One payment on a claim | Claims Platform | 540,000 a year |
| `quote` | One quote, sold or not | Pricing Engine | 4 million a year |
| `broker` | One brokerage | Broker Portal | 1,150 |

## Known problems

| Table | Problem | Status |
|---|---|---|
| `policy_endorsement` | No rows from 15 June to 26 August 2026 | Being reloaded (DAT-81) |
| `claim` | The closed date was empty before July 2026 | Fixed. The older rows were filled in |
| `quote` | Quotes rejected by the Pricing Engine are not stored | By design. Ask Pricing if you need them |

## Rules

- Personal data (names, addresses, phone numbers) is only in the tables that start with `pii_`. You need a reason and your team lead's approval to read them.
- Postal codes are stored in full in the `pii_` tables, and cut to their first three characters everywhere else.
- Never join on a customer's name. Use `customer_id`.

## Asking for a new table or column

Open a ticket in the DAT project. Say which report needs it, and who will use it. A table without a user is deleted after 90 days.
