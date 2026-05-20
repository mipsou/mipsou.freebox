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
module: route
short_description: Manage Freebox static routes declaratively
version_added: "0.3.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Create or delete a static IPv4 or IPv6 route on a Freebox.
  - Idempotency key for IPv4 is C((ip, mask, gw)); for IPv6 it is
    C((ip, prefix_len, gw)).
  - The Freebox API does not expose a PUT on individual routes; updates
    are implemented as DELETE+POST.
  - I(ip_version) is auto-detected from I(ip) when not provided (presence
    of C(:) implies IPv6).
options:
  ip:
    description:
      - Destination network address.
      - Required when I(gather_facts=false).
    type: str
  mask:
    description:
      - Dotted-decimal subnet mask for IPv4 routes (e.g. C(255.255.255.0)).
      - Required when I(ip_version=4) and I(state=present).
    type: str
  prefix_len:
    description:
      - Prefix length for IPv6 routes (0..128).
      - Required when I(ip_version=6) and I(state=present).
    type: int
  gw:
    description:
      - Gateway address. Must match the address family of I(ip).
      - Required when I(state=present).
    type: str
  ip_version:
    description:
      - IP address family. Auto-detected from I(ip) when omitted.
    type: int
    choices: [4, 6]
  enabled:
    description: Whether the route is active.
    type: bool
    default: true
  state:
    description:
      - C(present) — the route must exist.
      - C(absent) — the route must not exist.
    type: str
    choices: [present, absent]
    default: present
  gather_facts:
    description:
      - When C(true), return all routes as C(ansible_facts.freebox_routes)
        (a dict with C(ipv4) and C(ipv6) lists). I(ip) is not required.
    type: bool
    default: false
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Add a static IPv4 route
  mipsou.freebox.route:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    ip: 10.20.0.0
    mask: 255.255.0.0
    gw: 192.168.1.254
    state: present

- name: Add a static IPv6 route
  mipsou.freebox.route:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    ip: "2001:db8::"
    prefix_len: 32
    gw: "fe80::1"
    state: present

- name: Remove an IPv4 route
  mipsou.freebox.route:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    ip: 10.20.0.0
    mask: 255.255.0.0
    gw: 192.168.1.254
    state: absent
"""

RETURN = r"""
ansible_facts:
  description: Populated when I(gather_facts=true).
  type: dict
  returned: when gather_facts=true
  contains:
    freebox_routes:
      description: Dict with C(ipv4) and C(ipv6) lists of route dicts.
      type: dict
route:
  description: Final state of the route, or the previous state when I(state=absent).
  type: dict
  returned: when not gather_facts
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
    parse_ipv4,
)


def _detect_ip_version(ip):
    """Return 4 or 6 based on presence of ':' in ip."""
    return 6 if ":" in ip else 4


def _validate_ipv4(ip, name):
    """Validate a dotted-decimal IPv4 address. Returns the string unchanged."""
    try:
        parse_ipv4(ip)
    except ValueError as exc:
        raise ValueError("%s: %s" % (name, exc))
    return ip


def _validate_ipv6(ip, name):
    """Basic IPv6 validation: must be a non-empty string containing ':'."""
    if not isinstance(ip, str) or ":" not in ip or ip.count(":") < 2:
        raise ValueError("%s: not a valid IPv6 address: %r" % (name, ip))
    return ip


def _api_path(ip_version):
    return "/ipv4/route/" if ip_version == 4 else "/ipv6/route/"


def _identity(route, ip_version):
    """Return the canonical identity tuple for a route dict."""
    if ip_version == 4:
        return (route.get("ip"), route.get("mask"), route.get("gw"))
    return (route.get("ip"), route.get("prefix_len"), route.get("gw"))


def _find_route(client, ip_version, identity):
    routes = client.get(_api_path(ip_version)) or []
    for route in routes:
        if _identity(route, ip_version) == identity:
            return route
    return None


def _ensure_present(module, client, ip_version, identity, body):
    existing = _find_route(client, ip_version, identity)
    if existing is not None:
        # Check if enabled flag differs.
        desired_enabled = body.get("enabled", True)
        if existing.get("enabled") == desired_enabled:
            return dict(changed=False, route=existing)
        if module.check_mode:
            simulated = dict(existing)
            simulated["enabled"] = desired_enabled
            return dict(changed=True, route=simulated)
        # No PUT on routes — DELETE+POST.
        _delete_route(client, ip_version, existing)

    if module.check_mode:
        return dict(changed=True, route=body)
    created = client.post(_api_path(ip_version), body=body) or body
    return dict(changed=True, route=created)


def _delete_route(client, ip_version, existing):
    route_id = existing.get("id")
    if route_id is not None:
        client.delete("{0}{1}".format(_api_path(ip_version), route_id))


def _ensure_absent(module, client, ip_version, identity):
    existing = _find_route(client, ip_version, identity)
    if existing is None:
        return dict(changed=False, route={})
    if module.check_mode:
        return dict(changed=True, route=existing)
    _delete_route(client, ip_version, existing)
    return dict(changed=True, route=existing)


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        ip=dict(type="str"),
        mask=dict(type="str"),
        prefix_len=dict(type="int"),
        gw=dict(type="str"),
        ip_version=dict(type="int", choices=[4, 6]),
        enabled=dict(type="bool", default=True),
        state=dict(type="str", default="present", choices=["present", "absent"]),
        gather_facts=dict(type="bool", default=False),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
        required_if=[("gather_facts", False, ["ip"])],
    )

    if module.params.get("gather_facts"):
        client = FreeboxClient(module)
        try:
            routes = {
                "ipv4": client.get("/routing/ipv4/route/") or [],
                "ipv6": client.get("/routing/ipv6/route/") or [],
            }
        except FreeboxError as exc:
            module.fail_json(msg=str(exc))
        module.exit_json(changed=False, ansible_facts={"freebox_routes": routes})
        return

    ip = module.params["ip"]
    ip_version = module.params.get("ip_version") or _detect_ip_version(ip)
    state = module.params["state"]

    # Validate ip and gw per address family.
    try:
        if ip_version == 4:
            _validate_ipv4(ip, "ip")
        else:
            _validate_ipv6(ip, "ip")
    except ValueError as exc:
        module.fail_json(msg=str(exc))

    gw = module.params.get("gw")
    if state == "present" and gw is None:
        module.fail_json(msg="gw is required when state=present")
    if gw is not None:
        try:
            if ip_version == 4:
                _validate_ipv4(gw, "gw")
            else:
                _validate_ipv6(gw, "gw")
        except ValueError as exc:
            module.fail_json(msg=str(exc))

    # Build identity tuple and request body.
    if ip_version == 4:
        mask = module.params.get("mask")
        if state == "present" and mask is None:
            module.fail_json(msg="mask is required for IPv4 routes when state=present")
        if mask is not None:
            try:
                _validate_ipv4(mask, "mask")
            except ValueError as exc:
                module.fail_json(msg=str(exc))
        identity = (ip, mask, gw)
        body = {"ip": ip, "mask": mask, "gw": gw, "enabled": module.params["enabled"]}
    else:
        prefix_len = module.params.get("prefix_len")
        if state == "present" and prefix_len is None:
            module.fail_json(msg="prefix_len is required for IPv6 routes when state=present")
        if prefix_len is not None and not (0 <= prefix_len <= 128):
            module.fail_json(msg="prefix_len must be in 0..128, got %d" % prefix_len)
        identity = (ip, prefix_len, gw)
        body = {"ip": ip, "prefix_len": prefix_len, "gw": gw, "enabled": module.params["enabled"]}

    client = FreeboxClient(module)
    try:
        if state == "absent":
            result = _ensure_absent(module, client, ip_version, identity)
        else:
            result = _ensure_present(module, client, ip_version, identity, body)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
