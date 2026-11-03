# Algorithm experimentation and stability analysis

## Scope

- Input: `district_features_cleaned.csv` (341 districts, 15 numeric indicators).
- Preprocessing: feature-wise standardization with `StandardScaler`.
- Algorithms searched: K-Means (k=2–8), agglomerative hierarchical clustering (Ward, complete, and average linkage; k=2–8), and DBSCAN (eps=1.50–4.50; min_samples=4, 6, 8, 10).
- Selection: highest silhouette score, then lower Davies–Bouldin index, then simpler cluster count. DBSCAN additionally requires at least 60% non-noise coverage.
- Stability: 50 paired 80% district subsamples; adjusted Rand index (ARI) on their shared districts. DBSCAN ARI excludes districts marked as noise by either fit, and reports retained overlap.

## Selected configurations

- **kmeans** — `kmeans_k2`; silhouette 0.304, Davies–Bouldin 1.440, 2 clusters, 100.0% of districts clustered.
- **hierarchical** — `hierarchical_complete_k2`; silhouette 0.437, Davies–Bouldin 0.904, 2 clusters, 100.0% of districts clustered.
- **dbscan** — `dbscan_eps2.75_min4`; silhouette 0.495, Davies–Bouldin 0.572, 2 clusters, 90.9% of districts clustered.

## Stability summary

- **dbscan**: median ARI 1.000; mean ARI 1.000; valid comparisons 25/50; median retained overlap 89.3%.
- **hierarchical**: median ARI 0.812; mean ARI 0.755; valid comparisons 50/50; median retained overlap 100.0%.
- **kmeans**: median ARI 0.925; mean ARI 0.907; valid comparisons 50/50; median retained overlap 100.0%.

## Interpretation guardrails

- Cluster identifiers are arbitrary and must not be interpreted as an ordinal ranking without reviewing each cluster profile.
- Internal validity and resampling stability support a useful segmentation, but they do not establish causal differences in healthcare access.
- Compare the selected-label CSVs and the full metric grid before choosing one operational model.
