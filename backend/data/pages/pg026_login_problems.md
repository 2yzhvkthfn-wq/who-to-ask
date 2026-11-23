---
id: pg026
title: "Login problems"
space: infrastructure_security
system: single_sign_on
type: doc
author: p019
created: 2026-07-15
updated: 2026-08-03
language: en
---

# Login problems

**tl;dr:** nine times out of ten it's the clock, the phone, or the password manager. Try the list below before you open a ticket.

Kept by Alexandre Bergeron. I add a line each time something new comes up.

## The sign-in page comes back again and again

- Check the clock of the computer. If it's more than 5 minutes off, Single Sign-On refuses you and doesn't say why. This hit the shared workstations of the claims centre in July 2026.
- Close every browser window and try again in a private window. If that works, clear the cookies of the sign-in site.

## The code from my phone is refused

- Codes change every 30 seconds. Type faster, or wait for the next one.
- New phone? The old codes are gone. Open a ticket in INF, component Single Sign-On, and say "new phone". We check who you are by video, then we reset it.
- Phone clock set by hand? Put it back on automatic.

## My password is refused, and I'm sure it's right

- Caps lock.
- Your password manager is filling in the old one. Yes, really. Look at what it typed.
- Passwords expire after 180 days. You get three emails before. They look like spam, but they're not.

## I'm locked out

Ten wrong tries lock the account for 30 minutes. Waiting is faster than a ticket. If you're locked out and it's urgent, your team lead can call the security line.

## It works on my laptop, but not on the shared workstation

See the clock thing above. If the clock is right, tell us which workstation: the name is on the sticker under the screen.

## I need to get into a system I've never used

That's not a login problem. Ask the team that owns the system: they decide who gets in, and how.
