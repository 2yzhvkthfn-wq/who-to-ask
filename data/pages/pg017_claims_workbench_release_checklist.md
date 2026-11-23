---
id: pg017
title: "Claims Workbench: release checklist"
space: claims_platform
system: claims_workbench
type: doc
author: p007
created: 2026-02-23
updated: 2026-09-08
language: en
---

# Claims Workbench: release checklist

**Owner:** Hélène Dubois · **Applies to:** every release of the Claims Workbench · **Updated:** 8 September 2026

Adjusters use the Workbench all day. A bad release stops payments. This checklist is not optional.

## Rules

- Releases happen on a Tuesday or a Wednesday, before 07:00. Never on a Friday, and never in the last three working days of the month.
- No release during a storm event. The claims centre tells us when one is declared.
- One person releases, another one watches. Both names go in the release ticket.

## Before the release

- [ ] Every ticket in the release is tested in staging by someone other than its developer
- [ ] Two adjusters from the claims centre have tried the changes that touch their screens
- [ ] The table of payment approval limits is unchanged, or the change has its own ticket (example: CLM-279)
- [ ] The release note is written in French and in English, in plain words
- [ ] The way back is tested: the previous version can be restored in under 15 minutes

## During the release

- [ ] 06:00: tell the claims centre supervisor that the release starts
- [ ] 06:05: release
- [ ] 06:20: smoke test: open a claim, add a note, attach a document, approve a small payment in the test file
- [ ] 06:40: tell the supervisor that it is done, or that we went back

## After the release

- [ ] Watch the error rate for one hour
- [ ] Ask the supervisor at 10:00 whether the adjusters saw anything odd
- [ ] Close the release ticket

## What went wrong, or nearly did, and what we changed

| When | What happened | Change to this checklist |
|---|---|---|
| March 2026 | A release on the last day of the month slowed the month-end payments | The rule on the last three working days |
| June 2026 | Claims with many documents froze the screen (CLM-262) | The smoke test now attaches a document |
| August 2026 | The adjusters' test caught a storm exception that also applied to glass claims, before the release (CLM-279) | That test is now a line of this checklist |
