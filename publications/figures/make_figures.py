"""Regenerate figures. Today only design-calculation and simulation figures can be produced; each is
watermarked with its evidence class. When real data exist, point --data at the dataset bundle."""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from plantpulse.digital_twin import crop
from plantpulse.optimization.nsga2 import nsga2
from plantpulse.optimization.pareto import knee_point
from plantpulse.optimization.problem import LightingProblem

OUT = Path(__file__).parent


def mark(ax, text):
    ax.text(0.99, 0.02, text, transform=ax.transAxes, ha="right", va="bottom", fontsize=8, color="0.45", style="italic")


def fig_light_response():
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.6))
    days = np.arange(1, 29)
    for ppfd, c in ((125, "#7a9cc6"), (200, "#3d6fa5"), (250, "#1f4e79"), (300, "#0b2a45")):
        r = crop.simulate_schedule(28, ppfd, 16)
        ax[0].plot(days, r["shoot_fw_g"][r["day_end_index"]], color=c, label=f"{ppfd}")
    ax[0].set(xlabel="Days after transplant", ylabel="Predicted shoot fresh mass (g per plant)")
    ax[0].legend(title="PPFD (µmol m$^{-2}$ s$^{-1}$), 16 h", frameon=False, fontsize=8)
    mark(ax[0], "MODEL PREDICTION - uncalibrated")
    dli = 14.4
    pp = np.linspace(12, 20, 9)
    fw = [crop.simulate_schedule(28, dli * 1e6 / 3600 / h, h)["shoot_fw_g"][-1] for h in pp]
    ax[1].plot(pp, fw, "o-", color="#1f4e79")
    ax[1].set(xlabel="Photoperiod (h) at constant DLI 14.4 mol m$^{-2}$ d$^{-1}$", ylabel="Predicted fresh mass at day 28 (g)")
    mark(ax[1], "MODEL PREDICTION - hypothesis for Study C")
    for a in ax:
        a.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "fig_twin_light_response_PREDICTED.png", dpi=180)


def fig_pareto():
    prob = LightingProblem(objectives=("neg_fw", "kwh_led"))
    res = nsga2(prob.evaluate, prob.bounds, pop_size=40, generations=25, seed=1, x_init=prob.baseline())
    F = res["F"][res["pareto"]]
    b = prob.evaluate(prob.baseline())["f"]
    k = knee_point(F)
    fig, ax = plt.subplots(figsize=(5.2, 3.8))
    ax.scatter(F[:, 1], -F[:, 0], s=18, color="#1f4e79", label="Predicted Pareto set (feasible)")
    ax.scatter([b[1]], [-b[0]], marker="s", s=45, color="#c0392b", label="Fixed 250 µmol, 16 h")
    ax.scatter([F[k, 1]], [-F[k, 0]], marker="*", s=130, color="#e67e22", label="Knee point")
    ax.set(xlabel="Lighting energy per pod and cycle (kWh)", ylabel="Shoot fresh mass (g per plant)")
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    mark(ax, "MODEL PREDICTION - constraints: DLI 6-17, PPFD 100-300, 12-20 h")
    fig.tight_layout()
    fig.savefig(OUT / "fig_pareto_energy_biomass_PREDICTED.png", dpi=180)
    return F, b


if __name__ == "__main__":
    fig_light_response()
    F, b = fig_pareto()
    print("baseline fw %.0f g, %.1f kWh; front spans %.0f-%.0f g, %.1f-%.1f kWh" % (-b[0], b[1], -F[:, 0].max(), -F[:, 0].min(), F[:, 1].min(), F[:, 1].max()))
