from pathlib import Path

from flask import Flask, jsonify, render_template


ROOT = Path(__file__).resolve().parent
app = Flask(__name__)


@app.get("/")
def dashboard():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify({"status": "ok", "data_file": "static/data/healthcare_dashboard_data.json"})


if __name__ == "__main__":
    app.run(debug=False)
