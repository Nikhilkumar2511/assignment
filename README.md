# FINPULSE AI

Financial health diagnosis for small businesses, and budget diagnosis for students. A team
project for the "AI Systems & Data for Decision-Makers" course.

## What is in this repository

| Folder | What it holds |
|---|---|
| `docs/` | The website. One self-contained page that runs in any browser with no server. |
| `finpulse/` | The engines (Python and JavaScript), the trained early-warning model, the API and the tests. |
| `campus_launch/` | Stress tests of the earlier snack-box idea. Kept for reference. |

## See the website

Open `docs/index.html` in a browser. Nothing needs to be installed, and nothing you type is
sent anywhere.

To put it on a public address, the repository owner turns on GitHub Pages once:
**Settings → Pages → Build and deployment → Deploy from a branch → `main` and `/docs` → Save.**
A minute later the site is at `https://nikhilkumar2511.github.io/assignment/`.

## Work on it

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. In short: make a branch, change the code, run
the tests, open a pull request.

```bash
cd finpulse
pip install -r requirements.txt
python3 -m pytest -q        # 30 tests, including the Python-versus-website comparison
python3 site/build.py       # rebuilds docs/index.html after any change under finpulse/site/
```

Everything in this repository uses synthetic sample data. Details, limits and the model's
test results are in [finpulse/README.md](finpulse/README.md).
