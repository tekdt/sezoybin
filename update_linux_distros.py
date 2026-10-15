#!/usr/bin/env python3
"""Refresh linux_distros.json from official distro pages.

Usage (run by hand or on a schedule):
    python update_linux_distros.py --check            # validate JSON only
    python update_linux_distros.py --update            # refresh all distros
    python update_linux_distros.py --update --distro kali
    python update_linux_distros.py --list              # show known distro specs

HOW TO ADD A NEW DISTRO YOURSELF (no new code for standard layouts):
  1. Append ONE dict to DISTRO_SPECS below (copy the closest example).
  2. Run:  python update_linux_distros.py --update --distro <new-id>
     The new distro entry is created in linux_distros.json automatically,
     with versions/editions/urls filled in from the scrape.
  3. Pick the kind that matches the distro's download layout:
     - "sums": a SHA256SUMS-style "hash  filename" file next to the ISOs
       (Ubuntu + flavors, Debian, Kali, Arch, Mint, Deepin, Asmi, Rocky, CentOS Stream).
     - "sidecar": a directory listing where each ISO has a sibling
       .sha256 file (openSUSE, antiX, CachyOS, Alpine, Mageia). Supports version-dir
       discovery for rolling releases (Tumbleweed snapshots).
     - "sourceforge": projects hosted on SourceForge (uses their
       best_release.json API, e.g. Winux, Q4OS, Bodhi Linux, SparkyLinux).
     - "fedora": Fedora's release-dir tree.
     - "tails": Tails official JSON release API.
     - "pop_os": Pop!_OS release page scraping.
     - "manual": anything exotic (email-gated downloads like Slax):
       the updater never touches it; edit the JSON entry by hand.

Rules:
  - A failing parser NEVER wipes existing data: that distro is skipped
    with a warning and its old entries are kept.
  - Merge, don't overwrite: new versions are added, known versions get
    their iso/urls/sha256/size refreshed, old versions are kept so SEZOY
    can still fall back to them.
  - Stdlib only (urllib + re + json): runs on any Python 3.8+ with no
    extra install, Windows or Linux.
"""

import argparse
import datetime
import io
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JSON = os.path.join(HERE, "linux_distros.json")
UA = {"User-Agent": "SEZOY-distro-updater/1.0 (+https://github.com/tekdt/sezoybin)"}


# ======================================================================
# DISTRO REGISTRY — adding a distro = appending one dict here.
# ======================================================================
# kind "sums": scrape one or more checksum files (GNU "hash  filename",
#   BSD "SHA256 (file) = hash" as in AlmaLinux CHECKSUM, sizes from
#   "# file: N bytes" comments) or {page + html: true} for pages with
#   direct ISO links but no sums file (Artix).
#   sources: [{sums: <url>, mirrors: [...]} | {page: <url>, html: true,
#     mirrors: [...]}]; urls[] = [mirror + filename] (failover).
#   discover (optional): find version dirs first, then build sources.
#     {url, dir_re (captures version), pick ("max" numeric or
#      "max-with-rows": newest dir whose sums file yields ISO rows —
#      skips beta/staging dirs), exclude_re (optional),
#      sums: <template with {ver}>, mirrors: <template list with {ver}>,
#      archs (optional): one source per arch with {arch}}.
#   rules: [{match (regex with (?P<ver>) + (?P<arch>)), edition,
#     edition_name, arch_map (optional, e.g. {"x64": "amd64"})}]
#     first matching rule wins; non-matching files are ignored.
# kind "sidecar": file listing + sibling checksum per ISO.
#   listings: [{listing: <dir url>, mirrors: [...], sha_base?}].
#   discover (optional): single version dir -> listing template.
#   discovers (optional): one entry per distro edition, each with its own
#     version-dir walk (Garuda/Manjaro style):
#     {url, dir_re, exclude_re?, file_page: <template {url}{ver}>
#      (page where ISO filenames are listed — may differ from the
#      download mirrors, e.g. a SourceForge folder),
#      mirrors: [...{ver}...], sha_base: <{url}{ver} template>,
#      edition/edition_name fixed, try_desc (default true)}.
#   version: discovered dir version wins, else (?P<ver>) from filename.
#   edition fixed per rule, or from a group via edition_from +
#   edition_map + edition_names. sha_suffix (default ".sha256");
#   sha512 sidecars (EndeavourOS .sha512sum) stored under "sha512".
#   skip_re drops alias/symlink duplicates; dedupe "max-iso" keeps the
#   highest filename per (version, arch) (Manjaro kernel variants).
# kind "sourceforge": {"project": <sf project>, rules: [...] (match on the
#   release filename), mirrors built as downloads.sourceforge.net + the
#   project files page}.
# kind "fedora": walk release dirs (params: root, editions).
# kind "manual": never touched by the updater; edit JSON by hand.
# ======================================================================

DISTRO_SPECS = [
    {
        "id": "ubuntu", "name": "Ubuntu",
        "site": "https://releases.ubuntu.com/",
        "kind": "sums",
        "sources": [
            {"sums": "https://releases.ubuntu.com/24.04/SHA256SUMS",
             "mirrors": ["https://releases.ubuntu.com/24.04/",
                         "https://releases.ubuntu.com/noble/"]},
        ],
        "rules": [
            {"match": r"ubuntu-(?P<ver>\d+\.\d+(?:\.\d+)?)-desktop-(?P<arch>amd64|arm64)\.iso",
             "edition": "desktop-lts", "edition_name": "Desktop LTS"},
            {"match": r"ubuntu-(?P<ver>\d+\.\d+(?:\.\d+)?)-live-server-(?P<arch>amd64|arm64)\.iso",
             "edition": "live-server", "edition_name": "Live Server"},
        ],
    },
    {
        "id": "debian", "name": "Debian",
        "site": "https://www.debian.org/distrib/",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/SHA256SUMS",
             "mirrors": ["https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/"]},
            {"sums": "https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/SHA256SUMS",
             "mirrors": ["https://cdimage.debian.org/debian-cd/current/amd64/iso-dvd/"]},
        ],
        "rules": [
            {"match": r"debian-(?P<ver>\d+\.\d+\.\d+)-(?P<arch>amd64)-netinst\.iso",
             "edition": "netinst", "edition_name": "Netinst (small net installer)"},
            {"match": r"debian-(?P<ver>\d+\.\d+\.\d+)-(?P<arch>amd64)-DVD-1\.iso",
             "edition": "dvd", "edition_name": "DVD (full offline set, disc 1)"},
        ],
    },
    {
        "id": "kali", "name": "Kali Linux",
        "site": "https://www.kali.org/get-kali/",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.kali.org/current/SHA256SUMS",
             "mirrors": ["https://cdimage.kali.org/current/"]},
        ],
        "rules": [
            {"match": r"kali-linux-(?P<ver>\d+\.\d+)-installer-(?P<arch>amd64|arm64)\.iso",
             "edition": "installer", "edition_name": "Installer (full offline)"},
            {"match": r"kali-linux-(?P<ver>\d+\.\d+)-installer-netinst-(?P<arch>amd64|arm64)\.iso",
             "edition": "netinst", "edition_name": "NetInstaller (small)"},
            {"match": r"kali-linux-(?P<ver>\d+\.\d+)-live-(?P<arch>amd64|arm64)\.iso",
             "edition": "live", "edition_name": "Live (try without installing)"},
        ],
    },
    {
        "id": "arch", "name": "Arch Linux",
        "site": "https://archlinux.org/download/",
        "kind": "sums",
        "sources": [
            {"sums": "https://geo.mirror.pkgbuild.com/iso/latest/sha256sums.txt",
             "mirrors": ["https://geo.mirror.pkgbuild.com/iso/latest/",
                         "https://mirror.rackspace.com/archlinux/iso/latest/"]},
        ],
        "rules": [
            {"match": r"archlinux-(?P<ver>\d+\.\d+\.\d+)-(?P<arch>x86_64)\.iso",
             "edition": "base", "edition_name": "Base ISO (monthly snapshot)"},
        ],
    },
    {
        "id": "mint", "name": "Linux Mint",
        "site": "https://linuxmint.com/download.php",
        "kind": "sums",
        "discover": {
            "url": "https://mirrors.kernel.org/linuxmint/stable/",
            "dir_re": r'href="(\d+(?:\.\d+)?)/"',
            "pick": "max-with-rows",
            "sums": "https://mirrors.kernel.org/linuxmint/stable/{ver}/sha256sum.txt",
            "mirrors": ["https://mirrors.kernel.org/linuxmint/stable/{ver}/",
                        "https://mirror.clarkson.edu/linuxmint-images/stable/{ver}/"],
        },
        "rules": [
            {"match": r"linuxmint-(?P<ver>\d+(?:\.\d+)?)-cinnamon-64bit\.iso",
             "edition": "cinnamon", "edition_name": "Cinnamon (flagship)"},
            {"match": r"linuxmint-(?P<ver>\d+(?:\.\d+)?)-mate-64bit\.iso",
             "edition": "mate", "edition_name": "MATE (classic desktop)"},
            {"match": r"linuxmint-(?P<ver>\d+(?:\.\d+)?)-xfce-64bit\.iso",
             "edition": "xfce", "edition_name": "Xfce (lightweight)"},
        ],
        "default_arch": "amd64",
    },
    {
        "id": "kubuntu", "name": "Kubuntu",
        "site": "https://kubuntu.org/getkubuntu/",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.ubuntu.com/kubuntu/releases/24.04/release/SHA256SUMS",
             "mirrors": ["https://cdimage.ubuntu.com/kubuntu/releases/24.04/release/"]},
        ],
        "rules": [
            {"match": r"kubuntu-(?P<ver>\d+\.\d+(?:\.\d+)?)-desktop-(?P<arch>amd64|arm64)\.iso",
             "edition": "desktop-lts", "edition_name": "Desktop LTS (KDE Plasma)"},
        ],
    },
    {
        "id": "lubuntu", "name": "Lubuntu",
        "site": "https://lubuntu.me/downloads/",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.ubuntu.com/lubuntu/releases/24.04/release/SHA256SUMS",
             "mirrors": ["https://cdimage.ubuntu.com/lubuntu/releases/24.04/release/"]},
        ],
        "rules": [
            {"match": r"lubuntu-(?P<ver>\d+\.\d+(?:\.\d+)?)-desktop-(?P<arch>amd64|arm64)\.iso",
             "edition": "desktop-lts", "edition_name": "Desktop LTS (LXQt)"},
        ],
    },
    {
        "id": "xubuntu", "name": "Xubuntu",
        "site": "https://xubuntu.org/download/",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.ubuntu.com/xubuntu/releases/24.04/release/SHA256SUMS",
             "mirrors": ["https://cdimage.ubuntu.com/xubuntu/releases/24.04/release/"]},
        ],
        "rules": [
            {"match": r"xubuntu-(?P<ver>\d+\.\d+(?:\.\d+)?)-desktop-(?P<arch>amd64|arm64)\.iso",
             "edition": "desktop-lts", "edition_name": "Desktop LTS (Xfce)"},
        ],
    },
    {
        "id": "opensuse-leap", "name": "openSUSE Leap",
        "site": "https://get.opensuse.org/leap/",
        "kind": "sidecar",
        "discover": {
            "url": "https://download.opensuse.org/distribution/leap/",
            "dir_re": r'href="\./([\d.]+)/"',
            "exclude_re": r"^42\.",
            "try_desc": True,
            "listing": "{url}{ver}/iso/",
            "mirrors": ["{url}{ver}/iso/"],
        },
        "default_arch": "x86_64",
        "skip_re": r"-(NET|DVD)-x86_64-Media\.iso$",
        "rules": [
            {"match": r"openSUSE-Leap-.*-(?P<ed>NET|DVD)-x86_64-.*\.iso",
             "edition_from": "ed",
             "edition_map": {"NET": "net", "DVD": "dvd"}},
        ],
        "edition_names": {"net": "Net installer", "dvd": "Full DVD"},
    },
    {
        "id": "opensuse-tumbleweed", "name": "openSUSE Tumbleweed",
        "site": "https://get.opensuse.org/tumbleweed/",
        "kind": "sidecar",
        "keep": 3,
        "listings": [
            {"listing": "https://download.opensuse.org/tumbleweed/iso/",
             "mirrors": ["https://download.opensuse.org/tumbleweed/iso/"]},
        ],
        "default_arch": "x86_64",
        "rules": [
            {"match": r"openSUSE-Tumbleweed-(?P<ed>DVD|NET)-x86_64-Snapshot(?P<ver>\d+)-Media\.iso",
             "edition_from": "ed",
             "edition_map": {"DVD": "dvd", "NET": "net"}},
        ],
        "edition_names": {"dvd": "DVD snapshot", "net": "Net installer snapshot"},
    },
    {
        "id": "antix", "name": "antiX Linux",
        "site": "https://antixlinux.com/download/",
        "kind": "sidecar",
        "discover": {
            "url": "https://mirror.math.princeton.edu/pub/mxlinux-iso/ANTIX/Final/",
            "dir_re": r'href="antiX-([\d.]+)/"',
            "listing": "{url}antiX-{ver}/",
            "mirrors": ["{url}antiX-{ver}/"],
        },
        "rules": [
            {"match": r"antiX-(?P<ver>[\d.]+)_(?P<arch>x64|386|arm64)-(?P<ed>full|base|core|net)\.iso",
             "edition_from": "ed",
             "edition_map": {"full": "full", "base": "base",
                             "core": "core", "net": "net"},
             "arch_map": {"x64": "amd64", "386": "i386"}},
        ],
        "edition_names": {"full": "Full", "base": "Base",
                          "core": "Core (no X)", "net": "Net (minimal)"},
    },
    {
        "id": "cachyos", "name": "CachyOS",
        "site": "https://cachyos.org/download/",
        "kind": "sidecar",
        "keep": 2,
        "discover": {
            "url": "https://mirror.cachyos.org/ISO/desktop/",
            "dir_re": r'href="(\d+)/"',
            "listing": "{url}{ver}/",
            "mirrors": ["https://mirror.cachyos.org/ISO/desktop/{ver}/"],
        },
        "default_arch": "x86_64",
        "rules": [
            {"match": r"cachyos-desktop-linux-(?P<ver>\d+)\.iso",
             "edition": "desktop", "edition_name": "Desktop (online installer)"},
        ],
    },
    {
        "id": "deepin", "name": "Deepin",
        "site": "https://www.deepin.org/en/download/",
        "kind": "sums",
        "discover": {
            "url": "https://cdimage.deepin.com/releases/",
            "dir_re": r'href="(\d+(?:\.\d+)+)/"',
            "pick": "max-with-rows",
            "sums": "https://cdimage.deepin.com/releases/{ver}/{arch}/SHA256SUMS",
            "mirrors": ["https://cdimage.deepin.com/releases/{ver}/{arch}/"],
            "archs": ["amd64", "arm64"],
        },
        "rules": [
            {"match": r"deepin-desktop-community-(?P<ver>\d+(?:\.\d+)+)-(?P<arch>amd64|arm64|loong64|riscv64)\.iso",
             "edition": "desktop", "edition_name": "Desktop Community"},
        ],
    },
    {
        "id": "asmi", "name": "Asmi Linux",
        "site": "https://teejeetech.com/asmi",
        "kind": "sums",
        "sources": [
            {"sums": "https://dl.teejeetech.com/asmi/sha256sum.txt",
             "mirrors": ["https://dl.teejeetech.com/asmi/"]},
        ],
        "rules": [
            {"match": r"asmi-linux-(?P<ver>13(?:\.\d+)?)-amd64\.iso",
             "edition": "debian", "edition_name": "Debian-based (Xfce)"},
            {"match": r"asmi-linux-(?P<ver>2\d\.\d+(?:\.\d+)?)-amd64\.iso",
             "edition": "ubuntu", "edition_name": "Ubuntu-based (Xfce)"},
        ],
    },
    {
        "id": "winux", "name": "Winux (Wubuntu)",
        "site": "https://www.winux.is/download/",
        "kind": "sourceforge",
        "project": "windows-linux",
        "rules": [
            {"match": r"winux-(?P<ver>\d+\.\d+\.\d+)-\w+-lts\.iso",
             "edition": "lts", "edition_name": "LTS (Windows-like)"},
        ],
    },
    {
        "id": "mx", "name": "MX Linux",
        "site": "https://mxlinux.org/download-links/",
        "kind": "sidecar",
        "skip_re": "ahs",
        "listings": [
            {"listing": "https://mirror.math.princeton.edu/pub/mxlinux-iso/MX/Final/Xfce/",
             "mirrors": ["https://mirror.math.princeton.edu/pub/mxlinux-iso/MX/Final/Xfce/",
                         "https://downloads.sourceforge.net/project/mx-linux/MX/Final/Xfce/"]},
            {"listing": "https://mirror.math.princeton.edu/pub/mxlinux-iso/MX/Final/KDE/",
             "mirrors": ["https://mirror.math.princeton.edu/pub/mxlinux-iso/MX/Final/KDE/",
                         "https://downloads.sourceforge.net/project/mx-linux/MX/Final/KDE/"]},
            {"listing": "https://mirror.math.princeton.edu/pub/mxlinux-iso/MX/Final/Fluxbox/",
             "mirrors": ["https://mirror.math.princeton.edu/pub/mxlinux-iso/MX/Final/Fluxbox/",
                         "https://downloads.sourceforge.net/project/mx-linux/MX/Final/Fluxbox/"]},
        ],
        "default_arch": "amd64",
        "rules": [
            {"match": r"MX-(?P<ver>\d+\.\d+)_Xfce_x64\.iso",
             "edition": "xfce", "edition_name": "Xfce (flagship)"},
            {"match": r"MX-(?P<ver>\d+\.\d+)_KDE_x64\.iso",
             "edition": "kde", "edition_name": "KDE Plasma"},
            {"match": r"MX-(?P<ver>\d+\.\d+)_[Ff]luxbox_(?:x64|386)\.iso",
             "edition": "fluxbox", "edition_name": "Fluxbox (lightweight)"},
        ],
    },
    {
        "id": "endeavouros", "name": "EndeavourOS",
        "site": "https://endeavouros.com/",
        "kind": "sidecar",
        "keep": 2,
        "sha_suffix": ".sha512sum",
        "listings": [
            {"listing": "https://mirror.moson.org/endeavouros/iso/",
             "mirrors": ["https://mirror.moson.org/endeavouros/iso/"]},
        ],
        "default_arch": "x86_64",
        "rules": [
            {"match": r"EndeavourOS_.*?-(?P<ver>\d{4}\.\d{2}\.\d{2})\.iso",
             "edition": "rolling", "edition_name": "Rolling ISO (monthly)"},
        ],
    },
    {
        "id": "garuda", "name": "Garuda Linux",
        "site": "https://garudalinux.org/downloads",
        "kind": "sidecar",
        "keep": 2,
        "discovers": [
            {"url": "https://iso.builds.garudalinux.org/iso/garuda/mokka/",
             "dir_re": r'href="(\d+)/"',
             "file_page": "{url}{ver}/",
             "mirrors": ["https://iso.builds.garudalinux.org/iso/garuda/mokka/{ver}/"],
             "edition": "mokka", "edition_name": "Mokka (KDE)"},
            {"url": "https://iso.builds.garudalinux.org/iso/garuda/dr460nized/",
             "dir_re": r'href="(\d+)/"',
             "file_page": "{url}{ver}/",
             "mirrors": ["https://iso.builds.garudalinux.org/iso/garuda/dr460nized/{ver}/"],
             "edition": "dr460nized", "edition_name": "Dr460nized (KDE gaming)"},
            {"url": "https://iso.builds.garudalinux.org/iso/garuda/gnome/",
             "dir_re": r'href="(\d+)/"',
             "file_page": "{url}{ver}/",
             "mirrors": ["https://iso.builds.garudalinux.org/iso/garuda/gnome/{ver}/"],
             "edition": "gnome", "edition_name": "GNOME"},
        ],
        "default_arch": "x86_64",
        "rules": [
            {"match": r"garuda-(?:mokka|dr460nized|gnome)-linux-garuda-(?P<ver>\d+)\.iso",
             "edition": "x", "edition_name": "x"},
        ],
    },
    {
        "id": "manjaro", "name": "Manjaro",
        "site": "https://manjaro.org/download/",
        "kind": "sidecar",
        "skip_re": "minimal",
        "dedupe": "max-iso",
        "discovers": [
            {"url": "https://sourceforge.net/projects/manjarolinux/files/kde/",
             "dir_re": r"/projects/manjarolinux/files/kde/(\d+\.\d+(?:\.\d+)?)/",
             "file_page": "https://sourceforge.net/projects/manjarolinux/files/kde/{ver}/",
             "mirrors": ["https://download.manjaro.org/kde/{ver}/",
                         "https://downloads.sourceforge.net/project/manjarolinux/kde/{ver}/"],
             "sha_base": "https://download.manjaro.org/kde/{ver}/",
             "edition": "kde", "edition_name": "KDE Plasma"},
            {"url": "https://sourceforge.net/projects/manjarolinux/files/xfce/",
             "dir_re": r"/projects/manjarolinux/files/xfce/(\d+\.\d+(?:\.\d+)?)/",
             "file_page": "https://sourceforge.net/projects/manjarolinux/files/xfce/{ver}/",
             "mirrors": ["https://download.manjaro.org/xfce/{ver}/",
                         "https://downloads.sourceforge.net/project/manjarolinux/xfce/{ver}/"],
             "sha_base": "https://download.manjaro.org/xfce/{ver}/",
             "edition": "xfce", "edition_name": "Xfce"},
            {"url": "https://sourceforge.net/projects/manjarolinux/files/gnome/",
             "dir_re": r"/projects/manjarolinux/files/gnome/(\d+\.\d+(?:\.\d+)?)/",
             "file_page": "https://sourceforge.net/projects/manjarolinux/files/gnome/{ver}/",
             "mirrors": ["https://download.manjaro.org/gnome/{ver}/",
                         "https://downloads.sourceforge.net/project/manjarolinux/gnome/{ver}/"],
             "sha_base": "https://download.manjaro.org/gnome/{ver}/",
             "edition": "gnome", "edition_name": "GNOME"},
        ],
        "default_arch": "x86_64",
        "rules": [
            {"match": r"manjaro-(?:kde|xfce|gnome)-(?P<ver>\d+\.\d+(?:\.\d+)?)-\d+-linux\d+\.iso",
             "edition": "x", "edition_name": "x"},
        ],
    },
    {
        "id": "artix", "name": "Artix Linux",
        "site": "https://artixlinux.org/download.php",
        "kind": "sums",
        "keep": 2,
        "sources": [
            {"page": "https://download.artixlinux.org/iso/", "html": True,
             "mirrors": ["https://download.artixlinux.org/iso/"]},
        ],
        "rules": [
            {"match": r"artix-base-openrc-(?P<ver>\d{8})-x86_64\.iso",
             "edition": "base", "edition_name": "Base (OpenRC)"},
            {"match": r"artix-cinnamon-openrc-(?P<ver>\d{8})-x86_64\.iso",
             "edition": "cinnamon", "edition_name": "Cinnamon (OpenRC)"},
            {"match": r"artix-gnome-openrc-(?P<ver>\d{8})-x86_64\.iso",
             "edition": "gnome", "edition_name": "GNOME (OpenRC)"},
            {"match": r"artix-mate-openrc-(?P<ver>\d{8})-x86_64\.iso",
             "edition": "mate", "edition_name": "MATE (OpenRC)"},
            {"match": r"artix-plasma-openrc-(?P<ver>\d{8})-x86_64\.iso",
             "edition": "plasma", "edition_name": "Plasma (OpenRC)"},
            {"match": r"artix-xfce-openrc-(?P<ver>\d{8})-x86_64\.iso",
             "edition": "xfce", "edition_name": "Xfce (OpenRC)"},
        ],
    },
    {
        "id": "void", "name": "Void Linux",
        "site": "https://voidlinux.org/download/",
        "kind": "sums",
        "sources": [
            {"sums": "https://repo-default.voidlinux.org/live/current/sha256sum.txt",
             "mirrors": ["https://repo-default.voidlinux.org/live/current/"]},
        ],
        "rules": [
            {"match": r"void-live-(?P<arch>x86_64)-(?P<ver>\d{8})-(?P<ed>base|xfce)\.iso",
             "edition_from": "ed", "edition_name": "",
             "edition": "", "edition_map": {"base": "base", "xfce": "xfce"}},
        ],
        "edition_names": {"base": "Base (no desktop)", "xfce": "Xfce"},
    },
    {
        "id": "devuan", "name": "Devuan",
        "site": "https://www.devuan.org/get-devuan",
        "kind": "sums",
        "sources": [
            {"sums": "https://files.devuan.org/devuan_daedalus/desktop-live/SHA256SUMS.txt",
             "mirrors": ["https://files.devuan.org/devuan_daedalus/desktop-live/"]},
        ],
        "rules": [
            {"match": r"devuan_daedalus_(?P<ver>[\d.]+)_(?P<arch>amd64|i386)_desktop-live\.iso",
             "edition": "desktop-live", "edition_name": "Desktop Live (Daedalus)"},
        ],
    },
    {
        "id": "almalinux", "name": "AlmaLinux OS",
        "site": "https://almalinux.org/get-linux/",
        "kind": "sums",
        "skip_re": "-latest-",
        "sources": [
            {"sums": "https://repo.almalinux.org/almalinux/9/isos/x86_64/CHECKSUM",
             "mirrors": ["https://repo.almalinux.org/almalinux/9/isos/x86_64/"]},
            {"sums": "https://repo.almalinux.org/almalinux/10/isos/x86_64/CHECKSUM",
             "mirrors": ["https://repo.almalinux.org/almalinux/10/isos/x86_64/"]},
        ],
        "rules": [
            {"match": r"AlmaLinux-(?P<ver>\d+\.\d+)-x86_64-(?P<ed>dvd|boot|minimal)\.iso",
             "edition_from": "ed", "edition_name": "",
             "edition": "", "edition_map": {"dvd": "dvd", "boot": "boot", "minimal": "minimal"}},
        ],
        "edition_names": {"dvd": "DVD (full)", "boot": "Boot (net installer)",
                          "minimal": "Minimal"},
    },
    {
        "id": "parrot", "name": "Parrot OS",
        "site": "https://parrotsec.org/download/",
        "kind": "sums",
        "torrent_probe": True,
        "discover": {
            "url": "https://parrotsec.org/download/?edition=home",
            "dir_re": r"/parrot/iso/([\d.]+)/",
            "pick": "max",
            "sums": "https://deb.parrot.sh/parrot/iso/{ver}/signed-hashes.txt",
            "mirrors": ["https://deb.parrot.sh/parrot/iso/{ver}/"],
        },
        "rules": [
            {"match": r"Parrot-(?P<ed>home|security|security-tuned)-(?P<ver>[\d.]+)_(?P<arch>amd64|arm64)\.iso",
             "edition_from": "ed",
             "edition_map": {"home": "home", "security": "security",
                             "security-tuned": "security-tuned"}},
            {"match": r"Parrot-spin-(?P<ed2>[a-z]+)-(?P<ver>[\d.]+)_(?P<arch>amd64|arm64)\.iso",
             "edition_from": "ed2",
             "edition_map": {"mate": "spin-mate", "lxqt": "spin-lxqt",
                             "htb": "spin-htb",
                             "enlightenment": "spin-enlightenment"}},
        ],
        "edition_names": {"home": "Home", "security": "Security",
                          "security-tuned": "Security Tuned",
                          "spin-mate": "Spin MATE", "spin-lxqt": "Spin LXQt",
                          "spin-htb": "Spin HTB",
                          "spin-enlightenment": "Spin Enlightenment"},
    },
    {
        "id": "zorin", "name": "Zorin OS",
        "site": "https://zorin.com/os/download/",
        "kind": "sums",
        "skip_re": "Beta",
        "sources": [
            {"sums": "https://mirror.kumi.systems/zorinos/18/SHA256SUMS.txt",
             "mirrors": ["https://mirror.kumi.systems/zorinos/18/",
                         "https://mirror.clarkson.edu/zorinos/isos/18/"]},
        ],
        "rules": [
            {"match": r"Zorin-OS-(?P<ver>\d+(?:\.\d+)?)-(?P<ed>Core|Education|Lite)-64-bit(?P<rspin>-r\d+)?\.iso",
             "ver_suffix_from": "rspin",
             "edition_from": "ed",
             "edition_map": {"Core": "core", "Education": "education",
                             "Lite": "lite"}},
        ],
        "edition_names": {"core": "Core", "education": "Education",
                          "lite": "Lite (Xfce)"},
    },
    {
        "id": "fedora", "name": "Fedora",
        "site": "https://fedoraproject.org/workstation/download",
        "kind": "fedora",
        "root": "https://download.fedoraproject.org/pub/fedora/linux/releases/",
        "editions": [
            ("workstation-live", "Workstation Live", "Workstation"),
            ("server-dvd", "Server DVD", "Server"),
        ],
    },
    {
        "id": "rocky", "name": "Rocky Linux",
        "site": "https://rockylinux.org/download",
        "kind": "sums",
        "skip_re": r"-latest-",
        "sources": [
            {"sums": "https://download.rockylinux.org/pub/rocky/9/isos/x86_64/CHECKSUM",
             "mirrors": ["https://download.rockylinux.org/pub/rocky/9/isos/x86_64/"]},
            {"sums": "https://download.rockylinux.org/pub/rocky/10/isos/x86_64/CHECKSUM",
             "mirrors": ["https://download.rockylinux.org/pub/rocky/10/isos/x86_64/"]},
        ],
        "rules": [
            {"match": r"Rocky-(?P<ver>\d+\.\d+)-x86_64-(?P<ed>dvd1?|boot|minimal)\.iso",
             "edition_from": "ed", "edition_name": "",
             "edition": "", "edition_map": {"dvd": "dvd", "dvd1": "dvd", "boot": "boot", "minimal": "minimal"}},
        ],
        "edition_names": {"dvd": "DVD (full)", "boot": "Boot (net installer)",
                          "minimal": "Minimal"},
    },
    {
        "id": "centos-stream", "name": "CentOS Stream",
        "site": "https://www.centos.org/download/",
        "kind": "sums",
        "skip_re": r"-latest-",
        "sources": [
            {"sums": "https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/iso/SHA256SUM",
             "mirrors": ["https://mirror.stream.centos.org/9-stream/BaseOS/x86_64/iso/"]},
            {"sums": "https://mirror.stream.centos.org/10-stream/BaseOS/x86_64/iso/SHA256SUM",
             "mirrors": ["https://mirror.stream.centos.org/10-stream/BaseOS/x86_64/iso/"]},
        ],
        "rules": [
            {"match": r"CentOS-Stream-(?P<ver>\d+-\d{8}\.\d+)-x86_64-(?P<ed>dvd1?|boot)\.iso",
             "edition_from": "ed", "edition_name": "",
             "edition": "", "edition_map": {"dvd": "dvd", "dvd1": "dvd", "boot": "boot"}},
        ],
        "edition_names": {"dvd": "DVD (full)", "boot": "Boot (net installer)"},
    },
    {
        "id": "alpine", "name": "Alpine Linux",
        "site": "https://alpinelinux.org/downloads/",
        "kind": "sidecar",
        "listings": [
            {"listing": "https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/",
             "mirrors": ["https://dl-cdn.alpinelinux.org/alpine/latest-stable/releases/x86_64/"]},
        ],
        "skip_re": r"(_rc\d|-xen|-virt)",
        "dedupe": "max-iso",
        "default_arch": "x86_64",
        "rules": [
            {"match": r"alpine-(?P<ed>standard|extended)-(?P<ver>[\d.]+)-x86_64\.iso",
             "edition_from": "ed",
             "edition_map": {"standard": "standard", "extended": "extended"}},
        ],
        "edition_names": {"standard": "Standard (console only)",
                          "extended": "Extended (extra packages)"},
    },
    {
        "id": "pop-os", "name": "Pop!_OS",
        "site": "https://system76.com/pop/",
        "kind": "pop_os",
        "url": "https://system76.com/pop/download/",
    },
    {
        "id": "tails", "name": "Tails",
        "site": "https://tails.net/",
        "kind": "tails",
        "api": "https://tails.net/install/v2/Tails/amd64/stable/latest.json",
        "mirror_base": "https://mirrors.edge.kernel.org/tails/stable/",
    },
    {
        "id": "ubuntu-mate", "name": "Ubuntu MATE",
        "site": "https://ubuntu-mate.org/download/",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.ubuntu.com/ubuntu-mate/releases/24.04/release/SHA256SUMS",
             "mirrors": ["https://cdimage.ubuntu.com/ubuntu-mate/releases/24.04/release/"]},
        ],
        "rules": [
            {"match": r"ubuntu-mate-(?P<ver>\d+\.\d+(?:\.\d+)?)-desktop-(?P<arch>amd64|arm64)\.iso",
             "edition": "desktop-lts", "edition_name": "Desktop LTS (MATE)"},
        ],
    },
    {
        "id": "ubuntu-budgie", "name": "Ubuntu Budgie",
        "site": "https://ubuntubudgie.org/downloads/",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.ubuntu.com/ubuntu-budgie/releases/24.04/release/SHA256SUMS",
             "mirrors": ["https://cdimage.ubuntu.com/ubuntu-budgie/releases/24.04/release/"]},
        ],
        "rules": [
            {"match": r"ubuntu-budgie-(?P<ver>\d+\.\d+(?:\.\d+)?)-desktop-(?P<arch>amd64|arm64)\.iso",
             "edition": "desktop-lts", "edition_name": "Desktop LTS (Budgie)"},
        ],
    },
    {
        "id": "ubuntustudio", "name": "Ubuntu Studio",
        "site": "https://ubuntustudio.org/download/",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.ubuntu.com/ubuntustudio/releases/24.04/release/SHA256SUMS",
             "mirrors": ["https://cdimage.ubuntu.com/ubuntustudio/releases/24.04/release/"]},
        ],
        "rules": [
            {"match": r"ubuntustudio-(?P<ver>\d+\.\d+(?:\.\d+)?)-dvd-(?P<arch>amd64)\.iso",
             "edition": "dvd-lts", "edition_name": "DVD LTS (Creative Suite)"},
        ],
    },
    {
        "id": "ubuntukylin", "name": "Ubuntu Kylin",
        "site": "https://www.ubuntukylin.com/downloads/",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.ubuntu.com/ubuntukylin/releases/24.04/release/SHA256SUMS",
             "mirrors": ["https://cdimage.ubuntu.com/ubuntukylin/releases/24.04/release/"]},
        ],
        "rules": [
            {"match": r"ubuntukylin-(?P<ver>\d+\.\d+(?:\.\d+)?)-desktop-(?P<arch>amd64)\.iso",
             "edition": "desktop-lts", "edition_name": "Desktop LTS (UKUI)"},
        ],
    },
    {
        "id": "edubuntu", "name": "Edubuntu",
        "site": "https://www.edubuntu.org/download",
        "kind": "sums",
        "sources": [
            {"sums": "https://cdimage.ubuntu.com/edubuntu/releases/24.04/release/SHA256SUMS",
             "mirrors": ["https://cdimage.ubuntu.com/edubuntu/releases/24.04/release/"]},
        ],
        "rules": [
            {"match": r"edubuntu-(?P<ver>\d+\.\d+(?:\.\d+)?)-desktop-(?P<arch>amd64)\.iso",
             "edition": "desktop-lts", "edition_name": "Desktop LTS (Education)"},
        ],
    },
    {
        "id": "mageia", "name": "Mageia",
        "site": "https://www.mageia.org/en/downloads/",
        "kind": "sidecar",
        "sha_suffix": ".sha512",
        "discovers": [
            {"url": "https://mirrors.kernel.org/mageia/iso/",
             "dir_re": r'href="(\d+)/"',
             "file_page": "{url}{ver}/Mageia-{ver}-Live-GNOME-x86_64/",
             "mirrors": ["https://mirrors.kernel.org/mageia/iso/{ver}/Mageia-{ver}-Live-GNOME-x86_64/"],
             "edition": "gnome", "edition_name": "GNOME Live"},
            {"url": "https://mirrors.kernel.org/mageia/iso/",
             "dir_re": r'href="(\d+)/"',
             "file_page": "{url}{ver}/Mageia-{ver}-Live-Plasma-x86_64/",
             "mirrors": ["https://mirrors.kernel.org/mageia/iso/{ver}/Mageia-{ver}-Live-Plasma-x86_64/"],
             "edition": "plasma", "edition_name": "Plasma Live"},
            {"url": "https://mirrors.kernel.org/mageia/iso/",
             "dir_re": r'href="(\d+)/"',
             "file_page": "{url}{ver}/Mageia-{ver}-Live-Xfce-x86_64/",
             "mirrors": ["https://mirrors.kernel.org/mageia/iso/{ver}/Mageia-{ver}-Live-Xfce-x86_64/"],
             "edition": "xfce", "edition_name": "Xfce Live"},
        ],
        "default_arch": "x86_64",
        "rules": [
            {"match": r"Mageia-(?P<ver>\d+)-Live-(?:GNOME|Plasma|Xfce)-x86_64\.iso",
             "edition": "x", "edition_name": "x"},
        ],
    },
    {
        "id": "q4os", "name": "Q4OS",
        "site": "https://q4os.org/downloads1.html",
        "kind": "sourceforge",
        "project": "q4os",
        "default_arch": "amd64",
        "rules": [
            {"match": r"q4os-(?P<ver>[\d.]+)-x64(?P<rev>\.r\d+)?\.iso",
             "edition": "desktop", "edition_name": "Desktop Edition"},
        ],
    },
    {
        "id": "bodhilinux", "name": "Bodhi Linux",
        "site": "https://www.bodhilinux.com/download/",
        "kind": "sourceforge",
        "project": "bodhilinux",
        "default_arch": "amd64",
        "rules": [
            {"match": r"bodhi-(?P<ver>[\d.]+)-64\.iso",
             "edition": "standard", "edition_name": "Standard (Moksha Desktop)"},
        ],
    },
    {
        "id": "sparkylinux", "name": "SparkyLinux",
        "site": "https://sparkylinux.org/download/",
        "kind": "sourceforge",
        "project": "sparkylinux",
        "default_arch": "x86_64",
        "rules": [
            {"match": r"sparkylinux-(?P<ver>[\d.]+)-x86_64-(?P<ed>minimalgui[a-z-]*)\.iso",
             "edition": "minimalgui", "edition_name": "MinimalGUI"},
        ],
    },
]

SPECS = {s["id"]: s for s in DISTRO_SPECS}


# ---------------------------------------------------------------- fetch

def fetch_text(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return raw.decode("utf-8", errors="replace")


# ---------------------------------------------------------------- schema

def validate(data):
    """Raise ValueError if the JSON does not match the schema."""
    if not isinstance(data, dict):
        raise ValueError("root must be an object")
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    distros = data.get("distros")
    if not isinstance(distros, list) or not distros:
        raise ValueError("distros must be a non-empty list")
    seen_d, seen_e = set(), set()
    for d in distros:
        for key in ("id", "name", "site", "editions"):
            if key not in d:
                raise ValueError("distro missing key: %s" % key)
        if d["id"] in seen_d:
            raise ValueError("duplicate distro id: %s" % d["id"])
        seen_d.add(d["id"])
        if not isinstance(d["editions"], list) or not d["editions"]:
            raise ValueError("distro %s: editions must be non-empty" % d["id"])
        for e in d["editions"]:
            for key in ("id", "name", "versions"):
                if key not in e:
                    raise ValueError("edition missing key: %s" % key)
            ek = (d["id"], e["id"])
            if ek in seen_e:
                raise ValueError("duplicate edition id: %s" % (ek,))
            seen_e.add(ek)
            if not isinstance(e["versions"], list) or not e["versions"]:
                raise ValueError("edition %s: versions must be non-empty" % ek)
            for v in e["versions"]:
                for key in ("version", "iso", "urls"):
                    if key not in v:
                        raise ValueError("version missing key: %s in %s" % (key, ek))
                if not isinstance(v["urls"], list) or not v["urls"]:
                    raise ValueError("version %s %s: urls must be non-empty"
                                     % (ek, v.get("version")))
                for u in v["urls"] + v.get("torrents", []):
                    if not (u.startswith("https://") or u.startswith("http://")):
                        raise ValueError("bad url %r in %s" % (u, ek))
    return True


# ---------------------------------------------------------------- merge

def merge_versions(old_list, new_list):
    """Merge scraped versions into stored ones. New data wins on known
    (version, arch); unknown entries are appended; stored-only entries kept."""
    by_key = {}
    order = []
    for v in old_list:
        k = (v.get("version"), v.get("arch", ""))
        if k not in by_key:
            order.append(k)
        by_key[k] = v
    for v in new_list:
        k = (v.get("version"), v.get("arch", ""))
        if k in by_key:
            merged = dict(by_key[k])
            merged.update({kk: vv for kk, vv in v.items() if vv is not None})
            extra = [u for u in by_key[k].get("urls", []) if u not in merged.get("urls", [])]
            merged["urls"] = list(merged.get("urls", [])) + extra
            by_key[k] = merged
        else:
            order.append(k)
            by_key[k] = v
    return [by_key[k] for k in order]


def apply_scrape(data, spec, scraped_editions):
    """Merge scrape result; AUTO-CREATE the distro entry if it is new."""
    for d in data["distros"]:
        if d["id"] == spec["id"]:
            known = {e["id"]: e for e in d["editions"]}
            for se in scraped_editions:
                if se["id"] in known:
                    ke = known[se["id"]]
                    ke["versions"] = merge_versions(ke.get("versions", []), se["versions"])
                else:
                    d["editions"].append(se)
                    known[se["id"]] = se
            if spec.get("keep"):
                # rolling releases (Tumbleweed snapshots): keep N newest
                # so the JSON does not grow forever
                touched = {se["id"] for se in scraped_editions}
                for e in d["editions"]:
                    if e["id"] in touched:
                        e["versions"] = sorted(
                            e["versions"], key=lambda v: str(v.get("version")),
                            reverse=True)[:spec["keep"]]
            else:
                # newest version first (combo boxes show the latest on top)
                touched = {se["id"] for se in scraped_editions}
                for e in d["editions"]:
                    if e["id"] in touched:
                        e["versions"] = sorted(
                            e["versions"], key=lambda v: str(v.get("version")),
                            reverse=True)
            return "updated"
    data["distros"].append({
        "id": spec["id"], "name": spec["name"], "site": spec["site"],
        "editions": scraped_editions,
    })
    if spec.get("keep"):
        for e in data["distros"][-1]["editions"]:
            e["versions"] = sorted(e["versions"],
                                   key=lambda v: str(v.get("version")),
                                   reverse=True)[:spec["keep"]]
    return "created"


# ---------------------------------------------------------------- parsers

def _sums_rows(text):
    """Parse GNU 'hash  filename' lines and BSD 'SHA256 (file) = hash'
    lines (AlmaLinux CHECKSUM). Returns [(sha, filename, size|None)]."""
    rows = []
    sizes = dict(re.findall(r"^#\s*(\S+):\s*(\d+)\s*bytes\s*$", text, re.M))
    for m in re.finditer(r"^([0-9a-fA-F]{64,128})\s+\*?(\S+)\s*$", text, re.M):
        sha, filename = m.group(1).lower(), m.group(2)
        rows.append((sha, filename, sizes.get(filename)))
    for m in re.finditer(r"^SHA(?:256|512)\s*\(([^)]+)\)\s*=\s*([0-9a-fA-F]{64,128})\s*$",
                         text, re.M | re.I):
        filename, sha = m.group(1), m.group(2).lower()
        if filename not in {f for _, f, _ in rows}:
            rows.append((sha, filename, sizes.get(filename)))
    return rows


def _html_iso_filenames(page):
    """Filenames for pages with direct ISO links but no sums file."""
    found = []
    for href in re.findall(r'href="([^"]+)"', page):
        m = re.search(r"([\w][\w.\-+]*\.iso)(?:[?#].*)?$", href)
        if m and m.group(1) not in found:
            found.append(m.group(1))
    return found


def _discover_versions(disc):
    """Return version dirs newest-first, honoring exclude_re."""
    html = fetch_text(disc["url"])
    vers = sorted(set(re.findall(disc["dir_re"], html)),
                  key=lambda v: [int(p) for p in re.findall(r"\d+", v)],
                  reverse=True)
    exc = disc.get("exclude_re")
    if exc:
        vers = [v for v in vers if not re.search(exc, v)]
    if not vers:
        raise ValueError("version discovery found nothing at " + disc["url"])
    return vers


def _sums_sources_from_disc(disc):
    """Build [{sums, mirrors}] from a discover block (supports archs)."""
    vers = _discover_versions(disc)
    archs = disc.get("archs") or [None]

    def build(ver):
        out = []
        for arch in archs:
            kw = {"ver": ver}
            if arch:
                kw["arch"] = arch
            out.append({
                "sums": disc["sums"].format(**kw),
                "mirrors": [m.format(**kw) for m in disc["mirrors"]],
            })
        return out

    if disc.get("pick") == "max-with-rows":
        # newest dir whose sums file actually yields ISO rows
        # (skips beta/staging dirs that only contain -beta files)
        tried = []
        for ver in vers:
            ok = True
            for src in build(ver):
                try:
                    rows = _sums_rows(fetch_text(src["sums"]))
                except Exception as exc:
                    tried.append("%s(%s)" % (ver, exc))
                    ok = False
                    break
                if not [f for _, f, _ in rows if f.endswith(".iso")]:
                    tried.append("%s(empty)" % ver)
                    ok = False
                    break
            if ok:
                return build(ver)
        raise ValueError("no usable version dir at " + disc["url"]
                         + " tried: " + ",".join(tried))
    return build(vers[0])


def _probe_torrent(iso_url, timeout=20):
    """HEAD <iso>.torrent; return the URL if it exists, else None.

    SEZOY downloads with aria2, which eats torrents natively, so a
    verified .torrent next to the ISO is a first-class fallback."""
    turl = iso_url + ".torrent"
    try:
        req = urllib.request.Request(turl, headers=UA, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status < 400:
                return turl
    except Exception:
        pass
    return None


def _hash_field(sha):
    """('sha256'|'sha512', sha) by length; (None, None) if unusable."""
    if not sha:
        return None, None
    if len(sha) == 64:
        return "sha256", sha
    if len(sha) == 128:
        return "sha512", sha
    return None, None


def _apply_rules(rules, filename, default_arch):
    """First matching rule wins. Returns dict or None."""
    for rx, eid, ename, amap in rules:
        m = rx.search(filename)
        if not m:
            continue
        gd = m.groupdict()
        arch = gd.get("arch") or default_arch
        if amap and arch in amap:
            arch = amap[arch]
        return {"edition": eid, "edition_name": ename,
                "version": gd.get("ver"), "arch": arch, "groups": gd}
    return None


def run_sums_spec(spec):
    """Generic parser for any distro publishing SHA256SUMS-style files."""
    sources = list(spec.get("sources", []))
    if spec.get("discover"):
        sources.extend(_sums_sources_from_disc(spec["discover"]))
    rules = [(re.compile(r["match"]), r.get("edition"), r.get("edition_name"),
              r.get("arch_map"), r.get("edition_from"), r.get("edition_map"), r)
             for r in spec["rules"]]
    default_arch = spec.get("default_arch", "amd64")
    edition_names = spec.get("edition_names") or {}
    found = {}
    for src in sources:
        if src.get("html"):
            # page with direct ISO links but no sums file (Artix)
            items = [(None, f, None) for f in _html_iso_filenames(fetch_text(src["page"]))]
            mirrors = src["mirrors"]
        else:
            items = [((s if len(s) in (64, 128) else None), f, z)
                     for s, f, z in _sums_rows(fetch_text(src["sums"]))]
            mirrors = src["mirrors"]
        for sha, filename, size in items:
            if not filename.endswith(".iso"):
                continue
            if spec.get("skip_re") and re.search(spec["skip_re"], filename):
                continue
            for rx, eid, ename, amap, ed_from, ed_map, raw in rules:
                m = rx.search(filename)
                if not m:
                    continue
                gd = m.groupdict()
                if ed_from:
                    key = gd.get(ed_from)
                    eid = (ed_map or {}).get(key, key.lower() if key else None)
                    ename = edition_names.get(eid, eid)
                arch = gd.get("arch") or default_arch
                if amap and arch in amap:
                    arch = amap[arch]
                ver = gd.get("ver") or ""
                vsuf = raw.get("ver_suffix_from")
                if vsuf and gd.get(vsuf):
                    ver += gd[vsuf]
                key, val = _hash_field(sha)
                row = {"version": ver, "arch": arch,
                       "iso": filename,
                       "urls": [base + filename for base in mirrors]}
                if key:
                    row[key] = val
                if size:
                    row["size"] = int(size)
                if spec.get("torrent_probe"):
                    t = _probe_torrent(row["urls"][0])
                    if t:
                        # same file on every mirror: swap the base
                        row["torrents"] = [
                            t if i == 0 else mb + filename + ".torrent"
                            for i, mb in enumerate(mirrors)]
                found.setdefault(eid, {"id": eid, "name": ename, "rows": []})
                found[eid]["rows"].append(row)
                break
    for e in found.values():
        # same ISO listed under several hash sections (Parrot md5/sha256/
        # sha512): fold into one row, keeping every hash field found
        by_iso = {}
        for v in e["rows"]:
            k = (v.get("version"), v.get("arch"), v["iso"])
            if k in by_iso:
                old = by_iso[k]
                for fk in ("sha256", "sha512", "size", "torrents"):
                    if fk not in old and fk in v:
                        old[fk] = v[fk]
                for u in v.get("urls", []):
                    if u not in old["urls"]:
                        old["urls"].append(u)
            else:
                by_iso[k] = v
        e["rows"] = list(by_iso.values())
    editions = [{"id": e["id"], "name": e["name"],
                 "versions": sorted(e["rows"], key=lambda r: r["version"], reverse=True)}
                for e in found.values() if e["id"]]
    if not editions:
        raise ValueError("no ISOs parsed for " + spec["id"])
    return editions


def _sidecar_sha(sha_base, filename, suffix=".sha256"):
    """Fetch sibling checksum file, return (field, hash) or (None, None)."""
    try:
        text = fetch_text(sha_base + filename + suffix)
    except Exception:
        return None, None
    m = re.search(r"([0-9a-fA-F]{128}|[0-9a-fA-F]{64})", text)
    return _hash_field(m.group(1).lower()) if m else (None, None)


def _sidecar_jobs(spec):
    """Build [(file_page, mirrors, sha_base, fixed_version, fixed_edition)].

    - listings: static [{listing, mirrors, sha_base?}]
    - discover: one version dir -> listing template
    - discovers: one entry per distro edition, each with its own
      version-dir discovery (Garuda/Manjaro style)."""
    jobs = []
    for src in spec.get("listings", []):
        jobs.append((src["listing"], src["mirrors"],
                     src.get("sha_base"), None, None, None))
    disc = spec.get("discover")
    if disc:
        vers = _discover_versions(disc)
        if disc.get("try_desc"):
            tried = []
            for ver in vers:
                listing = disc["listing"].format(url=disc["url"], ver=ver)
                try:
                    page = fetch_text(listing)
                except Exception as exc:
                    tried.append("%s(%s)" % (ver, exc))
                    continue
                if re.search(r"\.iso", page):
                    jobs.append((listing,
                                 [m.format(url=disc["url"], ver=ver)
                                  for m in disc["mirrors"]],
                                 None, ver, None, None))
                    break
                tried.append("%s(empty)" % ver)
            else:
                raise ValueError("no usable version dir at " + disc["url"]
                                 + " tried: " + ",".join(tried))
        else:
            ver = vers[0]
            jobs.append((disc["listing"].format(url=disc["url"], ver=ver),
                         [m.format(url=disc["url"], ver=ver)
                          for m in disc["mirrors"]],
                         None, ver, None, None))
    for dd in spec.get("discovers", []):
        vers = _discover_versions(dd)
        picked = None
        if dd.get("try_desc", True):
            tried = []
            for ver in vers:
                page_url = dd["file_page"].format(url=dd["url"], ver=ver)
                try:
                    page = fetch_text(page_url)
                except Exception as exc:
                    tried.append("%s(%s)" % (ver, exc))
                    continue
                if re.search(r"\.iso", page):
                    picked = ver
                    break
                tried.append("%s(empty)" % ver)
            if picked is None:
                raise ValueError("no usable version dir at " + dd["url"]
                                 + " tried: " + ",".join(tried))
        else:
            picked = vers[0]
        kw = {"url": dd["url"], "ver": picked}
        jobs.append((dd["file_page"].format(**kw),
                     [m.format(**kw) for m in dd["mirrors"]],
                     dd.get("sha_base", "").format(**kw) or None,
                     dd.get("version_from_dir", True) and picked or None,
                     dd.get("edition"), dd.get("edition_name")))
    return jobs


def run_sidecar_spec(spec):
    """Directory listing + sibling checksum file per ISO."""
    rules = [(re.compile(r["match"]), r.get("edition"), r.get("edition_name"),
              r.get("arch_map"), r.get("edition_from"), r.get("edition_map"))
             for r in spec["rules"]]
    default_arch = spec.get("default_arch", "amd64")
    sha_suffix = spec.get("sha_suffix", ".sha256")
    skip_rx = re.compile(spec["skip_re"]) if spec.get("skip_re") else None
    edition_names = spec.get("edition_names") or {}
    found = {}
    for page_url, mirrors, sha_base, fixed_ver, fixed_ed, fixed_ename in \
            _sidecar_jobs(spec):
        page = fetch_text(page_url)
        base = mirrors[0]
        for filename in sorted(set(re.findall(r"([\w][\w.\-+]*\.iso)", page))):
            if skip_rx and skip_rx.search(filename):
                continue  # mirror alias/symlink duplicate of the real file
            if "Current" in filename and "Snapshot" not in filename:
                continue  # symlink alias, the Snapshot* row covers it
            for rx, eid, ename, amap, ed_from, ed_map in rules:
                m = rx.search(filename)
                if not m:
                    continue
                gd = m.groupdict()
                if fixed_ed:
                    eid, ename = fixed_ed, fixed_ename
                elif ed_from:
                    key = gd.get(ed_from)
                    eid = (ed_map or {}).get(key, key.lower() if key else None)
                    ename = edition_names.get(eid, eid)
                arch = gd.get("arch") or default_arch
                if amap and arch in amap:
                    arch = amap[arch]
                ver = fixed_ver or gd.get("ver")
                key, val = _sidecar_sha(sha_base or base, filename, sha_suffix)
                row = {"version": ver, "arch": arch, "iso": filename,
                       "urls": [mb + filename for mb in mirrors]}
                if key:
                    row[key] = val
                if spec.get("torrent_probe"):
                    t = _probe_torrent(row["urls"][0])
                    if t:
                        row["torrents"] = [
                            t if i == 0 else mb + filename + ".torrent"
                            for i, mb in enumerate(mirrors)]
                found.setdefault(eid, {"id": eid, "name": ename, "rows": []})
                found[eid]["rows"].append(row)
                break
    if spec.get("dedupe") == "max-iso":
        # same (version, arch) from several builds (Manjaro kernels):
        # keep the highest ISO filename only
        for e in found.values():
            best = {}
            for v in e["rows"]:
                k = (v.get("version"), v.get("arch"))
                if k not in best or v["iso"] > best[k]["iso"]:
                    best[k] = v
            e["rows"] = list(best.values())
    editions = [{"id": e["id"], "name": e["name"],
                 "versions": sorted(e["rows"], key=lambda r: str(r["version"]),
                                    reverse=True)}
                for e in found.values()]
    if not editions:
        raise ValueError("no ISOs parsed for " + spec["id"])
    return editions


def run_sourceforge_spec(spec):
    """SourceForge best_release.json -> latest file + rules on filename."""
    api = "https://sourceforge.net/projects/%s/best_release.json" % spec["project"]
    info = json.loads(fetch_text(api))["release"]
    filename = info["filename"].lstrip("/")
    rules = [(re.compile(r["match"]), r["edition"], r["edition_name"],
              r.get("arch_map")) for r in spec["rules"]]
    default_arch = spec.get("default_arch", "amd64")
    hit = _apply_rules(rules, filename, default_arch)
    if not hit:
        raise ValueError("release %s matches no rule" % filename)
    base1 = "https://downloads.sourceforge.net/project/%s/" % spec["project"]
    base2 = "https://sourceforge.net/projects/%s/files/" % spec["project"]
    return [{"id": hit["edition"], "name": hit["edition_name"], "versions": [{
        "version": hit["version"], "arch": hit["arch"], "iso": filename,
        "size": info.get("bytes"),
        "sha256": info.get("sha256sum"),
        "urls": [base1 + filename, base2 + filename + "/download"],
    }]}]


def run_tails_spec(spec):
    """Tails official JSON API -> latest release info + SHA256."""
    data = json.loads(fetch_text(spec["api"]))
    inst = data["installations"][0]
    ver = inst["version"]
    iso_info = None
    for p in inst.get("installation-paths", []):
        if p.get("type") == "iso":
            iso_info = p["target-files"][0]
            break
    if not iso_info:
        raise ValueError("no ISO target found in Tails API")
    url = iso_info["url"]
    filename = url.split("/")[-1]
    mirrors = [url]
    if spec.get("mirror_base"):
        mirrors.append(spec["mirror_base"] + filename)
    return [{
        "id": "live",
        "name": "Live (Amnesic Incognito)",
        "versions": [{
            "version": ver,
            "arch": "amd64",
            "iso": filename,
            "size": iso_info.get("size"),
            "sha256": iso_info.get("sha256"),
            "urls": mirrors,
        }]
    }]


def run_pop_os_spec(spec):
    """Pop!_OS download page -> ISO download URLs + SHA256 sums."""
    html = fetch_text(spec["url"])
    editions = []
    pattern = r'href=[\x22\x27](https://iso\.pop-os\.org/(?P<path>(?P<ver>\d+\.\d+)/(?P<arch>[^/]+)/(?P<ed>intel|nvidia)/[^/]+/(?P<filename>[^\x22\x27]+\.iso)))[\x22\x27]'
    seen_editions = set()
    for m in re.finditer(pattern, html):
        d = m.groupdict()
        ed = d["ed"]
        if ed in seen_editions:
            continue
        seen_editions.add(ed)
        start = max(0, m.start() - 600)
        end = min(len(html), m.end() + 600)
        shas = re.findall(r"([0-9a-fA-F]{64})", html[start:end])
        sha = shas[0].lower() if shas else None
        ename = "Intel / AMD Graphics" if ed == "intel" else "NVIDIA Graphics"
        editions.append({
            "id": ed,
            "name": ename,
            "versions": [{
                "version": d["ver"],
                "arch": d["arch"],
                "iso": d["filename"],
                "urls": [m.group(1)],
                "sha256": sha,
            }]
        })
    if not editions:
        raise ValueError("no Pop!_OS ISOs found on " + spec["url"])
    return editions


def run_fedora_spec(spec):
    root = spec["root"]
    html = fetch_text(root)
    nums = sorted({int(m.group(1)) for m in
                   (re.match(r"(\d+)/?$", l.strip("/"))
                    for l in re.findall(r'href="([^"]+)"', html)) if m})
    if not nums:
        raise ValueError("no Fedora releases listed at " + root)
    rel = str(nums[-1])
    out = []
    for edition_id, edition_name, sub in spec["editions"]:
        d = "%s%s/%s/x86_64/iso/" % (root, rel, sub)
        page = fetch_text(d)
        isos = sorted({l for l in re.findall(r'href="([^"]+)"', page)
                       if l.endswith(".iso")})
        chk = {}
        m = re.search(r'href="([^"]*CHECKSUM[^"]*)"', page)
        if m:
            ctext = fetch_text(d + m.group(1))
            for cm in re.finditer(r"^SHA256\s*\(([^)]+)\)\s*=\s*([0-9a-fA-F]{64})",
                                  ctext, re.M):
                chk[cm.group(1)] = cm.group(2).lower()
        rows = [{"version": rel, "arch": "x86_64", "iso": iso,
                 "sha256": chk.get(iso),
                 "urls": [d + iso,
                          d.replace("https://download.fedoraproject.org",
                                    "https://dl.fedoraproject.org") + iso]}
                for iso in isos]
        if rows:
            out.append({"id": edition_id, "name": edition_name, "versions": rows})
    if not out:
        raise ValueError("no Fedora ISOs parsed for release " + rel)
    return out


def run_spec(spec):
    if spec["kind"] == "sums":
        return run_sums_spec(spec)
    if spec["kind"] == "sidecar":
        return run_sidecar_spec(spec)
    if spec["kind"] == "sourceforge":
        return run_sourceforge_spec(spec)
    if spec["kind"] == "fedora":
        return run_fedora_spec(spec)
    if spec["kind"] == "tails":
        return run_tails_spec(spec)
    if spec["kind"] == "pop_os":
        return run_pop_os_spec(spec)
    if spec["kind"] == "manual":
        raise ValueError("manual distro, edit JSON by hand")
    raise ValueError("unknown kind: %s" % spec.get("kind"))


# ---------------------------------------------------------------- main

def main(argv=None):
    ap = argparse.ArgumentParser(description="Refresh linux_distros.json")
    ap.add_argument("--file", default=DEFAULT_JSON)
    ap.add_argument("--check", action="store_true", help="validate only, no network")
    ap.add_argument("--update", action="store_true", help="scrape + merge + write")
    ap.add_argument("--distro", choices=sorted(SPECS), help="limit update to one distro")
    ap.add_argument("--list", action="store_true", help="list known distro specs")
    args = ap.parse_args(argv)

    if args.list:
        for s in DISTRO_SPECS:
            print("%-8s %-14s kind=%s %s" % (s["id"], s["name"], s["kind"], s["site"]))
        return 0

    with io.open(args.file, encoding="utf-8") as fh:
        data = json.load(fh)
    validate(data)
    if args.check and not args.update:
        print("OK: %s validates (schema_version=1, %d distros)"
              % (args.file, len(data["distros"])))
        return 0

    if not args.update:
        ap.error("need --check and/or --update")
    targets = [args.distro] if args.distro else [s["id"] for s in DISTRO_SPECS]
    failed = []
    for did in targets:
        spec = SPECS[did]
        if spec["kind"] == "manual":
            print("SKIP: %-8s manual entry, left untouched" % did)
            continue
        try:
            editions = run_spec(spec)
            n = sum(len(e["versions"]) for e in editions)
            how = apply_scrape(data, spec, editions)
            print("OK: %-8s %s (%d editions, %d versions)"
                  % (did, how, len(editions), n))
        except Exception as exc:  # keep old data on any failure
            failed.append(did)
            print("WARN: %-8s scrape failed, keeping old data: %s" % (did, exc))
    validate(data)
    data["updated_utc"] = (datetime.datetime.now(datetime.timezone.utc)
                           .replace(microsecond=0).isoformat().replace("+00:00", "Z"))
    with io.open(args.file, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("wrote %s (updated_utc=%s)%s" % (
        args.file, data["updated_utc"],
        (" FAILED: " + ",".join(failed)) if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
