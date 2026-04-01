"""Tests for secrets.py."""

from pathlib import Path
from unittest.mock import patch

import pytest

from drag_events import secrets


def test_get_anthropic_api_key_prefers_environment_variable():
    env = {
        "ANTHROPIC_API_KEY": "sk-env-key",
        "ANTHROPIC_API_KEY_FILE": "/tmp/unused",
    }

    assert secrets.get_anthropic_api_key(env) == "sk-env-key"


def test_get_anthropic_api_key_reads_injected_secret_file(tmp_path):
    secret_file = tmp_path / "anthropic.txt"
    secret_file.write_text("sk-file-key\n")

    env = {"ANTHROPIC_API_KEY_FILE": str(secret_file)}

    assert secrets.get_anthropic_api_key(env) == "sk-file-key"


def test_get_anthropic_api_key_reads_project_dotenv_when_other_sources_absent(tmp_path):
    project_dotenv = tmp_path / ".env"
    project_dotenv.write_text("ANTHROPIC_API_KEY=sk-project-key\n")

    with patch("drag_events.secrets.PROJECT_SECRET_FILE", project_dotenv):
        assert secrets.get_anthropic_api_key({}) == "sk-project-key"


def test_get_anthropic_api_key_prefers_explicit_secret_file_over_project_dotenv(tmp_path):
    explicit_secret = tmp_path / "anthropic.txt"
    explicit_secret.write_text("sk-file-key\n")
    project_dotenv = tmp_path / ".env"
    project_dotenv.write_text("ANTHROPIC_API_KEY=sk-project-key\n")

    with patch("drag_events.secrets.PROJECT_SECRET_FILE", project_dotenv):
        assert secrets.get_anthropic_api_key({"ANTHROPIC_API_KEY_FILE": str(explicit_secret)}) == "sk-file-key"


def test_get_anthropic_api_key_raises_for_missing_secret(tmp_path):
    with patch("drag_events.secrets.PROJECT_SECRET_FILE", tmp_path / ".missing-env"):
        with pytest.raises(secrets.SecretConfigurationError, match="define ANTHROPIC_API_KEY"):
            secrets.get_anthropic_api_key({})


def test_get_anthropic_api_key_raises_for_missing_secret_file(tmp_path):
    missing = tmp_path / "missing.txt"

    with pytest.raises(secrets.SecretConfigurationError, match="does not exist"):
        secrets.get_anthropic_api_key({"ANTHROPIC_API_KEY_FILE": str(missing)})


def test_get_anthropic_api_key_raises_for_empty_secret_file(tmp_path):
    secret_file = tmp_path / "empty.txt"
    secret_file.write_text(" \n")

    with pytest.raises(secrets.SecretConfigurationError, match="is empty"):
        secrets.get_anthropic_api_key({"ANTHROPIC_API_KEY_FILE": str(secret_file)})


def test_read_project_dotenv_key_strips_quotes(tmp_path):
    project_dotenv = tmp_path / ".env"
    project_dotenv.write_text('ANTHROPIC_API_KEY="sk-quoted-key"\n')

    assert secrets._read_project_dotenv_key(project_dotenv, "ANTHROPIC_API_KEY") == "sk-quoted-key"


def test_read_project_dotenv_key_raises_for_missing_file(tmp_path):
    missing = tmp_path / ".env"

    with pytest.raises(secrets.SecretConfigurationError, match="does not exist"):
        secrets._read_project_dotenv_key(missing, "ANTHROPIC_API_KEY")


def test_read_project_dotenv_key_raises_for_missing_key(tmp_path):
    project_dotenv = tmp_path / ".env"
    project_dotenv.write_text("OTHER_KEY=value\n")

    with pytest.raises(secrets.SecretConfigurationError, match="does not define"):
        secrets._read_project_dotenv_key(project_dotenv, "ANTHROPIC_API_KEY")


def test_read_project_dotenv_key_raises_for_empty_value(tmp_path):
    project_dotenv = tmp_path / ".env"
    project_dotenv.write_text("ANTHROPIC_API_KEY=\n")

    with pytest.raises(secrets.SecretConfigurationError, match="is empty"):
        secrets._read_project_dotenv_key(project_dotenv, "ANTHROPIC_API_KEY")


def test_get_anthropic_client_builds_client_with_resolved_key():
    secrets.get_anthropic_client.cache_clear()
    mock_client = object()

    with patch("drag_events.secrets.get_anthropic_api_key", return_value="sk-test-key"), \
         patch("drag_events.secrets.anthropic.Anthropic", return_value=mock_client) as mock_factory:
        result = secrets.get_anthropic_client()

    assert result is mock_client
    mock_factory.assert_called_once_with(api_key="sk-test-key")
    secrets.get_anthropic_client.cache_clear()


def test_get_anthropic_client_caches_result():
    secrets.get_anthropic_client.cache_clear()
    mock_client = object()

    with patch("drag_events.secrets.get_anthropic_api_key", return_value="sk-test-key"), \
         patch("drag_events.secrets.anthropic.Anthropic", return_value=mock_client) as mock_factory:
        first = secrets.get_anthropic_client()
        second = secrets.get_anthropic_client()

    assert first is second
    assert first is mock_client
    mock_factory.assert_called_once_with(api_key="sk-test-key")
    secrets.get_anthropic_client.cache_clear()
