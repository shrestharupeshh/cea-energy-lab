"""Mechanistic lettuce growth model.

Core: the two-state model of Van Henten (1994, Agricultural Systems 45:55-72) with states
non-structural dry weight X_nsdw and structural dry weight X_sdw (g m-2 ground area).
Parameter values are those commonly reproduced from that paper in the control literature; they
were NOT checked against the original in this project and must be before publication.

Extensions (clearly separated, all hypotheses to be calibrated on Study A/B data):
  * supra-optimal temperature penalty on gross photosynthesis (Van Henten's response is monotonic);
  * nutrient (EC) limitation factor;
  * canopy transpiration (big-leaf Penman-Monteith form);
  * fresh mass via dry-matter content.

Everything this module returns is a PREDICTION.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np

UMOL_PER_J = 4.6          # photons per joule of PAR for phosphor-white LEDs (approx.)


@dataclass(frozen=True)
class CropParams:
    # --- Van Henten (1994)
    c_alpha: float = 0.68          # CO2 -> CH2O conversion (30/44)
    c_beta: float = 0.80           # yield factor, CH2O -> structural dry weight
    c_gr_max: float = 5.0e-6       # s-1, saturation growth rate at 20 C
    c_gamma: float = 1.0
    c_q10_gr: float = 1.6
    c_resp_sht: float = 3.47e-7    # s-1, shoot maintenance respiration at 25 C
    c_resp_rt: float = 1.16e-7     # s-1, root maintenance respiration at 25 C
    c_q10_resp: float = 2.0
    c_tau: float = 0.07            # root fraction of structural dry weight
    c_k: float = 0.9               # extinction coefficient
    c_lar: float = 75.0e-3         # m2 leaf per g shoot structural dry weight
    c_omega: float = 1.83e-3       # g m-3 ppm-1, CO2 density
    c_Gamma: float = 40.0          # ppm, CO2 compensation point at 20 C
    c_q10_Gamma: float = 2.0
    c_eps: float = 17.0e-6         # g J-1, light-use efficiency at very high CO2
    g_bnd: float = 0.007           # m s-1 boundary layer conductance
    g_stm: float = 0.005           # m s-1 stomatal conductance
    c_car1: float = -1.32e-5
    c_car2: float = 5.94e-4
    c_car3: float = -2.64e-3
    # --- extensions (assumptions pending calibration)
    t_opt_high: float = 26.0       # C, above this gross photosynthesis is penalised
    t_max: float = 40.0            # C, photosynthesis reaches zero
    ec_half: float = 0.25          # mS cm-1, EC at which nutrient factor = 0.5 (Michaelis-Menten form)
    ec_ref: float = 1.4            # mS cm-1, EC at which the factor is normalised to 1
    dm_content: float = 0.048      # g dry / g fresh shoot (declines with light; treated as constant here)
    r_b: float = 200.0             # s m-1 leaf boundary-layer resistance
    r_s_light: float = 200.0       # s m-1 stomatal resistance in light
    r_s_dark: float = 2000.0
    plant_density: float = 25.0    # plants m-2

    def with_(self, **kw) -> "CropParams":
        return replace(self, **kw)

    def to_dict(self) -> dict:
        return asdict(self)


def p_sat(t_c):
    return 610.94 * np.exp(17.625 * t_c / (t_c + 243.04))


def temp_penalty(t, p: CropParams):
    return np.clip((p.t_max - t) / (p.t_max - p.t_opt_high), 0.0, 1.0)


def nutrient_factor(ec, p: CropParams):
    f = lambda e: e / (e + p.ec_half)
    return np.clip(f(np.asarray(ec, float)) / f(p.ec_ref), 0.0, 1.15)


def gross_photosynthesis(x_sdw, par_w, co2, t, p: CropParams, ec=None):
    """Canopy gross CO2 assimilation, g CO2 m-2 s-1."""
    Gamma = p.c_Gamma * p.c_q10_Gamma ** ((t - 20.0) / 10.0)
    eps = p.c_eps * (co2 - Gamma) / (co2 + 2.0 * Gamma)
    g_car = np.maximum(p.c_car1 * t**2 + p.c_car2 * t + p.c_car3, 1e-5)
    g_co2 = 1.0 / (1.0 / p.g_bnd + 1.0 / p.g_stm + 1.0 / g_car)
    dco2 = np.maximum(co2 - Gamma, 0.0)
    denom = eps * par_w + g_co2 * p.c_omega * dco2
    f_max = np.where(denom > 0, eps * par_w * g_co2 * p.c_omega * dco2 / np.maximum(denom, 1e-12), 0.0)
    interception = 1.0 - np.exp(-p.c_k * p.c_lar * (1.0 - p.c_tau) * x_sdw)
    f = interception * f_max * temp_penalty(t, p)
    if ec is not None:
        f = f * nutrient_factor(ec, p)
    return f


def derivatives(x_nsdw, x_sdw, par_w, co2, t, p: CropParams, ec=None):
    """Return (dX_nsdw/dt, dX_sdw/dt) in g m-2 s-1."""
    f_phot = gross_photosynthesis(x_sdw, par_w, co2, t, p, ec)
    r_gr = p.c_gr_max * x_nsdw / (p.c_gamma * x_sdw + x_nsdw + 1e-12) * p.c_q10_gr ** ((t - 20.0) / 10.0)
    f_resp = (p.c_resp_sht * (1 - p.c_tau) + p.c_resp_rt * p.c_tau) * x_sdw * p.c_q10_resp ** ((t - 25.0) / 10.0)
    d_s = r_gr * x_sdw
    d_n = p.c_alpha * f_phot - d_s - f_resp - (1 - p.c_beta) / p.c_beta * d_s
    return d_n, d_s


def lai(x_sdw, p: CropParams):
    return p.c_lar * (1.0 - p.c_tau) * x_sdw


def transpiration(x_sdw, par_w, t, rh, p: CropParams):
    """Canopy transpiration, g H2O m-2 s-1 (big-leaf Penman-Monteith form)."""
    L = lai(x_sdw, p)
    cover = 1.0 - np.exp(-p.c_k * L)
    rn = par_w * cover                                    # W m-2 absorbed short-wave (LED: mostly PAR)
    es = p_sat(t)
    vpd = es * (1.0 - rh / 100.0)
    delta = es * 17.625 * 243.04 / (t + 243.04) ** 2      # Pa K-1
    gamma = 66.0
    r_s = np.where(par_w > 1.0, p.r_s_light, p.r_s_dark)
    lam_e = (delta * rn + 2.0 * cover * 1.2 * 1005.0 * vpd / p.r_b) / (delta + gamma * (1.0 + r_s / p.r_b))
    return np.maximum(lam_e, 0.0) / 2.45e6 * 1000.0


@dataclass
class CropState:
    x_nsdw: float
    x_sdw: float

    @classmethod
    def from_seedling(cls, shoot_dw_g_per_plant: float, p: CropParams, nsdw_frac: float = 0.25) -> "CropState":
        total = shoot_dw_g_per_plant * p.plant_density / (1.0 - p.c_tau)
        return cls(x_nsdw=nsdw_frac * total, x_sdw=(1 - nsdw_frac) * total)

    @property
    def total(self) -> float:
        return self.x_nsdw + self.x_sdw


def outputs(x_nsdw, x_sdw, p: CropParams) -> dict:
    """Per-plant observable quantities derived from the states."""
    shoot_dw_m2 = (1.0 - p.c_tau) * (x_nsdw + x_sdw)
    return {
        "shoot_dw_g": shoot_dw_m2 / p.plant_density,
        "shoot_fw_g": shoot_dw_m2 / p.plant_density / p.dm_content,
        "leaf_area_cm2": lai(x_sdw, p) / p.plant_density * 1e4,
        "lai": lai(x_sdw, p),
    }


def simulate(ppfd, co2, t_air, hours, p: CropParams = CropParams(), init_shoot_dw: float = 0.06,
             ec=None, rh=None, dt_s: float = 600.0, substeps: int | None = None) -> dict:
    """Integrate the crop model over piecewise-constant inputs.

    ppfd, co2, t_air (and optionally ec, rh): arrays, one value per input interval of length
    `hours` (scalar, h). Returns arrays sampled at the END of each interval, plus cumulative
    transpiration per plant (g).
    """
    ppfd = np.atleast_1d(np.asarray(ppfd, float))
    n = len(ppfd)
    co2 = np.broadcast_to(np.asarray(co2, float), (n,))
    t_air = np.broadcast_to(np.asarray(t_air, float), (n,))
    ec_a = None if ec is None else np.broadcast_to(np.asarray(ec, float), (n,))
    rh_a = np.broadcast_to(np.asarray(70.0 if rh is None else rh, float), (n,))
    k = substeps or max(int(round(hours * 3600.0 / dt_s)), 1)
    h = hours * 3600.0 / k
    s = CropState.from_seedling(init_shoot_dw, p)
    xn, xs = s.x_nsdw, s.x_sdw
    out_n, out_s, out_w = np.empty(n), np.empty(n), np.empty(n)
    water = 0.0
    for i in range(n):
        par = ppfd[i] / UMOL_PER_J
        e = None if ec_a is None else ec_a[i]
        for _ in range(k):
            # Heun (RK2) step
            dn1, ds1 = derivatives(xn, xs, par, co2[i], t_air[i], p, e)
            dn2, ds2 = derivatives(xn + h * dn1, xs + h * ds1, par, co2[i], t_air[i], p, e)
            xn = max(xn + 0.5 * h * (dn1 + dn2), 0.0)
            xs = max(xs + 0.5 * h * (ds1 + ds2), 1e-9)
            water += float(transpiration(xs, par, t_air[i], rh_a[i], p)) * h
        out_n[i], out_s[i], out_w[i] = xn, xs, water / p.plant_density
    res = outputs(out_n, out_s, p)
    res.update({"x_nsdw": out_n, "x_sdw": out_s, "transp_g_plant_cum": out_w})
    return res


def simulate_schedule(days: int, ppfd: float | np.ndarray, photoperiod_h: float | np.ndarray, t_day=23.0, t_night=20.0,
                      co2=420.0, ec=None, rh=70.0, p: CropParams = CropParams(), init_shoot_dw: float = 0.06) -> dict:
    """Convenience wrapper: hourly resolution, day d has `photoperiod_h[d]` hours at `ppfd[d]`.
    Returns hourly arrays plus `day_end_index` for sampling at the end of each day."""
    ppfd_d = np.broadcast_to(np.asarray(ppfd, float), (days,))
    pp_d = np.broadcast_to(np.asarray(photoperiod_h, float), (days,))
    td = np.broadcast_to(np.asarray(t_day, float), (days,))
    tn = np.broadcast_to(np.asarray(t_night, float), (days,))
    hour = np.arange(24)
    light = (hour[None, :] < np.ceil(pp_d)[:, None]).astype(float)
    # fractional last hour
    frac = pp_d - np.floor(pp_d)
    for d in range(days):
        if frac[d] > 0:
            light[d, int(np.floor(pp_d[d]))] = frac[d]
    ppfd_h = (light * ppfd_d[:, None]).ravel()
    t_h = np.where(light > 0, td[:, None], tn[:, None]).ravel()
    ec_h = None if ec is None else np.repeat(np.broadcast_to(np.asarray(ec, float), (days,)), 24)
    res = simulate(ppfd_h, co2, t_h, 1.0, p, init_shoot_dw, ec=ec_h, rh=rh, substeps=4)
    res["day_end_index"] = np.arange(1, days + 1) * 24 - 1
    return res
