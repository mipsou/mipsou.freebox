# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
---
name: freebox_lan
short_description: Inventory plugin for Freebox LAN hosts
version_added: "0.3.0"
author:
  - Mipsou (@mipsou)
description:
  - Generates an Ansible inventory from the Freebox LAN browser
    (C(GET /lan/browser/pub/)).
  - Each host in the Freebox ARP/NDP table is added as an Ansible host.
  - Hosts are grouped automatically by C(host_type) when C(group_by_type)
    is C(true) (e.g. group C(freebox_workstation), C(freebox_smartphone)).
options:
  plugin:
    description:
      - Must be C(mipsou.freebox.freebox_lan).
    required: true
    choices: ["mipsou.freebox.freebox_lan"]
  url:
    description:
      - Base URL of the Freebox OS API (without trailing slash).
    type: str
    default: http://mafreebox.freebox.fr
    env:
      - name: FREEBOX_URL
  app_id:
    description:
      - Application identifier registered with the Freebox.
    type: str
    required: true
    env:
      - name: FREEBOX_APP_ID
  app_token:
    description:
      - Application token (secret).
    type: str
    required: true
    env:
      - name: FREEBOX_APP_TOKEN
  api_base:
    description:
      - API path prefix.
    type: str
    default: /api/v15
  validate_certs:
    description:
      - Whether to verify TLS certificates.
    type: bool
    default: true
  group_by_type:
    description:
      - When C(true), create groups named C(freebox_<host_type>) for each
        distinct C(host_type) returned by the Freebox.
    type: bool
    default: true
  reachable_only:
    description:
      - When C(true), only include hosts currently reachable on the LAN.
    type: bool
    default: false
"""

EXAMPLES = r"""
# freebox_lan.yml — place in your inventory directory
plugin: mipsou.freebox.freebox_lan
url: http://mafreebox.freebox.fr
app_id: ansible
app_token: "{{ lookup('env', 'FREEBOX_APP_TOKEN') }}"
group_by_type: true
reachable_only: false
"""

from ansible.errors import AnsibleError
from ansible.plugins.inventory import BaseInventoryPlugin

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    FreeboxClient,
    FreeboxError,
)


def _pick_hostname(host):
    """Return the best Ansible hostname for a LAN host dict."""
    return (
        (host.get("primary_name") or "").strip()
        or host.get("id", "")
        or host.get("mac", "unknown").replace(":", "_")
    )


def _group_name(host_type):
    """Return the Ansible group name for a given host_type."""
    return "freebox_%s" % host_type


class InventoryModule(BaseInventoryPlugin):
    NAME = "mipsou.freebox.freebox_lan"

    def verify_file(self, path):
        if not super(InventoryModule, self).verify_file(path):
            return False
        return path.endswith(("freebox_lan.yml", "freebox_lan.yaml"))

    def parse(self, inventory, loader, path, cache=False):
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        self._read_config_data(path)

        url = self.get_option("url")
        app_id = self.get_option("app_id")
        app_token = self.get_option("app_token")
        api_base = self.get_option("api_base")
        validate_certs = self.get_option("validate_certs")
        group_by_type = self.get_option("group_by_type")
        reachable_only = self.get_option("reachable_only")

        # Plugin context uses open_url; pass module=None.
        client = FreeboxClient(
            module=None,
            url=url,
            app_id=app_id,
            app_token=app_token,
            api_base=api_base,
            validate_certs=validate_certs,
        )

        try:
            hosts = client.get("/lan/browser/pub/") or []
        except FreeboxError as exc:
            raise AnsibleError("freebox_lan: failed to fetch LAN hosts: %s" % exc)

        for host in hosts:
            if reachable_only and not host.get("reachable", False):
                continue

            hostname = _pick_hostname(host)
            if not hostname:
                continue

            self.inventory.add_host(hostname)

            for var in ("mac", "reachable", "vendor_name"):
                val = host.get(var)
                if val is not None:
                    self.inventory.set_variable(hostname, var, val)

            # First L3 address as ansible var.
            l3 = host.get("l3connectivities") or []
            if l3:
                self.inventory.set_variable(hostname, "ip", l3[0].get("addr", ""))

            host_type = host.get("host_type", "")
            self.inventory.set_variable(hostname, "host_type", host_type)

            if group_by_type and host_type:
                grp = _group_name(host_type)
                self.inventory.add_group(grp)
                self.inventory.add_host(hostname, group=grp)
