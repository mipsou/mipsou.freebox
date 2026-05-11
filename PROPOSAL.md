# Proposal — `community.freebox` collection adoption

Paste-ready draft for a post on
[forum.ansible.com — Project Discussions](https://forum.ansible.com/c/project/7)
requesting adoption of an Ansible collection covering the Freebox HTTP API
(Free.fr ISP CPE). Tag the post with `coll-repo-request`.

> **Note (2026-05-11):** The legacy `ansible-collections/overview` GitHub repo
> and `ansible-community/community-topics` are now archived. All collection
> inclusion / namespace proposals moved to forum.ansible.com.

---

## Title

`New collection: community.freebox — Ansible modules for the Freebox HTTP API`

## Body

**Namespace / name:** `community.freebox`

**Maintainer:** [@mipsou](https://github.com/mipsou) (sole author at this
stage). Email: `chpujol@gmail.com`.

**Current home:** [github.com/mipsou/mipsou.freebox](https://github.com/mipsou/mipsou.freebox)
— published on Galaxy as
[`mipsou.freebox`](https://galaxy.ansible.com/ui/repo/published/mipsou/freebox/).
The `mipsou.*` track will remain available as a personal mirror or be
deprecated in favor of `community.freebox` if this proposal is accepted.

**Scope:** Declarative, idempotent management of a Freebox (Free.fr ISP CPE) via
its HTTP API. Targets `/api/v15` by default with `api_base` override. v0.1.1 ships
three P0 modules and one shared `module_utils.freebox_api.FreeboxClient`:

| Module | Purpose |
|---|---|
| `vm` | VM lifecycle (create / start / stop / delete / recreate) with cloud-init |
| `vm_disk` | Clone a source image into a per-VM disk (qcow2/raw) via async `/vm/disk/copy` |
| `fs_file` | Copy / move / rename / delete files on the Freebox NAS |

Roadmap (v0.2+): DHCP reservations, port forwarding, Wi-Fi config, inventory
plugin for VMs/devices on the LAN.

**Motivation:** Replace brittle bash scripts and ad-hoc HTTP calls (or a
manually-driven MCP server) with proper state-based modules supporting
`check_mode` and `diff`. Built for PRA / disaster-recovery workflows and
homelab infra-as-code. There is currently no Ansible collection covering the
Freebox API on Galaxy.

**Maintenance commitment:** Single maintainer for now; the codebase is small
(3 modules + auth helper, ~1500 LoC), test coverage is in place
(`ansible-test sanity` + `units` green on stable-2.16, stable-2.17, devel),
release pipeline is automated (tag → GitHub Actions → Galaxy). Open to
co-maintainers from the community.

**Licensing:** Currently EUPL-1.2 — happy to relicense to **GPL-3.0-or-later**
at acceptance time to align with `community.*` policy (sole author, no CLA
collection required; EUPL-1.2 Article 5 explicitly permits the GPL-3.0+
downstream migration).

**Migration plan if accepted:**

1. Relicense `mipsou.freebox` repo to GPL-3.0-or-later (single commit, sole
   author).
2. Transfer the repo to the `ansible-collections` org as
   `ansible-collections/community.freebox`.
3. Update `galaxy.yml` namespace `mipsou` → `community`, all Python import
   paths, all FQCN in EXAMPLES / docs / tests / CI workflow paths.
4. Publish first community release; mark `mipsou.freebox` as deprecated with a
   pointer to the new collection.

**Compliance with the [Collection Requirements](https://docs.ansible.com/ansible/devel/community/collection_contributors/collection_requirements.html):**

- ✅ Ansible-core support: `>=2.15`
- ✅ Sanity & unit tests green on stable-2.16, stable-2.17, devel
- ✅ `changelogs/` follows the antsibull-changelog format
- ✅ `meta/runtime.yml` declares `requires_ansible: '>=2.15'`
- ✅ All modules have proper `DOCUMENTATION` / `EXAMPLES` / `RETURN` blocks
  inheriting common args from `plugins/doc_fragments/main.py`
- ✅ No third-party Python dependencies at runtime (stdlib only)
- ✅ Idempotent, supports `check_mode` and `diff`

Happy to address any feedback before / during the SC review. Thanks!

---

## How to post this

1. Log in at https://forum.ansible.com (single sign-on with your GitHub
   account works).
2. Visit https://forum.ansible.com/new-topic?category=project
3. Title: `New collection: community.freebox — Ansible modules for the Freebox HTTP API`
4. Body: copy the "## Body" section above (everything between `## Body` and
   `## How to post this`).
5. **Tags**: add `coll-repo-request` (mandatory for routing to the right
   reviewers). Consider also `new-collection`.
6. Submit. Watch for Steering Committee triage; expect a few weeks for the
   review.
