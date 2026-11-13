"""Host-side node client: transport-agnostic (real serial port or SimNode), parses frames,
synchronises clocks, tracks acknowledgements, and buffers frames for the store."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone

import pandas as pd

from ..data.timesync import ClockModel

FRAME_COLUMNS = ["seq", "ms", "mode", "faults", "air_t", "rh", "co2", "par_raw", "sol_t", "sol_t2", "ph", "ec", "res_raw", "flow_hz",
                 "tach0_hz", "tach1_hz", "led_w", "act_w", "led_wh", "act_wh", "u_heat", "u_fan", "u_mix", "u_led", "pump", "humid",
                 "topup", "door", "leak", "flo", "fhi", "gpos"]


class SerialTransport:
    """Thin wrapper around pyserial (imported lazily so the package works without it)."""

    def __init__(self, port: str, baud: int = 115200):
        import serial  # type: ignore
        self.ser = serial.Serial(port, baud, timeout=0.05)

    def write(self, line: str):
        self.ser.write((line.strip() + "\n").encode())

    def readlines(self) -> list[str]:
        return [ln.decode(errors="replace").strip() for ln in self.ser.readlines()]


class NodeClient:
    def __init__(self, transport, pod: int | None = None, clock=time.time):
        self.t = transport
        self.pod = pod
        self.clock = clock
        self.clk = ClockModel()
        self.frames: list[dict] = []
        self.events: list[dict] = []
        self.acks: dict[int, dict] = {}
        self.hello: dict | None = None
        self.bad_lines = 0
        self._id = 0
        self.last_frame: dict | None = None
        self.last_seq: int | None = None
        self.dropped = 0

    def send(self, command: str) -> int:
        """Send a command (without id) and return the id to look up in `acks`."""
        self._id += 1
        self.t.write(f"{command} id={self._id}")
        return self._id

    def poll(self) -> int:
        """Read and parse everything available. Returns the number of sensor frames received."""
        n = 0
        now = self.clock()
        for line in self.t.readlines():
            if not line:
                continue
            try:
                m = json.loads(line.replace("nan", "NaN"))
            except json.JSONDecodeError:
                self.bad_lines += 1
                continue
            kind = m.get("t")
            if kind == "S":
                if self.pod is not None and m.get("pod") != self.pod:
                    self.bad_lines += 1
                    continue
                utc = self.clk.update(m["ms"], now)
                m["utc"] = datetime.fromtimestamp(utc, timezone.utc)
                m["host_utc"] = datetime.fromtimestamp(now, timezone.utc)
                if self.last_seq is not None and m["seq"] > self.last_seq + 1:
                    self.dropped += m["seq"] - self.last_seq - 1
                self.last_seq = m["seq"]
                self.frames.append(m)
                self.last_frame = m
                n += 1
            elif kind == "A":
                self.acks[m.get("id", -1)] = m
            elif kind == "E":
                m["host_utc"] = datetime.fromtimestamp(now, timezone.utc)
                self.events.append(m)
            elif kind == "H":
                self.hello = m
                self.pod = self.pod or m.get("pod")
                self.clk.reset()
        return n

    def drain(self) -> pd.DataFrame:
        """Return buffered frames as a DataFrame and clear the buffer."""
        frames, self.frames = self.frames, []
        if not frames:
            return pd.DataFrame()
        df = pd.DataFrame(frames)
        keep = ["utc", "host_utc", "pod"] + [c for c in FRAME_COLUMNS if c in df]
        return df[keep]
