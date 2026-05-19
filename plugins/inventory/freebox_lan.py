# -*- coding: utf-8 -*-
#
# Copyright (c) 2026 Mipsou <chpujol@gmail.com>
# GNU General Public License v3.0+ (see LICENSE or https://www.gnu.org/licenses/gpl-3.0.txt)
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import absolute_import, division, print_function

__metaclass__ = type

DOCUMENTATION = r"""
name: freebox_lan
short_description: Inventory hosts from the Freebox LAN browser
description:
  - Queries C(GET /lan/browser/pub/) to discover hosts on the local network.
  - Groups hosts by C(host_type) (e.g. C(freebox_workstation), C(freebox_smartphone)).
  - Sets C(ansible_host) to the first active IPv4 address, along with C(mac),
    C(host_type), and C(name) host variables.
version_added: "0.3.0"
author:
  - Mipsou (@mipsou)
options:
  plugin:
    description: Name of the plugin — must be C(mipsou.freebox.freebox_lan).
    required: true
    type: str
    choices: [mipsou.freebox.freebox_lan]
  freebox_url:
    description: Base URL of the Freebox API.
    type: str
    default: http://mafreebox.freebox.fr
    env:
      - name: FREEBOX_URL
  freebox_app_id:
    description: Application identifier used to authenticate against the Freebox.
    type: str
    required: true
    env:
      - name: FREEBOX_APP_ID
  freebox_app_token:
    description: Application token (keep secret).
    type: str
    required: true
    no_log: true
    env:
      - name: FREEBOX_APP_TOKEN
  freebox_api_base:
    description: API path prefix.
    type: str
    default: /api/v15
  freebox_validate_certs:
    description: Whether to validate TLS certificates.
    type: bool
    default: true
  freebox_timeout:
    description: HTTP timeout in seconds.
    type: int
    default: 30
"""

EXAMPLES = r"""
# freebox_lan.yml — place in an inventory directory
plugin: mipsou.freebox.freebox_lan
freebox_url: http://mafreebox.freebox.fr
freebox_app_id: ansible
freebox_app_token: "{{ lookup('env', 'FREEBOX_APP_TOKEN') }}"
"""

from ansible.plugins.inventory import BaseInventoryPlugin

from ansible_collections.mipsou.freebox.plugins.module_utils.freebox_api import (
    FreeboxClient,
    FreeboxError,
)


class InventoryModule(BaseInventoryPlugin):
    NAME = "mipsou.freebox.freebox_lan"

    def verify_file(self, path):
        if not super(InventoryModule, self).verify_file(path):
            return False
        return path.endswith(("freebox_lan.yml", "freebox_lan.yaml"))

    def parse(self, inventory, loader, path, cache=True):
        super(InventoryModule, self).parse(inventory, loader, path, cache)
        self._read_config_data(path)

        url = self.get_option("freebox_url")
        app_id = self.get_option("freebox_app_id")
        app_token = self.get_option("freebox_app_token")
        api_base = self.get_option("freebox_api_base")
        timeout = self.get_option("freebox_timeout")
        validate_certs = self.get_option("freebox_validate_certs")

        client = FreeboxClient(
            module=None,
            url=url,
            app_id=app_id,
            app_token=app_token,
            api_base=api_base,
            timeout=timeout,
            validate_certs=validate_certs,
        )

        try:
            hosts = client.get("/lan/browser/pub/") or []
        except FreeboxError as exc:
            raise Exception("freebox_lan inventory: %s" % exc)

        for host in hosts:
            hostname = host.get("primary_name") or host.get("id") or host.get("mac", "unknown")
            host_type = host.get("host_type", "unknown")
            mac = host.get("l2ident", {}).get("id") or host.get("mac", "")

            # First active IPv4 address.
            ansible_host = None
            for addr in host.get("l3connectivities") or []:
                if addr.get("af") == "ipv4" and addr.get("reachable"):
                    ansible_host = addr.get("addr")
                    break

            # Group name: prefix + sanitized host_type.
            group = "freebox_%s" % host_type.replace("-", "_").replace(" ", "_")
            self.inventory.add_group(group)
            self.inventory.add_host(hostname, group=group)

            if ansible_host:
                self.inventory.set_variable(hostname, "ansible_host", ansible_host)
            self.inventory.set_variable(hostname, "mac", mac)
            self.inventory.set_variable(hostname, "host_type", host_type)
            self.inventory.set_variable(hostname, "name", hostname)

    def get_option(self, option):
        return self._options.get(option)

    def _read_config_data(self, path):
        """Load YAML config and populate self._options."""
        try:
            from ansible.parsing.dataloader import DataLoader
            loader = DataLoader()
            data = loader.load_from_file(path) or {}
        except Exception:
            data = {}
        defaults = {
            "freebox_url": "http://mafreebox.freebox.fr",
            "freebox_app_id": None,
            "freebox_app_token": None,
            "freebox_api_base": "/api/v15",
            "freebox_timeout": 30,
            "freebox_validate_certs": True,
        }
        defaults.update(data)
        self._options = defaults
