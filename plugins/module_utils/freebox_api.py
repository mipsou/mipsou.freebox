# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import base64
import hashlib
import hmac
import json
import re
import time

from ansible.module_utils.six.moves.urllib.parse import quote
from ansible.module_utils.urls import fetch_url


DEFAULT_API_BASE = "/api/v15"
DEFAULT_URL = "http://mafreebox.freebox.fr"
DEFAULT_TIMEOUT = 30
SESSION_TTL_SECONDS = 25 * 60


class FreeboxError(Exception):
    """Base class for Freebox API errors."""


class FreeboxAuthError(FreeboxError):
    """App token is invalid or has been revoked — re-pair the application."""


class FreeboxAPIError(FreeboxError):
    """The API returned success=false."""

    def __init__(self, error_code, msg):
        self.error_code = error_code or ""
        self.msg = msg or ""
        super(FreeboxAPIError, self).__init__(
            "{code}: {msg}".format(code=self.error_code or "error", msg=self.msg)
        )


COMMON_ARGSPEC = dict(
    url=dict(type="str", default=DEFAULT_URL),
    app_id=dict(type="str", required=True),
    app_token=dict(type="str", required=True, no_log=True),
    api_base=dict(type="str", default=DEFAULT_API_BASE),
    timeout=dict(type="int", default=DEFAULT_TIMEOUT),
    validate_certs=dict(type="bool", default=True),
)


def encode_path(path):
    """Encode an absolute Freebox path to standard base64 (with padding).

    The Freebox API uses RFC 4648 §4 base64 (not URL-safe). Caller is responsible
    for sanitizing the path; this helper only handles encoding.
    """
    if not path.startswith("/"):
        path = "/" + path
    path = path.rstrip("/") or "/"
    return base64.b64encode(path.encode("utf-8")).decode("ascii")


def decode_path(encoded):
    """Inverse of :func:`encode_path`."""
    try:
        return base64.b64decode(encoded.encode("ascii")).decode("utf-8")
    except Exception as exc:
        raise FreeboxError("cannot decode path %r: %s" % (encoded, exc))


def as_list(value):
    """Coerce a Freebox-OS field that may be ``None``, ``""``, ``{}``, a single
    object, or a list, into a Python list.

    The Freebox firmware returns sentinel values like ``""`` for empty
    ``BindUSBPorts`` (vm), ``{}`` for empty DHCP ``options`` (dhcpconfig), or a
    single object instead of a single-element list (``l2ident`` on lan).
    """
    if value is None or value == "" or value == {}:
        return []
    if isinstance(value, list):
        return value
    return [value]


_MAC_RE = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")


def validate_mac(mac):
    """Return canonical MAC (lowercase, colon-separated). Raises ``ValueError``."""
    if not isinstance(mac, str) or not _MAC_RE.match(mac):
        raise ValueError("invalid MAC format: %r" % (mac,))
    return mac.replace("-", ":").lower()


def validate_port(port, name="port"):
    """Ensure ``1 <= port <= 65535``. Returns int. Raises ``ValueError``."""
    try:
        n = int(port)
    except (TypeError, ValueError):
        raise ValueError("%s must be an integer, got %r" % (name, port))
    if not 1 <= n <= 65535:
        raise ValueError("%s must be in 1..65535, got %d" % (name, n))
    return n


def parse_ipv4(ip):
    """Return a 4-tuple of octets for a valid IPv4 dotted-decimal address.

    Raises ``ValueError`` for anything else (non-string, wrong segment count,
    non-numeric segment, out-of-range octet). Implemented without
    ``ipaddress`` so the module works on Python 2.7 (ansible-test sanity
    runs import tests on Python 2.7 for stable-2.16).
    """
    if not isinstance(ip, str):
        raise ValueError("ip must be a string, got %r" % (ip,))
    parts = ip.split(".")
    if len(parts) != 4:
        raise ValueError("invalid IPv4 address: %r" % (ip,))
    octets = []
    for part in parts:
        if not part.isdigit():
            raise ValueError("invalid IPv4 address: %r" % (ip,))
        value = int(part)
        if not 0 <= value <= 255:
            raise ValueError("invalid IPv4 address: %r" % (ip,))
        octets.append(value)
    return tuple(octets)


def validate_rfc1918(ip):
    """Ensure ``ip`` is a literal IPv4 in RFC1918 private space. Raises ``ValueError``."""
    octets = parse_ipv4(ip)
    a, b = octets[0], octets[1]
    in_private = (
        a == 10
        or (a == 172 and 16 <= b <= 31)
        or (a == 192 and b == 168)
    )
    if not in_private:
        raise ValueError("%s is not in RFC1918 private space" % ip)
    return ".".join(str(o) for o in octets)


def validate_dhcp_ip(ip):
    """Like :func:`validate_rfc1918` but also rejects ``.0``, ``.1``, ``.254``,
    ``.255`` (Freebox-reserved gateway / broadcast / network addresses)."""
    canonical = validate_rfc1918(ip)
    last_octet = int(canonical.rsplit(".", 1)[1])
    if last_octet in (0, 1, 254, 255):
        raise ValueError(
            "DHCP IP cannot end in .%d (Freebox-reserved); got %s"
            % (last_octet, canonical)
        )
    return canonical


def validate_secureon_password(password):
    """SecureOn WoL password is MAC-formatted (6-octet hex). Raises ``ValueError``."""
    if not isinstance(password, str) or not _MAC_RE.match(password):
        raise ValueError(
            "invalid SecureOn password (expected 6-octet hex like a MAC), got %r"
            % (password,)
        )
    return password.replace("-", ":").lower()


def validate_disk_name(name):
    """Reject path separators / traversal and require ``.qcow2`` or ``.raw`` extension."""
    if not isinstance(name, str) or not name:
        raise ValueError("disk_name must be a non-empty string")
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(
            "disk_name must not contain path separators or '..': %r" % (name,)
        )
    lower = name.lower()
    if not (lower.endswith(".qcow2") or lower.endswith(".raw")):
        raise ValueError("disk_name must end with .qcow2 or .raw (got %r)" % (name,))
    return name


def sanitize_path(path):
    """Reject path traversal. Returns the cleaned absolute path.

    Raises :class:`ValueError` on invalid input.
    """
    if path is None or path == "":
        raise ValueError("path is required")
    if "\x00" in path:
        raise ValueError("path must not contain null bytes")
    if ".." in path.split("/"):
        raise ValueError("path traversal ('..') is not allowed")
    if not path.startswith("/"):
        path = "/" + path
    while "//" in path:
        path = path.replace("//", "/")
    path = path.rstrip("/")
    if path == "":
        raise ValueError("bare root '/' is not a valid path")
    return path


class FreeboxClient(object):
    """HTTP client for the Freebox OS API with session management."""

    def __init__(self, module, url=None, app_id=None, app_token=None,
                 api_base=None, timeout=None, validate_certs=None):
        self.module = module
        params = module.params if module is not None else {}
        self.url = (url if url is not None else params.get("url", DEFAULT_URL)).rstrip("/")
        self.api_base = (api_base if api_base is not None else params.get("api_base", DEFAULT_API_BASE)).rstrip("/")
        if not self.api_base.startswith("/"):
            raise FreeboxError("api_base must start with '/' (got %r)" % self.api_base)
        self.app_id = app_id if app_id is not None else params.get("app_id")
        self.app_token = app_token if app_token is not None else params.get("app_token")
        self.timeout = timeout if timeout is not None else params.get("timeout", DEFAULT_TIMEOUT)
        self.validate_certs = validate_certs if validate_certs is not None else params.get("validate_certs", True)
        self._session_token = None
        self._session_expires = 0.0

    # ── HTTP plumbing ────────────────────────────────────────────────────

    def _full_url(self, path):
        if not path.startswith("/"):
            path = "/" + path
        return self.url + self.api_base + path

    def _fetch(self, method, full_url, body=None, content_type="application/json",
               auth_token=None):
        headers = {"Accept": "application/json"}
        data = None
        if body is not None:
            headers["Content-Type"] = content_type
            if isinstance(body, (bytes, bytearray)):
                data = bytes(body)
            elif isinstance(body, str):
                data = body.encode("utf-8")
            else:
                data = json.dumps(body).encode("utf-8")
        if auth_token:
            headers["X-Fbx-App-Auth"] = auth_token

        resp, info = fetch_url(
            self.module,
            full_url,
            method=method,
            data=data,
            headers=headers,
            timeout=self.timeout,
            validate_certs=self.validate_certs,
        )
        status = info.get("status", -1)
        # Read body — Freebox returns JSON envelope even on 4xx (e.g. 403 with error_code).
        raw = b""
        if resp is not None:
            try:
                raw = resp.read()
            finally:
                resp.close()
        elif info.get("body"):
            body_field = info["body"]
            raw = body_field.encode("utf-8") if isinstance(body_field, str) else body_field

        if status == -1:
            raise FreeboxError("HTTP request failed: %s" % info.get("msg"))

        return status, raw

    # ── Auth dance ───────────────────────────────────────────────────────

    def _get_challenge(self):
        full = self._full_url("/login/")
        status, raw = self._fetch("GET", full)
        try:
            env = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise FreeboxError("invalid JSON from /login/ (status %d)" % status)
        if not env.get("success"):
            raise FreeboxError("login endpoint returned success=false")
        result = env.get("result") or {}
        challenge = result.get("challenge")
        if not challenge:
            raise FreeboxError("no challenge in /login/ response")
        return challenge

    def _open_session(self, password):
        full = self._full_url("/login/session/")
        body = {"app_id": self.app_id, "password": password}
        status, raw = self._fetch("POST", full, body=body)
        try:
            env = json.loads(raw.decode("utf-8"))
        except ValueError:
            raise FreeboxError("invalid JSON from /login/session/ (status %d)" % status)
        if not env.get("success"):
            code = env.get("error_code", "")
            msg = env.get("msg", "")
            if code in ("invalid_token", "pending_token"):
                raise FreeboxAuthError(
                    "app_token rejected (%s) — re-pair the application: %s" % (code, msg)
                )
            raise FreeboxAPIError(code, msg)
        return (env.get("result") or {}).get("session_token", "")

    def _sign(self, challenge):
        # SHA-1 is Freebox-API-mandated (HMAC challenge)
        return hmac.new(
            self.app_token.encode("ascii"),
            challenge.encode("ascii"),
            hashlib.sha1,
        ).hexdigest()

    def _ensure_session(self):
        if self._session_token and time.time() < self._session_expires:
            return self._session_token
        challenge = self._get_challenge()
        password = self._sign(challenge)
        token = self._open_session(password)
        self._session_token = token
        self._session_expires = time.time() + SESSION_TTL_SECONDS
        return token

    def invalidate_session(self):
        self._session_token = None
        self._session_expires = 0.0

    # ── Public API ───────────────────────────────────────────────────────

    def request(self, method, path, body=None, content_type="application/json",
                query=None):
        """Authenticated request returning the decoded `result` field.

        Retries once on ``auth_required``.
        """
        url = self._full_url(path)
        if query:
            qs = "&".join(
                "%s=%s" % (quote(str(k), safe=""), quote(str(v), safe=""))
                for k, v in query.items()
            )
            url = url + ("&" if "?" in url else "?") + qs

        for attempt in range(2):
            token = self._ensure_session()
            status, raw = self._fetch(method, url, body=body,
                                      content_type=content_type, auth_token=token)
            try:
                env = json.loads(raw.decode("utf-8")) if raw else {}
            except ValueError:
                raise FreeboxError("invalid JSON (status %d): %r" % (status, raw[:200]))
            if env.get("success"):
                return env.get("result")
            code = env.get("error_code", "")
            msg = env.get("msg", "")
            if code == "auth_required" and attempt == 0:
                self.invalidate_session()
                continue
            raise FreeboxAPIError(code, msg)
        # unreachable
        raise FreeboxError("retry loop exhausted")

    def get(self, path, query=None):
        return self.request("GET", path, query=query)

    def post(self, path, body=None, content_type="application/json"):
        return self.request("POST", path, body=body, content_type=content_type)

    def put(self, path, body=None):
        return self.request("PUT", path, body=body)

    def delete(self, path):
        return self.request("DELETE", path)

    # ── High-level helpers ───────────────────────────────────────────────

    def path_exists(self, abs_path):
        """Return the FSInfo dict if ``abs_path`` exists on the Freebox NAS, else None.

        ``abs_path`` must be a cleartext absolute path; it is base64-encoded
        internally before the GET /fs/info/ call.
        """
        encoded = encode_path(abs_path)
        try:
            return self.get("/fs/info/", query={"path": encoded})
        except FreeboxAPIError as exc:
            if exc.error_code in ("path_not_found", "no_such_file", "not_found"):
                return None
            raise

    def poll_fs_task(self, task_id, timeout=120, interval=1.0):
        """Poll /fs/tasks/{id} until the task finishes. Returns the final task dict.

        Raises :class:`FreeboxError` on ``failed`` state or timeout. A
        non-existent ``task_id`` surfaces as ``FreeboxAPIError`` with
        ``error_code='invalid_id'``.
        """
        # Path shape verified live on firmware 4.9.18.1 (2026-05-11):
        # /fs/tasks/{id} and /fs/tasks/{id}/ are interchangeable, both return
        # the same JSON envelope. We use the no-slash form for parity with the
        # rest of the API.
        deadline = time.time() + timeout
        last_state = None
        while time.time() < deadline:
            task = self.get("/fs/tasks/{0}".format(task_id)) or {}
            last_state = task.get("state", "")
            if last_state == "done":
                return task
            if last_state == "failed":
                raise FreeboxError(
                    "fs task {0} failed: {1}".format(task_id, task.get("error", ""))
                )
            time.sleep(interval)
        raise FreeboxError(
            "fs task {0} timed out after {1}s (last state: {2})".format(
                task_id, timeout, last_state or "unknown"
            )
        )

    def poll_vm_disk_task(self, task_id, timeout=600, interval=1.0):
        """Poll /vm/disk/task/{id} until ``done`` flips true.

        Shape (different from FS tasks): ``done: bool``, ``error: bool``. The
        Freebox does not return a structured error message — diagnose failures
        from the synchronous POST response that created the task.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            task = self.get("/vm/disk/task/{0}".format(task_id)) or {}
            if task.get("done"):
                if task.get("error"):
                    raise FreeboxError(
                        "vm disk task {0} reported error=true (no message — see prior POST)".format(task_id)
                    )
                return task
            time.sleep(interval)
        raise FreeboxError("vm disk task {0} timed out after {1}s".format(task_id, timeout))

    def delete_vm_disk_task(self, task_id):
        """Delete a finished VM disk task. Required by Freebox FS#30666 — without this
        call, completed tasks accumulate server-side."""
        try:
            self.delete("/vm/disk/task/{0}".format(task_id))
        except FreeboxAPIError:
            # Task may already be gone — non-fatal.
            pass

    def diff_and_put(self, path, desired, full_body=False, check_mode=False):
        """Read-modify-write helper for idempotent config endpoints.

        Performs ``GET path`` and compares each key of ``desired`` against the
        current state. Returns ``(changed, before, after)`` where ``changed``
        is True iff at least one key in ``desired`` differs from the current
        value.

        - When ``full_body=True``, the PUT body is the merged ``current+desired``
          dict — required for endpoints that reject partial PUT (e.g.
          ``/vm/{id}`` returns ``invalid_request`` if any field is missing).
        - When ``full_body=False`` (default), only the changed keys are sent
          as a partial PUT.
        - When ``check_mode=True``, no PUT is issued and ``after`` is computed
          locally as ``current+desired``.

        For PUT endpoints that return an empty/None body, ``after`` falls back
        to the locally merged dict.
        """
        before = self.get(path) or {}
        changed_keys = [k for k, v in desired.items() if before.get(k) != v]
        if not changed_keys:
            return False, before, before
        after_simulated = dict(before)
        after_simulated.update(desired)
        if check_mode:
            return True, before, after_simulated
        body = after_simulated if full_body else {k: desired[k] for k in changed_keys}
        after_actual = self.put(path, body=body) or after_simulated
        return True, before, after_actual
