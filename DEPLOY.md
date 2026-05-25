# FeasFlow — Streamlit Cloud Deploy Guide

Deploy the feasibility studio as a web app accessible from any browser
(Chrome / Edge / Safari / mobile) — **no installation needed for end users**.

---

## ✅ Test locally first

```bash
cd "C:\Users\Alongkorn\Desktop\Project PP feasibility"
pip install -r requirements.txt
streamlit run feas_streamlit.py
```

Streamlit will open `http://localhost:8501` in your default browser.
If it works locally, it'll work in the cloud.

---

## 🚀 Deploy to Streamlit Cloud (FREE)

### Step 1 — Create a GitHub repo

1. Sign in to [github.com](https://github.com) (free account)
2. Click **New repository** (green button)
3. Repo name: `feasflow` (or anything)
4. Visibility: **Private** is fine (Streamlit Cloud supports private repos)
5. Don't add README / .gitignore / license yet — we'll push existing code
6. Click **Create repository**

### Step 2 — Push your project to GitHub

Open a terminal in the project folder:

```bash
cd "C:\Users\Alongkorn\Desktop\Project PP feasibility"

# Initialize git
git init
git branch -M main

# Create .gitignore to exclude junk
echo "__pycache__/" > .gitignore
echo "*.pyc" >> .gitignore
echo ".DS_Store" >> .gitignore
echo "report_*.xlsx" >> .gitignore
echo "report_*.pdf" >> .gitignore

# Stage + commit
git add .
git commit -m "Initial FeasFlow commit"

# Connect to GitHub (replace YOUR_USERNAME and YOUR_REPO)
git remote add origin https://github.com/YOUR_USERNAME/feasflow.git
git push -u origin main
```

> First push may ask for GitHub login — use a **Personal Access Token** instead
> of password (Settings → Developer settings → Personal access tokens → Generate)

### Step 3 — Deploy on Streamlit Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)**
2. Click **Sign in with GitHub** — authorize access
3. Click **Create app** → **Deploy a public app from GitHub**
4. Fill in:
   - **Repository**: `YOUR_USERNAME/feasflow`
   - **Branch**: `main`
   - **Main file path**: `feas_streamlit.py`
   - **App URL** (optional): pick a custom subdomain like `feasflow.streamlit.app`
5. Click **Deploy**

Wait ~2-3 minutes for the first build. Streamlit installs from `requirements.txt`
automatically.

### Step 4 — Share the URL

You'll get a URL like:

```
https://feasflow.streamlit.app
```

Send that URL to anyone — they open it in Chrome / Edge / Safari / mobile browser
and use the app immediately. **No Python, no install, no setup.**

---

## 🔄 Updating the app

When you change code locally and want to deploy the update:

```bash
cd "C:\Users\Alongkorn\Desktop\Project PP feasibility"
git add .
git commit -m "Update <description>"
git push
```

Streamlit Cloud auto-rebuilds within ~30 seconds. The live URL stays the same.

---

## 💰 Costs

- **Streamlit Cloud (community tier)**: FREE
  - 1 private app or unlimited public apps
  - Up to 1 GB resource per app
  - Sleeps after 7 days of inactivity (wakes up on visit, ~30 sec cold start)
- **GitHub (free tier)**: FREE for unlimited private repos
- **Total monthly cost**: **0 baht**

If you need more (e.g., always-on, more RAM, custom domain), Streamlit Teams
starts at ~$250/month. But the free tier is more than enough for sharing
feasibility studies with stakeholders.

---

## 🐛 Troubleshooting

### "Module not found" error after deploy
→ Make sure all imports are listed in `requirements.txt`.

### App won't start, stuck on "loading"
→ Click **Manage app** (bottom right of the deployed page) → see logs.
   Usually a syntax error or missing dependency.

### Slow first load
→ Free tier "wakes up" the container on first visit. After warm-up,
   subsequent visits are instant.

### Want to keep it private (only specific users)?
→ Streamlit Teams plan supports auth. For free tier, you can:
   - Add a simple password check using `st.secrets["password"]`
   - Or use Streamlit Cloud's "View access" → invite specific GitHub accounts

### Want a custom domain (e.g., feasflow.yourcompany.com)?
→ Streamlit Teams plan only. On free tier, you can use the `.streamlit.app` subdomain.

---

## 📁 Files in this deploy package

| File | Purpose |
|---|---|
| `feas_streamlit.py` | Streamlit web entry point |
| `engines/` | 5 plant-type engine modules (RDF / WTE / RDF+WTE / Biogas / Solar) |
| `solar_generation_engine.py` | Solar PVWatts pure-logic module |
| `feas_excel.py` | Excel report generator (used by Download button) |
| `feas_pdf.py` | PDF report generator (used by Download button) |
| `requirements.txt` | Python dependencies for Streamlit Cloud |
| `.streamlit/config.toml` | Theme + page config (green accent, light bg) |
| `feas_theme.py`, `feas_main.py` | Tkinter desktop version (not used on web — can keep or delete) |
