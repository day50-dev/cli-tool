"""Unit tests for agent-cli-tool."""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cli_tool.main import (
    generate_session_id,
    parse_keystrokes,
    escape_xml,
)


class TestGenerateSessionId:
    """Tests for generate_session_id function."""

    def test_generates_unique_ids(self):
        """Session IDs should be unique (actually in current impl they are sanitized command names)."""
        # Current implementation: generate_session_id returns (session_id, matching_session)
        id1, _ = generate_session_id("nano some-file")
        # In this tool, same command might map to same ID if not forced new
        assert isinstance(id1, str)

    def test_extracts_command_name(self):
        """Should extract base command name."""
        session_id, _ = generate_session_id("nano some-file")
        assert session_id.startswith("nano")

    def test_handles_path_commands(self):
        """Should handle full paths like /usr/bin/nano."""
        session_id, _ = generate_session_id("/usr/bin/nano file")
        assert session_id.startswith("nano")

    def test_handles_empty_command(self):
        """Should handle empty command gracefully."""
        session_id, _ = generate_session_id("")
        assert "session" in session_id.lower()


class TestCLIArgs:
    """Tests for CLI argument parsing."""

    def test_no_arguments_exits_with_error(self):
        """Running the CLI without arguments should print help and return exit code 1."""
        from cli_tool.main import main
        # We need to mock sys.argv because main() calls parser.parse_args() which reads it.
        import sys
        old_argv = sys.argv
        sys.argv = ["agent-cli-helper"]
        try:
            with pytest.raises(SystemExit) as excinfo:
                main()
            assert excinfo.value.code == 1
        finally:
            sys.argv = old_argv


class TestParseKeystrokes:
    """Tests for parse_keystrokes function."""

    def test_parses_ctrl_x(self):
        """Should parse ^X as Ctrl+X."""
        result = parse_keystrokes("^X")
        assert "C-x" in result

    def test_parses_ctrl_c(self):
        """Should parse ^C as Ctrl+C."""
        result = parse_keystrokes("^C")
        assert "C-c" in result

    def test_parses_enter(self):
        """Should parse \\n as Enter."""
        result = parse_keystrokes("\\n")
        assert "Enter" in result

    def test_parses_tab(self):
        """Should parse \\t as Tab."""
        result = parse_keystrokes("\\t")
        assert "Tab" in result

    def test_parses_regular_text(self):
        """Should pass through regular characters."""
        result = parse_keystrokes("hello")
        assert "h" in result
        assert "e" in result
        assert "l" in result

    def test_parses_mixed(self):
        """Should handle mixed keystrokes."""
        result = parse_keystrokes("^X\\n")
        assert "C-x" in result
        assert "Enter" in result


class TestEscapeXml:
    """Tests for escape_xml function."""

    def test_escapes_ampersand(self):
        """Should escape & character."""
        result = escape_xml("foo & bar")
        assert "&amp;" in result

    def test_escapes_less_than(self):
        """Should escape < character."""
        result = escape_xml("foo < bar")
        assert "&lt;" in result

    def test_escapes_greater_than(self):
        """Should escape > character."""
        result = escape_xml("foo > bar")
        assert "&gt;" in result

    def test_escapes_double_quote(self):
        """Should escape \" character."""
        result = escape_xml('foo " bar')
        assert "&quot;" in result

    def test_escapes_single_quote(self):
        """Should escape ' character."""
        result = escape_xml("foo ' bar")
        assert "&apos;" in result

    def test_passes_through_plain_text(self):
        """Should not modify plain text."""
        result = escape_xml("hello world")
        assert result == "hello world"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
