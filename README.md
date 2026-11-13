# Ansible Role: Debian

Normalize and prepare a Debian server.

This role configures common baseline settings for Debian hosts:

- APT repositories using `deb822_repository` module
- optional unattended upgrades
- optional package installation
- hostname and `/etc/hosts`
- static `/etc/resolv.conf` DNS configuration
- locale generation
- `systemd-timesyncd` NTP configuration
- timezone
- persistent `journald` logs

## Requirements & Dependencies

- Ansible `2.20.0` or newer.
- Debian `bookworm` or `trixie`.
- `community.general` collection for locale and timezone modules.

The role has no role dependencies.

## Role Variables

Defaults are documented inline in [`defaults/main.yml`](./defaults/main.yml).

Most features can be disabled by setting their variable to an empty value:

- `debian_apt_sources: []` skips APT source management.
- `debian_packages: []` skips extra package installation.
- `debian_hostname: ""` skips hostname management.
- `debian_dns_servers: []` skips `/etc/resolv.conf` management.
- `debian_locales: []` skips locale generation.
- `debian_ntp_servers: []` skips `systemd-timesyncd` setup.
- `debian_timezone: ""` skips timezone management.
- `debian_setup_upgrades: false` skips unattended upgrades.
- `debian_setup_journald: false` skips persistent journald setup.

### Main Variables

| Variable | Default | Description |
| --- | --- | --- |
| `debian_apt_mirror` | `deb.debian.org` | Debian mirror hostname used by default APT sources. |
| `debian_release` | target host distribution release | Debian codename used in APT suite names, such as `bookworm` or `trixie`. |
| `debian_apt_sources` | Debian, updates, backports, and security | Source definitions managed with `ansible.builtin.deb822_repository`. |
| `debian_setup_upgrades` | `true` | Install and enable `unattended-upgrades`. |
| `debian_packages` | `[]` | Extra packages to install after APT is configured. |
| `debian_host` | `127.0.1.1` | IP address written to the managed host line in `/etc/hosts`; override with a real node IP for Proxmox VE. |
| `debian_set_systemd_hostname` | `true` | Set the system hostname; `false` does not disable `/etc/hosts` management. |
| `debian_hostname` | `inventory_hostname` | Hostname set through `systemd-hostnamed` and written to `/etc/hosts`. |
| `debian_hostname_short` | first component of `debian_hostname` | Short hostname alias written to `/etc/hosts`; explicit overrides are preserved. |
| `debian_hosts_extra` | `[]` | Additional raw lines rendered into `/etc/hosts`. |
| `debian_dns_servers` | `1.1.1.1`, `1.0.0.1` | DNS servers written to `/etc/resolv.conf`; disables `systemd-resolved` when installed. |
| `debian_search_domain` | derived from `debian_hostname` | Optional `search` domain written to `/etc/resolv.conf`. |
| `debian_locales` | `en_US.UTF-8` | Locales generated with `community.general.locale_gen`. |
| `debian_ntp_servers` | `0.pool.ntp.org` through `3.pool.ntp.org` | NTP servers configured in a `systemd-timesyncd` drop-in. |
| `debian_timezone` | `""` | Timezone to set, for example `Etc/UTC` or `Europe/Warsaw`. |
| `debian_setup_journald` | `true` | Enable persistent `journald` storage. |

### Hostname and local resolution

By default, `debian_hostname: app.example.com` produces:

```text
127.0.1.1 app.example.com app
```

The short name follows `debian_hostname`, even when it differs from the inventory
alias. Single-label hostnames are written once, without a duplicate alias.
Explicit `debian_hostname_short` and `debian_host` values take precedence.

Setting `debian_hostname: ""` skips both setting the system hostname and managing
`/etc/hosts`. An empty `debian_host` or `debian_hostname_short` skips only
`/etc/hosts` management. Skipping leaves existing configuration unchanged.
Setting `debian_set_systemd_hostname: false` skips only the system hostname task;
the role still manages the entire `/etc/hosts` file when its inputs are nonempty.

**Breaking default change:** `debian_host` no longer follows `ansible_host`.
Set it explicitly if the hostname must resolve locally to a network address.

**Proxmox VE:** the node hostname must resolve to a reachable, non-loopback IP.
Do not use the loopback default for Proxmox nodes. For example, for an existing
node whose system hostname is already correct:

```yaml
debian_set_systemd_hostname: false
debian_hostname: pve1.example.com
debian_host: 192.0.2.20  # Replace with the node's actual management IP.
```

This writes `192.0.2.20 pve1.example.com pve1` without setting the system hostname.
See the [Proxmox hostname resolution requirements](https://pve.proxmox.com/wiki/Install_Proxmox_VE_on_Debian_13_Trixie#Ensure_Hostname_Resolves_to_Hosts_IP_Address).

Run the isolated hostname regression tests (no host configuration changes):

```bash
ansible-playbook -i localhost, -c local tests/hostname.yml
```

## Example Playbook

```yaml
- name: Prepare Debian servers
  hosts: debian
  gather_facts: true
  become: true

  roles:
    - role: denis-volin.debian
      vars:
        debian_packages:
          - curl
          - vim
```

## Role Tags

- `apt`: all APT configuration tasks.
- `sources`: APT sources.
- `unattended_upgrades`: automatic security upgrades.
- `packages`: optional package installation from `debian_packages`.
- `system`: hostname, hosts file, DNS, and locale tasks.
- `hostname`: hostname and `/etc/hosts`.
- `dns`: `systemd-resolved` disablement and `/etc/resolv.conf`.
- `locales`: locale generation.
- `time`: NTP and timezone tasks.
- `ntp`: `systemd-timesyncd` setup.
- `timezone`: timezone configuration.
- `logs`: persistent `journald` setup.

## License

MIT

## Author Information

Denis Volin (<denis@volin.me>)
