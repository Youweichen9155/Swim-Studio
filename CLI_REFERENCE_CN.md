# 蝌蚪游动轨迹与刺激后距离分析 v1.0

这是一个独立、配置文件驱动的固定代码包，用于：

1. 用 CoTracker3 追踪蝌蚪头部多点；
2. 用培养皿椭圆把像素坐标换算为毫米坐标；
3. 读取人工复核的镊子接触区间；
4. 计算严格排除接触帧的游动距离、速度和刺激后 2 s 距离；
5. 输出表格、图、方法说明和完整 provenance。

包内不含原始视频，也不默认运行旧分辨率专用的自动镊子检测。人工复核 TSV 是主分析输入。

## 快速开始

在本目录中创建固定环境：

```bash
conda env create -f environment.yml
conda activate tadpole-swimming-tracking-v1
```

检查去标识化示例配置、人工区间和缓存：

```bash
python prepare_config.py check \
  --config examples/configs/tadpole_recording_001.json
```

仅用包内缓存复算，不运行 CoTracker：

```bash
python tadpole_swimming_tracking.py \
  --config examples/configs/tadpole_recording_001.json \
  --cache-only
```

也可以运行：

```bash
scripts/run_cached_example.sh
```

默认结果写入 `example_run/tadpole_recording_001/`。若没有视频，数值表和分析图仍会生成，视频 QA 会自动跳过，provenance 中的视频 SHA256 状态为 `not_computed_no_video`。

## 复现测试

不提供视频也可检查全部数值和边界情况：

```bash
python tests/run_reproduction_test.py
```

如需同时在运行时核验视频元数据并计算视频 SHA256：

```bash
python tests/run_reproduction_test.py --video ./input/recording.mp4
```

测试不会运行 CoTracker。固定报告见 `tests/reproduction_report.md` 和 `tests/reproduction_report.json`。

示例缓存的 v1.0 预期结果：

| 指标 | 预期值 |
|---|---:|
| 追踪帧数 | 4657 |
| 独立刺激 bouts | 14 |
| 严格非接触距离 | 340.6404827 mm |
| 刺激后 2 s 平均距离 | 15.9001959 mm |
| 刺激后 2 s 中位距离 | 11.7054573 mm |
| 全程平均速度 | 2.1966107 mm/s |
| 可分析帧比例 | 0.8359459 |

## 每个视频的独立输入

每个视频必须有：

- 一个 JSON 配置，分别记录视频元数据、模型追踪、头部点选择、培养皿标定、人工接触审核和分析参数；
- 一个 forceps interval TSV，至少含 `start_s` 和 `end_s`；
- 原始视频或已经审核过的 CoTracker `.npz` 缓存。

示例 TSV 还含 `start_raw_frame` 和 `end_raw_frame`。当六位小数时间恰好位于帧边界附近时，这两列固定人工审核后的逐帧归属，避免不同浮点实现产生一帧偏差。新数据若需要严格复现，也建议在人工逐帧审核后保留这两列。

使用工具创建新配置：

```bash
python prepare_config.py init \
  --output examples/configs/new_recording.json \
  --analysis-id new_recording \
  --logical-name new_recording.mp4 \
  --video ./input/new_recording.mp4 \
  --roi 100,100,900,900 \
  --model-size 560,560 \
  --query-points '400,420;410,420;420,425' \
  --maximum-spread-px 38 \
  --dish-center 500,500 \
  --dish-diameters 800,805 \
  --dish-angle 0 \
  --dish-diameter-mm 100
```

JSON 内所有路径必须是相对路径。临时绝对路径只通过 `--video`、`--cache` 或 `--output` 传入，并且不会写入结果。

## 完整模型追踪

先获取并核验固定 CoTracker commit：

```bash
python prepare_config.py fetch-model \
  --config examples/configs/new_recording.json
```

随后运行：

```bash
python tadpole_swimming_tracking.py \
  --config examples/configs/new_recording.json \
  --video ./input/new_recording.mp4 \
  --force-retrack
```

模型阶段、培养皿标定、头部点选择和人工接触复核是四个独立步骤。更改任一项后，应更新对应配置或 TSV，并重新做完整 QA。

## 输出

- `tables/01_frame_level_head_trajectory.tsv`：逐帧轨迹、有效性、距离、速度和刺激状态；
- `tables/02_swimming_summary.tsv`：主要汇总指标；
- `tables/04_forceps_stimulation_bouts.tsv`：合并后的刺激 bouts；
- `tables/05_post_stimulus_repeat_metrics.tsv`：每个 bout 后 2 s 指标；
- `plots/`：PDF 和 600 dpi PNG 分析图；
- `video/tracked_head_QA.mp4`：仅在有视频且启用 QA 时生成；
- `reports/01_effective_config.json`：本次有效配置快照；
- `reports/02_parameter_manifest.tsv`：参数清单；
- `reports/03_provenance.json`：程序、配置、输入哈希、软件和模型来源；
- `reports/04_method_and_interpretation_note.md`：本次运行的方法说明。

详细算法见 `METHODS.md`。CoTracker 来源和非商业许可提醒见 `THIRD_PARTY_NOTICES.md`。

