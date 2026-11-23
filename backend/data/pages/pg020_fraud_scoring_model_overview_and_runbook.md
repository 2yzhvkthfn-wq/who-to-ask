---
id: pg020
title: "Fraud Scoring Model: overview and runbook"
space: data_analytics
system: fraud_scoring_model
type: doc
author: p023
created: 2026-04-17
updated: 2026-10-06
language: en
---

# Fraud Scoring Model: overview and runbook

**Owner:** Priya Patel (Data & Analytics), since March 2026. I took the model over from Tom Walsh. · **Version in production:** 3.0, since 20 April 2026

## What the model does

Every night, the model gives each new claim a score between 0 and 1. A claim with a score of 0.65 or more is flagged, and an investigator looks at it before any payment. The score is a hint for a person. It never refuses a claim by itself.

Adjusters see the score on the claim summary screen of the Claims Workbench.

## Numbers to know

| Measure | Version 2 | Version 3 |
|---|---|---|
| Flag rate in a normal month | 4.3% | 4.1% |
| Flag rate during the August 2025 storm | 11% | 4.6% |
| Recall on confirmed fraud | 0.71 | 0.74 |
| Precision | 0.41 | 0.44 |

Read these with care: "confirmed fraud" only counts the claims that someone investigated. Fraud that nobody looked at is invisible in these numbers.

## What changed in version 3

- Trained on the claims opened from 2022 to 2025.
- New: the event code of the claim, and the number of claims in the same area during the same event.
- Removed: `claim_cluster_7d`. It flagged every claim after a storm (see DAT-52).

## Every night

| Time | Step |
|---|---|
| 01:30 | The job reads the new claims of the day from the Claims API |
| 01:40 | It computes the features and the scores |
| 02:00 | It writes the scores back, and the Workbench shows them from the morning |

If the job fails, the data team channel gets an alert, and the next run scores the claims that were missed.

## Every week

A drift report runs each Monday (DAT-73). Look at it. If the flag rate is outside 3% to 5% two weeks in a row, find out why before you change anything.

## When something goes wrong

- **Too many flags after a storm:** check that the claims centre set the event code. Without it, version 3 behaves like version 2.
- **No scores in the morning:** look at the alert in the data team channel first. Nine times out of ten, the job's credentials have expired, or it started late.
- **An investigator disagrees with a score:** that is normal, and useful. Ask them to record the result of the investigation. It is the training data of the next version.

## What this model must not be used for

- Refusing or delaying a payment without a person looking at the claim.
- Pricing or underwriting. It was trained on claims, not on customers.

## Older documents

The design notes of version 2 are still in this space. They describe features that no longer exist. Use them for history only.
