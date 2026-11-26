"""End-to-end API tests: play, win, lose, teach, undo, admin."""
from app.main import kb_store

ADMIN = {"Authorization": "Bearer test-admin-token"}


def answer_as(client, game, name):
    """Answer every question the way a player thinking of `name` would, until the game guesses."""
    kb = kb_store.get()
    row = kb.entity_names.index(name)
    for _ in range(80):
        if game["status"] != "asking":
            return game
        p = kb.P[row, kb.qidx[game["question"]["id"]]]
        ans = "yes" if p > 0.6 else "no" if p < 0.4 else "dont_know"
        r = client.post(f"/api/games/{game['game_id']}/answer", json={"question_id": game["question"]["id"], "answer": ans})
        assert r.status_code == 200, r.text
        game = r.json()
    return game


def test_home_and_stats(client):
    assert client.get("/").status_code == 200
    s = client.get("/api/stats").json()
    assert s["characters"] >= 240 and s["questions"] >= 100
    assert client.get("/healthz").json()["ok"]


def test_win_and_learn(client):
    g = client.post("/api/games").json()
    assert g["status"] == "asking" and g["question"]["text"]
    g = answer_as(client, g, "Virat Kohli")
    assert g["status"] == "guessing" and g["guess"]["name"] == "Virat Kohli"
    version = client.get("/healthz").json()["kb_version"]
    g = client.post(f"/api/games/{g['game_id']}/guess", json={"correct": True}).json()
    assert g["status"] == "won" and g["answer_entity"]["name"] == "Virat Kohli"
    kb_store.invalidate()
    assert client.get("/healthz").json()["kb_version"] > version
    assert client.get("/api/stats").json()["games_won"] >= 1


def test_double_submit_is_harmless(client):
    g = client.post("/api/games").json()
    body = {"question_id": g["question"]["id"], "answer": "yes"}
    first = client.post(f"/api/games/{g['game_id']}/answer", json=body)
    second = client.post(f"/api/games/{g['game_id']}/answer", json=body)
    assert first.status_code == second.status_code == 200
    assert first.json()["step"] == second.json()["step"]


def test_undo(client):
    g = client.post("/api/games").json()
    q1 = g["question"]["id"]
    client.post(f"/api/games/{g['game_id']}/answer", json={"question_id": q1, "answer": "no"})
    g = client.post(f"/api/games/{g['game_id']}/undo").json()
    assert g["question"]["id"] == q1 and g["step"] == 1


def lose(client):
    r = client.post("/api/games")
    assert r.status_code == 201, r.text
    g = r.json()
    while g["status"] != "lost":
        if g["status"] == "asking":
            g = client.post(f"/api/games/{g['game_id']}/answer",
                            json={"question_id": g["question"]["id"], "answer": "dont_know"}).json()
        else:
            g = client.post(f"/api/games/{g['game_id']}/guess", json={"correct": False}).json()
    assert g["can_teach"]
    return g


def test_teach_existing_character(client):
    g = lose(client)
    hit = client.get("/api/characters", params={"search": "sherlock"}).json()
    assert hit and hit[0]["name"] == "Sherlock Holmes"
    r = client.post(f"/api/games/{g['game_id']}/teach", json={"entity_id": hit[0]["id"]})
    assert r.status_code == 200 and not r.json()["created"]
    again = client.post(f"/api/games/{g['game_id']}/teach", json={"entity_id": hit[0]["id"]})
    assert again.status_code == 400


def test_teach_new_character_goes_live_after_two_players(client):
    for i in range(2):
        g = lose(client)
        r = client.post(f"/api/games/{g['game_id']}/teach",
                        json={"name": "Detective Conan", "description": "Boy detective from a Japanese anime"}).json()
        assert r["entity"]["status"] == ("pending" if i == 0 else "active")
    kb_store.invalidate()
    assert "Detective Conan" in kb_store.get().entity_names


def test_bad_names_rejected(client):
    for bad in ["x", "visit www.spam.example", "12345", "<script>"]:
        g = lose(client)
        r = client.post(f"/api/games/{g['game_id']}/teach", json={"name": bad})
        assert r.status_code == 400, bad


def test_cannot_teach_unfinished_game(client):
    g = client.post("/api/games").json()
    r = client.post(f"/api/games/{g['game_id']}/teach", json={"name": "Someone New"})
    assert r.status_code == 400


def test_admin_requires_token(client):
    assert client.get("/api/admin/pending").status_code == 401
    assert client.get("/api/admin/pending", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/admin/pending", headers=ADMIN).status_code == 200


def test_admin_hide_character(client):
    hit = client.get("/api/characters", params={"search": "pac man"}).json()[0]
    r = client.post(f"/api/admin/entities/{hit['id']}/hide", headers=ADMIN)
    assert r.json()["status"] == "hidden"
    assert client.get("/api/characters", params={"search": "pac man"}).json() == []
    client.post(f"/api/admin/entities/{hit['id']}/unhide", headers=ADMIN)


def test_unknown_game_404(client):
    assert client.get("/api/games/does-not-exist").status_code == 404
