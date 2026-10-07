# UHF RFID reader over Ethernet — Selfmade Reader

Status (2026-10-01): **WORKING.** The reader pushes tag data over Ethernet to this PC; it is shown live, stored in a CSV, and can be forwarded over HTTP / MQTT / TCP. A browser-based configuration UI ("Selfmade Reader") replaces the vendor tool.

---

## 1. Quick start

```bash
cd ~/Desktop/rfid
python3 selfmade_reader.py            # opens http://127.0.0.1:8088
```
1. Make sure the PC's wired port is on the reader's network (`192.168.1.10/24`) and the reader (`192.168.1.250`) is cabled and powered.
2. Open the **Reader setup** tab. If the reader is not already configured: press **One-click Ethernet setup** (sets Interface = RJ45, remote server = this PC, restarts the reader).
3. Hold a UHF EPC Gen2 tag at the antenna: the reader beeps, tags appear on the **Dashboard** and in `selfmade_reads.csv`.

Options: `--host 0.0.0.0` (UI reachable from other PCs), `--port 8089`, `--no-browser`. Rename the product by editing `APP_NAME` at the top of `selfmade_reader.py`.

### Start automatically (boot / login)

```bash
python3 selfmade_reader.py --install-autostart      # install + start now
python3 selfmade_reader.py --uninstall-autostart    # remove
```
| OS | How | Notes |
|---|---|---|
| Linux | systemd **user** service `selfmade-reader` (`~/.config/systemd/user/`), restarts itself 5 s after a crash | tries `loginctl enable-linger` so it also runs at boot before login; if that needs root run once `sudo loginctl enable-linger $USER`. Check: `systemctl --user status selfmade-reader`, logs: `journalctl --user -u selfmade-reader -f` |
| macOS | launchd agent `~/Library/LaunchAgents/com.selfmade.selfmade-reader.plist` (RunAtLoad + KeepAlive) | starts at login; log in `selfmade_reader.log` |
| Windows | Task Scheduler task `SelfmadeReader` (at logon, uses `pythonw.exe` so no console window) | run Command Prompt once to install; allow Python through the firewall |

**Verified on this Linux PC only** (installed, running, enabled, linger on, auto-restart after `kill -9`, reader reconnected by itself). macOS and Windows code paths are written but untested. Auto-start runs with default settings (UI on 127.0.0.1:8088, listen port from `selfmade_reader_config.json`). If you move the folder or change Python, re-run `--install-autostart`.

Data volume: a tag sitting near the antenna is read ~9 times/s, i.e. ~50 MB of CSV per day. In *Data & forwarding* set the save mode to "one row per tag per 1 s / 5 s / 60 s" to keep the file small.

## 2. What the app does

| Tab | Features |
|---|---|
| Dashboard | live tag table (EPC, reads, RSSI, antenna, last seen), counters, CSV download, clear |
| Reader setup | find reader on LAN (UDP discovery), one-click Ethernet setup, read/edit Interface, Work mode, RF power (0–30 dBm), Wiegand timing, reader IP/mask/gateway, remote server IP/port, local port, heartbeat, WiFi SSID/password, restart reader, backup / restore |
| Data & forwarding | CSV path + de-duplication (every read / per 1 s / 5 s / 60 s); forward every read to **HTTP webhook** (POST JSON, optional auth header), **MQTT** (QoS 0), **TCP** (JSON line). Test buttons. Uses whatever link the PC has (Ethernet, WiFi, 4G/5G hotspot) |
| Log | live activity log |

- Settings persist in `selfmade_reader_config.json`.
- **A backup of the reader's settings is saved to `backup/` before every write**; *Restore selected* writes it back (then restart the reader).
- Security: UI binds to 127.0.0.1 by default; POST requests need a same-origin header.
- Forward payload: `{"epc","rssi","antenna","reader","time"}`.
- CSV columns: `timestamp,epc,rssi,antenna,reader_ip`.

## 3. Hardware and network

- All-in-one UHF reader, board **SN5300 V1.6**, module **M605 V2.1** (865–868 MHz, "Europe" band), firmware 4.11, probably sold as CF5300. Has RJ45, RS232/RS485, USB/keyboard, Wiegand, relay, WiFi (ESP-07S).
- Reader **192.168.1.250/24**, gateway 192.168.1.1, MAC `68:f7:03:14:45:2c`.
- **TCP 60000 = command/config port** on the reader. It sends a UDP discovery broadcast (port 65000 -> 65001) every ~6 s.
- With Interface = RJ45 the reader acts as a **TCP client**: it connects to *RemoteIP:RemotePort* (now `192.168.1.10:6000`) and pushes tag frames.
- PC wired NIC `enp0s31f6` = `192.168.1.10/24`, manual, no default route (internet stays on WiFi). Linux:
  `nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses 192.168.1.10/24 ipv4.never-default yes && nmcli con up "Wired connection 1"`
- Only **UHF EPC Gen2** tags are read (not 125 kHz cards).

## 4. Root cause (why Ethernet was silent) and the fix

The reader was in **Active mode with Interface = RS232/RS485**, so it pushed tags out the serial port; TCP 60000 only carries commands. Remote server was `120.78.148.145:0` (factory default).

Fix, done 2026-10-01 with the vendor tool *Reader software 5.0* (run under Wine):
- ParameterSet: Interface `RS232/RS485` -> `RJ45`, WorkMode stays ActiveMode, **Set**.
- Network Settings: RemoteIP -> `192.168.1.10`, RemotePort -> `6000`, **Set** (reader restarts).
- Original settings are saved in `backup/reader_config_backup_2026-10-01.json` (raw hex of commands 0x20 / 0x26 / 0x2E replies).

Lessons: (a) **Answer mode + poll command 0x01 did not work** and silenced the beeper — don't use it (restored); (b) the "4G" label in the vendor screenshots belonged to a different reader model; (c) direct `gdown` per-file download fails, use `https://drive.usercontent.google.com/download?id=<ID>&export=download&confirm=t`.

## 5. Protocol ("SW" requests / "CT" replies, TCP 60000)

```
Request : 53 57 | LEN(2,BE) | ADDR=FF | CMD | DATA... | CHK
Reply   : 43 54 | LEN(2,BE) | ADDR     | CMD | STATUS(01=ok) | DATA... | CHK
LEN = bytes after the length field incl. checksum;  CHK = (-sum(all preceding bytes)) & 0xFF
```
| CMD | Meaning |
|---|---|
| 0x20 / 0x21 | get / set reader params. Data after status (33 bytes): `c3 55`, **[2] Interface**, [6] RF power (dBm), **[7] WorkMode**, [17] Wiegand out interval, [18] pulse width, [19] pulse interval; other bytes preserved. Set = first 21 bytes + 13 zero bytes (34 total) |
| 0x26 / 0x27 | get / set network block (225 bytes; set = block + 28 zero bytes = 253): [3:9] MAC, [9:13] IP, [13:17] mask, [17:21] gateway, [21:25] remote IP, [25:27] local port (LE), [27:29] remote port (LE), [31] heartbeat (x10 s), [64:96] WiFi SSID, [96:128] WiFi password |
| 0x2E / 0x2F | get / set advanced params (MQTT/HTTP etc. inside the reader; not edited by the app) |
| 0x30 | restart reader |
| 0xE0 | handshake/status |
| 0x45 | **tag report pushed by the reader**: `01 45 01 <7-byte id> <count> { <len> <ant> <flag> <EPC...> <RSSI> }...` |

Interface codes (byte [2]): `00` USB, `01` RS232/RS485, `02` RJ45, `03` WIFI, `04` Weigand, `05` Keyboard, `06` KeyboardNoEnter, `07` 4G, `08` BlueTooth (list order of the vendor combo; 01, 02, 07 verified). Work mode: `00` Answer, `01` Active, `02` Trigger.

Example tag frame: `43 54 00 1c 01 45 01 c3 9b 24 03 14 45 2c 01 0f 01 01 30 08 33 b2 dd d9 01 40 00 00 00 00 3c 9a` -> EPC `300833B2DDD9014000000000`.

## 6. Files in this folder

| Path | What |
|---|---|
| `selfmade_reader.py` | **the app** (UI + receiver + CSV + forwarding + reader config) |
| `selfmade_reads.csv` | tag data written by the app |
| `selfmade_reader_config.json` | app settings (created on first save) |
| `backup/` | reader-settings backups (auto + manual) |
| `rfid_bridge.py` | older command-line bridge (superseded; can't run at the same time, both use port 6000) |
| `rfid_reads.csv`, `capture.pcap` | earlier test data / packet capture |
| `ReaderSoft/` | vendor *Reader software 5.0* (`ReaderSoft.exe` + DLLs), only needed if you want the vendor GUI |
| `drive_dl/ReaderSoftV5.0/` | vendor logs/language files from Drive (the protocol was decoded from `Log/*.log`) |
| `LIGO Configurator…`, `ComNewUpgradeTool…` | **not for this reader** (fuel-sensor tool / firmware flasher — do not use) |
| `CLAUDE.md` | older working notes (superseded by this file) |

Vendor Drive folder: https://drive.google.com/drive/folders/1BlciWPug2jCUd0cLGHBqEP24msFP5SNG

## 7. Requirements to run on any system

- **Python 3.8+** (standard library only) and the file **`selfmade_reader.py`**. Intended for Linux, Windows and macOS (tested on Linux only).
- A computer on the reader's network (wired `192.168.1.x/24`, or set the reader IP in the UI), reader powered, UHF antenna attached.
- Firewall must allow inbound **TCP 6000** (reader -> PC), the UI port (8088) if used remotely, and UDP 65001 for "find readers".
- Nothing else. The vendor tool / Wine is **not needed** once the reader is set up (the app can do the setup itself).
- To forward data: a reachable HTTP URL / MQTT broker / TCP server (internet via WiFi, Ethernet or a phone hotspot).
- Moving to a new PC: copy the folder (or just `selfmade_reader.py`), give the PC a `192.168.1.x` address, run it, press *One-click Ethernet setup* (this points the reader at the new PC's IP).

## 8. Status of features

Verified on the real reader: connection, tag reception + CSV, reading settings, network block round-trip (write-back identical), security check.
Verified against local test servers: HTTP (with auth header), MQTT, TCP forwarding.
**Not yet tested on the reader:** One-click Ethernet setup button, switching to WIFI or 4G interface, writing RF power / Wiegand values, the Restore button, forwarding to a real cloud service. (They use the same commands as the vendor tool, but have not been exercised end to end.)

## 9. Pending / ideas

1. Test WiFi: Interface = WIFI, SSID/password in *Reader setup* (reader has an ESP-07S), restart, confirm tags arrive; same for 4G if a module + SIM is present (APN field offset in the network block is not mapped yet).
2. Run the app automatically at boot (systemd service / Windows Task Scheduler) so data is always collected.
3. Test forwarding to the real destination (cloud endpoint / broker); add retry-to-disk if the link can be down for long.
4. Optional: settings export/import, per-tag history chart, tag whitelist filter, show the reader serial number (command 0xF4 returns zeros on this unit; the vendor tool shows `C39B240314452C`).

## 10. Troubleshooting

- *"no reader connected"*: check cable/power, `ping 192.168.1.250`, PC IP is `192.168.1.10`, nothing else uses port 6000 (stop `rfid_bridge.py`), then restart the reader.
- *Reader beeps but no rows*: in *Reader setup* press **Read from reader** — Interface must be `2 - RJ45`, Work mode `1 - Active`, remote server = this PC's IP and the listen port. If wrong, press *One-click Ethernet setup*.
- *Lost access after changing the reader's IP*: move the PC to the new subnet, or restore a backup, or use the reader's RS232 port with the vendor tool.
- Don't set Work mode to Answer (the reader stops pushing and the buzzer stops).
- To go back to the original factory-like state: Interface = RS232/RS485 (`1`) and remote server `120.78.148.145` port `0`. (The app's *Restore* only reads backups made by the app; the 2026-10-01 backup in `backup/reader_config_backup_2026-10-01.json` uses a different key format and is for reference.)
