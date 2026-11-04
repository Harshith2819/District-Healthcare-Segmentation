"""Local server for the District Healthcare Access Segmentation website."""

from pathlib import Path

from flask import Flask, jsonify, render_template


ROOT = Path(__file__).resolve().parent
app = Flask(__name__)


@app.after_request
def disable_browser_cache(response):
    """Keep HTML, CSS, and JavaScript in sync while the local site is being edited."""
    response.headers["Cache-Control"] = "no-store, max-age=0"
    return response


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    data_file = ROOT / "static" / "data" / "dashboard.json"
    return jsonify({"status": "ok", "dashboard_data_available": data_file.exists()})


if __name__ == "__main__":
    # Port 5051 intentionally avoids an older dashboard process that may still use 5000.
    app.run(host="127.0.0.1", port=5051, debug=False)
