# Hetzner Server Setup — Shubham

Hey Shubham. This is your task list for setting up the new DivineSide server. You don't need to know Linux commands — Claude Code does the actual work. Your job is to SSH into the server, open Claude Code inside the terminal, and give it each task below with the context provided.

**How this works:**
1. SSH into the server from your terminal
2. Run `claude` to open Claude Code inside the server
3. Paste each task below — Claude Code knows what to do
4. Verify it worked, move to the next task

---

## Before you start — get these from Mayank

- Root password for the server (Hetzner emailed it to Mayank when created)
- The full `.env` file contents (all API keys)
- The exported n8n workflow JSON files (Mayank exports from old Hostinger server)

---

## Part 1 — SSH into the server (manual, one time)

Open Terminal on your laptop (Mac: search Terminal, Windows: use Git Bash) and run:

```
ssh root@<SERVER_IP>
```

Enter the root password Mayank gave you. You are now inside the server.

---

## Part 2 — Set up your SSH key (no password login)

Inside the server, run `claude` to open Claude Code. Paste this task:

> **Task:** Set up SSH key authentication on this server so I can log in without a password.
>
> 1. Show me how to generate an SSH key on my own laptop (ed25519)
> 2. Show me the command to add my laptop's public key to this server's authorized_keys
> 3. Test that passwordless login works
>
> Server IP: <SERVER_IP>. I am currently logged in as root with a password.

---

## Part 3 — Base server setup

SSH in, run `claude`, paste:

> **Task:** Set up this fresh Ubuntu 26.04 server to run our web application stack. Install and configure:
> - Nginx (reverse proxy)
> - PM2 (process manager — keeps apps running after terminal closes)
> - Python 3 with pip and venv
> - Node.js v20
> - Docker and Docker Compose
> - Certbot (free SSL certificates)
> - UFW firewall — allow only ports 22 (SSH), 80 (HTTP), 443 (HTTPS), 5678 (n8n)
>
> Verify each one is working before moving on. Show me the version of each installed tool.

---

## Part 4 — Install and run n8n

n8n is our workflow automation tool, currently on the old Hostinger server. We are moving it here.

SSH in, run `claude`, paste:

> **Task:** Install and configure n8n on this server.
>
> - Install n8n globally via npm
> - Run it with PM2 (name: "n8n"), data folder at /root/n8n-data
> - n8n runs internally on port 5678
> - Public URL will be: https://n8n.divinesideai.com
> - Configure Nginx to reverse-proxy n8n.divinesideai.com to localhost:5678 with WebSocket support (n8n requires it)
> - Run Certbot to get the SSL certificate for n8n.divinesideai.com
>
> DNS for n8n.divinesideai.com already points to this server (<SERVER_IP>). Verify the full setup end to end.

---

## Part 5 — Import n8n workflows

Once n8n is live at `https://n8n.divinesideai.com`:

1. Open it in your browser and complete the account setup (create admin login)
2. For each JSON file Mayank gave you: click **+** → **Import from file** → select the JSON
3. Re-enter credentials inside n8n for each workflow — they don't export for security. Keys are in the `.env` file.

Credentials to re-enter in n8n:
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY`
- `AIRTABLE_TOKEN`
- `SUPABASE_DB_URL`
- Discord webhook URLs

---

## Part 6 — Clone the repo and set up environment

SSH in, run `claude`, paste:

> **Task:** Clone the DivineSide GitHub repo and set up the Python environment.
>
> - Repo: https://github.com/Mayank16-DS/DivineSide.git
> - Clone to: /root/DivineSide
> - Create a Python virtual environment at /root/DivineSide/.venv
> - Install dependencies from any requirements.txt files in the repo
> - Create an empty .env file at /root/DivineSide/.env (I will fill it manually)
> - Install Claude Code globally: npm install -g @anthropic-ai/claude-code
>
> After creating the .env file, tell me it's ready so I can paste the contents.

Once Claude Code creates the file, paste the `.env` contents Mayank gave you into it.

---

## Part 7 — Deploy divinecore-v2

divinecore-v2 is our FastAPI + Celery backend. It handles internal automations (Upwork proposals, Fathom meeting sync, Instantly outreach dashboard).

SSH in, run `claude`, paste:

> **Task:** Deploy the divinecore-v2 Docker stack.
>
> - Location: /root/DivineSide/divinecore-v2
> - Use: docker-compose.prod.yml
> - The .env is at /root/DivineSide/.env
> - Pull images, start all containers (api, worker, beat, redis) in detached mode
> - Verify all containers are running with no errors in logs
> - The API should be reachable on port 8000 internally

---

## Part 8 — Nginx for the app dashboard

The education dashboard (Target Academy product) will run on port 3001. Set up its domain now so it's ready when we deploy the frontend.

SSH in, run `claude`, paste:

> **Task:** Configure Nginx for app.divinesideai.com pointing to localhost:3001.
>
> The app isn't running yet — just set up the Nginx config and get the SSL certificate via Certbot.
> DNS for app.divinesideai.com already points to <SERVER_IP>.
> Make sure nginx -t passes cleanly.

---

## Part 9 — Final health check

SSH in, run `claude`, paste:

> **Task:** Full health check of this server. Verify and report on:
> 1. Nginx running, all domains responding (n8n.divinesideai.com, app.divinesideai.com)
> 2. n8n running in PM2, accessible at https://n8n.divinesideai.com
> 3. All divinecore-v2 Docker containers up (api, worker, beat, redis)
> 4. SSL certificates valid for all domains
> 5. UFW firewall active with correct rules
> 6. PM2 configured to start on reboot
>
> List anything that needs attention.

---

## Quick reference

Get back into the server:
```
ssh root@<SERVER_IP>
```

Open Claude Code once inside:
```
claude
```

If something breaks, tag Mayank in #operations on Discord with the error message.
