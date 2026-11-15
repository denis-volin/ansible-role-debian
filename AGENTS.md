## Role overview

This Ansible role bootstraps and maintains the base configuration of headless Debian servers.
Most targets are VMs provisioned from official Debian cloud images or supplied by cloud providers such as Vultr.
The role is also used on Proxmox nodes.

The initial run typically targets a fresh server with no applications installed.
Subsequent runs apply configuration changes.

The role manages system-wide settings and services, including APT, the hostname, DNS, and time synchronization.
Its goal is to provide a consistent baseline across hosting environments — for example, by using the same time synchronization service regardless of the provider.
