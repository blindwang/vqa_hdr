from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from tqdm import tqdm

from worker_new import SUPPORTED_FRAMEWORKS, config_enabled, dispatch_one


def _expand_zjuhdr_from_csv(test_data: pd.DataFrame, ref_dir: Path, dist_dir: Path):
    required_cols = {"ref_name", "dis_name"}
    missing_cols = required_cols - set(test_data.columns)
    if missing_cols:
        raise ValueError(f"ZJUHDR CSV missing required columns: {sorted(missing_cols)}")

    rows = []
    for i in range(len(test_data)):
        row_data = test_data.iloc[i].to_dict()
        ref_name = str(row_data.get("ref_name", "")).strip()
        dis_name = str(row_data.get("dis_name", "")).strip()
        if not ref_name or not dis_name:
            print(f"{row_data} - ref_name or dis_name is null")
            continue

        item = row_data.copy()
        item["ref"] = str(ref_dir / ref_name)
        item["dist"] = str(dist_dir / dis_name)
        item["trc"] = row_data.get("trc", "PQ")
        rows.append(item)

    return rows


def _load_checkpoint(out_csv: Path):
    if out_csv.exists():
        df = pd.read_csv(out_csv)
        if "video" in df.columns and "score" in df.columns:
            return dict(zip(df["video"].astype(str).values, df["score"].values))
    return {}


def _set_framework_log_dir(framework, fw_cfg, ds_name, log_root):
    if framework == "ColorVideoVDP":
        fw_cfg["ColorVideoVDP_log_dir"] = str(log_root / "ColorVideoVDP_log" / ds_name)
    elif framework == "VMAF":
        if config_enabled(fw_cfg.get("enable_pu21")):
            fw_cfg["VMAF_log_dir"] = str(log_root / f"{ds_name}_VMAF_PU21")
        else:
            fw_cfg["VMAF_log_dir"] = str(log_root / "VMAF_log" / ds_name)
    elif framework == "HDRMetrics":
        fw_cfg["HDRMetrics_log_dir"] = str(log_root / "HDRMetrics_log" / ds_name)


def _run_dataset(framework, fw_cfg, ds_name, ds_cfg, global_cfg, out_root):
    if framework not in SUPPORTED_FRAMEWORKS:
        raise ValueError(f"dataset_new.py only supports: {sorted(SUPPORTED_FRAMEWORKS)}")

    csv_path = Path(ds_cfg["test_data"])
    ref_dir = Path(ds_cfg["ref_dir"])
    dist_dir = Path(ds_cfg["dis_dir"])
    test_data = pd.read_csv(csv_path)
    videos = _expand_zjuhdr_from_csv(test_data, ref_dir, dist_dir)

    display_model = ds_cfg.get("display_model")
    if display_model:
        for v in videos:
            v["display_model"] = display_model

    print(f"Expanded ZJUHDR to {len(videos)} videos")
    out_root = Path(out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    out_suffix = framework
    if framework == "VMAF" and config_enabled(fw_cfg.get("enable_pu21")):
        out_suffix = f"{framework}_PU21"
    out_csv = out_root / f"{ds_name}_{out_suffix}.csv"

    result = _load_checkpoint(out_csv)
    done = set(str(k) for k, v in result.items() if not pd.isna(v))
    todo = [v for v in videos if v["dist"] not in done]

    num_workers = int(global_cfg.get("num_workers", 1))
    log_root = Path(global_cfg.get("output_dir", out_root))
    _set_framework_log_dir(framework, fw_cfg, ds_name, log_root)

    if num_workers <= 1:
        for v in tqdm(todo, desc=f"{ds_name} ({framework})"):
            v["dataset"] = ds_name
            k, s = dispatch_one(framework, fw_cfg, v, global_cfg)
            result[k] = s
    else:
        with ProcessPoolExecutor(max_workers=num_workers) as ex:
            futs = []
            for v in todo:
                v["dataset"] = ds_name
                futs.append(ex.submit(dispatch_one, framework, fw_cfg, v, global_cfg))
            for fut in tqdm(as_completed(futs), total=len(futs), desc=f"{ds_name} ({framework}, {num_workers}w)"):
                k, s = fut.result()
                result[k] = s

    pd.DataFrame.from_dict(result, orient="index", columns=["score"]).rename_axis("video").to_csv(out_csv)
