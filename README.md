# District Healthcare Access Segmentation for Rural Service Prioritization

## Project Overview
This project applies unsupervised machine learning to district-level healthcare indicators from NFHS-5 data to identify patterns in healthcare coverage across districts.

## Objectives
- Prepare and clean district-level healthcare data.
- Apply K-Means clustering using multiple cluster counts.
- Evaluate clustering configurations using WCSS, Silhouette Score, and Davies-Bouldin Index.
- Visualize clustering results using PCA.
- Interpret the resulting healthcare coverage groups.

## Dataset
The project uses selected district-level healthcare indicators from NFHS-5.

## Methodology
1. Data preparation and feature selection.
2. Missing-value treatment.
3. Feature standardization.
4. K-Means clustering.
5. Cluster evaluation.
6. PCA visualization.
7. Cluster interpretation.

## Repository Structure
- `analysis/` - Original Jupyter notebook and analysis documentation.
- `data/raw/` - Original NFHS-5 dataset.
- `data/processed/` - Cleaned features and final cluster assignments.
- `results/` - Cluster summaries, indicator comparisons, PCA coordinates, and state-level outputs.

## Machine Learning Approach
Unsupervised learning using K-Means clustering.

## Important Note
The identified clusters represent patterns in the selected healthcare indicators. They should not be interpreted as a complete measure of healthcare quality or as evidence of causation.

## Team Project
This is a collaborative academic project involving three contributors.
