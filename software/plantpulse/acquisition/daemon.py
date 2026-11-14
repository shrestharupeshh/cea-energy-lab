"""Acquisition daemon: one process on the central computer.

  python -m plantpulse.acquisition.daemon --experiment EXP-2027-P0 --ports /dev/ttyACM0,/dev/ttyACM1 ...
  python -m plantpulse.acquisition.daemon --experiment EXP-2027-S1 --sim 4 --speed 600 --duration 60

Loop: poll nodes -> buffer frames -> flush to the raw store every minute -> keep-alive PING ->
apply the day's recipe through the safety envelope -> raise alarms. Camera capture on real
hardware is delegated to the camera nodes (Pi Zero 2 W, picamera2); see docs/architecture.
In --sim mode the nodes are SimNode objects and the experiment must have data_class 'simulated'.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from ..config import DATA_ROOT
from ..data.db import MetaDB
from ..data.store import Store
from . import node_logic as nlg
from .node_client import NodeClient, SerialTransport
from .safety import Envelope, check_setpoints, to_node_command
from .sim_node import SimNode


def alarms(frame: dict, sp: dict) -> list[str]:
    out = [f"fault:{name}" for bit, name in nlg.FAULT_NAMES.items() if frame.get("faults", 0) & bit]
    if frame.get("mode") == nlg.AUTO and "air_t_day" in sp and frame.get("u_led", 0) > 0.05 and abs(frame["air_t"] - sp["air_t_day"]) > 3.0:
        out.append("air_temperature_deviation")
    if frame.get("pump") and frame.get("flow_hz", 1) < 5:
        out.append("no_flow")
    if frame.get("ph") == frame.get("ph") and not 5.2 <= frame.get("ph", 5.8) <= 6.5:
        out.append("ph_out_of_band")
    return out


def run(experiment: str, clients: dict[int, NodeClient], db: MetaDB, store: Store, duration_s: float, sim_nodes: dict | None = None,
        speed: float = 1.0, flush_s: float = 60.0, log=print):
    exp = db.q("SELECT data_class FROM experiment WHERE experiment_id=?", (experiment,))
    if exp.empty:
        raise SystemExit(f"unknown experiment {experiment}")
    if sim_nodes and exp.data_class[0] != "simulated":
        raise SystemExit("refusing to write simulated node data into a non-simulated experiment")
    units = db.q("SELECT u.pod, u.unit_id, t.recipe_json FROM unit u JOIN treatment t USING (treatment_id) WHERE u.experiment_id=?", (experiment,))
    current: dict[int, dict] = {}
    sim_clock = [time.time()]
    for _, u in units.iterrows():
        pod = int(u.pod)
        if pod not in clients:
            continue
        c = clients[pod]
        c.send(f"TIME epoch={int(sim_clock[0])}")
        recipe = {k: v for k, v in json.loads(u.recipe_json).items() if k != "ec"}
        ok, sp, why = check_setpoints(recipe, None, Envelope(), "recipe")
        db.log_setpoint(u.unit_id, "recipe", json.dumps(recipe), ok, "; ".join(why))
        if ok:
            ppfd_full = sim_nodes[pod].env.ppfd_full if sim_nodes else 338.0
            c.send(to_node_command(sp, ppfd_full).rsplit(" id=", 1)[0])
            c.send("MODE AUTO")
            current[pod] = sp
    t_end, last_flush, n_frames, seen = time.time() + duration_s, time.time(), 0, set()
    while time.time() < t_end:
        if sim_nodes:
            for node in sim_nodes.values():
                for _ in range(int(speed)):
                    node.step(1.0)
            sim_clock[0] += speed
        for pod, c in clients.items():
            n_frames += c.poll()
            c.send("PING")
            if c.last_frame:
                for a in alarms(c.last_frame, current.get(pod, {})):
                    if (pod, a) not in seen:
                        seen.add((pod, a))
                        log(f"ALARM pod {pod}: {a}")
        if time.time() - last_flush >= flush_s / (speed if sim_nodes else 1.0):
            for pod, c in clients.items():
                store.append_raw(experiment, pod, c.drain())
            last_flush = time.time()
        time.sleep(0 if sim_nodes else 0.2)
    for pod, c in clients.items():
        store.append_raw(experiment, pod, c.drain())
    return n_frames


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment", required=True)
    ap.add_argument("--root", default=str(DATA_ROOT))
    ap.add_argument("--ports", default="")
    ap.add_argument("--sim", type=int, default=0, help="number of simulated pods")
    ap.add_argument("--speed", type=float, default=1.0, help="simulated seconds per loop iteration")
    ap.add_argument("--duration", type=float, default=3600.0, help="wall-clock seconds to run")
    a = ap.parse_args()
    root = Path(a.root)
    db, store = MetaDB(root / "plantpulse_meta.db"), Store(root)
    sim_nodes = None
    if a.sim:
        sim_nodes = {p: SimNode(pod=p, seed=p) for p in range(1, a.sim + 1)}
        t0 = [time.time()]
        clients = {p: NodeClient(n, pod=p) for p, n in sim_nodes.items()}
    else:
        clients = {}
        for port in filter(None, a.ports.split(",")):
            c = NodeClient(SerialTransport(port))
            time.sleep(2.0)
            c.poll()
            if c.pod is None:
                raise SystemExit(f"no hello frame from {port}")
            clients[c.pod] = c
    n = run(a.experiment, clients, db, store, a.duration, sim_nodes, a.speed)
    print(f"{datetime.now(timezone.utc):%H:%M:%S} stored {n} frames")
    db.close()


if __name__ == "__main__":
    main()
