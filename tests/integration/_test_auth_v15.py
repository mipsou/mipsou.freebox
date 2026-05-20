#!/usr/bin/env python3
"""Test Freebox auth with /api/v15 exactly as the module does it."""
import hashlib
import hmac
import json
import sys

try:
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import urlopen, Request, HTTPError  # type: ignore

CONFIG = "/mnt/d/workspace/code/community.freebox/tests/integration/integration_config.yml"
BASE = "http://mafreebox.freebox.fr/api/v15"


def load_config():
    cfg = {}
    with open(CONFIG) as f:
        for line in f:
            if ":" in line and not line.strip().startswith("#"):
                k, _, v = line.partition(":")
                cfg[k.strip()] = v.strip().strip('"')
    return cfg


def get_json(path):
    with urlopen(BASE + path, timeout=10) as r:
        return r.getcode(), json.loads(r.read())


def post_json(path, body, session_token=None):
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if session_token:
        headers["X-Fbx-App-Auth"] = session_token
    req = Request(BASE + path, data=data, headers=headers)
    try:
        with urlopen(req, timeout=10) as r:
            return r.getcode(), json.loads(r.read())
    except HTTPError as e:
        body_bytes = e.read()
        print("  HTTPError body:", repr(body_bytes[:200]))
        try:
            return e.code, json.loads(body_bytes)
        except Exception:
            return e.code, {}


cfg = load_config()
app_id = cfg["freebox_app_id"]
app_token = cfg["freebox_app_token"]
print("app_id:", app_id, "token_len:", len(app_token))

# Step 1: GET /login/
s, login = get_json("/login/")
print("GET /login/ →", s, "challenge:", login["result"]["challenge"][:12] + "...")

# Step 2: HMAC-SHA1
challenge = login["result"]["challenge"]
password = hmac.new(app_token.encode("ascii"), challenge.encode("ascii"), hashlib.sha1).hexdigest()
print("HMAC password:", password[:12] + "...")

# Step 3: POST /login/session/
s, sess = post_json("/login/session/", {"app_id": app_id, "password": password})
print("POST /login/session/ →", s, "success:", sess.get("success"))
if not sess.get("success"):
    print("error:", sess.get("error_code"), sess.get("msg"))
    sys.exit(1)
session_token = sess["result"]["session_token"]
print("session_token:", session_token[:8] + "...")

# Step 4: GET /system/
s, sys_resp = get_json("/system/")
# Need auth header
req = Request(BASE + "/system/")
req.add_header("X-Fbx-App-Auth", session_token)
with urlopen(req, timeout=10) as r:
    sys_data = json.loads(r.read())
print("GET /system/ → success:", sys_data.get("success"))
if sys_data.get("success"):
    r = sys_data["result"]
    print("  firmware:", r.get("firmware_version"), "mac:", r.get("mac"))
