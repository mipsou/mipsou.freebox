# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

import hashlib
import hmac
import io
import json

import pytest

from ansible_collections.mipsou.freebox.plugins.module_utils import freebox_api
from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    FreeboxAPIError,
    FreeboxAuthError,
    FreeboxClient,
    FreeboxError,
    as_list,
    decode_path,
    encode_path,
    sanitize_path,
    validate_dhcp_ip,
    validate_disk_name,
    validate_mac,
    validate_port,
    validate_rfc1918,
    validate_secureon_password,
)


# ── helpers ──────────────────────────────────────────────────────────────


class StubResponse(object):
    def __init__(self, payload):
        self._buf = io.BytesIO(payload)

    def read(self):
        return self._buf.read()

    def close(self):
        self._buf.close()


def _envelope(success=True, result=None, error_code="", msg=""):
    body = {"success": success}
    if success:
        body["result"] = result if result is not None else {}
    else:
        body["error_code"] = error_code
        body["msg"] = msg
    return json.dumps(body).encode("utf-8")


class FakeFetch(object):
    """Replacement for ``ansible.module_utils.urls.fetch_url`` capturing every call."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, module, url, method="GET", data=None, headers=None,
                 timeout=None, validate_certs=None):
        self.calls.append(dict(url=url, method=method, data=data, headers=headers or {},
                               validate_certs=validate_certs))
        if not self.responses:
            raise AssertionError("FakeFetch: no scripted response left for %s %s" % (method, url))
        status, payload = self.responses.pop(0)
        return StubResponse(payload), {"status": status, "body": payload}


class _StubModule(object):
    def __init__(self):
        self.params = {}


@pytest.fixture
def client(monkeypatch):
    cl = FreeboxClient(
        module=_StubModule(),
        url="http://mafreebox.freebox.fr",
        app_id="test-app",
        app_token="topsecret",
        api_base="/api/v15",
        timeout=5,
        validate_certs=True,
    )
    fake = FakeFetch([])
    monkeypatch.setattr(freebox_api, "fetch_url", fake)
    cl._fake = fake
    return cl


# ── path helpers ─────────────────────────────────────────────────────────


def test_encode_path_known_vector():
    # /Disque dur → L0Rpc3F1ZSBkdXI= (from Freebox SDK docs)
    assert encode_path("/Disque dur") == "L0Rpc3F1ZSBkdXI="


def test_encode_path_normalizes_leading_and_trailing_slashes():
    assert encode_path("Disque 1/VMs/") == encode_path("/Disque 1/VMs")


def test_encode_decode_roundtrip_unicode():
    p = "/Disque 1/Vidéos/résumé.mp4"
    assert decode_path(encode_path(p)) == p


def test_sanitize_path_rejects_traversal():
    with pytest.raises(ValueError):
        sanitize_path("/Disque 1/../etc/passwd")


def test_sanitize_path_rejects_empty_and_root():
    with pytest.raises(ValueError):
        sanitize_path("")
    with pytest.raises(ValueError):
        sanitize_path("/")


def test_sanitize_path_collapses_double_slashes():
    assert sanitize_path("//Disque 1//VMs/") == "/Disque 1/VMs"


# ── HMAC challenge ───────────────────────────────────────────────────────


def test_sign_matches_hmac_sha1(client):
    challenge = "thechallenge1234"
    expected = hmac.new(b"topsecret", challenge.encode("ascii"), hashlib.sha1).hexdigest()
    assert client._sign(challenge) == expected


# ── auth dance ───────────────────────────────────────────────────────────


def test_ensure_session_runs_challenge_then_opens(client):
    challenge_payload = _envelope(result={"challenge": "abc", "logged_in": False})
    session_payload = _envelope(result={"session_token": "sess-xyz", "password_salt": "s"})
    client._fake.responses = [(200, challenge_payload), (200, session_payload)]

    token = client._ensure_session()
    assert token == "sess-xyz"

    calls = client._fake.calls
    assert calls[0]["url"].endswith("/api/v15/login/")
    assert calls[0]["method"] == "GET"
    assert calls[1]["url"].endswith("/api/v15/login/session/")
    body = json.loads(calls[1]["data"].decode("utf-8"))
    assert body["app_id"] == "test-app"
    expected_pw = hmac.new(b"topsecret", b"abc", hashlib.sha1).hexdigest()
    assert body["password"] == expected_pw


def test_open_session_raises_authentication_on_invalid_token(client):
    challenge_payload = _envelope(result={"challenge": "abc"})
    error_payload = _envelope(success=False, error_code="invalid_token", msg="revoked")
    client._fake.responses = [(200, challenge_payload), (403, error_payload)]
    with pytest.raises(FreeboxAuthError):
        client._ensure_session()


# ── request / retry ─────────────────────────────────────────────────────


def _seed_login(client):
    client._fake.responses.extend([
        (200, _envelope(result={"challenge": "abc"})),
        (200, _envelope(result={"session_token": "sess-1"})),
    ])


def test_get_returns_result_field(client):
    _seed_login(client)
    client._fake.responses.append((200, _envelope(result=[{"id": 1, "name": "vm1"}])))
    out = client.get("/vm/")
    assert out == [{"id": 1, "name": "vm1"}]
    # Session header sent on the authenticated call
    last_call = client._fake.calls[-1]
    assert last_call["headers"].get("X-Fbx-App-Auth") == "sess-1"


def test_request_retries_once_on_auth_required(client):
    _seed_login(client)
    auth_err = _envelope(success=False, error_code="auth_required", msg="session expired")
    refreshed_challenge = _envelope(result={"challenge": "def"})
    refreshed_session = _envelope(result={"session_token": "sess-2"})
    success = _envelope(result={"id": 1})
    client._fake.responses.extend([
        (403, auth_err),       # first authenticated request fails
        (200, refreshed_challenge),
        (200, refreshed_session),
        (200, success),        # retry succeeds
    ])
    out = client.get("/vm/1")
    assert out == {"id": 1}
    # Two distinct session tokens used
    auth_headers = [c["headers"].get("X-Fbx-App-Auth") for c in client._fake.calls
                    if c["headers"].get("X-Fbx-App-Auth")]
    assert auth_headers[0] == "sess-1"
    assert auth_headers[-1] == "sess-2"


def test_request_raises_api_error_on_business_failure(client):
    _seed_login(client)
    client._fake.responses.append((404, _envelope(success=False, error_code="path_not_found", msg="nope")))
    with pytest.raises(FreeboxAPIError) as excinfo:
        client.get("/fs/info/", query={"path": encode_path("/Disque 1/missing")})
    assert excinfo.value.error_code == "path_not_found"


# ── high-level helpers ──────────────────────────────────────────────────


def test_path_exists_returns_dict_when_found(client):
    _seed_login(client)
    info = {"type": "file", "size": 42, "name": "vm.qcow2"}
    client._fake.responses.append((200, _envelope(result=info)))
    assert client.path_exists("/Disque 1/VMs/vm.qcow2") == info


def test_path_exists_returns_none_when_missing(client):
    _seed_login(client)
    client._fake.responses.append((404, _envelope(success=False, error_code="path_not_found", msg="")))
    assert client.path_exists("/Disque 1/missing") is None


def test_path_exists_propagates_other_errors(client):
    _seed_login(client)
    client._fake.responses.append((500, _envelope(success=False, error_code="internal", msg="boom")))
    with pytest.raises(FreeboxAPIError):
        client.path_exists("/Disque 1/x")


def test_poll_fs_task_returns_on_done(client, monkeypatch):
    monkeypatch.setattr(freebox_api.time, "sleep", lambda _: None)
    _seed_login(client)
    client._fake.responses.extend([
        (200, _envelope(result={"id": 7, "state": "running"})),
        (200, _envelope(result={"id": 7, "state": "done"})),
    ])
    task = client.poll_fs_task(7, timeout=10, interval=0)
    assert task["state"] == "done"


def test_poll_fs_task_raises_on_failed(client, monkeypatch):
    monkeypatch.setattr(freebox_api.time, "sleep", lambda _: None)
    _seed_login(client)
    client._fake.responses.append((200, _envelope(result={"id": 8, "state": "failed", "error": "perm denied"})))
    with pytest.raises(FreeboxError) as excinfo:
        client.poll_fs_task(8, timeout=10, interval=0)
    assert "perm denied" in str(excinfo.value)


def test_poll_vm_disk_task_returns_on_done(client, monkeypatch):
    monkeypatch.setattr(freebox_api.time, "sleep", lambda _: None)
    _seed_login(client)
    client._fake.responses.extend([
        (200, _envelope(result={"id": 9, "done": False})),
        (200, _envelope(result={"id": 9, "done": True, "error": False})),
    ])
    task = client.poll_vm_disk_task(9, timeout=10, interval=0)
    assert task["done"] is True


def test_poll_vm_disk_task_raises_on_error_true(client, monkeypatch):
    monkeypatch.setattr(freebox_api.time, "sleep", lambda _: None)
    _seed_login(client)
    client._fake.responses.append((200, _envelope(result={"id": 9, "done": True, "error": True})))
    with pytest.raises(FreeboxError):
        client.poll_vm_disk_task(9, timeout=10, interval=0)


# ── as_list (tolerant deserializer) ──────────────────────────────────────


@pytest.mark.parametrize("value, expected", [
    (None, []),
    ("", []),
    ({}, []),
    ([], []),
    ([1, 2], [1, 2]),
    ({"x": 1}, [{"x": 1}]),
    ("hello", ["hello"]),
    (42, [42]),
])
def test_as_list_normalises_sentinels(value, expected):
    assert as_list(value) == expected


# ── defensive validators ─────────────────────────────────────────────────


@pytest.mark.parametrize("mac, expected", [
    ("aa:bb:cc:11:22:33", "aa:bb:cc:11:22:33"),
    ("AA:BB:CC:11:22:33", "aa:bb:cc:11:22:33"),
    ("aa-bb-cc-11-22-33", "aa:bb:cc:11:22:33"),
])
def test_validate_mac_canonicalises(mac, expected):
    assert validate_mac(mac) == expected


@pytest.mark.parametrize("bad", ["", "aa:bb:cc", "zz:zz:zz:zz:zz:zz", "aabbcc112233", None, 42])
def test_validate_mac_rejects_invalid(bad):
    with pytest.raises(ValueError):
        validate_mac(bad)


def test_validate_port_accepts_bounds():
    assert validate_port(1) == 1
    assert validate_port(65535) == 65535
    assert validate_port("8080") == 8080


@pytest.mark.parametrize("bad", [0, 65536, -1, "not a number", None])
def test_validate_port_rejects_out_of_range(bad):
    with pytest.raises(ValueError):
        validate_port(bad)


@pytest.mark.parametrize("ip", ["10.0.0.5", "172.16.42.1", "192.168.1.100"])
def test_validate_rfc1918_accepts_private(ip):
    assert validate_rfc1918(ip) == ip


@pytest.mark.parametrize("bad", ["8.8.8.8", "203.0.113.5", "172.32.0.1", "not-an-ip", "::1", None])
def test_validate_rfc1918_rejects_non_private(bad):
    with pytest.raises(ValueError):
        validate_rfc1918(bad)


def test_validate_dhcp_ip_accepts_safe_range():
    assert validate_dhcp_ip("192.168.1.42") == "192.168.1.42"


@pytest.mark.parametrize("last", [0, 1, 254, 255])
def test_validate_dhcp_ip_rejects_freebox_reserved(last):
    with pytest.raises(ValueError) as excinfo:
        validate_dhcp_ip("192.168.1.%d" % last)
    assert "Freebox-reserved" in str(excinfo.value)


def test_validate_secureon_password_canonicalises():
    assert validate_secureon_password("DE-AD-BE-EF-00-01") == "de:ad:be:ef:00:01"


@pytest.mark.parametrize("bad", ["", "deadbeef", "de:ad:be:ef:00", None])
def test_validate_secureon_password_rejects_invalid(bad):
    with pytest.raises(ValueError):
        validate_secureon_password(bad)


@pytest.mark.parametrize("name", ["disk.qcow2", "ubuntu-server.raw", "MyDisk.QCOW2"])
def test_validate_disk_name_accepts(name):
    assert validate_disk_name(name) == name


@pytest.mark.parametrize("bad", [
    "",
    None,
    "../etc/passwd.qcow2",
    "sub/disk.qcow2",
    "sub\\disk.qcow2",
    "disk.img",
    "noext",
])
def test_validate_disk_name_rejects(bad):
    with pytest.raises(ValueError):
        validate_disk_name(bad)


# ── diff_and_put ─────────────────────────────────────────────────────────


def test_diff_and_put_noop_when_state_matches(client):
    _seed_login(client)
    client._fake.responses.append((200, _envelope(result={"enabled": True, "port": 8080})))
    changed, before, after = client.diff_and_put("/wifi/config/", {"enabled": True})
    assert changed is False
    assert before == after == {"enabled": True, "port": 8080}
    # Only the GET happened (plus the two login responses already consumed)
    assert sum(1 for c in client._fake.calls if c["method"] == "PUT") == 0


def test_diff_and_put_partial_body_when_full_body_false(client):
    _seed_login(client)
    client._fake.responses.extend([
        (200, _envelope(result={"enabled": False, "port": 8080, "comment": "old"})),
        (200, _envelope(result={"enabled": True, "port": 8080, "comment": "old"})),
    ])
    changed, before, after = client.diff_and_put(
        "/wifi/config/", {"enabled": True, "port": 8080}
    )
    assert changed is True
    assert before["enabled"] is False
    assert after["enabled"] is True

    put_call = next(c for c in client._fake.calls if c["method"] == "PUT")
    body = json.loads(put_call["data"].decode("utf-8"))
    # Only the changed key 'enabled' is in the PUT body
    assert body == {"enabled": True}


def test_diff_and_put_full_body_sends_merged_dict(client):
    _seed_login(client)
    client._fake.responses.extend([
        (200, _envelope(result={"name": "vm1", "memory": 1024, "vcpus": 2})),
        (200, _envelope(result={"name": "vm1", "memory": 2048, "vcpus": 2})),
    ])
    changed, _before, _after = client.diff_and_put(
        "/vm/42", {"memory": 2048}, full_body=True
    )
    assert changed is True
    put_call = next(c for c in client._fake.calls if c["method"] == "PUT")
    body = json.loads(put_call["data"].decode("utf-8"))
    # Full merged body sent — name/vcpus preserved alongside the change
    assert body == {"name": "vm1", "memory": 2048, "vcpus": 2}


def test_diff_and_put_check_mode_does_not_call_put(client):
    _seed_login(client)
    client._fake.responses.append((200, _envelope(result={"enabled": False})))
    changed, before, after = client.diff_and_put(
        "/wifi/config/", {"enabled": True}, check_mode=True
    )
    assert changed is True
    assert before == {"enabled": False}
    assert after == {"enabled": True}
    assert sum(1 for c in client._fake.calls if c["method"] == "PUT") == 0


def test_diff_and_put_falls_back_to_simulated_when_put_returns_empty(client):
    _seed_login(client)
    # PUT response with no `result` field → request() returns None → helper
    # must fall back to the locally computed merge.
    client._fake.responses.extend([
        (200, _envelope(result={"enabled": False})),
        (200, json.dumps({"success": True}).encode("utf-8")),
    ])
    changed, before, after = client.diff_and_put("/wifi/config/", {"enabled": True})
    assert changed is True
    assert after == {"enabled": True}
