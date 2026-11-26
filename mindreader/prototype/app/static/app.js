"use strict";

const $ = (id) => document.getElementById(id);
const SCREENS = ["start", "question", "guess", "won", "lost"];
const STORE_KEY = "mindreader.game";
let game = null;
let busy = false;
let chosen = null;          // {id, name} picked from suggestions, or null for a new name

function store(id) {
  try { id ? localStorage.setItem(STORE_KEY, id) : localStorage.removeItem(STORE_KEY); } catch (_) {}
}
function stored() {
  try { return localStorage.getItem(STORE_KEY); } catch (_) { return null; }
}

async function api(path, body) {
  const opts = body === undefined ? {} : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  };
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = typeof data.detail === "string" ? data.detail : "Something went wrong. Please try again.";
    throw Object.assign(new Error(msg), { status: res.status });
  }
  return data;
}

function show(name) {
  for (const s of SCREENS) $("screen-" + s).hidden = s !== name;
}
function error(msg) {
  $("error").textContent = msg || "";
  $("error").hidden = !msg;
}
function thinking(on) {
  busy = on;
  $("orb").classList.toggle("thinking", on);
  document.querySelectorAll(".answers .btn, #btn-right, #btn-wrong").forEach((b) => (b.disabled = on));
}

async function run(fn) {
  if (busy) return;
  error("");
  thinking(true);
  try { await fn(); }
  catch (e) {
    if (e.status === 404) { store(null); show("start"); }
    error(e.message);
  }
  finally { thinking(false); }
}

function render(g) {
  game = g;
  store(["asking", "guessing"].includes(g.status) ? g.game_id : null);
  if (g.status === "asking") {
    $("q-step").textContent = "Question " + g.step;
    $("q-text").textContent = g.question.text;
    const pct = Math.round((g.confidence || 0) * 100);
    $("conf-text").textContent = pct + "%";
    $("conf-fill").style.width = pct + "%";
    $("btn-undo").disabled = !g.can_undo;
    show("question");
  } else if (g.status === "guessing") {
    $("g-step").textContent = `Guess ${g.wrong_guesses + 1} of ${g.max_guesses}`;
    $("g-name").textContent = g.guess.name;
    $("g-desc").textContent = g.guess.description || "";
    show("guess");
  } else if (g.status === "won") {
    $("won-text").textContent = `I guessed ${g.answer_entity.name} in ${g.step} questions. Want to try to beat me?`;
    show("won");
    loadStats();
  } else if (g.status === "lost") {
    resetTeach(!g.can_teach);
    show("lost");
    if (g.can_teach) $("teach-input").focus();
  }
}

const start = () => run(async () => render(await api("/api/games", {})));
const answer = (a) => game && game.status === "asking" &&
  run(async () => render(await api(`/api/games/${game.game_id}/answer`, { question_id: game.question.id, answer: a })));
const respond = (correct) => run(async () => render(await api(`/api/games/${game.game_id}/guess`, { correct })));
const undo = () => run(async () => render(await api(`/api/games/${game.game_id}/undo`, {})));

// ---------- teaching after a loss
function resetTeach(done) {
  chosen = null;
  $("teach-input").value = "";
  $("teach-desc").value = "";
  $("suggestions").innerHTML = "";
  $("new-char").hidden = true;
  $("btn-teach").disabled = true;
  $("teach-box").hidden = done;
  $("teach-done").hidden = !done;
  if (done) $("teach-msg").textContent = "Thanks for playing!";
}

let searchTimer = null;
$("teach-input").addEventListener("input", () => {
  chosen = null;
  const q = $("teach-input").value.trim();
  $("btn-teach").disabled = q.length < 2;
  clearTimeout(searchTimer);
  searchTimer = setTimeout(async () => {
    const list = $("suggestions");
    if (q.length < 2) { list.innerHTML = ""; $("new-char").hidden = true; return; }
    let items = [];
    try { items = await api("/api/characters?search=" + encodeURIComponent(q)); } catch (_) {}
    list.innerHTML = "";
    for (const it of items) {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      const name = document.createElement("strong");
      name.textContent = it.name;
      const desc = document.createElement("span");
      desc.className = "small muted";
      desc.textContent = it.description;
      li.append(name, desc);
      li.addEventListener("click", () => {
        chosen = { id: it.id, name: it.name };
        $("teach-input").value = it.name;
        list.innerHTML = "";
        $("new-char").hidden = true;
        $("btn-teach").disabled = false;
      });
      list.appendChild(li);
    }
    const exact = items.some((it) => it.name.toLowerCase() === q.toLowerCase());
    $("new-char").hidden = exact;
  }, 200);
});

$("btn-teach").addEventListener("click", () => run(async () => {
  const typed = $("teach-input").value.trim();
  const body = chosen && chosen.name === typed
    ? { entity_id: chosen.id }
    : { name: typed, description: $("teach-desc").value.trim() || null };
  const res = await api(`/api/games/${game.game_id}/teach`, body);
  $("teach-box").hidden = true;
  $("teach-done").hidden = false;
  $("teach-msg").textContent = res.message;
  loadStats();
}));

// ---------- wiring
$("btn-start").addEventListener("click", start);
document.querySelectorAll(".ans").forEach((b) => b.addEventListener("click", () => answer(b.dataset.answer)));
document.querySelectorAll("[data-action=restart]").forEach((b) => b.addEventListener("click", start));
$("btn-right").addEventListener("click", () => respond(true));
$("btn-wrong").addEventListener("click", () => respond(false));
$("btn-undo").addEventListener("click", undo);
$("btn-undo-guess").addEventListener("click", undo);
$("btn-quit").addEventListener("click", () => { store(null); show("start"); loadStats(); });

const KEYS = { "1": "yes", "2": "no", "3": "dont_know", "4": "probably", "5": "probably_not" };
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.metaKey || e.ctrlKey || e.altKey) return;
  if (!$("screen-question").hidden && KEYS[e.key]) answer(KEYS[e.key]);
});

async function loadStats() {
  try {
    const s = await api("/api/stats");
    let t = `I know ${s.characters} characters and ${s.questions} questions.`;
    if (s.games_finished) t += ` I have won ${Math.round(s.win_rate * 100)}% of ${s.games_finished} games.`;
    $("stats").textContent = t;
  } catch (_) {}
}

(async function boot() {
  loadStats();
  const id = stored();
  if (!id) return;
  try {
    const g = await api("/api/games/" + id);
    if (["asking", "guessing"].includes(g.status)) render(g);
  } catch (_) { store(null); }
})();
