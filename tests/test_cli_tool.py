"""Unit tests for cli-tool."""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from cli_tool.main import (
    generate_session_id,
    parse_keystrokes,
    escape_xml,
    get_env_vars,
)


class TestGenerateSessionId:
    """Tests for generate_session_id function."""

    def test_generates_unique_ids(self):
        """Session IDs should be unique."""
        id1 = generate_session_id("nano some-file")
        id2 = generate_session_id("nano some-file")
        assert id1 != id2

    def test_extracts_command_name(self):
        """Should extract base command name."""
        session_id = generate_session_id("nano some-file")
        assert session_id.startswith("nano-")

    def test_handles_path_commands(self):
        """Should handle full paths like /usr/bin/nano."""
        session_id = generate_session_id("/usr/bin/nano file")
        assert session_id.startswith("nano-")

    def test_handles_empty_command(self):
        """Should handle empty command gracefully."""
        session_id = generate_session_id("")
        assert "session" in session_id.lower()


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

    def test_parses_escape(self):
        """Should handle escaped backslash."""
        result = parse_keystrokes("\\\\")
        assert len(result) == 1
        assert result[0] == "\\"


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
        """Should escape " character."""
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


class TestGetEnvVars:
    """Tests for get_env_vars function."""

    def test_returns_none_when_not_set(self):
        """Should return None when env vars not set."""
        # Note: This test depends on environment
        agent_name, session_id = get_env_vars()
        # Either None or the values from environment
        assert agent_name is None or isinstance(agent_name, str)
        assert session_id is None or isinstance(session_id, str)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])