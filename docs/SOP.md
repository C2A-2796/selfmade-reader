# SOP — Deploying and operating the Selfmade Reader (UHF RFID over Ethernet)

| | |
|---|---|
| Document | Standard Operating Procedure |
| Applies to | SN5300 / CF5300 UHF RFID reader + any Windows / macOS / Linux computer |
| Tool | `selfmade_reader.py` (Python 3.8+, no extra packages) |
| Time needed | ~15 minutes for a first install |

**Verification legend used below:** ✅ verified on a real reader (Linux) · 🧪 verified against test servers only · ⚠️ written but not tested yet.

---

## 1. Purpose

Get tag data from the UHF reader into a computer **over Ethernet**, show it live, save it to a CSV file, and optionally forward it over the internet (HTTP / MQTT / TCP).

## 2. What you need

| Item | Details |
|---|---|
| Reader | SN5300 / CF5300 type, powered (12 V), UHF antenna attached |
| Cable | Ethernet cable reader ↔ computer (or both on the same switch) |
| Computer | Windows 10/11, macOS or Linux, with **Python 3.8+** |
| Files | this repository (download ZIP or `git clone`) |
| Tags | UHF **EPC Gen2** tags (868 MHz band). 125 kHz cards are never read |
| Reader's IP | factory/lab default **192.168.1.250**, mask 255.255.255.0 (confirm; see §4.3 if different) |

## 3. Rules (read first)

1. **Never set the reader's Work mode to "Answer".** It stops pushing tags and the buzzer goes silent.
2. Only **one computer** receives the tags at a time (the one the reader is pointed at).
3. Do not change the reader's own IP/mask/gateway unless required; a wrong value makes it unreachable.
4. The app saves a **backup** to `backup/` before every write. Do not delete it.
5. The web page can change reader settings: keep it on `127.0.0.1`, or only on a trusted LAN.

## 4. Procedure — first-time setup

### 4.1 Install Python
- **Windows:** download from python.org, tick **"Add Python to PATH"**. Check: `py --version`.
- **macOS:** python.org installer or `brew install python`. Check: `python3 --version`.
- **Linux:** normally present. Check: `python3 --version`.

### 4.2 Get the software
```bash
git clone <repository-url>
cd selfmade-reader
```
(or download the ZIP from GitHub and unzip).

### 4.3 Put the computer on the reader's network
Set a **fixed address** on the wired port, same subnet as the reader, no gateway (internet stays on WiFi):

| OS | Where | Values |
|---|---|---|
| Windows | Settings → Network & Internet → Ethernet → IP assignment → Edit → Manual | IP `192.168.1.20`, mask `255.255.255.0`, gateway empty |
| macOS | System Settings → Network → Ethernet → Details → TCP/IP → Configure IPv4: Manually | IP `192.168.1.20`, mask `255.255.255.0`, router empty |
| Linux | `nmcli con mod "Wired connection 1" ipv4.method manual ipv4.addresses 192.168.1.20/24 ipv4.never-default yes && nmcli con up "Wired connection 1"` | |

Use a different last number for every computer, never `.250`.
**Check:** `ping 192.168.1.250` must reply. If the reader has another IP, use its subnet instead (find it with *Find readers on the network* in §4.5).

### 4.4 Start the program
- Windows: double-click `START_WINDOWS.bat` (click **Allow** when the firewall asks about Python).
- macOS: double-click `START_MAC.command` (first time: right-click → Open).
- Linux: `./START_LINUX.sh`

A browser opens at **http://127.0.0.1:8088**. The top bar shows *"no reader connected"* until step 4.5 is done.
Firewall must allow inbound **TCP 6000** (reader → computer).

### 4.5 Point the reader at this computer  ✅
1. Open the tab **Reader setup**.
2. Click **Find readers on the network** (listens 7 s). Click **use it** next to your reader.
3. Click **One-click Ethernet setup** and confirm. The app: backs up the reader settings → sets *Interface = RJ45* → sets *Remote server = this computer, port 6000* → restarts the reader.
4. Wait ~15 s. The top bar turns green: **reader connected: 192.168.1.250**.

### 4.6 Verify  ✅
1. Hold a UHF tag 10–30 cm from the antenna. **The reader beeps.**
2. The tag's EPC appears in the **Dashboard** table with a growing *Reads* count.
3. A row is added to `selfmade_reads.csv` (columns: `timestamp, epc, rssi, antenna, reader_ip`).

If any of these fails go to §9.

## 5. Procedure — storage

*Data & forwarding* tab → **Storage**:
- *CSV file path*: where rows are written.
- *Save*: **every read** (a tag near the antenna is read ~9 times/s ≈ 50 MB/day) or **one row per tag per 1 s / 5 s / 60 s**. **Default is one row per tag per 1 s.**
- *New file every day*: writes `name_YYYY-MM-DD.csv` instead of one ever-growing file (recommended for long deployments).
Click **Save data settings**. ✅ (Daily files, de-duplication ✅ tested.)

## 6. Procedure — forward data over the internet 🧪

The computer's own connection is used (Ethernet, WiFi or a 4G/5G phone hotspot). Payload for HTTP/MQTT: `{"epc","rssi","antenna","reader","time"}`; TCP gets the same as one JSON line per read.

1. *Data & forwarding* tab, choose the sink and fill it in:
   - **HTTP:** URL (POST JSON) and optional auth header, e.g. `Authorization: Bearer <token>`.
   - **MQTT:** broker host, port (1883), topic, username/password, client ID. (QoS 0, plain TCP; no TLS.)
   - **TCP:** host and port of a listener.
2. Set *Enabled = yes*, click **Test** (must say "test OK"), then **Save data settings**.
3. The Dashboard counter *forwarded OK / failed* shows delivery. Failures are logged in the **Log** tab.

**If the link is down**, items that cannot be delivered are saved to `forward_spool.jsonl` (cap 100 MB) and **resent automatically, oldest first, every 30 s** once the destination works again (the Dashboard shows *waiting: N*). ✅ tested. The CSV always has every read regardless.
Limits: no TLS for MQTT; HTTP/MQTT/TCP are plain, so use a VPN or an HTTPS endpoint for sensitive data.

## 7. Procedure — start automatically at boot/login

Run once on the computer (or double-click the matching `INSTALL_AUTOSTART_*` file):
```bash
python3 selfmade_reader.py --install-autostart      # Windows: py selfmade_reader.py --install-autostart
```
- Linux ✅ (systemd user service, restarts after a crash; for start-before-login run `sudo loginctl enable-linger $USER` once if asked).
- macOS ⚠️ (launchd agent) and Windows ⚠️ (Task Scheduler task `SelfmadeReader`) are untested — verify by rebooting and opening http://127.0.0.1:8088.

Remove: `python3 selfmade_reader.py --uninstall-autostart`.
If you move the folder or change Python, run `--install-autostart` again.

## 8. Procedure — change computer, rollback, WiFi

### 8.1 Move to another computer ✅
Repeat §4.3 – §4.6 on the new computer. **§4.5 is mandatory** — it re-points the reader at the new computer's IP. Stop the old computer's program (otherwise it keeps port 6000 but receives nothing).

### 8.2 Roll back / restore a backup ⚠️
*Reader setup* → **Backups** → choose a file → **Restore selected** → **Restart reader**. (The app also saves a backup of the current state before restoring.)
Factory-like state: Interface `RS232/RS485`, remote server `120.78.148.145` port `0`.

### 8.3 Use WiFi instead of the cable ⚠️ (not yet tested)
*Reader setup* → **Reader network**: fill *WiFi network (SSID)* and *WiFi password*, set *Output interface* to **3 - WIFI**, **Write network settings**, **Write settings**, **Restart reader**. The computer must be reachable from the WiFi network and the *Remote server IP* must be the computer's address on that network. Record the result in §11 and report back, because this path has not been verified.

### 8.4 4G / 5G ⚠️ (not yet tested)
The reader's own 4G module (Interface `7 - 4G`) needs a SIM and an APN, and the APN field is not editable in this tool. To use mobile data, **forward from the computer** instead (§6) with a phone hotspot or modem as the computer's internet link.

## 9. Deployment hardening (read before putting it in service)

| Topic | What to do |
|---|---|
| Who can reach the page | Default is this computer only (127.0.0.1). If you must open it from other PCs: `python3 selfmade_reader.py --host 0.0.0.0 --password <strong password>` ✅. Put the password in the service environment (`SELFMADE_PASSWORD`), not on the command line, for auto-start. The page is plain HTTP — only on a trusted LAN/VPN |
| Who may send tags | *Reader setup* → **Only accept readers from these IPs** (e.g. `192.168.1.250`) ✅. Empty = any device that can reach port 6000 can inject tags |
| Monitoring | `GET http://127.0.0.1:8088/api/health` → HTTP **200** when a reader is pushing, **503** otherwise, with `reader_pushing`, `reader_reachable`, `last_tag_age_s`, `spool`, `uptime_s` (add the password if set) ✅. Point your monitoring/cron at it |
| Status bar meaning | green *reader connected* = OK · amber *reader reachable but not sending* = run One-click Ethernet setup · red *reader not reachable* = **check cable, reader power, IP** (the app pings the reader's command port every 15 s) |
| Disk | use *New file every day* and a 1–60 s save interval; archive/delete old CSVs; `forward_spool.jsonl` is capped at 100 MB |
| Survives reboot | Linux ✅ (started automatically on 3 consecutive reboots). Windows/macOS ⚠️ test with a reboot before relying on it |
| Fixed addressing | give the computer a **static** IP on the reader's subnet (§4.3). If the cable is unplugged the app keeps running and resumes when the link returns |
| Backups | keep `backup/` and copy `selfmade_reader_config.json` somewhere safe (it may contain credentials, never commit it) |
| Updates | `git pull`, then restart: Linux `systemctl --user restart selfmade-reader`; or re-run `--install-autostart` |
| Time | CSV timestamps use the computer's local clock — keep NTP/time sync on |

## 10. Troubleshooting

| Symptom | Check / fix |
|---|---|
| `ping 192.168.1.250` fails | cable, reader power, computer IP in `192.168.1.x`, no gateway typo; try *Find readers* |
| Red bar "reader not reachable" | physical: cable (the PC's Ethernet port must show link), reader power/LED, reader IP and the computer's IP in the same subnet. (Seen in practice: after a move the port was DOWN and no data came — not an app fault) |
| Amber bar "reachable but not sending" / no "reader connected" | run §4.5 again; firewall allows TCP 6000; no other program on port 6000 (log says *"Cannot listen on port 6000"*) |
| Reader beeps but no rows | *Reader setup* → **Read from reader**: Interface must be `2 - RJ45`, Work mode `1 - Active`, remote server = this computer's IP and port 6000. Fix with §4.5 |
| Buzzer silent, no data | Work mode was set to Answer — set `1 - Active`, write, restart reader |
| *Find readers* finds nothing | UDP 65001 blocked by firewall, or wrong subnet; enter the IP manually |
| Reader unreachable after IP change | put the computer on the new subnet; or restore a backup; or use the reader's RS232 port with the manufacturer's tool |
| "reader refused command" | restart the reader; make sure no other program holds its config connection |
| Windows: nothing happens on double-click | run `py selfmade_reader.py` in Command Prompt and read the error |
| macOS: "cannot be opened" | right-click the `.command` file → Open |
| CSV grows too fast | §5, choose "one row per tag per N s" |
| Page won't open | program not running; or port 8088 busy → `python3 selfmade_reader.py --port 8089` |

Useful logs: the **Log** tab; Linux service: `journalctl --user -u selfmade-reader -f`; macOS: `selfmade_reader.log`.

## 11. Acceptance checklist (sign-off)

- [ ] `ping 192.168.1.250` replies
- [ ] Program started; page opens on http://127.0.0.1:8088
- [ ] Top bar shows **reader connected**
- [ ] Tag held at antenna → reader beeps
- [ ] EPC appears on the Dashboard; *Reads* increases
- [ ] Row(s) appear in `selfmade_reads.csv`
- [ ] (if used) forwarding **Test** passes and *forwarded OK* increases
- [ ] (if used) auto-start installed; after a reboot the page is available and tags still arrive
- [ ] Backup file exists in `backup/`
- [ ] `/api/health` returns 200 while the reader is connected
- [ ] If the page is exposed beyond this computer: password set and reader IP allow-list set

Commissioned by: ____________  Date: ____________  Computer/OS: ____________  Reader serial/MAC: ____________

## 12. Test record (fill in after your run)

| Item | OS | Result | Notes |
|---|---|---|---|
| Windows start + one-click setup | | | |
| macOS start + one-click setup | | | |
| Windows/macOS auto-start | | | |
| WiFi interface | | | |
| HTTP/MQTT to real server | | | |
| Spool: unplug network, read tags, plug back → items resent | | | |
| Reboot → service/page back, tags arrive | | | |
| Restore backup | | | |

## 13. Reference

| Item | Value |
|---|---|
| Reader command port | TCP **60000** (reader side) |
| Tag push port | TCP **6000** (computer side, configurable) |
| Discovery | reader broadcasts UDP 65000 → 65001 every ~6 s |
| Web UI | `http://127.0.0.1:8088` (`--host`, `--port`, `--password` to change) |
| Health check | `/api/health` (200 = reader pushing, 503 = not) |
| Forward spool | `forward_spool.jsonl` (auto-resent) |
| Output data | `selfmade_reads.csv` in the program folder |
| Settings file | `selfmade_reader_config.json` (do not commit; may hold credentials) |
| Reader interface codes | 0 USB · 1 RS232/RS485 · **2 RJ45** · 3 WIFI · 4 Weigand · 5 Keyboard · 6 KeyboardNoEnter · 7 4G · 8 BlueTooth (1, 2, 7 verified) |
| Protocol and byte layouts | `docs/TECHNICAL_NOTES.md` |
