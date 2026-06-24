"""Tests for code_puppy.secret_store -- generic OS keyring wrapper.

Covers both platform backends:
    - ``_DirectBackend`` (Windows / Linux) -- one entry per secret
    - ``_ConsolidatedBackend`` (macOS) -- all secrets in a single JSON blob

Migration tests for downstream forks are not included here.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from code_puppy import secret_store
from code_puppy.secret_store import (
    _ConsolidatedBackend,
    _DirectBackend,
    configure_service_name,
    get_service_name,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _mock_keyring_core():
    """Shared in-memory keyring store.  Returns (fake, store) tuple."""
    store: dict[tuple[str, str], str] = {}
    fake = MagicMock()

    def _get_password(service, name):
        return store.get((service, name))

    def _set_password(service, name, value):
        store[(service, name)] = value

    def _delete_password(service, name):
        key = (service, name)
        if key not in store:
            raise Exception("not found")
        del store[key]

    fake.get_password = MagicMock(side_effect=_get_password)
    fake.set_password = MagicMock(side_effect=_set_password)
    fake.delete_password = MagicMock(side_effect=_delete_password)

    backend = MagicMock()
    backend.priority = 10
    fake.get_keyring = MagicMock(return_value=backend)
    return fake, store


@pytest.fixture
def mock_keyring(_mock_keyring_core):
    """Patch keyring + force _DirectBackend for individual-entry tests."""
    fake, store = _mock_keyring_core
    direct = _DirectBackend()
    with (
        patch.object(secret_store, "_keyring", fake),
        patch.object(secret_store, "_backend", direct),
    ):
        yield fake, store


@pytest.fixture
def mock_keyring_consolidated(_mock_keyring_core):
    """Patch keyring + use _ConsolidatedBackend."""
    fake, store = _mock_keyring_core
    consolidated = _ConsolidatedBackend()
    with (
        patch.object(secret_store, "_keyring", fake),
        patch.object(secret_store, "_backend", consolidated),
    ):
        yield fake, store, consolidated


@pytest.fixture
def broken_keyring():
    """Simulate a keyring backend that rejects every operation."""
    fake = MagicMock()
    fake.get_password = MagicMock(side_effect=OSError("locked"))
    fake.set_password = MagicMock(side_effect=OSError("denied"))
    fake.delete_password = MagicMock(side_effect=OSError("nope"))

    backend = MagicMock()
    backend.priority = 0
    fake.get_keyring = MagicMock(return_value=backend)

    direct = _DirectBackend()
    with (
        patch.object(secret_store, "_keyring", fake),
        patch.object(secret_store, "_backend", direct),
    ):
        yield fake


# ---------------------------------------------------------------------------
# configure_service_name / get_service_name
# ---------------------------------------------------------------------------


class TestConfigureServiceName:
    """Service name is configurable for enterprise/downstream namespacing."""

    def teardown_method(self):
        """Restore default after each test so we don't leak state."""
        secret_store._service_name = "code-puppy"

    def test_default_is_code_puppy(self):
        assert get_service_name() == "code-puppy"

    def test_can_override(self):
        configure_service_name("my-fork")
        assert get_service_name() == "my-fork"

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError, match="non-empty"):
            configure_service_name("")

    def test_rejects_whitespace_only(self):
        with pytest.raises(ValueError, match="non-empty"):
            configure_service_name("   ")

    def test_strips_whitespace(self):
        configure_service_name("  padded  ")
        assert get_service_name() == "padded"

    def test_backends_use_configured_name(self, mock_keyring):
        """After reconfiguring, secrets land under the new service name."""
        _, store = mock_keyring
        configure_service_name("enterprise-puppy")

        secret_store.set_secret("tok", "val")
        # Stored under the new name, NOT "code-puppy"
        assert ("enterprise-puppy", "tok") in store
        assert ("code-puppy", "tok") not in store

        assert secret_store.get_secret("tok") == "val"

    def test_consolidated_backend_uses_configured_name(
        self, mock_keyring_consolidated,
    ):
        """Consolidated vault uses the overridden service name."""
        _, store, _ = mock_keyring_consolidated
        configure_service_name("enterprise-puppy")

        secret_store.set_secret("tok", "vault-val")
        assert ("enterprise-puppy", "__vault__") in store
        assert ("code-puppy", "__vault__") not in store

        vault = json.loads(store[("enterprise-puppy", "__vault__")])
        assert vault["tok"] == "vault-val"


# ---------------------------------------------------------------------------
# keyring_available
# ---------------------------------------------------------------------------


class TestKeyringAvailable:
    def test_returns_true_with_good_backend(self, mock_keyring):
        assert secret_store.keyring_available() is True

    def test_returns_false_when_priority_zero(self, broken_keyring):
        assert secret_store.keyring_available() is False

    def test_returns_true_when_priority_missing(self):
        fake = MagicMock()
        backend = MagicMock(spec=[])  # no priority attribute
        fake.get_keyring = MagicMock(return_value=backend)
        with patch.object(secret_store, "_keyring", fake):
            assert secret_store.keyring_available() is True

    def test_returns_false_when_get_keyring_explodes(self):
        fake = MagicMock()
        fake.get_keyring = MagicMock(side_effect=RuntimeError("boom"))
        with patch.object(secret_store, "_keyring", fake):
            assert secret_store.keyring_available() is False


# ---------------------------------------------------------------------------
# DirectBackend (Windows / Linux)
# ---------------------------------------------------------------------------


class TestDirectGetSecret:
    def test_returns_value(self, mock_keyring):
        _, store = mock_keyring
        store[("code-puppy", "my_key")] = "hunter2"
        assert secret_store.get_secret("my_key") == "hunter2"

    def test_returns_none_when_missing(self, mock_keyring):
        assert secret_store.get_secret("nope") is None

    def test_strips_whitespace(self, mock_keyring):
        _, store = mock_keyring
        store[("code-puppy", "k")] = "  spaced  "
        assert secret_store.get_secret("k") == "spaced"

    def test_returns_none_for_blank_value(self, mock_keyring):
        _, store = mock_keyring
        store[("code-puppy", "k")] = "   "
        assert secret_store.get_secret("k") is None

    def test_swallows_runtime_exception(self, broken_keyring):
        assert secret_store.get_secret("any") is None


class TestDirectSetSecret:
    def test_stores_value(self, mock_keyring):
        _, store = mock_keyring
        assert secret_store.set_secret("tok", "abc123") is True
        assert store[("code-puppy", "tok")] == "abc123"

    def test_rejects_blank(self, mock_keyring):
        assert secret_store.set_secret("tok", "   ") is False

    def test_returns_false_on_runtime_failure(self, broken_keyring):
        assert secret_store.set_secret("tok", "abc") is False


class TestDirectDeleteSecret:
    def test_deletes_existing(self, mock_keyring):
        _, store = mock_keyring
        store[("code-puppy", "tok")] = "old"
        assert secret_store.delete_secret("tok") is True
        assert ("code-puppy", "tok") not in store

    def test_returns_false_on_runtime_failure(self, broken_keyring):
        assert secret_store.delete_secret("tok") is False


# ---------------------------------------------------------------------------
# ConsolidatedBackend (macOS)
# ---------------------------------------------------------------------------


class TestConsolidatedGetSecret:
    def test_reads_from_vault_blob(self, mock_keyring_consolidated):
        _, store, _ = mock_keyring_consolidated
        vault = {"my_key": "vault-value"}
        store[("code-puppy", "__vault__")] = json.dumps(vault)
        assert secret_store.get_secret("my_key") == "vault-value"

    def test_returns_none_when_key_missing(self, mock_keyring_consolidated):
        _, store, _ = mock_keyring_consolidated
        store[("code-puppy", "__vault__")] = json.dumps({"other": "val"})
        assert secret_store.get_secret("my_key") is None

    def test_returns_none_when_vault_empty(self, mock_keyring_consolidated):
        assert secret_store.get_secret("any") is None

    def test_strips_whitespace(self, mock_keyring_consolidated):
        _, store, _ = mock_keyring_consolidated
        vault = {"k": "  spaced  "}
        store[("code-puppy", "__vault__")] = json.dumps(vault)
        assert secret_store.get_secret("k") == "spaced"


class TestConsolidatedSetSecret:
    def test_stores_in_vault_blob(self, mock_keyring_consolidated):
        _, store, _ = mock_keyring_consolidated
        assert secret_store.set_secret("tok", "abc123") is True
        vault = json.loads(store[("code-puppy", "__vault__")])
        assert vault["tok"] == "abc123"

    def test_preserves_existing_keys(self, mock_keyring_consolidated):
        _, store, _ = mock_keyring_consolidated
        store[("code-puppy", "__vault__")] = json.dumps({"old": "val"})
        secret_store.set_secret("new", "val2")
        vault = json.loads(store[("code-puppy", "__vault__")])
        assert vault["old"] == "val"
        assert vault["new"] == "val2"

    def test_rejects_blank(self, mock_keyring_consolidated):
        assert secret_store.set_secret("tok", "   ") is False


class TestConsolidatedDeleteSecret:
    def test_removes_key_from_vault(self, mock_keyring_consolidated):
        _, store, _ = mock_keyring_consolidated
        store[("code-puppy", "__vault__")] = json.dumps(
            {"tok": "old", "keep": "this"}
        )
        assert secret_store.delete_secret("tok") is True
        vault = json.loads(store[("code-puppy", "__vault__")])
        assert "tok" not in vault
        assert vault["keep"] == "this"

    def test_returns_false_when_key_missing(self, mock_keyring_consolidated):
        _, store, _ = mock_keyring_consolidated
        store[("code-puppy", "__vault__")] = json.dumps({})
        assert secret_store.delete_secret("nope") is False


class TestConsolidatedEnsureMigrated:
    """The generic _ensure_migrated is a no-op; just verify it runs once."""

    def test_ensure_migrated_runs_only_once(
        self, mock_keyring_consolidated,
    ):
        _, _, backend = mock_keyring_consolidated
        assert backend._migrated is False
        secret_store.get_secret("anything")
        assert backend._migrated is True

    def test_vault_operations_work_without_migration(
        self, mock_keyring_consolidated,
    ):
        """Vault get/set work even when no migration has populated it."""
        assert secret_store.set_secret("new_key", "new_val") is True
        assert secret_store.get_secret("new_key") == "new_val"


# ---------------------------------------------------------------------------
# High-level: get_migrated_secret / set_migrated_secret / clear_migrated_secret
# ---------------------------------------------------------------------------


class TestGetMigratedSecret:
    def test_reads_from_keyring_first(self, mock_keyring):
        _, store = mock_keyring
        store[("code-puppy", "my_key")] = "kr-value"
        assert secret_store.get_migrated_secret("my_key") == "kr-value"

    def test_falls_back_to_cfg_and_migrates(self, mock_keyring):
        _, store = mock_keyring
        with patch("code_puppy.config.get_value", return_value="legacy"), \
             patch("code_puppy.config.reset_value") as mock_reset:
            result = secret_store.get_migrated_secret("my_key")

        assert result == "legacy"
        assert store[("code-puppy", "my_key")] == "legacy"
        mock_reset.assert_called_once_with("my_key")

    def test_leaves_cfg_when_backend_rejects_write(self, broken_keyring):
        with patch("code_puppy.config.get_value", return_value="fallback"), \
             patch("code_puppy.config.reset_value") as mock_reset:
            result = secret_store.get_migrated_secret("my_key")

        assert result == "fallback"
        mock_reset.assert_not_called()

    def test_returns_none_when_nothing_set(self, broken_keyring):
        with patch("code_puppy.config.get_value", return_value=None):
            assert secret_store.get_migrated_secret("my_key") is None


class TestSetMigratedSecret:
    def test_writes_to_keyring_and_scrubs_cfg(self, mock_keyring):
        _, store = mock_keyring
        with patch("code_puppy.config.reset_value") as mock_reset:
            secret_store.set_migrated_secret("my_key", "new-val")

        assert store[("code-puppy", "my_key")] == "new-val"
        mock_reset.assert_called_once_with("my_key")

    def test_falls_back_to_cfg_when_backend_rejects(self, broken_keyring):
        with patch("code_puppy.config.set_config_value") as mock_cfg:
            secret_store.set_migrated_secret("my_key", "val")

        mock_cfg.assert_called_once_with("my_key", "val")


class TestClearMigratedSecret:
    def test_removes_from_both(self, mock_keyring):
        _, store = mock_keyring
        store[("code-puppy", "my_key")] = "old"
        with patch("code_puppy.config.reset_value") as mock_reset:
            secret_store.clear_migrated_secret("my_key")

        assert ("code-puppy", "my_key") not in store
        mock_reset.assert_called_once_with("my_key")
