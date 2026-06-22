import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import numpy as np
import pandas as pd


PY = sys.executable
SUPPORTED_FRAMEWORKS = {"ColorVideoVDP", "VMAF", "HDRMetrics"}
PROJECT_ROOT = Path(__file__).resolve().parent


def config_enabled(value):
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "flase", "no", "none"}
    return bool(value)


class _WorkerEnv:
    def __init__(self, workdir):
        self.workdir = workdir

    def activate(self, check_exists=False):
        if not self.workdir:
            return None
        wd_path = Path(self.workdir)
        if check_exists and not wd_path.exists():
            return None
        os.chdir(str(wd_path))
        if str(wd_path) not in sys.path:
            sys.path.insert(0, str(wd_path))
        return wd_path


def _cvvdp_extract_score(csv_path: Path, metric) -> float:
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    col = metric
    v = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(v):
        return float(v.iloc[0])
    num = df.select_dtypes(include="number")
    if num.shape[1] and len(num):
        return float(num.iloc[0, 0])
    raise ValueError(f"Cannot parse score from: {csv_path}")


def _convert_to_pu21_yuv(
    dist_path_str,
    ref_path_str,
    pix_fmt,
    width=None,
    height=None,
    use_temp_suffix=False,
    temp_dir=None,
    force_convert_yuv=False,
    display_model="standard_hdr_pq_tv",
):
    py_iqa_path = Path(__file__).parent / "methods" / "PY-IQA"
    if str(py_iqa_path) not in sys.path:
        sys.path.append(str(py_iqa_path))

    try:
        import pycvvdp
        import torch
    except ImportError as e:
        raise ImportError(f"Failed to import pycvvdp or torch: {e}")

    dist_path = Path(dist_path_str)
    ref_path = Path(ref_path_str)

    if temp_dir is None:
        temp_dir = dist_path.parent
    else:
        temp_dir = Path(temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

    suffix = f"_pu21_{pix_fmt}.yuv"
    if use_temp_suffix:
        suffix = f"_pu21_{uuid.uuid4()}_{pix_fmt}.yuv"

    dist_yuv_path = temp_dir / f"{dist_path.stem}_dist{suffix}"
    ref_yuv_path = temp_dir / f"{dist_path.stem}_ref{suffix}"

    if not force_convert_yuv and dist_yuv_path.exists() and ref_yuv_path.exists():
        return dist_yuv_path, ref_yuv_path, False, False

    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    display_photometry = pycvvdp.vvdp_display_photometry.load(display_model, config_paths=[])
    display_geometry = pycvvdp.vvdp_display_geometry.load(display_model, config_paths=[])

    vs = pycvvdp.video_source_file(
        str(dist_path),
        str(ref_path),
        display_photometry=display_photometry,
        config_paths=[],
        full_screen_resize="nearest",
        resize_resolution=display_geometry.resolution,
        preload=False,
        ffmpeg_cc=False,
        verbose=False,
    )

    vh, vw, num_frames = vs.get_video_size()

    def open_ffmpeg_pipe(out_path):
        cmd = [
            "ffmpeg",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb48le",
            "-s",
            f"{vw}x{vh}",
            "-r",
            "25",
            "-i",
            "-",
            "-pix_fmt",
            pix_fmt,
            "-vf",
            "scale=out_color_matrix=bt2020:out_range=limited",
            str(out_path),
        ]
        return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    dist_proc = open_ffmpeg_pipe(dist_yuv_path)
    ref_proc = open_ffmpeg_pipe(ref_yuv_path)

    try:
        for i in range(num_frames):
            ref_t = vs.get_reference_frame(i, device, "RGB2020pu21")
            dist_t = vs.get_test_frame(i, device, "RGB2020pu21")

            def process_frame(t):
                if isinstance(t, (tuple, list)):
                    t = t[0]
                while t.dim() > 3:
                    t = t.squeeze(0) if t.shape[0] == 1 else t[0]
                img = t.permute(1, 2, 0).cpu().numpy()
                img = np.clip(img, 0, 1)
                return (img * 65535).astype(np.uint16).tobytes()

            dist_proc.stdin.write(process_frame(dist_t))
            ref_proc.stdin.write(process_frame(ref_t))
    finally:
        if dist_proc:
            dist_proc.stdin.close()
            dist_proc.wait()
        if ref_proc:
            ref_proc.stdin.close()
            ref_proc.wait()

    return dist_yuv_path, ref_yuv_path, True, True


def _convert_to_yuv(
    dist_path_str,
    ref_path_str,
    pix_fmt,
    width=None,
    height=None,
    use_temp_suffix=False,
    temp_dir=None,
    force_convert_yuv=False,
    src_pix_fmt=None,
    resize_flag=None,
):
    dist_path = Path(dist_path_str)
    ref_path = Path(ref_path_str)

    if temp_dir:
        temp_path = Path(temp_dir)
        temp_path.mkdir(parents=True, exist_ok=True)

    if use_temp_suffix:
        if dist_path.suffix.lower() == ".yuv" and not force_convert_yuv:
            dist_yuv_path = dist_path
            dist_created = False
        else:
            suffix = f".{uuid.uuid4().hex[:8]}.yuv"
            dist_yuv_path = temp_path / (dist_path.stem + suffix) if temp_dir else dist_path.with_suffix(suffix)
            dist_created = True
        if ref_path.suffix.lower() == ".yuv" and not force_convert_yuv:
            ref_yuv_path = ref_path
            ref_created = False
        else:
            suffix = f".{uuid.uuid4().hex[:8]}.yuv"
            ref_yuv_path = temp_path / (ref_path.stem + suffix) if temp_dir else ref_path.with_suffix(suffix)
            ref_created = True
    else:
        if temp_dir:
            dist_yuv_path = temp_path / (dist_path.stem + ".yuv")
            ref_yuv_path = temp_path / (ref_path.stem + ".yuv")
        else:
            dist_yuv_path = dist_path.with_suffix(".yuv")
            ref_yuv_path = ref_path.with_suffix(".yuv")
        dist_created = not dist_yuv_path.exists()
        ref_created = not ref_yuv_path.exists()

    def convert(src_path, out_path, should_create):
        if not should_create:
            return
        cmd = ["ffmpeg", "-y"]
        is_raw = src_path.suffix.lower() == ".yuv" and width is not None and height is not None and src_pix_fmt
        if is_raw:
            cmd.extend(
                [
                    "-f",
                    "rawvideo",
                    "-pixel_format",
                    str(src_pix_fmt),
                    "-video_size",
                    f"{int(width)}x{int(height)}",
                    "-i",
                    str(src_path),
                ]
            )
        else:
            cmd.extend(["-i", str(src_path)])
        if pix_fmt and str(pix_fmt).lower() not in ["none", "auto", "false"]:
            cmd.extend(["-pix_fmt", str(pix_fmt)])
        if width is not None and height is not None:
            if resize_flag:
                cmd.extend(["-vf", f"scale={int(width)}:{int(height)}:flags={resize_flag}"])
            else:
                cmd.extend(["-s", f"{int(width)}x{int(height)}"])
        cmd.extend(["-vsync", "0", str(out_path)])
        subprocess.run(
            cmd,
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    convert(dist_path, dist_yuv_path, dist_created)
    convert(ref_path, ref_yuv_path, ref_created)
    return dist_yuv_path, ref_yuv_path, dist_created, ref_created


def _worker_vmaf_yuv_cli(dist_path_str, ref_path_str, trc, vmaf_cfg, vmaf_log_dir, display_model=None):
    pix_fmt = vmaf_cfg.get("pix_fmt", "yuv420p10le")
    w = int(vmaf_cfg.get("w", 3840))
    h = int(vmaf_cfg.get("h", 2160))

    seq = Path(dist_path_str).stem
    out_json_path = Path(vmaf_log_dir) / f"vmaf_{seq}.json"
    if out_json_path.exists():
        try:
            with open(out_json_path, "r") as f:
                data = json.load(f)
            if "pooled_metrics" in data and "vmaf" in data["pooled_metrics"]:
                score = float(data["pooled_metrics"]["vmaf"]["mean"])
            elif "aggregate" in data and "VMAF_score" in data["aggregate"]:
                score = float(data["aggregate"]["VMAF_score"])
            else:
                score = None
        except Exception:
            score = None
    else:
        score = None

    enable_pu21 = config_enabled(vmaf_cfg.get("enable_pu21", False))
    if enable_pu21:
        if display_model is None:
            trc_str = str(trc).upper()
            if trc_str == "HLG":
                display_model = vmaf_cfg.get("display_model_hlg", "standard_hdr_hlg_tv")
            elif trc_str == "PQ":
                if score is not None:
                    return dist_path_str, score
                display_model = vmaf_cfg.get("display_model_pq", "standard_hdr_pq_tv")
            else:
                display_model = vmaf_cfg.get("display_model_sdr", "standard_fhd")

        dist_yuv_path, ref_yuv_path, dist_created, ref_created = _convert_to_pu21_yuv(
            dist_path_str,
            ref_path_str,
            pix_fmt=pix_fmt,
            width=w,
            height=h,
            use_temp_suffix=True,
            display_model=display_model,
        )
    else:
        dist_yuv_path, ref_yuv_path, dist_created, ref_created = _convert_to_yuv(
            dist_path_str,
            ref_path_str,
            pix_fmt=pix_fmt,
            width=w,
            height=h,
            use_temp_suffix=False,
        )

    try:
        os.makedirs(vmaf_log_dir, exist_ok=True)
        out_json = str(out_json_path)
        vmaf_bin = Path(str(vmaf_cfg.get("vmaf_bin", "vmaf")))
        if not vmaf_bin.is_absolute() and (PROJECT_ROOT / vmaf_bin).exists():
            vmaf_bin = (PROJECT_ROOT / vmaf_bin).resolve()

        model = str(vmaf_cfg.get("model", "version=vmaf_4k_v0.6.1neg"))
        if model.startswith("path="):
            model_path = Path(model[len("path=") :])
            if not model_path.is_absolute() and (PROJECT_ROOT / model_path).exists():
                model = f"path={(PROJECT_ROOT / model_path).resolve()}"

        cmd = [
            str(vmaf_bin),
            "-p",
            str(vmaf_cfg.get("p", "420")),
            "-w",
            str(w),
            "-h",
            str(h),
            "-b",
            str(vmaf_cfg.get("b", 10)),
            "-r",
            str(ref_yuv_path),
            "-d",
            str(dist_yuv_path),
            "-m",
            model,
            "-o",
            out_json,
            "--json",
        ]
        subprocess.run(cmd, check=True)
        with open(out_json, "r") as f:
            data = json.load(f)
        if "pooled_metrics" in data and "vmaf" in data["pooled_metrics"]:
            score = float(data["pooled_metrics"]["vmaf"]["mean"])
        elif "aggregate" in data and "VMAF_score" in data["aggregate"]:
            score = float(data["aggregate"]["VMAF_score"])
        else:
            raise KeyError(f"Unknown VMAF json schema keys: {list(data.keys())}")
        return dist_path_str, score
    finally:
        if dist_created and dist_yuv_path.exists():
            dist_yuv_path.unlink()
        if ref_created and ref_yuv_path.exists():
            ref_yuv_path.unlink()


def _worker_cvvdp(dist_path_str, ref_path_str, trc, device, fw_cfg, raw_out_dir, display_model=None):
    dist = Path(dist_path_str)
    ref = Path(ref_path_str)
    if display_model is not None:
        display = display_model
    else:
        trc_str = str(trc).upper()
        if trc_str == "HLG":
            display = "standard_hdr_hlg_tv"
        elif trc_str == "PQ":
            display = "standard_hdr_pq_tv"
        elif trc_str in ["SDR", "BT.709"]:
            display = "standard_fhd"
        else:
            display = str(trc)

    raw_out_dir = Path(raw_out_dir)
    raw_out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = raw_out_dir / f"{dist.stem}.pid{os.getpid()}.csv"
    cmd = [
        PY,
        "-m",
        "pycvvdp.run_cvvdp",
        "--test",
        str(dist),
        "--ref",
        str(ref),
        "--display",
        display,
        "--result",
        str(out_csv),
        "--gpu-mem",
        str(int(fw_cfg.get("gpu_mem", 16))),
        "--device",
        str(device),
    ]

    if dist.suffix.lower() in [".mp4", ".mkv", ".mov", ".avi", ".yuv", ".webm"]:
        cmd += ["-f", "nearest"]

    metric = fw_cfg.get("metric", "cvvdp")
    if metric:
        cmd += ["-m", str(metric)]
    workdir = Path(fw_cfg.get("workdir", "."))
    subprocess.run(cmd, cwd=str(workdir), check=True)
    return dist_path_str, _cvvdp_extract_score(out_csv, metric)


def _worker_hdrmetrics(dist_path_str, ref_path_str, trc, fw_cfg, work_root):
    if not ref_path_str:
        raise ValueError("HDRMetrics is full-reference: ref_dir/ref_name is required.")
    dist_path = Path(dist_path_str)
    ref_path = Path(ref_path_str)
    dist_yuv = dist_path.with_suffix(".yuv") if dist_path.suffix.lower() != ".yuv" else dist_path
    ref_yuv = ref_path.with_suffix(".yuv") if ref_path.suffix.lower() != ".yuv" else ref_path
    if not dist_yuv.exists():
        raise FileNotFoundError(f"HDRMetrics YUV file not found for dist: {dist_yuv}")
    if not ref_yuv.exists():
        raise FileNotFoundError(f"HDRMetrics YUV file not found for ref: {ref_yuv}")

    workdir = fw_cfg.get("workdir")
    _WorkerEnv(workdir).activate(check_exists=True)

    from hdrmetrics_runner import run_hdrmetrics

    def root_path(value):
        path = Path(value)
        return str(path if path.is_absolute() else PROJECT_ROOT / path)

    score = run_hdrmetrics(
        str(ref_yuv),
        str(dist_yuv),
        hdrtools_bin=root_path(fw_cfg.get("hdrtools_bin", "/data1/Users/wangjiayi/workspace/HDRTools-master/build/bin")),
        wpsnr_cfg=root_path(fw_cfg.get("wpsnr_cfg", "/data1/Users/wangjiayi/workspace/HDRTools-master/cfg/HDRMetricsYUV.cfg")),
        deltae_cfg=root_path(fw_cfg.get(
            "deltae_cfg",
            "/data1/Users/wangjiayi/workspace/HDRTools-master/cfg/JCTVC_CTC_cfgFiles/YCbCr/HDRMetric_CfE.cfg",
        )),
        hdrconvert_cfg=root_path(fw_cfg.get(
            "hdrconvert_cfg",
            "/data1/Users/wangjiayi/workspace/HDRTools-master/cfg/JCTVC_CTC_cfgFiles/YCbCr/HDRConvertYCbCr420ToEXR2020.cfg",
        )),
        width=int(fw_cfg.get("width", 3840)),
        height=int(fw_cfg.get("height", 2160)),
        bit_depth=int(fw_cfg.get("bit_depth", 10)),
        trc=trc,
        work_root=str(work_root),
        weight_table=root_path(fw_cfg.get("weight_table", "/data1/Users/wangjiayi/workspace/HDRTools-master/cfg/hdrTable.txt")),
    )
    return dist_path_str, score


def dispatch_one(framework, fw_cfg, v, global_cfg):
    if framework not in SUPPORTED_FRAMEWORKS:
        raise ValueError(f"Unsupported framework in worker_new.py: {framework}")
    if not v["ref"]:
        raise ValueError(f"{framework} is full-reference: ref_dir/ref_name is required.")

    device = global_cfg.get("device", "cuda:0")
    if framework == "VMAF":
        return _worker_vmaf_yuv_cli(
            v["dist"],
            v["ref"],
            v["trc"],
            fw_cfg,
            fw_cfg.get("VMAF_log_dir"),
            v.get("display_model"),
        )
    if framework == "ColorVideoVDP":
        return _worker_cvvdp(
            v["dist"],
            v["ref"],
            v["trc"],
            device,
            fw_cfg,
            fw_cfg.get("ColorVideoVDP_log_dir"),
            v.get("display_model"),
        )
    return _worker_hdrmetrics(
        v["dist"],
        v["ref"],
        v["trc"],
        fw_cfg,
        fw_cfg.get("HDRMetrics_log_dir"),
    )
