#!/usr/bin/env python3
"""Manual Freebox auth test — verifies HMAC flow with the current token."""
import hashlib
import hmac
import json
import sys

try:
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import urlopen, Request, HTTPError  # type: ignore

try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

CONFIG = "tests/integration/integration_config.yml"
FREEBOX_URL = "http://mafreebox.freebox.fr/api/v6"


def load_config():
    if HAVE_YAML:
        with open(CONFIG) as f:
            return yaml.safe_load(f)
    # Fallback: manual parse
    cfg = {}
    with open(CONFIG) as f:
        for line in f:
            if ":" in line and not line.strip().startswith("#"):
                k, _, v = line.partition(":")
                cfg[k.strip()] = v.strip().strip('"')
    return cfg


def get_json(path):
    with urlopen(FREEBOX_URL + path, timeout=10) as r:
        return json.loads(r.read())


def post_json(path, body):
    data = json.dumps(body).encode()
    req = Request(FREEBOX_URL + path, data=data,
                  headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as r:
            return r.getcode(), json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


cfg = load_config()
app_id = cfg.get("freebox_app_id") or cfg.get("freebox_app_id".replace("-", "_"))
app_token = cfg.get("freebox_app_token") or cfg.get("freebox_app_token".replace("-", "_"))

print("app_id   :", app_id)
print("token_len:", len(app_token) if app_token else 0)
print("token_ok :", bool(app_token) and app_token.isascii())

# Step 1: Get challenge
login = get_json("/login/")
challenge = login["result"]["challenge"]
print("challenge:", challenge[:12] + "...")

# Step 2: HMAC-SHA1
password = hmac.new(
    app_token.encode("ascii"),
    challenge.encode("ascii"),
    hashlib.sha1,
).hexdigest()
print("hmac     :", password[:12] + "...")

# Step 3: Open session
status, resp = post_json("/login/session/", {"app_id": app_id, "password": password})
print("status   :", status)
print("success  :", resp.get("success"))
if not resp.get("success"):
    print("error    :", resp.get("error_code"), resp.get("msg"))
    sys.exit(1)
print("session_token:", resp["result"]["session_token"][:8] + "...")
print("Auth OK!")
