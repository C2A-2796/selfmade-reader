#!/usr/bin/env python3
"""
Selfmade Reader  -  configure, monitor, store and forward UHF RFID tag data.

Works with the SN5300 / CF5300 style UHF reader ("SW"/"CT" protocol).
Needs only Python 3.8+ (standard library). Run:

    python3 selfmade_reader.py            # then open http://127.0.0.1:8088
    python3 selfmade_reader.py --host 0.0.0.0 --port 8088   # reachable from the LAN

How it works
  * The reader (Interface = RJ45/WIFI/4G) connects to THIS program as a TCP client
    and pushes tag reports. This program listens on `listen_port` (default 6000).
  * The reader's command port (TCP 60000) is used to read/write its settings.
  * Tags are shown live, appended to a CSV, and optionally forwarded over HTTP,
    TCP or MQTT using whatever network this computer has (Ethernet, WiFi, 4G/5G hotspot ...).
"""
import argparse, csv, json, os, queue, socket, struct, sys, threading, time, webbrowser
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

APP_NAME = "Selfmade Reader"
HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "selfmade_reader_config.json")
BACKUP_DIR = os.path.join(HERE, "backup")

DEFAULT_CONFIG = {
    "reader_ip": "192.168.1.250",
    "reader_port": 60000,          # reader's command / config port
    "listen_port": 6000,           # port this PC listens on for pushed tags
    "csv_path": os.path.join(HERE, "selfmade_reads.csv"),
    "csv_enabled": True,
    "dedup_seconds": 0,            # 0 = store every read, N = one row per EPC per N seconds
    "http":  {"enabled": False, "url": "", "auth_header": ""},
    "tcp":   {"enabled": False, "host": "", "port": 9000},
    "mqtt":  {"enabled": False, "host": "", "port": 1883, "topic": "rfid/tags",
              "user": "", "password": "", "client_id": "selfmade-reader"},
}

INTERFACES = {0: "USB", 1: "RS232/RS485", 2: "RJ45 (Ethernet)", 3: "WIFI", 4: "Weigand",
              5: "Keyboard", 6: "KeyboardNoEnter", 7: "4G", 8: "BlueTooth"}
WORKMODES = {0: "Answer mode", 1: "Active mode", 2: "Trigger mode"}

lock = threading.RLock()
cfg = {}
tags = {}                  # epc -> {count, rssi, last, first, ant}
recent = []                # last events
clients, clients_lock = [], threading.Lock()
stats = {"reads": 0, "connections": 0, "csv_rows": 0, "started": time.time(),
         "fwd_ok": 0, "fwd_fail": 0, "fwd_queued": 0}
reader_links = {}          # ip -> last seen
last_csv = {}              # epc -> last time written (dedup)
fwd_q = queue.Queue(maxsize=20000)
csv_lock = threading.Lock()


# ------------------------------------------------------------------ config
def load_config():
    global cfg
    c = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH) as f:
            saved = json.load(f)
        for k, v in saved.items():
            if isinstance(v, dict) and isinstance(c.get(k), dict):
                c[k].update(v)
            else:
                c[k] = v
    except (OSError, ValueError):
        pass
    cfg = c

def save_config():
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ------------------------------------------------------------------ events
def emit(event):
    msg = ("data: " + json.dumps(event) + "\n\n").encode()
    with clients_lock:
        for q in list(clients):
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass

def log(text, level="info"):
    line = f"{datetime.now().strftime('%H:%M:%S')} {text}"
    print(line, flush=True)
    emit({"type": "log", "text": line, "level": level})


# ------------------------------------------------------------------ protocol
def sw_frame(cmd, data=b""):
    """Request: 'SW' LEN(2,BE) ADDR=FF CMD DATA CHK; CHK = -sum(previous) & 0xFF."""
    b = b"SW" + (len(data) + 3).to_bytes(2, "big") + bytes([0xFF, cmd]) + data
    return b + bytes([(-sum(b)) & 0xFF])

def split_frames(buf):
    """Return (list_of_CT_frames, leftover) from a byte buffer."""
    out = []
    while buf:
        if buf[0] == 0x43 and len(buf) >= 2 and buf[1] == 0x54:
            if len(buf) < 4:
                break
            end = 4 + ((buf[2] << 8) | buf[3])
            if len(buf) < end:
                break
            out.append(buf[:end])
            buf = buf[end:]
        elif buf[0] == 0x43 and len(buf) < 2:
            break
        else:
            buf = buf[1:]
    return out, buf

def tag_records(frame):
    """Decode a CT 0x45 tag report -> list of (epc_hex, rssi, antenna)."""
    res = []
    if len(frame) < 16 or frame[5] != 0x45 or frame[6] != 0x01:
        return res
    n, i = frame[14], 15
    for _ in range(n):
        if i >= len(frame):
            break
        L = frame[i]
        rec = frame[i + 1:i + 1 + L]
        if len(rec) == L and L > 3:
            res.append((rec[2:L - 1].hex().upper(), rec[L - 1], rec[0]))
        i += 1 + L
    return res

def reader_cmd(cmd, data=b"", timeout=2.5):
    """Send one command to the reader's config port and return the reply data
    (bytes after the status byte, without checksum). Raises on failure."""
    with socket.create_connection((cfg["reader_ip"], int(cfg["reader_port"])), timeout=timeout) as s:
        s.settimeout(timeout)
        s.sendall(sw_frame(cmd, data))
        buf, deadline = b"", time.time() + timeout
        while time.time() < deadline:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
            frames, buf2 = split_frames(buf)
            for f in frames:
                if f[5] == cmd:          # ignore pushed tag frames
                    if f[6] != 0x01:
                        raise IOError(f"reader refused command 0x{cmd:02X} (status {f[6]:02X})")
                    return f[7:-1]
            buf = buf2
    raise IOError(f"no reply to command 0x{cmd:02X}")


# ------------------------------------------------------------------ reader settings
def decode_params(d):
    return {"interface": d[2], "rf_power": d[6], "work_mode": d[7],
            "wg_out_interval": d[17], "wg_pulse_width": d[18], "wg_pulse_interval": d[19],
            "raw": d.hex(" ")}

def decode_network(d):
    def ip(o): return ".".join(str(x) for x in d[o:o + 4])
    def txt(o): return d[o:o + 32].split(b"\0")[0].decode("ascii", "replace")
    return {"mac": d[3:9].hex(":"), "ip": ip(9), "mask": ip(13), "gateway": ip(17),
            "remote_ip": ip(21), "local_port": int.from_bytes(d[25:27], "little"),
            "remote_port": int.from_bytes(d[27:29], "little"), "heartbeat": d[31],
            "wifi_ssid": txt(64), "wifi_password": txt(96), "raw": d.hex(" ")}

def ip_bytes(s):
    p = [int(x) for x in s.split(".")]
    if len(p) != 4 or any(not 0 <= x <= 255 for x in p):
        raise ValueError(f"bad IP address: {s}")
    return bytes(p)

def backup_reader(note=""):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    snap = {"time": datetime.now().isoformat(timespec="seconds"), "note": note}
    for name, cmd in (("params", 0x20), ("network", 0x26), ("advanced", 0x2E)):
        try:
            snap[name] = reader_cmd(cmd).hex()
        except IOError as e:
            snap[name] = None
            snap[name + "_error"] = str(e)
    fn = os.path.join(BACKUP_DIR, f"selfmade_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(fn, "w") as f:
        json.dump(snap, f, indent=1)
    return os.path.basename(fn)

def write_params(d):
    return reader_cmd(0x21, bytes(d[:21]) + bytes(13))

def write_network(d):
    if len(d) != 225:
        raise ValueError("unexpected network block size")
    return reader_cmd(0x27, bytes(d) + bytes(28))

def apply_params(req):
    cur = bytearray(reader_cmd(0x20))
    if len(cur) != 33:
        raise IOError("unexpected parameter block size from reader")
    if "interface" in req:
        v = int(req["interface"]);   assert v in INTERFACES, "bad interface"; cur[2] = v
    if "work_mode" in req:
        v = int(req["work_mode"]);   assert v in WORKMODES, "bad work mode";  cur[7] = v
    if "rf_power" in req:
        v = int(req["rf_power"]);    assert 0 <= v <= 30, "RF power must be 0-30 dBm"; cur[6] = v
    for key, idx in (("wg_out_interval", 17), ("wg_pulse_width", 18), ("wg_pulse_interval", 19)):
        if key in req:
            v = int(req[key]);       assert 0 <= v <= 255, key; cur[idx] = v
    write_params(cur)

def apply_network(req):
    cur = bytearray(reader_cmd(0x26))
    if len(cur) != 225:
        raise IOError("unexpected network block size from reader")
    for key, off in (("ip", 9), ("mask", 13), ("gateway", 17), ("remote_ip", 21)):
        if req.get(key):
            cur[off:off + 4] = ip_bytes(req[key])
    for key, off in (("local_port", 25), ("remote_port", 27)):
        if req.get(key) not in (None, ""):
            v = int(req[key]); assert 0 <= v <= 65535, key
            cur[off:off + 2] = v.to_bytes(2, "little")
    if req.get("heartbeat") not in (None, ""):
        v = int(req["heartbeat"]); assert 0 <= v <= 255, "heartbeat"; cur[31] = v
    for key, off in (("wifi_ssid", 64), ("wifi_password", 96)):
        if key in req and req[key] is not None:
            raw = str(req[key]).encode("ascii")
            assert len(raw) <= 31, f"{key} too long"
            cur[off:off + 32] = raw.ljust(32, b"\0")
    write_network(cur)

def local_ip_for_reader():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((cfg["reader_ip"], 9))
        return s.getsockname()[0]
    finally:
        s.close()

def discover(seconds=7):
    """Listen for the reader's UDP discovery broadcast (port 65001)."""
    found = {}
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind(("", 65001))
    except OSError as e:
        return {"error": str(e), "readers": []}
    s.settimeout(1)
    end = time.time() + seconds
    while time.time() < end:
        try:
            data, addr = s.recvfrom(2048)
        except socket.timeout:
            continue
        if data[:2] == b"CT" and len(data) >= 37:
            found[addr[0]] = {"ip": ".".join(str(x) for x in data[24:28]),
                              "mac": data[18:24].hex(":"),
                              "gateway": ".".join(str(x) for x in data[32:36]),
                              "port": int.from_bytes(data[36:38], "big") if len(data) >= 38 else 60000}
    s.close()
    return {"readers": list(found.values())}


# ------------------------------------------------------------------ tag handling
def handle_tag(epc, rssi, ant, src):
    now = time.time()
    with lock:
        t = tags.setdefault(epc, {"count": 0, "first": now})
        t.update(count=t["count"] + 1, rssi=rssi, last=now, ant=ant, src=src)
        stats["reads"] += 1
        ev = {"type": "tag", "t": now, "epc": epc, "rssi": rssi, "ant": ant, "src": src,
              "count": t["count"]}
        recent.append(ev)
        del recent[:-300]
        write_csv = cfg["csv_enabled"] and cfg["csv_path"]
        ded = float(cfg.get("dedup_seconds") or 0)
        if ded > 0:
            if now - last_csv.get(epc, 0) < ded:
                write_csv = False
            else:
                last_csv[epc] = now
    if write_csv:
        csv_append(now, epc, rssi, ant, src)
    emit(ev)
    for sink in ("http", "tcp", "mqtt"):
        if cfg[sink]["enabled"]:
            try:
                fwd_q.put_nowait((sink, ev))
                stats["fwd_queued"] = fwd_q.qsize()
            except queue.Full:
                stats["fwd_fail"] += 1

def csv_append(ts, epc, rssi, ant, src):
    path = cfg["csv_path"]
    with csv_lock:
        try:
            new = not os.path.exists(path) or os.path.getsize(path) == 0
            with open(path, "a", newline="") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(["timestamp", "epc", "rssi", "antenna", "reader_ip"])
                w.writerow([datetime.fromtimestamp(ts).isoformat(timespec="milliseconds"),
                            epc, rssi, ant, src])
            stats["csv_rows"] += 1
        except OSError as e:
            log(f"CSV write failed: {e}", "error")


# ------------------------------------------------------------------ receiver (reader -> PC)
def serve_reader(conn, addr):
    ip = addr[0]
    stats["connections"] += 1
    log(f"Reader connected from {ip}")
    emit({"type": "link", "ip": ip, "up": True})
    buf = b""
    conn.settimeout(120)
    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            reader_links[ip] = time.time()
            frames, buf = split_frames(buf + data)
            for f in frames:
                for epc, rssi, ant in tag_records(f):
                    handle_tag(epc, rssi, ant, ip)
    except OSError:
        pass
    finally:
        conn.close()
        log(f"Reader {ip} disconnected")
        emit({"type": "link", "ip": ip, "up": False})

def listener_loop():
    """(Re)bind to listen_port whenever it changes."""
    current, srv = None, None
    while True:
        want = int(cfg["listen_port"])
        if want != current:
            if srv:
                srv.close()
            try:
                srv = socket.socket()
                srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                srv.bind(("0.0.0.0", want))
                srv.listen(5)
                srv.settimeout(1)
                current = want
                log(f"Listening for readers on TCP port {want}")
            except OSError as e:
                log(f"Cannot listen on port {want}: {e}", "error")
                srv, current = None, None
                time.sleep(3)
                continue
        try:
            conn, addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            current = None
            continue
        threading.Thread(target=serve_reader, args=(conn, addr), daemon=True).start()


# ------------------------------------------------------------------ forwarding (PC -> cloud)
class Mqtt:
    def __init__(self):
        self.sock, self.key = None, None
    @staticmethod
    def _s(b): return struct.pack(">H", len(b)) + b
    @staticmethod
    def _len(n):
        out = b""
        while True:
            d, n = n % 128, n // 128
            out += bytes([d | (128 if n else 0)])
            if not n:
                return out
    def _connect(self, c):
        s = socket.create_connection((c["host"], int(c["port"])), timeout=8)
        flags = 0x02
        payload = self._s(c["client_id"].encode() or b"selfmade")
        if c.get("user"):
            flags |= 0x80; payload += self._s(c["user"].encode())
            if c.get("password"):
                flags |= 0x40; payload += self._s(c["password"].encode())
        var = self._s(b"MQTT") + bytes([4, flags]) + struct.pack(">H", 60)
        s.sendall(b"\x10" + self._len(len(var) + len(payload)) + var + payload)
        ack = s.recv(4)
        if len(ack) < 4 or ack[0] != 0x20 or ack[3] != 0:
            s.close(); raise IOError(f"MQTT connect refused ({ack.hex()})")
        self.sock, self.key = s, json.dumps(c, sort_keys=True)
    def publish(self, c, topic, payload):
        if self.sock is None or self.key != json.dumps(c, sort_keys=True):
            self.close(); self._connect(c)
        body = self._s(topic.encode()) + payload
        try:
            self.sock.sendall(b"\x30" + self._len(len(body)) + body)
        except OSError:
            self.close(); self._connect(c)
            self.sock.sendall(b"\x30" + self._len(len(body)) + body)
    def close(self):
        try:
            if self.sock: self.sock.close()
        except OSError:
            pass
        self.sock = None

def forward_loop():
    mqtt, tcp = Mqtt(), {"sock": None, "key": None}
    while True:
        sink, ev = fwd_q.get()
        stats["fwd_queued"] = fwd_q.qsize()
        payload = json.dumps({"epc": ev["epc"], "rssi": ev["rssi"], "antenna": ev["ant"],
                              "reader": ev["src"],
                              "time": datetime.fromtimestamp(ev["t"]).isoformat(timespec="milliseconds")})
        ok = False
        for attempt in range(3):
            try:
                c = cfg[sink]
                if sink == "http":
                    req = urllib.request.Request(c["url"], data=payload.encode(), method="POST",
                                                 headers={"Content-Type": "application/json"})
                    if c.get("auth_header"):
                        k, _, v = c["auth_header"].partition(":")
                        req.add_header(k.strip(), v.strip())
                    urllib.request.urlopen(req, timeout=8).read()
                elif sink == "tcp":
                    key = (c["host"], c["port"])
                    if tcp["sock"] is None or tcp["key"] != key:
                        if tcp["sock"]: tcp["sock"].close()
                        tcp["sock"], tcp["key"] = socket.create_connection((c["host"], int(c["port"])), timeout=8), key
                    tcp["sock"].sendall(payload.encode() + b"\n")
                else:
                    mqtt.publish(c, c["topic"], payload.encode())
                ok = True
                break
            except Exception as e:
                if sink == "tcp" and tcp["sock"]:
                    try: tcp["sock"].close()
                    except OSError: pass
                    tcp["sock"] = None
                mqtt.close() if sink == "mqtt" else None
                err = str(e)
                time.sleep(1.5)
        if ok:
            stats["fwd_ok"] += 1
        else:
            stats["fwd_fail"] += 1
            log(f"Forward to {sink} failed: {err}", "error")


# ------------------------------------------------------------------ web UI
def state_json():
    with lock:
        rows = sorted(({"epc": e, **t} for e, t in tags.items()), key=lambda r: -r["last"])
        s = dict(stats)
    s["uptime"] = int(time.time() - s.pop("started"))
    now = time.time()
    return {"app": APP_NAME, "config": cfg, "stats": s, "tags": rows[:1000], "recent": recent[-100:],
            "links": {ip: round(now - t, 1) for ip, t in reader_links.items()},
            "interfaces": INTERFACES, "workmodes": WORKMODES}

def list_backups():
    try:
        return sorted(f for f in os.listdir(BACKUP_DIR) if f.endswith(".json"))[::-1]
    except OSError:
        return []

def api_post(path, body):
    global cfg
    if path == "/api/config":
        with lock:
            for k, v in body.items():
                if k in cfg:
                    if isinstance(cfg[k], dict) and isinstance(v, dict):
                        cfg[k].update(v)
                    else:
                        cfg[k] = v
            save_config()
        log("Settings saved")
        return {"ok": True}
    if path == "/api/tags/clear":
        with lock:
            tags.clear(); recent.clear(); last_csv.clear()
        emit({"type": "clear"})
        return {"ok": True}
    if path == "/api/reader/read":
        out = {}
        out["params"] = decode_params(reader_cmd(0x20))
        out["network"] = decode_network(reader_cmd(0x26))
        try:
            out["serial"] = reader_cmd(0xF4).split(b"\0")[0].decode("ascii", "replace")
        except IOError:
            out["serial"] = ""
        out["this_pc_ip"] = local_ip_for_reader()
        return out
    if path == "/api/reader/params":
        name = backup_reader("before params change")
        apply_params(body); log(f"Reader parameters written (backup {name})")
        return {"ok": True, "backup": name}
    if path == "/api/reader/network":
        name = backup_reader("before network change")
        apply_network(body); log(f"Reader network settings written (backup {name}); restart reader to apply")
        return {"ok": True, "backup": name}
    if path == "/api/reader/restart":
        try:
            reader_cmd(0x30, timeout=2)
        except IOError:
            pass                      # reader may reboot before answering
        log("Reader restart requested")
        return {"ok": True}
    if path == "/api/reader/setup_ethernet":
        pc = local_ip_for_reader()
        name = backup_reader("before one-click Ethernet setup")
        apply_params({"interface": 2})
        apply_network({"remote_ip": pc, "remote_port": cfg["listen_port"]})
        log(f"Reader set to RJ45, pushing to {pc}:{cfg['listen_port']} (backup {name}). Restart it to apply.")
        return {"ok": True, "backup": name, "pc_ip": pc}
    if path == "/api/reader/backup":
        return {"ok": True, "backup": backup_reader("manual")}
    if path == "/api/reader/restore":
        fn = os.path.basename(body["file"])
        with open(os.path.join(BACKUP_DIR, fn)) as f:
            snap = json.load(f)
        pre = backup_reader("before restore of " + fn)
        if snap.get("params"):
            write_params(bytearray(bytes.fromhex(snap["params"])))
        if snap.get("network"):
            write_network(bytes.fromhex(snap["network"]))
        log(f"Restored {fn} (current state saved as {pre}); restart reader to apply")
        return {"ok": True}
    if path == "/api/discover":
        return discover()
    if path == "/api/test/http":
        c = cfg["http"]
        req = urllib.request.Request(c["url"], data=b'{"test":true}', method="POST",
                                     headers={"Content-Type": "application/json"})
        if c.get("auth_header"):
            k, _, v = c["auth_header"].partition(":"); req.add_header(k.strip(), v.strip())
        return {"ok": True, "status": urllib.request.urlopen(req, timeout=8).status}
    if path == "/api/test/mqtt":
        m = Mqtt(); m.publish(cfg["mqtt"], cfg["mqtt"]["topic"], b'{"test":true}'); m.close()
        return {"ok": True}
    if path == "/api/test/tcp":
        socket.create_connection((cfg["tcp"]["host"], int(cfg["tcp"]["port"])), timeout=5).close()
        return {"ok": True}
    raise KeyError(path)

class Handler(BaseHTTPRequestHandler):
    server_version = "SelfmadeReader"
    def log_message(self, *a): pass
    def _send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)
    def _origin_ok(self):
        o = self.headers.get("Origin")
        return o is None or o.split("//")[-1] == self.headers.get("Host")
    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/":
            self._send(200, PAGE.replace("__APP__", APP_NAME), "text/html; charset=utf-8")
        elif p == "/api/state":
            self._send(200, state_json())
        elif p == "/api/backups":
            self._send(200, list_backups())
        elif p == "/download.csv":
            try:
                with open(cfg["csv_path"], "rb") as f:
                    data = f.read()
            except OSError:
                data = b""
            self._send(200, data, "text/csv", {"Content-Disposition": "attachment; filename=rfid_reads.csv"})
        elif p == "/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            q = queue.Queue(maxsize=2000)
            with clients_lock:
                clients.append(q)
            try:
                while True:
                    try:
                        self.wfile.write(q.get(timeout=10))
                    except queue.Empty:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except OSError:
                pass
            finally:
                with clients_lock:
                    if q in clients:
                        clients.remove(q)
        else:
            self._send(404, {"error": "not found"})
    def do_POST(self):
        if not self._origin_ok() or self.headers.get("X-Requested-With") != "selfmade":
            return self._send(403, {"error": "forbidden"})
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
            self._send(200, api_post(self.path, body))
        except KeyError:
            self._send(404, {"error": "unknown endpoint"})
        except Exception as e:                      # report any failure to the UI
            log(f"{self.path}: {e}", "error")
            self._send(500, {"error": str(e)})

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__APP__</title>
<style>
:root{--bg:#f4f6f8;--card:#fff;--ink:#17202a;--mut:#667085;--line:#e1e6ec;--acc:#0b6bcb;--acc2:#e8f1fb;--ok:#18794e;--bad:#c0362c;--warn:#a15c07}
@media(prefers-color-scheme:dark){:root{--bg:#0f1419;--card:#18202a;--ink:#e6ebf1;--mut:#93a1b1;--line:#263140;--acc:#4da3ff;--acc2:#16283d;--ok:#4cc38a;--bad:#ff7b72;--warn:#e3b341}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,Segoe UI,Roboto,sans-serif}
header{display:flex;align-items:center;gap:14px;padding:12px 20px;background:var(--card);border-bottom:1px solid var(--line);flex-wrap:wrap}
h1{font-size:18px;margin:0;font-weight:700}.pill{padding:3px 10px;border-radius:99px;font-size:12px;background:var(--acc2);color:var(--acc)}
.pill.ok{background:rgba(24,121,78,.15);color:var(--ok)}.pill.bad{background:rgba(192,54,44,.15);color:var(--bad)}
nav{display:flex;gap:4px;padding:0 20px;background:var(--card);border-bottom:1px solid var(--line);overflow:auto}
nav button{border:0;background:none;color:var(--mut);padding:11px 14px;font:inherit;cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap}
nav button.on{color:var(--acc);border-color:var(--acc);font-weight:600}
main{padding:18px 20px;max-width:1150px;margin:0 auto}section{display:none}section.on{display:block}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
.card h2{font-size:15px;margin:0 0 4px}.sub{color:var(--mut);margin:0 0 12px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
label{display:block;font-size:12px;color:var(--mut);margin-bottom:3px}
input,select{width:100%;padding:7px 9px;border:1px solid var(--line);border-radius:7px;background:var(--bg);color:var(--ink);font:inherit}
input[type=checkbox]{width:auto}
button.b{padding:8px 14px;border-radius:7px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer;font:inherit}
a.b{color:var(--ink);display:inline-block}button.b.p{background:var(--acc);border-color:var(--acc);color:#fff}button.b.d{color:var(--bad)}button.b:disabled{opacity:.5}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:12px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line)}
th{font-size:12px;color:var(--mut);font-weight:600}td.m{font-family:ui-monospace,Consolas,monospace}
tr.new{background:var(--acc2)}.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}.stat b{display:block;font-size:22px}.stat span{color:var(--mut);font-size:12px}
#log{font:12px ui-monospace,Consolas,monospace;height:340px;overflow:auto;background:#0d1117;color:#b9e6c9;padding:10px;border-radius:8px;white-space:pre-wrap}
.warn{color:var(--warn);font-size:12px;margin-top:4px}.note{background:var(--acc2);padding:9px 12px;border-radius:8px;font-size:13px;margin-bottom:12px}
#toast{position:fixed;right:18px;bottom:18px;padding:11px 16px;border-radius:8px;background:var(--ink);color:var(--bg);display:none;max-width:420px}
</style></head><body>
<header><h1>__APP__</h1><span id="link" class="pill bad">no reader connected</span><span id="up" class="pill"></span></header>
<nav id="nav"></nav>
<main>
<section id="s-dash"><div class="stats">
 <div class="stat"><b id="st-reads">0</b><span>reads received</span></div>
 <div class="stat"><b id="st-uniq">0</b><span>unique tags</span></div>
 <div class="stat"><b id="st-csv">0</b><span>rows saved to CSV</span></div>
 <div class="stat"><b id="st-fwd">0</b><span>forwarded OK / failed</span></div></div>
 <div class="card"><h2>Live tags</h2><p class="sub">Updated as the reader pushes data.</p>
 <div class="row" style="margin:0 0 10px"><button class="b" onclick="act('/api/tags/clear',{})">Clear list</button><a class="b" style="text-decoration:none" href="/download.csv">Download CSV</a></div>
 <table><thead><tr><th>Tag (EPC)</th><th>Reads</th><th>RSSI</th><th>Antenna</th><th>Last seen</th></tr></thead><tbody id="tags"></tbody></table></div></section>

<section id="s-setup"><div class="card"><h2>Quick setup: send tags over Ethernet</h2>
 <p class="sub">Sets the reader's Interface to RJ45 and points its remote server at this computer, then restarts it.</p>
 <div class="grid"><div><label>Reader IP</label><input id="c-ip"></div><div><label>Reader command port</label><input id="c-rport" type="number"></div>
 <div><label>Listen port on this computer</label><input id="c-lport" type="number"></div></div>
 <div class="row"><button class="b" onclick="saveConn()">Save</button><button class="b" onclick="discover()">Find readers on the network</button>
 <button class="b p" onclick="oneClick()">One-click Ethernet setup</button></div><div id="found" class="sub" style="margin-top:10px"></div></div>

 <div class="card"><h2>Reader settings</h2><p class="sub">Read the reader's current settings, edit, then write. A backup is saved before every change.</p>
 <div class="grid">
  <div><label>Output interface</label><select id="p-if"></select><div class="warn">Verified: RS232/RS485, RJ45, 4G</div></div>
  <div><label>Work mode</label><select id="p-wm"></select><div class="warn">Use Active mode. Answer mode stops pushing.</div></div>
  <div><label>RF power (dBm, 0-30)</label><input id="p-pw" type="number" min="0" max="30"></div>
  <div><label>Wiegand out interval (x10ms)</label><input id="p-wi" type="number"></div>
  <div><label>Wiegand pulse width (x10us)</label><input id="p-ww" type="number"></div>
  <div><label>Wiegand pulse interval (x100us)</label><input id="p-wp" type="number"></div></div>
 <div class="row"><button class="b" onclick="readReader()">Read from reader</button><button class="b p" onclick="writeParams()">Write settings</button>
 <span id="sn" class="sub" style="margin:0"></span></div></div>

 <div class="card"><h2>Reader network</h2><p class="sub">Used by Ethernet, WiFi and 4G. Changes apply after the reader restarts.</p>
 <div class="grid">
  <div><label>Reader IP</label><input id="n-ip"></div><div><label>Subnet mask</label><input id="n-mask"></div><div><label>Gateway</label><input id="n-gw"></div>
  <div><label>Remote server IP (where tags are pushed)</label><input id="n-rip"></div><div><label>Remote server port</label><input id="n-rport" type="number"></div>
  <div><label>Reader local port</label><input id="n-lport" type="number"></div><div><label>Heartbeat (x10 s)</label><input id="n-hb" type="number"></div>
  <div><label>WiFi network (SSID)</label><input id="n-ssid"></div><div><label>WiFi password</label><input id="n-wpass"></div></div>
 <div class="warn">Changing the reader's own IP/mask/gateway can make it unreachable from this computer. Use the backup to restore.</div>
 <div class="row"><button class="b p" onclick="writeNet()">Write network settings</button><button class="b" onclick="restart()">Restart reader</button>
 <button class="b" onclick="setPcAsRemote()">Use this computer as remote server</button></div></div>

 <div class="card"><h2>Backups</h2><p class="sub">Saved automatically before each change.</p><div class="row" style="margin:0 0 10px">
 <select id="bk" style="max-width:360px"></select><button class="b" onclick="backupNow()">Backup now</button><button class="b d" onclick="restore()">Restore selected</button></div></div></section>

<section id="s-data"><div class="card"><h2>Storage</h2><p class="sub">Every tag read is appended to a CSV file.</p>
 <div class="grid"><div><label>CSV file path</label><input id="d-csv"></div>
 <div><label>Save</label><select id="d-ded"><option value="0">every read</option><option value="1">one row per tag per 1 s</option><option value="5">per 5 s</option><option value="60">per minute</option></select></div>
 <div><label>CSV enabled</label><select id="d-csve"><option value="true">yes</option><option value="false">no</option></select></div></div></div>
 <div class="card"><h2>Forward over the internet</h2><p class="sub">Uses whatever connection this computer has: Ethernet, WiFi, or a 4G/5G hotspot.</p>
 <div class="note">HTTP and MQTT payload: {"epc","rssi","antenna","reader","time"}.</div>
 <h2 style="margin-top:6px">HTTP / webhook</h2><div class="grid"><div><label>Enabled</label><select id="h-en"><option value="false">no</option><option value="true">yes</option></select></div>
 <div><label>URL (POST JSON)</label><input id="h-url" placeholder="https://example.com/rfid"></div><div><label>Auth header (optional)</label><input id="h-auth" placeholder="Authorization: Bearer ..."></div></div>
 <div class="row"><button class="b" onclick="testSink('http')">Test</button></div>
 <h2 style="margin-top:14px">MQTT</h2><div class="grid"><div><label>Enabled</label><select id="m-en"><option value="false">no</option><option value="true">yes</option></select></div>
 <div><label>Broker host</label><input id="m-host"></div><div><label>Port</label><input id="m-port" type="number"></div><div><label>Topic</label><input id="m-topic"></div>
 <div><label>Username</label><input id="m-user"></div><div><label>Password</label><input id="m-pass" type="password"></div><div><label>Client ID</label><input id="m-cid"></div></div>
 <div class="row"><button class="b" onclick="testSink('mqtt')">Test</button></div>
 <h2 style="margin-top:14px">TCP (one JSON line per read)</h2><div class="grid"><div><label>Enabled</label><select id="t-en"><option value="false">no</option><option value="true">yes</option></select></div>
 <div><label>Host</label><input id="t-host"></div><div><label>Port</label><input id="t-port" type="number"></div></div>
 <div class="row"><button class="b" onclick="testSink('tcp')">Test</button><button class="b p" onclick="saveData()">Save data settings</button></div></div></section>

<section id="s-log"><div class="card"><h2>Activity log</h2><div id="log"></div></div></section>
</main><div id="toast"></div>
<script>
const $=id=>document.getElementById(id);let S=null,loaded=false;
const tabs=[["dash","Dashboard"],["setup","Reader setup"],["data","Data & forwarding"],["log","Log"]];
$("nav").innerHTML=tabs.map(t=>`<button data-t="${t[0]}">${t[1]}</button>`).join("");
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>show(b.dataset.t));
function show(t){document.querySelectorAll("section").forEach(s=>s.classList.toggle("on",s.id=="s-"+t));
 document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("on",b.dataset.t==t));localStorage.tab=t}
show(localStorage.tab||"dash");
function toast(m,bad){const t=$("toast");t.textContent=m;t.style.background=bad?"#c0362c":"";t.style.color=bad?"#fff":"";t.style.display="block";clearTimeout(t._x);t._x=setTimeout(()=>t.style.display="none",4500)}
async function api(p,b){const r=await fetch(p,{method:"POST",headers:{"X-Requested-With":"selfmade","Content-Type":"application/json"},body:JSON.stringify(b||{})});
 const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
async function act(p,b,ok){try{const j=await api(p,b);if(ok)toast(ok);return j}catch(e){toast(e.message,1);throw e}}
function fill(sel,map,v){sel.innerHTML=Object.entries(map).map(([k,n])=>`<option value="${k}">${k} - ${n}</option>`).join("");if(v!=null)sel.value=v}
function loadCfg(c){$("c-ip").value=c.reader_ip;$("c-rport").value=c.reader_port;$("c-lport").value=c.listen_port;
 $("d-csv").value=c.csv_path;$("d-ded").value=String(c.dedup_seconds);$("d-csve").value=String(c.csv_enabled);
 $("h-en").value=String(c.http.enabled);$("h-url").value=c.http.url;$("h-auth").value=c.http.auth_header;
 $("m-en").value=String(c.mqtt.enabled);$("m-host").value=c.mqtt.host;$("m-port").value=c.mqtt.port;$("m-topic").value=c.mqtt.topic;$("m-user").value=c.mqtt.user;$("m-pass").value=c.mqtt.password;$("m-cid").value=c.mqtt.client_id;
 $("t-en").value=String(c.tcp.enabled);$("t-host").value=c.tcp.host;$("t-port").value=c.tcp.port}
async function refresh(){const s=await (await fetch("/api/state")).json();S=s;
 if(!loaded){loaded=true;fill($("p-if"),s.interfaces);fill($("p-wm"),s.workmodes);loadCfg(s.config);loadBackups();readReader(true)}
 $("st-reads").textContent=s.stats.reads;$("st-uniq").textContent=s.tags.length;$("st-csv").textContent=s.stats.csv_rows;$("st-fwd").textContent=s.stats.fwd_ok+" / "+s.stats.fwd_fail;
 const links=Object.entries(s.links).filter(([ip,a])=>a<130);const l=$("link");
 l.className="pill "+(links.length?"ok":"bad");l.textContent=links.length?"reader connected: "+links.map(x=>x[0]).join(", "):"no reader connected";
 $("up").textContent="up "+Math.floor(s.stats.uptime/60)+" min";renderTags(s.tags)}
function renderTags(rows){$("tags").innerHTML=rows.map(r=>`<tr><td class="m">${r.epc}</td><td>${r.count}</td><td>${r.rssi}</td><td>${r.ant}</td><td>${new Date(r.last*1000).toLocaleTimeString()}</td></tr>`).join("")||`<tr><td colspan=5 class="sub">No tags yet. Hold a tag near the reader.</td></tr>`}
function logLine(t){const l=$("log");l.textContent+=t+"\n";if(l.textContent.length>60000)l.textContent=l.textContent.slice(-30000);l.scrollTop=l.scrollHeight}
const es=new EventSource("/events");es.onmessage=e=>{const d=JSON.parse(e.data);
 if(d.type=="log")logLine(d.text);else if(d.type=="tag"){clearTimeout(window._r);window._r=setTimeout(refresh,250)}
 else if(d.type=="link"||d.type=="clear")refresh()};
async function saveConn(){await act("/api/config",{reader_ip:$("c-ip").value.trim(),reader_port:+$("c-rport").value,listen_port:+$("c-lport").value},"Saved")}
async function discover(){$("found").textContent="Listening for reader broadcasts (7 s)...";try{const r=await act("/api/discover",{});
 $("found").innerHTML=r.readers.length?r.readers.map(x=>`Found reader <b>${x.ip}</b> (MAC ${x.mac}) <a href="#" onclick="$('c-ip').value='${x.ip}';saveConn();return false">use it</a>`).join("<br>"):"No reader found. Check cable and that this computer is on 192.168.1.x."}catch(e){$("found").textContent=""}}
async function readReader(quiet){try{const r=await api("/api/reader/read");const p=r.params,n=r.network;
 $("p-if").value=p.interface;$("p-wm").value=p.work_mode;$("p-pw").value=p.rf_power;$("p-wi").value=p.wg_out_interval;$("p-ww").value=p.wg_pulse_width;$("p-wp").value=p.wg_pulse_interval;
 $("n-ip").value=n.ip;$("n-mask").value=n.mask;$("n-gw").value=n.gateway;$("n-rip").value=n.remote_ip;$("n-rport").value=n.remote_port;$("n-lport").value=n.local_port;$("n-hb").value=n.heartbeat;$("n-ssid").value=n.wifi_ssid;$("n-wpass").value=n.wifi_password;
 $("sn").textContent="Reader serial: "+(r.serial||"?")+" | MAC "+n.mac+" | this computer: "+r.this_pc_ip;window._pc=r.this_pc_ip;if(!quiet)toast("Read OK")}catch(e){if(!quiet)toast(e.message,1)}}
async function writeParams(){if(!confirm("Write these settings to the reader?"))return;
 const r=await act("/api/reader/params",{interface:+$("p-if").value,work_mode:+$("p-wm").value,rf_power:+$("p-pw").value,wg_out_interval:+$("p-wi").value,wg_pulse_width:+$("p-ww").value,wg_pulse_interval:+$("p-wp").value},"Written. Restart the reader to apply.");loadBackups()}
async function writeNet(){if(!confirm("Write network settings? Changing the reader IP can make it unreachable."))return;
 await act("/api/reader/network",{ip:$("n-ip").value,mask:$("n-mask").value,gateway:$("n-gw").value,remote_ip:$("n-rip").value,remote_port:$("n-rport").value,local_port:$("n-lport").value,heartbeat:$("n-hb").value,wifi_ssid:$("n-ssid").value,wifi_password:$("n-wpass").value},"Written. Restart the reader to apply.");loadBackups()}
async function restart(){if(!confirm("Restart the reader now?"))return;await act("/api/reader/restart",{},"Restart sent");setTimeout(()=>readReader(true),15000)}
function setPcAsRemote(){if(window._pc){$("n-rip").value=window._pc;$("n-rport").value=$("c-lport").value}else toast("Read from the reader first",1)}
async function oneClick(){if(!confirm("Set the reader to Ethernet (RJ45) and push tags to this computer?"))return;
 await saveConn();const r=await act("/api/reader/setup_ethernet",{});await act("/api/reader/restart",{},"Done. Reader restarting, tags will appear in ~15 s.");loadBackups();setTimeout(()=>readReader(true),15000)}
async function loadBackups(){const b=await (await fetch("/api/backups")).json();$("bk").innerHTML=b.map(x=>`<option>${x}</option>`).join("")||"<option value=''>(none yet)</option>"}
async function backupNow(){await act("/api/reader/backup",{},"Backup saved");loadBackups()}
async function restore(){const f=$("bk").value;if(!f||!confirm("Restore "+f+" to the reader?"))return;await act("/api/reader/restore",{file:f},"Restored. Restart the reader to apply.");loadBackups()}
async function saveData(){await act("/api/config",{csv_path:$("d-csv").value,dedup_seconds:+$("d-ded").value,csv_enabled:$("d-csve").value=="true",
 http:{enabled:$("h-en").value=="true",url:$("h-url").value,auth_header:$("h-auth").value},
 mqtt:{enabled:$("m-en").value=="true",host:$("m-host").value,port:+$("m-port").value,topic:$("m-topic").value,user:$("m-user").value,password:$("m-pass").value,client_id:$("m-cid").value},
 tcp:{enabled:$("t-en").value=="true",host:$("t-host").value,port:+$("t-port").value}},"Saved")}
async function testSink(k){await saveData();try{await api("/api/test/"+k);toast(k.toUpperCase()+" test OK")}catch(e){toast(k.toUpperCase()+" test failed: "+e.message,1)}}
refresh();setInterval(refresh,5000);
</script></body></html>"""



# ------------------------------------------------------------------ auto-start at login/boot
SERVICE_NAME = "selfmade-reader"

def _run(cmd):
    import subprocess
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()

def autostart(install):
    """Install/remove start-at-login for this user (Linux systemd, macOS launchd, Windows Task Scheduler)."""
    script, exe = os.path.abspath(__file__), sys.executable
    if sys.platform.startswith("linux"):
        d = os.path.expanduser("~/.config/systemd/user")
        unit = os.path.join(d, SERVICE_NAME + ".service")
        if install:
            os.makedirs(d, exist_ok=True)
            with open(unit, "w") as f:
                f.write(f"[Unit]\nDescription={APP_NAME}\nAfter=network-online.target\n\n[Service]\n"
                        f"ExecStart={exe} {script} --no-browser\nWorkingDirectory={HERE}\n"
                        f"Restart=always\nRestartSec=5\n\n[Install]\nWantedBy=default.target\n")
            _run(["systemctl", "--user", "daemon-reload"])
            rc, out = _run(["systemctl", "--user", "enable", "--now", SERVICE_NAME + ".service"])
            print(out or "service enabled and started")
            rc2, out2 = _run(["loginctl", "enable-linger", os.environ.get("USER", "")])
            print("Runs from boot, even before login." if rc2 == 0 else
                  "Starts at login. For start at boot without login run once: sudo loginctl enable-linger $USER")
        else:
            _run(["systemctl", "--user", "disable", "--now", SERVICE_NAME + ".service"])
            if os.path.exists(unit): os.remove(unit)
            _run(["systemctl", "--user", "daemon-reload"]); print("auto-start removed")
    elif sys.platform == "darwin":
        plist = os.path.expanduser(f"~/Library/LaunchAgents/com.selfmade.{SERVICE_NAME}.plist")
        if install:
            os.makedirs(os.path.dirname(plist), exist_ok=True)
            with open(plist, "w") as f:
                f.write(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Label</key><string>com.selfmade.{SERVICE_NAME}</string>
<key>ProgramArguments</key><array><string>{exe}</string><string>{script}</string><string>--no-browser</string></array>
<key>WorkingDirectory</key><string>{HERE}</string><key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardOutPath</key><string>{HERE}/selfmade_reader.log</string><key>StandardErrorPath</key><string>{HERE}/selfmade_reader.log</string>
</dict></plist>''')
            _run(["launchctl", "unload", plist]); print(_run(["launchctl", "load", "-w", plist])[1] or "auto-start installed")
        else:
            _run(["launchctl", "unload", "-w", plist])
            if os.path.exists(plist): os.remove(plist)
            print("auto-start removed")
    elif sys.platform.startswith("win"):
        pyw = exe[:-10] + "pythonw.exe" if exe.lower().endswith("python.exe") and os.path.exists(exe[:-10] + "pythonw.exe") else exe
        if install:
            rc, out = _run(["schtasks", "/Create", "/TN", "SelfmadeReader", "/SC", "ONLOGON", "/F",
                            "/TR", f'"{pyw}" "{script}" --no-browser'])
            print(out)
            if rc == 0: _run(["schtasks", "/Run", "/TN", "SelfmadeReader"])
        else:
            print(_run(["schtasks", "/Delete", "/TN", "SelfmadeReader", "/F"])[1])
    else:
        sys.exit("auto-start is not supported on this system")
    if install:
        print(f"{APP_NAME} will now start automatically. UI: http://127.0.0.1:8088")

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=APP_NAME)
    ap.add_argument("--host", default="127.0.0.1", help="address for the web UI (default: this computer only)")
    ap.add_argument("--port", type=int, default=8088, help="web UI port")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--install-autostart", action="store_true", help="start automatically at login/boot, then exit")
    ap.add_argument("--uninstall-autostart", action="store_true", help="remove the automatic start, then exit")
    args = ap.parse_args()
    if args.install_autostart or args.uninstall_autostart:
        return autostart(args.install_autostart)
    load_config()
    threading.Thread(target=listener_loop, daemon=True).start()
    threading.Thread(target=forward_loop, daemon=True).start()
    try:
        srv = ThreadingHTTPServer((args.host, args.port), Handler)
    except OSError as e:
        sys.exit(f"Cannot start web UI on {args.host}:{args.port}: {e}")
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{args.port}"
    print(f"{APP_NAME} running. Open {url}   (Ctrl+C to stop)", flush=True)
    if not args.no_browser:
        threading.Timer(1, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("bye")

if __name__ == "__main__":
    main()
