import pytest


@pytest.fixture(scope="session")
def mini_lab(tmp_path_factory):
    """A tiny simulated experiment (2 runs x 2 pods, 6 days) shared by the integration tests."""
    from plantpulse.data.db import MetaDB
    from plantpulse.simulation.virtual_lab import run_virtual_experiment
    root = tmp_path_factory.mktemp("lab")
    db = MetaDB(root / "plantpulse_meta.db")
    out = []
    for i, alloc in enumerate(({1: "C", 2: "L"}, {1: "L", 2: "C"})):
        out.append(run_virtual_experiment(root, f"EXP-2027-M{i + 1}", alloc, days=6, onset_day=2, seed=40 + i, db=db,
                                          image_width=640, serial_harvest={3: 2}))
    db.close()
    return root, out
