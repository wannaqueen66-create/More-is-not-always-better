from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


FALSE_VALUES = {"", "0", "false", "no", "n", "none", "nan"}


def read_csv(path: str | Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig")


def write_csv(df: pd.DataFrame, path: str | Path) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out


def resolve_path(value: object, base_dir: str | Path) -> Optional[Path]:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return path
    return Path(base_dir) / path


def normalize_key_columns(df: pd.DataFrame, scene_col: str = "scene_id") -> pd.DataFrame:
    out = df.copy()
    if "participant_id" in out.columns:
        out["participant_id"] = out["participant_id"].astype(str).str.strip()
    if "subject_id" in out.columns:
        out["subject_id"] = out["subject_id"].astype(str).str.strip()
    if scene_col in out.columns:
        out[scene_col] = pd.to_numeric(out[scene_col], errors="coerce").astype("Int64")
    return out


def load_participants(path: str | Path) -> pd.DataFrame:
    participants = read_csv(path)
    required = {"participant_id", "eeg_subject_id", "eye_subject_id"}
    missing = required - set(participants.columns)
    if missing:
        raise ValueError(f"participants.csv missing columns: {sorted(missing)}")
    participants = participants.copy()
    for col in ["participant_id", "eeg_subject_id", "eye_subject_id"]:
        participants[col] = participants[col].astype(str).str.strip()
    if "exclude" not in participants.columns:
        participants["exclude"] = False
    participants["exclude"] = participants["exclude"].map(is_truthy)
    return participants


def active_participants(participants: pd.DataFrame) -> pd.DataFrame:
    return participants.loc[~participants["exclude"]].copy()


def is_truthy(value: object) -> bool:
    if value is None or pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in FALSE_VALUES


def assert_required_columns(df: pd.DataFrame, required: Iterable[str], name: str) -> None:
    missing = set(required) - set(df.columns)
    if missing:
        raise ValueError(f"{name} missing columns: {sorted(missing)}")


def assert_unique(df: pd.DataFrame, keys: list[str], name: str) -> None:
    duplicates = df[df.duplicated(keys, keep=False)]
    if not duplicates.empty:
        sample = duplicates[keys].head(10).to_dict("records")
        raise ValueError(f"{name} has duplicate keys {keys}. Sample: {sample}")
