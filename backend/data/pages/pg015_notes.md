---
id: pg015
title: "Notes"
space: policy_systems
system: policy_admin
type: doc
author: p025
created: 2026-02-04
updated: 2026-05-25
language: en
---

# Notes

my notes since i started (12 jan). mostly so i don't ask Amira the same thing twice. not official!!

## setup

- laptop: ask infra for the "dev-policy" profile, otherwise you can't reach staging
- Policy Admin runs locally with `make run-local`. the first start takes ~10 min, it loads test policies
- test login: any user from the test list, the password is in the vault under policy/dev
- the staging url is on the team page, i always forget it

## things nobody tells you

- "PAS" = Policy Admin. "the batch" = the renewal batch, runs every night at 20:00
- policies that ended before 2019 are NOT in our database. they're only in the legacy system. nobody on the team really knows it since Gérald retired. if a ticket says "legacy" -> ask Daniel first
- an "endorsement" is a change to a policy in the middle of the term (new car, new address...). took me 2 weeks to get that
- never run the batch by hand in prod. NEVER. Wei will find you

## the renewal batch (what i learned from POL-181)

- it picks policies that end in 60 days
- it skips a policy if has_pending_change is true
- that flag was stuck on for 4,112 policies because broker changes never cleared it. fixed now
- the log is in /var/log/pas/renewal, one file per night. search for "skipped"

## policy api

- i took over Yuki's tickets when she moved to the data team
- docs = Amira's developer guide, it's good
- to give a system a new scope: follow the section in the guide. Amira checks my changes

## todo

- understand how the documents endpoint finds the pdf
- ask Daniel what "PH40" is. it's in an old ticket
