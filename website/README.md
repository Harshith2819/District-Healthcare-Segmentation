# District Healthcare Access Segmentation — Website

This folder is self-contained for website handoff. The notebooks, original CSV files,
and clustering-analysis scripts remain outside `website/`.

## Folder contents

- `app.py` — local Flask server.
- `templates/` and `static/` — the complete user interface.
- `scripts/build_dashboard_data.py` — builds the browser data bundle from the project’s real outputs.
- `static/data/dashboard.json` — generated analytics data used by the interface.

## First-time setup or after data/model changes

From the project root:

```powershell
python enhancements\run_algorithm_experiment.py
python website\scripts\build_dashboard_data.py
```

## Everyday use

The generated data is saved, so only one command is needed:

```powershell
python website\app.py
```

Open `http://127.0.0.1:5051`.

## Chart behavior

The selected district’s indicator bar chart, radar chart, score pie chart, scenario
comparison bars, and selected-state mean line all update when a simulator slider
changes. The original cleaned CSV and model assignments are never altered.

## Deployment note

Chart.js is loaded from a public CDN. For an offline deployment, install and bundle
Chart.js locally before publishing.
