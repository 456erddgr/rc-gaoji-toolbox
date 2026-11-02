# -*- coding: utf-8 -*-
"""虚拟手柄：遥控器 →(adb reverse tcp:9999)→ 本机 → ViGEm(虚拟 X360 手柄)

协议（来自 RC2-EdgeTX/docs/next-ai-pc-pad-principles.md）：
  每行一个 JSON：{"ax":[lx,ly,rx,ry,p1,p2]} 或 {"ax":[...],"seq":1}
  值域 0..2047，中点 1024。轴序与 EdgeTX 一致：ax[0]=LV ax[1]=LH ax[2]=RV ax[3]=RH
  输出映射：左摇杆 x=ax[3] y=-ax[2]；右摇杆 x=ax[0] y=-ax[1]
"""
import json
import socket
import threading
import time

_IMPORT_ERR = ""
try:
    import vgamepad as vg
except Exception as _e:  # pragma: no cover
    vg = None
    _IMPORT_ERR = "%s: %s" % (type(_e).__name__, _e)

import engine as E

_LOCK = threading.Lock()
_ST = {
    "srv": None, "sock": None, "conn": None, "thread": None, "tick": None,
    "gp": None, "running": False, "err": "", "port": 9999,
    "axes": [1024] * 6, "prev": None, "t_last": 0.0, "t_prev": 0.0,
    "hz": 0.0, "count": 0, "peer": "", "reverse_ok": False, "axis_names": [],
}

# 预测参数（照搬 padcore 的口径，宁可保守）
CAP_MS = 45.0
OVER = 1.25


def available():
    return {"vgamepad": vg is not None, "err": ("" if vg is not None else "没装 vgamepad 库")}


def _n(v):
    v = max(0.0, min(2047.0, float(v)))
    return (v - 1024.0) / 1023.0


def _clamp(x):
    return max(-1.0, min(1.0, x))


def _open_pad():
    if vg is None:
        return None, "没装 vgamepad"
    try:
        gp = vg.VX360Gamepad()
        gp.reset()
        gp.update()
        return gp, ""
    except Exception as e:
        return None, "创建虚拟手柄失败: %s（ViGEmBus 驱动没装？）" % e


def _apply(gp, ax):
    # 左摇杆 <- ax[3] / -ax[2]；右摇杆 <- ax[0] / -ax[1]
    lx = _clamp(_n(ax[3]))
    ly = _clamp(-_n(ax[2]))
    rx = _clamp(_n(ax[0]))
    ry = _clamp(-_n(ax[1]))
    gp.left_joystick_float(x_value_float=lx, y_value_float=ly)
    gp.right_joystick_float(x_value_float=rx, y_value_float=ry)
    gp.update()


def _predict(ax, age_ms):
    """三点外推（速度 + 加速度），带过冲钳制；超时就衰减"""
    st = _ST
    prev = st["prev"]
    if prev is None:
        return ax
    dt = max(1.0, st["t_last"] - st["t_prev"])
    out = []
    for i in range(6):
        cur = ax[i]
        pr = prev[i]
        v = (cur - pr) / dt           # 每毫秒
        ahead = min(age_ms, CAP_MS)
        step = v * ahead
        cap = abs(step) * (OVER - 1.0) + 6.0
        step = max(-cap, min(cap, step))
        out.append(cur + step)
    return out


def _feed(raw_axes, t):
    st = _ST
    with _LOCK:
        st["prev"] = list(st["axes"]) if st["t_last"] else None
        st["t_prev"] = st["t_last"]
        st["t_last"] = t
        st["axes"] = list(raw_axes)
        st["count"] += 1
        if st["count"] % 10 == 0 and st["t_prev"]:
            dt = (t - st["t_prev"]) or 1.0
            st["hz"] = round(1000.0 / (dt / 10.0), 2)


def _parse_line(line):
    line = line.strip()
    if not line:
        return None
    try:
        j = json.loads(line)
    except Exception:
        # 兜底：ax:1,2,3,4,5,6
        if line.startswith("ax:"):
            try:
                return [int(x) for x in line[3:].split(",")[:6]]
            except Exception:
                return None
        return None
    ax = j.get("ax") if isinstance(j, dict) else None
    if isinstance(ax, list) and len(ax) >= 4:
        ax = list(ax[:6]) + [1024] * (6 - len(ax[:6]))
        return [int(x) for x in ax]
    return None


def _reader(conn):
    st = _ST
    buf = b""
    conn.settimeout(0.5)
    while st["running"]:
        try:
            data = conn.recv(4096)
        except socket.timeout:
            continue
        except Exception:
            break
        if not data:
            break
        buf += data
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            try:
                txt = line.decode("utf-8", "replace")
            except Exception:
                continue
            ax = _parse_line(txt)
            if ax:
                _feed(ax, time.time() * 1000.0)
    try:
        conn.close()
    except Exception:
        pass
    st["conn"] = None
    st["peer"] = ""


def _accept_loop(srv):
    st = _ST
    while st["running"]:
        try:
            conn, addr = srv.accept()
        except Exception:
            break
        st["conn"] = conn
        st["peer"] = "%s:%d" % (addr[0], addr[1])
        threading.Thread(target=_reader, args=(conn,), daemon=True).start()


def _tick_loop():
    st = _ST
    gp = st["gp"]
    while st["running"]:
        t = time.time() * 1000.0
        ax = list(st["axes"])
        age = max(0.0, t - st["t_last"]) if st["t_last"] else 0.0
        out = _predict(ax, age)
        if age > CAP_MS * 3:
            out = [1024] * 6  # 断流回中
        try:
            _apply(gp, out)
        except Exception as e:
            st["err"] = "推送失败: %s" % e
            break
        time.sleep(0.008)  # ~125Hz


def start(port=9999, reverse=True):
    st = _ST
    if st["running"]:
        return {"ok": True, "msg": "虚拟手柄已经在跑", "port": st["port"]}
    gp, err = _open_pad()
    if gp is None:
        return {"ok": False, "err": err}
    ser = E.device_serial()
    rev = False
    if reverse and ser:
        r = E._run([E.ADB, "reverse", "tcp:%d" % int(port), "tcp:%d" % int(port)], timeout=10)
        rev = bool(r.ok and "tcp:%d" % int(port) in (r.out or ""))
        if not rev:
            r2 = E._run([E.ADB, "reverse", "tcp:%d" % int(port), "tcp:%d" % int(port)], timeout=10)
            rev = bool(r2.ok)
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", int(port)))
        srv.listen(4)
        srv.settimeout(0.5)
    except Exception as e:
        try:
            gp.reset()
            gp.update()
        except Exception:
            pass
        return {"ok": False, "err": "监听 %d 端口失败: %s" % (int(port), e)}
    st.update({"srv": srv, "gp": gp, "running": True, "err": "", "port": int(port),
               "reverse_ok": rev, "count": 0, "hz": 0.0, "t_last": 0.0, "t_prev": 0.0,
               "axes": [1024] * 6, "prev": None})
    st["thread"] = threading.Thread(target=_accept_loop, args=(srv,), daemon=True)
    st["thread"].start()
    st["tick"] = threading.Thread(target=_tick_loop, daemon=True)
    st["tick"].start()
    return {"ok": True, "port": int(port), "reverse": rev,
            "msg": "已开始收流（%s）。遥控器上需要把摇杆流发到 127.0.0.1:%d" %
                   ("adb reverse 已建" if rev else "没建 reverse（无线调试时手动填 IP）", int(port))}


def stop():
    st = _ST
    st["running"] = False
    for k in ("sock", "conn"):
        try:
            if st.get(k):
                st[k].close()
        except Exception:
            pass
    try:
        if st["srv"]:
            st["srv"].close()
    except Exception:
        pass
    try:
        if st["gp"]:
            st["gp"].reset()
            st["gp"].update()
    except Exception:
        pass
    st.update({"srv": None, "conn": None, "gp": None, "peer": "", "hz": 0.0})
    if E.device_serial():
        try:
            E._run([E.ADB, "reverse", "--remove", "tcp:%d" % int(st["port"])], timeout=8)
        except Exception:
            pass
    return {"ok": True, "msg": "已停止"}


def state():
    st = _ST
    return {"ok": True, "running": bool(st["running"]), "port": st["port"],
            "peer": st["peer"], "hz": st["hz"], "count": st["count"],
            "axes": list(st["axes"]), "reverse": st["reverse_ok"],
            "vgamepad": vg is not None, "err": st["err"]}
