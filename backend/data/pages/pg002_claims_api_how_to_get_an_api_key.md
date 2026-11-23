---
id: pg002
title: "Claims API - how to get an API key"
space: claims_platform
system: claims_api
type: doc
author: p009
created: 2023-04-11
updated: 2024-02-06
language: en
---

# claims api - how to get an api key

quick notes, since people keep asking.

## steps

1. send me an email with the name of your system and what you need it for
2. i send you the key. same key for staging and prod for now
3. put it in the header:

       X-API-Key: <your key>

4. that's it

## good to know

- one key per team, not per system. share it inside your team if needed
- keys don't expire. if you think yours leaked, tell me and i'll make a new one
- no rate limit yet. please don't hammer prod during the day, the nightly batch already hurts
- base url is /v1/claims

## who has a key (feb 2024)

- portal team
- pricing
- data / reporting
- the broker portal guys asked, not done yet

## todo

- rotate the keys at some point
- move this to something better than email
