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
module: wifi_mac_filter
short_description: Manage Freebox Wi-Fi MAC address filter entries
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Create or delete a Wi-Fi MAC filter entry on the Freebox.
  - Idempotency is keyed on the canonical (lowercase, colon-separated) MAC address.
  - The active filter mode (whitelist / blacklist / disabled) is managed via
    M(mipsou.freebox.wifi_config).
options:
  mac:
    description:
      - MAC address to manage (colon or hyphen separated, case-insensitive).
      - Required when I(gather_facts=false).
    type: str
  comment:
    description:
      - Free-form label displayed in the Freebox UI.
    type: str
  state:
    description:
      - C(present) — the MAC entry must exist.
      - C(absent) — the MAC entry must not exist.
    type: str
    choices: [present, absent]
    default: present
  gather_facts:
    description:
      - When C(true), return all MAC filter entries as
        C(ansible_facts.freebox_wifi_mac_filter). I(mac) is not required.
    type: bool
    default: false
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Whitelist the workstation MAC
  mipsou.freebox.wifi_mac_filter:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    mac: "aa:bb:cc:dd:ee:ff"
    comment: workstation

- name: Remove a MAC from the filter
  mipsou.freebox.wifi_mac_filter:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    mac: "aa:bb:cc:dd:ee:ff"
    state: absent
"""

RETURN = r"""
entry:
  description: The filter entry dict (present state) or the deleted entry (absent).
  type: dict
  returned: when not gather_facts
ansible_facts:
  description: Populated when I(gather_facts=true).
  type: dict
  returned: when gather_facts=true
  contains:
    freebox_wifi_mac_filter:
      description: List of all WiFi MAC filter entry dicts.
      type: list
changed:
  description: Whether the Freebox state was modified.
  type: bool
  returned: always
"""

from ansible.module_utils.basic import AnsibleModule

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    COMMON_ARGSPEC,
    FreeboxClient,
    FreeboxError,
    validate_mac,
)


def _find_entry(client, mac):
    """Return the filter entry dict for the given canonical MAC, or None."""
    entries = client.get("/wifi/mac_filter/") or []
    for entry in entries:
        if validate_mac(entry.get("mac", "")) == mac:
            return entry
    return None


def _ensure_present(module, client, mac, comment):
    existing = _find_entry(client, mac)
    if existing is not None:
        # Entry already there — check if comment differs.
        if comment is None or existing.get("comment") == comment:
            return dict(changed=False, entry=existing)
        # Update comment via PUT.
        if module.check_mode:
            return dict(changed=True, entry=dict(existing, comment=comment))
        updated = client.put(
            "/wifi/mac_filter/%s" % existing["id"],
            body={"comment": comment},
        ) or dict(existing, comment=comment)
        return dict(changed=True, entry=updated)

    body = {"mac": mac}
    if comment is not None:
        body["comment"] = comment
    if module.check_mode:
        return dict(changed=True, entry=body)
    created = client.post("/wifi/mac_filter/", body=body) or body
    return dict(changed=True, entry=created)


def _ensure_absent(module, client, mac):
    existing = _find_entry(client, mac)
    if existing is None:
        return dict(changed=False, entry={})
    if module.check_mode:
        return dict(changed=True, entry=existing)
    client.delete("/wifi/mac_filter/%s" % existing["id"])
    return dict(changed=True, entry=existing)


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        mac=dict(type="str"),
        comment=dict(type="str"),
        state=dict(type="str", default="present", choices=["present", "absent"]),
        gather_facts=dict(type="bool", default=False),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
        required_if=[("gather_facts", False, ["mac"])],
    )

    client = FreeboxClient(module)

    if module.params.get("gather_facts"):
        try:
            entries = client.get("/wifi/mac_filter/") or []
        except FreeboxError as exc:
            module.fail_json(msg=str(exc))
        module.exit_json(changed=False, ansible_facts={"freebox_wifi_mac_filter": entries})
        return

    try:
        mac = validate_mac(module.params["mac"])
    except ValueError as exc:
        module.fail_json(msg="invalid mac: %s" % exc)

    comment = module.params.get("comment")
    state = module.params["state"]

    try:
        if state == "absent":
            result = _ensure_absent(module, client, mac)
        else:
            result = _ensure_present(module, client, mac, comment)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
