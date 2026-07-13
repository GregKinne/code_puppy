"""Tests for the agent-facing secret_tools plugin."""

from __future__ import annotations

from typing import Any

import pytest


class _FakeAgent:
    """Captures @agent.tool-decorated functions for direct invocation."""

    def __init__(self) -> None:
        self.registered: dict[str, Any] = {}

    def tool(self, fn):
        self.registered[fn.__name__] = fn
        return fn


@pytest.fixture
def in_memory_secret_store(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Patch secret_store calls with a tiny in-memory backend."""
    from code_puppy import secret_store

    data: dict[str, str] = {}
    monkeypatch.setattr(
        secret_store, "set_secret", lambda name, value: data.__setitem__(name, value)
    )
    monkeypatch.setattr(secret_store, "get_secret", lambda name: data.get(name))
    monkeypatch.setattr(
        secret_store, "delete_secret", lambda name: data.pop(name, None)
    )
    monkeypatch.setattr(secret_store, "keyring_available", lambda: True)
    monkeypatch.setattr(secret_store, "get_service_name", lambda: "test-service")
    return data


def _registered_tools() -> dict[str, Any]:
    from code_puppy.plugins.secret_tools import tools

    agent = _FakeAgent()
    tools.register_set_secret(agent)
    tools.register_get_secret(agent)
    tools.register_delete_secret(agent)
    tools.register_list_secrets(agent)
    return agent.registered


def test_set_get_list_delete_secret_round_trip(
    in_memory_secret_store: dict[str, str],
) -> None:
    registered = _registered_tools()

    stored = registered["set_secret"](None, "cvedetails_api_token", "secret-token")
    assert stored.stored is True
    assert stored.error is None
    assert stored.backend == "os-keyring:test-service"
    assert stored.name == "cvedetails_api_token"

    listed = registered["list_secrets"](None)
    assert listed.names == ["cvedetails_api_token"]
    assert listed.count == 1
    assert listed.error is None

    fetched = registered["get_secret"](None, "cvedetails_api_token")
    assert fetched.found is True
    assert fetched.value == "secret-token"

    deleted = registered["delete_secret"](None, "cvedetails_api_token")
    assert deleted.deleted is True
    assert deleted.error is None

    assert registered["get_secret"](None, "cvedetails_api_token").found is False
    assert registered["list_secrets"](None).names == []


def test_set_secret_rejects_blank_name(in_memory_secret_store: dict[str, str]) -> None:
    registered = _registered_tools()

    out = registered["set_secret"](None, "  ", "secret-token")

    assert out.stored is False
    assert out.error == "secret name must be non-empty"
    assert in_memory_secret_store == {}


def test_get_secret_does_not_create_index_entry(
    in_memory_secret_store: dict[str, str],
) -> None:
    registered = _registered_tools()

    out = registered["get_secret"](None, "missing")

    assert out.found is False
    assert out.value is None
    assert registered["list_secrets"](None).names == []


def test_register_tools_callback_advertises_secret_tools() -> None:
    from code_puppy.plugins.secret_tools import tools

    advertised = tools.register_tools_callback()

    assert [item["name"] for item in advertised] == [
        "set_secret",
        "get_secret",
        "delete_secret",
        "list_secrets",
    ]
    assert all(callable(item["register_func"]) for item in advertised)
