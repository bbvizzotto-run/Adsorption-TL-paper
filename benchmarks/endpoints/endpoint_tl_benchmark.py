#!/usr/bin/env python3
"""Endpoint-only, leakage-controlled transfer-learning benchmark.

The plan subcommand is TensorFlow-free.  The run subcommand consumes only a
frozen plan and its hashes; it never re-reads the workbook for observations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

EXPECTED_WORKBOOK_SHA: str | None = None  # supply a project-approved pin if appropriate
FEATURES = ["pH", "temperature_C", "C0_mg_L", "time_min"]
TARGETS_DEFAULT = ["Al:Si-APTS", "Al:Si-APTS-CO", "Fe:Si", "Fe:Si-APTS", "Fe:Si-APTS-CO"]
PROTOCOLS = ["FS", "random_frozen", "TL_frozen", "TL_finetune", "Ridge", "mean_baseline"]
BLOCK_STARTS = (1, 12, 23)
BLOCK_WIDTH = 10
HEADER_ROW = 2
DATA_START_ROW = 3
SOURCE_TARGET = "Al:Si"
OBS_COLUMNS = [
    "record_id", "target", "metal", "adsorbent", "sheet_name", "block_start_col",
    "worksheet_row", "worksheet_col_start", "worksheet_coord", "volume_ml", "mass_g",
    "dose_g_L", "temperature_C", "time_min", "time_raw", "time_header", "agitation_rpm",
    "pH", "C0_mg_L", "q", "R_percent", "condition_key", "q_unit_assumed",
    "q_unit_flag", "reported_blank_corrected",
]


class BenchmarkError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_int(*parts: Any) -> int:
    raw = "|".join(str(x) for x in parts).encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:8], 16) % (2**31 - 1)


def json_dump(path: Path, value: Any, immutable: bool = False) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    if immutable:
        path.chmod(0o444)


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fieldnames: list[str], immutable: bool = False) -> None:
    rows = list(rows)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    if immutable:
        path.chmod(0o444)


def hash_manifest_files(directory: Path, names: Iterable[str]) -> dict[str, str]:
    return {name: sha256_file(directory / name) for name in names}


def fmt_num(value: Any) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return "NA"
    return f"{float(value):.12g}"


def target_parts(target: str) -> tuple[str, str]:
    try:
        metal, adsorbent = target.split(":", 1)
    except ValueError as exc:
        raise BenchmarkError(f"Invalid target name: {target}") from exc
    if metal not in {"Al", "Fe"}:
        raise BenchmarkError(f"Invalid target metal in {target}")
    return metal, adsorbent


def parse_plan_args(args: argparse.Namespace) -> dict[str, Any]:
    targets = list(dict.fromkeys(args.targets))
    valid = set(TARGETS_DEFAULT)
    if any(t not in valid for t in targets):
        raise BenchmarkError(f"Targets must be drawn from {sorted(valid)}")
    if not targets:
        raise BenchmarkError("At least one target is required")
    seeds = list(dict.fromkeys(args.seeds))
    held = list(dict.fromkeys(args.held_temperatures))
    fractions = sorted(set(float(x) for x in args.fractions))
    if not seeds or not held or not fractions:
        raise BenchmarkError("seeds, held temperatures, and fractions cannot be empty")
    if any(x <= 0 or x > 1 for x in fractions):
        raise BenchmarkError("fractions must be in (0, 1]")
    if any(x not in {30, 40, 50, 60} for x in held):
        raise BenchmarkError("held temperatures must be among 30, 40, 50, 60 C")
    if args.epochs < 1 or args.patience < 1 or args.batch_size < 1 or args.learning_rate <= 0:
        raise BenchmarkError("Epochs, patience, batch size and learning rate must be positive")
    return {
        "seeds": seeds,
        "fractions": fractions,
        "held_temperatures": held,
        "targets": targets,
        "epochs": int(args.epochs),
        "patience": int(args.patience),
        "batch_size": int(args.batch_size),
        "learning_rate": float(args.learning_rate),
        "simulations_enabled": not bool(args.no_simulations),
        "simulation_points": 21,
        "simulation_C0_min": 20.0,
        "simulation_C0_max": 200.0,
        "blank_status_requested": args.blank_status,
        "save_models": bool(args.save_models),
    }


def condition_key(row: dict[str, Any]) -> str:
    return "|".join([
        row["metal"], row["adsorbent"], f"pH={fmt_num(row['pH'])}",
        f"T={fmt_num(row['temperature_C'])}", f"C0={fmt_num(row['C0_mg_L'])}",
        f"dose={fmt_num(row['dose_g_L'])}",
    ])


def endpoint_row(
    metal: str, sheet: str, block_start: int, row_number: int, values: list[Any],
    q_header: str, time_header: str, blank_status: str,
) -> dict[str, Any]:
    ads, volume, mass, temp, time_raw, agitation, ph, c0, q, recovery = values
    target = f"{metal}:{ads}"
    dose = None if mass is None or volume is None else float(mass) / float(volume) * 1000.0
    row = {
        "record_id": f"{metal}|{sheet}|r{row_number}|c{block_start}",
        "target": target,
        "metal": metal,
        "adsorbent": ads,
        "sheet_name": sheet,
        "block_start_col": block_start,
        "worksheet_row": row_number,
        "worksheet_col_start": block_start,
        "worksheet_coord": f"{get_column_letter(block_start)}{row_number}:{get_column_letter(block_start + BLOCK_WIDTH - 1)}{row_number}",
        "volume_ml": volume,
        "mass_g": mass,
        "dose_g_L": dose,
        "temperature_C": temp,
        "time_min": time_raw,
        "time_raw": time_raw,
        "time_header": time_header,
        "agitation_rpm": agitation,
        "pH": ph,
        "C0_mg_L": c0,
        "q": q,
        "R_percent": recovery,
        "condition_key": "",
        "q_unit_assumed": "unconfirmed_not_forced",
        "q_unit_flag": "stored_response_unit_unconfirmed",
        "reported_blank_corrected": blank_status if blank_status == "unavailable" else "reported_corrected_unverified",
    }
    row["condition_key"] = condition_key(row)
    return row


def audit_workbook(workbook: Path, config: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    wb = load_workbook(workbook, data_only=True, read_only=True)
    requested = set(config["targets"]) | {SOURCE_TARGET}
    selected: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    sheets = [("Al", "Dados Alumínio"), ("Fe", "Dados Ferro")]
    for metal, sheet in sheets:
        if sheet not in wb.sheetnames:
            raise BenchmarkError(f"Missing required worksheet: {sheet}")
        ws = wb[sheet]
        for block_start in BLOCK_STARTS:
            headers = [ws.cell(HEADER_ROW, c).value for c in range(block_start, block_start + BLOCK_WIDTH)]
            if headers[0] is None:
                continue
            q_header, time_header = headers[8], headers[4]
            for r in range(DATA_START_ROW, ws.max_row + 1):
                vals = [ws.cell(r, c).value for c in range(block_start, block_start + BLOCK_WIDTH)]
                if vals[0] is None:
                    continue
                row = endpoint_row(metal, sheet, block_start, r, vals, q_header, time_header, config["blank_status_requested"])
                reasons: list[str] = []
                if row["target"] not in requested:
                    reasons.append("target_not_requested")
                if row["volume_ml"] != 20:
                    reasons.append("volume_not_20_ml")
                if row["mass_g"] is None:
                    reasons.append("missing_mass_no_impute")
                elif not math.isclose(float(row["mass_g"]), 0.03, rel_tol=0, abs_tol=1e-12):
                    reasons.append("dose_mass_not_0.03_g")
                if row["dose_g_L"] is not None and not math.isclose(float(row["dose_g_L"]), 1.5, rel_tol=0, abs_tol=1e-9):
                    reasons.append("dose_not_1.5_g_L")
                if row["temperature_C"] not in {30, 40, 50, 60}:
                    reasons.append("temperature_not_endpoint_grid")
                if row["time_raw"] != 1440:
                    reasons.append("time_not_1440_stored_value")
                if row["agitation_rpm"] != 150:
                    reasons.append("agitation_not_150_rpm")
                expected_ph = 5.5 if metal == "Al" else 5
                if row["pH"] != expected_ph:
                    reasons.append(f"pH_not_{expected_ph}")
                if row["C0_mg_L"] not in {20, 50, 100, 150, 200}:
                    reasons.append("C0_not_endpoint_grid")
                if row["q"] is None or not isinstance(row["q"], (int, float)) or not math.isfinite(float(row["q"])):
                    reasons.append("missing_response_no_impute")
                eligible = not reasons
                audit_row = {
                    "record_id": row["record_id"], "sheet_name": sheet, "block_start_col": block_start,
                    "worksheet_row": r, "worksheet_coord": row["worksheet_coord"], "target": row["target"],
                    "adsorbent": row["adsorbent"], "requested_target": row["target"] in requested,
                    "volume_ml": row["volume_ml"], "mass_g": row["mass_g"], "temperature_C": row["temperature_C"],
                    "time_raw": row["time_raw"], "time_header": row["time_header"], "pH": row["pH"],
                    "C0_mg_L": row["C0_mg_L"], "response_present": bool(row["q"] is not None),
                    "decision": "selected" if eligible else "excluded",
                    "primary_reason": "selected" if eligible else reasons[0],
                    "all_reasons": ";".join(reasons) if reasons else "selected",
                    "q_unit_flag": row["q_unit_flag"],
                }
                audit.append(audit_row)
                if eligible:
                    selected.append(row)
    observations = pd.DataFrame(selected, columns=OBS_COLUMNS)
    if observations.empty:
        raise BenchmarkError("Endpoint selection produced no observations")
    if observations["condition_key"].duplicated().any():
        raise BenchmarkError("Duplicate physical condition in selected endpoint observations")
    expected = {"Al:Si": 19, "Al:Si-APTS": 19, "Al:Si-APTS-CO": 19, "Fe:Si": 20, "Fe:Si-APTS": 20, "Fe:Si-APTS-CO": 20}
    if set(config["targets"]) == set(TARGETS_DEFAULT):
        got = observations.groupby("target").size().to_dict()
        if got != expected:
            raise BenchmarkError(f"Expected endpoint counts {expected}, got {got}")
        if len(observations) != 117:
            raise BenchmarkError(f"Expected 117 selected endpoint rows, got {len(observations)}")
    audit_df = pd.DataFrame(audit)
    exclusions = audit_df[audit_df["decision"] == "excluded"].copy()
    count_rows = []
    for (sheet, block, decision, reason), group in audit_df.groupby(["sheet_name", "block_start_col", "decision", "primary_reason"], dropna=False):
        count_rows.append({"sheet_name": sheet, "block_start_col": block, "decision": decision, "reason": reason, "count": len(group)})
    counts = pd.DataFrame(count_rows)
    return observations, audit_df, exclusions, counts


def split_temperatures(held: int) -> tuple[list[int], int]:
    remaining = sorted(set([30, 40, 50, 60]) - {held})
    validation = remaining[len(remaining) // 2]
    train = [t for t in remaining if t != validation]
    return train, validation


def make_partition_manifest(obs: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    systems = [("source", SOURCE_TARGET)] + [("target", t) for t in config["targets"]]
    for fold_id, held in enumerate(config["held_temperatures"]):
        train_t, val_t = split_temperatures(held)
        for system, target in systems:
            data = obs[obs["target"] == target]
            if data.empty:
                raise BenchmarkError(f"No observations for {target}")
            if data["condition_key"].duplicated().any():
                raise BenchmarkError(f"Duplicate conditions for {system}/{target}")
            for _, row in data.iterrows():
                temp = int(row["temperature_C"])
                partition = "test" if temp == held else "validation" if temp == val_t else "train"
                rows.append({
                    "fold_id": fold_id, "held_temperature_C": held, "validation_temperature_C": val_t,
                    "system": system, "target": target, "partition": partition,
                    "condition_key": row["condition_key"], "record_id": row["record_id"],
                    "temperature_C": temp,
                })
            expected = len(data)
            seen = {x["record_id"] for x in rows if x["fold_id"] == fold_id and x["system"] == system and x["target"] == target}
            if len(seen) != expected:
                raise BenchmarkError("Partition manifest lost or duplicated condition IDs")
    manifest = pd.DataFrame(rows)
    for keys, group in manifest.groupby(["fold_id", "system", "target"], sort=False):
        if group["record_id"].duplicated().any() or set(group["partition"]) != {"train", "validation", "test"}:
            raise BenchmarkError(f"Invalid partition for {keys}")
    return manifest


def make_fraction_manifest(obs: pd.DataFrame, partitions: pd.DataFrame, config: dict[str, Any]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for seed in config["seeds"]:
        for fold_id in range(len(config["held_temperatures"])):
            for target in config["targets"]:
                part = partitions[(partitions.fold_id == fold_id) & (partitions.system == "target") & (partitions.target == target)]
                train = part[part.partition == "train"].sort_values("condition_key")
                ranked = sorted(train["record_id"].tolist(), key=lambda x: hashlib.sha256(f"{seed}|{fold_id}|{target}|{x}".encode()).hexdigest())
                selected_sets = {}
                for fraction in config["fractions"]:
                    n = int(math.ceil(float(fraction) * len(ranked)))
                    selected_sets[fraction] = set(ranked[:n])
                    if fraction != config["fractions"][0]:
                        prior = config["fractions"][config["fractions"].index(fraction) - 1]
                        if not selected_sets[prior].issubset(selected_sets[fraction]):
                            raise BenchmarkError("Target fraction manifest is not nested")
                for fraction in config["fractions"]:
                    selected = selected_sets[fraction]
                    for _, row in part.iterrows():
                        rows.append({
                            "seed": seed, "fold_id": fold_id, "target": target, "fraction": fraction,
                            "partition": row["partition"], "record_id": row["record_id"],
                            "condition_key": row["condition_key"],
                            "selected_for_fit": bool(row["record_id"] in selected and row["partition"] == "train"),
                        })
    return pd.DataFrame(rows)


def create_plan(args: argparse.Namespace) -> Path:
    config = parse_plan_args(args)
    workbook = Path(args.workbook).resolve()
    if not workbook.exists():
        raise BenchmarkError(f"Workbook not found: {workbook}")
    workbook_sha = sha256_file(workbook)
    if EXPECTED_WORKBOOK_SHA is not None and workbook_sha != EXPECTED_WORKBOOK_SHA:
        raise BenchmarkError(f"Workbook SHA mismatch: expected {EXPECTED_WORKBOOK_SHA}, got {workbook_sha}")
    out = Path(args.out).resolve()
    if out.exists():
        raise BenchmarkError(f"Refusing to overwrite existing plan directory: {out}")
    out.mkdir(parents=True)
    observations, audit, exclusions, counts = audit_workbook(workbook, config)
    observations.to_csv(out / "dataset.csv", index=False, lineterminator="\n")
    observations.to_csv(out / "observations.csv", index=False, lineterminator="\n")
    audit.to_csv(out / "dataset_audit.csv", index=False, lineterminator="\n")
    exclusions.to_csv(out / "exclusions.csv", index=False, lineterminator="\n")
    counts.to_csv(out / "exclusion_counts.csv", index=False, lineterminator="\n")
    partitions = make_partition_manifest(observations, config)
    fractions = make_fraction_manifest(observations, partitions, config)
    partitions.to_csv(out / "condition_partition_manifest.csv", index=False, lineterminator="\n")
    fractions.to_csv(out / "target_fraction_manifest.csv", index=False, lineterminator="\n")
    code_sha = sha256_file(Path(__file__).resolve())
    manifest_names = [
        "dataset.csv", "observations.csv", "dataset_audit.csv", "exclusions.csv", "exclusion_counts.csv",
        "condition_partition_manifest.csv", "target_fraction_manifest.csv",
    ]
    protocol = {
        "schema_version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "workbook": {"filename": workbook.name, "sha256": workbook_sha},
        "code_sha256": code_sha,
        "architecture_sha256": sha256_file(Path(__file__).with_name("historical_architecture.py")),
        "dataset_csv_sha256": sha256_file(out / "dataset.csv"),
        "manifest_sha256": hash_manifest_files(out, manifest_names),
        "dataset_rows": int(len(observations)),
        "selected_counts_by_target": {str(k): int(v) for k, v in observations.groupby("target").size().to_dict().items()},
        "config": config,
        "endpoint_selection": {
            "sheets": ["Dados Alumínio", "Dados Ferro"], "blocks_start_columns_1_indexed": list(BLOCK_STARTS),
            "header_row": HEADER_ROW, "data_start_row": DATA_START_ROW, "time_stored_value_exact": 1440,
            "volume_ml": 20, "mass_g": 0.03, "dose_g_L": 1.5, "agitation_rpm": 150,
            "pH_by_metal": {"Al": 5.5, "Fe": 5}, "temperatures_C": [30, 40, 50, 60],
            "C0_mg_L": [20, 50, 100, 150, 200], "stored_q_only": True, "q_correction": "none",
            "no_raw_blank_data": True, "missing_mass_policy": "exclude_no_impute",
            "q_unit_assumed": "unconfirmed_not_forced", "unit_warning": "stored_response_unit_unconfirmed",
        },
        "split_policy": {
            "condition_key": "metal|adsorbent|pH|T|C0|dose", "condition_is_singleton_endpoint": True,
            "held_temperature_global_exclusion": True, "validation_temperature": "median of remaining 3 temperatures",
            "train_temperatures": "two remaining temperatures", "source_and_targets_share_validation_temperature": True,
            "no_duplicate_condition_ids": True, "nested_sampling": True, "fraction_count_is_ceil_of_conditions": True,
            "target_fraction_manifest_created_before_fit": True,
        },
        "model_policy": {
            "historical_module": "historical_architecture.py", "architecture_import": "AdsorptionAI().build_deep_lstm()",
            "features": ["pH", "T", "C0", "time"], "input_shape": ["n", 1, 4],
            "two_lstm_layers": True, "lstm_units": [128, 64], "dropouts": [0.2, 0.1],
            "dense_head": [32, 16, 1], "head_type": "nonlinear_2625_not_33", "constant_time_not_removed": True,
            "dosage_feature_not_added": True, "dose_fixed_by_selection": True, "endpoint_single_step": True,
            "no_recurrent_necessity_claim": True, "same_optimizer_batch_early_stopping": True,
            "scalers_fit_only_source_train": True, "target_does_not_refit_scalers": True,
            "fresh_initial_weights_identical_across_neural_protocols": True,
            "head_reset_policy": "new_head_for_each_protocol; not exact historical run",
            "source_lstm_transfer": "copy both LSTM weights; TL_frozen freezes only LSTMs; TL_finetune trains all",
        },
        "evaluation_policy": {
            "metrics": ["R2", "RMSE", "MAE"], "raw_r2_unclipped": True,
            "score_kind_required": "measured_endpoint", "q_truth_source": "observations.csv",
            "simulation_kind": "simulation_grid", "simulation_has_no_q_true": True,
            "source_performance_separate": True, "pooled_oof": "single pooled R2/RMSE/MAE over fold test predictions",
            "pooled_is_cv_not_one_fit": True, "mean_sd_computational_not_experimental": True,
            "no_test_based_selection": True, "no_lucky_best_seed": True,
            "retrospectively_inspected_not_prospective_confirmatory": True,
        },
        "claims_and_scope": {
            "hypothesis_label": "originalTLhypothesis",
            "validation_label": "nocircularvalidation",
            "exact_historical_run": False, "endpoints_not_kinetics": True, "no_kinetic_memory_proof": True,
            "no_new_kinetics": True, "no_pseudo_measurements": True, "no_simulated_y": True,
            "reported_blank_correction": config["blank_status_requested"],
            "reported_blank_correction_unverified": config["blank_status_requested"] == "reported_corrected",
            "benchmark_purpose": "retrospective_benchmark" if len(config["seeds"]) >= 10 and config["epochs"] >= 50 else "integration_smoke",
        },
    }
    json_dump(out / "protocol.json", protocol, immutable=True)
    checksum = out / "protocol.sha256"
    checksum.write_text(sha256_file(out / "protocol.json") + "\n")
    checksum.chmod(0o444)
    for name in manifest_names:
        (out / name).chmod(0o444)
    return out


class AppendCSV:
    def __init__(self, path: Path, fields: list[str]):
        self.path = path
        self.fields = fields
        self.file = path.open("w", encoding="utf-8", newline="")
        self.writer = csv.DictWriter(self.file, fieldnames=fields, extrasaction="ignore")
        self.writer.writeheader()
        self.file.flush()

    def append(self, row: dict[str, Any]) -> None:
        self.writer.writerow(row)
        self.file.flush()

    def close(self) -> None:
        self.file.close()


def read_and_verify_plan(plan: Path) -> dict[str, Any]:
    protocol_path = plan / "protocol.json"
    if not protocol_path.exists():
        raise BenchmarkError(f"Missing frozen protocol: {protocol_path}")
    checksum_path = plan / "protocol.sha256"
    if not checksum_path.exists() or sha256_file(protocol_path) != checksum_path.read_text().strip():
        raise BenchmarkError("Frozen protocol hash check failed")
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if sha256_file(Path(__file__).with_name("historical_architecture.py")) != protocol["architecture_sha256"]:
        raise BenchmarkError("Historical architecture SHA does not match the frozen plan")
    code_sha = sha256_file(Path(__file__).resolve())
    if code_sha != protocol["code_sha256"]:
        raise BenchmarkError("Current code SHA does not match frozen plan code SHA")
    names = list(protocol["manifest_sha256"])
    for name, expected in protocol["manifest_sha256"].items():
        path = plan / name
        if not path.exists() or sha256_file(path) != expected:
            raise BenchmarkError(f"Frozen manifest hash check failed: {name}")
    if sha256_file(plan / "dataset.csv") != protocol["dataset_csv_sha256"]:
        raise BenchmarkError("Frozen dataset hash check failed")
    # The protocol stores only the basename and input checksum, never a local absolute path.
    if not names:
        raise BenchmarkError("Frozen plan contains no manifests")
    return protocol


def configure_tensorflow() -> Any:
    os.environ.setdefault("TF_NUM_INTRAOP_THREADS", "1")
    os.environ.setdefault("TF_NUM_INTEROP_THREADS", "1")
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("TF_DETERMINISTIC_OPS", "1")
    import tensorflow as tf
    try:
        tf.config.threading.set_intra_op_parallelism_threads(1)
        tf.config.threading.set_inter_op_parallelism_threads(1)
        tf.config.experimental.enable_op_determinism()
    except Exception:
        pass
    return tf


def prepare_training_frame(df: pd.DataFrame, scaler_x: Any, scaler_y: Any, fit: bool = False) -> tuple[np.ndarray, np.ndarray]:
    x = df[["pH", "temperature_C", "C0_mg_L", "time_min"]].astype(float).to_numpy()
    y = df[["q"]].astype(float).to_numpy()
    if fit:
        scaler_x.fit(x)
        scaler_y.fit(y)
    xs = scaler_x.transform(x).astype("float32").reshape((-1, 1, 4))
    ys = scaler_y.transform(y).astype("float32")
    return xs, ys


def tf_dataset(tf: Any, x: np.ndarray, y: np.ndarray, batch: int, shuffle: bool, seed: int) -> Any:
    ds = tf.data.Dataset.from_tensor_slices((x, y))
    options = tf.data.Options()
    options.threading.private_threadpool_size = 1
    options.threading.max_intra_op_parallelism = 1
    options.deterministic = True
    if shuffle:
        ds = ds.shuffle(max(1, len(x)), seed=seed, reshuffle_each_iteration=True)
    return ds.batch(batch).with_options(options).prefetch(1)


def fit_model(tf: Any, model: Any, x_train: np.ndarray, y_train: np.ndarray, x_val: np.ndarray, y_val: np.ndarray, config: dict[str, Any], seed: int) -> tuple[Any, dict[str, list[float]]]:
    model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=config["learning_rate"]), loss="mse", metrics=["mae"])
    callbacks = [tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=config["patience"], restore_best_weights=True)]
    history = model.fit(
        tf_dataset(tf, x_train, y_train, config["batch_size"], True, seed),
        validation_data=tf_dataset(tf, x_val, y_val, config["batch_size"], False, seed),
        epochs=config["epochs"], callbacks=callbacks, verbose=0,
    ).history
    return model, {k: [float(v) for v in vals] for k, vals in history.items()}


def fresh_historical_model(tf: Any, seed: int) -> Any:
    tf.keras.utils.set_random_seed(seed)
    from historical_architecture import AdsorptionAI
    return AdsorptionAI().build_deep_lstm()


def lstm_layers(tf: Any, model: Any) -> list[Any]:
    return [layer for layer in model.layers if isinstance(layer, tf.keras.layers.LSTM)]


def extract_lstm_weights(tf: Any, model: Any) -> list[list[np.ndarray]]:
    """Copy source recurrent weights out of Keras before clear_session()."""
    layers = lstm_layers(tf, model)
    if len(layers) != 2:
        raise BenchmarkError("Historical architecture does not contain exactly two LSTM layers")
    return [[np.array(weight, copy=True) for weight in layer.get_weights()] for layer in layers]


def copy_lstm_weights(tf: Any, source_weights: list[list[np.ndarray]], target: Any) -> None:
    dst_layers = lstm_layers(tf, target)
    if len(source_weights) != 2 or len(dst_layers) != 2:
        raise BenchmarkError("Historical architecture does not contain exactly two LSTM layers")
    for weights, dst in zip(source_weights, dst_layers):
        dst.set_weights([np.array(weight, copy=True) for weight in weights])


def freeze_lstm(tf: Any, model: Any) -> None:
    for layer in lstm_layers(tf, model):
        layer.trainable = False


def inverse_q(scaler_y: Any, y_scaled: np.ndarray) -> np.ndarray:
    return scaler_y.inverse_transform(np.asarray(y_scaled).reshape(-1, 1)).ravel()


def score_predictions(predictions: pd.DataFrame, observations: pd.DataFrame) -> dict[str, float]:
    if predictions.empty or set(predictions["kind"]) != {"measured_endpoint"}:
        raise BenchmarkError("Score function accepts measured_endpoint predictions only")
    truth = observations.set_index("record_id")["q"]
    if not predictions["record_id"].isin(truth.index).all():
        raise BenchmarkError("Prediction contains an ID absent from observations.csv")
    y_true = truth.loc[predictions["record_id"]].to_numpy(dtype=float)
    y_pred = predictions["predicted_q"].to_numpy(dtype=float)
    return {
        "r2": float(__import__("sklearn.metrics", fromlist=["r2_score"]).r2_score(y_true, y_pred)),
        "rmse": float(np.sqrt(__import__("sklearn.metrics", fromlist=["mean_squared_error"]).mean_squared_error(y_true, y_pred))),
        "mae": float(__import__("sklearn.metrics", fromlist=["mean_absolute_error"]).mean_absolute_error(y_true, y_pred)),
    }


def domain_flags(rows: pd.DataFrame, train: pd.DataFrame, prefix: str) -> pd.DataFrame:
    result = pd.DataFrame(index=rows.index)
    for feature in ["pH", "temperature_C", "C0_mg_L", "time_min"]:
        lo, hi = float(train[feature].min()), float(train[feature].max())
        result[f"{prefix}_domain_{feature}_within_train_range"] = rows[feature].astype(float).between(lo, hi).to_numpy()
    return result


def prediction_base(test: pd.DataFrame, predicted: np.ndarray, observations: pd.DataFrame, source_train: pd.DataFrame, target_train: pd.DataFrame, metadata: dict[str, Any]) -> pd.DataFrame:
    out = test[["record_id", "condition_key", "target", "temperature_C", "pH", "C0_mg_L", "time_min", "worksheet_coord"]].copy()
    out["kind"] = "measured_endpoint"
    out["predicted_q"] = np.asarray(predicted, dtype=float)
    out["q_observed"] = out["record_id"].map(observations.set_index("record_id")["q"])
    out["prediction_scale"] = "physical_inverse_q"
    for key, value in metadata.items():
        out[key] = value
    out = pd.concat([out, domain_flags(test, source_train, "source"), domain_flags(test, target_train, "target")], axis=1)
    return out


def simulation_rows(model_predict: Any, target: str, held: int, scaler_x: Any, scaler_y: Any, source_train: pd.DataFrame, target_train: pd.DataFrame, metadata: dict[str, Any], config: dict[str, Any]) -> pd.DataFrame:
    metal, _ = target_parts(target)
    ph = 5.5 if metal == "Al" else 5.0
    c0 = np.linspace(config["simulation_C0_min"], config["simulation_C0_max"], config["simulation_points"])
    grid = pd.DataFrame({"pH": ph, "temperature_C": held, "C0_mg_L": c0, "time_min": 1440.0})
    x = scaler_x.transform(grid[["pH", "temperature_C", "C0_mg_L", "time_min"]]).astype("float32").reshape((-1, 1, 4))
    pred = inverse_q(scaler_y, model_predict(x))
    out = grid.copy()
    out["target"] = target
    out["kind"] = "simulation_grid"
    out["predicted_q"] = pred
    out["prediction_scale"] = "physical_inverse_q"
    for key, value in metadata.items():
        out[key] = value
    out = pd.concat([out, domain_flags(grid, source_train, "source"), domain_flags(grid, target_train, "target")], axis=1)
    # Deliberately no q_true/q_observed column is added to generated rows.
    return out


def save_weights(model: Any, path: Path, save_models: bool) -> None:
    model.save_weights(str(path))
    if save_models:
        model.save(str(path.with_suffix(".keras")), include_optimizer=False)


def save_simulation_grid(simulation: pd.DataFrame, directory: Path, run_id: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    simulation.to_csv(directory / f"{run_id}.csv", index=False, lineterminator="\n")


def save_observed_predictions(predictions: pd.DataFrame, directory: Path, run_id: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(directory / f"{run_id}.csv", index=False, lineterminator="\n")


def metric_row(metadata: dict[str, Any], scores: dict[str, float], ntrain: int, nval: int, ntest: int, epochs_used: int, best_epoch: int, protocol: str) -> dict[str, Any]:
    row = dict(metadata)
    row.update({"protocol": protocol, "r2": scores["r2"], "rmse": scores["rmse"], "mae": scores["mae"], "ntrain": ntrain, "nval": nval, "ntest": ntest, "epochs_used": epochs_used, "best_epoch": best_epoch})
    return row


def run_benchmark(plan: Path, out: Path) -> Path:
    protocol = read_and_verify_plan(plan)
    if out.exists():
        raise BenchmarkError(f"Refusing to overwrite existing results directory: {out}")
    out.mkdir(parents=True)
    for name in ["protocol.json", "protocol.sha256", "dataset.csv", "observations.csv", "dataset_audit.csv", "exclusions.csv", "exclusion_counts.csv", "condition_partition_manifest.csv", "target_fraction_manifest.csv"]:
        shutil.copy2(plan / name, out / name)
    cfg = protocol["config"]
    observations = pd.read_csv(out / "observations.csv")
    partitions = pd.read_csv(out / "condition_partition_manifest.csv")
    fractions = pd.read_csv(out / "target_fraction_manifest.csv")
    for fold_id, held in enumerate(cfg["held_temperatures"]):
        fold = partitions[partitions.fold_id == fold_id]
        if fold.empty:
            raise BenchmarkError(f"Missing frozen partition fold {fold_id}")
        if (fold.loc[fold.partition.isin(["train", "validation"]), "temperature_C"] == held).any():
            raise BenchmarkError(f"Held temperature leaked into train/validation fold {fold_id}")
        if fold.duplicated(["system", "target", "record_id"]).any():
            raise BenchmarkError(f"Duplicate condition ID in frozen partition fold {fold_id}")
    for keys, group in fractions.groupby(["seed", "fold_id", "target", "fraction"], sort=False):
        selected = group[group.selected_for_fit == True]
        if selected["record_id"].duplicated().any():
            raise BenchmarkError(f"Duplicate sampled condition ID in target fraction {keys}")
    tf = configure_tensorflow()
    from sklearn.linear_model import Ridge
    import joblib
    from historical_architecture import AdsorptionAI  # noqa: F401, validates the requested historical module path
    histories = out / "histories"
    weights = out / "weights"
    simulations = out / "simulations"
    prediction_runs = out / "prediction_runs"
    histories.mkdir()
    weights.mkdir()
    simulations.mkdir()
    prediction_runs.mkdir()
    metric_fields = ["seed", "fold_id", "held_temperature_C", "validation_temperature_C", "fraction", "target", "protocol", "r2", "rmse", "mae", "ntrain", "nval", "ntest", "epochs_used", "best_epoch", "q_unit_flag", "evaluation_note"]
    prediction_fields = ["record_id", "condition_key", "target", "temperature_C", "pH", "C0_mg_L", "time_min", "worksheet_coord", "kind", "predicted_q", "q_observed", "prediction_scale", "seed", "fold_id", "held_temperature_C", "validation_temperature_C", "fraction", "protocol", "source_domain_pH_within_train_range", "source_domain_temperature_C_within_train_range", "source_domain_C0_mg_L_within_train_range", "source_domain_time_min_within_train_range", "target_domain_pH_within_train_range", "target_domain_temperature_C_within_train_range", "target_domain_C0_mg_L_within_train_range", "target_domain_time_min_within_train_range"]
    simulation_fields = [x for x in prediction_fields if x not in {"record_id", "condition_key", "worksheet_coord", "q_observed"}]
    metrics_file = AppendCSV(out / "all_metrics.csv", metric_fields)
    preds_file = AppendCSV(out / "observed_predictions.csv", prediction_fields)
    sim_file = AppendCSV(out / "simulation_predictions.csv", simulation_fields)
    source_metrics_file = AppendCSV(out / "source_metrics.csv", metric_fields)
    source_preds_file = AppendCSV(out / "source_observed_predictions.csv", prediction_fields)
    source_results: list[dict[str, Any]] = []
    try:
        source_partitions = partitions[(partitions.system == "source") & (partitions.target == SOURCE_TARGET)]
        for seed in cfg["seeds"]:
            for fold_id, held in enumerate(cfg["held_temperatures"]):
                part = source_partitions[source_partitions.fold_id == fold_id]
                source_train = observations[observations.record_id.isin(part[part.partition == "train"].record_id)]
                source_val = observations[observations.record_id.isin(part[part.partition == "validation"].record_id)]
                source_test = observations[observations.record_id.isin(part[part.partition == "test"].record_id)]
                scaler_x, scaler_y = __import__("sklearn.preprocessing", fromlist=["MinMaxScaler"]).MinMaxScaler(), __import__("sklearn.preprocessing", fromlist=["MinMaxScaler"]).MinMaxScaler()
                x_train, y_train = prepare_training_frame(source_train, scaler_x, scaler_y, fit=True)
                x_val, y_val = prepare_training_frame(source_val, scaler_x, scaler_y)
                x_test, _ = prepare_training_frame(source_test, scaler_x, scaler_y)
                tf.keras.backend.clear_session()
                source_model = fresh_historical_model(tf, stable_int(seed, fold_id, "source"))
                source_model, source_history = fit_model(tf, source_model, x_train, y_train, x_val, y_val, cfg, stable_int(seed, fold_id, "source_fit"))
                source_pred = inverse_q(scaler_y, source_model.predict(x_test, verbose=0))
                source_pred_df = pd.DataFrame({"record_id": source_test["record_id"].tolist(), "predicted_q": source_pred, "kind": "measured_endpoint"})
                source_scores = score_predictions(source_pred_df, observations)
                source_meta = {"seed": seed, "fold_id": fold_id, "held_temperature_C": held, "validation_temperature_C": split_temperatures(held)[1], "fraction": 1.0, "target": SOURCE_TARGET, "q_unit_flag": "stored_response_unit_unconfirmed", "evaluation_note": "source_test_separate_from_target_metrics"}
                source_metrics_file.append(metric_row(source_meta, source_scores, len(source_train), len(source_val), len(source_test), len(source_history.get("loss", [])), int(np.argmin(source_history.get("val_loss", [np.inf]))) + 1, "source_model"))
                src_rows = prediction_base(source_test, source_pred, observations, source_train, source_train, {**source_meta, "protocol": "source_model"})
                save_observed_predictions(src_rows, prediction_runs, f"source_seed{seed}_fold{fold_id}")
                for row in src_rows.to_dict("records"):
                    source_preds_file.append(row)
                source_results.append(source_meta | source_scores)
                np.savez(weights / f"source_weights_seed{seed}_fold{fold_id}.npz", **{f"w{i}": w for i, w in enumerate(source_model.get_weights())})
                joblib.dump({"scaler_X": scaler_x, "scaler_y": scaler_y}, weights / f"source_scalers_seed{seed}_fold{fold_id}.joblib")
                json_dump(histories / f"source_seed{seed}_fold{fold_id}.json", source_history)
                target_source_weights = extract_lstm_weights(tf, source_model)
                print(f"[source] seed={seed} held_T={held} ntrain={len(source_train)} epochs={len(source_history.get('loss', []))}", flush=True)
                for target in cfg["targets"]:
                    target_part = partitions[(partitions.system == "target") & (partitions.target == target) & (partitions.fold_id == fold_id)]
                    for fraction in cfg["fractions"]:
                        fm = fractions[(fractions.seed == seed) & (fractions.fold_id == fold_id) & (fractions.target == target) & (fractions.fraction == float(fraction))]
                        train_ids = fm[fm.selected_for_fit == True].record_id.tolist()
                        val_ids = target_part[target_part.partition == "validation"].record_id.tolist()
                        test_ids = target_part[target_part.partition == "test"].record_id.tolist()
                        target_train = observations[observations.record_id.isin(train_ids)]
                        target_val = observations[observations.record_id.isin(val_ids)]
                        target_test = observations[observations.record_id.isin(test_ids)]
                        if len(target_train) != len(train_ids) or len(target_test) == 0:
                            raise BenchmarkError("Target fraction or test manifest mismatch")
                        xtr, ytr = prepare_training_frame(target_train, scaler_x, scaler_y)
                        xv, yv = prepare_training_frame(target_val, scaler_x, scaler_y)
                        xt, _ = prepare_training_frame(target_test, scaler_x, scaler_y)
                        meta = {"seed": seed, "fold_id": fold_id, "held_temperature_C": held, "validation_temperature_C": split_temperatures(held)[1], "fraction": fraction, "target": target, "q_unit_flag": "stored_response_unit_unconfirmed", "evaluation_note": "endpoint_cv_test_only"}
                        models: dict[str, Any] = {}
                        histories_for_run: dict[str, dict[str, list[float]]] = {}
                        for proto in PROTOCOLS:
                            tf.keras.backend.clear_session()
                            if proto in {"Ridge", "mean_baseline"}:
                                xtr_flat = scaler_x.transform(target_train[["pH", "temperature_C", "C0_mg_L", "time_min"]].astype(float))
                                xt_flat = scaler_x.transform(target_test[["pH", "temperature_C", "C0_mg_L", "time_min"]].astype(float))
                                if proto == "Ridge":
                                    estimator = Ridge(alpha=1.0).fit(xtr_flat, target_train["q"].astype(float))
                                    pred = estimator.predict(xt_flat)
                                else:
                                    pred = np.repeat(float(target_train["q"].mean()), len(target_test))
                                pred_df = pd.DataFrame({"record_id": target_test["record_id"].tolist(), "predicted_q": pred, "kind": "measured_endpoint"})
                                scores = score_predictions(pred_df, observations)
                                metric = metric_row(meta, scores, len(target_train), len(target_val), len(target_test), 0, 0, proto)
                                metrics_file.append(metric)
                                pred_rows = prediction_base(target_test, pred, observations, source_train, target_train, {**meta, "protocol": proto})
                                run_id = f"seed{seed}_fold{fold_id}_frac{fraction:g}_{target.replace(':', '_').replace('-', '_')}_{proto}"
                                save_observed_predictions(pred_rows, prediction_runs, run_id)
                                for row in pred_rows.to_dict("records"):
                                    preds_file.append(row)
                                if cfg["simulations_enabled"]:
                                    sim = simulation_rows(lambda x, est=estimator if proto == "Ridge" else None: scaler_y.transform(est.predict(x.reshape(-1, 4)).reshape(-1, 1)).ravel() if est is not None else np.repeat(scaler_y.transform([[target_train["q"].mean()]])[0, 0], len(x)), target, held, scaler_x, scaler_y, source_train, target_train, {**meta, "protocol": proto}, cfg)
                                    save_simulation_grid(sim, simulations, run_id)
                                    for row in sim.to_dict("records"):
                                        sim_file.append(row)
                                print(f"[done] seed={seed} held_T={held} target={target} fraction={fraction:g} protocol={proto}", flush=True)
                                continue
                            model_seed = stable_int(seed, fold_id, target, fraction, "fresh_neural_init")
                            model = fresh_historical_model(tf, model_seed)
                            if proto == "random_frozen":
                                freeze_lstm(tf, model)
                            elif proto in {"TL_frozen", "TL_finetune"}:
                                copy_lstm_weights(tf, target_source_weights, model)
                                if proto == "TL_frozen":
                                    freeze_lstm(tf, model)
                            frozen_before = extract_lstm_weights(tf, model) if proto in {"TL_frozen", "random_frozen"} else None
                            model, hist = fit_model(tf, model, xtr, ytr, xv, yv, cfg, stable_int(seed, fold_id, target, fraction, "fit"))
                            if frozen_before is not None:
                                for before_layer, after_layer in zip(frozen_before, extract_lstm_weights(tf, model)):
                                    for before, after in zip(before_layer, after_layer):
                                        np.testing.assert_array_equal(before, after)
                            histories_for_run[proto] = hist
                            pred = inverse_q(scaler_y, model.predict(xt, verbose=0))
                            pred_df = pd.DataFrame({"record_id": target_test["record_id"].tolist(), "predicted_q": pred, "kind": "measured_endpoint"})
                            scores = score_predictions(pred_df, observations)
                            best_epoch = int(np.argmin(hist.get("val_loss", [np.inf]))) + 1
                            metrics_file.append(metric_row(meta, scores, len(target_train), len(target_val), len(target_test), len(hist.get("loss", [])), best_epoch, proto))
                            pred_rows = prediction_base(target_test, pred, observations, source_train, target_train, {**meta, "protocol": proto})
                            run_id = f"seed{seed}_fold{fold_id}_frac{fraction:g}_{target.replace(':', '_').replace('-', '_')}_{proto}"
                            save_observed_predictions(pred_rows, prediction_runs, run_id)
                            for row in pred_rows.to_dict("records"):
                                preds_file.append(row)
                            save_weights(model, weights / f"{run_id}.weights.h5", bool(cfg.get("save_models", False)))
                            json_dump(histories / f"{run_id}.json", hist)
                            if cfg["simulations_enabled"]:
                                sim = simulation_rows(lambda x, m=model: m.predict(x, verbose=0), target, held, scaler_x, scaler_y, source_train, target_train, {**meta, "protocol": proto}, cfg)
                                save_simulation_grid(sim, simulations, run_id)
                                for row in sim.to_dict("records"):
                                    sim_file.append(row)
                            print(f"[done] seed={seed} held_T={held} target={target} fraction={fraction:g} protocol={proto}", flush=True)
                        # Baseline histories are intentionally absent; they have no epochs or early stopping.
    finally:
        metrics_file.close(); preds_file.close(); sim_file.close(); source_metrics_file.close(); source_preds_file.close()
    summarize_results(out)
    return out


def summarize_results(results: Path) -> None:
    metrics = pd.read_csv(results / "all_metrics.csv")
    preds = pd.read_csv(results / "observed_predictions.csv")
    if metrics.empty:
        raise BenchmarkError("No metrics to summarize")
    uniqueness = preds.groupby(["seed", "target", "fraction", "protocol"]) ["record_id"].nunique()
    row_counts = preds.groupby(["seed", "target", "fraction", "protocol"]).size()
    if not uniqueness.equals(row_counts):
        raise BenchmarkError("Duplicate measured condition IDs found within a seed/target/fraction/protocol")
    group_cols = ["target", "fraction", "protocol", "held_temperature_C"]
    fold = metrics.groupby(group_cols, dropna=False).agg(
        r2_mean=("r2", "mean"), r2_sd=("r2", "std"), rmse_mean=("rmse", "mean"), rmse_sd=("rmse", "std"),
        mae_mean=("mae", "mean"), mae_sd=("mae", "std"), seed_count=("seed", "nunique"),
    ).reset_index()
    fold.to_csv(results / "fold_mean_sd.csv", index=False, lineterminator="\n")
    pooled_rows = []
    for keys, group in preds.groupby(["seed", "target", "fraction", "protocol"], dropna=False):
        score = score_predictions(group[["record_id", "predicted_q", "kind"]], pd.read_csv(results / "observations.csv"))
        pooled_rows.append({"seed": keys[0], "target": keys[1], "fraction": keys[2], "protocol": keys[3], **score, "n_predictions": len(group), "aggregation_note": "pooled_OOF_across_folds_CV_not_one_fit"})
    pd.DataFrame(pooled_rows).to_csv(results / "pooled_oof_metrics.csv", index=False, lineterminator="\n")
    comparison_rows = []
    index_cols = ["seed", "fold_id", "held_temperature_C", "fraction", "target"]
    comparisons = [(control, tl, f"{control}_minus_{tl}") for control in ["FS", "random_frozen", "Ridge"] for tl in ["TL_frozen", "TL_finetune"]]
    for left, right, label in comparisons:
        a = metrics[metrics.protocol == left].set_index(index_cols)
        b = metrics[metrics.protocol == right].set_index(index_cols)
        common = a.index.intersection(b.index)
        for idx in common:
            comparison_rows.append({**dict(zip(index_cols, idx)), "comparison": label, "delta_r2_TL_minus_control": b.loc[idx, "r2"] - a.loc[idx, "r2"], "delta_rmse": a.loc[idx, "rmse"] - b.loc[idx, "rmse"], "delta_mae": a.loc[idx, "mae"] - b.loc[idx, "mae"], "positive_delta_rmse_favors_TL": True})
    pd.DataFrame(comparison_rows).to_csv(results / "paired_comparisons.csv", index=False, lineterminator="\n")
    pooled = pd.DataFrame(pooled_rows)
    pooled.groupby(["target", "fraction", "protocol"]).agg(
        r2_mean=("r2", "mean"), r2_sd=("r2", "std"),
        rmse_mean=("rmse", "mean"), rmse_sd=("rmse", "std"),
        mae_mean=("mae", "mean"), mae_sd=("mae", "std"),
        seed_count=("seed", "nunique"), n_predictions=("n_predictions", "first"),
    ).reset_index().to_csv(results / "pooled_oof_mean_sd.csv", index=False)
    source = pd.read_csv(results / "source_metrics.csv")
    source.to_csv(results / "source_fold_performance.csv", index=False, lineterminator="\n")
    notes = {
        "warnings": ["stored_response_unit_unconfirmed", "reported_blank_correction_is_unverified_or_unavailable", "means_and_sds_are_computational_not_experimental", "source_performance_is_separate_from_target_metrics"],
        "comparison_interpretation": "FS_minus_TL and random_frozen_minus_TL RMSE: positive favors TL; no p-values or confidence claims are computed.",
        "test_selection": "No seed, held temperature, or protocol was selected by test performance.",
    }
    json_dump(results / "summary_notes.json", notes)


def summarize_command(results: Path) -> None:
    if not results.exists():
        raise BenchmarkError(f"Results directory not found: {results}")
    summarize_results(results)
    pooled = pd.read_csv(results / "pooled_oof_metrics.csv")
    print(pooled.to_string(index=False))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="extract immutable endpoint data and precompute manifests")
    plan.add_argument("--workbook", required=True, help="path to an authorized workbook; never committed by this repository")
    plan.add_argument("--out", required=True)
    plan.add_argument("--seeds", nargs="+", type=int, default=list(range(10)))
    plan.add_argument("--fractions", nargs="+", type=float, default=[0.1, 0.2, 0.4, 0.6, 0.8, 1.0])
    plan.add_argument("--held-temperatures", nargs="+", type=int, default=[30, 40, 50, 60])
    plan.add_argument("--targets", nargs="+", default=TARGETS_DEFAULT)
    plan.add_argument("--epochs", type=int, default=100)
    plan.add_argument("--patience", type=int, default=15)
    plan.add_argument("--batch-size", type=int, default=8)
    plan.add_argument("--learning-rate", type=float, default=0.001)
    plan.add_argument("--no-simulations", action="store_true")
    plan.add_argument("--blank-status", choices=["unavailable", "reported_corrected"], default="unavailable")
    plan.add_argument("--save-models", action="store_true")
    run = sub.add_parser("run", help="run the frozen benchmark; no configuration overrides")
    run.add_argument("--plan", required=True)
    run.add_argument("--out", required=True)
    summary = sub.add_parser("summarize", help="recompute summaries from a completed result directory")
    summary.add_argument("--results", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            print(f"Created immutable plan: {create_plan(args)}")
        elif args.command == "run":
            print(f"Completed benchmark: {run_benchmark(Path(args.plan).resolve(), Path(args.out).resolve())}")
        else:
            summarize_command(Path(args.results).resolve())
        return 0
    except (BenchmarkError, OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
