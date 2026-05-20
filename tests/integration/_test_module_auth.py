#!/usr/bin/env python3
"""
Minimal Ansible module that tests Freebox auth using raw urllib vs fetch_url.
Run: ansible localhost -m mipsou.freebox._test_module_auth -a "url=... app_id=... app_token=..." -v
"""
from __future__ import absolute_import, division, print_function
__metaclass__ = type

import hashlib
import hmac
import json

from ansible.module_utils.basic import AnsibleModule
from ansible.module_utils.urls import fetch_url

try:
    from urllib.request import urlopen, Request
    from urllib.error import HTTPError
except ImportError:
    from urllib2 import urlopen, Request, HTTPError  # type: ignore

DOCUMENTATION = r"""---
module: _test_module_auth
short_description: Test Freebox auth methods
"""


def auth_raw_urllib(url, app_id, app_token):
    """Auth using raw urllib (no Ansible)."""
    base = url.rstrip("/") + "/api/v15"
    with urlopen(base + "/login/", timeout=10) as r:
        login = json.loads(r.read())
    challenge = login["result"]["challenge"]
    password = hmac.new(app_token.encode("ascii"), challenge.encode("ascii"), hashlib.sha1).hexdigest()
    body = json.dumps({"app_id": app_id, "password": password}).encode("utf-8")
    req = Request(base + "/login/session/", data=body, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as r:
            sess = json.loads(r.read())
        return {"method": "raw_urllib", "success": sess.get("success"), "error": None, "challenge": challenge, "pwd_prefix": password[:8]}
    except HTTPError as e:
        sess = json.loads(e.read())
        return {"method": "raw_urllib", "success": False, "error": sess.get("error_code"), "challenge": challenge, "pwd_prefix": password[:8]}


def auth_fetch_url(module, url, app_id, app_token):
    """Auth using fetch_url (Ansible module context)."""
    base = url.rstrip("/") + "/api/v15"

    # Step 1: GET /login/
    resp, info = fetch_url(module, base + "/login/", method="GET", timeout=10)
    raw = b""
    if resp is not None:
        raw = resp.read()
        resp.close()
    if not raw and info.get("body"):
        body_field = info["body"]
        raw = body_field.encode("utf-8") if isinstance(body_field, str) else body_field
    login = json.loads(raw.decode("utf-8"))
    challenge = login["result"]["challenge"]

    # Step 2: HMAC
    password = hmac.new(app_token.encode("ascii"), challenge.encode("ascii"), hashlib.sha1).hexdigest()

    # Step 3: POST /login/session/
    post_body = json.dumps({"app_id": app_id, "password": password}).encode("utf-8")
    resp, info = fetch_url(
        module,
        base + "/login/session/",
        method="POST",
        data=post_body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=10,
    )
    raw = b""
    if resp is not None:
        raw = resp.read()
        resp.close()
    if not raw and info.get("body"):
        body_field = info["body"]
        raw = body_field.encode("utf-8") if isinstance(body_field, str) else body_field
    sess = json.loads(raw.decode("utf-8"))
    return {
        "method": "fetch_url",
        "success": sess.get("success"),
        "error": sess.get("error_code"),
        "challenge": challenge,
        "pwd_prefix": password[:8],
        "info_url": info.get("url", ""),
        "status": info.get("status"),
    }


def main():
    module = AnsibleModule(
        argument_spec=dict(
            url=dict(type="str", default="http://mafreebox.freebox.fr"),
            app_id=dict(type="str", required=True),
            app_token=dict(type="str", required=True, no_log=True),
        )
    )

    url = module.params["url"]
    app_id = module.params["app_id"]
    app_token = module.params["app_token"]

    result_raw = auth_raw_urllib(url, app_id, app_token)
    result_fetch = auth_fetch_url(module, url, app_id, app_token)

    module.exit_json(
        changed=False,
        raw_urllib=result_raw,
        fetch_url=result_fetch,
    )


if __name__ == "__main__":
    main()
