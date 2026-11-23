---
id: pg008
title: "Claims API: Access Guide"
space: claims_platform
system: claims_api
type: doc
author: p012
created: 2025-10-20
updated: 2026-09-15
language: en
---

# Claims API: Access Guide

**Owner:** Claims Platform · **Applies to:** Claims API version 2 · **Questions:** ask in the Claims Platform channel

This page explains how a system gets access to the Claims API. It replaces the shared keys of version 1, which were switched off on 30 January 2026.

## Who needs this

Any internal system that reads or creates claims: the portals, pricing, the data jobs, and so on. People don't get access, only systems do. If you want to look at one claim, use the Claims Workbench.

## The four steps

1. **Check that you really need the API.** If a nightly file is enough, the Data Warehouse already has the claims.
2. **Open a ticket** in the CLM project, with the type "Access request". Give:
   - the system that will call the API
   - the environment (staging or production)
   - the scopes you need (see below)
   - why, and how many calls a day
3. **Wait for the security approval.** Every production request is approved by the Security Manager. It usually takes one or two working days. Staging needs no approval.
4. **A Claims Platform developer creates your credentials** (a client id and a secret) and puts the secret in your team's vault path. You never get a secret by email or by chat.

Plan about a week from the ticket to a working access.

## Scopes

| Scope | What it allows |
|---|---|
| `claims.read` | Read claims and their status |
| `claims.create` | Create a new claim (first notice of loss) |
| `claims.update` | Change a claim. Given only to the Claims Workbench |

Ask only for what you need. A request for "everything" is sent back.

## Rules for every client

- Credentials expire after 12 months. You get a reminder 30 days before.
- The default limit is 60 calls a minute. Say so in the ticket if you need more.
- For a nightly bulk read, use `/claims/changes?since=...` instead of paging through `/claims`.
- Payment details and adjuster notes are never included, unless the ticket says why you need them.

## Getting a token

Your system asks Single Sign-On for a token with its client id and its secret (the OAuth client credentials flow), then sends the token with each call:

    POST /oauth/token
    grant_type=client_credentials&scope=claims.read

    GET /v2/claims/{claim_id}
    Authorization: Bearer <token>

A token is valid for 30 minutes.

## Common problems

- **401 right after you got access:** you are still sending a version 1 key. Those no longer work.
- **403 on a claim you should see:** your scope is filtered. For example, a broker only sees the claims of their own clients.
- **429:** you passed the rate limit. Wait a minute, or ask for a higher limit.

## History

- October 2025: first version of this guide, for version 2.
- January 2026: version 1 keys switched off.
- September 2026: added the bulk-read rule and the common problems.
