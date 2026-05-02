from __future__ import annotations

from selfrepair.git.codeowners import (
    CodeOwnerRule,
    owners_for,
    parse,
)


class TestParse:
    def test_skips_blank_and_comment_lines(self) -> None:
        text = (
            "# comment\n"
            "\n"
            "*.py    @py-team\n"
        )
        rules = parse(text)
        assert len(rules) == 1
        assert rules[0].pattern == "*.py"
        assert rules[0].owners == ("@py-team",)

    def test_handles_multiple_owners(self) -> None:
        rules = parse("/docs/   @docs @writers")
        assert rules[0].owners == ("@docs", "@writers")

    def test_strips_inline_comment(self) -> None:
        rules = parse("*.go @go-team  # the go champions")
        assert rules[0].owners == ("@go-team",)

    def test_skips_malformed_lines(self) -> None:
        rules = parse("only-pattern\n*.py @x")
        assert len(rules) == 1
        assert rules[0].pattern == "*.py"


class TestOwnersFor:
    def test_last_match_wins(self) -> None:
        rules = [
            CodeOwnerRule("*.py", ("@everyone",)),
            CodeOwnerRule("src/auth/*.py", ("@security",)),
        ]
        assert owners_for(["src/auth/login.py"], rules) == {"@security"}

    def test_no_match_returns_empty(self) -> None:
        rules = [CodeOwnerRule("*.py", ("@x",))]
        assert owners_for(["README.md"], rules) == set()

    def test_unions_owners_across_paths(self) -> None:
        rules = [
            CodeOwnerRule("*.py", ("@py",)),
            CodeOwnerRule("*.go", ("@go",)),
        ]
        result = owners_for(["a.py", "b.go"], rules)
        assert result == {"@py", "@go"}

    def test_recursive_glob(self) -> None:
        rules = [CodeOwnerRule("docs/**", ("@docs",))]
        assert owners_for(["docs/sub/page.md"], rules) == {"@docs"}

    def test_directory_pattern_with_trailing_slash(self) -> None:
        rules = [CodeOwnerRule("infra/", ("@platform",))]
        assert owners_for(["infra/k8s/deploy.yaml"], rules) == {"@platform"}
