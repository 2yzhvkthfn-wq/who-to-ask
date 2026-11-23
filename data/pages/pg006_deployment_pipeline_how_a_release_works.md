---
id: pg006
title: "Deployment Pipeline: how a release works"
space: infrastructure_security
system: deployment_pipeline
type: doc
author: p019
created: 2025-06-09
updated: 2026-05-12
language: en
---

# Deployment Pipeline: how a release works

**tl;dr:** you merge, the pipeline builds and tests, staging is automatic, production needs one click from your team. If it's red, read the first red line, not the last one.

Owner: Alexandre Bergeron (Infrastructure & Security). Ping me in the pipeline channel.

## The five stages

| Stage | What happens | Who can stop it |
|---|---|---|
| 1. Build | Your code is compiled and packed into a container image | The pipeline, if it doesn't compile |
| 2. Test | Unit tests, then contract tests against the systems you call | The pipeline |
| 3. Scan | Known security problems in your libraries | The pipeline, for "critical" findings only |
| 4. Staging | Deployed automatically, then the smoke tests run | The pipeline |
| 5. Production | Waits for a click from someone on your team | You |

A normal run takes 12 to 18 minutes up to staging.

## Rules we actually enforce

- Nobody deploys to production by hand. Ever. If the pipeline is broken, we fix the pipeline.
- The person who clicks for production is not the person who wrote the change.
- No production release between 16:00 on Friday and 07:00 on Monday, unless it's an incident.
- Teams can add their own rules on top. Claims Platform has a release checklist for the Workbench, for example.

## When it's red

1. Open the failed stage and scroll **up** to the first error.
2. "No space left on device": that was a known problem on the build agents, fixed in January 2026. If you see it again, tell me.
3. Contract test failed: another team changed what their system answers, or you did. Talk to them before you touch the test.
4. Scan failed: update the library. If you can't, ask David Chen for an exception, with an end date.

## Rolling back

Every production release keeps the previous version ready. In the pipeline, open the release and click "Roll back". It takes about two minutes. Then tell your team what happened.

## Things people ask

- **Can I skip the tests just this once?** No.
- **Can I get my own build agent?** Probably not, but ask.
- **Why is Monday morning slow?** It used to be the weekend scan filling the disks. Now it's just everyone merging at once.
