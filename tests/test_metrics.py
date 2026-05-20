"""Tests for the inspection metrics."""

from __future__ import annotations

import numpy as np

from optsim.analysis import (
    compute_metrics,
    edge_profile,
    histogram,
    michelson_contrast,
    snr_db,
)


def test_michelson_uniform() -> None:
    img = np.full((64, 64), 128, dtype=np.uint8)
    assert michelson_contrast(img) == 0.0


def test_michelson_step() -> None:
    img = np.zeros((64, 64), dtype=np.uint8)
    img[:, 32:] = 255
    c = michelson_contrast(img)
    assert abs(c - 1.0) < 1e-3


def test_snr_uniform_high() -> None:
    img = np.full((64, 64), 100, dtype=np.uint8)
    img = img + np.random.default_rng(0).normal(0, 1.0, img.shape).astype(np.int16)
    img = np.clip(img, 0, 255).astype(np.uint8)
    assert snr_db(img) > 20.0


def test_histogram_uniform() -> None:
    img = np.full((10, 10), 128, dtype=np.uint8)
    counts, _ = histogram(img)
    assert counts.sum() == 100


def test_edge_profile_basic() -> None:
    img = np.zeros((100, 100), dtype=np.float64)
    img[:, 50:] = 1.0
    p = edge_profile(img, (10.0, 50.0), (90.0, 50.0))
    assert p.intensity[0] < 0.1
    assert p.intensity[-1] > 0.9


def test_compute_metrics_returns_all_fields() -> None:
    rng = np.random.default_rng(42)
    img = (rng.normal(1500, 80, (256, 256))).clip(0, 4095).astype(np.uint16)
    m = compute_metrics(img)
    assert m.mean > 0
    assert m.std > 0
    assert m.michelson > 0
    assert 0.0 <= m.saturated_fraction <= 1.0
