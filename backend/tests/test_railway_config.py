import json
from pathlib import Path


def test_web_service_restarts_after_clean_worker_recycle():
    config_path = Path(__file__).parents[1] / "railway.json"
    deploy = json.loads(config_path.read_text(encoding="utf-8"))["deploy"]

    assert deploy["restartPolicyType"] == "ALWAYS"
