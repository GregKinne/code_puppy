"""OS secret storage for Code Puppy.

Platform strategy:

    **macOS** -- All secrets are consolidated into a single Keychain entry
    (a JSON blob under account ``__vault__``).  This limits the user to
    ONE Keychain password prompt on first access or after a Python binary
    upgrade, instead of one per secret.

    **Windows / Linux** -- Each secret is stored as its own credential.
    Neither platform prompts per-entry (DPAPI is transparent, GNOME
    Keyring / KWallet unlock at login), so consolidation isn't needed
    and individual entries avoid the 2,560-byte Windows Credential
    Manager limit.

Two API layers:

    **Low-level** (``get_secret`` / ``set_secret`` / ``delete_secret``)
        Pure keyring operations routed through the platform backend.

    **High-level** (``get_migrated_secret`` / ``set_migrated_secret``)
        Keyring-first with puppy.cfg fallback and transparent migration.
"""

from __future__ import annotations

import json

import keyring as _keyring

_service_name = "code-puppy"
_VAULT_ACCOUNT = "__vault__"


def get_service_name() -> str:
    """Return the current keyring service name."""
    return _service_name


def configure_service_name(name: str) -> None:
    """Override the keyring service name used for all secret operations.

    Call this early at startup -- before any get/set/delete calls -- to
    namespace secrets.  Enterprise or downstream forks typically call
    this from a plugin ``startup`` callback::

        from code_puppy.secret_store import configure_service_name
        configure_service_name("my-fork")

    The default is ``"code-puppy"``.
    """
    global _service_name
    name = str(name).strip()
    if not name:
        raise ValueError("service name must be non-empty")
    _service_name = name


def _needs_consolidated_backend() -> bool:
    """Return True when the active keyring backend prompts per-entry.

    macOS Keychain (``keyring.backends.macOS.Keyring``) prompts the
    user for *every* credential when the calling binary's adhoc
    signature changes (e.g. after a ``uv`` Python upgrade).  On this
    backend we consolidate all secrets into a single entry to limit
    prompts to one.

    All other backends (Windows DPAPI, GNOME Keyring, KWallet, etc.)
    are transparent -- no prompts, no consolidation needed.
    """
    try:
        backend = _keyring.get_keyring()
        return type(backend).__module__ == "keyring.backends.macOS"
    except Exception:
        return False


# ===================================================================
# Platform backends
# ===================================================================


class _DirectBackend:
    """One keyring entry per secret (Windows / Linux)."""

    def get(self, name: str) -> str | None:
        try:
            value = _keyring.get_password(_service_name, name)
        except Exception:
            return None
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def set(self, name: str, value: str) -> bool:
        normalized = str(value).strip()
        if not normalized:
            return False
        try:
            _keyring.set_password(_service_name, name, normalized)
        except Exception:
            return False
        return True

    def delete(self, name: str) -> bool:
        try:
            _keyring.delete_password(_service_name, name)
        except Exception:
            return False
        return True


class _ConsolidatedBackend:
    """All secrets in a single JSON blob (macOS).

    Stores a JSON dict under the configured service name, account
    ``__vault__`` so the user faces at most ONE Keychain prompt
    per Python binary change.
    """

    def __init__(self) -> None:
        self._migrated = False

    # -- vault I/O -----------------------------------------------------

    def _load_vault(self) -> dict[str, str]:
        try:
            raw = _keyring.get_password(_service_name, _VAULT_ACCOUNT)
        except Exception:
            return {}
        if not raw:
            return {}
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _save_vault(self, vault: dict[str, str]) -> bool:
        try:
            _keyring.set_password(
                _service_name, _VAULT_ACCOUNT, json.dumps(vault),
            )
        except Exception:
            return False
        return True

    # -- migration hook ------------------------------------------------

    def _ensure_migrated(self) -> None:
        """Run-once hook for legacy entry consolidation.

        In the default build this is a no-op.  Downstream forks can
        override this method or call a consolidation helper at startup
        to sweep individual entries into the vault before the first API
        call reaches this method.
        """
        if self._migrated:
            return
        self._migrated = True

    # -- public API ----------------------------------------------------

    def get(self, name: str) -> str | None:
        self._ensure_migrated()
        vault = self._load_vault()
        value = vault.get(name)
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    def set(self, name: str, value: str) -> bool:
        self._ensure_migrated()
        normalized = str(value).strip()
        if not normalized:
            return False
        vault = self._load_vault()
        vault[name] = normalized
        return self._save_vault(vault)

    def delete(self, name: str) -> bool:
        self._ensure_migrated()
        vault = self._load_vault()
        if name not in vault:
            return False
        del vault[name]
        return self._save_vault(vault)


# Select the platform backend at import time.
_backend: _DirectBackend | _ConsolidatedBackend = (
    _ConsolidatedBackend() if _needs_consolidated_backend() else _DirectBackend()
)


# ===================================================================
# Public low-level API
# ===================================================================


def keyring_available() -> bool:
    """Return True when a usable keyring backend is configured.

    A backend with ``priority <= 0`` (e.g. the fail/null backend on
    headless Linux) is treated as unavailable.
    """
    try:
        backend = _keyring.get_keyring()
    except Exception:
        return False
    priority = getattr(backend, "priority", None)
    if priority is None:
        return True
    try:
        return float(priority) > 0
    except Exception:
        return True


def get_secret(name: str) -> str | None:
    """Read a secret from the OS keyring."""
    return _backend.get(name)


def set_secret(name: str, value: str) -> bool:
    """Persist ``value`` in the OS keyring.  Returns True on success."""
    return _backend.set(name, value)


def delete_secret(name: str) -> bool:
    """Best-effort delete of a secret from the OS keyring."""
    return _backend.delete(name)


# ===================================================================
# High-level: keyring-first with puppy.cfg fallback + auto-migration
# ===================================================================


def get_migrated_secret(cfg_key: str) -> str | None:
    """Read a secret, preferring keyring with cfg fallback and auto-migration.

    1. Try keyring (fast path).
    2. Fall back to ``puppy.cfg`` via ``get_value(cfg_key)``.
    3. If found in cfg and keyring is available, migrate it to keyring and
       scrub the plaintext from cfg.

    Returns ``None`` when the secret is not stored anywhere.
    """
    kr_value = get_secret(cfg_key)
    if kr_value:
        return kr_value

    from code_puppy.config import get_value, reset_value

    cfg_value = get_value(cfg_key)
    if not cfg_value:
        return None

    # Best-effort migrate to keyring and scrub plaintext.
    if set_secret(cfg_key, cfg_value):
        try:
            reset_value(cfg_key)
        except Exception:
            pass

    return cfg_value


def set_migrated_secret(cfg_key: str, value: str) -> None:
    """Write a secret to keyring (preferred) with cfg fallback.

    On successful keyring write the cfg key is scrubbed. When the keyring
    backend rejects the write, the value is written to ``puppy.cfg``
    with ``0o600`` perms (the secure fallback path for headless / CI).
    """
    if set_secret(cfg_key, value):
        # Scrub from cfg if it was there.
        from code_puppy.config import reset_value

        try:
            reset_value(cfg_key)
        except Exception:
            pass
    else:
        from code_puppy.config import set_config_value

        set_config_value(cfg_key, value)


def clear_migrated_secret(cfg_key: str) -> None:
    """Remove a secret from both keyring and cfg."""
    delete_secret(cfg_key)
    from code_puppy.config import reset_value

    try:
        reset_value(cfg_key)
    except Exception:
        pass
