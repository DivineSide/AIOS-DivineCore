# DsideOS — Deployment Runbook (Hetzner CX23)

Server: `divinesideai` · `<SERVER_IP>` · 2 vCPU / 4 GB / 40 GB.
Public URL (after DNS + first deploy): `https://dsideos.divinesideai.com`.

The flow: **push to `main` → GitHub Actions → builds api/worker images →
pushes to GHCR → SSHes into the server → `docker compose pull && up -d` → Discord
ping.**

---

## ⚠ AS ACTUALLY DEPLOYED (verified on the box 2026-09-17)

**The sections below this one describe the ORIGINAL Caddy-based plan. That is
NOT what runs.** Verified against the live server; trust this section.

**nginx terminates TLS and routes — not Caddy.** There is no Caddy container and
`systemctl is-active caddy` reports inactive. The `Caddyfile` in this repo is
dead config, kept only as a record of the original design. Real routing lives in
five nginx sites under `/etc/nginx/sites-enabled/`: `dsideos`, `dsideos-console`,
`crm`, `n8n`, `app`.

**TLS is Certbot/Let's Encrypt**, auto-renewing via `certbot.timer`
(`certbot renew --dry-run` passes for all four certs).

**`dsideos.divinesideai.com` path-splits four ways**, longest-prefix wins:

| path | goes to |
|---|---|
| `/api/` | FastAPI backend, `127.0.0.1:8000` (the `api` container) |
| `/api/public/`, `/api/ingest/` | console container, `127.0.0.1:3001` |
| `/r/ /f/ /g/ /go/ /kit/`, `/_next/` | console container (growth module: referral, feedback, tracked review redirect) |
| `/` | **static** landing build on disk at `/var/www/dsideos-landing` |

**There is no `frontend` container.** `docker-compose.prod.yml` still declares a
`frontend` service pointing at `ghcr.io/divineside/dsideos-frontend`, but it is
not running and nginx never proxies to it — the landing page is static files
served directly by nginx. Either wire that service up or delete it from compose;
leaving it declared-but-dead is what made this doc wrong in the first place.

**Running containers** (7): `dsideos-api-1`, `dsideos-worker-1`, `dsideos-beat-1`,
`dsideos-redis-1`, `dsideos-console-1`, plus two unrelated to DsideOS —
`n8n` (kept deliberately) and `divinecore-crm` (idle since 2026-07-20).

### Operational gotchas found the hard way

**Docker's log driver is UNCAPPED by default** and there is no
`/etc/docker/daemon.json`. A crash-looping PM2-managed n8n (long since replaced
by the n8n *container*) wrote a **7.3GB** `/root/.pm2/logs/n8n-error.log` plus a
1.8GB `pm2.log`, filling the disk to 72% and making the console container fail
with `ENOSPC: no space left on device`. Cleared 2026-09-17 (disk 72% → 41%).
`journald` is now capped at 200M via `SystemMaxUse`; **Docker's own log rotation
is still uncapped** — setting it requires a daemon restart, which bounces every
container, so it is deliberately left as a scheduled task rather than done live.

**`pm2 list` is empty** — PM2 manages nothing now. Its logs were pure orphan.
Note a log file held open by a live process must be TRUNCATED (`: > file`), not
`rm`'d: unlinking an open file does not return the space until the handle closes.

**CI does not run the test suite.** The `test` job is `py_compile` plus the
krutidev check (~20s). `tests/test_reasoning.py` — the correctness gate for a
question path that deliberately bypasses every runtime validator — is NOT run on
push. Fixing that is the single highest-value CI change available.

---

## One-time setup (ORIGINAL Caddy plan — superseded, see the section above)

### 1. DNS (free subdomain — no purchase)
In Hetzner DNS (or wherever divinesideai.com is managed), add an **A record**:

```
Type: A   Name: dsideos   Value: <SERVER_IP>   TTL: auto
```

`dsideos.divinesideai.com` now resolves to the server. (AAAA to the IPv6
`2a01:4f9:c014:ae4a::` is optional.)

### 2. Firewall (Hetzner console → Firewalls)
Open inbound **22** (SSH), **80** (HTTP, for Let's Encrypt), **443** (HTTPS).
Caddy needs 80 + 443 reachable to issue the cert.

### 3. Server prep (SSH in once)
```bash
ssh root@<SERVER_IP>

# Docker + compose plugin
curl -fsSL https://get.docker.com | sh

# App dir + config
mkdir -p /root/DsideOS && cd /root/DsideOS
# copy these three files up (scp from your machine or paste):
#   docker-compose.prod.yml
#   Caddyfile
#   .env            (from .env.example, with real ANTHROPIC_API_KEY)

# Log in to GHCR so the server can pull private images
echo "<GHCR_PULL_TOKEN>" | docker login ghcr.io -u <github-user> --password-stdin
```

`.env` on the server (only these matter in prod — REDIS_URL/JOBS_DIR are set by compose):
```
OPENAI_API_KEY=sk-...          # PRIMARY for text (extraction, explanations)
ANTHROPIC_API_KEY=sk-ant-...   # fallback on quota/auth errors + the vision path
LLM_PRIMARY=openai             # leader; falls back to anthropic automatically
JOB_TTL_HOURS=24
MAX_UPLOAD_MB=50
```

**Model routing:** OpenAI runs all text calls until credits run out; on a quota /
rate / auth error the same call retries on Claude automatically (see
`pipeline/llm.py:complete()`). Vision (scanned PDFs / photos) is Claude-first.

### 4. GitHub repo secrets (Settings → Secrets → Actions)

| Secret | What it is |
|--------|-----------|
| `HETZNER_HOST` | `<SERVER_IP>` |
| `HETZNER_USER` | `root` |
| `HETZNER_SSH_KEY` | private key whose public half is in the server's `~/.ssh/authorized_keys` |
| `GHCR_PULL_TOKEN` | a GitHub PAT with `read:packages` (server uses it to pull images) |
| `DISCORD_WEBHOOK_URL` | `#deploys` channel webhook (optional ping) |

`GITHUB_TOKEN` (build/push to GHCR in CI) is auto-provided — no setup.

### 4b. Client branded assets (required — not in the image)

The builders need the client's branded files at runtime. They're client IP
(gitignored, never in the repo or image) so they're mounted from the server:

```
/root/DsideOS/assets/
  resources/   <- copy clients/target-academy/resources/ here (front-page.docx, …)
  templates/   <- copy clients/target-academy/templates/  here (logo, watermark)
```

scp them up from your machine:
```bash
scp -r clients/target-academy/resources root@<SERVER_IP>:/root/DsideOS/assets/
scp -r clients/target-academy/templates root@<SERVER_IP>:/root/DsideOS/assets/
```
The worker mounts these read-only (see `docker-compose.prod.yml`). Without them,
builds fail at the first template open.

### 4c. Fonts (for correct PDF rendering)

The worker image bundles whatever is in `DsideOS/fonts/` at build time, but the
.ttf files are gitignored. For correct Kruti Dev / Unicode PDFs, the **build host**
(GitHub Actions runner) needs the fonts — simplest path: commit them to a private
location or bake them in a base image. Interim: PDFs render with fallback fonts
until provisioned. (Tracked as a follow-up — does not block the API.)

### 5. First deploy
Push to `main` (or run the workflow manually via **Actions → DsideOS CI/CD →
Run workflow**). The deploy job pulls + starts everything. Caddy fetches the TLS
cert on the first HTTPS hit.

Smoke test:
```bash
curl https://dsideos.divinesideai.com/api/        # -> {"ok": true, ...}
```

---

## Day-to-day

- **Deploy** = push to `main`. CI handles the rest.
- **Manual deploy** on the server:
  ```bash
  cd /root/DsideOS
  export DSIDEOS_IMAGE_TAG=latest
  docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d
  ```
- **Logs:** `docker compose -f docker-compose.prod.yml logs -f worker`
- **Job storage** lives in the `jobs` volume; the beat task purges folders older
  than `JOB_TTL_HOURS`. Disk is 40 GB (~6 MB/run) — thousands of runs of headroom.

## Frontend

Built + published from its own repo as `ghcr.io/divineside/dsideos-frontend`.
The `frontend` service in `docker-compose.prod.yml` runs that image; Caddy routes
`/*` to it and `/api/*` to the backend (same origin → no CORS). Until the frontend
image exists, comment out the `frontend` service — `/api/*` still works.

## Memory note (CX23 is 4 GB)

Worker runs `--concurrency=2` (LibreOffice + Claude calls are memory-hungry). If
you see OOM kills (`docker compose logs` shows workers restarting), drop to
`--concurrency=1` or resize the server up one tier (CX33 = 8 GB).
