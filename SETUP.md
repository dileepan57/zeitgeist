# Zeitgeist — Setup Guide

## What This Is

A fully automated opportunity intelligence system that:
1. Collects 20+ signals daily across 6 independent categories
2. Scores topics by genuine mindshare (not media echo)
3. Identifies gaps between demand and supply
4. Uses Claude to generate opportunity briefs
5. Self-improves via outcome tracking and signal calibration
6. Includes a collaborative build agent to scaffold apps for top opportunities

---

## Prerequisites

### Accounts to Create (all free unless noted)

| Service | Purpose | Cost | URL |
|---|---|---|---|
| GitHub | Repo + Actions cron | Free | github.com |
| Supabase | Database | Free tier | supabase.com |
| Anthropic | Claude API | ~$5-15/mo | console.anthropic.com |
| Vercel | Frontend hosting | Free | vercel.com |
| Render | API hosting | Free | render.com |
| Google Cloud | YouTube Data API | Free quota | console.cloud.google.com |
| Reddit | OAuth app | Free | reddit.com/prefs/apps |
| Adzuna | Job postings API | Free | developer.adzuna.com |
| Apple Developer | App Store (Phase 7+) | $99/yr | developer.apple.com |
| Google Play | Android (Phase 7+) | $25 one-time | play.google.com/console |
| RevenueCat | Subscriptions (Phase 10+) | Free to $2.5k MRR | revenuecat.com |

---

## Step 1: Clone & Configure

```bash
git clone https://github.com/YOUR_USERNAME/zeitgeist.git
cd zeitgeist
cp .env.example .env
# Fill in all values in .env
```

---

## Step 2: Supabase Setup

1. Create a new Supabase project at supabase.com
2. Go to SQL Editor
3. Run the contents of `supabase/migrations/001_initial_schema.sql`
4. Copy your Project URL, anon key, and service role key into `.env`

---

## Step 3: API Keys

### YouTube Data API v3
1. Go to console.cloud.google.com
2. Create new project → Enable "YouTube Data API v3"
3. Create credentials → API Key
4. Add to `.env` as `YOUTUBE_API_KEY`

### Reddit OAuth
1. Go to reddit.com/prefs/apps
2. Click "Create App" → type: "script"
3. Note the client_id (under app name) and client_secret
4. Add to `.env`

### Adzuna
1. Register at developer.adzuna.com
2. Create an app to get app_id and app_key
3. Add to `.env`

---

## Step 4: Python Environment

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

---

## Step 5: Test the Pipeline

```bash
python -m pipeline.run --dry-run
```

This runs all collectors and scoring without writing to the database.
Check that data flows through without errors.

Then run for real:
```bash
python -m pipeline.run
```

---

## Step 6: GitHub Actions Setup

1. Push repo to GitHub:
```bash
git remote add origin https://github.com/YOUR_USERNAME/zeitgeist.git
git push -u origin main
```

2. In GitHub repo → Settings → Secrets and variables → Actions
3. Add all secrets from your `.env` file

The daily pipeline will run automatically at 6 AM UTC.
To trigger manually: Actions → "Daily Pipeline" → "Run workflow"

---

## Step 7: Deploy the API (Render)

1. Connect GitHub repo to Render
2. Create new "Web Service"
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn api.main:app --host 0.0.0.0 --port $PORT`
5. Add all environment variables
6. Note your Render URL (e.g., `https://zeitgeist-api.onrender.com`)

---

## Step 8: Deploy the Dashboard (Vercel)

1. Install Node.js (nodejs.org)
2. In the `web/` directory:
```bash
cd web
npm install
npm run dev   # test locally first
```

3. Connect to Vercel:
```bash
npx vercel
```

4. Set environment variables in Vercel dashboard:
   - `NEXT_PUBLIC_API_URL` = your Render URL
   - `NEXT_PUBLIC_SUPABASE_URL` = your Supabase URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = your anon key

---

## Step 9: Set Your Build Thesis

Go to `/settings` in your dashboard and fill in:
- Who you are as a builder
- Domains you care about
- Your skills
- Past projects (so the agent doesn't recommend things you've tried)
- Domains to avoid

This is injected into every analysis — the more specific, the better.

---

## Step 10: First Run

1. Trigger the pipeline manually from GitHub Actions
2. Wait ~10-15 minutes for all collectors to run
3. Open your dashboard — you should see today's opportunities
4. Go to `/crystal-ball` — signal performance table will be empty but will fill over time
5. Go to `/session` — start chatting with the build agent

---

## Daily Workflow

**Morning:**
1. Open `/` — check today's top opportunities
2. Open `/session` — get today's build brief
3. Ask the agent what to build or continue from yesterday

**Weekly (automatic every Sunday):**
- Signal calibration runs
- Institutional knowledge brief generated
- Visible in `/crystal-ball`

**As you build:**
- Go to `/topic/[id]` and tag outcomes (REAL_MARKET, FIZZLED, etc.)
- This trains the system over time

---

## Cost Estimate

| Service | Monthly Cost |
|---|---|
| Claude API (20 topics/day × 2 calls) | ~$8-15 |
| Supabase | Free |
| Vercel | Free |
| Render | Free |
| GitHub Actions | Free |
| All APIs | Free |
| **Total** | **~$8-15/mo** |
