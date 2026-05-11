from __future__ import annotations

from pathlib import Path

import pandas as pd

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
