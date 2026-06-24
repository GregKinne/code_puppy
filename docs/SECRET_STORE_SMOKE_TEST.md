# Secret Store Manual Smoke Test

Run these prompts inside the open-source code-puppy to verify the
keyring-backed secret store works end-to-end.

## Prerequisites

```bash
cd ~/git/public_code_puppy
.venv/bin/code-puppy
/model ollama-qwen3-8b
```

## 1. Verify keyring is wired up

```
run this python command and show me the output: python3 -c "from code_puppy.secret_store import keyring_available, get_service_name; print('keyring available:', keyring_available()); print('service name:', get_service_name())"
```

**Expected:** `keyring available: True`, `service name: code-puppy`

## 2. Write a secret and read it back

```
run this python command and show me the output: python3 -c "from code_puppy.secret_store import set_secret, get_secret; set_secret('oss_test', 'hello-from-puppy'); print('stored:', get_secret('oss_test'))"
```

**Expected:** `stored: hello-from-puppy`

## 3. Verify the secret is in macOS Keychain, not in puppy.cfg

```
run these 2 commands and show me the output:
1. security find-generic-password -s "code-puppy" -a "__vault__" -w
2. grep oss_test ~/.code_puppy/puppy.cfg || echo "not in cfg - GOOD"
```

**Expected:** JSON blob containing `oss_test`, and `not in cfg - GOOD`

## 4. Test the cfg-to-keyring migration path

```
run these 3 commands in order and show me the output:
1. python3 -c "from code_puppy.config import set_config_value; set_config_value('oss_migrate', 'was-plaintext')"
2. python3 -c "from code_puppy.secret_store import get_migrated_secret; print('migrated:', get_migrated_secret('oss_migrate'))"
3. grep oss_migrate ~/.code_puppy/puppy.cfg || echo "scrubbed from cfg - GOOD"
```

**Expected:** `migrated: was-plaintext` then `scrubbed from cfg - GOOD`

## 5. Verify migrated value is in Keychain

```
run: security find-generic-password -s "code-puppy" -a "__vault__" -w
```

**Expected:** JSON blob now contains both `oss_test` and `oss_migrate`

## 6. Cleanup

```
run: python3 -c "from code_puppy.secret_store import delete_secret; delete_secret('oss_test'); delete_secret('oss_migrate'); print('cleaned up')"
```

**Expected:** `cleaned up`

## 7. Verify cleanup

```
run: security find-generic-password -s "code-puppy" -a "__vault__" -w 2>/dev/null || echo "vault empty"
```

**Expected:** JSON blob with no `oss_test` or `oss_migrate` keys (or `vault empty`)

## What this covers

| Layer | Status |
|-------|--------|
| Keyring detection | Step 1 |
| Write / read round-trip | Step 2 |
| Keychain vault storage (macOS consolidated backend) | Step 3 |
| Plaintext cfg exclusion | Step 3 |
| Legacy cfg-to-keyring auto-migration | Step 4 |
| Post-migration cfg scrubbing | Step 4 |
| Delete / cleanup | Steps 6-7 |

## Note on real-world secrets

The open-source code-puppy with a local Ollama model has no real secrets
flowing through the system. Cloud API keys (OpenAI, Anthropic, etc.)
would exercise this path naturally when a user runs `/set OPENAI_API_KEY=sk-...`,
but those require paid accounts. The `puppy_token` path is enterprise-only.

These synthetic test values prove the plumbing works identically to
how real secrets would flow.
