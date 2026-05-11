#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: EUPL-1.2
#
# One-shot, idempotent Freebox OS pairing helper for mipsou.freebox.
#
# Behaviour mirrors the run-once pattern of the Go ``freebox-mcp``:
#   - First run: physical pairing → token saved in the OS credential store.
#       * Windows : Credential Manager (advapi32 CRED_TYPE_GENERIC)
#       * POSIX   : ``$XDG_CONFIG_HOME/community-freebox/app_token`` (mode 0600)
#   - Subsequent runs: token reused, no physical interaction required.
#
# Stdout is reserved for the ``app_token`` so the helper composes with shell
# pipelines:
#
#     python3 scripts/pair.py | ansible-vault encrypt_string --stdin-name freebox_app_token
#
# All progress / status messages are emitted on stderr.

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import ssl
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://mafreebox.freebox.fr"
DEFAULT_API_BASE = "/api/v15"
DEFAULT_APP_ID = "community-freebox-ansible"
DEFAULT_APP_NAME = "Ansible — mipsou.freebox"
DEFAULT_APP_VERSION = "0.1.0"
DEFAULT_TARGET = "community-freebox-ansible"
DEFAULT_USER = "app"
GRANT_TIMEOUT_SECONDS = 90
POLL_INTERVAL_SECONDS = 2


def stderr(msg: str = "") -> None:
    print(msg, file=sys.stderr, flush=True)


# ── credential store ────────────────────────────────────────────────────────

class CredentialStore:
    """Persistent app_token store. Backend depends on platform."""

    def read(self):  # -> str | None
        raise NotImplementedError

    def write(self, token):
        raise NotImplementedError

    def delete(self):
        raise NotImplementedError

    def describe(self):  # -> str
        raise NotImplementedError


class FileStore(CredentialStore):
    def __init__(self, path):
        self.path = path

    def read(self):
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                value = f.read().strip()
                return value or None
        except FileNotFoundError:
            return None

    def write(self, token):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        # Open with O_CREAT|O_TRUNC and 0o600 perms in one shot — avoids the
        # brief window where another user could read a default-mode file.
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(self.path, flags, 0o600)
        try:
            os.write(fd, (token + "\n").encode("utf-8"))
        finally:
            os.close(fd)
        # Tighten perms even if umask masked the mode argument above.
        try:
            os.chmod(self.path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass

    def delete(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass

    def describe(self):
        return "file " + self.path


class WincredStore(CredentialStore):
    """Windows Credential Manager via advapi32 CRED_TYPE_GENERIC.

    Mirrors the Go ``internal/wincred`` implementation: UTF-16LE blob, local
    machine persistence, ERROR_NOT_FOUND maps to ``None``.
    """

    CRED_TYPE_GENERIC = 1
    CRED_PERSIST_LOCAL_MACHINE = 2
    ERROR_NOT_FOUND = 1168

    def __init__(self, target, user):
        import ctypes
        from ctypes import wintypes

        self._ctypes = ctypes
        self._target = target
        self._user = user

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [
                ("Flags",              wintypes.DWORD),
                ("Type",               wintypes.DWORD),
                ("TargetName",         wintypes.LPWSTR),
                ("Comment",            wintypes.LPWSTR),
                ("LastWritten",        wintypes.FILETIME),
                ("CredentialBlobSize", wintypes.DWORD),
                ("CredentialBlob",     ctypes.c_void_p),
                ("Persist",            wintypes.DWORD),
                ("AttributeCount",     wintypes.DWORD),
                ("Attributes",         ctypes.c_void_p),
                ("TargetAlias",        wintypes.LPWSTR),
                ("UserName",           wintypes.LPWSTR),
            ]

        self._CREDENTIAL = CREDENTIAL
        self._PCREDENTIAL = ctypes.POINTER(CREDENTIAL)

        self._advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        self._advapi32.CredReadW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            ctypes.POINTER(self._PCREDENTIAL),
        ]
        self._advapi32.CredReadW.restype = wintypes.BOOL
        self._advapi32.CredWriteW.argtypes = [self._PCREDENTIAL, wintypes.DWORD]
        self._advapi32.CredWriteW.restype = wintypes.BOOL
        self._advapi32.CredDeleteW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
        ]
        self._advapi32.CredDeleteW.restype = wintypes.BOOL
        self._advapi32.CredFree.argtypes = [ctypes.c_void_p]
        self._advapi32.CredFree.restype = None

    def read(self):
        ctypes = self._ctypes
        cred_ptr = self._PCREDENTIAL()
        ok = self._advapi32.CredReadW(
            self._target, self.CRED_TYPE_GENERIC, 0, ctypes.byref(cred_ptr),
        )
        if not ok:
            err = ctypes.get_last_error()
            if err == self.ERROR_NOT_FOUND:
                return None
            raise OSError(err, "CredReadW failed (target={0!r})".format(self._target))
        try:
            cred = cred_ptr.contents
            size = cred.CredentialBlobSize
            if size == 0:
                return None
            blob = ctypes.string_at(cred.CredentialBlob, size)
            return blob.decode("utf-16-le")
        finally:
            self._advapi32.CredFree(cred_ptr)

    def write(self, token):
        ctypes = self._ctypes
        blob = token.encode("utf-16-le")
        # ctypes.create_string_buffer holds blob memory alive for the call.
        blob_buf = ctypes.create_string_buffer(blob, len(blob))
        cred = self._CREDENTIAL(
            Flags=0,
            Type=self.CRED_TYPE_GENERIC,
            TargetName=self._target,
            Comment=None,
            CredentialBlobSize=len(blob),
            CredentialBlob=ctypes.cast(blob_buf, ctypes.c_void_p),
            Persist=self.CRED_PERSIST_LOCAL_MACHINE,
            AttributeCount=0,
            Attributes=None,
            TargetAlias=None,
            UserName=self._user,
        )
        ok = self._advapi32.CredWriteW(ctypes.byref(cred), 0)
        if not ok:
            err = ctypes.get_last_error()
            raise OSError(err, "CredWriteW failed (target={0!r})".format(self._target))

    def delete(self):
        ok = self._advapi32.CredDeleteW(self._target, self.CRED_TYPE_GENERIC, 0)
        if not ok:
            err = self._ctypes.get_last_error()
            if err == self.ERROR_NOT_FOUND:
                return
            raise OSError(err, "CredDeleteW failed (target={0!r})".format(self._target))

    def describe(self):
        return "Windows Credential Manager (target={0!r}, user={1!r})".format(
            self._target, self._user,
        )


def default_file_path():
    base = os.environ.get("XDG_CONFIG_HOME") \
        or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(base, "community-freebox", "app_token")


def make_store(target, user, force_file=False):
    if sys.platform == "win32" and not force_file:
        return WincredStore(target, user)
    return FileStore(default_file_path())


# ── Ansible Vault backend ────────────────────────────────────────────────────

DEFAULT_VAULT_VAR = "vault_freebox_app_token"

_TOP_LEVEL_KEY_RE_TMPL = r"^{0}\s*:"


def _vault_var_present(vault_file, var_name):
    try:
        with open(vault_file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return False
    pat = re.compile(_TOP_LEVEL_KEY_RE_TMPL.format(re.escape(var_name)), re.MULTILINE)
    return bool(pat.search(content))


def _remove_vault_var_block(content, var_name):
    """Return ``content`` with the ``var_name`` block stripped.

    A block starts at a line matching ``^{name}\\s*:`` and continues through
    any subsequent indented or blank lines until the next top-level key.
    """
    lines = content.splitlines(keepends=True)
    pat = re.compile(_TOP_LEVEL_KEY_RE_TMPL.format(re.escape(var_name)))
    out = []
    i = 0
    while i < len(lines):
        if pat.match(lines[i]):
            i += 1
            while i < len(lines):
                line = lines[i]
                if line.startswith(" ") or line.startswith("\t") or line.strip() == "":
                    i += 1
                    continue
                break
        else:
            out.append(lines[i])
            i += 1
    return "".join(out)


def _ansible_vault_encrypt_string(plaintext, var_name, password_file):
    """Return the YAML scalar produced by ``ansible-vault encrypt_string``."""
    cmd = [
        "ansible-vault", "encrypt_string",
        "--vault-password-file", password_file,
        "--stdin-name", var_name,
    ]
    try:
        result = subprocess.run(
            cmd, input=plaintext.encode("utf-8"),
            capture_output=True, check=False,
        )
    except FileNotFoundError:
        raise SystemExit(
            "pair: 'ansible-vault' not on PATH — install ansible-core or run "
            "from WSL/Linux (Windows ansible-core fails on import fcntl)."
        )
    if result.returncode != 0:
        raise SystemExit(
            "pair: ansible-vault encrypt_string failed (exit {0}): {1}".format(
                result.returncode, result.stderr.decode("utf-8", errors="replace").strip(),
            )
        )
    body = result.stdout.decode("utf-8")
    return body.rstrip("\n") + "\n"


def _write_vault_var(vault_file, var_name, plaintext, password_file, replace):
    encrypted = _ansible_vault_encrypt_string(plaintext, var_name, password_file)

    parent = os.path.dirname(vault_file)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent, exist_ok=True)

    try:
        with open(vault_file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = "---\n"

    if re.search(_TOP_LEVEL_KEY_RE_TMPL.format(re.escape(var_name)), content, re.MULTILINE):
        if not replace:
            raise SystemExit(
                "pair: variable {0!r} already present in {1} — use --force to overwrite".format(
                    var_name, vault_file,
                )
            )
        content = _remove_vault_var_block(content, var_name)

    if content and not content.endswith("\n"):
        content += "\n"
    content += encrypted

    tmp_path = vault_file + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    try:
        os.chmod(tmp_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    except OSError:
        pass
    os.replace(tmp_path, vault_file)


def _delete_vault_var(vault_file, var_name):
    try:
        with open(vault_file, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return False
    if not re.search(_TOP_LEVEL_KEY_RE_TMPL.format(re.escape(var_name)), content, re.MULTILINE):
        return False
    new_content = _remove_vault_var_block(content, var_name)
    tmp_path = vault_file + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    os.replace(tmp_path, vault_file)
    return True


# ── Freebox pairing flow ────────────────────────────────────────────────────

def _request(url, *, data, ctx):
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json"} if data else {},
    )
    try:
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        raw = exc.read() or b""
    return json.loads(raw.decode("utf-8")) if raw else {}


def authorize(base_url, app_id, app_name, app_version, device, ctx):
    body = json.dumps({
        "app_id": app_id,
        "app_name": app_name,
        "app_version": app_version,
        "device_name": device,
    }).encode("utf-8")
    env = _request(base_url + "/login/authorize/", data=body, ctx=ctx)
    if not env.get("success"):
        raise SystemExit("pair: /login/authorize/ refused: {0}".format(env.get("msg") or env))
    result = env.get("result") or {}
    token = result.get("app_token")
    track_id = result.get("track_id")
    if not token or track_id is None:
        raise SystemExit("pair: missing app_token/track_id: {0}".format(env))
    return token, int(track_id)


def wait_for_grant(base_url, track_id, ctx, deadline):
    last_status = ""
    while time.monotonic() < deadline:
        env = _request(
            "{0}/login/authorize/{1}".format(base_url, track_id),
            data=None, ctx=ctx,
        )
        if not env.get("success"):
            raise SystemExit("pair: poll refused: {0}".format(env.get("msg") or env))
        status = ((env.get("result") or {}).get("status") or "").lower()
        if status != last_status:
            stderr("  status: {0}".format(status or "(empty)"))
            last_status = status
        if status == "granted":
            return
        if status == "denied":
            raise SystemExit("pair: refused at the Freebox front panel")
        if status == "timeout":
            raise SystemExit("pair: front-panel timeout (no validation in time)")
        time.sleep(POLL_INTERVAL_SECONDS)
    raise SystemExit(
        "pair: client-side timeout after {0}s (last status: {1})".format(
            GRANT_TIMEOUT_SECONDS, last_status or "unknown",
        )
    )


# ── main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Pair the mipsou.freebox Ansible app with a Freebox "
                    "(idempotent — physical button press only on first run).",
    )
    parser.add_argument("--url", default=DEFAULT_URL,
                        help="Freebox base URL (default: %(default)s)")
    parser.add_argument("--api-base", default=DEFAULT_API_BASE,
                        help="API version prefix (default: %(default)s)")
    parser.add_argument("--app-id", default=DEFAULT_APP_ID,
                        help="Application identifier (default: %(default)s)")
    parser.add_argument("--app-name", default=DEFAULT_APP_NAME,
                        help="Display name on the Freebox screen "
                             "(default: %(default)s)")
    parser.add_argument("--app-version", default=DEFAULT_APP_VERSION,
                        help="Application version (default: %(default)s)")
    parser.add_argument("--device", default=socket.gethostname(),
                        help="Device name (default: this host's name)")
    parser.add_argument("--insecure", action="store_true",
                        help="Skip TLS verification (for https://<id>.fbxos.fr "
                             "URLs that use the Freebox private CA)")
    parser.add_argument("--target", default=DEFAULT_TARGET,
                        help="Credential store target name on Windows "
                             "(default: %(default)s)")
    parser.add_argument("--user", default=DEFAULT_USER,
                        help="Credential store username (default: %(default)s)")
    parser.add_argument("--force-file-store", action="store_true",
                        help="Bypass the Windows Credential Manager and use the "
                             "POSIX-style file store on all platforms")
    parser.add_argument("--force", action="store_true",
                        help="Re-pair even if a token is already stored "
                             "(deletes the stored token first)")
    parser.add_argument("--no-save", action="store_true",
                        help="Do not persist the new token after pairing")
    parser.add_argument("--delete", action="store_true",
                        help="Delete the stored token and exit (no pairing)")
    parser.add_argument("--from-stdin", action="store_true",
                        help="Read an existing token from stdin instead of "
                             "running the physical pairing flow (useful for "
                             "migrating a token from another store).")
    parser.add_argument("--vault-file",
                        help="Path to an Ansible Vault file. Enables the "
                             "vault output mode: the token is encrypted with "
                             "ansible-vault encrypt_string and stored as a "
                             "named variable in this file (idempotent).")
    parser.add_argument("--vault-password-file",
                        help="Path to the Ansible Vault password file. "
                             "Required with --vault-file.")
    parser.add_argument("--vault-var-name", default=DEFAULT_VAULT_VAR,
                        help="Variable name in the vault file "
                             "(default: %(default)s)")
    args = parser.parse_args()

    if args.vault_file and not args.vault_password_file:
        raise SystemExit("pair: --vault-password-file is required with --vault-file")

    if args.vault_file:
        return _vault_main(args)
    return _store_main(args)


def _read_token_from_stdin():
    raw = sys.stdin.read()
    token = (raw or "").strip()
    if not token:
        raise SystemExit("pair: --from-stdin set but stdin was empty")
    return token


def _physical_pair(args):
    base_url = args.url.rstrip("/") + args.api_base
    ctx = None
    if base_url.startswith("https"):
        ctx = ssl.create_default_context()
        if args.insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

    stderr("  URL       : {0}".format(base_url))
    stderr("  app_id    : {0}".format(args.app_id))
    stderr("  app_name  : {0}".format(args.app_name))
    stderr("  device    : {0}".format(args.device))
    stderr("")
    stderr("→ Requesting authorization …")

    token, track_id = authorize(
        base_url, args.app_id, args.app_name, args.app_version, args.device, ctx,
    )
    stderr("  track_id  : {0}".format(track_id))
    stderr("")
    stderr("*** The Freebox front panel is now blinking. ***")
    stderr("*** Press the RIGHT ARROW on the box to grant access. ***")
    stderr("*** Waiting up to {0} s … ***".format(GRANT_TIMEOUT_SECONDS))
    stderr("")

    deadline = time.monotonic() + GRANT_TIMEOUT_SECONDS
    wait_for_grant(base_url, track_id, ctx, deadline)
    stderr("")
    stderr("✔ Pairing granted.")
    return token


def _store_main(args):
    store = make_store(args.target, args.user, force_file=args.force_file_store)

    if args.delete:
        store.delete()
        stderr("✓ Deleted stored credential from {0}.".format(store.describe()))
        return 0

    # Run-once: reuse persisted token unless --force.
    if not args.force:
        existing = store.read()
        if existing:
            stderr("✓ Token already paired ({0}).".format(store.describe()))
            stderr("  Use --force to re-pair, or --delete to drop the stored token.")
            print(existing)
            return 0

    if args.force:
        store.delete()

    stderr("mipsou.freebox pairing helper")
    stderr("  store     : {0}".format(store.describe()))
    stderr("")

    try:
        if args.from_stdin:
            token = _read_token_from_stdin()
            stderr("✓ Token read from stdin (no physical pairing).")
        else:
            token = _physical_pair(args)
    except KeyboardInterrupt:
        stderr("\npair: interrupted by user — no token saved.")
        return 130

    if not args.no_save:
        try:
            store.write(token)
            stderr("✓ Token saved to {0}.".format(store.describe()))
        except OSError as exc:
            stderr("! Token NOT saved: {0}".format(exc))
            stderr("  Capture the stdout value and store it manually.")

    stderr("")
    stderr("→ Open: Freebox OS → Paramètres → Gestion des accès → Applications")
    stderr("  Uncheck every permission you do not need. v0.1 needs only:")
    stderr("    • Contrôle de la VM")
    stderr("    • Accès aux fichiers de la Freebox")
    stderr("")

    print(token)
    return 0


def _vault_main(args):
    vault_file = args.vault_file
    var_name = args.vault_var_name
    password_file = args.vault_password_file

    if args.delete:
        removed = _delete_vault_var(vault_file, var_name)
        if removed:
            stderr("✓ Removed {0!r} from {1}.".format(var_name, vault_file))
        else:
            stderr("✓ {0!r} not present in {1} (nothing to delete).".format(var_name, vault_file))
        return 0

    # Idempotent: var already there → no-op.
    if not args.force and _vault_var_present(vault_file, var_name):
        stderr("✓ {0!r} already present in {1}. Nothing to do.".format(var_name, vault_file))
        stderr("  Use --force to re-pair and overwrite the encrypted value.")
        return 0

    stderr("mipsou.freebox pairing helper (vault mode)")
    stderr("  vault file: {0}".format(vault_file))
    stderr("  password  : {0}".format(password_file))
    stderr("  variable  : {0}".format(var_name))
    stderr("")

    # Token source order: --from-stdin → local store (wincred/file) → physical pair.
    token = None
    source = None

    if args.from_stdin:
        token = _read_token_from_stdin()
        source = "stdin"

    if token is None:
        store = make_store(args.target, args.user, force_file=args.force_file_store)
        candidate = store.read()
        if candidate:
            token = candidate
            source = store.describe()

    if token is None:
        try:
            token = _physical_pair(args)
        except KeyboardInterrupt:
            stderr("\npair: interrupted by user — vault not modified.")
            return 130
        source = "physical pairing"

    stderr("→ Token source: {0}".format(source))
    stderr("→ Encrypting with ansible-vault and writing to {0} …".format(vault_file))
    _write_vault_var(vault_file, var_name, token, password_file, replace=args.force)
    stderr("✓ {0} written (encrypted) to {1}.".format(var_name, vault_file))
    stderr("")
    stderr("Reference it in your playbook with: app_token: \"{{{{ {0} }}}}\"".format(var_name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
