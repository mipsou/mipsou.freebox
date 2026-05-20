#!/usr/bin/env python3
"""List and revoke stale Freebox app pairings for app_id 'app'.
Uses the current valid token from integration_config.yml.
"""
import hashlib
import hmac
import json
import sys

try:
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import urlopen, Request, HTTPError  # type: ignore

CONFIG = "tests/integration/integration_config.yml"
FREEBOX_URL = "http://mafreebox.freebox.fr/api/v15"


def load_config():
    cfg = {}
    with open(CONFIG) as f:
        for line in f:
            if ":" in line and not line.strip().startswith("#"):
                k, _, v = line.partition(":")
                cfg[k.strip()] = v.strip().strip('"')
    return cfg


def get_json(path, session_token=None):
    req = Request(FREEBOX_URL + path)
    if session_token:
        req.add_header("X-Fbx-App-Auth", session_token)
    with urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def post_json(path, body, session_token=None):
    data = json.dumps(body).encode()
    req = Request(FREEBOX_URL + path, data=data,
                  headers={"Content-Type": "application/json"})
    if session_token:
        req.add_header("X-Fbx-App-Auth", session_token)
    try:
        with urlopen(req, timeout=10) as r:
            return r.getcode(), json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def delete_req(path, session_token):
    req = Request(FREEBOX_URL + path, method="DELETE")
    req.add_header("X-Fbx-App-Auth", session_token)
    try:
        with urlopen(req, timeout=10) as r:
            return r.getcode(), json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


cfg = load_config()
app_id = cfg["freebox_app_id"]
app_token = cfg["freebox_app_token"]

# Auth
login = get_json("/login/")
challenge = login["result"]["challenge"]
password = hmac.new(app_token.encode("ascii"), challenge.encode("ascii"), hashlib.sha1).hexdigest()
_, sess = post_json("/login/session/", {"app_id": app_id, "password": password})
session_token = sess["result"]["session_token"]
print("Authenticated. Session token: %s..." % session_token[:8])

# List authorized apps
apps_resp = get_json("/login/authorized_apps/", session_token)
apps = apps_resp.get("result", [])
print("\nAuthorized apps (%d):" % len(apps))
for a in apps:
    print("  app_id=%(app_id)s  name=%(app_name)s  comment=%(comment)s" % a)

# Revoke all except the current token
current = app_token
revoked = 0
for a in apps:
    tok = a.get("app_token", "")
    if tok == current:
        print("\n→ Keeping current token (app_id=%s)" % a["app_id"])
        continue
    aid = a.get("app_id", "")
    print("\n→ Revoking app_id=%s (%s)..." % (aid, a.get("app_name", "")))
    status, resp = delete_req("/login/authorized_apps/%s" % aid, session_token)
    if resp.get("success"):
        print("  ✓ Revoked (status %d)" % status)
        revoked += 1
    else:
        print("  ✗ Failed (status %d): %s" % (status, resp))

print("\nDone: %d revoked, 1 kept." % revoked)
