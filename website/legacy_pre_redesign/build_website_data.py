"""Create a browser-friendly data bundle from the project's real analysis outputs."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
OUTPUTS = ROOT / "enhancements" / "outputs"
WEB_DATA = ROOT / "enhancements" / "webapp" / "static" / "data" / "healthcare_dashboard_data.json"
ID_COLUMNS = ["state_code", "state", "district"]


def number(value: float) -> float:
    return round(float(value), 3)


def short_label(label: str) -> str:
    text = label.split(". ", 1)[-1].replace(" (%)", "")
    return text if len(text) <= 58 else text[:55].rstrip() + "…"


def json_records(frame: pd.DataFrame) -> list[dict]:
    """Use pandas' JSON encoder so numeric NaN becomes the JSON value null."""
    return json.loads(frame.to_json(orient="records"))


def main() -> None:
    features = pd.read_csv(ROOT / "district_features_cleaned.csv")
    baseline = pd.read_csv(ROOT / "final_district_healthcare_clusters.csv")[ID_COLUMNS + ["Cluster"]]
    data = features.merge(baseline, on=ID_COLUMNS, validate="one_to_one")
    feature_columns = [column for column in features.columns if column not in ID_COLUMNS]
    values = data[feature_columns].astype(float)
    score = MinMaxScaler().fit_transform(values).mean(axis=1) * 100
    data["coverage_score"] = score
    data["cluster_label"] = data["Cluster"].map({0: "Higher coverage", 1: "Lower coverage"})

    cluster_profiles = data.groupby("Cluster", observed=True)[feature_columns].mean()
    gaps = pd.DataFrame(
        {
            "indicator": feature_columns,
            "higher_coverage_mean": cluster_profiles.loc[0, feature_columns].to_numpy(),
            "lower_coverage_mean": cluster_profiles.loc[1, feature_columns].to_numpy(),
        }
    )
    gaps["gap"] = gaps["higher_coverage_mean"] - gaps["lower_coverage_mean"]
    gaps["absolute_gap"] = gaps["gap"].abs()
    gaps = gaps.sort_values("absolute_gap", ascending=False).reset_index(drop=True)

    state_summary = (
        data.groupby("state", observed=True)
        .agg(
            districts=("district", "size"),
            higher_coverage=("Cluster", lambda labels: int((labels == 0).sum())),
            lower_coverage=("Cluster", lambda labels: int((labels == 1).sum())),
            mean_score=("coverage_score", "mean"),
        )
        .reset_index()
    )
    state_summary["lower_coverage_share"] = state_summary["lower_coverage"] / state_summary["districts"] * 100
    state_summary = state_summary.sort_values("lower_coverage_share", ascending=False)

    algorithms = pd.read_csv(OUTPUTS / "selected_configurations.csv")
    stability = pd.read_csv(OUTPUTS / "stability_summary.csv")
    seed_stability = pd.read_csv(OUTPUTS / "kmeans_random_seed_stability_summary.csv")
    scaled = StandardScaler().fit_transform(values)

    feature_metadata = [
        {
            "index": index,
            "label": column,
            "short_label": short_label(column),
            "min": number(values[column].min()),
            "max": number(values[column].max()),
            "mean": number(values[column].mean()),
            "missing": int(values[column].isna().sum()),
            "scaled_mean": number(scaled[:, index].mean()),
            "scaled_std": number(scaled[:, index].std()),
        }
        for index, column in enumerate(feature_columns)
    ]
    district_records = [
        {
            "id": f"{row.state_code}|{row.district}",
            "state_code": row.state_code,
            "state": row.state,
            "district": row.district,
            "cluster": int(row.Cluster),
            "cluster_label": row.cluster_label,
            "coverage_score": number(row.coverage_score),
            "values": [number(row[column]) for column in feature_columns],
        }
        for _, row in data.iterrows()
    ]
    profiles = [
        {
            "cluster": int(cluster),
            "label": "Higher coverage" if cluster == 0 else "Lower coverage",
            "mean_score": number(data.loc[data.Cluster == cluster, "coverage_score"].mean()),
            "values": [number(value) for value in cluster_profiles.loc[cluster, feature_columns]],
        }
        for cluster in (0, 1)
    ]
    gap_records = [
        {
            "indicator": row.indicator,
            "short_label": short_label(row.indicator),
            "higher_coverage_mean": number(row.higher_coverage_mean),
            "lower_coverage_mean": number(row.lower_coverage_mean),
            "gap": number(row.gap),
            "absolute_gap": number(row.absolute_gap),
        }
        for row in gaps.itertuples(index=False)
    ]
    state_records = [
        {
            "state": row.state,
            "districts": int(row.districts),
            "higher_coverage": int(row.higher_coverage),
            "lower_coverage": int(row.lower_coverage),
            "lower_coverage_share": number(row.lower_coverage_share),
            "mean_score": number(row.mean_score),
        }
        for row in state_summary.itertuples(index=False)
    ]
    top_state = state_summary.iloc[0]
    top_gap = gaps.iloc[0]
    payload = {
        "metadata": {
            "title": "District Healthcare Access Segmentation",
            "district_count": len(data),
            "feature_count": len(feature_columns),
            "baseline": "K-Means, k=2; existing project baseline retained.",
            "score_method": "Analytical score: unweighted mean of each indicator after min-max rescaling to 0–100. It is not an official health index.",
            "source_note": "NFHS-5 district-level outputs supplied with this project.",
        },
        "features": feature_metadata,
        "districts": district_records,
        "cluster_profiles": profiles,
        "gaps": gap_records,
        "states": state_records,
        "quality": {
            "cleaned_missing_values": int(values.isna().sum().sum()),
            "districts": len(data),
            "features": len(feature_columns),
            "imputation_note": "The original notebook documents median imputation for missing childhood-vaccination values before this cleaned table was exported.",
        },
        "algorithms": json_records(algorithms),
        "subsample_stability": json_records(stability),
        "seed_stability": json_records(seed_stability),
        "insights": [
            f"{top_state.state} has the largest share of baseline lower-coverage districts: {top_state.lower_coverage_share:.1f}% ({int(top_state.lower_coverage)} of {int(top_state.districts)}).",
            f"The largest baseline cluster gap is {short_label(top_gap.indicator)}: {top_gap.absolute_gap:.1f} percentage points.",
            f"The retained baseline contains {int((data.Cluster == 0).sum())} higher-coverage and {int((data.Cluster == 1).sum())} lower-coverage districts.",
        ],
        "map": {
            "boundary_file": "static/data/india_district_boundaries.geojson",
            "available": False,
            "message": "District boundary GeoJSON is not bundled. Add a compatible boundary file at the stated path to enable the choropleth layer; the explorer and state/district drill-down already work without it.",
        },
    }
    WEB_DATA.parent.mkdir(parents=True, exist_ok=True)
    WEB_DATA.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {WEB_DATA} with {len(district_records)} districts.")


if __name__ == "__main__":
    main()
