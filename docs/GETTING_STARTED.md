# Getting Started with Code Puppy (Open Source)

A step-by-step guide to installing and running Code Puppy from scratch.
No paid subscriptions required.

---

## Prerequisites

- **Python 3.11+** (check with `python3 --version`)
- **A terminal** (macOS Terminal, iTerm2, Windows Terminal, any Linux terminal)
- **One of:** Ollama (free, local), or an API key from any supported provider

---

## Step 1: Install UV

[UV](https://docs.astral.sh/uv/) is the recommended Python package manager.

### macOS / Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows (PowerShell as Admin)

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart your terminal after installing.

---

## Step 2: Run Code Puppy

No install step needed. UV runs it directly:

```bash
uvx code-puppy
```

On first launch, Code Puppy will ask you two things:

```
Let's get your Puppy ready!
What should we name the puppy? mack
What's your name (so Code Puppy knows its owner)? Greg
```

This creates a config at `~/.config/code_puppy/puppy.cfg` (or
`~/.code_puppy/puppy.cfg` on older setups).

---

## Step 3: Connect a Model

Code Puppy needs an AI model to work. You have three paths, all
starting from free.

### Option A: Ollama (free, runs locally, full privacy)

This keeps everything on your machine. No API keys, no cloud calls.

**1. Install Ollama:**

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Windows: download from https://ollama.com
```

**2. Pull a model:**

Code Puppy requires models with **tool/function calling** support.
Pick one based on your RAM:

| Model         | Download | RAM Needed | Quality     |
|---------------|----------|------------|-------------|
| `qwen3:1.7b`  | ~1 GB    | ~2 GB      | Basic       |
| `qwen3:4b`    | ~2 GB    | ~3 GB      | Good        |
| `qwen3:8b`    | ~5 GB    | ~6 GB      | Great       |
| `qwen3:30b`   | ~17 GB   | ~20 GB     | Excellent   |

```bash
ollama pull qwen3:4b
```

**3. Register it with Code Puppy:**

Create `~/.local/share/code_puppy/extra_models.json`
(or `~/.code_puppy/extra_models.json`):

```json
{
    "local-qwen3": {
        "type": "ollama",
        "name": "qwen3:4b",
        "context_length": 32768
    }
}
```

**4. Start Ollama, then Code Puppy:**

```bash
ollama serve &     # start the local server (if not already running)
uvx code-puppy     # launch Code Puppy
```

Inside Code Puppy, switch to your local model:

```
/model local-qwen3
```

### Option B: Ollama Cloud (free, no local RAM needed)

Ollama also offers cloud-hosted models. Your machine just streams
responses.

```bash
ollama login                 # one-time browser auth
uvx code-puppy
```

Then inside Code Puppy:

```
/ollama-setup qwen3.5
/model ollama-qwen35-cloud
```

### Option C: Cloud API Key (free tiers available)

Many providers offer free tiers. Set an environment variable and go:

**Cerebras (free tier, fast inference):**

```bash
# Sign up at https://cloud.cerebras.ai, free API key
export CEREBRAS_API_KEY="csk-your-key-here"
uvx code-puppy
```

**Google Gemini (free tier):**

```bash
# Get a key at https://aistudio.google.com/apikey
export GEMINI_API_KEY="your-key-here"
uvx code-puppy
```

**OpenAI (paid):**

```bash
export OPENAI_API_KEY="sk-your-key-here"
uvx code-puppy
```

**Anthropic (paid):**

```bash
export ANTHROPIC_API_KEY="sk-ant-your-key-here"
uvx code-puppy
```

Once inside Code Puppy, use `/model` and tab to see all available
models, or `/add_model` to browse 65+ providers interactively.

---

## Step 4: Verify It Works

Give Code Puppy a simple task:

```
create a file called hello.py that prints "woof woof"
```

It should:
1. Create the file using its built-in tools
2. Optionally run it to verify the output

If you see tool calls executing and files being created, you're good.

---

## Useful Commands

| Command           | What it does                                  |
|-------------------|-----------------------------------------------|
| `/model`          | Show current model, tab to switch             |
| `/model <name>`   | Switch to a specific model                    |
| `/add_model`      | Browse and add models from 65+ providers   |
| `/ollama-setup`   | Set up Ollama cloud models                    |
| `/agent`          | List available agents or switch agents        |
| `/help`           | Show all commands                             |
| `/session`        | Manage conversation sessions                  |
| `/truncate <N>`   | Keep only N recent messages (saves context)   |
| `/mcp`            | Manage MCP tool servers                       |
| `Ctrl+C`          | Cancel current generation                     |
| `Ctrl+D` or `/q`  | Quit                                          |

---

## Project Layout

After first run, Code Puppy creates:

```
~/.config/code_puppy/
    puppy.cfg              # name, owner, preferences
    mcp_servers.json       # MCP server configs (if any)

~/.local/share/code_puppy/
    models.json            # built-in model registry
    extra_models.json      # your custom models (Ollama, etc.)
    agents/                # custom agent definitions
    skills/                # installed skills

~/.cache/code_puppy/       # session cache, temp files
```

On macOS without XDG vars set, everything lives under `~/.code_puppy/`.

---

## Running from Source (for development)

```bash
git clone https://github.com/mpfaffenberger/code_puppy.git
cd code_puppy
uv venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"
code-puppy
```

Run tests:

```bash
python -m pytest tests/ -v
```

---

## Troubleshooting

**"No models available"**
You need at least one model configured. See Step 3 above.

**Ollama connection refused**
Make sure `ollama serve` is running. Check with `curl http://localhost:11434/v1/models`.

**"Model does not support tool calling"**
Code Puppy requires tool/function calling. Swap to a supported model
(Qwen 3, Llama 3.1+, GPT-4, Claude, Gemini).

**Python version too old**
Code Puppy requires Python 3.11+. Check with `python3 --version`.
Install a newer version via `uv python install 3.12` or your system
package manager.
