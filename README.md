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
| `debian_host` | `ansible_host` | IP address written to the managed host line in `/etc/hosts`. |
| `debian_hostname` | `inventory_hostname` | FQDN set through `systemd-hostnamed` and written to `/etc/hosts`. |
| `debian_hostname_short` | `inventory_hostname_short` | Short hostname alias written to `/etc/hosts`. |
| `debian_hosts_extra` | `[]` | Additional raw lines rendered into `/etc/hosts`. |
| `debian_dns_servers` | `1.1.1.1`, `1.0.0.1` | DNS servers written to `/etc/resolv.conf`; disables `systemd-resolved` when installed. |
| `debian_search_domain` | derived from `debian_hostname` | Optional `search` domain written to `/etc/resolv.conf`. |
| `debian_locales` | `en_US.UTF-8` | Locales generated with `community.general.locale_gen`. |
| `debian_ntp_servers` | `0.pool.ntp.org` through `3.pool.ntp.org` | NTP servers configured in a `systemd-timesyncd` drop-in. |
| `debian_timezone` | `""` | Timezone to set, for example `Etc/UTC` or `Europe/Warsaw`. |
| `debian_setup_journald` | `true` | Enable persistent `journald` storage. |

## Example Playbook

```yaml
- name: Prepare Debian servers
  hosts: debian
  gather_facts: true
  become: true

  roles:
    - role: denis_volin.debian
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
