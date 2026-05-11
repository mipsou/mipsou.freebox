# Audit Freebox API — source freebox-mcp

**Source** : `D:\infra\mcp-servers\freebox-mcp` commit `7c200246c1bbbc5b292788e58371cd2f9280fcf8` (2026-05-09)
**Date d'audit** : 2026-05-12
**Périmètre** : 39 domaines API enregistrés via `internal/tools/tools.go:RegisterAll` (38 listés dans le prompt + `discovery` qui était classé "infra"). Tous les fichiers non-test du package `internal/tools/` ont été lus, plus `internal/client/{client,errors}.go` et `internal/auth/auth.go`.

**Convention de citation** : `tools/<fichier>.go:<ligne>` pointe vers `D:\infra\mcp-servers\freebox-mcp\internal\tools\<fichier>.go:<ligne>`.

**Note préliminaire — destinataire** : ce livrable est rendu en sortie de message uniquement. La consigne demandait l'écriture dans `D:\workspace\code\community.freebox\AUDIT.md` mais l'agent fonctionne en read-only et n'a pas accès aux outils Write/Edit. Sauvegarder cette sortie dans le fichier cible côté utilisateur.

---

## Patterns transverses

### A. Envelope de réponse

Toutes les réponses authentifiées de l'API Freebox utilisent la même enveloppe JSON, décodée systématiquement par `client/client.go:136-152` :

```json
{
  "success": true,
  "msg": "",
  "error_code": "",
  "result": <payload spécifique au endpoint, peut être objet, tableau, scalaire, absent>
}
```

Le helper `Client.do()` désérialise l'enveloppe, vérifie `success`, retourne `*APIError{ErrorCode, Msg}` (`client/errors.go:11`) si `success=false`, sinon désérialise `result` dans la struct cible. **Exception** : le endpoint de discovery `GET http://mafreebox.freebox.fr/api_version` (`client/client.go:69-84`, `tools/discovery.go:23-32`) renvoie un JSON brut sans enveloppe — pas d'auth, pas de `success`.

**Implication Ansible** : le `FreeboxClient` doit lever une exception sur `success=false` avec `error_code` + `msg` propagés vers `module.fail_json`. Les modules ne voient jamais l'enveloppe ; ils manipulent uniquement le payload de `result`.

### B. Gestion d'erreur

- Code `auth_required` : le client le détecte (`client/client.go:97-102` et `client/client.go:48-54`), invalide la session via `auth.Manager.Invalidate()`, et **retente automatiquement l'appel une seule fois**. Transparent pour l'appelant.
- Code `invalid_token` / `pending_token` (lors de l'ouverture de session) : retourné comme `auth.ErrTokenRevoked` (`auth/auth.go:26`, `auth/auth.go:161-163`). Ces erreurs **exigent un re-pairing** — l'app_token stocké est mort.
- Autres `error_code` : remontés tels quels dans `APIError.ErrorCode`. Aucune liste exhaustive n'est codifiée côté freebox-mcp ; les codes observés en pratique sont `invalid_request` (body malformé, ex. champ `id` envoyé en POST), `nodev`, `task_not_found`, `not_found`, `denied` (permission manquante), `internal_error`.
- Permissions documentées dans les commentaires des handlers : plusieurs PUT mentionnent **"Nécessite la permission 'settings'"** (`tools/dhcpconfig.go:139`, `tools/netshare.go:60`). C'est une propriété de l'app_token (déclarée à l'enregistrement), pas un en-tête runtime.

**Implication Ansible** : prévoir une exception class hierarchy `FreeboxAPIError` avec attribut `error_code` exposé, plus une exception spécifique `TokenRevokedError`. Les modules doivent traiter `not_found` comme idempotent en mode `state: absent`.

### C. Tâches async

**freebox-mcp expose DEUX shapes incompatibles de tâches asynchrones, plus deux outliers** :

| Pattern | Champ erreur | Champ état | Endpoints | Référence |
|---|---|---|---|---|
| `FSTask` | `error: string` (message ou vide) | `state: string` (`queued`/`running`/`done`/`failed`) | `POST /fs/rm/`, `POST /fs/mv/`, `POST /fs/cp/` | `tools/filesystem.go:60-68` |
| `VMDiskTask` | `error: bool` (présence) | `state: string` **empiriquement vide** ; utiliser `done: bool` | `POST /vm/disk/resize`, `POST /vm/disk/create` | `tools/vm.go:89-97` |
| Outlier 1 | n/a | n/a | `POST /fs/mkdir/` retourne **un bare string** (task ID seul, pas d'objet) | `tools/filesystem.go:182-187` |
| Outlier 2 | n/a | n/a | `POST /fs/rename/` est **synchrone** (retourne le nouveau path base64 directement) malgré son URL `/fs/...` | `tools/filesystem.go:332-375` |

**Polling** :
- FS tasks : `GET /fs/tasks/{id}` — **non implémenté dans freebox-mcp** (mais le pattern existe côté Freebox OS). À découvrir par contrat lors de l'implémentation Ansible.
- VM disk tasks : `GET /vm/disk/task/{id}` (`tools/vm.go:455-471`).

**Suppression obligatoire** des tâches terminées (Freebox bug tracker FS#30666) : `DELETE /vm/disk/task/{id}` (`tools/vm.go:473-490`). Si on omet ce DELETE les tâches s'accumulent côté firmware. Probablement vrai aussi pour `/fs/tasks/`.

**Implication Ansible** : implémenter un helper de poll réutilisable avec deux variantes (bool/string `error`, et fallback `done` quand `state` est vide). Toujours faire le DELETE final côté VM disk tasks. Le polling doit avoir un timeout configurable (`async_timeout`) et un `interval` paramétrable.

### D. Pagination

**Absente sur tous les endpoints lus**. Aucun handler ne construit de query-string `?offset=`, `?limit=`, `?cursor=`. Les listings (`/dhcp/static_lease/`, `/lan/browser/pub/`, `/wifi/stations/`, `/downloads/`, `/call/log/`, `/contact/`, `/fw/redir/`, etc.) renvoient des tableaux complets. Confirmé par absence — aucune mention de pagination dans les commentaires. Hypothèse plausible : la Freebox a peu de ressources par type (< 1000 entrées même sur les plus gros), pas besoin de pagination.

**Implication Ansible** : modules `_info` peuvent retourner toute la liste sans paginer. Pas de paramètre `page_size`.

### E. Auth

Flow confirmé conforme à ce qui est déjà implémenté côté Ansible (`auth/auth.go`) :

1. **App token** : stocké hors session (l'utilisateur l'obtient une fois via la procédure de pairing physique sur la Freebox — bouton "flèche droite" sur l'écran). Non géré par freebox-mcp ni par client.go.
2. **Challenge** : `GET /login/` → `{result: {challenge: "..."}}` (`auth/auth.go:108-128`). **Pas d'enveloppe `error_code` analysée** ici, juste `success`.
3. **Signature** : `HMAC-SHA1(app_token, challenge)` en hex lowercase (`auth/auth.go:96-101`). Free spécifie HMAC-SHA1 (commentaire `//nolint:gosec` car cryptographiquement faible mais imposé par l'API).
4. **Session** : `POST /login/session/` avec `{app_id, password: <signature>}` → `{result: {session_token, password_salt, permissions}}` (`auth/auth.go:136-167`).
5. **Header sur chaque requête** : `X-Fbx-App-Auth: <session_token>` (`client/client.go:120`).
6. **Durée de session** : la doc dit ~30 min, freebox-mcp utilise une marge à **25 minutes hardcodée** (`auth/auth.go:166-167`). Sur erreur `auth_required` à mi-vie, la session est invalidée et reconstruite automatiquement.

**Implication Ansible** : le `FreeboxClient` existant fait déjà ça. À vérifier que le retry sur `auth_required` est bien implémenté côté Ansible — sinon, ajouter. La permission `settings` doit être requise lors de la création de l'app_token pour la plupart des modules de configuration.

### F. Encodage base64 (transverse mais critique)

Plusieurs endpoints exigent des chemins encodés en **base64 standard avec padding** (RFC 4648 §4, *pas* base64url) :

| Endpoint | Champ | Mode |
|---|---|---|
| `GET /fs/ls/{path_b64}` | segment d'URL | `tools/filesystem.go:148` |
| `GET /fs/info/?path={url_encoded_b64}` | **query-string** (URL-encode du base64) | `tools/filesystem.go:122-125` |
| `POST /fs/mkdir/`, `/fs/rm/`, `/fs/mv/`, `/fs/cp/`, `/fs/rename/` | champs body (`parent`, `files`, `dst`, `src`) | `tools/filesystem.go` (multiples) |
| `POST /vm/` | `disk_path`, `cd_path` | `tools/vm.go:256, 276` |
| `POST /vm/disk/resize`, `/vm/disk/create` | `disk_path` | `tools/vm.go:392, 443` |
| `POST /downloads/add/` | `download_dir` (champ form-urlencoded) | `tools/downloads.go:44` |
| `PUT /downloads/config/` | `download_dir`, `watch_dir` | `tools/downloadconfig.go:78, 86` |
| `GET /tftp/config/` (réponse) | `root` (réponse base64 — à décoder côté client) | `tools/tftp.go:20` |

Helper : `tools/filesystem.go:82-89` (`encodeFSPath`).

### G. Content-Type quirk

Tout est `application/json` **sauf** `POST /downloads/add/` qui exige `application/x-www-form-urlencoded` ET le paramètre s'appelle `download_url` (pas `url`) (`tools/downloads.go:36-47`). C'est pourquoi `client.go` expose `PostForm()` (`client/client.go:46-55`).

### H. Versions d'API mélangées

Les commentaires Go référencent tantôt `/api/v4/...`, tantôt `/api/v15/...`. **Mais le client utilise un seul `baseURL` fixé à la construction** (`client/client.go:30-32`, `client/client.go:116`). Les chemins passés aux handlers (`/dhcp/static_lease/`, `/vm/info`, etc.) sont concaténés au `baseURL` qui inclut déjà `/api/v15`. La cohabitation v4/v15 dans les commentaires reflète l'historique des endpoints : ils ont été ajoutés dans des versions différentes mais restent accessibles via le préfixe v15 actuel.

**Implication Ansible** : un seul paramètre `api_version` (ou un `base_url` complet) suffit. Pas besoin de routage par version par endpoint.

### I. PUT semantics inconsistant entre domaines

**Critique pour la conception de l'idempotence Ansible.** Le comportement de PUT varie :

| Endpoint | Sémantique | Référence |
|---|---|---|
| `PUT /vm/{id}` | **Rejette les patchs partiels** (`invalid_request`). Read-modify-write obligatoire avec body complet. | `tools/vm.go:311-313` (#80) |
| `PUT /lan/browser/pub/{id}` | Accepte patchs partiels (struct `omitempty`). | `tools/lanconfig.go:30-33` (#94) |
| `PUT /dhcp/config/` | Patch partiel fonctionne **mais via la struct complète** `dhcpConfigUpdate` (champs read-only `gateway`/`netmask` exclus). Pattern read-modify-write quand même utilisé. | `tools/dhcpconfig.go:85-96` |
| `PUT /connection/config/` | Patch direct via `map[string]any` — true partial PUT. | `tools/connectionconfig.go:60-87` |
| `PUT /netshare/samba/` | Patch direct via `map[string]any`. | `tools/netshare.go:72-99` |
| `PUT /downloads/config/` | Patch direct via `map[string]any`. | `tools/downloadconfig.go:70-117` |
| `PUT /wifi/config/` | Patch via map (champ `enabled` seul). | `tools/wifi.go:84-92` |
| `PUT /wifi/bss/{id}` | Patch via map (champ `enabled` seul). | `tools/wifibss.go:83-91` |
| `PUT /fw/redir/{id}` | Patch via map (champ `enabled` seul). | `tools/nat.go:131-141` |
| `PUT /downloads/{id}` | Patch via map (champ `status` seul). | `tools/downloads.go:99-109` |
| `PUT /lcd/config/` | Patch via map (champ `brightness` seul). | `tools/lcd.go:46-54` |

**Heuristique observée** : les endpoints de **config singleton** acceptent souvent le patch partiel. Les endpoints de **ressources individuelles** (VM, hôte LAN, BSS, NAT rule, download) tantôt acceptent le patch (`/lan/browser/pub/{id}`, toggles ciblés), tantôt l'exigent complet (`/vm/{id}`). Pas de règle universelle — à valider runtime par endpoint.

**Implication Ansible** : implémenter un helper `_diff_then_put()` qui fait GET → diff → PUT avec body complet par défaut (sécurité), et un opt-in `patch=true` pour les endpoints connus pour accepter les patchs.

---

## Domaines API

### 1. discovery

- **Endpoints** :
  - `GET http://{host}/api_version` (sans auth, sans enveloppe) — `tools/discovery.go:21-32, 34-47`
- **Payload** : retourne `ApiVersionInfo {uid, device_name, api_version, api_base_url, device_type, https_available, https_port, box_model, box_model_name}`
- **Idempotency key** : n/a (lecture seule)
- **Type** : read-only (singleton)
- **Async** : non
- **Dépendances** : aucune ; précède toute auth
- **Notes Ansible** : utile pour un module `freebox_discover_info` ou pour le bootstrap d'un play (récupérer `https_port`, `box_model`). Probablement à fusionner avec `system` dans un seul module `freebox_facts`.

### 2. connection

- **Endpoints** :
  - `GET /connection/` — `ConnectionStatus` (state, type, media, ipv4, ipv6, débits) — `tools/connection.go:89-101`
  - `GET /connection/xdsl/` — `XdslStatus` (SNR, atténuation, FEC/CRC errors) — `tools/connection.go:103-114`
  - `GET /connection/ftth/` — `FtthStatus` (SFP, signal Tx/Rx) — `tools/connection.go:116-127`
  - `GET /dynDns/` — `[]DynDNSEntry` — `tools/connection.go:129-140`
- **Payload** : tous lecture seule, voir structs `tools/connection.go:18-87`
- **Idempotency key** : n/a (read-only)
- **Type** : read-only (4 endpoints distincts agrégés)
- **Async** : non
- **Dépendances** : aucune
- **Notes Ansible** : 1 module `freebox_connection_info` (agrège status/xdsl/ftth) + 1 module `freebox_dyndns_info`. Le dynDNS est listé GET-only ici mais l'API doit supporter CRUD — à vérifier (lacune freebox-mcp).

### 3. connectionconfig

- **Endpoints** :
  - `GET /connection/config/` — `ConnectionConfig {ping, is_secure_pass, remote_access, remote_access_port, remote_access_ip, wol_port, adblock}` — `tools/connectionconfig.go:28-41`
  - `PUT /connection/config/` — patch partiel (map) — `tools/connectionconfig.go:43-87`
- **Payload** : voir struct, modifiable : `ping`, `remote_access`, `remote_access_port`, `wol_port`, `adblock`. `remote_access_ip` est read-only.
- **Idempotency key** : config singleton
- **Type** : config (singleton, partial PUT)
- **Async** : non
- **Dépendances** : aucune
- **Notes Ansible** : module `freebox_connection_config` (singleton, idempotent via diff sur GET avant PUT).

### 4. connectionipv6

- **Endpoints** :
  - `GET /connection/ipv6/config/` — `ConnectionIPv6Config {ipv6_enabled, ipv6_firewall, ipv6_prefix_firewall, ipv6ll, delegations[]}` — `tools/connectionipv6.go:33-46`
- **Payload** : lecture seule dans freebox-mcp. Délégations = préfixes IPv6 (DHCPv6-PD).
- **Idempotency key** : config singleton
- **Type** : read-only (probablement config singleton côté API mais MCP n'expose pas le PUT)
- **Async** : non
- **Dépendances** : aucune
- **Notes Ansible** : module `freebox_connection_ipv6_info` en première intention. Endpoint PUT à découvrir empiriquement si on veut un module config.

### 5. connectionlogs

- **Endpoints** :
  - `GET /connection/logs/` — `[]ConnectionLogEntry {id, date, type, state, link, bw_down, bw_up}` — `tools/connectionlogs.go:28-40`
- **Payload** : historique des transitions de ligne (up/down) avec débits négociés
- **Idempotency key** : n/a (read-only)
- **Type** : read-only
- **Async** : non
- **Dépendances** : aucune
- **Notes Ansible** : module `freebox_connection_logs_info` — utile pour PRA / monitoring.

### 6. lan

- **Endpoints** :
  - `GET /lan/browser/pub/` — `[]LanHost` (id, primary_name, host_type, l2ident[], vendor_name, reachable, l3connectivities[]) — `tools/lan.go:88-99`
  - `GET /lan/browser/interfaces/` — `[]LanInterface {name, host_count}` (ex: `pub`, `guest`) — `tools/lan.go:101-112`
- **Payload** : voir structs `tools/lan.go:20-85`. **Quirk** : `l2ident` peut être objet OU tableau selon le firmware (custom unmarshaler `tools/lan.go:31-53`).
- **Idempotency key** : `id` (string) pour les hôtes
- **Type** : read-only ici, mais `PUT /lan/browser/pub/{id}` existe (voir lanconfig)
- **Async** : non
- **Dépendances** : référencé par `wifimacfilter` (champ `host`), `wol` (interface name)
- **Notes Ansible** : `freebox_lan_hosts_info` et `freebox_lan_interfaces_info` ; module CRUD couvert via `lanconfig`.

### 7. lanconfig

- **Endpoints** :
  - `GET /lan/config/` — `LanConfig {ip, name, name_dns, name_mdns, name_netbios, type}` — `tools/lanconfig.go:35-48`
  - `PUT /lan/browser/pub/{id}` — patch partiel via `LanHostUpdate {primary_name?, host_type?}` — `tools/lanconfig.go:50-125`
- **Payload** : 27 valeurs de `host_type` énumérées et **validées runtime** sur firmware 4.9.18.1 (enum exhaustif dans `tools/lanconfig.go:87-105`). La doc dev.freebox.fr/sdk/os/lan/ est **figée v4 et incomplète** (commentaire `tools/lanconfig.go:85`).
- **Idempotency key** : config singleton pour `/lan/config/` ; `id` host pour `/lan/browser/pub/{id}`
- **Type** : config singleton (GET-only ici) + stateful PUT sur les hôtes
- **Async** : non
- **Dépendances** : utilise IDs de `lan` (host)
- **Notes Ansible** : 
  - `freebox_lan_config_info` (GET singleton)
  - `freebox_lan_host` (update partiel : `primary_name`, `host_type`) — idempotent via diff. Note : pas de DELETE évident sur les hosts (auto-géré par la box).

### 8. dhcp

- **Endpoints** :
  - `GET /dhcp/static_lease/` — `[]DhcpStaticLease {id, mac, hostname, ip, comment}` — `tools/dhcp.go:39-50`
  - `GET /dhcp/dynamic_lease/` — `[]DhcpDynamicLease {mac, hostname, ip, assign_time, refresh_time, lease_remaining, is_static}` — `tools/dhcp.go:53-64`
  - `POST /dhcp/static_lease/` — body `DhcpStaticLease` (sans `id`) — `tools/dhcp.go:66-101`
  - `DELETE /dhcp/static_lease/{id}` — `tools/dhcp.go:103-118`
- **Payload** : voir structs `tools/dhcp.go:18-35`
- **Idempotency key** : **`mac`** (le `id` est attribué par la box mais `mac` est unique par contrainte logique)
- **Type** : stateful CRUD (statiques) + read-only (dynamiques)
- **Async** : non
- **Dépendances** : aucune ; mais `validateDHCPIP` (`tools/validate.go:127-144`) rejette `.0`, `.1`, `.254`, `.255` (validation côté MCP, pas côté API)
- **Notes Ansible** :
  - `freebox_dhcp_static_lease` — CRUD avec `state: present/absent`, idempotence par `mac` (faire GET liste → match par mac → POST si absent, DELETE si présent et `state: absent`)
  - `freebox_dhcp_dynamic_leases_info` (read-only)
  - **Pas de PUT exposé sur `/dhcp/static_lease/{id}`** — pour modifier, il faut probablement DELETE + POST. À vérifier (lacune freebox-mcp).

### 9. dhcpconfig

- **Endpoints** :
  - `GET /dhcp/config/` — `DHCPConfig` (enabled, sticky_assign, plage IP, dns, options[]) — `tools/dhcpconfig.go:98-111`
  - `PUT /dhcp/config/` — read-modify-write avec struct complète `dhcpConfigUpdate` (exclut `gateway`/`netmask` read-only) — `tools/dhcpconfig.go:136-238`
  - `PUT /dhcp/config/` (variante options uniquement) — `dhcpOptionsUpdate` pour ajouter/modifier/supprimer options DHCP custom (RFC2132) — `tools/dhcpconfig.go:240-333`
- **Payload** : `DHCPConfig.options` est `[]{id, val}` (option ID type `tftp_server_name`, `bootfile_name`, etc.). **Quirk** : l'API renvoie `{}` (objet vide) au lieu de `[]` quand pas d'options → custom unmarshaler `DHCPOptions` (`tools/dhcpconfig.go:32-57`).
- **Idempotency key** : singleton ; pour les options, `id` (string) de l'option DHCP
- **Type** : config singleton + sous-collection stateful (options)
- **Async** : non
- **Dépendances** : aucune
- **Notes Ansible** :
  - `freebox_dhcp_config` (singleton, idempotent via diff)
  - `freebox_dhcp_option` (CRUD sur options par `id`, ex: `tftp_server_name`) — utile pour PXE/iPXE

### 10. dhcpv6

- **Endpoints** :
  - `GET /dhcpv6/config/` — `DHCPv6Config {enabled, use_custom_dns, dns[]}` — `tools/dhcpv6.go:23-36`
- **Payload** : lecture seule dans freebox-mcp
- **Idempotency key** : config singleton
- **Type** : read-only (probablement config côté API)
- **Async** : non
- **Notes Ansible** : `freebox_dhcpv6_info` ; PUT à découvrir empiriquement pour un module config.

### 11. nat

- **Endpoints** :
  - `GET /fw/redir/` — `[]PortForwarding {id, enabled, comment, lan_port, wan_port_start, wan_port_end, lan_ip, ip_proto, src_ip}` — `tools/nat.go:32-43`
  - `POST /fw/redir/` — body `PortForwarding` — `tools/nat.go:46-118`
  - `PUT /fw/redir/{id}` — patch partiel (map, ex. `{enabled}`) — `tools/nat.go:121-141`
  - `DELETE /fw/redir/{id}` — `tools/nat.go:144-158`
- **Payload** : voir struct ; validation : `validateRFC1918` (lan_ip), `validatePort` (1-65535)
- **Idempotency key** : **composite** — `(ip_proto, wan_port_start, wan_port_end, src_ip)` identifie la règle, `id` est attribué par la box. À matcher côté module pour idempotence.
- **Type** : stateful CRUD
- **Async** : non
- **Dépendances** : `lan_ip` doit être un hôte joignable (RFC1918)
- **Notes Ansible** : `freebox_port_forward` — CRUD ; idempotence par tuple `(ip_proto, wan_port_start, wan_port_end)` + `lan_ip`. Permettre `state: present/absent`.

### 12. firewall

- **Endpoints** :
  - `GET /fw/incoming/` — `[]FirewallIncomingRule {id, enabled, comment, action, ip_proto, src_ip, dst_port, src_port}` — `tools/firewall.go:34-47`
  - `GET /fw/dmz/` — `DMZConfig {enabled, ip}` — `tools/firewall.go:49-61`
- **Payload** : lecture seule dans freebox-mcp
- **Idempotency key** : `id` (string) pour rules incoming ; singleton pour DMZ
- **Type** : read-only ici (lacune)
- **Async** : non
- **Notes Ansible** : `freebox_firewall_incoming_info` et `freebox_firewall_dmz_info`. **Lacune freebox-mcp** : pas de POST/PUT/DELETE sur `/fw/incoming/` ni `/fw/dmz/` exposés — l'API les supporte certainement (cohérence avec `/fw/redir/`). À implémenter empiriquement pour des modules CRUD.

### 13. firmware

- **Endpoints** :
  - `GET /system/update/` — `FirmwareUpdate {update_available, version}` — `tools/firmware.go:22-34`
- **Payload** : check de disponibilité de MAJ
- **Idempotency key** : n/a
- **Type** : read-only
- **Async** : non (action de mise à jour réelle non exposée)
- **Notes Ansible** : `freebox_firmware_update_info`. Pas d'action `apply_update` ici — à découvrir empiriquement si désiré (probablement async via reboot).

### 14. ftp

- **Endpoints** :
  - `GET /ftp/config/` — `FtpConfig {enabled, allow_anonymous, allow_anonymous_write, allow_remote_access, weak_password, port_ctrl, port_data, remote_domain}` — `tools/ftp.go:28-40`
- **Payload** : lecture seule
- **Type** : read-only ici (config singleton côté API)
- **Notes Ansible** : `freebox_ftp_info`. PUT probable mais non exposé.

### 15. tftp

- **Endpoints** :
  - `GET /tftp/config/` — `TftpConfig {enabled, root}` (`root` en base64) — `tools/tftp.go:23-35`
- **Payload** : ajouté en firmware 4.9.15 (janvier 2026), **non documenté dans le SDK officiel** (commentaire `tools/tftp.go:17`)
- **Type** : read-only ici (config singleton côté API)
- **Notes Ansible** : `freebox_tftp_info`. Module config à valider runtime (PUT non testé).

### 16. upnp

- **Endpoints** :
  - `GET /upnp/config/` — `UPnPConfig {enabled}` — `tools/upnp.go:36-48`
  - `GET /upnp/igd/rules/` — `[]UPnPIGDMapping {id, enabled, ext_ip, ext_port, int_ip, int_port, proto, desc, duration}` — `tools/upnp.go:50-62`
- **Payload** : voir structs
- **Type** : read-only ici. Config singleton + listing IGD
- **Notes Ansible** : `freebox_upnp_info` + `freebox_upnp_rules_info`. PUT sur config probable (toggle enabled), à valider.

### 17. wifi

- **Endpoints** :
  - `GET /wifi/ap/` — `[]WifiAp {id, name, status, config}` — `tools/wifi.go:49-60`
  - `GET /wifi/config/` — `WifiGlobalConfig {enabled, mac_filter_state}` — `tools/wifi.go:62-74`
  - `PUT /wifi/config/` — toggle global (map `{enabled}`) — `tools/wifi.go:76-93`
- **Payload** : voir structs, dont `WifiApStatus` (state, channel_width, primary_channel, dfs_cac_remaining_time) et `WifiApConfig` (band, channel_width, primary_channel, dfs_enabled)
- **Idempotency key** : config singleton (global) ; `id` (int) pour les APs
- **Type** : config singleton + read-only listing AP
- **Async** : non
- **Notes Ansible** : `freebox_wifi_config` (toggle global) + `freebox_wifi_aps_info`. PUT sur `/wifi/ap/{id}` (changer canal/largeur/DFS) probable mais non exposé — à valider pour un module CRUD canal.

### 18. wifibss

- **Endpoints** :
  - `GET /wifi/bss/` — `[]WifiBss {id, bssid, ssid, band, enabled, hide_ssid, encryption, ap_id}` — `tools/wifibss.go:43-56`
  - `GET /wifi/stations/` — `[]WifiStation {mac, bssid, band, signal, rx_rate, tx_rate, authorized, active}` — `tools/wifibss.go:58-70`
  - `PUT /wifi/bss/{id}` — toggle SSID (map `{enabled}`) — `tools/wifibss.go:72-92`
- **Idempotency key** : `id` (string) pour BSS, `mac` pour stations
- **Type** : stateful (toggle SSID) + read-only stations
- **Notes Ansible** : `freebox_wifi_ssid` (toggle, et possiblement update SSID/encryption/hide_ssid via PUT plus complet à découvrir) + `freebox_wifi_stations_info`.

### 19. wifimacfilter

- **Endpoints** :
  - `GET /wifi/mac_filter/` — `[]WifiMacFilterEntry {id, mac, type, comment, hostname, host(raw)}` (type = `whitelist`|`blacklist`) — `tools/wifimacfilter.go:30-42`
- **Payload** : `host` est `json.RawMessage` car shape varie
- **Type** : read-only ici
- **Idempotency key** : `mac` (logique)
- **Notes Ansible** : `freebox_wifi_mac_filter_info`. **Lacune freebox-mcp** : pas de CRUD exposé sur `/wifi/mac_filter/` — l'API supporte certainement POST/DELETE. À implémenter pour un module `freebox_wifi_mac_filter` CRUD.

### 20. wifiplanning

- **Endpoints** :
  - `GET /wifi/planning/` — `WifiPlanning {use_planning, resolution, mapping[]}` — `tools/wifiplanning.go:27-39`
- **Payload** : `mapping` est tableau de strings "on"/"off" représentant la grille hebdomadaire (typiquement 168 ou 336 slots)
- **Type** : read-only ici (config singleton côté API)
- **Notes Ansible** : `freebox_wifi_planning_info`. PUT probable pour configurer la grille, non exposé.

### 21. storage

- **Endpoints** :
  - `GET /storage/disk/` — `[]StorageDisk {id, type, connector, state, total_bytes, idle, spinning, table_type, display_name, partitions[]}` — `tools/storage.go:48-58`
  - `GET /storage/partition/` — `[]StoragePartition {id, disk_id, fstype, label, state, path, total_bytes, free_bytes, used_bytes}` — `tools/storage.go:60-72`
  - `GET /storage/raid/` — `[]StorageRAID {id, name, state, level}` (renvoie `null` si pas de RAID, normalisé en `[]` côté MCP) — `tools/storage.go:74-87`
- **Payload** : `connector` est un int enum (0=unknown, 1=USB, 2=eSATA, 3=PCIe…)
- **Type** : read-only
- **Idempotency key** : `id` numérique
- **Dépendances** : référencé par `vm` (le `disk_dir` doit pointer vers un `path` de partition montée)
- **Notes Ansible** : `freebox_storage_info` (agrège disk/partition/raid). Lecture seule.

### 22. filesystem

- **Endpoints** :
  - `GET /fs/info/?path={url_encoded_b64}` — `FSInfo {name, path, type, size, ...}` — `tools/filesystem.go:108-130`
  - `GET /fs/ls/{path_b64}` — wrapper `FSListResult {entries[], parent}` — `tools/filesystem.go:132-153`
  - `POST /fs/mkdir/` body `{parent: b64, dirname: str}` → **bare string task ID** — `tools/filesystem.go:155-189`
  - `POST /fs/rm/` body `{files: [b64]}` → `FSTask` async — `tools/filesystem.go:191-216`
  - `POST /fs/mv/` body `{files: [b64], dst: b64, mode: enum}` → `FSTask` async — `tools/filesystem.go:218-271`
  - `POST /fs/cp/` body `{files: [b64], dst: b64, mode: enum}` → `FSTask` async — `tools/filesystem.go:273-326`
  - `POST /fs/rename/` body `{src: b64, dst: basename}` → **synchrone**, retourne nouveau path b64 — `tools/filesystem.go:328-375`
- **Payload** : `dst_mode` ∈ `{overwrite, both, recent, skip}` ; modes verrouillés par enum
- **Idempotency key** : `path` absolu (string)
- **Type** : stateful (CRUD fichiers) + async sur rm/mv/cp + helpers info/list
- **Async** : oui pour rm/mv/cp (FSTask) ; mkdir async mais shape "bare string" ; rename **synchrone**
- **Dépendances** : `/fs/info` exige path en query-string URL-encodé (différent des autres endpoints du domaine qui prennent le b64 en segment d'URL)
- **Sécurité** : `sanitizeFSPath` (`tools/filesystem.go:91-104`) interdit `..` et `/` nu
- **Notes Ansible** :
  - `freebox_fs_info` (lookup)
  - `freebox_fs_list` (list_filter type module)
  - `freebox_fs_directory` (state: present/absent → mkdir + rm)
  - `freebox_fs_file` (déjà existant côté Ansible — vérifier alignement)
  - `freebox_fs_copy` / `freebox_fs_move` / `freebox_fs_rename` (actions plutôt que CRUD pur, sauf si `state` style)
  - **Polling** : prévoir helper commun `_wait_fs_task(task_id)` avec timeout, basé sur le shape FSTask (state enum + error string).

### 23. vm

- **Endpoints** :
  - `GET /vm/` — `[]VM` — `tools/vm.go:120-132`
  - `POST /vm/{id}/start` — `tools/vm.go:135-149`
  - `POST /vm/{id}/stop` (ACPI gracieux) — `tools/vm.go:152-167`
  - `POST /vm/{id}/kill` (force) — `tools/vm.go:171-186`
  - `POST /vm/` body `vmCreateRequest` → `VM` — `tools/vm.go:188-289`
  - `PUT /vm/{id}` body `VM` complet (read-modify-write, partial **rejeté**) — `tools/vm.go:291-340`
  - `DELETE /vm/{id}` — `tools/vm.go:342-357`
  - `POST /vm/disk/resize` body `vmDiskResizeRequest {disk_path(b64), size, shrink_allow}` → `VMDiskTask` async — `tools/vm.go:359-402`
  - `POST /vm/disk/create` body `vmDiskCreateRequest {disk_path(b64), size, disk_type}` → `VMDiskTask` async — `tools/vm.go:404-453`
  - `GET /vm/disk/task/{id}` → `VMDiskTask` (polling) — `tools/vm.go:455-471`
  - `DELETE /vm/disk/task/{id}` (cleanup obligatoire FS#30666) — `tools/vm.go:473-490`
- **Payload** : `VM` (id, name, status, memory, vcpus, disk_path b64, disk_type, os, enable_screen, enable_cloudinit, cloudinit_userdata, cd_path b64, bind_usb_ports). Validation : `validateDiskName` (`tools/validate.go:152-163`) ; `cloudinit_userdata` ≤ 4096 chars (firmware bug FS#37547, `tools/vm.go:74`). `enable_cloudinit` est dérivé automatiquement de la présence de `cloudinit_userdata` au create.
- **Idempotency key** : `name` (logique côté Ansible, `id` est généré par la box)
- **Type** : stateful CRUD + actions (start/stop/kill) + async sur disk operations
- **Async** : oui pour disk resize/create (VMDiskTask). Voir Pattern C.
- **Dépendances** : `disk_path`/`cd_path` doivent pointer vers un chemin valide (utiliser `storage` pour découvrir les partitions). Resize exige `status == "stopped"`.
- **Quirk** : `BindUSBPorts` (`tools/vm.go:23-37`) — l'API renvoie `""` au lieu de `[]` quand vide. Custom unmarshaler.
- **Notes Ansible** :
  - `freebox_vm` (déjà existant) — vérifier qu'il fait bien read-modify-write sur le PUT et que `state: present/absent/started/stopped/killed` est géré
  - `freebox_vm_disk` (déjà existant) — vérifier le polling async + DELETE final
  - `freebox_vm_info` (read-only listing)

### 24. vminfo

- **Endpoints** :
  - `GET /vm/info` (sans trailing slash !) — `VMInfo {used_cpus, total_cpus, used_memory, total_memory, usb_used, sata_used, usb_ports[], sata_ports[]}` — `tools/vminfo.go:40-52`
  - `GET /vm/distros/` — `[]VMDistro {name, os, url, hash}` (distros installables Free-hosted) — `tools/vminfo.go:54-65`
- **Payload** : agrégat de ressources VM
- **Type** : read-only
- **Notes Ansible** : `freebox_vm_info` (différent du listing — c'est l'agrégat ressources) + `freebox_vm_distros_info`. Utile pour valider `memory`/`vcpus` avant create.

### 25. system

- **Endpoints** :
  - `GET /system/` — `SystemInfo {mac, serial, uptime, uptime_val, board_name, firmware_version, disk_status, box_authenticated, sensors[], fans[]}` — `tools/system.go:44-56`
- **Payload** : voir struct ; capteurs en °C, ventilateurs en RPM
- **Type** : read-only
- **Notes Ansible** : `freebox_system_info` — bon candidat pour facts (Ansible `ansible_freebox_*`).

### 26. sysaction

- **Endpoints** :
  - `POST /system/reboot/` — pas de body — `tools/sysaction.go:18-29`
- **Payload** : action seule
- **Type** : action (singleton trigger)
- **Async** : implicite (la box reboot, prend ~2 min, mais pas de task)
- **Notes Ansible** : `freebox_reboot` — module style "action" avec `confirm: true` requis. Permettre `wait_for_reachable: true` avec timeout en option (re-check `/system/` jusqu'à retour).

### 27. switch

- **Endpoints** :
  - `GET /switch/status/` — `[]SwitchPortStatus {id, link, speed, duplex, mac_list[]}` — `tools/switch.go:32-43`
- **Payload** : voir struct ; `mac_list` = MAC + hostname vus sur ce port
- **Type** : read-only
- **Notes Ansible** : `freebox_switch_info`.

### 28. switchconfig

- **Endpoints** :
  - `GET /switch/port/{id}` — `SwitchPortConfig {id, duplex, speed}` (modes `auto`|`full`|`half`, `auto`|`10`|`100`|`1000`) — `tools/switchconfig.go:66-83`
  - `GET /switch/port/{id}/stats` — `SwitchStats` (compteurs Rx/Tx exhaustifs) — `tools/switchconfig.go:85-102`
- **Payload** : voir structs ; schéma `SwitchStats` validé runtime firmware 4.9.18.1
- **Type** : read-only ici
- **Idempotency key** : `id` (int) port
- **Notes Ansible** : `freebox_switch_port_info` (config + stats). PUT sur `/switch/port/{id}` (forcer vitesse/duplex) probable mais non exposé — à valider.

### 29. vpn

- **Endpoints** :
  - `GET /vpn/` — `[]VPNServer {type, name, state, connection_count, auth_connection_count}` (PPTP, OpenVPN routé/bridgé, IPsec IKEv2, WireGuard) — `tools/vpn.go:51-64`
  - `GET /vpn/connection/` — `[]VPNConnection {id, vpn, user, authenticated, auth_time, src_ip, src_port, local_ip, rx_bytes, tx_bytes}` — `tools/vpn.go:66-78`
  - `GET /vpn_client/config/` — `[]VPNClientConfig {id, description, active, type}` (config sortantes vers VPN externes) — `tools/vpn.go:80-92`
- **Payload** : voir structs
- **Type** : read-only ici
- **Notes Ansible** : `freebox_vpn_info` (états serveurs + connexions + client configs). **Lacune freebox-mcp** : pas de CRUD sur serveurs VPN (toggle, user management) ni sur `vpn_client/config` — l'API les supporte certainement. Gros chantier potentiel.

### 30. netshare

- **Endpoints** :
  - `GET /netshare/samba/` — `SambaConfig {file_share_enabled, print_share_enabled, logon_enabled, logon_user, workgroup}` — `tools/netshare.go:44-54`
  - `PUT /netshare/samba/` — patch partiel (map) — `tools/netshare.go:57-99`
  - `GET /netshare/samba/share/` — `[]SambaShare {id, name, path, readonly}` — `tools/netshare.go:101-113`
  - `GET /netshare/afp/` — `AFPConfig {enabled, guest_allow, server_type, login_name}` — `tools/netshare.go:115-127`
- **Type** : config singleton (samba GET+PUT, afp GET-only) + read-only listing samba shares
- **Idempotency key** : singleton ; `id` pour les shares
- **Notes Ansible** :
  - `freebox_samba_config` (singleton, partial PUT)
  - `freebox_afp_config_info` (GET ; PUT à valider empiriquement pour un module config)
  - `freebox_samba_share` — **Lacune freebox-mcp** : pas de CRUD share. À implémenter pour un module CRUD complet.

### 31. downloads

- **Endpoints** :
  - `GET /downloads/` — `[]Download {id, name, status, type, size, rx_bytes, tx_bytes, download_dir, ...}` — `tools/downloads.go:49-62`
  - `POST /downloads/add/` (`application/x-www-form-urlencoded`, param `download_url` !) — `tools/downloads.go:64-86`
  - `PUT /downloads/{id}` body map (`{status: stopped|downloading}`) — `tools/downloads.go:88-109`
  - `DELETE /downloads/{id}` (n'efface pas le fichier sur disque) — `tools/downloads.go:111-126`
- **Payload** : `status` ∈ `{stopped, seeding, downloading, done, error, checking, repairing, extracting, retry}`. `type` ∈ `{http, bt, nzb}`.
- **Idempotency key** : composite (`download_url` + `download_dir`) — pas de notion explicite côté API ; `id` attribué
- **Type** : stateful (CRUD avec PUT partiel)
- **Async** : non au niveau API (le téléchargement lui-même est asynchrone mais on poll via GET ; pas de task_id)
- **Sécurité** : `validateDownloadURL` (`tools/validate.go:82-102`) — blocklist loopback/link-local, schemes whitelist (http/https/magnet/nzb)
- **Notes Ansible** : `freebox_download` (state: present/absent/stopped/downloading) + `freebox_downloads_info` (listing).

### 32. downloadconfig

- **Endpoints** :
  - `GET /downloads/config/` — `DownloadConfig {max_downloading_tasks, download_dir(b64), watch_dir(b64), use_watch_dir, seed_ratio, stop_seeding_on_battery, scheduled_download, bw_normal, max_downloading_speed, max_uploading_speed}` — `tools/downloadconfig.go:40-53`
  - `PUT /downloads/config/` — patch partiel via map ; champ spécial `throttling.mode` ∈ `{normal, slow, hibernate, schedule}` — `tools/downloadconfig.go:55-117`
- **Payload** : voir struct ; paths en base64
- **Type** : config singleton (partial PUT)
- **Notes Ansible** : `freebox_download_config` (singleton).

### 33. calls

- **Endpoints** :
  - `GET /call/log/` — `[]CallEntry {id, type, number, name, duration, datetime, new}` (type ∈ `{accepted, missed, outgoing}`) — `tools/calls.go:29-42`
- **Type** : read-only
- **Notes Ansible** : `freebox_call_log_info`. **Lacune** : pas de DELETE / mark_as_read exposé — l'API les supporte (cf web UI). À découvrir.

### 34. parental

- **Endpoints** :
  - `GET /parental/config/` — `ParentalConfig {default_filter_mode}` (∈ `{allowed, denied, webonly}`) — `tools/parental.go:44-55`
  - `GET /parental/filter/{id}/planning` — `ParentalFilterPlanning {resolution, cdayranges[], mapping[]}` — `tools/parental.go:58-74`
  - `GET /parental/filter/` — `[]ParentalFilter {id, macs[], hosts[], desc, forced, forced_mode, tmp_mode, tmp_mode_expire, scheduling_mode, filter_state}` — `tools/parental.go:76-88`
- **Type** : read-only ici
- **Idempotency key** : `id` (int) ; `macs` côté filtre logique
- **Notes Ansible** : `freebox_parental_info`. **Lacune freebox-mcp** : pas de CRUD sur filtres parentaux — l'API les supporte certainement. À implémenter pour un module `freebox_parental_filter` CRUD.

### 35. contacts

- **Endpoints** :
  - `GET /contact/` — `[]Contact` — `tools/contacts.go:37-49`
  - `GET /contact/{id}/` — `Contact` détail — `tools/contacts.go:51-66`
- **Type** : read-only ici
- **Idempotency key** : `id` (int)
- **Notes Ansible** : `freebox_contacts_info`. CRUD non exposé — peu de valeur en automation infra (mais facile à ajouter pour complétude).

### 36. wol

- **Endpoints** :
  - `POST /lan/wol/{iface}/` body `WolRequest {mac, password}` (par défaut `iface=pub`) — `tools/wol.go:22-54`
- **Payload** : MAC validée (`validateMAC`), password SecureOn optionnel (`validateSecureOn`)
- **Type** : action (idempotente par nature — envoyer un WoL plusieurs fois est sans effet de bord)
- **Dépendances** : `iface` issu de `lan_interfaces` (mais hardcodé `pub` en défaut)
- **Notes Ansible** : `freebox_wol` — action module.

### 37. tv

- **Endpoints** :
  - `GET /tv/channels/` — `[]TVChannel {uuid, name, number, quality, logo_url}` — `tools/tv.go:38-50`
  - `GET /pvr/programmed/` — `[]TVRecord {id, name, start, end, channel_uuid, status, error}` — `tools/tv.go:52-64`
- **Type** : read-only
- **Notes Ansible** : `freebox_tv_info` (channels + programmed records). Peu de valeur pour homelab/PRA infra.

### 38. lcd

- **Endpoints** :
  - `GET /lcd/config/` — `LCDConfig {brightness, orientation_forced, orientation}` — `tools/lcd.go:24-36`
  - `PUT /lcd/config/` — patch partiel via map (`brightness` seul exposé) — `tools/lcd.go:38-55`
- **Type** : config singleton (Freebox Delta uniquement)
- **Notes Ansible** : `freebox_lcd` — singleton avec `brightness` (0-100) et possiblement `orientation` via PUT plus complet à valider.

### 39. airmedia

- **Endpoints** :
  - `GET /airmedia/config/` — `AirMediaConfig {enabled, password}` — `tools/airmedia.go:29-42`
  - `GET /airmedia/receivers/` — `[]AirMediaReceiver {name, password_protected, capabilities[]}` (capabilities ∈ `{photo, video, audio, screen}`) — `tools/airmedia.go:44-56`
- **Type** : read-only ici (config singleton + listing)
- **Notes Ansible** : `freebox_airmedia_info`. PUT sur config à valider empiriquement pour un module config.

---

## Synthèse de modules Ansible recommandés

Convention des types : **CRUD** = stateful ressource individuelle (state: present/absent) ; **config** = singleton (read-modify-write ou partial PUT) ; **info** = read-only ; **action** = idempotent par nature ou trigger one-shot.

| Module Ansible | Domaine source | Type | Idempotency key | Async ? |
|---|---|---|---|---|
| `freebox_facts` (ou `freebox_system_info` + `freebox_discover_info`) | discovery + system | info | n/a | non |
| `freebox_connection_info` | connection | info | n/a | non |
| `freebox_dyndns_info` | connection | info | n/a | non |
| `freebox_connection_config` | connectionconfig | config (partial PUT) | singleton | non |
| `freebox_connection_ipv6_info` | connectionipv6 | info | n/a | non |
| `freebox_connection_logs_info` | connectionlogs | info | n/a | non |
| `freebox_lan_hosts_info` | lan | info | n/a | non |
| `freebox_lan_interfaces_info` | lan | info | n/a | non |
| `freebox_lan_config_info` | lanconfig | info | singleton | non |
| `freebox_lan_host` | lanconfig | config (partial PUT par id) | `id` host | non |
| `freebox_dhcp_static_lease` | dhcp | CRUD | `mac` | non |
| `freebox_dhcp_dynamic_leases_info` | dhcp | info | n/a | non |
| `freebox_dhcp_config` | dhcpconfig | config (read-modify-write) | singleton | non |
| `freebox_dhcp_option` | dhcpconfig | CRUD sous-collection | `id` option | non |
| `freebox_dhcpv6_info` | dhcpv6 | info | singleton | non |
| `freebox_port_forward` | nat | CRUD | composite `(ip_proto, wan_port_start, wan_port_end)` | non |
| `freebox_firewall_incoming_info` | firewall | info | n/a | non |
| `freebox_firewall_dmz_info` | firewall | info | singleton | non |
| `freebox_firmware_update_info` | firmware | info | n/a | non |
| `freebox_ftp_info` | ftp | info | singleton | non |
| `freebox_tftp_info` | tftp | info | singleton | non |
| `freebox_upnp_info` | upnp | info | singleton | non |
| `freebox_upnp_rules_info` | upnp | info | n/a | non |
| `freebox_wifi_config` | wifi | config (partial PUT) | singleton | non |
| `freebox_wifi_aps_info` | wifi | info | n/a | non |
| `freebox_wifi_ssid` | wifibss | config (partial PUT par id) | `id` BSS | non |
| `freebox_wifi_stations_info` | wifibss | info | n/a | non |
| `freebox_wifi_mac_filter_info` | wifimacfilter | info | n/a | non |
| `freebox_wifi_planning_info` | wifiplanning | info | singleton | non |
| `freebox_storage_info` | storage | info | n/a | non |
| `freebox_fs_info` | filesystem | info | `path` | non |
| `freebox_fs_list` | filesystem | info | n/a | non |
| `freebox_fs_directory` | filesystem | CRUD (mkdir/rm) | `path` | oui (rm/mkdir) |
| `freebox_fs_file` (existant) | filesystem | CRUD | `path` | oui (rm) |
| `freebox_fs_copy` | filesystem | action | n/a | oui |
| `freebox_fs_move` | filesystem | action | n/a | oui |
| `freebox_fs_rename` | filesystem | action | n/a | non (synchrone) |
| `freebox_vm` (existant) | vm | CRUD + actions | `name` (logique) | oui sur disk ops |
| `freebox_vm_disk` (existant) | vm | action async | n/a (task_id) | oui |
| `freebox_vm_info` | vm + vminfo | info | n/a | non |
| `freebox_vm_distros_info` | vminfo | info | n/a | non |
| `freebox_reboot` | sysaction | action | trigger | implicite |
| `freebox_switch_info` | switch | info | n/a | non |
| `freebox_switch_port_info` | switchconfig | info | `id` port | non |
| `freebox_route` | network | CRUD (IPv4 uniquement exposé) | `id` route | non |
| `freebox_routes_info` | network | info | n/a | non |
| `freebox_vpn_info` | vpn | info | n/a | non |
| `freebox_samba_config` | netshare | config (partial PUT) | singleton | non |
| `freebox_samba_shares_info` | netshare | info | n/a | non |
| `freebox_afp_info` | netshare | info | singleton | non |
| `freebox_download` | downloads | CRUD | composite (url+dir) | non |
| `freebox_downloads_info` | downloads | info | n/a | non |
| `freebox_download_config` | downloadconfig | config (partial PUT) | singleton | non |
| `freebox_call_log_info` | calls | info | n/a | non |
| `freebox_parental_info` | parental | info | n/a | non |
| `freebox_contacts_info` | contacts | info | n/a | non |
| `freebox_wol` | wol | action | n/a | non |
| `freebox_tv_info` | tv | info | n/a | non |
| `freebox_lcd` | lcd | config (partial PUT) | singleton | non |
| `freebox_airmedia_info` | airmedia | info | singleton | non |

**Total** : ~58 modules potentiels en couvrant toute la surface lue, dont **~14 modules CRUD/config stateful** et **~38 modules `_info`**, plus quelques actions.

---

## Surprises / pièges identifiés

### Comptage des domaines

Le prompt initial liste **38 domaines** mais `tools/tools.go:33-74` enregistre **39 `register*`** (38 domaines + `registerDiscovery`). Discovery est listé dans la liste des fichiers infra du prompt mais c'est en réalité un domaine MCP-exposé (un outil utilisable comme les autres). À considérer comme un domaine à part entière côté Ansible (`freebox_discover_info` ou intégré à `freebox_facts`).

### Tasks async : trois shapes, pas un

Le pattern "task async" n'est pas uniforme côté Freebox OS. Trois shapes coexistent (voir Pattern C) :
- `FSTask` (string error, state enum)
- `VMDiskTask` (bool error, state vide en pratique)
- `string` brut pour `/fs/mkdir/`
- `/fs/rename/` est **synchrone** malgré son chemin `/fs/...`

Un helper Ansible `_poll_task()` doit accepter une stratégie d'évaluation de complétion (basée sur `state`, `done`, ou les deux).

### PUT non uniforme

`PUT /vm/{id}` **rejette** les patchs partiels (`invalid_request` si champ manquant). Confirmé issue #80 freebox-mcp. C'est la **seule** ressource qui a ce comportement parmi celles auditées — toutes les autres acceptent au moins le patch via map. Cela complique le helper de PUT côté Ansible : prévoir un opt-in `full_body` ou un read-modify-write toujours par défaut (sûr mais surcoûteux).

### Sentinelles JSON firmware

Trois cas documentés de désérialisation non-standard (firmware-side) :
- `BindUSBPorts` : `""` au lieu de `[]` (`tools/vm.go:23-37`)
- `L2Idents` : objet single au lieu de `[{...}]` (`tools/lan.go:31-53`)
- `DHCPOptions` : `{}` au lieu de `[]` (`tools/dhcpconfig.go:32-57`)

Probable d'en rencontrer d'autres. Côté Ansible, prévoir un helper de désérialisation tolérant (`as_list(x)` qui accepte `None | "" | {} | [x] | x`).

### Convention de path encoding

Le base64 standard **avec padding** (RFC 4648 §4) est obligatoire pour tous les paths du domaine `fs/` et les `disk_path`/`cd_path` des VMs. **Pas base64url**. Un piège classique côté Python serait d'utiliser `base64.urlsafe_b64encode` — ça échouera silencieusement (l'API n'invalide pas l'encodage mais cherche un path inexistant).

`/fs/info/?path=...` est un cas particulier : le base64 est passé en **query-string URL-encodée** (donc doublement encodé), pas en segment d'URL comme les autres endpoints `/fs/`.

### `download_url` vs `url`

`POST /downloads/add/` exige `Content-Type: application/x-www-form-urlencoded` ET le nom du paramètre est `download_url`, pas `url`. C'est la seule entrée form-encoded de tout l'API surface auditée. Source : `tools/downloads.go:36-47`.

### Validation MCP-side vs API-side

freebox-mcp implémente côté Go plusieurs validations qui sont **purement défensives, pas imposées par l'API** :
- `validateDHCPIP` rejette `.0`, `.1`, `.254`, `.255` (`tools/validate.go:127-144`)
- `validateRFC1918` impose RFC1918 sur `lan_ip` des règles NAT (`tools/validate.go:108-113`)
- `validateDownloadURL` blocklist loopback/link-local pour anti-SSRF (`tools/validate.go:82-102`)
- `validateDiskName` interdit `..`, `/`, `\` et impose extension `.qcow2|.raw` (`tools/validate.go:152-163`)
- `validateSecureOn` impose format MAC pour le password SecureOn (`tools/validate.go:57-68`)
- `maxCloudinitLen = 4096` (`tools/vm.go:74`) — c'est en revanche une limite **firmware** (FS#37547)

**Implication Ansible** : les modules **doivent re-implémenter** ces validations côté Python — l'API les laisserait probablement passer (avec parfois un effet de bord destructeur, ex. .254 = collision avec la box, ou un crash de la VM).

### Lacunes freebox-mcp (endpoints non exposés malgré probable support API)

À découvrir empiriquement lors de l'implémentation Ansible. freebox-mcp est délibérément focalisé sur les usages d'un opérateur — il n'a pas toujours implémenté les CRUD complets. Liste des suspicions fortes :

- **firewall** : aucun POST/PUT/DELETE sur `/fw/incoming/` ni `/fw/dmz/`. L'API doit les supporter (cohérence avec `/fw/redir/` qui est CRUD complet).
- **wifimacfilter** : aucun POST/DELETE sur `/wifi/mac_filter/`. Probablement supporté.
- **parental** : aucun CRUD sur `/parental/filter/` ni `/parental/config/` (PUT pour `default_filter_mode`). Probablement supporté.
- **vpn** : aucun CRUD sur serveurs VPN, utilisateurs VPN, ni `/vpn_client/config/`. Gros chantier.
- **wifibss** : seul `toggle` (`enabled`) exposé sur `PUT /wifi/bss/{id}`. PUT plus complet (SSID, encryption, hide_ssid) probablement supporté.
- **wifi/ap** : aucun PUT exposé. Configuration de canal/largeur/DFS probablement supportée.
- **routes IPv6** : GET-only sur `/network/route/ipv6/` (alors que IPv4 est CRUD complet dans le même fichier `tools/network.go`).
- **dyndns** : GET-only sur `/dynDns/`. CRUD probable côté API.
- **netshare/samba/share** : GET-only sur les partages. CRUD probable.
- **netshare/afp** : GET-only. PUT probable.
- **dhcpv6, ftp, tftp, upnp, lcd (orientation), airmedia, wifi planning, switch port config** : tous GET-only avec PUT probable côté API non exposé.
- **calls** : GET-only sur `/call/log/`. DELETE et mark-as-read côté API probables.
- **system update** : `GET /system/update/` exposé, mais pas d'action `apply`. Probablement disponible côté API (avec reboot async impliqué).

### Versions d'API mélangées dans les commentaires

Les structs sont annotées `/api/v4/...` ou `/api/v15/...` selon l'ancienneté du endpoint. **Le client n'utilise qu'un seul `baseURL`** qui inclut un préfixe de version. Pour l'Ansible, **un seul `api_version` (ou `base_url`) suffit** au niveau client — pas de routage par endpoint. La cohabitation est cosmétique.

### Sessions à courte durée

`auth/auth.go:166-167` utilise un TTL hardcodé de **25 minutes** (la doc dit ~30 min). Ce n'est pas configurable. Côté Ansible, si on enchaîne beaucoup de tâches sur un play long, le retry transparent sur `auth_required` (cf Pattern B) suffit normalement, mais à valider que le `FreeboxClient` Python le fait aussi.

### Comportement de `network`

`tools/network.go` mélange routes IPv4 (CRUD complet) et IPv6 (GET-only). C'est asymétrique et probablement un oubli côté freebox-mcp plutôt qu'une vraie limite API. Pour Ansible, garder un module unifié `freebox_route` avec un param `family: ipv4|ipv6` est probablement plus propre que deux modules séparés — mais valider que le POST IPv6 marche côté API.

### Pas de notion de "tags" ou de "labels" réutilisables

Aucun domaine n'expose un système de tags ou de catégorisation transverse. L'idempotence côté Ansible doit reposer uniquement sur les `id` natifs (numériques ou strings) ou sur des clés naturelles (mac, name, path, ip_proto+ports). Pour gérer des règles managées par Ansible distinctes des règles utilisateur, utiliser le champ `comment` comme convention (préfixer par `[ansible]` ou similaire) — c'est ce que fait freebox-mcp implicitement.

---
