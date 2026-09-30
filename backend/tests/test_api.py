"""API tests: role separation, the non-skippable gates, and the clerk -> registrar flow."""

import pytest
from sqlalchemy import select

from app import services
from app.db import SessionLocal
from app.models import ModelRun


def first_pending(client, auth, **params):
    r = client.get("/api/cases", params={"limit": 1, **params}, headers=auth("registrar"))
    assert r.status_code == 200, r.text
    return r.json()["items"][0]


# --- auth & roles -----------------------------------------------------------

def test_login_rejects_bad_password(client):
    assert client.post("/api/auth/login", data={"username": "clerk", "password": "nope"}).status_code == 401


def test_requires_token(client):
    assert client.get("/api/cases").status_code == 401


@pytest.mark.parametrize("user,method,path,body", [
    ("clerk", "post", "/api/cycles/W2026-09-28/decisions", {"case_id": "x", "action": "approve"}),
    ("clerk", "post", "/api/cases/x/risk-review", {"action": "approve"}),
    ("registrar", "post", "/api/cases/x/hearings", {"hearing_date": "2026-09-25", "outcome": "proceeded"}),
    ("magistrate", "get", "/api/cases", None),
    ("registrar", "put", "/api/settings", {"escalation_cycles": 2}),
    ("registrar", "post", "/api/model/train", None),
    ("clerk", "get", "/api/fairness", None),
])
def test_separation_of_duties(client, auth, user, method, path, body):
    r = getattr(client, method)(path, headers=auth(user), **({"json": body} if body is not None else {}))
    assert r.status_code == 403, r.text


# --- clerk data entry (FR-11) & re-scoring (FR-2) -----------------------------

def test_clerk_records_hearing_and_case_is_rescored(client, auth):
    case = first_pending(client, auth, controllable=True, sort="id", order="asc")
    before = case["risk"]
    r = client.post(f"/api/cases/{case['id']}/hearings", headers=auth("clerk"), json={
        "hearing_date": "2026-09-25", "outcome": "adjourned", "adjournment_reason": "forensic"})
    assert r.status_code == 201, r.text
    after = r.json()["rescored_risk"]
    assert after["scored_at"] != before["scored_at"]
    assert after["court_controllable"] is False
    assert "forensic" in after["delay_status"].lower()

    detail = client.get(f"/api/cases/{case['id']}", headers=auth("registrar")).json()
    assert detail["hearings"][0]["recorded_by"] == "Court Clerk (demo)"
    assert detail["active_flags"]["flag_forensic"] is True


@pytest.mark.parametrize("body,msg", [
    ({"hearing_date": "2026-09-25", "outcome": "adjourned"}, "reason"),
    ({"hearing_date": "2027-01-01", "outcome": "proceeded"}, "future"),
    ({"hearing_date": "1990-01-01", "outcome": "proceeded"}, "before"),
])
def test_hearing_validation(client, auth, body, msg):
    case = first_pending(client, auth, sort="id", order="desc")
    r = client.post(f"/api/cases/{case['id']}/hearings", headers=auth("clerk"), json=body)
    assert r.status_code == 400 and msg in r.json()["detail"].lower()


def test_clerk_registers_case_and_it_is_scored_at_filing(client, auth):
    ref = client.get("/api/reference", headers=auth("clerk")).json()
    mags = client.get("/api/magistrates", headers=auth("admin")).json()
    m = next(x for x in mags if x["court_level"] == "District")
    r = client.post("/api/cases", headers=auth("clerk"), json={
        "case_type": "Land", "court_level": "District", "court_station": m["court_station"],
        "n_parties": 3, "represented": True, "filing_date": "2026-09-20"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["risk"] is not None and body["risk"]["category"] in {"Low", "Medium", "High"}
    assert body["region"] == ref["station_region"][m["court_station"]]


# --- registrar review (FR-6) ----------------------------------------------------

def test_cause_list_workflow(client, auth):
    cyc = client.get("/api/review-queue", headers=auth("registrar")).json()["open_cycle"]
    assert cyc
    detail = client.get(f"/api/cycles/{cyc}", headers=auth("registrar")).json()
    items = detail["items"]
    a, b, c = items[0], items[1], items[2]

    # Only one open cause list at a time.
    assert client.post("/api/cycles", headers=auth("registrar"), json={}).status_code == 409

    url = f"/api/cycles/{cyc}/decisions"
    h = auth("registrar")
    assert client.post(url, headers=h, json={"case_id": b["case_id"], "action": "edit", "day": "Fri"}).status_code == 400
    assert client.post(url, headers=h, json={"case_id": a["case_id"], "action": "approve"}).status_code == 201
    assert client.post(url, headers=h, json={"case_id": b["case_id"], "action": "edit", "day": "Fri",
                                             "reason": "Advocate on circuit"}).status_code == 201
    assert client.post(url, headers=h, json={"case_id": c["case_id"], "action": "remove",
                                             "reason": "Accused not produced"}).status_code == 201
    wrong_mag = next(m for key, ms in detail["magistrate_options"].items() for m in ms
                     if m["id"] != a["magistrate_id"] and key.split("|")[0] != a["court_station"])
    assert client.post(url, headers=h, json={"case_id": a["case_id"], "action": "edit",
                                             "magistrate_id": wrong_mag["id"], "reason": "x"}).status_code == 400

    out = client.post(f"/api/cycles/{cyc}/finalise", headers=h).json()
    assert out["approved_listings"] == 2  # nothing undecided is scheduled
    assert client.post(url, headers=h, json={"case_id": a["case_id"], "action": "approve"}).status_code == 409

    sched = client.get("/api/my-schedule", headers=auth("registrar"),
                       params={"magistrate_id": b["magistrate_id"]}).json()
    listed = {r["case_id"]: r for w in sched["weeks"] if w["cycle_id"] == cyc for r in w["listings"]}
    assert listed[b["case_id"]]["day"] == "Fri"
    assert c["case_id"] not in listed


def test_magistrate_sees_only_own_schedule(client, auth):
    r = client.get("/api/my-schedule", headers=auth("magistrate"), params={"magistrate_id": "someone-else"})
    assert r.status_code == 200
    me = client.get("/api/auth/me", headers=auth("magistrate")).json()
    assert r.json()["magistrate"]["id"] == me["magistrate_id"]


def test_risk_override_needs_reason_and_takes_effect(client, auth):
    case = first_pending(client, auth, risk="Low")
    url = f"/api/cases/{case['id']}/risk-review"
    h = auth("registrar")
    assert client.post(url, headers=h, json={"action": "override", "category": "High"}).status_code == 400
    r = client.post(url, headers=h, json={"action": "override", "category": "High",
                                          "reason": "Accused in remand for 2 years"})
    assert r.status_code == 200 and r.json()["category"] == "High"
    detail = client.get(f"/api/cases/{case['id']}", headers=h).json()
    assert detail["risk"]["category"] == "High" and detail["risk"]["model_category"] == "Low"
    assert detail["decisions"][0]["action"] == "override_risk"


# --- fairness gate (FR-4) --------------------------------------------------------

def test_failed_fairness_gate_blocks_scheduling(client, auth):
    db = SessionLocal()
    run = db.scalars(select(ModelRun).order_by(ModelRun.id.desc())).first()
    run.audit_passed = False
    db.commit()
    try:
        r = client.post("/api/cycles", headers=auth("registrar"), json={"week_start": "2026-10-05"})
        assert r.status_code == 409 and "fairness" in r.json()["detail"].lower()
        assert client.get("/api/fairness", headers=auth("manager")).json()["cleared_for_real_data"] is False
    finally:
        run.audit_passed = True
        db.commit()
        db.close()


# --- escalations (FR-7), reports, settings ------------------------------------------

def test_escalations_exist_and_ack_needs_response(client, auth):
    esc = client.get("/api/escalations", headers=auth("manager")).json()
    assert esc, "seed history should produce escalations"
    url = f"/api/escalations/{esc[0]['id']}/acknowledge"
    assert client.post(url, headers=auth("manager"), json={"response": " "}).status_code == 400
    assert client.post(url, headers=auth("registrar"), json={"response": "x"}).status_code == 403
    assert client.post(url, headers=auth("manager"), json={"response": "Raised with DR"}).status_code == 200


def test_backlog_report(client, auth):
    rep = client.get("/api/reports/backlog", headers=auth("manager")).json()
    assert rep["benchmark_months"] == 12 and len(rep["trend"]) == 24
    assert {r["court_level"] for r in rep["by_level"]} <= {"Primary", "District", "Resident Magistrate", "High Court"}


def test_dashboard(client, auth):
    d = client.get("/api/dashboard", headers=auth("registrar")).json()
    assert d["pending"] > 0 and sum(d["risk_counts"].values()) > 0 and d["model"]["audit_passed"]


def test_settings_validation(client, auth):
    h = auth("admin")
    assert client.put("/api/settings", headers=h, json={"bogus": 1}).status_code == 400
    r = client.put("/api/settings", headers=h, json={"escalation_cycles": 3})
    assert r.status_code == 200 and r.json()["escalation_cycles"] == 3


def test_admin_user_management(client, auth):
    h = auth("admin")
    r = client.post("/api/users", headers=h, json={"username": "clerk2", "full_name": "Clerk Two",
                                                   "role": "clerk", "password": "longenough"})
    assert r.status_code == 201
    assert client.post("/api/users", headers=h, json={"username": "m2", "full_name": "M", "role": "magistrate",
                                                      "password": "longenough"}).status_code == 400
    me = client.get("/api/auth/me", headers=h).json()
    assert client.patch(f"/api/users/{me['id']}", headers=h, json={"active": False}).status_code == 400
