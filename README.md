# Ansible Collection — `mipsou.freebox`

[![CI](https://github.com/mipsou/mipsou.freebox/actions/workflows/ci.yml/badge.svg)](https://github.com/mipsou/mipsou.freebox/actions/workflows/ci.yml)
[![License: EUPL-1.2](https://img.shields.io/badge/License-EUPL--1.2-blue.svg)](https://joinup.ec.europa.eu/page/eupl-text-11-12)

Declarative, idempotent management of a Freebox (Free.fr ISP CPE) via its HTTP
API. Built for PRA / disaster-recovery workflows and homelab infra-as-code.

> First Ansible collection for the Freebox API. Replaces brittle bash scripts
> and ad-hoc HTTP calls with proper state-based modules supporting `check_mode`
> and `diff`.

## Scope (v0.1.0)

| Module | Purpose |
|---|---|
| [`mipsou.freebox.vm`](plugins/modules/vm.py) | Manage VM lifecycle (create, start, stop, delete, recreate) with cloud-init |
| [`mipsou.freebox.vm_disk`](plugins/modules/vm_disk.py) | Clone a source image into a per-VM disk (qcow2/raw) |
| [`mipsou.freebox.fs_file`](plugins/modules/fs_file.py) | Copy / move / rename / delete files on the Freebox NAS |

A shared `module_utils.freebox_api.FreeboxClient` handles the auth dance
(HMAC-SHA1 challenge, session refresh, automatic retry on `auth_required`).

## Requirements

- Ansible `>= 2.15`
- Python `>= 3.9` on the controller
- A Freebox Delta / Pop / Revolution / V7+ with an app token already registered
  (see [`docs/auth.md`](docs/auth.md))

## Quick start

```yaml
- hosts: localhost
  gather_facts: false
  vars:
    freebox_url: "https://mafreebox.freebox.fr"
    freebox_app_id: "community-freebox-ansible"
    freebox_app_token: "{{ lookup('ansible.builtin.env', 'FREEBOX_APP_TOKEN') }}"
  tasks:
    - name: Ensure VM fbx-vm-01 exists and is running
      mipsou.freebox.vm:
        url: "{{ freebox_url }}"
        app_id: "{{ freebox_app_id }}"
        app_token: "{{ freebox_app_token }}"
        name: fbx-vm-01
        state: present
        vcpus: 2
        memory: 1024
        disk:
          source_image: "/Disque 1/VMs/AlmaLinux-10-GenericCloud.aarch64.qcow2"
          name: fbx-vm-01.qcow2
          dir: "/Disque 1/VMs"
        cloudinit_file: ./cloud-init/fbx-vm-01.yaml
        started: true
```

See [`docs/getting_started.md`](docs/getting_started.md) for a full walkthrough.

## API version

The collection targets `/api/v15` by default — the version exposed by recent
Freebox firmware. The public Freebox SDK documentation
(<https://dev.freebox.fr/sdk/os/>) is frozen at v4 but the request/response
schemas are unchanged between v9 and v15. Override with the `api_base`
parameter if you need a different version.

## License

EUPL-1.2. See [`LICENSE`](LICENSE).
