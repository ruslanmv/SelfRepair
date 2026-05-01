from selfrepair.matrixlab.executor import execute_command

def test_local_executor(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = execute_command(tmp_path, ["python", "-c", "print('ok')"], 10)
    assert result.ok
