#!/usr/bin/env python3
"""Probe Freebox API paths for app management endpoints."""
import hashlib
import hmac
import json
from urllib.request import urlopen, Request
from urllib.error import HTTPError

CONFIG = "/mnt/d/workspace/code/community.freebox/tests/integration/integration_config.yml"
BASE = "http://mafreebox.freebox.fr/api/v15"

cfg = {}
with open(CONFIG) as f:
    for line in f:
        if ":" in line and not line.strip().startswith("#"):
            k, _, v = line.partition(":")
            cfg[k.strip()] = v.strip().strip('"')

app_id = cfg["freebox_app_id"]
app_token = cfg["freebox_app_token"]

ch = json.loads(urlopen(BASE + "/login/", timeout=5).read())["result"]["challenge"]
pw = hmac.new(app_token.encode(), ch.encode(), hashlib.sha1).hexdigest()
data = json.dumps({"app_id": app_id, "password": pw}).encode()
req = Request(BASE + "/login/session/", data=data, headers={"Content-Type": "application/json"})
sess = json.loads(urlopen(req, timeout=5).read())["result"]["session_token"]
print("Session OK:", sess[:8] + "...")

for ver in ["v4", "v6", "v8", "v10", "v12", "v14"]:
    path = "/apps/"
    base_v = "http://mafreebox.freebox.fr/api/" + ver
    r = Request(base_v + path)
    r.add_header("X-Fbx-App-Auth", sess)
    try:
        resp = urlopen(r, timeout=5)
        body = json.loads(resp.read())
        print(ver + path, resp.getcode(), str(body)[:200])
    except HTTPError as e:
        print(ver + path, e.code)

for path in ["/apps/"]:
    r = Request(BASE + path)
    r.add_header("X-Fbx-App-Auth", sess)
    try:
        resp = urlopen(r, timeout=5)
        body = json.loads(resp.read())
        print(path, resp.getcode(), str(body)[:100])
    except HTTPError as e:
        print(path, e.code)
