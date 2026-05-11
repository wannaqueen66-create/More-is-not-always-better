from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional


DEFAULT_COLUMNS_MAP = Path(__file__).resolve().parents[2] / "configs" / "columns_default.json"


def load_columns_map(path: Optional[str | Path] = None) -> Dict[str, List[str]]:
    map_path = Path(path) if path else DEFAULT_COLUMNS_MAP
    with open(map_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out: Dict[str, List[str]] = {}
    for key, value in data.items():
        if isinstance(value, list):
            out[str(key)] = [str(v) for v in value]
        else:
            out[str(key)] = [str(value)]
    return out


def resolve_columns(
    df_columns: Iterable[str],
    required_to_candidates: Dict[str, List[str]],
) -> Dict[str, str]:
    raw_columns = [str(c).lstrip("\ufeff").strip() for c in df_columns]
    raw_set = set(raw_columns)
    resolved: Dict[str, str] = {}
    for required, candidates in required_to_candidates.items():
        if required in raw_set:
            resolved[required] = required
            continue
        for candidate in candidates:
            candidate_clean = str(candidate).lstrip("\ufeff").strip()
            if candidate_clean in raw_set:
                resolved[required] = candidate_clean
                break
    return resolved


def rename_df_columns_inplace(df, required_to_candidates: Dict[str, List[str]]) -> Dict[str, str]:
    df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]
    resolved = resolve_columns(df.columns, required_to_candidates)
    actual_to_required = {
        actual: required
        for required, actual in resolved.items()
        if actual != required
    }
    if actual_to_required:
        df.rename(columns=actual_to_required, inplace=True)
    return resolved


def missing_required(df_columns: Iterable[str], required: list[str]) -> list[str]:
    cols = set(df_columns)
    return [col for col in required if col not in cols]
