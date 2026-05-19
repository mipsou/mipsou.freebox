#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
module: wakeup
short_description: Send a Wake-on-LAN magic packet via the Freebox
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Send a Wake-on-LAN (WoL) magic packet to a given MAC address through the
    Freebox using C(POST /lan/wol/{ifname}/{mac}/).
  - This action is inherently non-idempotent. C(changed) is always C(true)
    unless C(check_mode=true).
  - In check mode the packet is not sent but C(changed=true) is still reported
    to signal that the action would have occurred.
options:
  mac:
    description:
      - Destination MAC address (colon or hyphen separated, case-insensitive).
    type: str
    required: true
  ifname:
    description:
      - Network interface name on the Freebox to use for the WoL broadcast.
    type: str
    default: pub0
  password:
    description:
      - Optional SecureOn password (6-octet hex, same format as a MAC address).
        Sent as-is; required only when the target NIC supports SecureOn.
    type: str
    no_log: true
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Wake up the NAS
  mipsou.freebox.wakeup:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    mac: "aa:bb:cc:dd:ee:ff"

- name: Wake up with SecureOn password
  mipsou.freebox.wakeup:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    mac: "aa:bb:cc:dd:ee:ff"
    password: "{{ wol_secureon }}"
    no_log: true
"""

RETURN = r"""
mac:
  description: Canonical (lowercase, colon-separated) MAC address that was targeted.
  type: str
  returned: always
ifname:
  description: Interface used for the WoL broadcast.
  type: str
  returned: always
changed:
  description: Always C(true) unless check_mode skipped the send.
  type: bool
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
    validate_mac,
    validate_secureon_password,
)


def _send_wol(client, ifname, mac, body=None):
    """POST the WoL magic packet. Returns whatever the API sends back."""
    return client.post("/lan/wol/%s/%s/" % (ifname, mac), body=body or {})


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        mac=dict(type="str", required=True),
        ifname=dict(type="str", default="pub0"),
        password=dict(type="str", no_log=True),
    ))

    module = AnsibleModule(argument_spec=argspec, supports_check_mode=True)

    try:
        mac = validate_mac(module.params["mac"])
    except ValueError as exc:
        module.fail_json(msg="invalid mac: %s" % exc)

    password_raw = module.params.get("password")
    body = {}
    if password_raw is not None:
        try:
            body["password"] = validate_secureon_password(password_raw)
        except ValueError as exc:
            module.fail_json(msg="invalid password: %s" % exc)

    ifname = module.params["ifname"]

    if module.check_mode:
        module.exit_json(changed=True, mac=mac, ifname=ifname)

    client = FreeboxClient(module)
    try:
        _send_wol(client, ifname, mac, body)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(changed=True, mac=mac, ifname=ifname)


if __name__ == "__main__":
    main()
