---
id: pg021
title: "Underwriting Rules: flood-zone postal codes"
space: pricing_underwriting
system: underwriting_rules
type: doc
author: p021
created: 2026-05-22
updated: 2026-05-22
language: en
---

# Underwriting Rules: flood-zone postal codes

**Owner:** Samuel Okafor (Pricing & Underwriting) · **Rule:** HOME-FLOOD-01 · **In force since:** 21 May 2026

## What the rule does

When someone asks for a **new home policy**, the rule looks at the postal code of the home:

| The postal code is... | Result |
|---|---|
| On the high-risk list | The request is declined, with the message "We cannot offer this coverage at this address" |
| On the rural review list | The request goes to an underwriter, who decides within two working days |
| On neither list | The request continues to pricing |

The rule never touches an existing policy or a renewal.

## Where the lists come from

- The high-risk list has 1,904 postal codes. It comes from the province's 2026 flood map: every postal code where more than half of the homes are in a zone that was flooded at least once in 20 years.
- The rural review list has 18 postal codes. In the country, one postal code can cover both a riverbank and a hill, so a person looks at the address.

## Numbers

Tested on the 140 homes that we insured in 2025 and that were flooded in April 2026:

| Outcome with the new rule | Homes |
|---|---|
| Declined | 118 |
| Sent to an underwriter | 13 |
| Accepted | 9 |

Expected effect on new business: about 0.6% of home requests declined, against 0.4% with the old map.

## This rule is not the territory lookup of the Pricing Engine

A decline from this rule is a decision: the postal code is known, and we choose not to insure. If a quote fails because the postal code is **unknown**, that is the territory table of the Pricing Engine, not this rule.

## Changing the lists

Any change needs the approval of the team lead in the ticket (see PRC-74). The lists are reviewed each year in May, after the spring thaw.
