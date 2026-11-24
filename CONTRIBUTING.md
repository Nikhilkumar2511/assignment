# Working on FINPULSE AI as a team

## Get access

The repository owner adds each teammate once:
**Settings → Collaborators → Add people**, then the teammate accepts the email invitation.

## The routine for every change

1. Get the latest code: `git checkout main && git pull`
2. Make a branch named for the change: `git checkout -b student-weekly-view`
3. Make the change.
4. Run the tests: `cd finpulse && python3 -m pytest -q`
5. If you touched anything under `finpulse/site/`, rebuild the website: `python3 site/build.py`
6. Commit, push, and open a pull request into `main`.
7. Ask one teammate to read it before it is merged.

Do not push straight to `main`. A pull request is where mistakes get caught.

## Rules that protect the project

These come from the course brief and from how the product is built. A pull request that breaks
one should not be merged.

- **No real personal or company data.** Sample data must be synthetic. Never commit a real
  person's spending, a real company's accounts, a name, a phone number or an ID.
- **No secrets.** Never commit an API key or a password. Keys belong in environment variables.
- **Every figure must come from the code.** If you change a number in a README, the blueprint
  section or the website text, it has to match what the engine or the test output produces.
  Do not type in a figure you did not run.
- **No accuracy claims about real users.** The model was trained and tested on synthetic
  students only. Say so wherever its results are quoted.
- **No investment recommendations.** The product explains, compares and shows scenarios. It
  must never name a share, fund or scheme to buy, and never promise a return.
- **Keep the limits visible.** Do not remove the "sample data", "not financial advice" or
  "Limits" text from the website or the READMEs.
- **Change the two engines together.** The website runs `finpulse/site/finpulse-engine.js`,
  a port of the Python in `finpulse/finpulse_engine/`. `tests/test_js_parity.py` fails if they
  disagree. If you change a calculation, change both and keep that test green.
- **Do not edit `docs/index.html` by hand.** It is generated. Edit `finpulse/site/page.html`
  or `finpulse/site/finpulse-engine.js`, then run `python3 site/build.py`.
- **Do not weaken a test to make it pass.** If a test fails, the change is wrong or the test
  needs a reasoned update that the pull request explains.

## Your AI Integrity Log

The course grades how you used AI. Each time you use an AI tool on this project, note what you
asked, what it got wrong, how you caught it, and what you decided yourself. Much of the first
version of this code was AI-built under Stage 3 of the brief, and the log should say so.

## What the automatic check does

Every pull request runs the full test suite and confirms that `docs/index.html` matches its
sources. A red cross on a pull request means one of those failed. Open the check to see which.
