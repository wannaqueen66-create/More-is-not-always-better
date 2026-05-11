from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PolygonAOI:
    class_name: str
    polygon_id: int
    points: List[Tuple[float, float]]


def load_aoi_json(path: str | Path) -> List[PolygonAOI]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    aois: list[PolygonAOI] = []
    if isinstance(data.get("aoi_classes"), dict):
        for class_name, polygons in data["aoi_classes"].items():
            aois.extend(_polygons_from_items(class_name, polygons))
        return aois

    if isinstance(data.get("classes"), dict):
        for class_name, polygons in data["classes"].items():
            aois.extend(_polygons_from_items(class_name, polygons))
        return aois

    if isinstance(data.get("aois"), list):
        class_counts: dict[str, int] = {}
        for item in data["aois"]:
            class_name = str(item.get("class_name") or item.get("name") or item.get("class") or "AOI")
            points = _extract_points(item)
            if not points:
                continue
            class_counts[class_name] = class_counts.get(class_name, 0) + 1
            aois.append(PolygonAOI(class_name, class_counts[class_name], points))
        return aois

    raise ValueError(f"Unsupported AOI JSON format: {path}")


def _polygons_from_items(class_name: str, polygons: object) -> list[PolygonAOI]:
    out: list[PolygonAOI] = []
    if not isinstance(polygons, list):
        return out
    for idx, item in enumerate(polygons, start=1):
        points = _extract_points(item)
        if points:
            out.append(PolygonAOI(str(class_name), idx, points))
    return out


def _extract_points(item: object) -> list[tuple[float, float]]:
    if isinstance(item, dict):
        raw = item.get("points") or item.get("polygon") or item.get("vertices")
    else:
        raw = item
    points: list[tuple[float, float]] = []
    if not isinstance(raw, list):
        return points
    for point in raw:
        if isinstance(point, dict):
            x = point.get("x")
            y = point.get("y")
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            x, y = point[0], point[1]
        else:
            continue
        points.append((float(x), float(y)))
    return points


def point_in_poly(
    x: np.ndarray,
    y: np.ndarray,
    poly: List[Tuple[float, float]],
    boundary_eps: float = 1e-6,
) -> np.ndarray:
    n = len(poly)
    if n < 3:
        return np.zeros_like(x, dtype=bool)

    px = np.array([p[0] for p in poly], dtype=float)
    py = np.array([p[1] for p in poly], dtype=float)
    bbox = (
        (x >= np.nanmin(px) - boundary_eps)
        & (x <= np.nanmax(px) + boundary_eps)
        & (y >= np.nanmin(py) - boundary_eps)
        & (y <= np.nanmax(py) + boundary_eps)
    )
    inside = np.zeros_like(x, dtype=bool)
    if not np.any(bbox):
        return inside

    xx = x[bbox].astype(float)
    yy = y[bbox].astype(float)
    on_edge = np.zeros_like(xx, dtype=bool)

    j = n - 1
    for i in range(n):
        x1, y1 = px[j], py[j]
        x2, y2 = px[i], py[i]
        minx, maxx = min(x1, x2), max(x1, x2)
        miny, maxy = min(y1, y2), max(y1, y2)
        seg_bbox = (
            (xx >= minx - boundary_eps)
            & (xx <= maxx + boundary_eps)
            & (yy >= miny - boundary_eps)
            & (yy <= maxy + boundary_eps)
        )
        cross = (xx - x1) * (y2 - y1) - (yy - y1) * (x2 - x1)
        on_edge |= seg_bbox & (np.abs(cross) <= boundary_eps)
        j = i

    ray_inside = np.zeros_like(xx, dtype=bool)
    j = n - 1
    for i in range(n):
        xi, yi = px[i], py[i]
        xj, yj = px[j], py[j]
        intersects = ((yi > yy) != (yj > yy)) & (
            xx < (xj - xi) * (yy - yi) / ((yj - yi) + 1e-12) + xi
        )
        ray_inside ^= intersects
        j = i

    inside[bbox] = ray_inside | on_edge
    return inside


def compute_metrics(
    df: pd.DataFrame,
    aois: List[PolygonAOI],
    dwell_mode: str = "fixation",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    _require_eye_columns(df)
    x = pd.to_numeric(df["Gaze Point X[px]"], errors="coerce").to_numpy()
    y = pd.to_numeric(df["Gaze Point Y[px]"], errors="coerce").to_numpy()
    t = pd.to_numeric(df["Recording Time Stamp[ms]"], errors="coerce").to_numpy()
    t0 = float(np.nanmin(t)) if np.isfinite(t).any() else np.nan
    finite_xy = np.isfinite(x) & np.isfinite(y)

    per_poly_rows: list[dict] = []
    class_to_masks: Dict[str, List[np.ndarray]] = {}
    for aoi in aois:
        mask = point_in_poly(x, y, aoi.points) & finite_xy
        class_to_masks.setdefault(aoi.class_name, []).append(mask)
        per_poly_rows.append(_metric_row(df.loc[mask], t0, aoi.class_name, dwell_mode, {
            "polygon_id": aoi.polygon_id,
            "samples": int(mask.sum()),
        }))

    per_class_rows: list[dict] = []
    for class_name, masks in class_to_masks.items():
        union = np.logical_or.reduce(masks) if masks else np.zeros_like(x, dtype=bool)
        per_class_rows.append(_metric_row(df.loc[union], t0, class_name, dwell_mode, {
            "polygon_count": len(masks),
            "samples": int(union.sum()),
        }))

    return pd.DataFrame(per_poly_rows), pd.DataFrame(per_class_rows)


def compute_timebin_metrics(
    df: pd.DataFrame,
    aois: List[PolygonAOI],
    bin_size_ms: int = 2000,
    eye_offset_ms: float = 0.0,
    dwell_mode: str = "fixation",
) -> pd.DataFrame:
    _require_eye_columns(df)
    if bin_size_ms <= 0:
        raise ValueError("bin_size_ms must be positive")

    out = df.copy()
    t = pd.to_numeric(out["Recording Time Stamp[ms]"], errors="coerce")
    if not t.notna().any():
        return pd.DataFrame()
    aligned_ms = t - t.min() + float(eye_offset_ms or 0.0)
    out["eye_aligned_ms"] = aligned_ms
    out["bin_index"] = np.floor(aligned_ms / bin_size_ms).astype("Int64")

    rows: list[dict] = []
    for bin_index, sub in out.dropna(subset=["bin_index"]).groupby("bin_index", sort=True):
        bin_start_ms = int(bin_index) * bin_size_ms
        bin_end_ms = bin_start_ms + bin_size_ms
        _, class_df = compute_metrics(sub, aois, dwell_mode=dwell_mode)
        if class_df.empty:
            rows.append({
                "bin_index": int(bin_index),
                "bin_start_ms": bin_start_ms,
                "bin_end_ms": bin_end_ms,
                "class_name": "",
                "polygon_count": 0,
                "samples": 0,
                "dwell_time_ms": np.nan,
                "fixation_count": 0,
                "TTFF_ms": np.nan,
            })
            continue
        class_df = class_df.copy()
        class_df.insert(0, "bin_end_ms", bin_end_ms)
        class_df.insert(0, "bin_start_ms", bin_start_ms)
        class_df.insert(0, "bin_index", int(bin_index))
        rows.extend(class_df.to_dict("records"))
    return pd.DataFrame(rows)


def eye_file_stats(df: pd.DataFrame, eye_offset_ms: float = 0.0, bin_size_ms: int = 2000) -> dict:
    if "Recording Time Stamp[ms]" not in df.columns:
        return {
            "eye_sample_count": int(len(df)),
            "eye_duration_s": np.nan,
            "eye_first_timestamp_ms": np.nan,
            "eye_last_timestamp_ms": np.nan,
            "timebin_count": 0,
        }
    t = pd.to_numeric(df["Recording Time Stamp[ms]"], errors="coerce").dropna()
    if t.empty:
        return {
            "eye_sample_count": int(len(df)),
            "eye_duration_s": np.nan,
            "eye_first_timestamp_ms": np.nan,
            "eye_last_timestamp_ms": np.nan,
            "timebin_count": 0,
        }
    duration_ms = float(t.max() - t.min())
    aligned_max = duration_ms + float(eye_offset_ms or 0.0)
    n_bins = int(np.ceil(max(aligned_max, 0.0) / bin_size_ms)) if bin_size_ms > 0 else 0
    return {
        "eye_sample_count": int(len(df)),
        "eye_duration_s": duration_ms / 1000.0,
        "eye_first_timestamp_ms": float(t.min()),
        "eye_last_timestamp_ms": float(t.max()),
        "timebin_count": n_bins,
    }


def _require_eye_columns(df: pd.DataFrame) -> None:
    required = ["Gaze Point X[px]", "Gaze Point Y[px]", "Recording Time Stamp[ms]"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Eye dataframe missing columns: {missing}")


def _metric_row(
    sub: pd.DataFrame,
    t0: float,
    class_name: str,
    dwell_mode: str,
    extra: dict,
) -> dict:
    row = {"class_name": class_name}
    row.update(extra)
    dwell = _dwell_time(sub, mode=dwell_mode)
    row["dwell_time_ms"] = float(dwell) if pd.notna(dwell) else np.nan
    row["fixation_count"] = _fixation_count(sub)
    if len(sub) and pd.notna(t0):
        ttff = pd.to_numeric(sub["Recording Time Stamp[ms]"], errors="coerce").min() - t0
        row["TTFF_ms"] = float(ttff) if pd.notna(ttff) else np.nan
    else:
        row["TTFF_ms"] = np.nan
    return row


def _dwell_time(sub: pd.DataFrame, mode: str = "fixation") -> float:
    if sub is None or len(sub) == 0 or "Fixation Duration[ms]" not in sub.columns:
        return np.nan
    if mode not in {"row", "fixation"}:
        raise ValueError("dwell_mode must be 'row' or 'fixation'")
    durations = pd.to_numeric(sub["Fixation Duration[ms]"], errors="coerce")
    if mode == "row" or "Fixation Index" not in sub.columns:
        return float(durations.dropna().sum())
    tmp = pd.DataFrame({
        "Fixation Index": pd.to_numeric(sub["Fixation Index"], errors="coerce"),
        "Fixation Duration[ms]": durations,
    }).dropna()
    if tmp.empty:
        return np.nan
    return float(tmp.groupby("Fixation Index")["Fixation Duration[ms]"].max().sum())


def _fixation_count(sub: pd.DataFrame) -> int:
    if len(sub) == 0 or "Fixation Index" not in sub.columns:
        return 0
    return int(pd.to_numeric(sub["Fixation Index"], errors="coerce").dropna().nunique())
