"""Register agent-facing secret tools.

This plugin tells agents to persist reusable credentials through
``code_puppy.secret_store`` instead of writing plaintext secrets to files.
"""

from __future__ import annotations

from code_puppy.callbacks import register_callback

from . import tools

_SECRET_TOOL_NAMES = ("set_secret", "get_secret", "delete_secret", "list_secrets")

_SECRET_PROMPT = """

## Secret handling
When a user asks you to persist an API token, password, refresh token, or other
credential for later reuse, use the OS-backed secret tools: `set_secret`,
`get_secret`, `delete_secret`, and `list_secrets`.

Use these tools instead of writing secrets to project files, dotfiles, shell
history, logs, memory notes, or generated documentation.

Use stable, descriptive names such as `cvedetails_api_token` so the value can be
retrieved later. Retrieve secret values only for an immediate command or API
call, and do not print them back to the user.
""".rstrip()


def _on_load_prompt() -> str:
    return _SECRET_PROMPT


def _advertise_tools_to_agent(_agent_name: str | None = None) -> list[str]:
    return list(_SECRET_TOOL_NAMES)


register_callback("load_prompt", _on_load_prompt)
register_callback("register_tools", tools.register_tools_callback)
register_callback("register_agent_tools", _advertise_tools_to_agent)
