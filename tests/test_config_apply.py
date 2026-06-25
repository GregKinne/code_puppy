"""Tests for config_apply.py — credential routing and /set command behaviour.

Covers:
- _is_credential_key() detection heuristic
- apply_setting() routing: credential keys -> keyring, plain keys -> cfg
- Fallback behaviour when keyring is unavailable
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from code_puppy.command_line.config_apply import _is_credential_key, apply_setting


# ---------------------------------------------------------------------------
# _is_credential_key
# ---------------------------------------------------------------------------


class TestIsCredentialKey:
    """Pattern-matching helper that identifies secret keys."""

    @pytest.mark.parametrize("key", [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "CEREBRAS_API_KEY",
        "SYN_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "OPENROUTER_API_KEY",
        "ZAI_API_KEY",
        "GROQ_API_KEY",
        "FIREWORKS_API_KEY",
        "CUSTOM_PROVIDER_API_KEY",
    ])
    def test_matches_api_key_suffix(self, key):
        assert _is_credential_key(key) is True

    @pytest.mark.parametrize("key", [
        "puppy_token",
        "MY_SERVICE_TOKEN",
        "REFRESH_TOKEN",
        "ACCESS_TOKEN",
    ])
    def test_matches_token_suffix(self, key):
        assert _is_credential_key(key) is True

    @pytest.mark.parametrize("key", [
        "CLIENT_SECRET",
        "APP_SECRET",
        "WEBHOOK_SECRET",
    ])
    def test_matches_secret_suffix(self, key):
        assert _is_credential_key(key) is True

    def test_case_insensitive(self):
        assert _is_credential_key("openai_api_key") is True
        assert _is_credential_key("Anthropic_Api_Key") is True

    @pytest.mark.parametrize("key", [
        "model",
        "yolo_mode",
        "cancel_agent_key",
        "output_level",
        "enable_dbos",
        "smooth_response_stream",
        "OPENAI_ENDPOINT",
        "AZURE_OPENAI_ENDPOINT",
    ])
    def test_does_not_match_plain_config_keys(self, key):
        assert _is_credential_key(key) is False


# ---------------------------------------------------------------------------
# apply_setting — credential routing
# ---------------------------------------------------------------------------


class TestApplySettingCredentialRouting:
    """Credential keys must go through set_api_key, not set_config_value."""

    def _make_mock_agent(self):
        agent = MagicMock()
        agent.reload_code_generation_agenvalue = None
        return agent

    @pytest.mark.parametrize("key", [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "CUSTOM_API_KEY",
    ])
    def test_api_keys_routed_to_set_secret(self, key):
        with patch("code_puppy.secret_store.set_secret") as mock_set, \
             patch("code_puppy.config.set_config_value") as mock_cfg:
            result = apply_setting(key, "sk-test-value", reload_agent=False)

        assert result.ok is True
        mock_set.assert_called_once_with(key, "sk-test-value")
        mock_cfg.assert_not_called()

    def test_plain_key_routed_to_set_config_value(self):
        with patch("code_puppy.config.set_config_value") as mock_set_cfg, \
             patch("code_puppy.secret_store.set_secret") as mock_set:
            result = apply_setting("model", "gpt-4o", reload_agent=False)

        assert result.ok is True
        mock_set_cfg.assert_called_once_with("model", "gpt-4o")
        mock_set.assert_not_called()

    def test_token_routed_to_set_secret(self):
        with patch("code_puppy.secret_store.set_secret") as mock_set, \
             patch("code_puppy.config.set_config_value") as mock_cfg:
            result = apply_setting("puppy_token", "tok-abc", reload_agent=False)

        assert result.ok is True
        mock_set.assert_called_once_with("puppy_token", "tok-abc")
        mock_cfg.assert_not_called()

    def test_empty_key_returns_error(self):
        result = apply_setting("", "value", reload_agent=False)
        assert result.ok is False
        assert result.error

    def test_clearing_api_key_calls_delete_secret(self):
        """Empty value routes to delete_secret, not set_secret."""
        with patch("code_puppy.secret_store.delete_secret") as mock_clear, \
             patch("code_puppy.secret_store.set_secret") as mock_set:
            result = apply_setting("OPENAI_API_KEY", "", reload_agent=False)

        assert result.ok is True
        mock_clear.assert_called_once_with("OPENAI_API_KEY")
        mock_set.assert_not_called()


# ---------------------------------------------------------------------------
# apply_setting — end-to-end with real keyring mock
# ---------------------------------------------------------------------------


class TestApplySettingE2E:
    """Trace the full path from apply_setting down to secret_store."""

    def test_set_api_key_reaches_keyring(self, mock_config_paths):
        """Full stack: apply_setting -> set_secret -> keyring."""
        with patch("code_puppy.secret_store.keyring_set", return_value=True) as mock_kr:
            result = apply_setting("OPENAI_API_KEY", "sk-e2e-test", reload_agent=False)

        assert result.ok is True
        mock_kr.assert_called_once_with("OPENAI_API_KEY", "sk-e2e-test")

    def test_set_api_key_falls_back_to_cfg_when_keyring_fails(self, mock_config_paths):
        """When keyring rejects the write, value lands in puppy.cfg."""
        import configparser

        mock_cfg_dir, mock_cfg_file, _ = mock_config_paths
        import os
        os.makedirs(mock_cfg_dir, exist_ok=True)
        cfg = configparser.ConfigParser()
        cfg["puppy"] = {}
        with open(mock_cfg_file, "w") as f:
            cfg.write(f)

        with patch("code_puppy.secret_store.keyring_set", return_value=False):
            result = apply_setting("ANTHROPIC_API_KEY", "sk-ant-fallback", reload_agent=False)

        assert result.ok is True
        saved = configparser.ConfigParser()
        saved.read(mock_cfg_file)
        assert saved["puppy"]["ANTHROPIC_API_KEY"] == "sk-ant-fallback"

    def test_plain_key_never_touches_keyring(self, mock_config_paths):
        """Non-credential keys bypass the secret store entirely."""
        with patch("code_puppy.secret_store.keyring_set") as mock_kr, \
             patch("code_puppy.config.set_config_value"):  # avoid needing a real cfg file
            apply_setting("output_level", "high", reload_agent=False)

        mock_kr.assert_not_called()


@pytest.fixture
def mock_config_paths(monkeypatch, tmp_path):
    """Isolated puppy.cfg for E2E tests."""
    import os
    from code_puppy import config as cp_config

    mock_config_dir = str(tmp_path / ".config" / "code_puppy")
    mock_config_file = os.path.join(mock_config_dir, "puppy.cfg")
    mock_data_dir = str(tmp_path / ".local" / "share" / "code_puppy")
    mock_cache_dir = str(tmp_path / ".cache" / "code_puppy")
    mock_state_dir = str(tmp_path / ".local" / "state" / "code_puppy")

    monkeypatch.setattr(cp_config, "CONFIG_DIR", mock_config_dir)
    monkeypatch.setattr(cp_config, "CONFIG_FILE", mock_config_file)
    monkeypatch.setattr(cp_config, "DATA_DIR", mock_data_dir)
    monkeypatch.setattr(cp_config, "CACHE_DIR", mock_cache_dir)
    monkeypatch.setattr(cp_config, "STATE_DIR", mock_state_dir)

    return mock_config_dir, mock_config_file, mock_data_dir
