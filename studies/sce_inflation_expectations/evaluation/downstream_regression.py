import numpy as np
import pandas as pd


OUTCOMES = {
    "wage_growth_overall": {"kind": "percent", "label": "Atlanta Fed wage growth"},
    "PCEDGC96": {"kind": "log_level", "label": "Real durable-goods consumption"},
    "REVOLSL": {"kind": "log_level", "label": "Revolving consumer credit"},
    "MICH": {"kind": "percent", "label": "Michigan one-year inflation expectations"},
}

MODELS = [
    "persistence",
    "expanding_mean",
    "ar1",
    "domain_arx",
    "official_sce",
    "simulated_sce",
    "blended_sce",
    "official_plus_simulated",
]

CONTRASTS = [
    ("persistence", "expanding_mean"),
    ("persistence", "ar1"),
    ("persistence", "domain_arx"),
    ("persistence", "official_sce"),
    ("persistence", "simulated_sce"),
    ("persistence", "blended_sce"),
    ("ar1", "domain_arx"),
    ("ar1", "official_sce"),
    ("ar1", "simulated_sce"),
    ("ar1", "blended_sce"),
    ("domain_arx", "official_sce"),
    ("domain_arx", "simulated_sce"),
    ("domain_arx", "blended_sce"),
    ("domain_arx", "official_plus_simulated"),
    ("official_sce", "simulated_sce"),
    ("official_sce", "blended_sce"),
    ("official_sce", "official_plus_simulated"),
]


def load_merged_inputs(panel_path, a_path, b_path):
    panel = pd.read_csv(panel_path)
    panel["date"] = pd.to_datetime(panel["date"])
    if panel["date"].duplicated().any():
        raise ValueError("Monthly panel contains duplicate dates")
    a = pd.read_csv(a_path, dtype={"month": str}).rename(columns={
        "truth_pp": "official_sce",
        "CoreNormal_tau8_pure": "simulated_sce",
        "CoreNormal_tau8_blend_mse": "blended_sce",
    })
    b = pd.read_csv(b_path, dtype={"month": str}).rename(columns={
        "truth_pp": "official_sce",
        "expanded_pp": "simulated_sce",
        "expanded_blend_pp": "blended_sce",
    })
    sce = []
    for frame, scope in [(a, "A"), (b, "B")]:
        required = {"month", "official_sce", "simulated_sce", "blended_sce"}
        if not required.issubset(frame.columns):
            raise ValueError(f"Missing {scope} SCE columns: {sorted(required - set(frame.columns))}")
        selected = frame[["month", "official_sce", "simulated_sce", "blended_sce"]].copy()
        selected["date"] = pd.to_datetime(selected["month"], format="%Y%m")
        selected["scope"] = scope
        sce.append(selected.drop(columns="month"))
    merged = panel.merge(pd.concat(sce, ignore_index=True), on="date", how="left", validate="one_to_one")
    return merged.sort_values("date").reset_index(drop=True)


def feature_columns(outcome, model):
    if outcome not in OUTCOMES:
        raise ValueError(f"Unknown outcome: {outcome}")
    base = ["current_transformed", "outcome_delta", "UNRATE", "CPI_YOY", "UMCSENT", "FEDFUNDS"]
    if outcome == "wage_growth_overall":
        base.append("JTSJOL")
    elif outcome in {"PCEDGC96", "REVOLSL"}:
        base.append("REAL_INCOME_GROWTH")
    elif outcome == "MICH":
        base.append("CORE_CPI_YOY")
    additions = {
        "domain_arx": [],
        "official_sce": ["official_sce", "official_sce_delta"],
        "simulated_sce": ["simulated_sce", "simulated_sce_delta"],
        "blended_sce": ["blended_sce", "blended_sce_delta"],
        "official_plus_simulated": [
            "official_sce", "official_sce_delta", "simulated_sce", "simulated_sce_delta"
        ],
    }
    if model not in additions:
        raise ValueError(f"Model has no regression feature set: {model}")
    return base + additions[model]


def build_analysis_frame(merged, outcome, horizon):
    if horizon not in {1, 2, 3}:
        raise ValueError("The ConsumerSim-style first stage uses horizons 1, 2 and 3 only")
    kind = OUTCOMES[outcome]["kind"]
    frame = merged.sort_values("date").reset_index(drop=True).copy()
    frame["date"] = pd.to_datetime(frame["date"])
    if kind == "log_level":
        if (frame[outcome].dropna() <= 0).any():
            raise ValueError(f"Log-growth outcome must be positive: {outcome}")
        frame["current_transformed"] = np.log(frame[outcome])
    else:
        frame["current_transformed"] = frame[outcome]
    frame["outcome_delta"] = frame["current_transformed"].diff()
    frame["target_date"] = frame["date"].shift(-horizon)
    frame["target"] = frame["current_transformed"].shift(-horizon) - frame["current_transformed"]
    frame["CPI_YOY"] = 100 * (frame["CPIAUCSL"] / frame["CPIAUCSL"].shift(12) - 1)
    frame["CORE_CPI_YOY"] = 100 * (frame["CPILFESL"] / frame["CPILFESL"].shift(12) - 1)
    frame["REAL_INCOME_GROWTH"] = 100 * (frame["DSPIC96"] / frame["DSPIC96"].shift(1) - 1)
    for name in ["official_sce", "simulated_sce", "blended_sce"]:
        frame[f"{name}_delta"] = frame[name].diff()
    required = {"date", "target_date", "target", "current_transformed", "scope"}
    required.update(feature_columns(outcome, "official_plus_simulated"))
    required.update(feature_columns(outcome, "blended_sce"))
    result = frame.dropna(subset=sorted(required)).reset_index(drop=True)
    result.attrs["outcome"] = outcome
    result.attrs["horizon"] = horizon
    return result


def fit_ols(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    if len(x) != len(y) or len(y) == 0:
        raise ValueError("OLS needs equally sized, non-empty X and y")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("OLS inputs must be finite")
    center = x.mean(axis=0)
    scale = x.std(axis=0)
    if np.any(scale <= 0):
        raise ValueError("OLS features must vary in the training sample")
    z = (x - center) / scale
    design = np.column_stack([np.ones(len(z)), z])
    coefficients = np.linalg.lstsq(design, y, rcond=None)[0]
    return {"center": center, "scale": scale, "coefficients": coefficients}


def predict_ols(fit, x):
    x = np.asarray(x, dtype=float)
    if x.ndim == 1:
        x = x.reshape(-1, 1)
    z = (x - fit["center"]) / fit["scale"]
    design = np.column_stack([np.ones(len(z)), z])
    return design @ fit["coefficients"]


def r_squared(y, prediction):
    y = np.asarray(y, dtype=float)
    prediction = np.asarray(prediction, dtype=float)
    denominator = np.sum((y - y.mean()) ** 2)
    if denominator <= 0:
        return np.nan
    return 1 - np.sum((y - prediction) ** 2) / denominator


def training_rows(frame, origin):
    return frame[(frame["target_date"] <= origin) & (frame["date"] < origin)]


def _fit_predict(model, train, test, outcome):
    if model == "persistence":
        return np.zeros(len(test)), None
    if model == "expanding_mean":
        return np.full(len(test), train["target"].mean()), None
    if model == "ar1":
        fit = fit_ols(train[["current_transformed"]], train["current_transformed"] + train["target"])
        future = predict_ols(fit, test[["current_transformed"]])
        return future - test["current_transformed"].to_numpy(), fit
    columns = feature_columns(outcome, model)
    fit = fit_ols(train[columns], train["target"])
    return predict_ols(fit, test[columns]), fit


def _metrics(rows):
    error = rows["prediction"] - rows["actual"]
    return {
        "n": int(len(rows)),
        "mae": float(error.abs().mean()),
        "rmse": float(np.sqrt(np.mean(error ** 2))),
        "bias": float(error.mean()),
    }


def evaluate_a_b(frame, min_train=36):
    outcome = frame.attrs["outcome"]
    horizon = frame.attrs["horizon"]
    prediction_records = []
    in_sample_records = []
    a = frame[frame["scope"] == "A"]
    b = frame[frame["scope"] == "B"]
    for model in MODELS:
        for origin in sorted(a["date"].unique()):
            test = a[a["date"] == origin]
            train = training_rows(a, origin)
            if len(train) < min_train:
                continue
            prediction, _ = _fit_predict(model, train, test, outcome)
            for position, (_, row) in enumerate(test.iterrows()):
                prediction_records.append({
                    "outcome": outcome,
                    "horizon": horizon,
                    "scope": "A",
                    "evaluation": "A_expanding",
                    "date": row["date"],
                    "target_date": row["target_date"],
                    "model": model,
                    "n_train": len(train),
                    "prediction": prediction[position],
                    "actual": row["target"],
                })
        if not b.empty:
            first_b = b["date"].min()
            train = training_rows(a, first_b)
            if len(train) < min_train:
                raise ValueError(f"Insufficient frozen-A training rows for B transfer: {len(train)}")
            prediction, _ = _fit_predict(model, train, b, outcome)
            for position, (_, row) in enumerate(b.iterrows()):
                prediction_records.append({
                    "outcome": outcome,
                    "horizon": horizon,
                    "scope": "B",
                    "evaluation": "B_frozen_A",
                    "date": row["date"],
                    "target_date": row["target_date"],
                    "model": model,
                    "n_train": len(train),
                    "prediction": prediction[position],
                    "actual": row["target"],
                })
        if model == "persistence":
            fitted = np.zeros(len(a))
        elif model == "expanding_mean":
            fitted = np.full(len(a), a["target"].mean())
        else:
            fitted, _ = _fit_predict(model, a, a, outcome)
        in_sample_records.append({
            "outcome": outcome,
            "horizon": horizon,
            "model": model,
            "n": len(a),
            **_metrics(pd.DataFrame({"prediction": fitted, "actual": a["target"].to_numpy()})),
            "r2": r_squared(a["target"], fitted),
        })
    predictions = pd.DataFrame(prediction_records)
    predictions["error"] = predictions["prediction"] - predictions["actual"]
    summary_rows = []
    keys = ["outcome", "horizon", "scope", "evaluation", "model"]
    for values, rows in predictions.groupby(keys, sort=True):
        summary_rows.append({
            **dict(zip(keys, values)),
            **_metrics(rows),
            "n_train_min": int(rows["n_train"].min()),
            "n_train_max": int(rows["n_train"].max()),
        })
    return predictions, pd.DataFrame(summary_rows), pd.DataFrame(in_sample_records)


def contrast_metrics(summary, in_sample):
    records = []
    group_columns = ["outcome", "horizon", "scope"]
    if "evaluation" in summary.columns:
        group_columns.append("evaluation")
    indexed = summary.set_index(group_columns + ["model"])
    in_sample_indexed = in_sample.set_index(["outcome", "horizon", "model"])
    for reference, candidate in CONTRASTS:
        for key, rows in summary.groupby(group_columns, sort=True):
            key = key if isinstance(key, tuple) else (key,)
            reference_key = (*key, reference)
            candidate_key = (*key, candidate)
            if reference_key not in indexed.index or candidate_key not in indexed.index:
                continue
            reference_row = indexed.loc[reference_key]
            candidate_row = indexed.loc[candidate_key]
            in_sample_key = (key[0], key[1])
            ref_r2 = in_sample_indexed.loc[(*in_sample_key, reference), "r2"]
            cand_r2 = in_sample_indexed.loc[(*in_sample_key, candidate), "r2"]
            records.append({
                **dict(zip(group_columns, key)),
                "reference": reference,
                "candidate": candidate,
                "n": int(candidate_row["n"]),
                "reference_rmse": reference_row["rmse"],
                "candidate_rmse": candidate_row["rmse"],
                "rmse_improvement": (reference_row["rmse"] - candidate_row["rmse"]) / reference_row["rmse"],
                "reference_mae": reference_row["mae"],
                "candidate_mae": candidate_row["mae"],
                "mae_improvement": (reference_row["mae"] - candidate_row["mae"]) / reference_row["mae"],
                "reference_r2": ref_r2,
                "candidate_r2": cand_r2,
                "delta_r2": cand_r2 - ref_r2,
            })
    return pd.DataFrame(records)
