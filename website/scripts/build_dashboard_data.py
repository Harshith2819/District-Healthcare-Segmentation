"""Build the browser data bundle from the project's verified analysis outputs.

This does not edit the notebook or source results. It creates website/static/data/dashboard.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, StandardScaler


WEBSITE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = WEBSITE_ROOT.parent
ANALYSIS_OUTPUTS = PROJECT_ROOT / "enhancements" / "outputs"
OUTPUT = WEBSITE_ROOT / "static" / "data" / "dashboard.json"
IDENTIFIERS = ["state_code", "state", "district"]


def short_label(label: str) -> str:
    text = label.split(". ", 1)[-1].replace(" (%)", "")
    return text if len(text) <= 58 else text[:55].rstrip() + "…"


def num(value: float) -> float:
    return round(float(value), 3)


def records(frame: pd.DataFrame) -> list[dict]:
    """Serialize NaN as JSON null instead of JavaScript-invalid NaN."""
    return json.loads(frame.to_json(orient="records"))


def main() -> None:
    cleaned = pd.read_csv(PROJECT_ROOT / "district_features_cleaned.csv")
    baseline = pd.read_csv(PROJECT_ROOT / "final_district_healthcare_clusters.csv")[IDENTIFIERS + ["Cluster"]]
    data = cleaned.merge(baseline, on=IDENTIFIERS, validate="one_to_one")
    feature_columns = [column for column in cleaned.columns if column not in IDENTIFIERS]
    values = data[feature_columns].astype(float)
    data["coverage_score"] = MinMaxScaler().fit_transform(values).mean(axis=1) * 100
    data["cluster_label"] = data["Cluster"].map({0: "Higher coverage", 1: "Lower coverage"})

    profiles = data.groupby("Cluster", observed=True)[feature_columns].mean()
    gaps = pd.DataFrame(
        {
            "indicator": feature_columns,
            "higher_coverage_mean": profiles.loc[0, feature_columns].to_numpy(),
            "lower_coverage_mean": profiles.loc[1, feature_columns].to_numpy(),
        }
    )
    gaps["gap"] = gaps["higher_coverage_mean"] - gaps["lower_coverage_mean"]
    gaps["absolute_gap"] = gaps["gap"].abs()
    gaps = gaps.sort_values("absolute_gap", ascending=False).reset_index(drop=True)

    state_summary = data.groupby("state", observed=True).agg(
        districts=("district", "size"),
        higher_coverage=("Cluster", lambda series: int((series == 0).sum())),
        lower_coverage=("Cluster", lambda series: int((series == 1).sum())),
        mean_score=("coverage_score", "mean"),
    ).reset_index()
    state_summary["lower_coverage_share"] = 100 * state_summary["lower_coverage"] / state_summary["districts"]
    state_summary = state_summary.sort_values("lower_coverage_share", ascending=False)
    scaled = StandardScaler().fit_transform(values)

    feature_metadata = [
        {
            "index": index,
            "label": column,
            "short_label": short_label(column),
            "min": num(values[column].min()),
            "max": num(values[column].max()),
            "mean": num(values[column].mean()),
            "missing": int(values[column].isna().sum()),
            "scaled_mean": num(scaled[:, index].mean()),
            "scaled_std": num(scaled[:, index].std()),
        }
        for index, column in enumerate(feature_columns)
    ]
    districts = [
        {
            "id": f"{row['state_code']}|{row['district']}",
            "state": row["state"],
            "state_code": row["state_code"],
            "district": row["district"],
            "cluster": int(row["Cluster"]),
            "cluster_label": row["cluster_label"],
            "coverage_score": num(row["coverage_score"]),
            "values": [num(row[column]) for column in feature_columns],
        }
        for _, row in data.iterrows()
    ]
    cluster_profiles = [
        {
            "cluster": cluster,
            "label": "Higher coverage" if cluster == 0 else "Lower coverage",
            "mean_score": num(data.loc[data.Cluster == cluster, "coverage_score"].mean()),
            "values": [num(value) for value in profiles.loc[cluster, feature_columns]],
        }
        for cluster in (0, 1)
    ]
    top_state, top_gap = state_summary.iloc[0], gaps.iloc[0]
    payload = {
        "meta": {
            "district_count": len(data),
            "feature_count": len(feature_columns),
            "score_method": "Unweighted mean of min–max rescaled 15 indicators (0–100). This is an analytical score, not an official health index.",
        },
        "features": feature_metadata,
        "districts": districts,
        "cluster_profiles": cluster_profiles,
        "gaps": [
            {
                "indicator": row.indicator,
                "short_label": short_label(row.indicator),
                "higher_coverage_mean": num(row.higher_coverage_mean),
                "lower_coverage_mean": num(row.lower_coverage_mean),
                "gap": num(row.gap),
                "absolute_gap": num(row.absolute_gap),
            }
            for row in gaps.itertuples(index=False)
        ],
        "states": [
            {
                "state": row.state,
                "districts": int(row.districts),
                "higher_coverage": int(row.higher_coverage),
                "lower_coverage": int(row.lower_coverage),
                "lower_coverage_share": num(row.lower_coverage_share),
                "mean_score": num(row.mean_score),
            }
            for row in state_summary.itertuples(index=False)
        ],
        "quality": {
            "cleaned_missing_values": int(values.isna().sum().sum()),
            "imputation_note": "The existing notebook documents median imputation for missing childhood-vaccination values before exporting this cleaned table.",
        },
        "algorithms": records(pd.read_csv(ANALYSIS_OUTPUTS / "selected_configurations.csv")),
        "subsample_stability": records(pd.read_csv(ANALYSIS_OUTPUTS / "stability_summary.csv")),
        "seed_stability": records(pd.read_csv(ANALYSIS_OUTPUTS / "kmeans_random_seed_stability_summary.csv")),
        "insights": [
            f"{top_state.state} has the largest share of lower-coverage baseline districts: {top_state.lower_coverage_share:.1f}% ({int(top_state.lower_coverage)} of {int(top_state.districts)}).",
            f"The largest baseline cluster gap is {short_label(top_gap.indicator)} at {top_gap.absolute_gap:.1f} percentage points.",
            f"The retained baseline is 236 higher-coverage and 105 lower-coverage districts.",
        ],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(districts)} districts and {len(feature_columns)} indicators.")


if __name__ == "__main__":
    main()
