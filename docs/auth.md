# Authenticating against the Freebox API

The Freebox HTTP API uses a two-step authentication scheme:

1. **App registration** (one-shot, physical) — produces an `app_token`.
2. **Session** (per run) — exchanges the `app_token` for a short-lived
   `session_token` via an HMAC-SHA1 challenge.

This collection handles step 2 automatically inside `module_utils.freebox_api`.
You only need to perform step 1 once per controller / Freebox pair.

## 1. Register your application

The collection ships a **run-once, idempotent** pairing helper at
[`scripts/pair.py`](../scripts/pair.py). It requires only Python ≥ 3.8 (stdlib
only — no extra dependencies) and walks the official Freebox OS authorization
flow with sensible defaults.

```bash
# from a checkout of this collection
python3 scripts/pair.py

# or, once installed via ansible-galaxy
python3 ~/.ansible/collections/ansible_collections/community/freebox/scripts/pair.py
```

Status updates are emitted on stderr; the **app_token is printed on stdout**,
so the helper composes cleanly with shell pipelines:

```bash
python3 scripts/pair.py | ansible-vault encrypt_string --stdin-name freebox_app_token
```

### Run-once behaviour and credential persistence

The helper supports three persistence backends; pick whichever fits your
workflow. All three are idempotent — re-running is safe.

| Mode | Backend | When to use |
|---|---|---|
| **Vault** *(recommended for Ansible)* | An Ansible Vault file (`ansible-vault encrypt_string`) | You consume the token from a playbook and already use Ansible Vault |
| Wincred | Windows `advapi32` Credential Manager (`CRED_TYPE_GENERIC`, target `community-freebox-ansible`, user `app`) | Casual Windows-only use without a vault |
| File | Mode-`0600` file at `$XDG_CONFIG_HOME/community-freebox/app_token` (defaults to `~/.config/community-freebox/app_token`) | Casual POSIX use without a vault |

Subsequent runs detect the existing token and **skip the physical button
press entirely** — they just reprint the stored token on stdout (wincred/file
mode) or no-op (vault mode). The script is safe to call repeatedly from
automation scripts or CI bootstrap.

#### Vault mode (the integrated, idempotent flow)

The collection's recommended pattern: the token lives **encrypted, in the same
Ansible Vault file you already use for other secrets**. The playbook then
references it as any other variable.

```bash
# from a Linux/WSL host (ansible-vault is not available on Windows due to fcntl)
python3 scripts/pair.py \
    --vault-file ansible/group_vars/freebox/vault.yml \
    --vault-password-file ansible/.vault_pass \
    --vault-var-name vault_freebox_app_token
```

Behaviour:

| Situation | Outcome |
|---|---|
| Variable not yet in the vault file | Runs the pairing flow (or imports from another store / stdin), encrypts via `ansible-vault encrypt_string`, appends to the file |
| Variable already present | No-op (idempotent). Use `--force` to rotate |
| `--force` | Removes the existing block, re-pairs, writes the new encrypted scalar (neighboring vars are preserved) |
| `--delete` | Removes the variable block from the file (leaves the file with its other entries intact) |
| `--from-stdin` | Skip the physical pairing; read a plaintext token from stdin (useful for migrating an existing pairing) |

The token sourcing order in vault mode is: `--from-stdin` → local wincred/file
store → physical pairing. So a user who already ran `pair.py` once on the same
host will not re-press the box button when switching to vault storage — the
existing token is imported automatically.

The vault file is created with a leading `---` document marker if it does not
exist yet; otherwise existing entries (other vault variables, comments) are
preserved verbatim.

Reference the variable from your playbook with:

```yaml
- mipsou.freebox.vm:
    app_token: "{{ vault_freebox_app_token }}"
    ...
```

##### Migrating an existing pairing into a vault

`ansible-vault` requires `fcntl` and therefore cannot run on native Windows
Python. If you already paired on Windows (token in Credential Manager) and now
want the vault-based flow from WSL/Linux, two options:

```bash
# Option A — re-pair (one extra button press, but single-shot)
python3 scripts/pair.py --vault-file …/vault.yml --vault-password-file …/.vault_pass

# Option B — pipe the existing Windows-side token into the WSL pair.py
# Run on Windows to dump the wincred token:
py -3.13 D:\workspace\code\mipsou.freebox\scripts\pair.py
# Then on WSL/Linux:
echo 'PASTE_TOKEN_HERE' | python3 scripts/pair.py --from-stdin \
    --vault-file …/vault.yml --vault-password-file …/.vault_pass
```

#### Wincred / file mode (legacy / casual use)

Without `--vault-file`, the helper falls back to the platform-native store
described in the table above.

| Flag | Purpose |
|---|---|
| *(no flag)* | First call pairs + saves; subsequent calls reuse the stored token |
| `--force` | Drop the stored token and re-pair physically |
| `--delete` | Drop the stored token and exit (no pairing) |
| `--no-save` | Pair but do not persist the new token |
| `--target <name>` | Override the Windows Credential Manager target |
| `--force-file-store` | Use the POSIX-style file backend even on Windows |
| `--url https://<id>.fbxos.fr` | Pair through the box's public HTTPS URL (combine with `--insecure`) |
| `--insecure` | Skip TLS verification (Freebox uses a private CA on public URLs) |
| `--app-id <id>` | Register under a different identifier (default: `community-freebox-ansible`) |
| `--app-name "..."` | What appears on the Freebox screen and in the access management UI |

### First-run walkthrough

1. The Freebox front panel starts blinking and prompts you to confirm — press
   the **right arrow** on the box's screen within 90 seconds.
2. Once granted, the long-lived `app_token` is printed on stdout and saved to
   the credential store described above.
3. Open *Freebox OS → Paramètres → Gestion des accès → Applications* and
   **uncheck every permission you do not need**. The Freebox grants all scopes
   by default. The v0.1 modules of this collection need only:
   - **Contrôle de la VM**
   - **Accès aux fichiers de la Freebox**

The underlying flow is the standard Freebox OS pairing dance documented at
<https://dev.freebox.fr/sdk/os/login/> (the public doc references API v4 but
the flow is unchanged in v15).

### Alternative: existing pairings

If you already paired another tool (e.g. `freebox-pair` from
[`mcp-freebox`](https://github.com/mipsou/mcp-freebox)) and want to reuse its
token, supply that `app_token` to the modules — but you must also pass the
matching `app_id` (the Freebox identifies apps by `app_id`, not by display
name). The dedicated `community-freebox-ansible` pairing exists so Freebox OS
audit shows a clean, separable application entry.

## 2. Store the app token

Treat `app_token` like an SSH private key. Options, in order of preference:

- **Ansible Vault**:
  ```bash
  ansible-vault create group_vars/freebox.yml
  ```
  ```yaml
  freebox_app_token: !vault |
            $ANSIBLE_VAULT;1.1;AES256
            ...
  ```
- **Environment variable** (CI runners, ad-hoc playbooks):
  ```bash
  export FREEBOX_APP_TOKEN='...'
  ```
  ```yaml
  app_token: "{{ lookup('ansible.builtin.env', 'FREEBOX_APP_TOKEN') }}"
  ```
- **OS keyring** (Windows Credential Manager, macOS Keychain, libsecret):
  exfiltrate via a wrapper script, then pass into Ansible as above.

The modules in this collection mark `app_token` with `no_log=True`, so it
never appears in playbook output or fact dumps.

## 3. How the session refresh works

Every authenticated module run executes:

1. `GET /api/v15/login/` → server returns a 64-char `challenge`.
2. `password = HMAC-SHA1(app_token, challenge)` (lowercase hex).
3. `POST /api/v15/login/session/ {"app_id": ..., "password": ...}` →
   response carries a `session_token` valid ~30 minutes.
4. Every API call includes `X-Fbx-App-Auth: <session_token>`.
5. On `error_code: auth_required` (token expired), the client invalidates
   the session and retries the request once.

If the box reports `error_code: invalid_token` or `pending_token` during the
session step, the module fails immediately with
`FreeboxAuthError: app_token rejected (...) — re-pair the application`. This
typically means the user revoked the app in the Freebox UI; redo step 1.

## 4. API version

The collection targets `/api/v15` by default. The public Freebox SDK
documentation is frozen at v4, but the request/response schemas are unchanged
between v9 and v15. Override per-task if you need to point at an older path:

```yaml
- mipsou.freebox.vm:
    url: https://mafreebox.freebox.fr
    api_base: /api/v12
    ...
```

Discover the live version exposed by your box with:

```bash
curl http://mafreebox.freebox.fr/api_version
```
