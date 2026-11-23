---
id: pg004
title: "Policy API: developer guide"
space: policy_systems
system: policy_api
type: doc
author: p014
created: 2024-09-16
updated: 2026-07-14
language: en
---

# Policy API: developer guide

**Owner:** Amira Khalil (Policy Systems) · **Current version:** 3.6 · **Updated:** July 2026

The Policy API lets other internal systems read policies and coverages. It is read-only: only Policy Admin changes a policy.

## Who uses it

The Customer Portal, the Broker Portal, the Pricing Engine, the Claims Workbench, and the Data Warehouse.

## Base URL and versions

    https://policy-api.internal.tamberly.example/v3

We keep the previous major version alive for 12 months. Version 2 was switched off in March 2025.

## Main endpoints

| Endpoint | Returns |
|---|---|
| `GET /policies/{id}` | One policy, with its coverages and its endorsements |
| `GET /policies?customer_id=` | The policies of one customer |
| `GET /policies?broker_id=&page=` | The policies of one broker, 100 per page |
| `GET /policies/{id}/documents` | The documents of a policy (needs its own scope) |

### Example

    GET /v3/policies/QC-4471203

    {
      "id": "QC-4471203",
      "product": "home",
      "status": "active",
      "effective_date": "2026-02-01",
      "coverages": [{"code": "FIRE", "limit": 450000, "deductible": 1000}],
      "endorsements": []
    }

## Paging

Every list is paged. Read `next_page` in the response until it is empty. Do not build the page numbers yourself: a broker with 8,000 policies taught us why (POL-152).

## Endorsements

Since version 3.4, a policy comes with the changes made during its term, ordered by effective date. Cancelled endorsements are left out.

## Getting access

The Policy API still uses one key per client system. Open an "Access request" ticket in the POL project, with the system, the environment, and the scopes you need:

| Scope | What it allows |
|---|---|
| `policies.read` | Read policies and coverages |
| `policies.documents.read` | Download the documents of a policy |

Production access is approved by the Security Manager. The move to Single Sign-On is planned for 2027.

## Errors

| Code | Meaning |
|---|---|
| 401 | The key is missing or wrong |
| 403 | The key is valid, but the scope is missing |
| 404 | No policy with this id. Policies that ended before 2019 were never imported: they are only in the Legacy Policy System |
| 429 | Too many calls: the limit is 120 a minute per client |

## Changes

- 3.6 (July 2026): the `documents` endpoint returns the language of each document.
- 3.5.2 (December 2025): the broker search is paged by the database.
- 3.4 (July 2025): endorsements in the policy details.
