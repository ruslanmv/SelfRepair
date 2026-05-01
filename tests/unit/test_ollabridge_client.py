from selfrepair.llm.ollabridge_client import OllaBridgeClient
from selfrepair.settings import Settings

def test_ollabridge_unavailable(tmp_path):
    settings = Settings(
        OLLABRIDGE_ENABLED=True,
        OLLABRIDGE_BASE_URL="http://localhost:99999",
        WORK_DIR=tmp_path / "work",
        STATE_DIR=tmp_path / "state",
        STATUS_SITE_DIR=tmp_path / "status-site",
    )
    client = OllaBridgeClient(settings)
    assert client.available() is False
