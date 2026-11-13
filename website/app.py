"""Flask application for the District Healthcare Service Planning tool.

The website is a decision-support tool, not a prediction system. All scenario
calculations happen here in Flask; the browser only collects input and displays
the response.
"""

from __future__ import annotations

import json
from pathlib import Path

from flask import Flask, jsonify, render_template, request


ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "static" / "data" / "dashboard.json"
app = Flask(__name__)


def load_dashboard() -> dict:
    """Read the generated project data bundle without modifying source results."""
    if not DATA_FILE.exists():
        raise FileNotFoundError(
            "Website data is missing. Run: python website/scripts/build_dashboard_data.py"
        )
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


def bounded_number(value: object, lower: float, upper: float) -> float:
    """Convert user input safely and keep it within the observed indicator range."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Each scenario value must be a number.") from exc
    return max(lower, min(upper, number))


def analytical_score(values: list[float], features: list[dict]) -> float:
    """The documented unweighted min-max score used by the project website."""
    scaled = []
    for value, feature in zip(values, features, strict=True):
        spread = feature["max"] - feature["min"]
        scaled.append(100 * (value - feature["min"]) / (spread or 1))
    return sum(scaled) / len(scaled)


def readable_indicator(feature: dict) -> str:
    return feature["short_label"].replace("…", "")


def build_service_actions(scenario: list[float], dashboard: dict) -> list[dict]:
    """Evidence-led planning prompts, never clinical recommendations."""
    features = dashboard["features"]
    higher_profile = next(
        profile for profile in dashboard["cluster_profiles"] if profile["cluster"] == 0
    )
    opportunities = []
    for index, (value, feature) in enumerate(zip(scenario, features, strict=True)):
        target = higher_profile["values"][index]
        gap = max(0.0, target - value)
        opportunities.append((gap, index, target))

    opportunities.sort(key=lambda row: row[0], reverse=True)
    actions = []
    for gap, index, target in opportunities[:3]:
        feature = features[index]
        label = readable_indicator(feature).lower()
        action = "Maintain and monitor local coverage."
        if "antenatal" in label or "mothers" in label or "birth" in label:
            action = "Use ASHA/ANM follow-up lists, appointment reminders, and referral tracking."
        elif "vaccine" in label or "vitamin" in label:
            action = "Review outreach-session coverage and follow up with missed eligible children."
        elif "water" in label or "sanitation" in label:
            action = "Coordinate with water and sanitation teams and track underserved hamlets."
        elif "insurance" in label:
            action = "Run enrolment and awareness support through local health and community workers."
        actions.append(
            {
                "indicator": readable_indicator(feature),
                "current": round(scenario[index], 1),
                "higher_coverage_reference": round(target, 1),
                "gap": round(gap, 1),
                "action": action,
            }
        )
    return actions


@app.after_request
def disable_browser_cache(response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/dashboard")
def dashboard_data():
    return jsonify(load_dashboard())


@app.post("/api/plan")
def calculate_plan():
    """Calculate a hypothetical service scenario on the backend."""
    payload = request.get_json(silent=True) or {}
    dashboard = load_dashboard()
    district = next(
        (row for row in dashboard["districts"] if row["id"] == payload.get("district_id")),
        None,
    )
    if district is None:
        return jsonify({"error": "Choose a valid district."}), 400

    values = payload.get("values")
    if not isinstance(values, list) or len(values) != len(dashboard["features"]):
        return jsonify({"error": "A value is required for every healthcare indicator."}), 400

    try:
        scenario = [
            bounded_number(value, feature["min"], feature["max"])
            for value, feature in zip(values, dashboard["features"], strict=True)
        ]
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    original_score = analytical_score(district["values"], dashboard["features"])
    scenario_score = analytical_score(scenario, dashboard["features"])
    changes = [
        {
            "label": readable_indicator(feature),
            "original": round(original, 1),
            "scenario": round(updated, 1),
            "change": round(updated - original, 1),
        }
        for original, updated, feature in zip(
            district["values"], scenario, dashboard["features"], strict=True
        )
        if abs(updated - original) >= 0.05
    ]
    changes.sort(key=lambda item: abs(item["change"]), reverse=True)

    return jsonify(
        {
            "original_score": round(original_score, 1),
            "scenario_score": round(scenario_score, 1),
            "score_change": round(scenario_score - original_score, 1),
            "changed_indicators": changes[:5],
            "service_actions": build_service_actions(scenario, dashboard),
            "notice": "Planning scenario only: it does not overwrite the dataset, predict outcomes, or provide clinical advice.",
        }
    )


@app.get("/health")
def health():
    return jsonify({"status": "ok", "dashboard_data_available": DATA_FILE.exists()})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5051, debug=False)
