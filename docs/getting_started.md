# Getting started with `mipsou.freebox`

This walkthrough takes you from a freshly-paired Freebox to a fully
provisioned VM in three steps. Familiarity with Ansible basics is assumed.

## Prerequisites

- A Freebox Delta / Pop / Revolution / V7+ on firmware 4.9+ (the API path
  `/api/v15` is what this collection targets).
- An `app_token` registered against your box — see [`auth.md`](auth.md).
- Ansible `>= 2.15` on your controller.
- For VM provisioning: at least one cloud-init capable image (qcow2)
  uploaded to the Freebox NAS via Freebox OS or a separate transfer tool.

## Install the collection

```bash
ansible-galaxy collection install mipsou.freebox
```

Or from a local checkout:

```bash
ansible-galaxy collection build
ansible-galaxy collection install mipsou-freebox-*.tar.gz --force
```

## Step 1 — health check

A `mipsou.freebox.fs_file` task in check_mode is the simplest probe; it
will fail loudly on auth issues and silently succeed otherwise.

```yaml
- hosts: localhost
  gather_facts: false
  vars:
    freebox_url: "https://mafreebox.freebox.fr"
    freebox_app_id: "community-freebox-ansible"
    freebox_app_token: "{{ lookup('ansible.builtin.env', 'FREEBOX_APP_TOKEN') }}"
  tasks:
    - name: Verify auth + reachability
      mipsou.freebox.fs_file:
        url: "{{ freebox_url }}"
        app_id: "{{ freebox_app_id }}"
        app_token: "{{ freebox_app_token }}"
        path: /Disque 1
        state: present
      check_mode: true
```

The directory `/Disque 1` exists on Delta/Pop boxes; adapt to your model
(`/Freebox` on Revolution).

## Step 2 — clone a disk image

`vm_disk` is the workhorse for VM provisioning. It encapsulates the
copy-then-rename pattern that the Freebox API forces (the native `fs_copy`
endpoint cannot specify a destination filename).

```yaml
- name: Provision a per-VM disk from the AlmaLinux base image
  mipsou.freebox.vm_disk:
    url: "{{ freebox_url }}"
    app_id: "{{ freebox_app_id }}"
    app_token: "{{ freebox_app_token }}"
    path: "/Disque 1/VMs/fbx-vm-01.qcow2"
    source_image: "/Disque 1/VMs/AlmaLinux-10-GenericCloud.aarch64.qcow2"
    state: present
```

Re-runs are idempotent: the module probes the destination via
`GET /fs/info/?path=...` and skips the clone if the file already exists.
Use `force: true` to refresh from a newer base image.

## Step 3 — declare the VM

```yaml
- name: Bring up fbx-vm-01
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

Notes:

- The Freebox firmware caps cloud-init userdata at 4096 bytes. For larger
  payloads, write a stub that uses `#include https://your-host/userdata.yaml`
  and serve the real content over HTTP. The module fails fast on oversized
  inputs.
- Configuration drift is reported as a warning, not auto-applied. To change
  CPU/memory/cloud-init on an existing VM, set `force_recreate: true` (and
  `delete_disk: true` for a full clean rebuild).
- The Freebox does not allow specifying the VM's MAC address at creation. If
  you need a stable MAC for DHCP reservation, capture it after first boot
  (see the inventory plugin roadmap in [`README.md`](../README.md)).

## Waiting for SSH

The `vm` module does not poll the guest. Compose it with
`ansible.builtin.wait_for_connection` once you trust the IP/hostname:

```yaml
- name: Wait for SSH on fbx-vm-01
  ansible.builtin.wait_for_connection:
    timeout: 600
  delegate_to: fbx-vm-01.local
```

## Tearing down

```yaml
- name: Destroy fbx-vm-01 and its disk
  mipsou.freebox.vm:
    url: "{{ freebox_url }}"
    app_id: "{{ freebox_app_id }}"
    app_token: "{{ freebox_app_token }}"
    name: fbx-vm-01
    state: absent
    delete_disk: true
```

`delete_disk: false` (the default) is the safe choice if you want to keep
the qcow2 around for forensic recovery.
