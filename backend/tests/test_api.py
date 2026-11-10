"""API tests: auth, words, the practice workflow, uploads, adaptation and privacy."""

from __future__ import annotations

from .conftest import wav_bytes


def upload(client, auth, word_id, session_id=None, silent=False, store=False):
    data = {"word_id": str(word_id), "store_recording": "true" if store else "false"}
    if session_id:
        data["session_id"] = session_id
    return client.post("/api/pronunciation/analyze", headers=auth, data=data,
                       files={"audio": ("rec.wav", wav_bytes(silent), "audio/wav")})


# ----------------------------------------------------------------------- auth
def test_register_login_and_me(client):
    r = client.post("/api/auth/register", json={"email": "A@Example.com", "password": "longenough"})
    assert r.status_code == 201
    assert client.post("/api/auth/register", json={"email": "a@example.com", "password": "longenough"}).status_code == 409
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "wrong-pass"}).status_code == 401
    tok = client.post("/api/auth/login", json={"email": "a@example.com", "password": "longenough"}).json()["access_token"]
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {tok}"}).json()
    assert me["email"] == "a@example.com" and me["store_recordings_consent"] is False


def test_validation_and_auth_errors(client):
    assert client.post("/api/auth/register", json={"email": "nope", "password": "longenough"}).status_code == 422
    assert client.post("/api/auth/register", json={"email": "x@y.io", "password": "short"}).status_code == 422
    assert client.get("/api/users/me").status_code == 401
    assert client.get("/api/users/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


# ---------------------------------------------------------------------- words
def test_words_endpoints(client):
    words = client.get("/api/words").json()
    assert words["total"] >= 100
    hard = client.get("/api/words", params={"difficulty": "hard"}).json()
    assert hard["total"] > 0 and all(w["difficulty"] == "hard" for w in hard["items"])
    r_words = client.get("/api/words", params={"phoneme": "r"}).json()["items"]
    assert r_words and all("r" in w["phonemes"] for w in r_words)
    detail = client.get(f"/api/words/{words['items'][0]['id']}").json()
    assert detail["variants"] and detail["evaluation_features"]
    assert client.get("/api/words/99999").status_code == 404
    phon = client.get("/api/words/phonemes").json()
    assert any(p["phoneme"] == "θ" for p in phon)
    audio = client.get(f"/api/words/{words['items'][0]['id']}/audio")
    assert audio.status_code == 200 and audio.headers["content-type"] == "audio/wav"


# ----------------------------------------------------------- practice workflow
def test_full_practice_workflow(client, auth):
    s = client.post("/api/sessions", json={"mode": "easy", "size": 3}, headers=auth).json()
    assert s["total_words"] == 3 and s["current_index"] == 0
    wid = s["words"][0]["word"]["id"]

    a = upload(client, auth, wid, s["id"])
    assert a.status_code == 200, a.text
    body = a.json()
    assert body["analysis"]["overall_score"] == 78 and body["attempt_number"] == 1

    fb = client.post("/api/feedback", json={"attempt_id": body["attempt_id"]}, headers=auth).json()
    assert fb["recommendations"][0]["issue_id"] == "ph0-substitution" and fb["source"] == "rule_based"
    # feedback is stored with the attempt
    assert client.get(f"/api/attempts/{body['attempt_id']}", headers=auth).json()["feedback"]["summary"] == fb["summary"]

    retry = upload(client, auth, wid, s["id"]).json()
    assert retry["attempt_number"] == 2

    s2 = client.post(f"/api/sessions/{s['id']}/advance", headers=auth).json()
    assert s2["current_index"] == 1 and s2["words"][0]["attempts"] == 2 and s2["words"][0]["best_score"] == 78
    for _ in range(3):
        s2 = client.post(f"/api/sessions/{s['id']}/advance", headers=auth).json()
    assert s2["status"] == "completed"

    prog = client.get("/api/users/me/progress", headers=auth).json()
    assert prog["assessed_attempts"] == 2 and prog["average_score"] == 78 and prog["total_sessions"] == 1
    assert prog["most_mispronounced"][0]["common_substitution"] == "w"
    hist = client.get("/api/attempts", headers=auth).json()
    assert hist["total"] == 2


def test_retry_required_is_saved_without_score(client, auth):
    words = client.get("/api/words", params={"limit": 1}).json()["items"]
    r = upload(client, auth, words[0]["id"], silent=True).json()
    assert r["analysis"]["status"] == "retry_required" and r["analysis"]["overall_score"] is None
    fb = client.post("/api/feedback", json={"attempt_id": r["attempt_id"]}, headers=auth).json()
    assert fb["recommendations"] == []


def test_stateless_feedback_endpoint(client, auth):
    words = client.get("/api/words", params={"limit": 1}).json()["items"]
    analysis = upload(client, auth, words[0]["id"]).json()["analysis"]
    fb = client.post("/api/feedback", json={"analysis": analysis}, headers=auth)
    assert fb.status_code == 200 and fb.json()["recommendations"]


def test_adaptive_session_prioritises_weak_sounds(client, auth):
    # practise /r/ words: the fake marks the first phoneme as poor every time
    r_words = [w for w in client.get("/api/words", params={"phoneme": "r"}).json()["items"] if w["phonemes"][0] == "r"]
    for w in r_words[:4]:
        upload(client, auth, w["id"])
    s = client.post("/api/sessions", json={"mode": "adaptive", "size": 8}, headers=auth).json()
    assert "r" in s["focus_phonemes"]
    with_r = sum("r" in item["word"]["phonemes"] for item in s["words"])
    assert with_r >= 4  # most planned words contain the weak sound


def test_phoneme_and_missed_modes(client, auth):
    s = client.post("/api/sessions", json={"mode": "phoneme", "phoneme": "θ", "size": 5}, headers=auth).json()
    assert all("θ" in w["word"]["phonemes"] for w in s["words"])
    bad = client.post("/api/sessions", json={"mode": "phoneme", "phoneme": "x", "size": 5}, headers=auth)
    assert bad.status_code == 422
    assert client.post("/api/sessions", json={"mode": "missed", "size": 5}, headers=auth).status_code == 201


# -------------------------------------------------------------------- uploads
def test_upload_validation(client, auth):
    words = client.get("/api/words", params={"limit": 2}).json()["items"]
    bad_type = client.post("/api/pronunciation/analyze", headers=auth, data={"word_id": words[0]["id"]},
                           files={"audio": ("x.txt", b"hello" * 20, "text/plain")})
    assert bad_type.status_code == 415
    fake_wav = client.post("/api/pronunciation/analyze", headers=auth, data={"word_id": words[0]["id"]},
                           files={"audio": ("x.wav", b"not really audio" * 10, "audio/wav")})
    assert fake_wav.status_code == 415
    too_big = client.post("/api/pronunciation/analyze", headers=auth, data={"word_id": words[0]["id"]},
                          files={"audio": ("x.wav", b"RIFF" + b"\0" * 2_100_000, "audio/wav")})
    assert too_big.status_code == 413
    s = client.post("/api/sessions", json={"mode": "easy", "size": 3}, headers=auth).json()
    other = next(w for w in client.get("/api/words", params={"difficulty": "hard"}).json()["items"])
    assert upload(client, auth, other["id"], s["id"]).status_code == 422
    assert client.post("/api/pronunciation/analyze", data={"word_id": "1"},
                       files={"audio": ("x.wav", wav_bytes(), "audio/wav")}).status_code == 401


# -------------------------------------------------------------------- privacy
def test_recordings_require_consent_and_can_be_deleted(client, auth):
    wid = client.get("/api/words", params={"limit": 1}).json()["items"][0]["id"]
    a1 = upload(client, auth, wid, store=True).json()
    assert a1["has_recording"] is False  # no consent yet
    client.patch("/api/users/me", json={"store_recordings_consent": True}, headers=auth)
    a2 = upload(client, auth, wid, store=True).json()
    assert a2["has_recording"] is True
    rec = client.get(f"/api/attempts/{a2['attempt_id']}/recording", headers=auth)
    assert rec.status_code == 200 and rec.content.startswith(b"RIFF")
    assert client.delete("/api/users/me/recordings", headers=auth).json()["deleted"] == 1
    assert client.get(f"/api/attempts/{a2['attempt_id']}/recording", headers=auth).status_code == 404


def test_other_users_cannot_read_attempts(client, auth):
    wid = client.get("/api/words", params={"limit": 1}).json()["items"][0]["id"]
    a = upload(client, auth, wid).json()
    other = client.post("/api/auth/register", json={"email": "intruder@example.com", "password": "longenough"})
    h2 = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(f"/api/attempts/{a['attempt_id']}", headers=h2).status_code == 404
    assert client.post("/api/feedback", json={"attempt_id": a["attempt_id"]}, headers=h2).status_code == 404


def test_delete_data_and_account(client, auth):
    wid = client.get("/api/words", params={"limit": 1}).json()["items"][0]["id"]
    upload(client, auth, wid)
    export = client.get("/api/users/me/export", headers=auth).json()
    assert export["attempts"]
    assert client.delete("/api/users/me/data", headers=auth).status_code == 204
    assert client.get("/api/users/me/progress", headers=auth).json()["total_attempts"] == 0
    assert client.delete("/api/users/me", headers=auth).status_code == 204
    assert client.get("/api/users/me", headers=auth).status_code == 401


def test_system_status_and_openapi(client):
    st = client.get("/api/system/status").json()
    assert st["status"] == "ok" and st["words"] >= 100 and st["feedback"]["mode"] == "rule_based"
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/api/words", "/api/words/{word_id}", "/api/pronunciation/analyze", "/api/feedback", "/api/sessions",
              "/api/sessions/{session_id}", "/api/users/me/progress"]:
        assert p in paths
