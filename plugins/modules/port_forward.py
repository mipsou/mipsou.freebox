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
module: port_forward
short_description: Manage Freebox port-forwarding (NAT) rules declaratively
version_added: "0.2.0"
extends_documentation_fragment:
  - mipsou.freebox.main
description:
  - Create, update or delete a port-forwarding rule on a Freebox.
  - Idempotency is keyed on the composite tuple
    C((ip_proto, wan_port_start, wan_port_end, src_ip)) since the Freebox API
    assigns the C(id) server-side. The Freebox API exposes a partial PUT on
    C(/fw/redir/{id}), so updates do not require DELETE+POST.
options:
  ip_proto:
    description:
      - Transport protocol the rule applies to.
    type: str
    choices: [tcp, udp]
    required: true
  wan_port_start:
    description:
      - First public WAN port (1..65535). For single-port forwards, set
        I(wan_port_end) to the same value.
    type: int
    required: true
  wan_port_end:
    description:
      - Last public WAN port (1..65535). Defaults to I(wan_port_start) for
        single-port rules.
    type: int
  lan_ip:
    description:
      - Destination LAN IPv4 (must be in RFC1918 private space). Required
        when I(state=present).
    type: str
  lan_port:
    description:
      - First destination LAN port. Required when I(state=present). The
        Freebox derives the LAN port range from the WAN range automatically.
    type: int
  src_ip:
    description:
      - Source IP restriction. Empty string means "any source"; otherwise an
        IPv4 / CIDR accepted by the Freebox. The empty default participates in
        the idempotency tuple — two rules differing only by I(src_ip) are
        distinct.
    type: str
    default: ""
  enabled:
    description:
      - Whether the rule is active. Disabled rules are kept in the Freebox
        configuration but do not forward traffic.
    type: bool
    default: true
  comment:
    description:
      - Free-form comment displayed in the Freebox UI.
    type: str
  state:
    description:
      - C(present) — the rule must exist and match the requested fields. The
        Freebox API supports partial PUT, so only the differing keys are
        sent.
      - C(absent) — the matching rule (if any) must be deleted.
    type: str
    choices: [present, absent]
    default: present
author:
  - Mipsou (@mipsou)
"""

EXAMPLES = r"""
- name: Forward HTTPS to the reverse proxy
  mipsou.freebox.port_forward:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    ip_proto: tcp
    wan_port_start: 443
    wan_port_end: 443
    lan_ip: 192.168.1.50
    lan_port: 443
    comment: "https-reverse-proxy"

- name: Disable the SSH passthrough without deleting it
  mipsou.freebox.port_forward:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    ip_proto: tcp
    wan_port_start: 22
    lan_ip: 192.168.1.10
    lan_port: 22
    enabled: false

- name: Remove the legacy game-server rule
  mipsou.freebox.port_forward:
    url: http://mafreebox.freebox.fr
    app_id: ansible
    app_token: "{{ freebox_app_token }}"
    ip_proto: udp
    wan_port_start: 27015
    wan_port_end: 27015
    state: absent
"""

RETURN = r"""
rule:
  description: Final state of the rule, or the previous state when I(state=absent).
  type: dict
  returned: always
  sample:
    id: 7
    enabled: true
    ip_proto: "tcp"
    wan_port_start: 443
    wan_port_end: 443
    lan_ip: "192.168.1.50"
    lan_port: 443
    src_ip: ""
    comment: "https-reverse-proxy"
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
    validate_port,
    validate_rfc1918,
)


def _identity(rule):
    """Composite identity tuple used to match an existing rule on the box."""
    return (
        rule.get("ip_proto"),
        rule.get("wan_port_start"),
        rule.get("wan_port_end"),
        rule.get("src_ip") or "",
    )


def _find_rule(client, identity):
    rules = client.get("/fw/redir/") or []
    for rule in rules:
        if _identity(rule) == identity:
            return rule
    return None


def _diff_fields(existing, desired):
    """Return the dict of fields whose ``desired`` value differs from ``existing``."""
    return {
        key: value
        for key, value in desired.items()
        if value is not None and existing.get(key) != value
    }


def _ensure_present(module, client, identity, desired):
    existing = _find_rule(client, identity)
    if existing is None:
        if module.check_mode:
            return dict(changed=True, rule=dict(desired))
        body = {k: v for k, v in desired.items() if v is not None}
        created = client.post("/fw/redir/", body=body) or body
        return dict(changed=True, rule=created)

    diff = _diff_fields(existing, desired)
    if not diff:
        return dict(changed=False, rule=existing)

    if module.check_mode:
        simulated = dict(existing)
        simulated.update(diff)
        return dict(changed=True, rule=simulated)

    updated = client.put("/fw/redir/{0}".format(existing["id"]), body=diff)
    if not updated:
        updated = dict(existing)
        updated.update(diff)
    return dict(changed=True, rule=updated)


def _ensure_absent(module, client, identity):
    existing = _find_rule(client, identity)
    if existing is None:
        return dict(changed=False, rule={})
    if module.check_mode:
        return dict(changed=True, rule=existing)
    client.delete("/fw/redir/{0}".format(existing["id"]))
    return dict(changed=True, rule=existing)


def main():
    argspec = dict(COMMON_ARGSPEC)
    argspec.update(dict(
        ip_proto=dict(type="str", required=True, choices=["tcp", "udp"]),
        wan_port_start=dict(type="int", required=True),
        wan_port_end=dict(type="int"),
        lan_ip=dict(type="str"),
        lan_port=dict(type="int"),
        src_ip=dict(type="str", default=""),
        enabled=dict(type="bool", default=True),
        comment=dict(type="str"),
        state=dict(type="str", default="present", choices=["present", "absent"]),
    ))

    module = AnsibleModule(
        argument_spec=argspec,
        supports_check_mode=True,
        required_if=[("state", "present", ["lan_ip", "lan_port"])],
    )

    try:
        wan_start = validate_port(module.params["wan_port_start"], "wan_port_start")
    except ValueError as exc:
        module.fail_json(msg=str(exc))

    wan_end_raw = module.params.get("wan_port_end")
    wan_end = wan_start if wan_end_raw is None else None
    if wan_end_raw is not None:
        try:
            wan_end = validate_port(wan_end_raw, "wan_port_end")
        except ValueError as exc:
            module.fail_json(msg=str(exc))
    if wan_end < wan_start:
        module.fail_json(
            msg="wan_port_end (%d) must be >= wan_port_start (%d)" % (wan_end, wan_start)
        )

    lan_ip = module.params.get("lan_ip")
    if lan_ip is not None:
        try:
            lan_ip = validate_rfc1918(lan_ip)
        except ValueError as exc:
            module.fail_json(msg="invalid lan_ip: %s" % exc)

    lan_port = module.params.get("lan_port")
    if lan_port is not None:
        try:
            lan_port = validate_port(lan_port, "lan_port")
        except ValueError as exc:
            module.fail_json(msg=str(exc))

    src_ip = module.params.get("src_ip") or ""
    identity = (module.params["ip_proto"], wan_start, wan_end, src_ip)

    desired = dict(
        ip_proto=module.params["ip_proto"],
        wan_port_start=wan_start,
        wan_port_end=wan_end,
        src_ip=src_ip,
        lan_ip=lan_ip,
        lan_port=lan_port,
        enabled=module.params["enabled"],
        comment=module.params.get("comment"),
    )

    client = FreeboxClient(module)
    state = module.params["state"]

    try:
        if state == "absent":
            result = _ensure_absent(module, client, identity)
        else:
            result = _ensure_present(module, client, identity, desired)
    except FreeboxError as exc:
        module.fail_json(msg=str(exc))

    module.exit_json(**result)


if __name__ == "__main__":
    main()
