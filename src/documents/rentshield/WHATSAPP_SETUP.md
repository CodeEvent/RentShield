# Reverse-WhatsApp-QR phone verification (signup Option 2)

Free phone verification with **no outbound message cost**: the user scans a QR
that opens WhatsApp with `RentShield verify <code>` pre-filled to *our* number;
they **send it to us**, and we confirm on receipt. Because we only *receive*,
there's no per-message cost and no international SMS surcharge — it works
wherever WhatsApp messaging is allowed (incl. the UAE, where WhatsApp calls are
blocked but messages are not).

```
signup contact details -> email code -> [QR page] -> user sends WhatsApp to us
   -> WAHA inbound webhook marks it verified -> page auto-advances -> account made
```

## What you need
- **Nothing new on the phone** — WhatsApp is already there.
- **On the host:** one Docker container, **WAHA** (`devlikeapro/waha`) with the
  **NOWEB** engine (Baileys — no headless Chrome, light on RAM).
- A WhatsApp number to *receive* the codes (a spare/dedicated number is best —
  keep volume low; unofficial WhatsApp automation can be rate-limited/banned).

## 1. Run WAHA (host networking so it can reach the dev server on :8008)
```
docker run -d --name waha --network host \
  -e WHATSAPP_DEFAULT_ENGINE=NOWEB \
  -e WHATSAPP_HOOK_URL=http://localhost:8008/api/whatsapp/inbound/ \
  -e WHATSAPP_HOOK_EVENTS=message \
  devlikeapro/waha
```
Open WAHA's dashboard at **http://localhost:3000**, start the **default** session,
and **scan the QR with the WhatsApp you want to receive on** (WhatsApp →
Settings → Linked Devices → Link a device). That number is now the receiver.

## 2. Point RentShield at it (env — no code change)
```
PAPERLESS_PHONE_VERIFY=whatsapp_qr                 # default already
PAPERLESS_WHATSAPP_NUMBER=<the linked number, E.164, e.g. +9715...>
PAPERLESS_WA_WEBHOOK_SECRET=<optional shared secret>   # also set it in WAHA's hook
```
Restart the backend. The QR the signup shows will be
`wa.me/<PAPERLESS_WHATSAPP_NUMBER>?text=RentShield verify <code>`.

If you set `PAPERLESS_WA_WEBHOOK_SECRET`, add the same value to WAHA's webhook as
a custom header `X-Api-Key` (or append `?secret=...` to `WHATSAPP_HOOK_URL`), so
the inbound callback is authenticated.

## 3. Verify
Sign up with any number → scan the QR (or tap "Open WhatsApp & send" on a phone)
→ send → the page advances on its own within a few seconds. The webhook
(`documents/rentshield_views.whatsapp_inbound_webhook`) finds the pending
`WhatsAppVerification` by its code, stamps it verified, records the sender, and
`signup_phone_status_view`'s poll flips the page forward.

## Notes
- **Security:** verification is keyed on the per-signup `code` (unguessable) and,
  optionally, the webhook secret — so the endpoint can't flip an arbitrary
  account. The inbound sender number is recorded for the audit trail.
- **Switch back to SMS** any time with `PAPERLESS_PHONE_VERIFY=sms` (the
  sms-gate.app path in `otp_sms.py` — see `SMS_SETUP.md`).
- **Production:** for scale/compliance, graduate to the official **WhatsApp
  Business Cloud API** (authentication templates) behind the same webhook idea.
