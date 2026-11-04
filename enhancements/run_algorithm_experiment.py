"""Compare clustering algorithms and quantify segmentation stability.

This script deliberately reads the already-cleaned district feature table and writes
only under ``enhancements/outputs``.  It does not modify the original notebook,
source data, or previously exported project results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.cluster import AgglomerativeClustering, DBSCAN, KMeans
from sklearn.metrics import (
    adjusted_rand_score,
    calinski_harabasz_score,
    davies_bouldin_score,
    silhouette_score,
)
from sklearn.preprocessing import StandardScaler


RANDOM_SEED = 42
IDENTIFIER_COLUMNS = ("state_code", "state", "district")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run K-Means, hierarchical, and DBSCAN experiments for district healthcare features."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "district_features_cleaned.csv",
        help="Cleaned district feature CSV from the original project.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "outputs",
        help="Directory for generated enhancement artifacts.",
    )
    parser.add_argument(
        "--stability-repeats",
        type=int,
        default=50,
        help="Number of paired 80%% subsamples used for each selected model.",
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_features(path: Path) -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Load identifiers and numeric features, rejecting accidental input changes."""
    data = pd.read_csv(path)
    missing_ids = [column for column in IDENTIFIER_COLUMNS if column not in data.columns]
    if missing_ids:
        raise ValueError(f"Input is missing identifier columns: {missing_ids}")
    feature_columns = [column for column in data.columns if column not in IDENTIFIER_COLUMNS]
    if not feature_columns:
        raise ValueError("No feature columns were found in the input CSV.")
    features = data[feature_columns].apply(pd.to_numeric, errors="raise")
    if features.isna().any().any():
        raise ValueError("Input contains missing feature values; impute them before clustering.")
    scaler = StandardScaler()
    return data.loc[:, IDENTIFIER_COLUMNS].copy(), features, scaler.fit_transform(features)


def metrics_for_labels(X: np.ndarray, labels: np.ndarray) -> dict[str, float | int]:
    """Return clustering quality metrics, explicitly recording DBSCAN noise."""
    labels = np.asarray(labels)
    clustered = labels != -1
    clustered_labels = labels[clustered]
    cluster_count = len(np.unique(clustered_labels))
    coverage = float(clustered.mean())
    result: dict[str, float | int] = {
        "n_clusters": int(cluster_count),
        "n_noise": int((~clustered).sum()),
        "clustered_fraction": coverage,
        "silhouette": np.nan,
        "davies_bouldin": np.nan,
        "calinski_harabasz": np.nan,
    }
    if cluster_count >= 2 and clustered.sum() > cluster_count:
        result["silhouette"] = float(silhouette_score(X[clustered], clustered_labels))
        result["davies_bouldin"] = float(davies_bouldin_score(X[clustered], clustered_labels))
        result["calinski_harabasz"] = float(calinski_harabasz_score(X[clustered], clustered_labels))
    return result


def evaluate_kmeans(X: np.ndarray) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    rows, labels_by_id = [], {}
    for k in range(2, 9):
        model = KMeans(n_clusters=k, n_init=30, random_state=RANDOM_SEED)
        labels = model.fit_predict(X)
        config_id = f"kmeans_k{k}"
        rows.append({"algorithm": "kmeans", "config_id": config_id, "k": k, **metrics_for_labels(X, labels), "inertia": model.inertia_})
        labels_by_id[config_id] = labels
    return pd.DataFrame(rows), labels_by_id


def evaluate_hierarchical(X: np.ndarray) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    rows, labels_by_id = [], {}
    for linkage in ("ward", "complete", "average"):
        for k in range(2, 9):
            model = AgglomerativeClustering(n_clusters=k, linkage=linkage)
            labels = model.fit_predict(X)
            config_id = f"hierarchical_{linkage}_k{k}"
            rows.append(
                {
                    "algorithm": "hierarchical",
                    "config_id": config_id,
                    "linkage": linkage,
                    "k": k,
                    **metrics_for_labels(X, labels),
                    "inertia": np.nan,
                }
            )
            labels_by_id[config_id] = labels
    return pd.DataFrame(rows), labels_by_id


def evaluate_dbscan(X: np.ndarray) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    rows, labels_by_id = [], {}
    for min_samples in (4, 6, 8, 10):
        for eps in np.round(np.arange(1.50, 4.51, 0.25), 2):
            model = DBSCAN(eps=float(eps), min_samples=min_samples)
            labels = model.fit_predict(X)
            config_id = f"dbscan_eps{eps:.2f}_min{min_samples}"
            rows.append(
                {
                    "algorithm": "dbscan",
                    "config_id": config_id,
                    "eps": float(eps),
                    "min_samples": min_samples,
                    **metrics_for_labels(X, labels),
                    "inertia": np.nan,
                }
            )
            labels_by_id[config_id] = labels
    return pd.DataFrame(rows), labels_by_id


def choose_configuration(results: pd.DataFrame, algorithm: str) -> pd.Series | None:
    """Choose the strongest non-degenerate configuration for one algorithm family."""
    candidates = results[(results["algorithm"] == algorithm) & results["silhouette"].notna()].copy()
    if candidates.empty:
        return None
    if algorithm == "dbscan":
        # A score based on only a tiny non-noise subset is not a useful segmentation.
        candidates = candidates[candidates["clustered_fraction"] >= 0.60]
        if candidates.empty:
            return None
    return candidates.sort_values(
        ["silhouette", "davies_bouldin", "clustered_fraction", "n_clusters"],
        ascending=[False, True, False, True],
    ).iloc[0]


def refit_labels(config: pd.Series, X: np.ndarray, seed: int = RANDOM_SEED) -> np.ndarray:
    if config["algorithm"] == "kmeans":
        return KMeans(n_clusters=int(config["k"]), n_init=30, random_state=seed).fit_predict(X)
    if config["algorithm"] == "hierarchical":
        return AgglomerativeClustering(n_clusters=int(config["k"]), linkage=str(config["linkage"])).fit_predict(X)
    if config["algorithm"] == "dbscan":
        return DBSCAN(eps=float(config["eps"]), min_samples=int(config["min_samples"])).fit_predict(X)
    raise ValueError(f"Unsupported algorithm: {config['algorithm']}")


def paired_subsample_stability(
    X: np.ndarray, config: pd.Series, repeats: int, seed: int = RANDOM_SEED
) -> pd.DataFrame:
    """Compare two independent 80% samples on their overlap using adjusted Rand index.

    ARI is label-permutation invariant.  For DBSCAN, points marked noise in either
    sample are excluded so the score measures stability of formed clusters; the
    retained overlap fraction is reported alongside it.
    """
    if repeats < 2:
        raise ValueError("stability-repeats must be at least 2.")
    rng = np.random.default_rng(seed)
    sample_size = max(3, int(np.floor(0.80 * len(X))))
    rows = []
    for replicate in range(1, repeats + 1):
        left_indices = np.sort(rng.choice(len(X), size=sample_size, replace=False))
        right_indices = np.sort(rng.choice(len(X), size=sample_size, replace=False))
        left_labels = refit_labels(config, X[left_indices], seed=seed + 2 * replicate)
        right_labels = refit_labels(config, X[right_indices], seed=seed + 2 * replicate + 1)
        common, left_pos, right_pos = np.intersect1d(left_indices, right_indices, return_indices=True)
        left_common = left_labels[left_pos]
        right_common = right_labels[right_pos]
        retained = (left_common != -1) & (right_common != -1)
        score = np.nan
        if retained.sum() >= 3 and len(np.unique(left_common[retained])) >= 2 and len(np.unique(right_common[retained])) >= 2:
            score = float(adjusted_rand_score(left_common[retained], right_common[retained]))
        rows.append(
            {
                "algorithm": config["algorithm"],
                "config_id": config["config_id"],
                "replicate": replicate,
                "overlap_districts": len(common),
                "retained_overlap_fraction": float(retained.mean()),
                "adjusted_rand_index": score,
            }
        )
    return pd.DataFrame(rows)


def kmeans_random_seed_stability(X: np.ndarray, config: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Measure assignment consistency for the selected K-Means setup across seeds."""
    if config["algorithm"] != "kmeans":
        raise ValueError("Random-seed stability is defined here for K-Means only.")
    seeds = list(range(50))
    labels_by_seed = {
        seed: KMeans(n_clusters=int(config["k"]), n_init=30, random_state=seed).fit_predict(X)
        for seed in seeds
    }
    pair_rows = []
    for left_position, left_seed in enumerate(seeds):
        for right_seed in seeds[left_position + 1 :]:
            pair_rows.append(
                {
                    "config_id": config["config_id"],
                    "seed_a": left_seed,
                    "seed_b": right_seed,
                    "adjusted_rand_index": adjusted_rand_score(labels_by_seed[left_seed], labels_by_seed[right_seed]),
                }
            )
    pairs = pd.DataFrame(pair_rows)
    summary = pd.DataFrame(
        [
            {
                "algorithm": "kmeans",
                "config_id": config["config_id"],
                "seeds_tested": len(seeds),
                "pairwise_comparisons": len(pairs),
                "ari_mean": pairs["adjusted_rand_index"].mean(),
                "ari_median": pairs["adjusted_rand_index"].median(),
                "ari_min": pairs["adjusted_rand_index"].min(),
            }
        ]
    )
    return pairs, summary


def write_label_file(
    identifiers: pd.DataFrame, raw_features: pd.DataFrame, labels: np.ndarray, config: pd.Series, output_dir: Path
) -> Path:
    result = pd.concat([identifiers.reset_index(drop=True), raw_features.reset_index(drop=True)], axis=1)
    result["cluster"] = labels
    result["algorithm"] = config["algorithm"]
    result["configuration"] = config["config_id"]
    path = output_dir / f"selected_{config['algorithm']}_labels.csv"
    result.to_csv(path, index=False)
    return path


def plot_quality(metrics: pd.DataFrame, output_dir: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    for algorithm, group in metrics.groupby("algorithm"):
        valid = group.dropna(subset=["silhouette"])
        axes[0].scatter(valid["n_clusters"], valid["silhouette"], label=algorithm, alpha=0.8)
        axes[1].scatter(valid["n_clusters"], valid["davies_bouldin"], label=algorithm, alpha=0.8)
    axes[0].set(title="Silhouette comparison", xlabel="Clusters formed", ylabel="Silhouette (higher is better)")
    axes[1].set(title="Davies–Bouldin comparison", xlabel="Clusters formed", ylabel="Davies–Bouldin (lower is better)")
    for axis in axes:
        axis.grid(alpha=0.25)
        axis.legend()
    fig.tight_layout()
    fig.savefig(output_dir / "algorithm_quality_comparison.png", dpi=180)
    plt.close(fig)


def plot_stability(stability: pd.DataFrame, output_dir: Path) -> None:
    fig, axis = plt.subplots(figsize=(8, 5))
    groups = [group["adjusted_rand_index"].dropna().to_numpy() for _, group in stability.groupby("algorithm")]
    labels = [name for name, _ in stability.groupby("algorithm")]
    if groups:
        axis.boxplot(groups, tick_labels=labels, showmeans=True)
    axis.set(title="Paired-subsample stability", ylabel="Adjusted Rand index (higher is better)")
    axis.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    fig.savefig(output_dir / "stability_distribution.png", dpi=180)
    plt.close(fig)


def write_report(
    path: Path,
    input_path: Path,
    features: pd.DataFrame,
    selected: list[pd.Series],
    stability_summary: pd.DataFrame,
    dbscan_selected: bool,
) -> None:
    lines = [
        "# Algorithm experimentation and stability analysis",
        "",
        "## Scope",
        "",
        f"- Input: `{input_path.name}` ({len(features)} districts, {features.shape[1]} numeric indicators).",
        "- Preprocessing: feature-wise standardization with `StandardScaler`.",
        "- Algorithms searched: K-Means (k=2–8), agglomerative hierarchical clustering (Ward, complete, and average linkage; k=2–8), and DBSCAN (eps=1.50–4.50; min_samples=4, 6, 8, 10).",
        "- Selection: highest silhouette score, then lower Davies–Bouldin index, then simpler cluster count. DBSCAN additionally requires at least 60% non-noise coverage.",
        "- Stability: 50 paired 80% district subsamples; adjusted Rand index (ARI) on their shared districts. DBSCAN ARI excludes districts marked as noise by either fit, and reports retained overlap.",
        "",
        "## Selected configurations",
        "",
    ]
    for config in selected:
        lines.append(
            f"- **{config['algorithm']}** — `{config['config_id']}`; silhouette {config['silhouette']:.3f}, "
            f"Davies–Bouldin {config['davies_bouldin']:.3f}, {int(config['n_clusters'])} clusters, "
            f"{config['clustered_fraction']:.1%} of districts clustered."
        )
    if not dbscan_selected:
        lines.extend(["- **DBSCAN** — evaluated, but no configuration both formed at least two clusters and retained 60% of districts; it is not presented as a final segmentation."])
    lines.extend(["", "## Stability summary", ""])
    for _, row in stability_summary.iterrows():
        lines.append(
            f"- **{row['algorithm']}**: median ARI {row['ari_median']:.3f}; mean ARI {row['ari_mean']:.3f}; "
            f"valid comparisons {int(row['valid_replicates'])}/{int(row['replicates'])}; "
            f"median retained overlap {row['retained_overlap_median']:.1%}."
        )
    lines.extend(
        [
            "",
            "## Interpretation guardrails",
            "",
            "- Cluster identifiers are arbitrary and must not be interpreted as an ordinal ranking without reviewing each cluster profile.",
            "- Internal validity and resampling stability support a useful segmentation, but they do not establish causal differences in healthcare access.",
            "- Compare the selected-label CSVs and the full metric grid before choosing one operational model.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    identifiers, raw_features, X = load_features(input_path)

    kmeans_results, _ = evaluate_kmeans(X)
    hierarchical_results, _ = evaluate_hierarchical(X)
    dbscan_results, _ = evaluate_dbscan(X)
    metrics = pd.concat([kmeans_results, hierarchical_results, dbscan_results], ignore_index=True)
    metrics.to_csv(output_dir / "algorithm_metrics.csv", index=False)
    plot_quality(metrics, output_dir)

    selected = [
        config
        for config in (choose_configuration(metrics, "kmeans"), choose_configuration(metrics, "hierarchical"), choose_configuration(metrics, "dbscan"))
        if config is not None
    ]
    selected_table = pd.DataFrame(selected)
    selected_table.to_csv(output_dir / "selected_configurations.csv", index=False)

    selected_kmeans = next(config for config in selected if config["algorithm"] == "kmeans")
    seed_pairs, seed_summary = kmeans_random_seed_stability(X, selected_kmeans)
    seed_pairs.to_csv(output_dir / "kmeans_random_seed_stability.csv", index=False)
    seed_summary.to_csv(output_dir / "kmeans_random_seed_stability_summary.csv", index=False)

    stability_parts = []
    for config in selected:
        labels = refit_labels(config, X)
        write_label_file(identifiers, raw_features, labels, config, output_dir)
        stability_parts.append(paired_subsample_stability(X, config, args.stability_repeats))
    stability = pd.concat(stability_parts, ignore_index=True)
    stability.to_csv(output_dir / "stability_replicates.csv", index=False)
    stability_summary = (
        stability.groupby(["algorithm", "config_id"], as_index=False)
        .agg(
            replicates=("replicate", "size"),
            valid_replicates=("adjusted_rand_index", "count"),
            ari_mean=("adjusted_rand_index", "mean"),
            ari_median=("adjusted_rand_index", "median"),
            ari_std=("adjusted_rand_index", "std"),
            retained_overlap_median=("retained_overlap_fraction", "median"),
        )
    )
    stability_summary.to_csv(output_dir / "stability_summary.csv", index=False)
    plot_stability(stability, output_dir)
    write_report(
        output_dir / "algorithm_experiment_report.md",
        input_path,
        raw_features,
        selected,
        stability_summary,
        dbscan_selected=any(config["algorithm"] == "dbscan" for config in selected),
    )
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_file": input_path.name,
        "input_sha256": file_sha256(input_path),
        "districts": len(raw_features),
        "features": raw_features.shape[1],
        "stability_repeats": args.stability_repeats,
        "scikit_learn_version": sklearn.__version__,
    }
    (output_dir / "run_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"Completed experiments for {len(raw_features)} districts and {raw_features.shape[1]} features.")
    print(f"Outputs written to: {output_dir}")


if __name__ == "__main__":
    main()
