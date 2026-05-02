import httpx
import pytest

from selfrepair.connectors.gitpilot import (
    Budget,
    GitPilotClient,
    GitPilotError,
    RepairRequest,
    Workspace,
    _iter_sse,
)


class TestSSEParser:
    def test_parses_event_and_data_pair(self) -> None:
        lines = [
            "event: plan",
            'data: {"steps": ["a", "b"]}',
            "",
        ]
        events = list(_iter_sse(iter(lines)))
        assert events == [{"event": "plan", "data": {"steps": ["a", "b"]}}]

    def test_handles_multiline_data(self) -> None:
        lines = ["event: msg", 'data: {"x":', "data: 1}", ""]
        events = list(_iter_sse(iter(lines)))
        assert events == [{"event": "msg", "data": {"x": 1}}]

    def test_ignores_comments_and_heartbeats(self) -> None:
        lines = [": heartbeat", "event: ping", "data: {}", ""]
        events = list(_iter_sse(iter(lines)))
        assert events == [{"event": "ping", "data": {}}]

    def test_handles_invalid_json_payload(self) -> None:
        lines = ["event: bad", "data: not-json{", ""]
        events = list(_iter_sse(iter(lines)))
        assert events == [{"event": "bad", "data": {"raw": "not-json{"}}]


def _make_client(
    *, status: int, sse_lines: list[str] | None = None, body: bytes | None = None
) -> GitPilotClient:
    if body is None:
        body = ("\n".join(sse_lines or []) + "\n").encode("utf-8")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            status_code=status,
            content=body,
            headers={"content-type": "text/event-stream"},
        )
    )
    return GitPilotClient(
        base_url="http://gitpilot",
        token="t",
        client=httpx.Client(transport=transport),
    )


def _request() -> RepairRequest:
    return RepairRequest(
        repair_id="rep_test",
        workspace=Workspace(kind="git_bundle", url="s3://bundle"),
        context={"finding": {"kind": "missing_makefile"}},
        budget=Budget(usd=0.10),
    )


class TestGitPilotClient:
    def test_repair_returns_success_on_done_event(self) -> None:
        client = _make_client(
            status=200,
            sse_lines=[
                "event: plan",
                'data: {"steps": []}',
                "",
                "event: done",
                'data: {"patch_url": "s3://patch", "signed_provenance": {"sig": "abc"}}',
                "",
            ],
        )
        result = client.repair(_request())
        assert result.success is True
        assert result.patch_url == "s3://patch"
        assert result.provenance == {"sig": "abc"}

    def test_repair_returns_failure_on_error_event(self) -> None:
        client = _make_client(
            status=200,
            sse_lines=[
                "event: error",
                'data: {"error": "budget exceeded"}',
                "",
            ],
        )
        result = client.repair(_request())
        assert result.success is False
        assert result.error == "budget exceeded"

    def test_repair_returns_failure_on_no_events(self) -> None:
        client = _make_client(status=200, body=b"")
        result = client.repair(_request())
        assert result.success is False
        assert result.error and "no events" in result.error

    def test_http_error_raises_gitpilot_error(self) -> None:
        client = _make_client(status=503, body=b"upstream down")
        with pytest.raises(GitPilotError, match="503"):
            client.repair(_request())

    def test_idempotency_key_is_set_to_repair_id(self) -> None:
        captured: dict[str, dict[str, str]] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["headers"] = {
                k.lower(): v for k, v in request.headers.items()
            }
            return httpx.Response(
                status_code=200,
                content=b"event: done\ndata: {}\n\n",
                headers={"content-type": "text/event-stream"},
            )

        client = GitPilotClient(
            base_url="http://gitpilot",
            token="t",
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        client.repair(_request())
        assert captured["headers"]["idempotency-key"] == "rep_test"
        assert captured["headers"]["authorization"] == "Bearer t"

    def test_context_manager_closes_client(self) -> None:
        client = _make_client(
            status=200,
            sse_lines=["event: done", "data: {}", ""],
        )
        with client as c:
            c.repair(_request())
        assert c._client.is_closed
