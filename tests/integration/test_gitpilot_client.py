from selfrepair.gitpilot.client import GitPilotClient

def test_gitpilot_client_unavailable(temp_settings):
    client = GitPilotClient(temp_settings)
    result = client.run_headless("agent-matrix/demo", "hello")
    assert result["success"] is False
