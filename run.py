import os
import sys
import yaml
import argparse
from pathlib import Path
from dataset_new import _run_dataset
 
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=str, required=True)
    p.add_argument("--only", type=str, default="", help="comma separated frameworks to run, e.g. ColorVideoVDP,VMAF")
    p.add_argument("--datasets", type=str, default="", help="comma separated datasets to run")
    p.add_argument("--device", type=str, help="device to run on")
    p.add_argument("--worker", type=int, help="number of workers")
    return p.parse_args()

def main():
    print("Starting run.py...")
    args = parse_args()
    print(f"Loading config: {args.config}")
    with open(args.config, "r") as f:
        cfg = yaml.safe_load(f)
    global_cfg = cfg.get("global", {})
    if args.device is not None:
        global_cfg["device"] = args.device
    if args.worker is not None:
        global_cfg["num_workers"] = args.worker
    out_root = global_cfg.get("output_dir", "vqa_infer_result")
    frameworks = cfg.get("frameworks", {})
    datasets = cfg.get("datasets", {})
    runs = cfg.get("runs", [])
    only = set(x.strip() for x in args.only.split(",") if x.strip()) if args.only else None
    only_datasets = set(x.strip() for x in args.datasets.split(",") if x.strip()) if args.datasets else None
    base_dir = Path(__file__).resolve().parent
    for run in runs:
        framework = run["framework"]
        if only is not None and framework not in only:
            continue
        fw_cfg = frameworks.get(framework, {})
        workdir = fw_cfg.get("workdir", "")
        if workdir:
            wd = Path(workdir)
            if not wd.is_absolute():
                wd = base_dir / wd
            os.chdir(str(wd))
            fw_cfg["workdir"] = str(wd)  # Update workdir to absolute path
            if str(wd) not in sys.path:
                sys.path.insert(0, str(wd))
        ds_list = run.get("datasets", [])
        for ds_name in ds_list:
            if only_datasets is not None and ds_name not in only_datasets:
                continue
            if ds_name not in datasets:
                raise KeyError(f"Dataset '{ds_name}' not found in config.datasets")
            _run_dataset(framework, fw_cfg, ds_name, datasets[ds_name], global_cfg, out_root)

if __name__ == "__main__":
    main()
