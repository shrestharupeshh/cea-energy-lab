"""Timestamp synchronisation between node clocks (millisecond uptime counters) and host UTC."""
from __future__ import annotations

import numpy as np

NOMINAL = 1e-3   # seconds per node millisecond


class ClockModel:
    """Online estimate of utc = offset + node_ms / 1000.

    Serial transport and host polling only ever make arrival times LATE, never early, so within a
    sliding window the minimum of (host arrival - node time) is the best estimate of the offset.
    The window (default 10 min of 1 Hz frames) is short enough that crystal drift (tens of ppm,
    i.e. tens of milliseconds per 10 min) is tracked by the moving minimum; no slope is fitted,
    because batching of arrivals makes short-window slope estimates noisy. Long-term drift is
    reported for diagnostics from the change of the offset since the first window."""

    def __init__(self, window: int = 600):
        self.window = window
        self.reset()

    def reset(self):
        self.ms: list[float] = []
        self.utc: list[float] = []
        self.offset = None
        self._first = None

    def update(self, node_ms: float, host_utc_s: float) -> float:
        if self.ms and node_ms < self.ms[-1]:           # node rebooted: uptime counter restarted
            self.reset()
        self.ms.append(node_ms)
        self.utc.append(host_utc_s)
        if len(self.ms) > self.window:
            self.ms.pop(0)
            self.utc.pop(0)
        self.offset = float(np.min(np.asarray(self.utc) - NOMINAL * np.asarray(self.ms)))
        if self._first is None and len(self.ms) >= min(self.window, 60):
            self._first = (node_ms, self.offset)
        return self.to_utc(node_ms)

    def to_utc(self, node_ms: float) -> float:
        return self.offset + NOMINAL * node_ms

    @property
    def drift_ppm(self) -> float:
        """Node clock rate error relative to the host, from the offset change since start-up."""
        if self._first is None or not self.ms or self.ms[-1] - self._first[0] < 600_000:
            return float("nan")
        return (self.offset - self._first[1]) / ((self.ms[-1] - self._first[0]) * NOMINAL) * 1e6
