import subprocess
from pathlib import Path
import csv
import os


def _infer_frame_num(yuv_path: Path, width: int, height: int) -> int:
    size_bytes = yuv_path.stat().st_size
    bytes_per_frame = width * height * 3
    if bytes_per_frame <= 0:
        raise ValueError("Invalid width/height for frame size computation")
    frame_num = size_bytes // bytes_per_frame
    if frame_num <= 0:
        raise ValueError(f"Cannot infer positive frame count from file size: {yuv_path}")
    return int(frame_num)


def _parse_wpsnr_score(log_path: Path) -> float:
    header_tokens = None
    wtpsnr_indices = []
    d_avg_values = []

    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            # Only the table header defines wtPSNR columns; config lines such as
            # EnableWTPSNR must not be treated as metric headers.
            if header_tokens is None and line_stripped.startswith("Frame#") and "wtPSNR" in line_stripped:
                header_tokens = line_stripped.split()
                wtpsnr_indices = [idx for idx, t in enumerate(header_tokens) if t.startswith("wtPSNR-")]
                continue
            if line_stripped.startswith("D_Avg"):
                tokens = line_stripped.split()
                if wtpsnr_indices and all(len(tokens) > idx for idx in wtpsnr_indices):
                    try:
                        value = sum(float(tokens[idx]) for idx in wtpsnr_indices)
                        d_avg_values.append(value)
                        continue
                    except ValueError:
                        pass
                for token in reversed(tokens[1:]):
                    try:
                        value = float(token)
                        d_avg_values.append(value)
                        break
                    except ValueError:
                        continue

    if not d_avg_values:
        raise ValueError(f"Cannot find D_Avg WTPSNR value in log: {log_path}")
    return float(d_avg_values[-1])


def _parse_deltae_psnrl100(log_path: Path) -> tuple[float, float]:
    header_tokens = None
    deltae_index = None
    psnrl100_index = None
    deltae_sum = 0.0
    psnrl100_sum = 0.0

    with log_path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()
            if not line_stripped:
                continue
            if header_tokens is None and "Frame#" in line_stripped:
                header_tokens = [field for field in line_stripped.split() if field != ""]
                for idx, t in enumerate(header_tokens):
                    if "PSNR_DE0100" in t:
                        deltae_index = idx
                    if "PSNR_L0100" in t:
                        psnrl100_index = idx
                continue
            if line_stripped.startswith("D_Avg"):
                tokens = [field for field in line_stripped.split() if field != ""]
                if deltae_index is not None and len(tokens) > deltae_index:
                    v = tokens[deltae_index]
                    if v != "inf":
                        try:
                            deltae_sum += float(v)
                        except ValueError:
                            pass
                if psnrl100_index is not None and len(tokens) > psnrl100_index:
                    v = tokens[psnrl100_index]
                    if v != "inf":
                        try:
                            psnrl100_sum += float(v)
                        except ValueError:
                            pass

    if deltae_index is None or psnrl100_index is None:
        raise ValueError(f"Cannot find PSNR_DE0100/PSNR_L0100 in log: {log_path}")
    return float(deltae_sum), float(psnrl100_sum)


def run_hdrmetrics(
    ref_yuv: str,
    dist_yuv: str,
    *,
    hdrtools_bin: str,
    wpsnr_cfg: str,
    deltae_cfg: str,
    hdrconvert_cfg: str,
    width: int,
    height: int,
    bit_depth: int,
    trc: str,
    work_root: str,
    weight_table=None,
    keep_exr: bool = False,
) -> str:
    work_root_path = Path(work_root)
    work_root_path.mkdir(parents=True, exist_ok=True)
    wpsnr_log_dir = work_root_path / "wpsnr_logs"
    deltae_log_dir = work_root_path / "deltae_logs"
    wpsnr_log_dir.mkdir(parents=True, exist_ok=True)
    deltae_log_dir.mkdir(parents=True, exist_ok=True)

    ref_yuv_path = Path(ref_yuv)
    dist_yuv_path = Path(dist_yuv)

    frame_num = _infer_frame_num(dist_yuv_path, width, height)

    ref_stem = ref_yuv_path.stem
    dist_stem = dist_yuv_path.stem
    wpsnr_log = wpsnr_log_dir / f"{dist_stem}.log"
    deltae_log = deltae_log_dir / f"{dist_stem}.log"

    hdrtools_bin_path = Path(hdrtools_bin)
    hdrmetrics_exe = str(hdrtools_bin_path / "HDRMetrics")
    hdrconvert_exe = str(hdrtools_bin_path / "HDRConvert")

    hdrconvert_params = []
    deltae_params = []
    trc_upper = str(trc).upper()
    if trc_upper == "HLG":
        hdrconvert_params = [
            "-p",
            "SourceTransferFunction=11",
            "-p",
            "SourceNormalizationScale=1000.0",
            "-p",
            "OutputNormalizationScale=1000.0",
            "-p",
            "SourceSystemGamma=1.2",
            "-p",
            "SourceDisplayAdjustment=1",
        ]
        deltae_params = [
            "-p",
            "MaxSampleValue=1000.0",
        ]
    elif trc_upper != "PQ":
        raise ValueError(f"Unsupported TRC for HDRMetrics: {trc}")

    wpsnr_cmd = [
        hdrmetrics_exe,
        "-f",
        str(wpsnr_cfg),
        "-p",
        f"Input0File={ref_yuv_path}",
        "-p",
        f"Input1File={dist_yuv_path}",
        "-p",
        f"Input0Width={width}",
        "-p",
        f"Input0Height={height}",
        "-p",
        f"Input1Width={width}",
        "-p",
        f"Input1Height={height}",
        "-p",
        "Input0ColorPrimaries=1",
        "-p",
        "Input1ColorPrimaries=1",
        "-p",
        f"Input0BitDepthCmp0={bit_depth}",
        "-p",
        f"Input0BitDepthCmp1={bit_depth}",
        "-p",
        f"Input0BitDepthCmp2={bit_depth}",
        "-p",
        f"Input1BitDepthCmp0={bit_depth}",
        "-p",
        f"Input1BitDepthCmp1={bit_depth}",
        "-p",
        f"Input1BitDepthCmp2={bit_depth}",
        "-p",
        "Input0Rate=1",
        "-p",
        "Input1Rate=1",
        "-p",
        f"NumberOfFrames={frame_num}",
        "-p",
        "EnableWTPSNR=1",
        "-p",
        "EnableJVETPSNR=1",
    ]
    if weight_table is not None:
        wpsnr_cmd += [
            "-p",
            f"WeightTableFile={weight_table}",
        ]
    wpsnr_cmd += [
        "-p",
        "EnableShowMSE=0",
        "-p",
        "SilentMode=0",
    ]

    exr_dir = work_root_path / f"{dist_stem}_exr"
    ori_exr_dir = work_root_path / f"{ref_stem}_exr"
    exr_dir.mkdir(parents=True, exist_ok=True)
    ori_exr_dir.mkdir(parents=True, exist_ok=True)
    exr_file = exr_dir / "frames%03d.exr"
    ori_exr_file = ori_exr_dir / "frames%03d.exr"

    yuv2exr_cmd = [
        hdrconvert_exe,
        "-f",
        str(hdrconvert_cfg),
        "-p",
        f"SourceFile={dist_yuv_path}",
        "-p",
        f"OutputFile={exr_file}",
        "-p",
        "SourceSampleRange=0",
        "-p",
        f"SourceHeight={height}",
        "-p",
        f"SourceWidth={width}",
        "-p",
        f"OutputHeight={height}",
        "-p",
        f"OutputWidth={width}",
        "-p",
        f"NumberOfFrames={frame_num}",
    ] + hdrconvert_params

    ori_yuv2exr_cmd = [
        hdrconvert_exe,
        "-f",
        str(hdrconvert_cfg),
        "-p",
        f"SourceFile={ref_yuv_path}",
        "-p",
        f"OutputFile={ori_exr_file}",
        "-p",
        "SourceSampleRange=0",
        "-p",
        f"SourceHeight={height}",
        "-p",
        f"SourceWidth={width}",
        "-p",
        f"OutputHeight={height}",
        "-p",
        f"OutputWidth={width}",
        "-p",
        f"NumberOfFrames={frame_num}",
    ] + hdrconvert_params

    deltae_cmd = [
        hdrmetrics_exe,
        "-f",
        str(deltae_cfg),
        "-p",
        f"Input0File={ori_exr_file}",
        "-p",
        f"Input1File={exr_file}",
        "-p",
        f"Input0Height={height}",
        "-p",
        f"Input0Width={width}",
        "-p",
        f"Input1Height={height}",
        "-p",
        f"Input1Width={width}",
        "-p",
        f"NumberOfFrames={frame_num}",
    ] + deltae_params

    # HDRTools is compiled with the system GCC runtime; avoid inheriting IDE
    # helper library paths that may shadow the system libstdc++.
    hdrtools_env = os.environ.copy()
    hdrtools_env.pop("LD_LIBRARY_PATH", None)

    try:
        with wpsnr_log.open("w", encoding="utf-8") as f_log:
            subprocess.run(
                wpsnr_cmd,
                check=True,
                stdout=f_log,
                stderr=subprocess.STDOUT,
                env=hdrtools_env,
            )

        subprocess.run(
            yuv2exr_cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=hdrtools_env,
        )
        subprocess.run(
            ori_yuv2exr_cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=hdrtools_env,
        )

        with deltae_log.open("w", encoding="utf-8") as f_log:
            subprocess.run(
                deltae_cmd,
                check=True,
                stdout=f_log,
                stderr=subprocess.STDOUT,
                env=hdrtools_env,
            )

        wpsnr_value = _parse_wpsnr_score(wpsnr_log)
        deltae_value, psnrl100_value = _parse_deltae_psnrl100(deltae_log)

        metrics_csv = work_root_path / f"{dist_stem}.csv"
        with metrics_csv.open("w", encoding="utf-8", newline="") as f_out:
            writer = csv.writer(f_out)
            writer.writerow(["video", "wpsnr", "psnrl100", "deltae"])
            writer.writerow([dist_stem, wpsnr_value, psnrl100_value, deltae_value])

        combined_score = f"{wpsnr_value:.6f}/{psnrl100_value:.6f}/{deltae_value:.6f}"
        return combined_score
    finally:
        if not keep_exr:
            if exr_dir.exists():
                for p in exr_dir.glob("*.exr"):
                    p.unlink()
                exr_dir.rmdir()
            if ori_exr_dir.exists():
                for p in ori_exr_dir.glob("*.exr"):
                    p.unlink()
                ori_exr_dir.rmdir()
