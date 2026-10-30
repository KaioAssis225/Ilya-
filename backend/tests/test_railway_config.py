import json
from pathlib import Path


def test_web_service_restarts_after_clean_worker_recycle():
    config_path = Path(__file__).parents[1] / "railway.json"
    deploy = json.loads(config_path.read_text(encoding="utf-8"))["deploy"]

    assert deploy["restartPolicyType"] == "ALWAYS"


def test_order_email_worker_config_has_no_http_healthcheck_or_migration():
    # O worker de e-mail não serve HTTP: herdar o healthcheck e o pré-deploy de
    # migration da API derrubaria o deploy dele.
    config_path = Path(__file__).parents[1] / "railway.order-email-worker.json"
    deploy = json.loads(config_path.read_text(encoding="utf-8"))["deploy"]

    assert deploy["startCommand"] == "python -m app.workers.order_email_sender"
    assert deploy["restartPolicyType"] == "ALWAYS"
    assert "healthcheckPath" not in deploy
    assert "preDeployCommand" not in deploy
