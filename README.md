# TPZ Daily Ads Digest — Web App

A hosted dashboard that pulls data from Meta Ads, Google Ads, and Shopify, analyzes it with Claude AI, and delivers a daily performance digest via email and a web dashboard.

## What You Get

- **Web Dashboard** — view your latest reports in the browser anytime
- **Daily Email** — automated digest delivered to your inbox every morning
- **AI Analysis** — Claude AI identifies trends, anomalies, and opportunities
- **Source of Truth** — uses Shopify revenue (not platform-reported) for real ROAS
- **Settings UI** — enter and update your API credentials through the web interface (no terminal needed)

## Deploy in 5 Minutes

### Option A: Railway (Recommended)

1. **Create a GitHub account** if you don't have one → [github.com](https://github.com)

2. **Upload this project to GitHub:**
   - Go to [github.com/new](https://github.com/new)
   - Name the repo `ads-digest` and set it to **Private**
   - Click "Create repository"
   - Upload all the files from this project (drag and drop works)

3. **Deploy on Railway:**
   - Go to [railway.com](https://railway.com) and sign in with GitHub
   - Click **"New Project"** → **"Deploy from GitHub Repo"**
   - Select your `ads-digest` repo
   - Railway will auto-detect the config and start deploying

4. **Set a dashboard password:**
   - In Railway, go to your project → **Variables** tab
   - Add: `DASHBOARD_PASSWORD` = (pick a password you'll remember)
   - Add: `FLASK_SECRET_KEY` = (any random string, like mash your keyboard)

5. **Open your app:**
   - Railway gives you a URL like `ads-digest-production.up.railway.app`
   - Open it → log in → go to Settings → enter your API credentials
   - Click "Test Run" to send your first sample report

**Cost:** Railway free tier gives you $5/month in credits. This app uses about $0.50-1/month.

### Option B: Render

1. Upload the project to GitHub (same as above)
2. Go to [render.com](https://render.com) and sign in with GitHub
3. Click **"New"** → **"Web Service"** → Select your repo
4. Render auto-detects the `render.yaml` config
5. Click **Deploy**

**Cost:** Free tier available.

## How It Works

1. **Enter your credentials** in the Settings page (they're stored on the server, never exposed)
2. **Set your schedule** (default: 7 AM Mountain Time)
3. **The app runs daily**, pulling from Meta + Google Ads + Shopify
4. **Claude AI analyzes** the data and writes strategic recommendations
5. **You get an email** with the full digest + it's viewable on the dashboard

## Dashboard Features

| Page | What It Does |
|------|-------------|
| **Dashboard** | Shows latest stats, report history, "Run Now" button |
| **Settings** | Enter/update API credentials, set schedule |
| **Reports** | Click any past report to view the full HTML digest |

## Security

- Set `DASHBOARD_PASSWORD` to protect the web interface
- Credentials are stored on the server filesystem (not in the URL or code)
- The app only requests **read-only** access to your ad platforms and store
- All connections use HTTPS

## Environment Variables

Set these in Railway/Render's **Variables** panel (not in the Settings page):

| Variable | Purpose |
|----------|---------|
| `DASHBOARD_PASSWORD` | Protects the web UI (required) |
| `FLASK_SECRET_KEY` | Session encryption (any random string) |

All other credentials (Shopify, Meta, Google, etc.) are entered through the web Settings page.

## Adding More Brands Later

The app currently supports one brand. To add LOMA or other brands:
- Deploy a second instance with its own credentials
- Or contact me and I'll update the app to support multi-brand

## Troubleshooting

**App crashes on Railway:**
→ Check the logs in Railway's **Deployments** tab for error details

**Reports show empty data for Meta/Google:**
→ Your tokens may have expired. Update them in Settings.

**Shopify returns "shop_not_permitted":**
→ Make sure the Dev Dashboard app and your store are in the same Shopify organization

**Emails not arriving:**
→ Check spam folder. Verify the Gmail app password in Settings.
