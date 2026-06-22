# HDR-VQA

HDR 视频质量评估项目，用于在 ZJUHDR 格式数据集上批量运行全参考视频质量指标，并将每个失真视频的质量分数写出为 CSV。

当前精简版核心支持：

- `ColorVideoVDP`
- `VMAF`
- `HDRMetrics`
- `ZJUHDR` CSV 数据格式

## 目录结构

```text
.
├── run.py                    # 原始批量运行入口
├── vqa_multi_config.yml      # 指标、数据集、输出目录配置示例
├── dataset_new.py            # 精简版 ZJUHDR 数据集加载与任务调度
├── worker_new.py             # 精简版指标执行逻辑
├── methods/
│   ├── ColorVideoVDP/        # ColorVideoVDP 源码与运行所需参数
│   ├── HDRMetrics/           # HDRMetrics runner
│   ├── HDRTools/             # HDRTools 源码；仅推理必需 bin 入库
│   └── vmaf/                 # Netflix VMAF 源码；仅推理必需 bin 入库
└── outputs/                  # 本机运行输出目录，不入库
```

## 数据格式

`dataset_new.py` 读取 ZJUHDR 风格 CSV，至少需要以下字段：

```csv
ref_name,dis_name,mos,trc,ref_width,ref_height,ref_bits,dis_width,dis_height,dis_bits,codec
```

字段说明：

- `ref_name`：参考视频文件名。
- `dis_name`：失真视频文件名。
- `mos`：主观质量分。
- `trc`：传递函数，常见取值为 `PQ`、`HLG`、`SDR`。
- `ref_width/ref_height/ref_bits`：参考视频分辨率与位深。
- `dis_width/dis_height/dis_bits`：失真视频分辨率与位深。
- `codec`：编码或失真类型标识。

运行时会将 `ref_dir/ref_name` 和 `dis_dir/dis_name` 拼成实际视频路径。

## 环境依赖

基础 Python 依赖：

```bash
pip install pandas numpy tqdm pyyaml
```

额外依赖按指标启用：

- `ColorVideoVDP`：需要 `methods/ColorVideoVDP` 可导入，并安装其依赖。
- `VMAF`：需要可执行 `vmaf` 命令，且可用 `ffmpeg` 做视频/YUV 转换。
- `HDRMetrics`：需要已编译的 HDRTools，并在配置中填写 `hdrtools_bin` 和相关 cfg 路径。

## HDRTools 和 VMAF 安装

推荐将两个工具安装到项目的 `methods/` 目录，配置使用相对路径，避免依赖系统全局环境。

### 安装 HDRTools

```bash
git clone https://gitlab.com/standards/HDRTools methods/HDRTools
cmake -S methods/HDRTools -B methods/HDRTools/build -DCMAKE_BUILD_TYPE=Release
cmake --build methods/HDRTools/build --parallel 8
```

编译完成后，核心二进制位于：

### 安装 VMAF

基础验证：

```bash
methods/vmaf/libvmaf/build/tools/vmaf -v
env -u LD_LIBRARY_PATH methods/HDRTools/build/bin/HDRMetrics
```

## 配置说明

配置文件参考 `vqa_multi_config.yml`，核心结构如下：

```yaml
frameworks:
  VMAF:
    vmaf_bin: methods/vmaf/libvmaf/build/tools/vmaf
    w: 3840
    h: 2160
    b: 10
    p: "420"
    model: path=methods/vmaf/model/vmaf_4k_v0.6.1.json
    enable_pu21: false

  HDRMetrics:
    hdrtools_bin: methods/HDRTools/build/bin
    wpsnr_cfg: methods/HDRTools/cfg/HDRMetricsYUV.cfg
    hdrconvert_cfg: methods/HDRTools/cfg/JCTVC_CTC_cfgFiles/YCbCr/HDRConvertYCbCr420ToEXR2020.cfg
    deltae_cfg: methods/HDRTools/cfg/JCTVC_CTC_cfgFiles/YCbCr/HDRMetric_CfE.cfg
    weight_table: methods/HDRTools/cfg/hdrTable.txt
    width: 3840
    height: 2160
    bit_depth: 10
    workdir: methods/HDRMetrics

global:
  device: cuda:0
  num_workers: 1
  output_dir: /path/to/vqa_infer_result

datasets:
  ZJUHDR_full:
    type: TestVideoSet
    test_data: /path/to/ZJUHDR-info-mp4-all.csv
    ref_dir: /path/to/reference/videos
    dis_dir: /path/to/distorted/videos
    lower_better: false

runs:
  - framework: VMAF
    datasets:
      - ZJUHDR_full
```

注意：

- `enable_pu21` 支持布尔值和字符串；`false`、`flase`、`0`、`no`、`none` 会被识别为关闭。
- `num_workers > 1` 时会用多进程并行执行。
- 输出文件默认写入 `output_dir/{dataset}_{framework}.csv`。
- 已完成的视频会从输出 CSV 中恢复，重复运行时自动跳过已有分数。

## 运行方式

使用配置文件运行全部任务：

```bash
python run.py --config vqa_multi_config.yml
```

只运行指定指标：

```bash
python run.py --config vqa_multi_config.yml --only VMAF
```

只运行指定数据集：

```bash
python run.py --config vqa_multi_config.yml --datasets ZJUHDR_full
```

覆盖设备和 worker 数：

```bash
python run.py --config vqa_multi_config.yml --device cuda:0 --worker 1
```

如果使用精简后的实现文件，请确认运行入口导入的是 `dataset_new._run_dataset`。

## 输出结果

每个指标和数据集生成一个 CSV：

```csv
video,score
/path/to/distorted/video_001.mp4,92.31
```

其中：

- `video`：失真视频完整路径。
- `score`：对应指标输出分数。

各指标的中间日志会写入 `output_dir` 下的指标子目录，例如：

- `VMAF_log/{dataset}`
- `ColorVideoVDP_log/{dataset}`
- `HDRMetrics_log/{dataset}`
