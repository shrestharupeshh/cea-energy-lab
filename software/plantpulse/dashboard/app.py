"""PLANTPULSE LAB research dashboard.   streamlit run software/plantpulse/dashboard/app.py

Reads the metadata database and processed tables under the data root (env PLANTPULSE_DATA or the
sidebar field). Treatment labels are hidden behind blind codes unless 'Unblind' is ticked.
Measured values, model predictions and simulated data are always labelled as such.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from plantpulse.config import DATA_ROOT
from plantpulse.dashboard import services as S

st.set_page_config(page_title="PlantPulse Lab", layout="wide")
root = st.sidebar.text_input("Data root", os.environ.get("PLANTPULSE_DATA", str(DATA_ROOT)))
db, store = S.open_lab(root)
exps = S.experiments(db)
st.sidebar.caption(f"{len(exps)} experiment(s)")
exp = st.sidebar.selectbox("Experiment", exps["experiment_id"].tolist()) if len(exps) else None
unblind = st.sidebar.checkbox("Unblind treatments", value=False, help="Leave off during a running study.")
st.title("PlantPulse Lab")

tabs = st.tabs(["Overview", "Environment", "Plants", "Models", "Resources", "Compare", "Digital twin", "Experiments", "Export"])

if exp:
    info = S.progress(db, exp)
    if info["data_class"] != "experimental":
        st.warning(f"Data class: **{info['data_class'].upper()}** - not experimental results.")

with tabs[0]:
    if not exp:
        st.info("No experiment yet. Create one in the Experiments tab.")
    else:
        c = st.columns(4)
        c[0].metric("Status", info["status"])
        c[1].metric("Day", f"{info['day']} / {info['days_planned']}" if info["day"] is not None else "-")
        c[2].metric("Images", info["images"])
        c[3].metric("Manual records", info["manual_records"])
        if info["day"] is not None:
            st.progress(min(max(info["day"] / info["days_planned"], 0.0), 1.0))
        st.subheader("Latest conditions (measured)")
        cur = S.current_conditions(store, exp)
        st.dataframe(cur.round({c: 2 for c in cur.select_dtypes("number").columns}), width="stretch") if len(cur) else st.caption("No processed sensor data.")
        st.subheader("Units")
        st.dataframe(S.units(db, exp, unblind), width="stretch")

with tabs[1]:
    if exp:
        col = st.selectbox("Variable", ["air_t", "rh", "co2", "ppfd", "sol_t", "ph", "ec", "led_w", "act_w"])
        h = S.history(store, exp, col)
        st.line_chart(h) if len(h) else st.caption("No data.")
        st.caption("30-minute means of QC-passed 1-minute records, by pod.")

with tabs[2]:
    if exp:
        trait = st.selectbox("Trait (vision-derived)", ["projected_area_cm2", "diameter_max_mm", "station_cover", "exg_mean", "yellow_frac", "brown_frac"])
        g = S.growth_curves(store, db, exp, trait, unblind)
        st.line_chart(g) if len(g) else st.caption("No trait data.")
        st.caption("Unit means of per-plant values. Projected area is at lid-plane scale; per-plant values are unreliable once canopies touch.")
        imgs = db.q("SELECT image_id, unit_id, station, captured_utc, path FROM image WHERE experiment_id=? ORDER BY captured_utc DESC LIMIT 300", (exp,))
        if len(imgs):
            pick = st.selectbox("Image", imgs["image_id"].tolist())
            p = store.image_path(imgs.set_index("image_id").loc[pick, "path"])
            st.image(str(p), caption=pick, width=640) if Path(p).exists() else st.caption("Image file not on this machine.")
        with st.expander("Enter manual measurement"):
            plants = db.q("SELECT plant_id FROM plant p JOIN unit u USING (unit_id) WHERE u.experiment_id=? ORDER BY plant_id", (exp,))["plant_id"].tolist()
            with st.form("manual"):
                pid = st.selectbox("Plant", plants)
                qty = st.selectbox("Quantity", ["leaf_count", "diameter_max", "diameter_perp", "height", "tipburn_score", "shoot_fresh_mass", "shoot_dry_mass", "leaf_area"])
                val = st.number_input("Value", value=0.0)
                unit_ = st.text_input("Unit", "mm")
                destructive = st.checkbox("Destructive")
                op = st.text_input("Operator initials")
                if st.form_submit_button("Save") and op:
                    db.add_manual(pid, qty, float(val), unit_, destructive=destructive, operator=op)
                    st.success("Saved.")

with tabs[3]:
    st.subheader("Model runs")
    mr = S.model_runs(db)
    st.dataframe(mr.drop(columns=["metrics_json"], errors="ignore"), width="stretch") if len(mr) else st.caption("No model runs registered.")
    if exp:
        pr = S.predictions(db, exp)
        st.subheader("Predictions (model output, not measurements)")
        st.dataframe(pr, width="stretch") if len(pr) else st.caption("No predictions stored for this experiment.")

with tabs[4]:
    if exp:
        r = S.resources(store, exp)
        st.dataframe(r.round(2), width="stretch") if len(r) else st.caption("No daily summaries.")
        st.caption("kWh from the per-pod DC power monitors (LED rail, actuator rail); water from the top-up reservoir load cell.")

with tabs[5]:
    if exp:
        if not unblind:
            st.info("Tick 'Unblind treatments' to compare conditions.")
        else:
            q = st.selectbox("Quantity", ["shoot_dry_mass", "shoot_fresh_mass", "leaf_area", "diameter_max"])
            cmp_ = S.compare_conditions(db, exp, q)
            st.dataframe(cmp_.round(3), width="stretch")
            if len(cmp_):
                st.bar_chart(cmp_.groupby("treatment")["unit_mean"].mean())
            st.caption("Descriptive unit means. The experimental unit is the pod-run; run the pre-specified analysis for inference.")

with tabs[6]:
    st.caption("Digital-twin scenario. All numbers below are PREDICTIONS from an uncalibrated model until validation test VAL-DT-01 has passed.")
    a, b, c = st.columns(3)
    ppfd = a.slider("PPFD (umol m-2 s-1)", 100, 300, 250, 10)
    pp = a.slider("Photoperiod (h)", 12.0, 20.0, 16.0, 0.5)
    td = b.slider("Air temperature, light (C)", 18.0, 30.0, 23.0, 0.5)
    tn = b.slider("Air temperature, dark (C)", 16.0, 28.0, 20.0, 0.5)
    rh = c.slider("RH setpoint (%)", 50, 85, 68)
    ec = c.slider("EC (mS/cm)", 0.4, 2.4, 1.4, 0.1)
    dli = ppfd * pp * 3600 / 1e6
    st.write(f"DLI {dli:.1f} mol m-2 d-1" + (" - above the 17 mol limit used as a tipburn guard" if dli > 17 else ""))
    if st.button("Run 28-day prediction"):
        traj, summ = S.what_if(ppfd, pp, td, tn, rh, ec)
        m = st.columns(4)
        m[0].metric("Predicted fresh mass / plant", f"{summ['shoot_fw_g_plant']:.0f} g")
        m[1].metric("Predicted lighting energy", f"{summ['kwh_led']:.1f} kWh")
        m[2].metric("Predicted wall energy", f"{summ['kwh_wall']:.1f} kWh")
        m[3].metric("Predicted water", f"{summ['water_l_pod']:.1f} L")
        st.line_chart(traj.set_index("t_day")[["shoot_fw_g"]])
        st.line_chart(traj.set_index("t_day")[["air_t", "rh"]])

with tabs[7]:
    st.subheader("Create experiment")
    with st.form("newexp"):
        a, b, c = st.columns(3)
        year = a.number_input("Year", 2026, 2100, datetime.now(timezone.utc).year)
        code = b.text_input("Code (e.g. P0, U1, A1)", "P0")
        study = c.selectbox("Study", ["pilot", "uniformity", "A", "B", "C", "D"])
        title = st.text_input("Title", "Commissioning run")
        dclass = st.selectbox("Data class", ["pilot", "experimental", "simulated"])
        preset = st.selectbox("Treatments", ["All control (uniformity / pilot)", "Study A: C, L, H, N", "Study C: fixed vs adaptive"])
        onset = st.number_input("Treatment onset day", 0, 27, 10)
        seed = st.number_input("Randomisation seed (record it in the lab notebook)", 0, 2**31 - 1, 12345)
        day0 = st.text_input("Day 0 (UTC, ISO 8601)", datetime.now(timezone.utc).strftime("%Y-%m-%dT06:00:00Z"))
        if st.form_submit_button("Create"):
            from plantpulse.simulation.virtual_lab import CONTROL, TREATMENTS
            if preset.startswith("All"):
                tr, alloc = {"C": TREATMENTS["C"]}, {p: "C" for p in range(1, 5)}
            elif preset.startswith("Study A"):
                tr, alloc = dict(TREATMENTS), None
            else:
                tr, alloc = {"F": {"description": "Fixed lighting", "recipe": CONTROL}, "A": {"description": "Adaptive (MPC) lighting", "recipe": CONTROL}}, None
            try:
                new = S.create_experiment(db, int(year), code, study, title, dclass, tr, alloc, day0, int(seed), onset_day=int(onset))
                st.success(f"Created {new}; plant IDs {new}-P01-N01 ... assigned. Print labels from the plant table.")
            except Exception as e:  # noqa: BLE001
                st.error(str(e))
    if exp:
        st.subheader("Imaging schedule")
        with st.form("sched"):
            iv = st.number_input("Interval (min)", 10, 720, 120)
            ws = st.number_input("Window start (minute of day)", 0, 1439, 390)
            we = st.number_input("Window end (minute of day)", 0, 1439, 1290)
            stereo = st.checkbox("Stereo offsets (height)", True)
            if st.form_submit_button("Save schedule"):
                S.set_imaging_schedule(db, exp, int(iv), int(ws), int(we), stereo)
                st.success("Saved. Imaging is restricted to the photoperiod.")
        st.subheader("Log intervention")
        with st.form("interv"):
            u = st.selectbox("Unit", S.units(db, exp, unblind)["unit_id"].tolist())
            kind = st.selectbox("Kind", ["pH_adjust", "EC_adjust", "reservoir_refill", "solution_exchange", "door_open", "cleaning", "pest_check", "deviation", "other"])
            det = st.text_input("Detail")
            qv = st.number_input("Quantity", value=0.0)
            qu = st.text_input("Unit of quantity", "mL")
            op = st.text_input("Operator")
            if st.form_submit_button("Log") and op:
                db.add_intervention(u, kind, det, float(qv), qu, op)
                st.success("Logged.")

with tabs[8]:
    st.subheader("Export dataset bundle")
    sel = st.multiselect("Experiments", exps["experiment_id"].tolist() if len(exps) else [])
    ver = st.text_input("Version", "0.1.0")
    out_dir = st.text_input("Output directory", str(Path(root) / "export"))
    if st.button("Export") and sel:
        try:
            st.success(f"Wrote {S.export(db, store, sel, out_dir, ver)} (manifest with SHA-256, datapackage.json, README, LICENSE).")
        except Exception as e:  # noqa: BLE001
            st.error(str(e))
