# SEZOY - Releases & Test Lab

**English** | [Tiếng Việt](README.vi.md)

This repository hosts SEZOY installers plus the ready-made VPN profile for the public test lab.
Full documentation lives at **https://tekdt.xyz** (Docs page).

> SEZOY is a Windows deployment platform: build bootable USB drives or a PXE/HTTP
> boot server, manage Windows ISOs, inject drivers, answer installations unattended,
> and monitor every client from one web dashboard.

---

## 1. Try SEZOY in 10 minutes - no install needed (public test lab)

A public SEZOY server (`192.168.251.1`) runs 24/7 with an open VPN Hub for testers.
You (machine C) join the same Layer-2 network over VPN, bridge a test VM straight
into the VPN adapter, and your VM network-boots from the remote server **as if
plugged into the same switch**. You can also open the shared dashboard at
`https://192.168.251.1:5893` (if you were given access).

### What you need

- **SoftEther VPN Client** (free) on your PC.
- **VMware Workstation Pro** (or any VM software that can bridge to a chosen NIC).
- A test VM: firmware **UEFI**, RAM ≥ 4 GB, disk ≥ 40 GB, **Network Boot / PXE first** in boot order.

### Step 1 - Connect the VPN (import the ready-made profile)

1. Install **SoftEther VPN Client**, then open **VPN Client Manager**.
2. Create a virtual NIC once: **New Virtual Network Adapter** → name it `SEZOY-VPN` → Enable.
3. Import the profile from this repo: **New VPN Connection Setting → Import VPN Connection Setting**,
   pick [`SEZOY-VPN-Connection.vpn`](SEZOY-VPN-Connection.vpn) - every field fills itself in:
   - Host: `sezoyhost.vpnazure.net`, port `443`, hub `SEZOY.HUB`, user `tester00` `tester99`.
4. Double-click the connection → **Connected**.
   Errors `1 / 2 / 691` mean wrong hub/user/password or port 443 blocked - recheck and retry.

> Manual setup also works (same values as above; the current password is posted in
> the release notes / community topic - credentials rotate occasionally).

### Step 2 - HARD-bridge the VM to the VPN adapter

> ⚠️ **Never leave bridging on Automatic.** The VM would grab an IP from your home
> router instead of the test network.

1. VMware **Edit → Virtual Network Editor** (Run as Administrator).
2. Pick an unused VMnet (e.g. **VMnet2**), type **Bridged**, **Bridged to:** the
   SoftEther virtual NIC - **not** Automatic. Apply.
3. VM settings → Network Adapter → **Custom: VMnet2**.

### Step 3 - Boot and test

1. Power on → PXE → the VM gets an IP like `192.168.251.x` → the SEZOY boot menu
   appears (allow 5–15 s over the Internet).
2. Pick a shared Windows/Linux ISO and the tester template → deploy.
3. **Lab etiquette** (the pool holds ~50 addresses, one server for everyone):
   - **One VM per person**, light boot first (hardware-check ISO, Linux live),
     full Windows install after (gigabytes over VPN - slowness is normal).
   - Shut the VM down cleanly, then **Disconnect the VPN** to free the slot.
   - Never stop the host's Boot Server or quit its app.
   - Sessions idle over ~5 minutes expire - just reboot fresh.
4. Report back: VM config (UEFI/Legacy, RAM), ISO booted, SecureBoot ON/OFF,
   boot time, screenshot + VM MAC on errors.

| Symptom | Quick fix |
|---|---|
| Boots straight to BIOS, no menu | Bridged to the wrong NIC - re-pin to the VPN adapter |
| Has IP but boot files time out | Weak link/firewall - retry, test with PC firewall off |
| Menu shows but everything is slow | Normal WAN jitter - don't reboot in a loop |
| VM gets a home IP (`192.168.1.x`) | VMnet still Automatic - pin it and reboot the VM |

---

## 2. Download & install your own SEZOY

Get the installer from the [**Releases**](releases) page of this repo:

| File | Channel | When to use |
|---|---|---|
| `SEZOY_beta.msi` | Beta (`vX.X.X.X-beta`) | Current builds - new features first |
| `SEZOY.msi` | Stable (`vX.X.X.X`) | Official stable releases (when published) |

- Installs **per user** (no admin rights needed for setup), then **run SEZOY as
  administrator** - it drives network/VPN drivers and the boot server.
- The **first launch needs Internet** (one-time activation + tool downloads);
  afterwards it runs fully offline.
- The FREE license is built in - open the app and it just runs, no key request.

---

## 3. Five-minute quick start (`https://localhost:5893`)

### Step 1 - USB drive or Boot Server

| Mode | What it does |
|---|---|
| **USB Drive** | Creates a bootable USB/disk that installs Windows directly, machine by machine (GPT/MBR, exFAT/NTFS/FAT32, boot themes, auto disk-select). |
| **BOOT Server** | Starts a PXE/HTTP server so clients on the network boot into the installer (ProxyDHCP recommended alongside your router, Full DHCP for isolated nets). |

While the Boot Server runs, configuration locks - stop it to edit settings.

### Step 2 - ISOs (3 tabs) + Deployment Modes

- **ISO List**: use ISOs you already have (add/remove, keep chosen editions, toggle the hardware-diagnostic ISO).
- **Selenium Download**: fetch genuine Microsoft ISOs (Edition → Language → Architecture), most stable.
- **Fido Script**: fast multi-version downloads - don't hammer it or Microsoft may throttle you temporarily.

When you pick editions for a Windows ISO, the **Deployment Modes** card appears:

| Mode | What happens | Pick it when… |
|---|---|---|
| **SEZOY (Panther Drop-in)** | Auto disk prep + fully unattended install from your answer file | Bulk, hands-off deploys pre-configured in Unattend Generator |
| **Microsoft Setup (Standard Setup)** | Hands over to stock Windows Setup; profile/preset decides the rest | You want the original Setup experience or manual control |

> ⚠️ **USB = exactly one mode per ISO** (radio buttons). **Boot Server = tick
> several** - each client's profile decides which mode it boots.

### Step 3 - Post-install apps, then Create

Browse the WinGet catalog, tick what each machine should get after setup
(selected packages apply to the default presets; custom presets keep their own
lists), then press **Create/Start** and watch progress live on the dashboard.

---

## 4. Stay updated - `Settings → Update`

The **Update** page (right above About) auto-checks whenever you open it online,
or check manually like Firefox/Chrome:

- **Beta** tab is active; **Stable** stays greyed out until an official release.
- Marquee bar while checking, **real % + size** while downloading (multi-link
  fallback, hash-verified).
- Defaults (all ON): **auto-install after download**, save to **Windows temp
  folder**, **delete the `.msi` afterwards**. Install is silent - the app closes
  itself to finish.

---

## 5. License & live support

- **Machine fingerprint** (`Settings → About`) uniquely identifies your PC -
  send it to TekDT to upgrade to PRO/ENTERPRISE. ENTERPRISE unlocks every
  Settings section; Language, Drivers, Update and About work on all tiers.
- **Live chat**: when the PC is online, a chat bubble appears in Settings and
  your messages automatically carry fingerprint + version + tier. Offline, the
  bubble hides - no queues, ever.

---

## 6. Quick FAQ

- **Offline?** Yes after first launch (tools + activation are one-time downloads).
- **Does it modify my ISO?** No - ISOs stay pristine; editions you untick are only stripped from the created device.
- **SecureBoot?** No need to disable. Linux ISO without a valid signature shows a reason screen instead of hanging.
- **Wi-Fi boot?** Needs a hotspot-capable card on the server and an HTTP-Boot-capable client; wired boot always works.
- **Missing disk in WinPE?** Download the MassStorage DriverPack first (`Settings → Drivers`).

Full guides, driver catalogs and unattended-generator references are on the Docs site.
