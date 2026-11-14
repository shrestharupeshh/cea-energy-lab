"""End-to-end tests on a small simulated experiment (fixture `mini_lab`)."""
import json

import numpy as np
import pandas as pd
import pytest

from plantpulse.acquisition.node_client import NodeClient
from plantpulse.acquisition.scheduler import capture_sequence, due_times, lights_window_ok
from plantpulse.acquisition.sim_node import SimNode
from plantpulse.data import validation
from plantpulse.data.db import MetaDB
from plantpulse.data.export import export_dataset, verify_dataset
from plantpulse.data.store import Store


def test_protocol_session_with_simulated_node():
    t = [1_800_000_000.0]
    node = SimNode(pod=3, seed=1)
    c = NodeClient(node, clock=lambda: t[0])
    ids = [c.send(f"TIME epoch={int(t[0])}"), c.send("SET air_t_day=23 air_t_night=20 rh=68 led=0.74 on=0 off=960"), c.send("MODE AUTO"),
           c.send("SET led=3"), c.send("MOVE station=2"), c.send("CAPTURE")]
    for i in range(900):
        node.step(1.0)
        t[0] += 1.0
        if i % 7 == 0:
            c.send("PING")
            c.poll()
    c.poll()
    assert c.hello["pod"] == 3 and c.pod == 3
    assert [c.acks[i]["ok"] for i in ids] == [True, True, True, False, True, True]
    assert any(e["ev"] == "capture_done" for e in c.events) and c.dropped == 0 and c.bad_lines == 0
    df = c.drain()
    assert len(df) == 900 and df.utc.is_monotonic_increasing and df["gpos"].iloc[-1] == (400 - 20) * 80
    assert abs((df.utc.iloc[-1] - df.utc.iloc[0]).total_seconds() - 899) < 0.5
    assert df["air_t"].iloc[-1] > 21.5 and df["u_led"].iloc[-1] == pytest.approx(0.74), "lights on, chamber warming towards 23 C"


def test_node_keeps_lights_off_without_time_and_survives_host_silence():
    node = SimNode(pod=1, seed=2)
    node.write("SET led=0.7 on=0 off=1200")
    node.write("MODE AUTO")
    assert node.step(1.0)["u_led"] == 0, "no time base -> lights stay off"
    node.write("TIME epoch=1800000000")
    for _ in range(400):
        f = node.step(1.0)
    assert f["faults"] & 4 and f["u_led"] > 0.6, "host silent > 120 s: fault raised, recipe continues"


def test_virtual_experiment_traceability_and_treatments(mini_lab):
    root, runs = mini_lab
    db = MetaDB(root / "plantpulse_meta.db")
    assert set(db.q("SELECT data_class FROM experiment").data_class) == {"simulated"}
    r = runs[0]
    assert r["frames"] == {1: 6 * 1440, 2: 6 * 1440}
    m = r["minute"]
    assert validation.completeness(m[m.pod == 1].utc, 60.0) > 0.999 and (m.air_t_qc == 0).mean() > 0.98
    d = r["daily"].merge(db.q("SELECT unit_id, treatment FROM v_plant_full GROUP BY unit_id"), on="unit_id")
    post = d[d.day >= 3].groupby("treatment")[["ppfd_light", "dli", "air_t_light", "kwh_led"]].mean()
    assert abs(post.loc["C", "ppfd_light"] - 250) < 6 and abs(post.loc["L", "ppfd_light"] - 125) < 4
    assert abs(post.loc["C", "air_t_light"] - 23.0) < 0.4 and post.loc["L", "kwh_led"] < 0.6 * post.loc["C", "kwh_led"]
    # every image row resolves to an existing file with the recorded checksum, a unit, a camera
    store = Store(root)
    from plantpulse.data.store import sha256_file
    img = db.q("SELECT * FROM image").sample(5, random_state=0)
    for _, i in img.iterrows():
        assert sha256_file(store.image_path(i.path)) == i.sha256 and i.unit_id and i.camera_id
    # every trait row resolves to a plant and an image
    t = r["traits"]
    assert set(t.plant_id) <= set(db.q("SELECT plant_id FROM plant").plant_id) and t.image_id.isin(db.q("SELECT image_id FROM image").image_id).all()
    # setpoint log: every command was checked; the treatment change is recorded
    sl = db.q("SELECT * FROM setpoint_log")
    assert sl.accepted.all() and (sl.source == "recipe").all() and len(sl) == 2 * (2 + 1)
    # serial harvest removed one plant per pod
    assert len(db.q("SELECT * FROM plant WHERE harvest_day = 3")) == 4
    # raw counts were converted by the calibration table (reservoir mass in grams, PPFD in umol)
    assert 3000 < m.res_g.dropna().median() < 5100
    db.close()


def test_vision_tracks_truth_in_virtual_experiment(mini_lab):
    _, runs = mini_lab
    t = runs[0]["traits"]
    t = t[(t.qc == 0) & (t.true_visible_area_cm2 > 2)]
    assert len(t) > 30 and (t.n_fiducials >= 3).all()
    rel = t.projected_area_cm2 / t.true_visible_area_cm2 - 1
    assert rel.abs().median() < 0.03 and rel.abs().max() < 0.12


def test_dataset_export_is_verifiable_and_immutable(mini_lab, tmp_path):
    root, runs = mini_lab
    db, store = MetaDB(root / "plantpulse_meta.db"), Store(root)
    exps = [r["experiment_id"] for r in runs]
    out = export_dataset(db, store, exps, tmp_path, "0.0.1-test", include_images=True)
    assert verify_dataset(out) == []
    readme = (out / "README.md").read_text()
    assert "WARNING" in readme and "simulated" in readme
    pkg = json.loads((out / "datapackage.json").read_text())
    assert pkg["data_classes"] == ["simulated"] and pkg["licenses"][0]["name"] == "CC-BY-4.0"
    assert "treatment_id" not in pd.read_csv(out / "metadata" / "unit.csv").columns, "allocation is kept in a separate unblinding file"
    assert (out / "metadata" / "allocation_UNBLINDING.csv").exists()
    victim = next((out / "processed").rglob("*.parquet"))
    victim.write_bytes(victim.read_bytes() + b"x")
    assert any("checksum mismatch" in p for p in verify_dataset(out))
    with pytest.raises(FileExistsError):
        export_dataset(db, store, exps, tmp_path, "0.0.1-test")
    db.close()


def test_scheduler():
    from datetime import datetime, timezone
    d0 = datetime(2027, 1, 4, tzinfo=timezone.utc)
    t = due_times(d0, 120, 390, 1290)
    assert len(t) == 8 and t[0].hour == 6 and t[0].minute == 30
    seq = capture_sequence(stereo=True)
    assert len(seq) == 10 and seq[-1]["station"] == 0 and [s["tag"] for s in seq[:3]] == ["L", "R", ""]
    assert lights_window_ok(390, 1290, 360, 16) and not lights_window_ok(300, 1290, 360, 16)
    with pytest.raises(ValueError):
        due_times(d0, 5)


def test_daemon_refuses_simulated_data_in_real_experiment(tmp_path):
    from plantpulse.acquisition import daemon
    db = MetaDB(tmp_path / "m.db")
    db.create_experiment("EXP-2027-R1", "pilot", "real", "pilot", day0_utc="2027-01-04T06:00:00Z")
    with pytest.raises(SystemExit, match="refusing"):
        daemon.run("EXP-2027-R1", {}, db, Store(tmp_path), 0.1, sim_nodes={1: SimNode()})
    db.close()


def test_dashboard_services_and_app(mini_lab, monkeypatch):
    root, runs = mini_lab
    from plantpulse.dashboard import services as S
    db, store = S.open_lab(root)
    exp = runs[0]["experiment_id"]
    assert len(S.experiments(db)) == 2 and len(S.current_conditions(store, exp)) == 2
    assert "treatment" not in S.units(db, exp, unblind=False) and "treatment" in S.units(db, exp, unblind=True)
    g = S.growth_curves(store, db, exp)
    assert g.shape[1] == 2 and g.iloc[-1].min() > g.iloc[0].max()
    assert S.progress(db, exp)["images"] == 36 and S.resources(store, exp)["kwh_led"].min() > 2
    new = S.create_experiment(db, 2027, "N1", "A", "t", "simulated", {c: {"recipe": {"ppfd": 250}} for c in "CLHN"}, None, "2027-06-01T06:00:00Z", 5)
    assert sorted(S.units(db, new, True).treatment) == ["C", "H", "L", "N"]
    S.set_imaging_schedule(db, new, 60, 400, 1200, True)
    assert db.q("SELECT interval_min FROM imaging_schedule WHERE experiment_id=?", (new,)).interval_min[0] == 60
    traj, summ = S.what_if(250, 16, 23, 20, 68, 1.4, days=3)
    assert summ["provenance"] == "predicted" and (traj.provenance == "predicted").all()
    db.close()
    st_testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setenv("PLANTPULSE_DATA", str(root))
    from pathlib import Path
    app = Path(S.__file__).with_name("app.py")
    at = st_testing.AppTest.from_file(str(app), default_timeout=120).run()
    assert not at.exception and any("SIMULATED" in w.value for w in at.warning)
