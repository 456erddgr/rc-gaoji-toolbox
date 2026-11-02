# -*- coding: utf-8 -*-
"""投屏后端：scrcpy 真视频流 + app_process 可用性探测

DJI RC2 的 SELinux 拦掉了 app_process，scrcpy 的服务端起不来；
RC Pro / RC Pro 2 / RC Plus / RC1 这些没被拦，可以直接跑 scrcpy。
"""
import os
import subprocess
import threading
import time

import engine as E

_LOCK = threading.Lock()
_PROC = None
_PROBE = {"ok": None, "msg": "", "at": 0.0}


def scrcpy_ready():
    return os.path.isfile(E.SCRCPY)


def probe_app_process(force=False):
    """返回 {ok: True/False/None, msg}；None 表示无法判断（没设备）"""
    global _PROBE
    with _LOCK:
        if (not force) and _PROBE["ok"] is not None and (time.time() - _PROBE["at"] < 300):
            return dict(_PROBE)
    if not E.device_serial():
        r = {"ok": None, "msg": "没检测到设备"}
    else:
        res = E._run([E.ADB, "shell",
                      "app_process /system/bin --nice-name=rc2probe 2>&1"], timeout=15)
        txt = ((res.out or "") + " " + (res.err or "")).strip()
        low = txt.lower()
        if ("classnotfound" in low) or ("usage: app_process" in low) or ("error:" in low):
            r = {"ok": True, "msg": "app_process 可用（可以走 scrcpy 真视频流）"}
        elif not txt:
            r = {"ok": False, "msg": "app_process 无输出 —— 被 SELinux 拦了，只能用截图推流"}
        else:
            r = {"ok": True, "msg": txt[:160]}
    with _LOCK:
        _PROBE.update(r)
        _PROBE["at"] = time.time()
    return r


def _running():
    return _PROC is not None and _PROC.poll() is None


def start(max_size=1920, max_fps=60, bitrate="8M", serial=None,
          no_audio=True, record=False, extra=None):
    global _PROC
    if not scrcpy_ready():
        return {"ok": False, "err": "没找到 scrcpy.exe：%s" % E.SCRCPY}
    ser = serial or E.device_serial()
    if not ser:
        return {"ok": False, "err": "没检测到设备。请用 USB 连接遥控器。"}
    with _LOCK:
        if _running():
            return {"ok": True, "msg": "scrcpy 已经在跑了", "pid": _PROC.pid}
        args = [E.SCRCPY, "--serial", ser,
                "--max-size=%d" % int(max_size),
                "--max-fps=%d" % int(max_fps),
                "--window-title=RC 搞机工具箱 · 投屏",
                "--stay-awake"]
        if bitrate:
            args.append("--video-bit-rate=%s" % bitrate)
        if no_audio:
            args.append("--no-audio")
        if record:
            out = E.ensure_out()
            args.append("--record=%s" % os.path.join(out, "record_%s.mp4" % time.strftime("%Y%m%d_%H%M%S")))
        if extra:
            args.extend([str(x) for x in extra])
        try:
            _PROC = subprocess.Popen(
                args, cwd=E.SCRCPY_DIR, creationflags=E.NO_WINDOW,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            return {"ok": False, "err": "启动 scrcpy 失败: %s" % e}
    time.sleep(1.2)
    if _PROC.poll() is not None:
        return {"ok": False, "err": "scrcpy 启动后立刻退出了（多半是 app_process 被拦，换截图推流）"}
    return {"ok": True, "pid": _PROC.pid, "msg": "scrcpy 已启动（独立窗口）"}


def stop():
    global _PROC
    with _LOCK:
        if _PROC is not None and _PROC.poll() is None:
            try:
                _PROC.terminate()
            except Exception:
                pass
    subprocess.run(["taskkill", "/F", "/IM", "scrcpy.exe"],
                   capture_output=True, creationflags=E.NO_WINDOW)
    _PROC = None
    return {"ok": True, "msg": "已停止"}


def status():
    return {"ok": True, "running": _running(),
            "pid": (_PROC.pid if _running() else None),
            "scrcpy": scrcpy_ready(),
            "app_process": probe_app_process()}
