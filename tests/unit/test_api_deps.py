"""Unit tests for `selfrepair.api.deps`.

The cursor encode/decode pair is on every list endpoint's hot path;
small bugs there silently truncate pagination. Cover the roundtrip,
the URL-safe alphabet, and rejection of garbage tokens.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from selfrepair.api.deps import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    Pagination,
    decode_cursor,
    encode_cursor,
    pagination,
)


class TestCursorRoundtrip:
    def test_simple_payload(self) -> None:
        token = encode_cursor({"after_id": "abc", "n": 7})
        decoded = decode_cursor(token)
        assert decoded == {"after_id": "abc", "n": 7}

    def test_empty_payload(self) -> None:
        token = encode_cursor({})
        assert decode_cursor(token) == {}

    def test_uuid_serialises_via_default(self) -> None:
        u = uuid.uuid4()
        token = encode_cursor({"after_id": str(u)})
        assert decode_cursor(token)["after_id"] == str(u)

    def test_token_uses_urlsafe_alphabet(self) -> None:
        # 256 bytes of payload is very unlikely to round-trip without
        # padding, so we exercise that path too.
        token = encode_cursor({"k": "x" * 256})
        # urlsafe alphabet only: A-Z a-z 0-9 - _.
        assert all(c.isalnum() or c in {"-", "_"} for c in token)

    def test_garbage_cursor_is_400(self) -> None:
        with pytest.raises(HTTPException) as exc:
            decode_cursor("not-base64-!@#")
        assert exc.value.status_code == 400

    def test_non_dict_cursor_is_400(self) -> None:
        # The decoder demands a dict at the top level. A well-formed
        # JSON list must be rejected with 400, not silently accepted.
        import base64

        token = base64.urlsafe_b64encode(b"[1,2,3]").rstrip(b"=").decode("ascii")
        with pytest.raises(HTTPException) as exc:
            decode_cursor(token)
        assert exc.value.status_code == 400


class TestPagination:
    def test_default_limit(self) -> None:
        page = pagination()
        assert page.limit == DEFAULT_LIMIT
        assert page.cursor is None

    def test_explicit_limit_passed_through(self) -> None:
        page = pagination(limit=10)
        assert page.limit == 10

    @pytest.mark.parametrize("bad", [0, -1, MAX_LIMIT + 1, 10_000])
    def test_out_of_range_limit_is_400(self, bad: int) -> None:
        with pytest.raises(HTTPException) as exc:
            pagination(limit=bad)
        assert exc.value.status_code == 400

    def test_cursor_decoded_into_dict(self) -> None:
        token = encode_cursor({"after_id": "xyz"})
        page = pagination(cursor=token)
        assert isinstance(page.cursor, dict)
        assert page.cursor["after_id"] == "xyz"

    def test_pagination_dataclass_is_immutable(self) -> None:
        page = Pagination(limit=10, cursor=None)
        # frozen=True dataclass raises FrozenInstanceError on mutation.
        from dataclasses import FrozenInstanceError

        with pytest.raises(FrozenInstanceError):
            page.limit = 99  # type: ignore[misc]
