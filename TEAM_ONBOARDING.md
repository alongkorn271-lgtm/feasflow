# FeasFlow — Team onboarding & migration guide

How to bring the FeasFlow project into a Claude Team so the whole team can work
on it with Claude. Backbone = **GitHub repo + `CLAUDE.md`**; a Claude Project on
claude.ai is optional for non-coding discussion.

Repo: https://github.com/alongkorn271-lgtm/feasflow

---

## Step 1 — Give the team access to the code (GitHub)

Pick ONE (start with A; do B later if you outgrow it):

**A. Add collaborators (simplest, recommended now)**
1. GitHub → repo **feasflow** → *Settings → Collaborators* → *Add people*
2. Enter each teammate's GitHub username → choose role
   (*Write* = can push, *Read* = view only) → they accept the email invite.

**B. Move to an organization (later, for a larger team)**
1. Create a GitHub Organization (Team plan) and add members.
2. Repo → *Settings → General → Transfer ownership* → transfer to the org.
3. Set team permissions in the org. (The URL/remote changes — everyone re-clones
   or runs `git remote set-url origin <new-url>`.)

## Step 2 — Each teammate sets up locally
```bash
git clone https://github.com/alongkorn271-lgtm/feasflow.git
cd feasflow
python -m venv .venv && .venv\Scripts\activate    # Windows
pip install -r requirements.txt
python feas_main.py          # desktop, or:  streamlit run feas_streamlit.py
```
Requires Python 3.11+.

## Step 3 — Use Claude Code with shared context
`CLAUDE.md` is committed at the repo root, so **every teammate's Claude Code loads
the same project context automatically** (architecture, how to run, the engine
contract, conventions). Nothing to configure — just open the folder in Claude Code.

House rules already baked into `CLAUDE.md`: keep the common output schema, keep
`audit_correctness.py` at 59/59, don't commit build artifacts, don't push without
being asked.

## Step 4 (optional) — Claude Project on claude.ai for discussion
For teammates who want to ask about the model **without opening the code**:
1. claude.ai (Team workspace) → *Projects* → *Create project* → share with the team.
2. Add custom instructions: *"You are helping with FeasFlow, a multi-engine power-
   plant feasibility model. Answer from the attached docs."*
3. Upload as project knowledge (docs only — not the whole codebase):
   - `README.md`
   - `CLAUDE.md`
   - `FLOWCHARTS.md`
   - `IMPROVEMENTS.md`
   - `CORRECTNESS_AUDIT.md`
   - `METRICS.md`
   - (optional) `docs/gui-overview.png`, `gui-charts.png`, `gui-biogas.png`

> Code work happens in Claude Code on the cloned repo; the Claude Project is only
> a shared knowledge base for questions and planning.

---

## Files already prepared in the repo
| File | Purpose |
|---|---|
| `CLAUDE.md` | project context for Claude Code (auto-loaded) |
| `README.md` | overview + screenshots + how to run |
| `FLOWCHARTS.md` | per-engine technical + financial diagrams |
| `IMPROVEMENTS.md` | engine refinement notes |
| `CORRECTNESS_AUDIT.md` | methodology verification (59 checks) |
| `METRICS.md` | every KPI explained: formula, discount rate, colour bands, where shown |
| `requirements.txt` · `.gitignore` · `.streamlit/config.toml` | env / deploy config |
| `FeasFlow.spec` · `build_installer.bat` · `FeasFlow_installer.iss` | Windows packaging |

## Migration checklist
- [ ] Add teammates as GitHub collaborators (Step 1A)
- [ ] Everyone clones + `pip install -r requirements.txt` + runs the app (Step 2)
- [ ] Confirm `CLAUDE.md` loads in each teammate's Claude Code (Step 3)
- [ ] (optional) Create the Claude Project and upload the docs (Step 4)
- [ ] Agree on a branch/PR workflow (e.g. feature branches → PR → review → merge)
- [ ] Decide who holds the code-signing cert / release build (installer)

---
*Prepared for the FeasFlow team · © 2026 Alongkorn Chanta*
