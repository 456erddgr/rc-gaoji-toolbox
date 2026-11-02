# -*- coding: utf-8 -*-
"""RC2 搞机工具箱 —— 核心引擎（作者：软糖布丁）

旧版全部失效的根因：
  1. su 必须用绝对路径 /debug_ramdisk/su —— 设备 PATH 里没有 su，
     旧版所有 su -c 都返回 "su: inaccessible or not found"，
     所以一键 root / 一键备份 / 超频 全部静默失败。
  2. adb 调用统一 UTF-8，避免中文乱码。
  3. 复杂 shell 命令写脚本 push 到设备再执行。
  4. PyInstaller 打包后资源路径用 sys._MEIPASS。
"""

import os
import re
import sys
import subprocess


def _res_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


RES = _res_dir()
APPDIR = _app_dir()
ADB = os.path.join(RES, "tools", "platform-tools", "adb.exe")
FASTBOOT = os.path.join(RES, "tools", "platform-tools", "fastboot.exe")
SCRCPY_DIR = os.path.join(RES, "tools", "scrcpy")
SCRCPY = os.path.join(SCRCPY_DIR, "scrcpy.exe")
OUT = os.path.join(APPDIR, "out")

SU = "/debug_ramdisk/su"
SU_FALLBACKS = [SU, "/data/adb/magisk/su", "/system/bin/su"]

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def ensure_out():
    os.makedirs(OUT, exist_ok=True)
    return OUT


class Result:
    __slots__ = ("ok", "code", "out", "err", "cmd")

    def __init__(self, ok, code, out, err, cmd=""):
        self.ok = ok
        self.code = code
        self.out = out or ""
        self.err = err or ""
        self.cmd = cmd

    def text(self):
        return (self.out + ("\n" + self.err if self.err else "")).strip()

    def __bool__(self):
        return self.ok

    def __repr__(self):
        return "Result(ok=%s code=%s out=%r)" % (self.ok, self.code, self.out[:60])


def _run(args, timeout=60):
    try:
        p = subprocess.run(args, capture_output=True, timeout=timeout,
                           stdin=subprocess.DEVNULL,
                           creationflags=NO_WINDOW)
        out = (p.stdout or b"").decode("utf-8", "replace").strip()
        err = (p.stderr or b"").decode("utf-8", "replace").strip()
        return Result(p.returncode == 0, p.returncode, out, err)
    except subprocess.TimeoutExpired:
        return Result(False, -1, "", "超时(%ss)" % timeout)
    except FileNotFoundError:
        return Result(False, -2, "", "找不到程序: %s" % args[0])
    except Exception as e:
        return Result(False, -3, "", "异常: %s" % e)


def adb(*args, timeout=60):
    return _run([ADB] + [str(a) for a in args], timeout=timeout)


def adb_shell(cmd, timeout=60):
    return adb("shell", cmd, timeout=timeout)


def devices():
    r = adb("devices")
    out = []
    for line in r.out.splitlines():
        line = line.strip()
        if not line or line.startswith("List of"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            out.append((parts[0], parts[1]))
    return out


def device_serial():
    for serial, state in devices():
        if state == "device":
            return serial
    return None


def is_connected():
    return device_serial() is not None


_SU_PATH = None
_SU_STATE = None


def find_su():
    """探测可用的 su 绝对路径（缓存）"""
    global _SU_PATH
    if _SU_PATH:
        return _SU_PATH
    for cand in SU_FALLBACKS:
        r = adb_shell("%s -c id" % cand, timeout=15)
        if "uid=0" in r.out:
            _SU_PATH = cand
            return cand
    return None


def has_root():
    global _SU_STATE
    if _SU_STATE is not None:
        return _SU_STATE
    _SU_STATE = find_su() is not None
    return _SU_STATE


def reset_root_cache():
    global _SU_PATH, _SU_STATE
    _SU_PATH = None
    _SU_STATE = None


def sh(cmd, timeout=60):
    """执行需要 root 的命令（★ 用绝对路径 su，这是旧版最大的坑）"""
    su = find_su()
    if not su:
        return Result(False, -1, "", "无 root 权限（未找到 su）")
    return adb_shell("%s -c '%s'" % (su, cmd.replace("'", "'\''")), timeout=timeout)


def push_script(content, name="rc2task.sh", timeout=120):
    """写脚本（LF 无 BOM）并 push 到设备"""
    ensure_out()
    local = os.path.join(OUT, name)
    with open(local, "w", encoding="utf-8", newline="\n") as f:
        f.write(content.replace("\r\n", "\n"))
    remote = "/data/local/tmp/" + name
    r = adb("push", local, remote, timeout=timeout)
    return remote, r


def run_script(content, name="rc2task.sh", root=True, timeout=180):
    """推送脚本并执行（复杂操作的统一入口）"""
    remote, pr = push_script(content, name, timeout=60)
    if not pr.ok:
        return pr
    if root:
        su = find_su()
        if not su:
            return Result(False, -1, "", "无 root 权限")
        return adb_shell("%s -c 'sh %s'" % (su, remote), timeout=timeout)
    return adb_shell("sh %s" % remote, timeout=timeout)


def _getprop(key):
    return adb_shell("getprop " + key, timeout=15).out.strip()


class DeviceInfo:
    def __init__(self):
        self.serial = device_serial() or "-"
        self.model = _getprop("ro.product.model") or "-"
        self.brand = _getprop("ro.product.brand") or "-"
        self.android = _getprop("ro.build.version.release") or "-"
        self.sdk = _getprop("ro.build.version.sdk") or "-"
        self.abi = _getprop("ro.product.cpu.abi") or "-"
        self.kernel = _getprop("ro.kernel.version") or _kernel()
        self.bootloader = _getprop("ro.bootloader") or "-"
        self.slot = _getprop("ro.boot.slot_suffix") or "-"
        self.zygote_policy = _getprop("persist.dji.zygote_policy") or "-"
        self.root = has_root()

    def __repr__(self):
        return "DeviceInfo(%s)" % self.serial


def _kernel():
    r = adb_shell("cat /proc/version", timeout=15)
    if r.ok:
        m = re.search(r"Linux version (\S+)", r.out)
        if m:
            return m.group(1)
    return "-"


def mem_info():
    r = adb_shell("cat /proc/meminfo", timeout=15)
    d = {}
    for line in r.out.splitlines():
        m = re.match(r"(\w+):\s+(\d+)", line)
        if m:
            d[m.group(1)] = int(m.group(2))
    return {"total": d.get("MemTotal", 0), "available": d.get("MemAvailable", 0),
            "free": d.get("MemFree", 0), "swap_total": d.get("SwapTotal", 0),
            "swap_free": d.get("SwapFree", 0)}


def swaps():
    r = adb_shell("cat /proc/swaps", timeout=15)
    rows = []
    for line in r.out.splitlines():
        if not line.strip() or line.lower().startswith("filename"):
            continue
        p = re.split(r"\s+", line.strip())
        if len(p) >= 5:
            try:
                rows.append({"file": p[0], "type": p[1], "size": int(p[2]),
                             "used": int(p[3]), "prio": int(p[4])})
            except ValueError:
                continue
    return rows


def battery():
    """★ 本机电池节点是 aprimary-bat，不是 battery（旧版写错）"""
    d = {}
    for key, node in (("capacity", "aprimary-bat/capacity"),
                      ("temp", "aprimary-bat/temp"),
                      ("status", "aprimary-bat/status"),
                      ("voltage", "aprimary-bat/voltage_now"),
                      ("current", "aprimary-bat/current_now"),
                      ("health", "aprimary-bat/health")):
        r = adb_shell("cat /sys/class/power_supply/%s 2>/dev/null" % node, timeout=10)
        d[key] = r.out.strip()
    return d


def cpu_temp():
    """★ 本机只有 thermal_zone40/44/16 免 root 可读"""
    for z in ("40", "44", "16", "0", "1"):
        r = adb_shell("cat /sys/class/thermal/thermal_zone%s/temp 2>/dev/null" % z, timeout=10)
        if r.ok and r.out.strip().isdigit():
            v = int(r.out.strip())
            if v > 1000:
                return round(v / 1000.0, 1)
            if v > 0:
                return float(v)
    return None


def cpu_freq():
    r = adb_shell("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null", timeout=10)
    if r.ok and r.out.strip().isdigit():
        return int(r.out.strip()) // 1000
    return None


def cpu_governor():
    r = adb_shell("cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null", timeout=10)
    return r.out.strip() or "-"


def gpu_freq():
    r = adb_shell("cat /sys/class/kgsl/kgsl-3d0/gpuclk 2>/dev/null", timeout=10)
    if r.ok and r.out.strip().isdigit():
        return int(r.out.strip()) // 1000000
    return None


def storage():
    r = adb_shell("df -k /data", timeout=15)
    for line in r.out.splitlines():
        p = re.split(r"\s+", line.strip())
        if len(p) >= 4 and p[0].startswith("/"):
            try:
                return {"total": int(p[1]) * 1024, "used": int(p[2]) * 1024,
                        "free": int(p[3]) * 1024}
            except ValueError:
                continue
    return {"total": 0, "used": 0, "free": 0}


def screen_size():
    r = adb_shell("wm size", timeout=15)
    m = re.search(r"(\d+)x(\d+)", r.out)
    if m:
        return int(m.group(1)), int(m.group(2))
    return 0, 0


def human(n):
    n = float(n or 0)
    for u in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return ("%.1f%s" % (n, u)) if u != "B" else ("%d%s" % (n, u))
        n /= 1024.0
    return "%.1fPB" % n


def kb_human(kb):
    return human((kb or 0) * 1024)
