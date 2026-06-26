# DsideOS Console — Developer Handoff
## Auth, Landing Page, and Frontend–Backend Integration

**Owner:** Mayank Rawat (DivineSide)  
**Scope:** Two deliverables — (1) Google OAuth login with per-institute invite flow, (2) landing page + console wired to the existing DsideOS FastAPI backend.  
**Domain:** `console.dsideos.divinesideai.com`  
**Backend already live at:** `dsideos.divinesideai.com` (FastAPI + Celery + Redis, Hetzner VPS)

---

## What you are building

The console is a multi-tenant web app. DivineSide sets up each institute's account themselves — branding, fonts, data — and then invites the institute owner's Gmail. The owner clicks the invite link, signs in with Google, and lands directly in their pre-configured dashboard. They never see another institute's data.

This is the same model as Notion, Linear, or Vercel workspaces: admin creates the workspace, invites the user, user authenticates via Google and the workspace is already waiting.

Two pages:
1. **Landing page** — `console.dsideos.divinesideai.com/` — marketing/entry, "Sign in with Google" CTA
2. **Console** — `console.dsideos.divinesideai.com/dashboard/...` — the actual app (Generate, Questions, Solutions, Answer Key)

---

## Architecture Overview

```
Browser
  └── console.dsideos.divinesideai.com  (Next.js, Vercel or same Hetzner VPS)
        ├── /                            Landing page + Sign in with Google
        ├── /auth/callback               Google OAuth callback handler
        ├── /dashboard/generate/full     Full Run page (calls DsideOS API)
        ├── /dashboard/generate/...      Other generate pages
        └── /api/...                     Next.js API routes (thin proxy to DsideOS)

DsideOS Backend (already live)
  └── dsideos.divinesideai.com/api/...  FastAPI (extract, build, full, jobs, files)

Supabase (auth + institute data)
  └── auth.users                        Google OAuth users
  └── institute_members                 invite table (email → institute_id)
  └── institutes                        per-institute config (name, fonts, branding)
```

The frontend talks to the DsideOS backend through Next.js API routes — never directly from the browser. This keeps the DsideOS API internal and lets you add per-request auth headers.

---

## Part 1 — Auth: Google OAuth + Invite Flow

### How it works

```
DivineSide admin
  1. Creates institute row in Supabase
  2. Sets up branding, fonts, config
  3. Calls POST /api/admin/invite { email: "owner@gmail.com", institute_id: "xyz" }
     → writes row to institute_members table
     → sends invite email (Resend / SendGrid)

Institute owner
  4. Opens invite email → clicks link → lands on /invite?token=abc
  5. Clicks "Sign in with Google"
  6. Google OAuth flow → callback → Supabase session created
  7. Middleware checks institute_members for their email
  8. If found → redirect to /dashboard
  9. If not found → show "Access restricted" page
```

### Supabase tables (run in SQL editor)

```sql
-- One row per institute (set up by DivineSide)
create table institutes (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  slug        text unique not null,       -- e.g. "target-academy"
  font        text default 'unicode',     -- "unicode" | "krutidev"
  logo_url    text,
  created_at  timestamptz default now()
);

-- Maps a Gmail address to an institute (the invite)
create table institute_members (
  id            uuid primary key default gen_random_uuid(),
  institute_id  uuid references institutes(id) on delete cascade,
  email         text not null,            -- the Gmail they will sign in with
  role          text default 'owner',     -- "owner" | "admin" | "viewer"
  invited_at    timestamptz default now(),
  accepted_at   timestamptz,
  unique(institute_id, email)
);
```

Row-level security — enable it. Members can only read their own institute:

```sql
alter table institutes enable row level security;
alter table institute_members enable row level security;

create policy "member reads own institute"
  on institutes for select
  using (
    id in (
      select institute_id from institute_members
      where email = auth.jwt() ->> 'email'
    )
  );

create policy "member reads own membership"
  on institute_members for select
  using (email = auth.jwt() ->> 'email');
```

### Google OAuth setup

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID → Web application
3. Authorized redirect URIs:
   - `https://console.dsideos.divinesideai.com/auth/callback`
   - `http://localhost:3000/auth/callback` (dev)
4. Copy Client ID and Client Secret

In Supabase dashboard → Authentication → Providers → Google:
- Paste Client ID and Secret
- Enable Google provider

### Next.js auth implementation

Install:
```bash
npm install @supabase/supabase-js @supabase/ssr
```

**`lib/supabase/client.ts`**
```typescript
import { createBrowserClient } from '@supabase/ssr'

export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!
  )
}
```

**`lib/supabase/server.ts`**
```typescript
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export async function createClient() {
  const cookieStore = await cookies()
  return createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return cookieStore.getAll() },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        },
      },
    }
  )
}
```

**`app/auth/callback/route.ts`** — handles Google redirect
```typescript
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')

  if (code) {
    const supabase = await createClient()
    const { data: { user }, error } = await supabase.auth.exchangeCodeForSession(code)

    if (!error && user?.email) {
      // Check if this email has been invited
      const { data: membership } = await supabase
        .from('institute_members')
        .select('institute_id, accepted_at')
        .eq('email', user.email)
        .single()

      if (!membership) {
        // Not invited — sign them out and show error
        await supabase.auth.signOut()
        return NextResponse.redirect(`${origin}/?error=not_invited`)
      }

      // Mark invite as accepted if first login
      if (!membership.accepted_at) {
        await supabase
          .from('institute_members')
          .update({ accepted_at: new Date().toISOString() })
          .eq('email', user.email)
      }

      return NextResponse.redirect(`${origin}/dashboard/generate/full`)
    }
  }

  return NextResponse.redirect(`${origin}/?error=auth_failed`)
}
```

**`middleware.ts`** — protects all /dashboard routes
```typescript
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return request.cookies.getAll() },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()

  if (!user && request.nextUrl.pathname.startsWith('/dashboard')) {
    return NextResponse.redirect(new URL('/', request.url))
  }

  return supabaseResponse
}

export const config = {
  matcher: ['/dashboard/:path*'],
}
```

### Admin invite endpoint

**`app/api/admin/invite/route.ts`**
```typescript
import { createClient } from '@/lib/supabase/server'
import { NextResponse } from 'next/server'

export async function POST(request: Request) {
  // Protect with a simple admin secret header
  const adminSecret = request.headers.get('x-admin-secret')
  if (adminSecret !== process.env.ADMIN_SECRET) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
  }

  const { email, institute_id } = await request.json()
  const supabase = await createClient()

  const { error } = await supabase
    .from('institute_members')
    .insert({ email, institute_id })

  if (error) return NextResponse.json({ error: error.message }, { status: 400 })

  // TODO: send invite email via Resend/SendGrid
  // The invite email should link to: /invite?email=<email>
  // which renders a "You've been invited — Sign in with Google" page

  return NextResponse.json({ success: true })
}
```

To invite an owner, Mayank runs:
```bash
curl -X POST https://console.dsideos.divinesideai.com/api/admin/invite \
  -H "x-admin-secret: $ADMIN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"email": "owner@gmail.com", "institute_id": "xyz-uuid"}'
```

---

## Part 2 — Frontend wired to DsideOS backend

### Current backend endpoints (already live at dsideos.divinesideai.com)

| Method | Path | What it does |
|--------|------|-------------|
| `POST` | `/api/extract` | Upload file → returns job_id, extracts questions |
| `POST` | `/api/full` | Upload file + meta → job_id, all 4 deliverables |
| `POST` | `/api/build` | Questions + format/font → job_id |
| `POST` | `/api/answer-key` | Questions + font → job_id |
| `POST` | `/api/solutions` | Questions + font → job_id |
| `GET` | `/api/jobs/{id}` | Poll status: QUEUED → RUNNING → DONE/FAILED |
| `GET` | `/api/files/{id}/{filename}` | Download output file |

**Job polling pattern** — all endpoints return a job_id immediately, then you poll:
```typescript
// Poll until DONE or FAILED
async function pollJob(jobId: string) {
  while (true) {
    const res = await fetch(`/api/proxy/jobs/${jobId}`)
    const job = await res.json()
    if (job.status === 'DONE') return job
    if (job.status === 'FAILED') throw new Error(job.error)
    await new Promise(r => setTimeout(r, 2000))  // poll every 2s
  }
}
```

### Next.js proxy routes (never expose DsideOS URL to browser)

**`app/api/proxy/[...path]/route.ts`**
```typescript
import { createClient } from '@/lib/supabase/server'
import { NextResponse } from 'next/server'

const BACKEND = process.env.DSIDEOS_BACKEND_URL  // dsideos.divinesideai.com

export async function POST(
  request: Request,
  { params }: { params: { path: string[] } }
) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const path = params.path.join('/')
  const body = await request.blob()

  const upstream = await fetch(`${BACKEND}/api/${path}`, {
    method: 'POST',
    body,
    headers: { 'content-type': request.headers.get('content-type') || '' },
  })

  const data = await upstream.json()
  return NextResponse.json(data, { status: upstream.status })
}

export async function GET(
  request: Request,
  { params }: { params: { path: string[] } }
) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const path = params.path.join('/')
  const upstream = await fetch(`${BACKEND}/api/${path}`)

  // File download — stream it through
  if (path.startsWith('files/')) {
    const buffer = await upstream.arrayBuffer()
    return new Response(buffer, {
      headers: {
        'content-type': upstream.headers.get('content-type') || 'application/octet-stream',
        'content-disposition': upstream.headers.get('content-disposition') || '',
      },
    })
  }

  const data = await upstream.json()
  return NextResponse.json(data, { status: upstream.status })
}
```

All frontend fetch calls use `/api/proxy/...` — never the raw backend URL.

### Per-institute config in session

After login, load the institute config and store it in React context:

```typescript
// hooks/useInstitute.ts
import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

export function useInstitute() {
  const [institute, setInstitute] = useState(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getUser().then(({ data: { user } }) => {
      if (!user) return
      supabase
        .from('institutes')
        .select('*')
        .single()
        .then(({ data }) => setInstitute(data))
    })
  }, [])

  return institute
}
```

Use `institute.font`, `institute.name`, `institute.logo_url` throughout the UI to render per-client branding.

---

## Part 3 — Landing Page

**URL:** `console.dsideos.divinesideai.com/`

**What it needs:**
- DivineSide / DsideOS branding
- One-line description of what the console does
- "Sign in with Google" button — this is the only action
- If `?error=not_invited` in URL → show a message: "Your account hasn't been set up yet. Contact your DivineSide representative."
- If `?error=auth_failed` → "Something went wrong. Try again."

**Sign in with Google button implementation:**
```typescript
// components/SignInButton.tsx
'use client'
import { createClient } from '@/lib/supabase/client'

export function SignInButton() {
  const handleSignIn = async () => {
    const supabase = createClient()
    await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: `${window.location.origin}/auth/callback`,
      },
    })
  }

  return (
    <button onClick={handleSignIn}>
      Sign in with Google
    </button>
  )
}
```

---

## Environment Variables

Create `.env.local` for development, set these as secrets in Vercel/VPS for production:

```bash
# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>   # server-side only, never expose

# DsideOS backend (internal — never sent to browser)
DSIDEOS_BACKEND_URL=https://dsideos.divinesideai.com

# Admin invite protection
ADMIN_SECRET=<strong-random-string>
```

---

## Deployment

### Option A — Vercel (recommended, zero config)

```bash
npx create-next-app@latest dsideos-console --typescript --tailwind --app
cd dsideos-console
# implement the above
vercel deploy
# set custom domain: console.dsideos.divinesideai.com in Vercel dashboard
```

DNS: Add CNAME `console` → `cname.vercel-dns.com` in your domain registrar.

### Option B — Same Hetzner VPS as DsideOS

Add to `docker-compose.prod.yml`:
```yaml
console:
  image: ghcr.io/divineside/dsideos-console:latest
  restart: unless-stopped
  env_file: .env.console
  expose:
    - "3000"
```

Add to `Caddyfile`:
```
console.dsideos.divinesideai.com {
  reverse_proxy console:3000
}
```

---

## Implementation Order

Do these in order — each unlocks the next:

1. **Supabase setup** — create project, run the two SQL tables, enable Google OAuth provider
2. **Google Cloud Console** — create OAuth credentials, add redirect URI
3. **Next.js project** — scaffold, install `@supabase/ssr`, implement auth files above
4. **Landing page** — `/` with SignInButton, error state handling
5. **Auth callback** — `/auth/callback/route.ts`, test full Google sign-in flow
6. **Middleware** — protect `/dashboard` routes, verify redirect to `/` when logged out
7. **Proxy routes** — `/api/proxy/[...path]`, test against live DsideOS backend
8. **Dashboard pages** — wire the existing UI (Full Run, Questions, Solutions, Answer Key) to use proxy routes
9. **Institute context** — `useInstitute` hook, per-client font/branding rendering
10. **Admin invite** — `POST /api/admin/invite`, test full invite → login flow end-to-end
11. **Deploy** — Vercel or Hetzner, set env vars, point DNS

---

## Notes for Mayank

- The DsideOS backend (`dsideos.divinesideai.com/api/...`) does not need to change — the console proxies through Next.js API routes, so the backend stays internal.
- The `institute_members` table is the access control list. To give someone access: insert a row with their Gmail. To revoke: delete the row (they get kicked on next session refresh).
- `SUPABASE_SERVICE_ROLE_KEY` bypasses RLS — only use it in server-side code, never in the browser.
- The `ADMIN_SECRET` for the invite endpoint should be a strong random string. Store it only in env vars, never in code.
- Font per institute: the DsideOS backend already supports `font: "unicode" | "krutidev"` in the build request meta. The console should read `institute.font` and pass it through to every `/api/build` call automatically — the owner never has to think about it.
