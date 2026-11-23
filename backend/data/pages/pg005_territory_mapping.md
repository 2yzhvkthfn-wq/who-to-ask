---
id: pg005
title: "Territory mapping: from postal code to rating territory"
space: pricing_underwriting
system: pricing_engine
type: doc
author: p010
created: 2025-03-10
updated: 2026-10-21
language: en
---

# Territory mapping: from postal code to rating territory

**Owner:** Karim Haddad (Pricing & Underwriting) · **System:** Pricing Engine

The Pricing Engine does not price a postal code directly. It first turns the postal code into a **rating territory**, and the territory gives the base rate. This page explains the lookup, and how to change it.

## How the lookup works

1. Take the first three characters of the postal code. This is the forward sortation area (FSA): `H2X 1Y4` gives `H2X`.
2. Look the FSA up in the table `territory_map`, which has one row per FSA.
3. The row gives the territory, for example `QC-03`.

Extract of the table:

    fsa   province  territory  valid_from
    H2X   QC        QC-03      2019-01-01
    J7N   QC        QC-14      2021-07-01
    K1A   ON        ON-07      2019-01-01

The table is part of the rating tables, so it is versioned with them: `2026.3` is the third release of 2026.

## What happens when the FSA is not in the table

The engine answers `422 TERRITORY_NOT_FOUND`, and the quote is rejected. The portals then show "We could not price this risk".

This happens in two cases:

- **The postal code is wrong** (a typo). Nothing to do on our side.
- **The FSA is new.** The postal service adds FSAs a few times a year, mostly in new suburbs. Until we add a row, every quote in that area fails. This is what happened in September and October 2026 (PRC-88).

## How to add an FSA

1. Check that the FSA really exists in the latest postal update.
2. Choose the territory. With no claims history, use the territory of the areas around it, and write down why.
3. Add the row in staging. `valid_from` is the release date, never a date in the past.
4. Run 20 test quotes for the area, and compare them by hand with a neighbouring FSA.
5. Get the approval of the team lead in the ticket. Every change to a rating table needs it, even one row.
6. Release as a new version of the rating tables, and add a line to the table log for the auditors.

## Things that look like this problem, but are not

- **A postal code declined for flood risk.** That is an underwriting rule, not pricing: the quote is priced, then declined. See the Underwriting Rules pages.
- **A postal code refused by a form in a portal.** That is the address check of the portal. The Pricing Engine never sees the request.

## Planned

PRC-95: use a fallback territory for an unknown FSA, instead of rejecting the quote.
