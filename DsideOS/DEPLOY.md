# DsideOS — Deployment Runbook (Hetzner CX23)

Server: `divinesideai` · `204.168.198.139` · 2 vCPU / 4 GB / 40 GB.
Public URL (after DNS + first deploy): `https://dsideos.divinesideai.com`.

The flow: **push to `main` → GitHub Actions tests → builds api/worker images →
pushes to GHCR → SSHes into the server → `docker compose pull && up -d` → Discord
ping.** Caddy terminates TLS and path-splits `/api/*` (backend) vs `/*` (frontend).

---

## One-time setup

### 1. DNS (free subdomain — no purchase)
In Hetzner DNS (or wherever divinesideai.com is managed), add an **A record**:

```
Type: A   Name: dsideos   Value: 204.168.198.139   TTL: auto
```

`dsideos.divinesideai.com` now resolves to the server. (AAAA to the IPv6
`2a01:4f9:c014:ae4a::` is optional.)

### 2. Firewall (Hetzner console → Firewalls)
Open inbound **22** (SSH), **80** (HTTP, for Let's Encrypt), **443** (HTTPS).
Caddy needs 80 + 443 reachable to issue the cert.

### 3. Server prep (SSH in once)
```bash
ssh root@204.168.198.139

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
| `HETZNER_HOST` | `204.168.198.139` |
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
scp -r clients/target-academy/resources root@204.168.198.139:/root/DsideOS/assets/
scp -r clients/target-academy/templates root@204.168.198.139:/root/DsideOS/assets/
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
