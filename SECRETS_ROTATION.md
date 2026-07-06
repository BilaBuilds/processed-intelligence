# Secrets Rotation Checklist

Security status: project credentials were exposed outside version control and must be treated as compromised.

Do not run production enrichment, mailbox draft sync, or provider calls until the required credentials below have been rotated and `.env` has been repopulated locally.

## Rotation Inventory

| Credential | Env var | Status | Rotate at source | After rotation |
| --- | --- | --- | --- | --- |
| Companies House API key | `COMPANIES_HOUSE_API_KEY` | Required | Companies House Developer Hub -> application -> create/revoke API key | Put the new key in local `.env` only. Run a single Companies House smoke test. |
| Hostinger mailbox password | `HOSTINGER_EMAIL_PASSWORD` | Required | Hostinger hPanel -> Emails -> mailbox/account password | Put the new password in local `.env` only. Run `sync_hermes_drafts.py --dry-run` first, then one draft sync if needed. |
| Hostinger mailbox address | `HOSTINGER_EMAIL` | Review | Hostinger hPanel -> Emails | Keep as the sender identity if still correct. This is not a password but should be treated as operationally sensitive. |
| Hostinger IMAP host/port/folder | `HOSTINGER_IMAP_HOST`, `HOSTINGER_IMAP_PORT`, `HOSTINGER_DRAFTS_FOLDER` | Non-secret config | Hostinger email settings | Keep in `.env.example` and `.env`; do not treat as a credential. |
| Hunter API key | `HUNTER_API_KEY` | Future / optional | Hunter dashboard -> API keys | Add only when the provider exists. Store in local `.env`; never in config files. |
| SMTP username | `SMTP_USERNAME` | Future / optional | Mail provider admin panel | Add only if direct SMTP send/verify is introduced. |
| SMTP password | `SMTP_PASSWORD` | Future / optional | Mail provider admin panel | Add only if direct SMTP send/verify is introduced. |
| Gmail / connector OAuth | external connector | Review if used | Google account security / connected apps | Revoke only if suspicious activity is detected; no token is stored in this repo. |

## Required Actions

1. Revoke the exposed Companies House API key.
2. Create a fresh Companies House API key for the ProcessEd application.
3. Change the Hostinger mailbox password.
4. Confirm no mailbox forwarding rules or unknown sessions exist in Hostinger.
5. Update local `.env` with the new key/password.
6. Run the repo secret audit again.
7. Run `python -m unittest discover -s tests`.
8. Run a small non-bulk smoke test before any production batch.

## Files That May Contain Local Secrets

- `.env` only.

## Files That Must Never Contain Secrets

- `.env.example`
- `enrichment/config.yaml`
- `README.md`
- `agent_ops/**`
- `data/hermes/runs/**`
- `data/hermes/memory/**`
- `enrichment/**/*.py`
- `scripts/**/*.py`
- `warehouse/**/*.sql`
- `docs/**/*.md`

## Local `.env` Template

```text
COMPANIES_HOUSE_API_KEY=
HOSTINGER_EMAIL=
HOSTINGER_EMAIL_PASSWORD=
HOSTINGER_IMAP_HOST=imap.hostinger.com
HOSTINGER_IMAP_PORT=993
HOSTINGER_DRAFTS_FOLDER=Drafts
HUNTER_API_KEY=
SMTP_USERNAME=
SMTP_PASSWORD=
```

## Verification Commands

```powershell
git check-ignore -v .env
git log --all --full-history -- .env
git ls-files --stage -- .env
python -m unittest discover -s tests
```
