# Selfmade Reader

Browser-based configuration, monitoring and data-forwarding tool for **UHF RFID readers of the SN5300 / CF5300 type** (board "SN5300 V1.6", module "M605").
One Python file, **no dependencies** (Python 3.8+ standard library only).

- Configure the reader from a web page (output interface, remote server, network, WiFi, RF power) with automatic backup/restore.
- Live tag dashboard.
- Stores reads to CSV (de-duplicated, optional daily files).
- Forwards reads to an HTTP webhook, an MQTT broker or a TCP server over whatever network the computer has (Ethernet, WiFi, 4G/5G hotspot).
- Queues forwarded data on disk when the link is down and resends it; `/api/health` endpoint for monitoring; optional password and reader-IP allow-list.
- Optional start-at-boot (Linux systemd, macOS launchd, Windows Task Scheduler).

> **New to this?** Follow **[docs/SOP.md](docs/SOP.md)** step by step.

## Quick start

```bash
python3 selfmade_reader.py          # Windows: py selfmade_reader.py
# open http://127.0.0.1:8088 -> Reader setup -> "One-click Ethernet setup"
```
Or double-click `START_WINDOWS.bat` / `START_MAC.command` / `START_LINUX.sh`.

The computer must be on the reader's network (reader default `192.168.1.250/24`; give the computer e.g. `192.168.1.20/24`, no gateway).

## How it works

The reader's Interface is set to **RJ45**; it then connects *as a TCP client* to this program (default port **6000**) and pushes tag reports. The reader's own command port (**TCP 60000**) is used for reading/writing its settings. Protocol details: [docs/TECHNICAL_NOTES.md](docs/TECHNICAL_NOTES.md).

## Files

| File | Purpose |
|---|---|
| `selfmade_reader.py` | the whole application |
| `START_*` / `INSTALL_AUTOSTART_*` | double-click launchers for Windows / macOS / Linux |
| `docs/SOP.md` | standard operating procedure for deploying and operating |
| `docs/TECHNICAL_NOTES.md` | protocol, settings layout, findings, status of features |

## Status

Developed and tested on **Linux** with a real reader (tag reception, CSV, settings read, auto-start, crash-restart). HTTP/MQTT/TCP forwarding verified against local test servers only. **Not yet tested:** Windows/macOS, WiFi and 4G interfaces, forwarding to a real cloud endpoint. See the SOP for what is verified.

## Safety

- Never set the reader's *Work mode* to **Answer**: it stops pushing tags and silences the buzzer.
- A backup of the reader settings is saved to `backup/` before every write. Keep it.
- The web UI listens on `127.0.0.1` only unless started with `--host 0.0.0.0`; anyone who can open the page can change the reader's settings, so use `--password` and only expose it on a trusted network. You can also restrict which reader IPs may push tags.
- Don't commit `selfmade_reader_config.json` (may hold MQTT/HTTP credentials) or the CSV data; `.gitignore` already excludes them.

## Not included

The manufacturer's Windows tool ("Reader software 5.0") is not redistributed here. It is not required.

## License

No license has been chosen yet (all rights reserved by default). Add a `LICENSE` file before sharing publicly.
