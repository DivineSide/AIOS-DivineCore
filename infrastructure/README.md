# Infrastructure — VPS, Credentials, Deployments

Do not store passwords or API keys in files. This README references where they live.

## VPS Access

**Host:** srv1445995.hstgr.cloud | IP: 187.124.96.99 | Provider: Hostinger

**SSH authorized keys** (edit `/root/.ssh/authorized_keys` to grant/revoke):
- Pang (yhpang@oneboxagency.com) — authorized 2026-05-03, ed25519 key, no passphrase, generated on Windows laptop at `C:\Users\user\.ssh\id_ed25519`
- Mayank's personal SSH key also authorized as of 2026-05-03
- CI will use a separate deploy keypair (pending setup)

## External Services

- **n8n:** https://n8n.srv1445995.hstgr.cloud
- **Airtable base:** DivineCore (api key in password manager)
- **Primary email (legacy):** mayankrawat000072@gmail.com

## GitHub Repositories

**Upstream `DivineSide/AIOS-DivineCore`** — source of truth as of 2026-05. Mayank pushes direct. Pang has admin access, can push without PR. Its CI builds prod images.

**Fork `OneBox69/AIOS-DivineCore`** — Pang's dev sandbox. Fork CI builds images to `ghcr.io/onebox69/...` (unused; prod pulls from upstream org). CI secrets:
- `GITHUB_TOKEN` — auto-provisioned
- `DISCORD_WEBHOOK_URL` — webhook for `#deploys` channel, configured 2026-05-03

## GitHub Container Registry (GHCR)

**Images:** `ghcr.io/divineside/aios-divinecore/{api,worker}` — private, published by upstream CI.

**VPS auth:** GitHub PAT with `read:packages` scope, cached at `/root/.docker/config.json`. Anyone pulling on a new machine needs DivineSide-org package access + their own PAT.

**Migration note:** Previously pulled from `ghcr.io/onebox69/...` (set up 2026-05-03); switched to `divineside` org on 2026-05-13.

## Deployment Checklist

When deploying to VPS:

```
ssh root@srv1445995.hstgr.cloud "cd /root/divinecore-v2 && docker compose pull && docker compose up -d"
```

Smoke test: `curl https://upwork.srv1445995.hstgr.cloud/` (returns `{"status":"ok",...}`) or run `/tasks/echo` test.

Check logs: `docker compose -f /root/divinecore-v2/docker-compose.prod.yml logs -f`.
