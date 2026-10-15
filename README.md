# RentShield

**A Dubai tenancy-notice & landlord identity-verification platform** — built to let property
owners verify their identity once, then generate legally-sound, bilingual (English/Arabic),
statute-cited tenancy notices that are ready for the Rental Dispute Settlement Centre (RDSC).

> Built as a fork of [paperless-ngx](https://github.com/paperless-ngx/paperless-ngx)
> (document-management engine, GPLv3), extended with a full RentShield domain layer.

---

## The problem

Serving a tenancy notice in Dubai that will actually *hold up* at the RDSC is hard for
individual landlords: the notice must cite the right articles of **UAE Law No. 33 of 2008**,
be served and documented correctly (Ejari, notary/official service), and the owner's identity
must be verifiable. Get any step wrong and the filing is rejected. RentShield turns that into a
guided, compliance-gated workflow.

## Key features

- **Owner identity verification** — passport **NFC-chip** read + **live selfie**, with an
  independent chip-photo-vs-selfie match, surfaced to a **Notary Public** for the final decision
  (integrates a self-hosted Idswyft instance; the notary is always the human in the loop).
- **Bilingual, statute-cited notices** — generates EN/AR tenancy notices referencing the correct
  provisions of UAE Law 33/2008.
- **RDSC compliance gate** — a filing packet can only be produced once identity is *verified*,
  an *Ejari* certificate is linked, and *proper service* is evidenced — enforced **server-side**,
  not just in the UI.
- **RDSC filing workflow** — modelled with `django-viewflow` (process + flow for the filing
  lifecycle).
- **Security** — TOTP **two-factor authentication** with backup codes.
- **Billing / arrears** tracking; AED pricing, no subscription.

## Tech stack

| Layer | Tech |
|-------|------|
| Backend | **Django** + **Django REST Framework** (Python) |
| Frontend | **Angular** + TypeScript |
| Workflow | `django-viewflow` (RDSC filing process) |
| Identity | self-hosted **Idswyft** (NFC + liveness) + independent face-match |
| Auth | TOTP 2FA + backup codes |
| Base engine | forked from **paperless-ngx** (documents, OCR, custom fields) |

## Architecture highlights

- A **provenance-first compliance model**: the RDSC readiness check
  (`documents/rentshield/compliance.py`) validates three checkpoints — identity, lease/Ejari,
  and service — and the packet generator **re-enforces the same gate server-side**, so a notice
  can never be filed out of compliance.
- Custom fields on documents drive the notice + identity data model.

---

## Status & notes

This is a **portfolio / in-progress** project. Secrets, certificates and local-dev credentials
are intentionally **excluded** from this repository (see `.gitignore`); deployment configuration
is provided through environment variables.

## Licence

Derivative of **paperless-ngx** — distributed under the **GNU GPL v3** (see `LICENSE`).
