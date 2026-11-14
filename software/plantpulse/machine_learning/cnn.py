"""Deep-learning models (optional; require PyTorch).

STATUS: this module could not be executed in the environment where the repository was created
(PyTorch was not installable), so it is UNTESTED code. It is included so that the planned
comparison (classical features vs CNN vs temporal vs multimodal) has a concrete starting point.
Run tests/test_cnn_optional.py after installing torch.

  PlantCNN        small ResNet-style regressor/classifier on per-plant crops (input: 3 x 128 x 128)
  TemporalGRU     GRU over daily feature vectors (unit or plant level)
  FusionNet       late fusion of CNN image embedding and an environment time-series embedding

Black-box caveats that must be addressed before any claim: inputs are colour-calibrated crops at a
fixed scale (document the crop size in mm); outputs are point estimates (use deep ensembles or MC
dropout for uncertainty); splits must be grouped by run (splits.grouped_splits); with fewer than
a few hundred independent plants, expect the classical models to win and report it if they do.
"""
from __future__ import annotations

try:
    import torch
    from torch import nn
    HAVE_TORCH = True
except Exception:  # noqa: BLE001
    HAVE_TORCH = False


def require_torch():
    if not HAVE_TORCH:
        raise ImportError("PyTorch is required for plantpulse.machine_learning.cnn (pip install torch)")


if HAVE_TORCH:

    class _Block(nn.Module):
        def __init__(self, cin, cout, stride):
            super().__init__()
            self.c1 = nn.Conv2d(cin, cout, 3, stride, 1, bias=False)
            self.b1 = nn.BatchNorm2d(cout)
            self.c2 = nn.Conv2d(cout, cout, 3, 1, 1, bias=False)
            self.b2 = nn.BatchNorm2d(cout)
            self.skip = None if stride == 1 and cin == cout else nn.Sequential(nn.Conv2d(cin, cout, 1, stride, bias=False), nn.BatchNorm2d(cout))

        def forward(self, x):
            y = torch.relu(self.b1(self.c1(x)))
            y = self.b2(self.c2(y))
            return torch.relu(y + (x if self.skip is None else self.skip(x)))

    class PlantCNN(nn.Module):
        """~0.7 M parameters. `n_out` = 1 for regression (log biomass) or number of classes."""

        def __init__(self, n_out: int = 1, embed: int = 128, dropout: float = 0.2):
            super().__init__()
            self.stem = nn.Sequential(nn.Conv2d(3, 24, 3, 2, 1, bias=False), nn.BatchNorm2d(24), nn.ReLU())
            self.body = nn.Sequential(_Block(24, 32, 2), _Block(32, 64, 2), _Block(64, embed, 2), nn.AdaptiveAvgPool2d(1), nn.Flatten())
            self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(embed, n_out))

        def embed(self, x):
            return self.body(self.stem(x))

        def forward(self, x):
            return self.head(self.embed(x))

    class TemporalGRU(nn.Module):
        """Sequence model over daily features: input (batch, days, n_features), output per day."""

        def __init__(self, n_features: int, hidden: int = 32, n_out: int = 1):
            super().__init__()
            self.gru = nn.GRU(n_features, hidden, batch_first=True)      # causal: output at day d sees days <= d only
            self.head = nn.Linear(hidden, n_out)

        def forward(self, x):
            h, _ = self.gru(x)
            return self.head(h)

    class FusionNet(nn.Module):
        """Late fusion: image embedding (CNN) + environment sequence embedding (GRU) -> prediction."""

        def __init__(self, n_env: int, n_out: int = 1, embed: int = 128, hidden: int = 32):
            super().__init__()
            self.cnn = PlantCNN(n_out=1, embed=embed)
            self.env = nn.GRU(n_env, hidden, batch_first=True)
            self.head = nn.Sequential(nn.Linear(embed + hidden, 64), nn.ReLU(), nn.Dropout(0.2), nn.Linear(64, n_out))

        def forward(self, image, env_seq):
            z_img = self.cnn.embed(image)
            _, h = self.env(env_seq)
            return self.head(torch.cat([z_img, h[-1]], dim=1))

    def train_regressor(model, loader_train, loader_val, epochs: int = 40, lr: float = 1e-3, weight_decay: float = 1e-4, device: str = "cpu"):
        """Minimal training loop with early stopping on the (group-disjoint) validation loader."""
        model.to(device)
        opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
        best, best_state, patience = float("inf"), None, 0
        for _ in range(epochs):
            model.train()
            for x, y in loader_train:
                opt.zero_grad()
                loss = nn.functional.smooth_l1_loss(model(x.to(device)).squeeze(-1), y.to(device))
                loss.backward()
                opt.step()
            model.eval()
            with torch.no_grad():
                val = sum(nn.functional.l1_loss(model(x.to(device)).squeeze(-1), y.to(device), reduction="sum").item() for x, y in loader_val)
            if val < best:
                best, best_state, patience = val, {k: v.clone() for k, v in model.state_dict().items()}, 0
            else:
                patience += 1
                if patience >= 6:
                    break
        if best_state:
            model.load_state_dict(best_state)
        return model


def crop_plant(bgr, centre_px, mm_per_px: float, size_mm: float = 320.0, out_px: int = 128):
    """Fixed-physical-size crop around a plant centre, resized to out_px (keeps scale information)."""
    import cv2
    import numpy as np
    half = size_mm / mm_per_px / 2
    x, y = centre_px
    M = np.array([[out_px / (2 * half), 0, -(x - half) * out_px / (2 * half)], [0, out_px / (2 * half), -(y - half) * out_px / (2 * half)]], np.float32)
    return cv2.warpAffine(bgr, M, (out_px, out_px), flags=cv2.INTER_AREA, borderValue=(0, 0, 0))
