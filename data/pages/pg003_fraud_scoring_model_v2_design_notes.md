---
id: pg003
title: "Fraud Scoring Model v2 - design notes"
space: data_analytics
system: fraud_scoring_model
type: doc
author: p011
created: 2024-05-06
updated: 2025-02-18
language: en
---

# fraud scoring model v2 - design notes

status: live since 2024-06. these are working notes, not a spec.

## tl;dr

gbm on ~60 features, binary target = "investigation confirmed fraud". retrained once a year, by hand. cutoff 0.62.

## data

- claims 2019-2023 minus 2021 (the 2021 labels are garbage, the investigation team changed its codes mid-year. don't use it, don't ask)
- ~1.2M claims, 2.5% positive
- labels only exist for claims that got investigated => selection bias. known, not fixed

## features that matter (top 8 by gain)

1. claim_cluster_7d: nb of claims within 2 km in the last 7 days
2. days_since_policy_start
3. claim_amount / insured_value
4. nb_prior_claims_36m
5. late_report_days
6. loss_type (theft, fire, water, collision, glass, other)
7. broker_fraud_rate_24m
8. third_party_repeat: same body shop or contractor seen in confirmed fraud before

claim_cluster_7d is by far the strongest. it is also the one i trust least: it can't tell a fraud ring from a hailstorm. TODO add an event flag.

## training

scripts live in fraud-model/train. you need to run make_labels first, then build_features, then train. order matters, nothing checks it.

two paths are hardcoded in build_features (the claims extract and the body shop list). TODO make them config.

the cat event list is pasted by hand from the claims centre's spreadsheet once a year. TODO automate, or at least write down where the spreadsheet is.

## scoring

nightly, 01:30, reads the claims export file. if the file is late the job dies quietly. TODO alert.

## eval (2023 hold-out)

    cutoff  flag_rate  precision  recall
    0.50    7.9%       0.25       0.80
    0.62    4.3%       0.41       0.71
    0.70    2.6%       0.56       0.58

went with 0.62: investigators can handle ~4-5% of claims.

## open questions

- do we score at first notice of loss or after the first adjuster note? (now: first notice)
- fairness review: never done. TODO before v3
