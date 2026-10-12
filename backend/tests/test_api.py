"""API tests: role separation, the non-skippable gates, and the clerk -> registrar flow."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app import services
from app.db import SessionLocal
from justiceflow import config as C

from app.models import Case, Hearing, ModelRun


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
        "case_type": "Criminal", "offence": "Robbery / violence", "in_custody": True, "court_level": "District",
        "court_station": m["court_station"], "n_parties": 3, "represented": True, "filing_date": "2026-09-20"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["risk"] is not None and body["risk"]["category"] in {"Low", "Medium", "High"}
    assert body["region"] == ref["station_region"][m["court_station"]]
    assert body["in_custody"] is True and body["offence"] == "Robbery / violence"


@pytest.mark.parametrize("change,msg", [
    ({"case_type": "Land", "court_level": "District"}, "land division"),  # land goes to DLHT / HC Land Division
    ({"case_type": "Civil", "court_level": "Primary", "represented": True}, "advocates"),  # MCA s.33
    ({"case_type": "Criminal", "court_level": "District", "offence": None}, "offence"),
])
def test_registration_follows_jurisdiction_rules(client, auth, change, msg):
    mags = client.get("/api/magistrates", headers=auth("admin")).json()
    level = change["court_level"]
    m = next(x for x in mags if x["court_level"] == level)
    body = {"case_type": "Civil", "court_station": m["court_station"], "n_parties": 2, "represented": False,
            "filing_date": "2026-09-20", **change}
    r = client.post("/api/cases", headers=auth("clerk"), json=body)
    assert r.status_code == 400 and msg in r.json()["detail"].lower(), r.text


def test_next_date_suggestion_follows_the_case(client, auth):
    case = first_pending(client, auth, sort="id", order="asc")
    url = f"/api/cases/{case['id']}/suggest-next-date"
    h = auth("clerk")
    forensic = client.post(url, headers=h, json={"hearing_date": "2026-09-25", "adjournment_reason": "forensic",
                                                 "in_custody": False}).json()
    gap = (date.fromisoformat(forensic["date"]) - date(2026, 9, 25)).days
    assert gap >= C.FORENSIC_WAIT_DAYS and "Government Chemist" in forensic["reasons"][0]
    remand = client.post(url, headers=h, json={"hearing_date": "2026-09-25", "adjournment_reason": "forensic",
                                               "in_custody": True}).json()
    if case["case_type"] in C.CRIMINAL_TYPES:
        assert (date.fromisoformat(remand["date"]) - date(2026, 9, 25)).days <= C.REMAND_MAX_GAP_DAYS + 30
    s = client.post(url, headers=h, json={"hearing_date": "2026-09-25", "outcome": "proceeded"}).json()
    assert date.fromisoformat(s["date"]).weekday() < 5
    if s["capacity"]:
        assert s["load"] < s["capacity"] or "fully booked" in " ".join(s["reasons"])
    assert client.post(url, headers=h, json={"hearing_date": "2026-09-25", "outcome": "disposed"}).json()["date"] is None


def test_recording_a_hearing_fixes_the_next_date(client, auth):
    case = first_pending(client, auth, sort="id", order="asc")
    url = f"/api/cases/{case['id']}/hearings"
    h = auth("clerk")
    bad = client.post(url, headers=h, json={"hearing_date": "2026-09-25", "outcome": "proceeded",
                                            "next_date": "2026-09-24"})
    assert bad.status_code == 400 and "after the hearing" in bad.json()["detail"]
    ok = client.post(url, headers=h, json={"hearing_date": "2026-09-25", "outcome": "adjourned",
                                           "adjournment_reason": "witness", "next_date": "2026-10-20"})
    assert ok.status_code == 201, ok.text
    detail = client.get(f"/api/cases/{case['id']}", headers=auth("registrar")).json()
    assert detail["next_date"] == "2026-10-20" and detail["active_flags"]["flag_witness"] is True
    assert "summons" in detail["responsible"].lower()


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


def test_cause_list_starts_from_dates_fixed_in_court(client, auth):
    h = auth("registrar")
    cycles = sorted(client.get("/api/cycles", headers=h).json(), key=lambda c: c["week_start"])
    items = [client.get(f"/api/cycles/{c['id']}", headers=h).json()["items"] for c in cycles]
    proposed = [{r["case_id"] for r in rows} for rows in items]
    for rows in items:
        assert {r["kind"] for r in rows} <= {"fixed", "new", "brought_forward"}
        assert sum(r["kind"] == "fixed" for r in rows) > 0
    # Each week is a different set of cases: the replay holds the hearings and fixes new dates.
    for prev, cur in zip(proposed, proposed[1:]):
        assert len(prev & cur) < 0.5 * len(cur)

    week = date.fromisoformat(cycles[-1]["week_start"]) + timedelta(weeks=1)
    week_end = week + timedelta(days=4)
    r = client.post("/api/cycles", headers=h, json={"week_start": week.isoformat()})
    assert r.status_code == 201, r.text
    rows = client.get(f"/api/cycles/{r.json()['id']}", headers=h).json()["items"]
    db = SessionLocal()
    try:
        cases = {c.id: c for c in db.scalars(select(Case).where(Case.id.in_([x["case_id"] for x in rows])))}
        recent = set(db.scalars(select(Hearing.case_id).where(
            Hearing.hearing_date >= week - timedelta(days=services.RELIST_GAP_DAYS), Hearing.hearing_date < week)))
    finally:
        db.close()
    for x in rows:
        c = cases[x["case_id"]]
        assert x["magistrate_id"] == c.assigned_magistrate_id  # cases stay with their officer
        assert not C.is_sessions_case(c.court_level, c.case_type, c.offence)  # those go to sessions
        if x["kind"] == "fixed":
            assert week <= c.next_date <= week_end and x["date"] == c.next_date.isoformat()
        if x["kind"] == "new":
            assert x["case_id"] not in recent
        if x["kind"] == "brought_forward":
            assert c.next_date > week_end and x["risk_category"] == "High"


def test_approve_selected_listings(client, auth):
    h = auth("registrar")
    cyc = next(c for c in client.get("/api/cycles", headers=h).json() if c["status"] == "PROPOSED")
    ids = [i["case_id"] for i in client.get(f"/api/cycles/{cyc['id']}", headers=h).json()["items"][:3]]
    url = f"/api/cycles/{cyc['id']}/approve-selected"
    assert client.post(url, headers=h, json=[*ids, "NOT-A-CASE"]).status_code == 404
    assert client.post(url, headers=auth("clerk"), json=ids).status_code == 403
    assert client.post(url, headers=h, json=ids).json() == {"approved": 3}
    assert client.post(url, headers=h, json=ids).json() == {"approved": 0}  # already decided
    after = client.get(f"/api/cycles/{cyc['id']}", headers=h).json()
    assert after["approved"] == 3


def test_overdue_cases_report_days_overdue_and_lead_the_review_queue(client, auth):
    h = auth("registrar")
    q = client.get("/api/review-queue", headers=h, params={"risk": "High", "limit": 50}).json()["risk_pending"]
    assert q
    overdue = [c for c in q if c["risk"]["overdue"]]
    assert overdue and all(c["days_overdue"] > 0 for c in overdue)
    # Ordered like the scheduler's priority: overdue, court-controllable, remand first.
    def priority(c):
        mult = 1.0 if c["risk"]["court_controllable"] else C.EXTERNAL_BLOCK_PENALTY
        return ((100 * c["risk"]["probability"] + (20 if c["risk"]["overdue"] else 0)) * mult
                + (C.CUSTODY_PRIORITY if c["in_custody"] else 0))
    p = [priority(c) for c in q]
    assert all(a >= b - 1e-6 for a, b in zip(p, p[1:]))


def test_needs_attention_groups(client, auth):
    na = client.get("/api/needs-attention", headers=auth("registrar")).json()
    assert set(na) == {"date_passed", "no_date", "far_date_high", "repeated_external", "long_remand"}
    assert sum(g["total"] for g in na.values()) > 0
    for r in na["long_remand"]["items"]:
        assert r["in_custody"] and r["remand_days"] > services.LONG_REMAND_DAYS
    for r in na["repeated_external"]["items"]:
        assert r["responsible"]
    assert client.get("/api/needs-attention", headers=auth("clerk")).status_code == 403


def test_criminal_sessions_are_planned_separately(client, auth):
    h = auth("registrar")
    plans = client.get("/api/sessions", headers=h).json()
    assert plans and plans[0]["status"] == "PROPOSED"  # the seed proposes one
    plan = plans[0]
    assert all(c["case_id"].startswith("SYN-") for c in plan["cases"])
    first = plan["cases"][0]["case_id"]
    after = client.delete(f"/api/sessions/{plan['id']}/cases/{first}", headers=h).json()
    assert first not in {c["case_id"] for c in after["cases"]}
    assert client.post(f"/api/sessions/{plan['id']}/approve", headers=auth("clerk")).status_code == 403
    approved = client.post(f"/api/sessions/{plan['id']}/approve", headers=h).json()
    assert approved["status"] == "APPROVED"
    detail = client.get(f"/api/cases/{approved['cases'][0]['case_id']}", headers=h).json()
    assert detail["next_date"] == approved["cases"][0]["planned_date"] and detail["sessions_case"]
    assert client.post(f"/api/sessions/{plan['id']}/approve", headers=h).status_code == 409
    opts = client.get("/api/sessions/options", headers=h).json()
    st = opts["stations"][0]
    bad = client.post("/api/sessions", headers=h, json={"court_station": st["court_station"],
                                                       "magistrate_id": "MAG-NOPE", "start_date": "2026-11-02"})
    assert bad.status_code == 400


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
    assert all(e["responsible"] for e in esc)
    agenda = client.get("/api/escalations/agenda", headers=auth("manager")).json()
    assert agenda["total"] == len(esc) and agenda["groups"]
    url = f"/api/escalations/{esc[0]['id']}/acknowledge"
    assert client.post(url, headers=auth("manager"), json={"response": " "}).status_code == 400
    assert client.post(url, headers=auth("registrar"), json={"response": "x"}).status_code == 403
    assert client.post(url, headers=auth("manager"), json={"response": "Raised with DR"}).status_code == 200


def test_backlog_report(client, auth):
    rep = client.get("/api/reports/backlog", headers=auth("manager")).json()
    assert rep["benchmark_months"] == 12 and len(rep["trend"]) == 24
    assert {r["court_level"] for r in rep["by_level"]} <= set(C.COURT_LEVELS)
    assert all(r["published_avg_days_2025"] for r in rep["by_level"])
    assert {r["division"] for r in rep["by_division"]} <= {C.division("High Court", t) for t in C.CASE_TYPES}


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
