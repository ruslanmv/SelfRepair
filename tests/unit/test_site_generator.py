import json

from selfrepair.models import RepoHealthReport
from selfrepair.site.generator import generate_site

def test_generate_site(temp_settings):
    latest = temp_settings.state_dir / "latest_status.json"
    report = RepoHealthReport(repo={"name":"demo","full_name":"agent-matrix/demo","clone_url":"https://x","default_branch":"main"}, status="healthy")
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({"items":[report.model_dump(mode="json")]}), encoding="utf-8")
    generate_site(temp_settings)
    assert (temp_settings.status_site_dir / "data" / "summary.json").exists()
