# More Is Not Always Better：EEG + 眼动融合项目

本仓库用于把 EEG 场景级频段功率结果与眼动场景 CSV/AOI 指标合并成一个可直接写论文、建模和出图的独立项目。原始参考仓库为：

- 眼动：https://github.com/wannaqueen66-create/eyetrack
- EEG：https://github.com/wannaqueen66-create/eeg

本仓库不依赖也不修改上述两个仓库。核心合并键是 `participant_id + scene_id`。

## 对齐原则

每个眼动 CSV 已经是单个场景，因此默认：

```text
eye_aligned_ms = 眼动时间戳 - 该 CSV 最小时间戳 + eye_offset_ms
```

也就是说，每个眼动场景 CSV 的起点对齐到 EEG 中该场景 `view` 段的起点，即 marker `7 -> 8`。

## 主要输出

- `outputs/fusion/aligned_scene_table.csv`：场景级 EEG + 眼动融合主表。
- `outputs/fusion/aligned_timebin_table.csv`：默认 2 秒非重叠 time-bin 的眼动 AOI 指标，并附加对应场景 EEG 指标。
- `outputs/fusion/sync_qc.csv`：同步质量检查，包括 EEG view 时长、眼动 CSV 时长、差值、样本数、bin 数、缺失和 mismatch 标记。

## 推荐运行

```bash
python -m pip install -r requirements.txt
python scripts/run_eye_aoi_batch.py --participants manifests/participants.csv --scene_manifest manifests/scene_manifest.csv --outdir outputs/eye --dwell_mode fixation
python scripts/run_fusion.py --participants manifests/participants.csv --scene_manifest manifests/scene_manifest.csv --eeg_scene_csv outputs/eeg/summary/all_subjects_scene_level.csv --eye_aoi_class_csv outputs/eye/batch_aoi_metrics_by_class.csv --outdir outputs/fusion
```

## 数据表要求

`manifests/participants.csv`：

```csv
participant_id,eeg_subject_id,eye_subject_id,SportFreq,Experience,Order,exclude
P001,P001,P001,High,Low,1,false
```

`manifests/scene_manifest.csv`：

```csv
participant_id,scene_id,block,position,scene_name,eye_csv_path,aoi_json_path,WWR,Cond,Complexity,eye_offset_ms
P001,1,1,1,scene_01,data/raw/eye/P001_scene01.csv,data/raw/aoi/scene_01_aoi.json,0.2,A,1,0
```

`eye_offset_ms` 用于修正固定同步延迟；没有延迟时填 `0`。
