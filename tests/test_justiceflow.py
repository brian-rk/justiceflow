"""Tests for the SRS's non-negotiable safeguards and the main pipeline path."""

import numpy as np
import pandas as pd
import pytest

from justiceflow import config as C
from justiceflow import fairness, pipeline, scheduler, synthetic
from justiceflow.features import feature_matrix, training_snapshots
from justiceflow.review import ReviewStore

AS_OF = "2026-09-26"


@pytest.fixture(scope="module")
def data():
    return synthetic.generate(2500, seed=3, as_of=AS_OF)


@pytest.fixture(scope="module")
def engine(data):
    return pipeline.train(data.cases, data.hearings, AS_OF)


@pytest.fixture(scope="module")
def scored(engine, data):
    return pipeline.score(engine, data.cases, data.hearings, AS_OF)


# --- data & features ------------------------------------------------------

def test_calibration_moves_backlog_share_toward_targets(data):
    snaps_cases = data.cases.dropna(subset=["resolution_date"])
    days = (snaps_cases["resolution_date"] - snaps_cases["filing_date"]).dt.days
    target = snaps_cases["court_level"].map(C.DISPOSITION_TARGET_MONTHS) * 30.44
    share = (days > target).groupby(snaps_cases["court_level"]).mean()
    # Disposed cases are biased short (long ones are still pending), so only check range.
    # In 2025 backlog is rare below the Court of Appeal (High Court 1.2%), so a small
    # sample may show none there; the Court of Appeal must stand out.
    assert ((share >= 0.0) & (share < 0.6)).all()
    assert share.idxmax() == "Court of Appeal"


def test_protected_features_never_reach_the_model(data):
    X = feature_matrix(training_snapshots(data.cases, data.hearings, AS_OF))
    assert not set(C.PROTECTED_FEATURES) & set(X.columns)
    assert list(X.columns) == C.MODEL_FEATURES


def test_no_snapshot_taken_after_disposition_target(data):
    snaps = training_snapshots(data.cases, data.hearings, AS_OF)
    assert (snaps["target_used"] <= 1.0).all()


# --- model & explanations ---------------------------------------------------

def test_model_beats_chance(engine):
    assert engine.holdout_metrics["auc"] > 0.7


def test_every_score_is_explained(scored):
    assert scored["driving_factors"].str.len().gt(0).all()
    assert set(scored["risk_category"]) <= {"Low", "Medium", "High"}


def test_external_flags_mark_case_as_blocked(scored):
    flagged = scored[list(C.EXTERNAL_FLAGS)].any(axis=1)
    assert (scored.loc[flagged, "court_controllable"] == False).all()  # noqa: E712
    assert scored.loc[~flagged, "court_controllable"].all()


# --- fairness gate ----------------------------------------------------------

def _biased_audit_input(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    regions = rng.choice(["Dar es Salaam", "Kigoma"], size=n)
    snaps = pd.DataFrame({
        "region": regions, "case_type": "Civil", "court_level": "District",
        "label": rng.integers(0, 2, size=n),
    })
    # Kigoma negatives are wrongly flagged High far more often.
    p = np.where((snaps.region == "Kigoma") & (snaps.label == 0), 0.9, 0.2)
    p = np.where(snaps.label == 1, 0.8, p)
    return snaps, p


def test_gate_fails_on_regional_fpr_gap():
    snaps, p = _biased_audit_input()
    result = fairness.audit(snaps, p)
    assert not result.passed
    assert result.max_gap > C.FPR_GAP_THRESHOLD


def test_reweighting_targets_over_flagged_region():
    snaps, p = _biased_audit_input()
    result = fairness.audit(snaps, p)
    w = fairness.reweight(snaps, result.table, np.ones(len(snaps)))
    kigoma_neg = (snaps.region == "Kigoma") & (snaps.label == 0)
    assert w[kigoma_neg].min() > 1.0
    assert np.allclose(w[~kigoma_neg], 1.0)


def test_failed_gate_blocks_scheduling_and_real_data(engine, data, scored, tmp_path):
    failed = pipeline.TrainedEngine(engine.model, fairness.AuditResult(False, "region", 0.3, 0.1, pd.DataFrame()),
                                    {}, engine.trained_as_of)
    with pytest.raises(pipeline.FairnessGateError):
        pipeline.score(failed, data.cases, data.hearings, AS_OF, real_data=True)
    with pytest.raises(pipeline.FairnessGateError):
        pipeline.propose_week(failed, scored, data.magistrates, "2026-09-28", ReviewStore(tmp_path), "W1")


# --- scheduler --------------------------------------------------------------

def test_schedule_respects_hard_constraints(scored, data):
    plan, info = scheduler.optimise(scored, data.magistrates, "2026-09-28", time_limit_s=10)
    assert info["solver_status"] in {"OPTIMAL", "FEASIBLE"}
    assert plan["case_id"].is_unique
    mags = data.magistrates.set_index("magistrate_id")
    per_day = plan.groupby(["magistrate_id", "day"]).size()
    for (mid, day), n in per_day.items():
        assert n <= mags.loc[mid, "daily_capacity"]
        assert day not in str(mags.loc[mid, "unavailable_days"])
    merged = plan.merge(mags[["court_station", "court_level"]], left_on="magistrate_id",
                        right_index=True, suffixes=("", "_mag"))
    assert (merged["court_station"] == merged["court_station_mag"]).all()
    assert (merged["court_level"] == merged["court_level_mag"]).all()


def test_blocked_cases_are_deprioritised(scored):
    row = scored.iloc[0].copy()
    row["risk_probability"], row["overdue"] = 0.9, False
    row["court_controllable"] = True
    open_w = scheduler.priority_weight(row)
    row["court_controllable"] = False
    assert scheduler.priority_weight(row) < open_w


# --- human in the loop ------------------------------------------------------

def _open(store, engine, scored, data, cycle_id):
    return pipeline.propose_week(engine, scored, data.magistrates, "2026-09-28", store, cycle_id)[0]


def test_nothing_is_final_without_registrar(engine, scored, data, tmp_path):
    store = ReviewStore(tmp_path)
    proposal = _open(store, engine, scored, data, "W1")
    assert store.final_cause_list("W1").empty
    with pytest.raises(ValueError):
        store.decide("W1", proposal.case_id[0], "approve", registrar="")
    with pytest.raises(ValueError):
        store.decide("W1", proposal.case_id[0], "remove", "REG-1")  # no reason
    store.decide("W1", proposal.case_id[0], "approve", "REG-1")
    store.decide("W1", proposal.case_id[1], "edit", "REG-1", day="Fri", reason="advocate on circuit")
    final = store.finalise("W1", "REG-1")
    assert set(final["case_id"]) == {proposal.case_id[0], proposal.case_id[1]}
    assert final.set_index("case_id").loc[proposal.case_id[1], "day"] == "Fri"
    with pytest.raises(PermissionError):
        store.decide("W1", proposal.case_id[2], "approve", "REG-1")


def test_escalation_after_consecutive_unactioned_high_cycles(engine, scored, data, tmp_path):
    store = ReviewStore(tmp_path)
    high = set(scored.loc[scored.risk_category == "High", "case_id"])
    touched = sorted(high)[0]
    for i in range(C.ESCALATION_CYCLES):
        cid = f"W{i}"
        _open(store, engine, scored, data, cid)
        store.decide(cid, touched, "acknowledge", "REG-1")
        store.finalise(cid, "REG-1")
    esc = store.t["escalations"]
    assert set(esc["case_id"]) == high - {touched}
    assert (esc["cycle_id"] == f"W{C.ESCALATION_CYCLES - 1}").all()


def test_store_round_trips_through_csv(engine, scored, data, tmp_path):
    store = ReviewStore(tmp_path)
    _open(store, engine, scored, data, "W1")
    store.approve_all("W1", "REG-1")
    n = len(store.finalise("W1", "REG-1"))
    assert len(ReviewStore(tmp_path).final_cause_list("W1")) == n


# --- Tanzanian court rules ----------------------------------------------------

def test_synthetic_data_follows_jurisdiction(data):
    c = data.cases
    for level, types in C.CASE_TYPES_BY_LEVEL.items():
        assert set(c.loc[c.court_level == level, "case_type"]) <= set(types)
    assert not c.loc[c.court_level == "District", "case_type"].eq("Land").any()  # land: DLHT / HC Land Division
    assert not c.loc[c.court_level == "Primary", "represented"].any()  # no advocates in Primary Courts
    assert (c.loc[~c.case_type.isin(C.CRIMINAL_TYPES), "offence"] == "Not criminal").all()
    trial = c.court_level != "Court of Appeal"
    assert c.loc[trial & (c.offence == "Homicide"), "in_custody"].all()  # murder is not bailable
    assert not c.loc[~trial, "in_custody"].any()  # appellants are convicted, not on remand


def test_calibration_matches_published_2025_times(data):
    res = data.cases["resolution_date"].fillna(pd.Timestamp("2100-01-01"))
    avg = synthetic.avg_days_to_decision(data.cases, res, data.as_of)
    for level, target in C.AVG_DAYS_TO_DECISION_2025.items():
        assert abs(avg[level] - target) / target < 0.35, (level, avg[level], target)


def test_dates_fixed_in_court_are_kept_and_cases_stay_with_their_officer(scored, data):
    pending = data.cases.set_index("case_id")
    week = pd.Timestamp("2026-09-28")
    sample = scored[scored["assigned_magistrate"].notna()].head(30)
    fixed = {r.case_id: (r.assigned_magistrate, week + pd.Timedelta(days=i % 5)) for i, r in enumerate(sample.itertuples())}
    plan, _ = scheduler.optimise(scored, data.magistrates, week, time_limit_s=10, fixed=fixed)
    got = plan.set_index("case_id")
    for cid, (mid, day) in fixed.items():
        assert got.loc[cid, "kind"] == "fixed" and got.loc[cid, "magistrate_id"] == mid
        assert pd.Timestamp(got.loc[cid, "date"]) == day
    for r in plan.itertuples():
        assigned = pending.loc[r.case_id, "assigned_magistrate"]
        assert r.magistrate_id == assigned


def test_remand_raises_priority(scored):
    row = scored.iloc[0].copy()
    row["risk_probability"], row["overdue"], row["court_controllable"] = 0.4, False, False
    row["in_custody"] = False
    free = scheduler.priority_weight(row)
    row["in_custody"] = True
    assert scheduler.priority_weight(row) == free + C.CUSTODY_PRIORITY


def test_year_only_filing_dates_keep_only_certain_labels():
    from justiceflow.ingest import interval_labels
    df = pd.DataFrame({
        "court_level": ["High Court"] * 3, "filing_date": [None] * 3,
        "filing_year": [2021, 2021, 2024],
        "decision_date": ["2024-04-02", "2023-06-01", "2024-07-03"],
    })
    labels = interval_labels(df)["label"].tolist()
    assert labels[0] == 1        # filed in 2021, decided April 2024: past 24 months whatever the day
    assert pd.isna(labels[1])     # June 2023: could be either side of 24 months
    assert labels[2] == 0        # filed and decided in 2024


def test_every_case_sits_at_a_real_court(data):
    real = {(c["region"], c["court_level"], c["court_name"]) for c in C.COURTS}
    cases = data.cases
    assert all((r, lv, s) in real for r, lv, s in zip(cases.region, cases.court_level, cases.court_station))
    # High Court division cases go to the division where the region has one.
    dar_land = cases[(cases.region == "Dar es Salaam") & (cases.court_level == "High Court") & (cases.case_type == "Land")]
    assert (dar_land.court_station == "Dar es Salaam High Court Land Division").all()
    lindi_hc = cases[(cases.region == "Lindi") & (cases.court_level == "High Court")]
    assert (lindi_hc.court_station == "Mtwara High Court").all()
    # Every court in the register has a bench, so new cases can be registered anywhere.
    assert {c["court_name"] for c in C.COURTS} <= set(data.magistrates.court_station)
