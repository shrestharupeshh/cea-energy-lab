from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from plantpulse.data import naming, validation
from plantpulse.data.calibration import apply_coeffs, fit_linear
from plantpulse.data.db import MetaDB
from plantpulse.data.store import Store
from plantpulse.data.timesync import ClockModel


def test_naming_round_trip():
    exp = naming.experiment_id(2027, "a1")
    ts = datetime(2027, 3, 4, 12, 30, 5, tzinfo=timezone.utc)
    iid = naming.image_id(exp, 3, 2, ts, "L")
    assert exp == "EXP-2027-A1" and naming.plant_id(exp, 3, 5) == "EXP-2027-A1-P03-N05"
    assert iid == "EXP-2027-A1-P03-S2-20270304T123005Z-L" and all(naming.validate(k, v) for k, v in
                                                                  (("experiment", exp), ("unit", naming.unit_id(exp, 3)), ("image", iid)))
    assert naming.image_relpath(iid) == "EXP-2027-A1/images/P03/20270304/" + iid + ".png"
    assert naming.plants_at_station(2) == [2, 5]
    with pytest.raises(ValueError):
        naming.utc_stamp(datetime(2027, 1, 1))            # naive timestamps are refused


def test_db_traceability(tmp_path):
    db = MetaDB(tmp_path / "m.db")
    exp = db.create_experiment("EXP-2027-X1", "A", "t", "pilot", day0_utc="2027-01-04T06:00:00Z", randomization_seed=1)
    for c in "CL":
        db.add_treatment(exp, c, c, {"ppfd": 250 if c == "C" else 125}, 10)
    units = db.assign_units(exp, {1: "C", 2: "L"}, seed=1)
    assert len(units) == 2 and len(db.q("SELECT * FROM plant")) == 12
    blind = db.allocation(exp)
    assert "treatment" not in blind and blind.blind_code.is_unique
    assert set(db.allocation(exp, blinded=False).treatment) == {"C", "L"}
    full = db.q("SELECT * FROM v_plant_full WHERE plant_id='EXP-2027-X1-P02-N03'").iloc[0]
    assert full.treatment == "L" and full.experiment_id == exp and full.data_class == "pilot"
    with pytest.raises(Exception):
        db.create_experiment("bad id", "A", "t", "pilot")
    with pytest.raises(Exception):                       # foreign keys enforced
        db.add_manual("NOPE", "height", 1.0, "mm")
    db.add_sensor("S1", 1, "air_t", "air_temperature", "C")
    db.add_calibration("S1", {"type": "linear", "gain": 1.0, "offset": 0.1}, "ice bath", valid_from_utc="2027-01-01T00:00:00Z")
    db.add_calibration("S1", {"type": "linear", "gain": 1.0, "offset": 0.2}, "ice bath", valid_from_utc="2027-02-01T00:00:00Z")
    cal = db.q("SELECT * FROM calibration ORDER BY valid_from_utc")
    assert cal.valid_to_utc.iloc[0] == "2027-02-01T00:00:00Z" and pd.isna(cal.valid_to_utc.iloc[1])
    db.close()


def test_calibration_functions():
    assert np.allclose(apply_coeffs([10, 20], {"type": "linear", "gain": 2, "offset": 1}), [21, 41])
    assert np.allclose(apply_coeffs([12000, 442000], {"type": "two_point", "raw0": 12000, "raw_ref": 442000, "ref": 1000}), [0, 1000])
    f = fit_linear(np.arange(10.0), 0.5 * np.arange(10.0) + 2)
    assert np.isclose(f["coeffs"]["gain"], 0.5) and np.isclose(f["coeffs"]["offset"], 2.0)
    with pytest.raises(ValueError):
        apply_coeffs([1], {"type": "mystery"})


def test_raw_store_is_append_only(tmp_path):
    s = Store(tmp_path)
    t0 = datetime(2027, 1, 4, 23, 59, 58, tzinfo=timezone.utc)
    df = pd.DataFrame({"utc": [t0 + timedelta(seconds=i) for i in range(4)], "air_t": [1.0, 2, 3, 4]})
    files = s.append_raw("EXP-2027-X1", 1, df)
    assert len(files) == 2, "frames spanning midnight go to two date partitions"
    s.append_raw("EXP-2027-X1", 1, df.assign(air_t=9.0))
    assert len(s.read_raw("EXP-2027-X1")) == 8 and not (files[0].stat().st_mode & 0o222), "raw files are read-only"


def test_qc_flags():
    n = 700
    t = pd.date_range("2027-01-04", periods=n, freq="1min", tz="UTC")
    rng = np.random.default_rng(0)
    df = pd.DataFrame({"utc": t, "air_t": 23 + rng.normal(0, 0.05, n), "rh": 65 + rng.normal(0, 0.5, n), "door": 0, "faults": 0})
    df.loc[50, "air_t"] = 31.0            # spike
    df.loc[60, "air_t"] = np.nan          # missing
    df.loc[70, "air_t"] = 80.0            # impossible
    df.loc[200:500, "rh"] = 64.2          # stuck sensor (longer than the 240-sample flatline window)
    df.loc[100:105, "door"] = 1
    out = validation.validate_frame(df)
    q = out["air_t_qc"]
    assert q[50] & validation.QC_SPIKE and q[60] & validation.QC_MISSING and q[70] & validation.QC_RANGE and q[102] & validation.QC_DOOR_OPEN
    assert (out["rh_qc"][495] & validation.QC_FLATLINE) and not (out["rh_qc"][150] & validation.QC_FLATLINE)
    assert (q == 0).mean() > 0.95
    s = validation.summarize(out).set_index("column")
    assert s.loc["air_t", "spike"] >= 1 and s.loc["air_t", "missing"] == 1


def test_gap_detection_and_completeness():
    t = pd.Series(pd.date_range("2027-01-04", periods=100, freq="1min", tz="UTC")).drop(index=range(40, 55))
    g = validation.find_gaps(t, 60.0)
    assert len(g) == 1 and g.missing_samples[0] == 15
    assert np.isclose(validation.completeness(t, 60.0), 0.85)


def test_clock_model_tracks_offset_and_reboot():
    rng = np.random.default_rng(0)
    c = ClockModel()
    true_offset = 1_800_000_000.0
    err = []
    for i in range(1, 900):
        ms = i * 1000.0
        est = c.update(ms, true_offset + ms / 1000 * (1 + 40e-6) + abs(rng.normal(0, 0.02)))    # 40 ppm drift, late arrivals only
        err.append(est - (true_offset + ms / 1000 * (1 + 40e-6)))
    assert abs(np.median(err[100:])) < 0.03
    c.update(500.0, true_offset + 2000.0)                 # uptime counter restarted
    assert len(c.ms) == 1
