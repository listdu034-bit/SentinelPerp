"""One versioned numerical representation shared by history and live windows."""

import json

import numpy as np
import pandas as pd

REPRESENTATION = "market-window-v1"
DIMENSIONS = 1536
METRICS = (
    "price_change_pct",
    "volatility",
    "amplitude_pct",
    "buy_sell_ratio",
    "oi_change_pct",
    "oi_volume_ratio",
    "funding_rate",
    "funding_trend",
    "obi",
    "liq_imbalance",
    "liquidation_intensity",
    "quality",
)


def feature_snapshot(rows):
    if not rows:
        raise ValueError("No market features in window")
    frame = pd.DataFrame([dict(row) for row in rows])
    metrics = {}
    for key in METRICS:
        series = pd.to_numeric(frame.get(key, pd.Series(dtype=float)), errors="coerce")
        finite = series[np.isfinite(series)]
        metrics[key] = round(float(finite.mean()), 8) if len(finite) else None
    return {"representation": REPRESENTATION, "minutes": len(rows), "metrics": metrics}


def embedding_text(snapshot):
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)


def valid_vector(vector):
    result = np.asarray(vector, dtype=np.float32)
    if (
        result.shape != (DIMENSIONS,)
        or not np.isfinite(result).all()
        or np.linalg.norm(result) == 0
    ):
        raise ValueError("Embedding must be a finite nonzero 1536-dimensional vector")
    return result
