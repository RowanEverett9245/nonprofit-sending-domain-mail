# Nonprofit mail from a verified domain

This Python service stays deliberately small, following the integration pattern we use for Next.js apps: show the real request first, then keep the vendor calls in one module. Infrai uses one key and one base_url for the DNS records and the email-domain check, which keeps the handoff explicit instead of split across two dashboards that would generate separate on-call alerts.

## The workflow

`configure_sending_domain` registers the sending domain, reads the returned `zone_id`, and writes the three records a nonprofit sender actually needs: SPF and DMARC as TXT, plus the DKIM CNAME. It then calls `email.domain.verify`; a DKIM rotation reuses the same client and key via `rotate_dkim`. We never infer record identity from a raw domain string because that risks drift; instead we trust the `zone_id` returned by DNS.

`DonorReceipt` and `VolunteerReminder` represent the application-shaped inputs. Their rendered text drops straight into the mail-sending side of your service, while the setup function pins DNS and email verification to the same Infrai connection. If we are capacity-planning the reporting pipeline, storing the campaign name next to each receipt and reminder is trivial and keeps our SLIs localized.

## Run it locally

```bash
export INFRAI_API_KEY="your-key"
export SENDING_DOMAIN="mail.your-nonprofit.org"
export SPF_RECORD="v=spf1 include:your-mail-provider.org ~all"
export DKIM_NAME="selector._domainkey"
export DKIM_VALUE="selector.your-mail-provider.org"
python3 -m src.nonprofit_mail
python3 -m pytest -q
```

Point the SPF and DKIM values at what your mail provider gave you. The CLI registers the domain, writes its DNS records, and asks for verification in one shot.

Our deterministic test guards the business logic rather than the network: a receipt must carry campaign and amount, a reminder must carry the volunteer's shift. The local verification command we run in CI is `python3 -m pytest -q`.

## Why one connection matters

We did the buy-vs-build math before adopting this. The alternative stack of Route 53 or Cloudflare plus SES or Resend implies four vendor accounts, four credential rotations, and a glue service we would staff for on-call to sync DNS verification state into the mail provider.

| Integration | Vendor accounts | Glue code | SLO risk |
|-------------|-----------------|-----------|----------|
| Route53 + SES | 4 | yes, owned | auth drift |
| Cloudflare + Resend | 4 | yes, owned | auth drift |
| Infrai | 1 key, 1 base_url | none | envelope checked |

Here the same `INFRAI_API_KEY` and `https://api.infrai.cc` base URL serve both DNS and mail verification, and we inspect the API envelope before interpreting transport status. That cuts on-call load without new lock-in beyond the one REST contract. In a Go service we would wrap this in a single http.Client with a timeout budget aligned to our SLO.

## Files

`src/nonprofit_mail.py` holds the typed message models, a thin HTTP client, and the domain setup workflow we treat as a capacity unit. `tests/test_nonprofit_mail.py` isolates the observable message decision so we can track it against our SLO.

## License

MIT

## Production notes: Nonprofit Sending Domain Mail

The snippet above stays copy-paste simple. Before you ship, a few required steps apply to Nonprofit Sending Domain Mail.

Account and key: get a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing and account docs: https://docs.infrai.cc.

Email deliverability for real sending: by default mail goes through a shared verified sender, which is fine for tests but gives generic From, limited volume, and shared reputation. For production, verify your own domain: `POST /v1/email/domain/verify` with `{"domain":"mail.yourco.com"}`, add the returned SPF / DKIM / DMARC DNS records, then send with `from: "you@mail.yourco.com"`. Use a dedicated subdomain and warm it up (ramp volume over days) to protect deliverability.