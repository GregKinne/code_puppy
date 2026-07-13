"""Agent-facing tools for storing reusable secrets.

Write and delete operations return metadata only. Secret values are returned
only by ``get_secret``, which is the explicit read operation used before a CLI
command or API call.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import RunContext

from code_puppy.secret_store import SecretStoreError

_INDEX_SECRET_NAME = "code_puppy_secret_tools_index"


class SetSecretOutput(BaseModel):
    """Store-secret result."""

    name: str
    stored: bool
    backend: str
    error: str | None = None
    warning: str | None = None


class GetSecretOutput(BaseModel):
    """Secret lookup result."""

    name: str
    found: bool
    value: str | None = None
    error: str | None = None


class DeleteSecretOutput(BaseModel):
    """Delete-secret result."""

    name: str
    deleted: bool
    error: str | None = None
    warning: str | None = None


class ListSecretsOutput(BaseModel):
    """Known secret-name listing result."""

    names: list[str] = Field(default_factory=list)
    count: int = 0
    error: str | None = None


def _secret_store():
    """Import ``secret_store`` lazily for test monkeypatching."""
    from code_puppy import secret_store

    return secret_store


def _normalize_name(name: str) -> str:
    name = str(name or "").strip()
    if not name:
        raise ValueError("secret name must be non-empty")
    return name


def _load_index() -> set[str]:
    raw = _secret_store().get_secret(_INDEX_SECRET_NAME)
    if not raw:
        return set()
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(decoded, list):
        return set()
    return {item for item in decoded if isinstance(item, str) and item}


def _save_index(names: set[str]) -> None:
    payload = json.dumps(sorted(names), separators=(",", ":"))
    _secret_store().set_secret(_INDEX_SECRET_NAME, payload)


def _index_add(name: str) -> str | None:
    try:
        names = _load_index()
        names.add(name)
        _save_index(names)
        return None
    except Exception as exc:  # noqa: BLE001 - index is best-effort metadata.
        return f"Secret stored, but updating the local name index failed: {exc}"


def _index_remove(name: str) -> str | None:
    try:
        names = _load_index()
        names.discard(name)
        if names:
            _save_index(names)
        else:
            _secret_store().delete_secret(_INDEX_SECRET_NAME)
        return None
    except Exception as exc:  # noqa: BLE001 - deletion already happened.
        return f"Secret deleted, but updating the local name index failed: {exc}"


def _backend_label() -> str:
    store = _secret_store()
    service = store.get_service_name()
    if store.keyring_available():
        return f"os-keyring:{service}"
    return f"hardened-file-fallback:{service}"


def register_set_secret(agent: Any) -> None:
    """Register the ``set_secret`` tool."""

    @agent.tool
    def set_secret(
        context: RunContext,
        name: str,
        value: str,
    ) -> SetSecretOutput:
        """Store a reusable secret in the OS-backed secret manager.

        Use this for API tokens, refresh tokens, passwords, and other
        credentials the user wants Code Puppy to persist.

        Do not write secret values to project files, shell history, logs,
        memory, or generated documentation.

        Args:
            name: Stable lookup name, such as ``cvedetails_api_token``.
            value: Secret value to store. Must be non-empty.
        """
        try:
            normalized = _normalize_name(name)
            _secret_store().set_secret(normalized, value)
            warning = _index_add(normalized)
            return SetSecretOutput(
                name=normalized,
                stored=True,
                backend=_backend_label(),
                warning=warning,
            )
        except (ValueError, SecretStoreError) as exc:
            return SetSecretOutput(
                name=name or "",
                stored=False,
                backend=_backend_label(),
                error=str(exc),
            )

    return set_secret


def register_get_secret(agent: Any) -> None:
    """Register the ``get_secret`` tool."""

    @agent.tool
    def get_secret(context: RunContext, name: str) -> GetSecretOutput:
        """Retrieve a reusable secret from the OS-backed secret manager.

        Call this only when the value is needed for an immediate action, such as
        configuring a CLI, setting an environment variable for one command, or
        calling an API. Do not echo the value back to the user.
        """
        try:
            normalized = _normalize_name(name)
            value = _secret_store().get_secret(normalized)
            return GetSecretOutput(
                name=normalized, found=value is not None, value=value
            )
        except ValueError as exc:
            return GetSecretOutput(name=name or "", found=False, error=str(exc))

    return get_secret


def register_delete_secret(agent: Any) -> None:
    """Register the ``delete_secret`` tool."""

    @agent.tool
    def delete_secret(context: RunContext, name: str) -> DeleteSecretOutput:
        """Delete a reusable secret from the OS-backed secret manager."""
        try:
            normalized = _normalize_name(name)
            _secret_store().delete_secret(normalized)
            warning = _index_remove(normalized)
            return DeleteSecretOutput(name=normalized, deleted=True, warning=warning)
        except (ValueError, SecretStoreError) as exc:
            return DeleteSecretOutput(name=name or "", deleted=False, error=str(exc))

    return delete_secret


def register_list_secrets(agent: Any) -> None:
    """Register the ``list_secrets`` tool."""

    @agent.tool
    def list_secrets(context: RunContext) -> ListSecretsOutput:
        """List reusable secret names known to Code Puppy.

        Most OS keyrings do not provide portable enumeration. This tool returns
        the best-effort name index maintained by ``set_secret`` and
        ``delete_secret``. It never returns secret values.
        """
        try:
            names = sorted(_load_index())
            return ListSecretsOutput(names=names, count=len(names))
        except Exception as exc:  # noqa: BLE001 - tool should report, not crash.
            return ListSecretsOutput(error=f"list_secrets failed: {exc}")

    return list_secrets


def register_tools_callback() -> list[dict[str, Any]]:
    """Expose secret tools to the plugin tool registry."""
    return [
        {"name": "set_secret", "register_func": register_set_secret},
        {"name": "get_secret", "register_func": register_get_secret},
        {"name": "delete_secret", "register_func": register_delete_secret},
        {"name": "list_secrets", "register_func": register_list_secrets},
    ]
