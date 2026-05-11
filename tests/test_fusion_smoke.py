from __future__ import annotations

from pathlib import Path

import pandas as pd

from more_is_not_always_better.discovery import (
    build_participants_from_roots,
    build_scene_manifest_from_eye_root,
    scan_eye_raw,
)
from more_is_not_always_better.eye_batch import run_eye_aoi_batch
from more_is_not_always_better.fusion import run_fusion


FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_eye_batch_and_fusion_smoke(tmp_path: Path) -> None:
    eye_out = tmp_path / "eye"
    fusion_out = tmp_path / "fusion"

    eye_paths = run_eye_aoi_batch(
        participants_csv=FIXTURES / "participants.csv",
        scene_manifest_csv=FIXTURES / "scene_manifest.csv",
        outdir=eye_out,
        dwell_mode="fixation",
    )
    assert eye_paths["class"].exists()
    eye_class = pd.read_csv(eye_paths["class"])
    assert {"participant_id", "scene_id", "class_name", "dwell_time_ms", "TTFF_ms", "fixation_count"}.issubset(eye_class.columns)
    assert not eye_class.duplicated(["participant_id", "scene_id", "class_name"]).any()

    fusion_paths = run_fusion(
        participants_csv=FIXTURES / "participants.csv",
        scene_manifest_csv=FIXTURES / "scene_manifest.csv",
        eeg_scene_csv=FIXTURES / "eeg" / "all_subjects_scene_level.csv",
        eye_aoi_class_csv=eye_paths["class"],
        outdir=fusion_out,
        expected_scenes_per_subject=2,
        duration_tolerance_s=2.0,
    )

    aligned_scene = pd.read_csv(fusion_paths["aligned_scene"])
    sync_qc = pd.read_csv(fusion_paths["sync_qc"])
    aligned_timebin = pd.read_csv(fusion_paths["aligned_timebin"])

    assert {"participant_id", "scene_id", "class_name", "O_alpha", "dwell_time_ms"}.issubset(aligned_scene.columns)
    assert not aligned_scene.duplicated(["participant_id", "scene_id", "class_name"]).any()
    assert len(sync_qc) == 2
    assert sync_qc["duration_mismatch"].astype(str).str.lower().isin(["false", "0"]).all()
    assert {"participant_id", "scene_id", "bin_start_ms", "bin_end_ms", "class_name", "eeg_O_alpha"}.issubset(aligned_timebin.columns)
    assert len(aligned_timebin) > 0


def test_eye_batch_without_aoi_outputs_whole_scene(tmp_path: Path) -> None:
    manifest = tmp_path / "scene_manifest_no_aoi.csv"
    eye_csv = FIXTURES / "eye" / "P01_scene01.csv"
    manifest.write_text(
        "participant_id,scene_id,block,position,scene_name,eye_csv_path,aoi_json_path,WWR,Cond,Complexity,eye_offset_ms\n"
        f"P01,1,1,1,scene_01,{eye_csv.as_posix()},,0.2,A,1,0\n",
        encoding="utf-8",
    )

    eye_paths = run_eye_aoi_batch(
        participants_csv=FIXTURES / "participants.csv",
        scene_manifest_csv=manifest,
        outdir=tmp_path / "eye_no_aoi",
    )
    eye_class = pd.read_csv(eye_paths["class"])
    eye_qc = pd.read_csv(eye_paths["qc"])

    assert eye_class.loc[0, "class_name"] == "whole_scene"
    assert bool(eye_class.loc[0, "aoi_available"]) is False
    assert eye_class.loc[0, "samples"] == 5
    assert bool(eye_qc.loc[0, "missing_aoi_file"]) is True


def test_manifest_builder_generates_raw_root_manifests_without_alias(tmp_path: Path) -> None:
    eye_root = tmp_path / "eye"
    eeg_root = tmp_path / "eeg"
    _write_eye_csv(eye_root / "(1-1-1\u30012-1-1) \u7ec41-C1W45" / "raw_\u5f20\u4e09_260101000001_0207000001.csv")
    _write_eye_csv(eye_root / "(1-1-2\u30012-1-2) \u7ec41-C0W15" / "raw_\u5f20\u4e09_260101000001_0207000002.csv")
    _write_eeg_pair(eeg_root, "\u5f20\u4e09")

    participants_csv = tmp_path / "participants.csv"
    scene_manifest_csv = tmp_path / "scene_manifest.csv"
    participants = build_participants_from_roots(eye_root, eeg_root, out_csv=participants_csv)
    scene_manifest = build_scene_manifest_from_eye_root(eye_root, participants_csv, out_csv=scene_manifest_csv)
    eye_raw = scan_eye_raw(eye_root)

    assert participants.loc[0, "participant_id"] == "\u5f20\u4e09"
    assert bool(participants.loc[0, "exclude"]) is False
    assert participants.loc[0, "eye_scene_file_count"] == 2
    assert eye_raw["participant_id"].tolist() == ["\u5f20\u4e09", "\u5f20\u4e09"]
    assert sorted(scene_manifest["scene_id"].tolist()) == [1, 2]
    assert scene_manifest["alias_source"].fillna("").eq("").all()


def test_manifest_builder_supports_manual_alias_csv(tmp_path: Path) -> None:
    eye_root = tmp_path / "eye"
    eeg_root = tmp_path / "eeg"
    _write_eye_csv(eye_root / "(1-1-1\u30012-1-1) \u7ec41-C1W45" / "raw_User1_260101000001_0207000001.csv")
    _write_eeg_pair(eeg_root, "\u5f20\u4e09")
    alias_csv = tmp_path / "aliases.csv"
    alias_csv.write_text("eye_subject_id,participant_id\nUser1,\u5f20\u4e09\n", encoding="utf-8")

    participants_csv = tmp_path / "participants.csv"
    scene_manifest_csv = tmp_path / "scene_manifest.csv"
    participants = build_participants_from_roots(eye_root, eeg_root, out_csv=participants_csv, eye_alias_csv=alias_csv)
    scene_manifest = build_scene_manifest_from_eye_root(eye_root, participants_csv, out_csv=scene_manifest_csv, eye_alias_csv=alias_csv)

    assert participants.loc[0, "participant_id"] == "\u5f20\u4e09"
    assert bool(participants.loc[0, "exclude"]) is False
    assert scene_manifest.loc[0, "participant_id"] == "\u5f20\u4e09"
    assert scene_manifest.loc[0, "eye_subject_alias"] == "User1"
    assert scene_manifest.loc[0, "alias_source"] == "manual"


def _write_eye_csv(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("Recording Time Stamp[ms],Gaze Point X[px],Gaze Point Y[px]\n0,1,1\n", encoding="utf-8")


def _write_eeg_pair(root: Path, subject: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{subject}.set").write_text("placeholder", encoding="utf-8")
    (root / f"{subject}.fdt").write_text("placeholder", encoding="utf-8")
