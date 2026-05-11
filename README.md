# More Is Not Always Better

Independent fusion pipeline for scene-level and time-bin aligned EEG + eye-tracking analysis.

This repository is designed to stand alone from the original source repositories:

- Eye-tracking source reference: https://github.com/wannaqueen66-create/eyetrack
- EEG source reference: https://github.com/wannaqueen66-create/eeg

The main fusion key is `participant_id + scene_id`. Each eye-tracking CSV is assumed to contain one scene only. Its minimum recording timestamp is treated as scene `t=0` and aligned to the EEG `view` segment start, corresponding to marker transition `7 -> 8` in the EEG pipeline.

## Project Layout

```text
configs/
  columns_default.json          Eye-tracking column aliases.
  fusion_config.json            Default fusion parameters.
manifests/
  participants.csv              Participant/group mapping template.
  scene_manifest.csv            Scene/order/file mapping template.
scripts/
  run_eye_aoi_batch.py          Compute eye AOI metrics from scene CSVs.
  run_fusion.py                 Build aligned scene, time-bin, and sync-QC tables.
src/more_is_not_always_better/
  aoi.py                        AOI loading and polygon metrics.
  eye_batch.py                  Batch eye-tracking AOI runner.
  fusion.py                     EEG + eye fusion and synchronization QC.
matlab/
  README.md                     EEG export contract for MATLAB/EEGLAB runs.
tests/
  fixtures/                     Minimal 1-subject, 2-scene smoke data.
```

## Inputs

`manifests/participants.csv`

```csv
participant_id,eeg_subject_id,eye_subject_id,SportFreq,Experience,Order,exclude
P001,P001,P001,High,Low,1,false
```

`manifests/scene_manifest.csv`

```csv
participant_id,scene_id,block,position,scene_name,eye_csv_path,aoi_json_path,WWR,Cond,Complexity,eye_offset_ms
P001,1,1,1,scene_01,data/raw/eye/P001_scene01.csv,data/raw/aoi/scene_01_aoi.json,0.2,A,1,0
```

EEG summary input:

```text
outputs/eeg/summary/all_subjects_scene_level.csv
```

Eye AOI batch input to fusion:

```text
outputs/eye/batch_aoi_metrics_by_class.csv
```

## Quick Start

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Compute eye-tracking AOI metrics:

```bash
python scripts/run_eye_aoi_batch.py \
  --participants manifests/participants.csv \
  --scene_manifest manifests/scene_manifest.csv \
  --outdir outputs/eye \
  --dwell_mode fixation
```

Build fusion outputs:

```bash
python scripts/run_fusion.py \
  --participants manifests/participants.csv \
  --scene_manifest manifests/scene_manifest.csv \
  --eeg_scene_csv outputs/eeg/summary/all_subjects_scene_level.csv \
  --eye_aoi_class_csv outputs/eye/batch_aoi_metrics_by_class.csv \
  --outdir outputs/fusion
```

Generated outputs:

- `outputs/fusion/aligned_scene_table.csv`
- `outputs/fusion/aligned_timebin_table.csv`
- `outputs/fusion/sync_qc.csv`

## Alignment Rule

For each row in `scene_manifest.csv`:

```text
eye_aligned_ms = eye_timestamp_ms - min(eye_timestamp_ms) + eye_offset_ms
```

The aligned `0 ms` point is interpreted as the EEG scene-viewing start, i.e. the EEG marker transition `7 -> 8`.

Default time bins are non-overlapping `2000 ms` bins, matching the EEG pipeline's 2-second Welch window convention. The current time-bin output computes eye AOI metrics per bin and attaches the corresponding scene-level EEG columns to every bin. If a future EEG export provides true per-bin bandpower, that file can be joined on the same `participant_id + scene_id + bin_start_ms`.

## Synchronization QC

`sync_qc.csv` reports:

- EEG view duration, inferred from `view_dur_s`, `dur_s`, `duration_s`, or start/end columns.
- Eye CSV duration from canonical eye timestamp columns.
- Duration delta and `duration_mismatch`, using a default tolerance of `2 s`.
- Eye sample count, time-bin count, missing EEG/eye flags, and scene-count checks.

## Tests

```bash
python -m pytest
```

The smoke test uses one subject and two scenes to validate manifest loading, eye AOI batch output, scene fusion, sync QC, and time-bin output.
