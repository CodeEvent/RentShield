# Turning on real phone-OTP SMS (sms-gate.app)

RentShield's signup phone step (`documents/rentshield/otp_sms.py`) ships with
the **`console`** backend: in DEBUG the 6-digit code is shown on the verify
page and **nothing is sent off the machine**. To text real codes, switch to the
**`smsgate`** backend, which sends through **sms-gate.app**
(github.com/capcom6/android-sms-gateway, Apache-2.0) — an Android phone + SIM
you control acting as a REST SMS gateway. No Twilio, no third party routing your
OTPs.

## 1. Stand up the gateway (your phone)

1. Install **"SMS Gateway for Android"** from the project
   (github.com/capcom6/android-sms-gateway — Play Store, F-Droid, or the APK) on
   an Android 5.0+ phone with a SIM that can send SMS.
2. Open the app and choose a mode:
   - **Local server** — the app runs an HTTP server on the phone (`http://<phone-ip>:8080`).
     Simplest on a LAN; the phone must be reachable from the RentShield host.
   - **Self-hosted server** — run the open-source server (Docker) and the phone
     connects out to it. Best if the host can't reach the phone directly.
3. The app shows a **username** and **password** (Basic auth). Note them and the
   base URL.
4. Send yourself a test SMS from the app's UI to confirm the SIM works.

## 2. Point RentShield at it (env vars only — no code change)

Set these on the RentShield backend (your `.env` / compose env):

```
PAPERLESS_SMS_BACKEND=smsgate
PAPERLESS_SMS_GATE_URL=http://<phone-or-server-ip>:8080      # no trailing slash
PAPERLESS_SMS_GATE_USER=<gateway username>
PAPERLESS_SMS_GATE_PASS=<gateway password>
```

Restart the backend. That's it — `otp_sms.send_sms_otp()` now POSTs
`{"message": "...", "phoneNumbers": ["+9715..."]}` to `"<URL>/message"` with
Basic auth. The code is never shown on screen any more (that only happens with
the console backend in DEBUG).

## 3. Verify

Run a signup with a real phone number and confirm the SMS arrives. If the
gateway is unreachable or rejects the send, the user sees *"We couldn't send the
code right now"* and **no account is created** (never a 500) — see
`SmsOtpError` handling in `signup_phone_view`.

## Swapping gateways

`textbee` (MIT) and `httpSMS` are drop-in alternatives — they expose the same
"Android phone as REST SMS gateway" shape. To use one, adjust the single
`_send_via_smsgate()` body in `otp_sms.py` (URL path / payload keys); nothing
else in the signup flow changes.

## Notes for UAE

- SMS to UAE (+971) numbers from a UAE SIM works for low volume. High-volume or
  branded-sender-ID SMS in the UAE is regulated (TRA / the telcos) — for
  production scale you may later want a UAE provider (e.g. Unifonic) behind this
  same `send_sms_otp()` seam.
- A mobile number is personal data under the UAE PDPL; RentShield stores it
  **encrypted at rest** (`VerifiedPhone.phone`, EncryptedCharField).
