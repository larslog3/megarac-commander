#!/usr/bin/env python3
# MegaRAC Commander — Unified IPMI 2.0 & Chromeless OpenJDK 8 JViewer Bridge Server
import argparse
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import time
import urllib.parse
import urllib.request
import zipfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

JVIEWER_PROC = None
WORK_DIR = "/tmp/megarac_jviewer"
JVIEWER_LOG_PATH = "/tmp/megarac_jviewer/jviewer.log"
APP_DIR = os.path.dirname(os.path.abspath(__file__))


def is_port_listening(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect((host, port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def append_jviewer_log(msg: str):
    os.makedirs(WORK_DIR, exist_ok=True)
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line.strip(), flush=True)
    with open(JVIEWER_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line)


def ensure_novnc_stack() -> list:
    steps = []
    os.makedirs(WORK_DIR, exist_ok=True)
    if not os.path.exists(JVIEWER_LOG_PATH):
        with open(JVIEWER_LOG_PATH, "w", encoding="utf-8") as f:
            f.write("=== MegaRAC Commander Chromeless JViewer Bridge ===\n")

    if not shutil.which("Xvfb"):
        return ["Native desktop mode (Xvfb not installed on host; running local bridge)"]

    env = os.environ.copy()
    env["DISPLAY"] = ":99"

    if not os.path.exists("/tmp/.X11-unix/X99"):
        subprocess.Popen(
            ["Xvfb", ":99", "-screen", "0", "1280x800x24", "-ac", "+extension", "GLX", "+render", "-noreset"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(40):
            if os.path.exists("/tmp/.X11-unix/X99"):
                break
            time.sleep(0.1)
        steps.append("Started Xvfb display :99 (1280x800x24)")

        fb_dir = os.path.expanduser("~/.fluxbox")
        os.makedirs(fb_dir, exist_ok=True)
        with open(os.path.join(fb_dir, "init"), "w", encoding="utf-8") as f:
            f.write("session.screen0.toolbar.visible: false\n")
            f.write("session.screen0.defaultDeco: NONE\n")

        if shutil.which("fluxbox"):
            subprocess.Popen(["fluxbox"], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(0.3)
            steps.append("Started borderless fluxbox window manager on :99")

    if not is_port_listening(5900) and shutil.which("x11vnc"):
        subprocess.Popen(
            ["x11vnc", "-display", ":99", "-nopw", "-forever", "-shared", "-rfbport", "5900"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            if is_port_listening(5900):
                break
            time.sleep(0.1)
        steps.append(f"x11vnc listening on 127.0.0.1:5900 (ready={is_port_listening(5900)})")

    if not is_port_listening(6080) and shutil.which("websockify"):
        subprocess.Popen(
            ["websockify", "--web=/usr/share/novnc/", "0.0.0.0:6080", "127.0.0.1:5900"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(30):
            if is_port_listening(6080):
                break
            time.sleep(0.1)
        steps.append(f"noVNC websockify listening on 0.0.0.0:6080 (ready={is_port_listening(6080)})")

    return steps


def curl_fetch_bytes(url: str, post_data: str = None, cookie_header: str = None, timeout: int = 10) -> bytes:
    cmd = ["curl", "-k", "-s", "-L", "--raw", "--max-time", str(timeout)]
    if post_data is not None:
        cmd += ["--data", post_data]
    if cookie_header:
        cmd += ["-H", f"Cookie: {cookie_header}"]
    cmd.append(url)
    proc = subprocess.run(cmd, capture_output=True)
    return proc.stdout


def authenticate_megarac_web(host: str, user: str, password: str) -> dict:
    token_regex = re.compile(r"['\"]?(SESSION_COOKIE|STOKEN|SESSION_TOKEN)['\"]?\s*:\s*['\"]([^'\"]+)['\"]")
    post_payload = f"WEBVAR_USERNAME={user}&WEBVAR_PASSWORD={password}"

    for scheme in ["http", "https"]:
        base_url = f"{scheme}://{host}"
        login_url = f"{base_url}/rpc/WEBSES/create.asp"
        append_jviewer_log(f"Authenticating to {login_url} as '{user}'...")
        raw_bytes = curl_fetch_bytes(login_url, post_data=post_payload, timeout=8)
        body = raw_bytes.decode("utf-8", errors="ignore")
        m = token_regex.search(body)
        if m and m.group(2) and m.group(2) != "Failure_Session_Creation":
            cookie = m.group(2)
            stoken = cookie
            append_jviewer_log(f"Obtained SESSION_COOKIE={cookie[:10]}... from {base_url}")
            for ck_hdr in [f"SessionCookie={cookie}", f"Cookie=SessionCookie={cookie}"]:
                t_bytes = curl_fetch_bytes(f"{base_url}/rpc/getsessiontoken.asp", cookie_header=ck_hdr, timeout=6)
                t_body = t_bytes.decode("utf-8", errors="ignore")
                tm = token_regex.search(t_body)
                if tm and tm.group(2):
                    stoken = tm.group(2)
                    append_jviewer_log(f"Obtained KVM STOKEN={stoken[:10]}...")
                    break
            return {
                "ok": True,
                "base_url": base_url,
                "session_cookie": cookie,
                "stoken": stoken,
                "ssl": scheme == "https",
            }

    return {
        "ok": False,
        "stderr": f"Could not obtain SESSION_COOKIE from http(s)://{host}/rpc/WEBSES/create.asp.",
    }


def fetch_megarac_jnlp(host: str, user: str, password: str) -> dict:
    auth = authenticate_megarac_web(host, user, password)
    if not auth["ok"]:
        return auth

    base_url = auth["base_url"]
    cookie = auth["session_cookie"]
    stoken = auth["stoken"]

    candidate_paths = [
        f"/Java/jviewer.jnlp?EXTRNIP={host}&JNLPSTR=JViewer",
        "/Java/jviewer.jnlp",
        f"/viewer.jnlp?{host}",
        "/viewer.jnlp",
        f"/odin/jviewer.jnlp?EXTRNIP={host}",
    ]
    cookie_variants = [
        f"SessionCookie={cookie}",
        f"Cookie=SessionCookie={cookie}",
        f"SessionCookie={cookie}; Stoken={stoken}",
    ]

    for path in candidate_paths:
        for ck in cookie_variants:
            raw = curl_fetch_bytes(base_url + path, cookie_header=ck, timeout=8)
            txt = raw.decode("utf-8", errors="ignore")
            if "<jnlp" in txt.lower():
                append_jviewer_log(f"Fetched JNLP ({len(raw)} bytes) from {path}")
                return {
                    "ok": True,
                    "jnlp_xml": txt,
                    "base_url": base_url,
                    "session_cookie": cookie,
                    "stoken": stoken,
                    "source": path,
                }

    xml = f'''<?xml version="1.0" encoding="utf-8"?>
<jnlp spec="1.0+" codebase="{base_url}/Java/">
  <information>
    <title>JViewer ({host})</title>
    <vendor>American Megatrends, Inc.</vendor>
  </information>
  <security><all-permissions/></security>
  <resources>
    <j2se version="1.5+"/>
    <jar href="release/JViewer.jar"/>
    <jar href="release/JViewer-SOC.jar"/>
  </resources>
  <resources os="Linux" arch="amd64">
    <nativelib href="release/Linux_x86_64.jar"/>
  </resources>
  <application-desc main-class="com.ami.kvm.jviewer.JViewer">
    <argument>-apptype</argument><argument>JViewer</argument>
    <argument>-hostname</argument><argument>{host}</argument>
    <argument>-kvmtoken</argument><argument>{stoken}</argument>
    <argument>-vport</argument><argument>7578</argument>
    <argument>-cdport</argument><argument>5120</argument>
    <argument>-kbdport</argument><argument>7578</argument>
    <argument>-ssl</argument><argument>0</argument>
    <argument>-localization</argument><argument>en</argument>
  </application-desc>
</jnlp>'''
    return {
        "ok": True,
        "jnlp_xml": xml,
        "base_url": base_url,
        "session_cookie": cookie,
        "stoken": stoken,
        "source": "fallback_template",
    }


def ensure_bridge_compiled():
    java_src = os.path.join(APP_DIR, "ModernJViewerBridge.java")
    class_file = os.path.join(APP_DIR, "ModernJViewerBridge.class")
    if os.path.exists(java_src) and not os.path.exists(class_file) and shutil.which("javac"):
        subprocess.run(["javac", "-source", "1.8", "-target", "1.8", java_src], cwd=APP_DIR)
    for fname in os.listdir(APP_DIR):
        if fname.startswith("ModernJViewerBridge") and fname.endswith(".class"):
            shutil.copyfile(os.path.join(APP_DIR, fname), os.path.join(WORK_DIR, fname))


def launch_jviewer_in_novnc(host: str, user: str, password: str) -> dict:
    global JVIEWER_PROC
    ensure_novnc_stack()
    with open(JVIEWER_LOG_PATH, "w", encoding="utf-8") as f:
        f.write(f"=== Starting Chromeless ModernJViewerBridge for {host} ===\n")

    jnlp_info = fetch_megarac_jnlp(host, user, password)
    if not jnlp_info["ok"]:
        append_jviewer_log("ERROR: " + jnlp_info.get("stderr", "Authentication failed"))
        return {
            "ok": False,
            "stderr": jnlp_info.get("stderr", "Auth failed"),
            "log": open(JVIEWER_LOG_PATH, "r", encoding="utf-8").read(),
        }

    base_url = jnlp_info["base_url"]
    cookie = jnlp_info["session_cookie"]
    stoken = jnlp_info["stoken"]
    xml = jnlp_info["jnlp_xml"]

    jnlp_path = os.path.join(WORK_DIR, "jviewer.jnlp")
    with open(jnlp_path, "w", encoding="utf-8") as f:
        f.write(xml)

    href_jars = re.findall(r'href=["\']([^"\']+\.jar)["\']', xml, flags=re.IGNORECASE)
    jar_candidates = []
    for h in href_jars + ["release/JViewer.jar", "release/JViewer-SOC.jar", "release/Linux_x86_64.jar", "release/Linux_x86_32.jar"]:
        if h not in jar_candidates:
            jar_candidates.append(h)

    downloaded_jars = []
    for rel_jar in jar_candidates:
        fname = os.path.basename(rel_jar)
        dest = os.path.join(WORK_DIR, fname)
        clean_rel = rel_jar.lstrip("/")
        urls_to_try = [rel_jar] if rel_jar.startswith("http") else [f"{base_url}/Java/{clean_rel}", f"{base_url}/{clean_rel}"]

        for u in urls_to_try:
            data = curl_fetch_bytes(u, cookie_header=f"SessionCookie={cookie}", timeout=12)
            if len(data) > 200 and data[:2] == b"PK":
                with open(dest, "wb") as f:
                    f.write(data)
                downloaded_jars.append(fname)
                append_jviewer_log(f"Downloaded {fname} ({len(data)} bytes)")
                if "linux" in fname.lower() or "native" in fname.lower():
                    try:
                        with zipfile.ZipFile(dest, "r") as zf:
                            zf.extractall(WORK_DIR)
                        append_jviewer_log(f"Extracted native .so libraries from {fname}")
                    except Exception as ex:
                        append_jviewer_log(f"Warning extracting {fname}: {ex}")
                break

    if "JViewer.jar" not in downloaded_jars:
        msg = f"ERROR: Could not download JViewer.jar from {base_url}/Java/release/JViewer.jar"
        append_jviewer_log(msg)
        return {
            "ok": False,
            "stderr": msg,
            "log": open(JVIEWER_LOG_PATH, "r", encoding="utf-8").read(),
        }

    ensure_bridge_compiled()

    jnlp_args = [a.strip() for a in re.findall(r"<argument>([^<]+)</argument>", xml) if a.strip()]
    if not jnlp_args:
        jnlp_args = [host, "7578", stoken, cookie]

    if JVIEWER_PROC and JVIEWER_PROC.poll() is None:
        JVIEWER_PROC.terminate()
        time.sleep(0.4)

    env = os.environ.copy()
    if os.path.exists("/tmp/.X11-unix/X99"):
        env["DISPLAY"] = ":99"
    env["LD_LIBRARY_PATH"] = WORK_DIR

    main_cls = "ModernJViewerBridge" if os.path.exists(os.path.join(WORK_DIR, "ModernJViewerBridge.class")) else "com.ami.kvm.jviewer.JViewer"
    java_cmd = [
        "java",
        f"-Djava.library.path={WORK_DIR}",
        "-cp",
        f"{WORK_DIR}:{WORK_DIR}/*:/usr/share/icedtea-web/netx.jar",
        main_cls,
    ] + jnlp_args

    append_jviewer_log(f"Launching {main_cls}: " + " ".join(java_cmd))
    log_handle = open(JVIEWER_LOG_PATH, "a", encoding="utf-8")
    JVIEWER_PROC = subprocess.Popen(java_cmd, env=env, cwd=WORK_DIR, stdout=log_handle, stderr=subprocess.STDOUT)
    time.sleep(1.5)

    if JVIEWER_PROC.poll() is not None:
        pos_cmd = [
            "java",
            f"-Djava.library.path={WORK_DIR}",
            "-cp",
            f"{WORK_DIR}:{WORK_DIR}/*:/usr/share/icedtea-web/netx.jar",
            main_cls,
            host,
            "7578",
            stoken,
            cookie,
        ]
        append_jviewer_log(f"Trying positional args with {main_cls}: " + " ".join(pos_cmd))
        JVIEWER_PROC = subprocess.Popen(pos_cmd, env=env, cwd=WORK_DIR, stdout=log_handle, stderr=subprocess.STDOUT)
        time.sleep(1.5)

    return {
        "ok": True,
        "log": open(JVIEWER_LOG_PATH, "r", encoding="utf-8", errors="ignore").read(),
    }


def query_jviewer_bridge(path: str) -> dict:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:9099{path}", timeout=2.5) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except Exception as e:
        return {"ok": False, "stderr": str(e)}


def build_ipmitool_base_cmd(host: str, user: str, password: str, cipher: str) -> list:
    if cipher == "lan_v15":
        return ["ipmitool", "-I", "lan", "-H", host, "-U", user, "-P", password]
    elif cipher == "lanplus_c3":
        return ["ipmitool", "-I", "lanplus", "-C", "3", "-H", host, "-U", user, "-P", password]
    elif cipher == "lanplus_c17":
        return ["ipmitool", "-I", "lanplus", "-C", "17", "-H", host, "-U", user, "-P", password]
    elif cipher == "lanplus_c0":
        return ["ipmitool", "-I", "lanplus", "-C", "0", "-H", host, "-U", user, "-P", password]
    return ["ipmitool", "-I", "lanplus", "-H", host, "-U", user, "-P", password]


def run_ipmitool_with_fallback(host: str, user: str, password: str, cipher: str, args: list, timeout: int = 10) -> dict:
    profiles = (
        ["lanplus_default", "lanplus_c3", "lanplus_c17", "lan_v15", "lanplus_c0"]
        if cipher == "auto"
        else [cipher]
    )
    errors = []
    for prof in profiles:
        cmd = build_ipmitool_base_cmd(host, user, password, prof) + [str(a) for a in args]
        safe_cmd = [c if idx != cmd.index("-P") + 1 else "***" for idx, c in enumerate(cmd)]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if proc.returncode == 0:
                return {
                    "ok": True,
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                    "used_interface": prof,
                    "cmd": " ".join(shlex.quote(c) for c in safe_cmd),
                }
            errors.append(f"[{prof}] {(proc.stderr or proc.stdout).strip()}")
        except subprocess.TimeoutExpired:
            errors.append(f"[{prof}] Timed out after {timeout}s talking to {host}:623")
        except Exception as exc:
            errors.append(f"[{prof}] {exc}")

    return {
        "ok": False,
        "stdout": "",
        "stderr": "\n".join(errors),
        "diagnostics": "\n".join(errors),
    }


def probe_bmc_ports(host: str) -> str:
    report = []
    for port, name in [(80, "HTTP Web UI"), (443, "HTTPS Web UI"), (7578, "JViewer iKVM Video"), (5120, "Virtual CD Media")]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.5)
        try:
            s.connect((host, port))
            report.append(f"[OPEN]   TCP {host}:{port:<5} ({name})")
        except Exception as e:
            report.append(f"[CLOSED] TCP {host}:{port:<5} ({name}) -> {e}")
        finally:
            s.close()

    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.settimeout(2.5)
    rmcp_ping = bytes([0x06, 0x00, 0xFF, 0x06, 0x00, 0x00, 0x11, 0xBE, 0x80, 0x00, 0x00, 0x00])
    try:
        udp.sendto(rmcp_ping, (host, 623))
        data, _ = udp.recvfrom(128)
        report.append(f"[OPEN]   UDP {host}:623   (IPMI RMCP Pong: {len(data)} bytes)")
    except Exception as e:
        report.append(f"[NO PONG] UDP {host}:623  (IPMI RMCP Ping -> {e})")
    finally:
        udp.close()

    return "\n".join(report)


class MegaRACBridgeHandler(SimpleHTTPRequestHandler):
    def _set_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._set_cors()
        self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length) or b"{}")

        action = payload.get("action", "ipmitool")
        host = payload.get("host", "").strip()
        user = payload.get("user", "admin").strip()
        password = payload.get("password", "admin")
        cipher = payload.get("cipher", "auto")

        if action == "network_probe":
            result = {"ok": True, "probe_report": probe_bmc_ports(host)}
        elif action == "sync_all":
            mc = run_ipmitool_with_fallback(host, user, password, cipher, ["mc", "info"])
            if not mc["ok"]:
                probe = probe_bmc_ports(host)
                result = {
                    "ok": False,
                    "stderr": mc["stderr"],
                    "diagnostics": f"--- IPMI Connection Attempts ---\n{mc['stderr']}\n\n--- Network Port Probe ({host}) ---\n{probe}",
                }
            else:
                used = mc["used_interface"]
                ch = run_ipmitool_with_fallback(host, user, password, used, ["chassis", "status"])
                sdr = run_ipmitool_with_fallback(host, user, password, used, ["sdr", "elist", "full"], timeout=20)
                boot = run_ipmitool_with_fallback(host, user, password, used, ["chassis", "bootparam", "get", "5"])
                sel = run_ipmitool_with_fallback(host, user, password, used, ["sel", "elist"])
                result = {
                    "ok": True,
                    "used_interface": used,
                    "mc_info": mc["stdout"],
                    "chassis_status": ch["stdout"],
                    "sdr_raw": sdr["stdout"],
                    "boot_param": boot["stdout"],
                    "sel_raw": sel["stdout"],
                    "cmd": mc["cmd"],
                    "stdout": mc["stdout"],
                }
        elif action == "fetch_jnlp":
            result = fetch_megarac_jnlp(host, user, password)
        elif action == "launch_jviewer_novnc":
            result = launch_jviewer_in_novnc(host, user, password)
        elif action == "jviewer_state":
            result = query_jviewer_bridge("/state")
        elif action == "jviewer_click":
            target_id = urllib.parse.quote(payload.get("id", ""))
            result = query_jviewer_bridge(f"/click?id={target_id}")
        elif action == "jviewer_chrome":
            val = "true" if payload.get("chromeless", True) else "false"
            result = query_jviewer_bridge(f"/chrome?chromeless={val}")
        elif action == "jviewer_logs":
            txt = ""
            if os.path.exists(JVIEWER_LOG_PATH):
                txt = open(JVIEWER_LOG_PATH, "r", encoding="utf-8", errors="ignore").read()
            result = {"ok": True, "log": txt or "(No JViewer stdout/stderr logged yet)"}
        elif action == "xdotool_key":
            key = payload.get("key", "Return")
            env = os.environ.copy()
            env["DISPLAY"] = ":99"
            if shutil.which("xdotool"):
                subprocess.run(["xdotool", "key", key], env=env)
            result = {"ok": True}
        elif action == "xdotool_type":
            text = payload.get("text", "")
            env = os.environ.copy()
            env["DISPLAY"] = ":99"
            if shutil.which("xdotool"):
                subprocess.run(["xdotool", "type", "--delay", "25", text], env=env)
            result = {"ok": True}
        else:
            args = payload.get("args", ["mc", "info"])
            result = run_ipmitool_with_fallback(host, user, password, cipher, args)

        self.send_response(200)
        self._set_cors()
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description="MegaRAC Commander Unified Bridge")
    parser.add_argument("--bind", default="0.0.0.0", help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Bind port (default: 8765)")
    args = parser.parse_args()

    os.chdir(APP_DIR)
    try:
        steps = ensure_novnc_stack()
        for s in steps:
            print(f"[NOVNC INIT] {s}", flush=True)
    except Exception as e:
        print(f"[NOVNC WARN] {e}", flush=True)

    server = ThreadingHTTPServer((args.bind, args.port), MegaRACBridgeHandler)
    print(f"MegaRAC Commander Unified Bridge listening on http://{args.bind}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
