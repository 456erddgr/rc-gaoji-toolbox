# -*- coding: utf-8 -*-
"""
RC 搞机工具箱 v6.0 - 启动器（自绘无边框窗口 + 内嵌 Edge 渲染）

结构：
  1) 本地 HTTP 服务提供 UI 与 /api/* 接口
  2) tkinter overrideredirect 无边框窗口当宿主（圆角由 Win32 region 裁）
  3) Edge --app 起窗口后 SetParent 塞进宿主当子窗口
  4) 子窗口向上偏移 chrome 高度，把 Chromium 自绘的标题栏顶出可见区域
  5) 移动 / 缩放 / 最大化 / 全屏 / 关闭 全部在 tk 主线程通过 Win32 处理

关键点（血泪教训）：
  · 这台机器是 2560x1600 @150%，tkinter 的 geometry() 坐标空间与 Win32 物理像素
    不一致，混用会算出「窗口跑到屏幕外 / 比例不对」。统一用 SetWindowPos + GetClientRect
    的物理像素，尺寸以 GetClientRect 为准。
  · Chromium 把标题栏画在客户区里（WS_CAPTION 位本来就是 0），只能靠向上偏移藏起来。
  · 所有窗口几何修改必须在 tk 主线程（root.after 循环）里做。

作者：软糖布丁
"""
import ctypes
import ctypes.wintypes as wt
import io
import json
import os
import subprocess
import sys
import threading
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "app"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def res_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return _HERE


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _HERE


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
dwmapi = ctypes.windll.dwmapi

GWL_STYLE = -16
WS_CHILD = 0x40000000
WS_VISIBLE = 0x10000000
WS_POPUP = 0x80000000
WS_CLIPCHILDREN = 0x02000000

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2

WIN_W, WIN_H = 1600, 1000
CHROME_H = 39          # Chromium 自绘标题栏高度（启动后会实测覆盖）
CORNER_R = 18
MIN_W, MIN_H = 960, 620

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass

PT = wt.POINT
RECT = wt.RECT


_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

def log(msg):
    try:
        with open(os.path.join(app_dir(), "run.log"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


def make_round(hwnd, w, h, r):
    try:
        rgn = gdi32.CreateRoundRectRgn(0, 0, int(w) + 1, int(h) + 1,
                                       int(r) * 2, int(r) * 2)
        user32.SetWindowRgn(hwnd, rgn, True)
    except Exception:
        pass


def set_border_color(hwnd, color=0x000E0908):
    """把 Win11 的窗口边框染成和界面底色一致，避免出现 1px 浅色亮线。

    DWMWA_BORDER_COLOR = 34；值按 0x00BBGGRR 排列。
    实测 0xFFFFFFFE（官方 NONE）在这台机器不生效，必须给具体颜色。
    """
    try:
        dwmapi.DwmSetWindowAttribute(hwnd, 34,
                                     ctypes.byref(ctypes.c_uint(color)), 4)
    except Exception:
        pass

def clear_round(hwnd):
    try:
        user32.SetWindowRgn(hwnd, 0, True)
    except Exception:
        pass


def screen_rect():
    return (0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1))


def work_rect():
    r = RECT()
    try:
        user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)
        if r.right > r.left and r.bottom > r.top:
            return (r.left, r.top, r.right - r.left, r.bottom - r.top)
    except Exception:
        pass
    return screen_rect()


def get_client(hwnd):
    r = RECT()
    try:
        user32.GetClientRect(hwnd, ctypes.byref(r))
        return r.right - r.left, r.bottom - r.top
    except Exception:
        return 0, 0


def measure_inset(edge_hwnd, edge_rect):
    """测量 Chromium 在窗口内部自己画的那圈边框：
    返回 (左, 上, 右, 下)，即网页渲染区相对 Edge 窗口的偏移"""
    rend = []

    def cb(h, lp):
        cls = ctypes.create_unicode_buffer(128)
        user32.GetClassNameW(h, cls, 128)
        if cls.value == "Chrome_RenderWidgetHostHWND":
            rend.append(h)
        return True

    user32.EnumChildWindows(
        edge_hwnd,
        ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(cb), 0)
    if not rend:
        return (0, CHROME_H, 0, 8)
    r2 = RECT()
    user32.GetWindowRect(rend[0], ctypes.byref(r2))
    il = r2.left - edge_rect.left
    it = r2.top - edge_rect.top
    ir = edge_rect.right - r2.right
    ib = edge_rect.bottom - r2.bottom
    # 夹到合理范围，防异常值
    il = il if 0 <= il < 80 else 0
    it = it if 0 <= it < 160 else CHROME_H
    ir = ir if 0 <= ir < 80 else 0
    ib = ib if 0 <= ib < 80 else 0
    return (il, it, ir, ib)


def _edge_hwnds(pid):
    out = []

    def cb(h, lp):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            cls = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(h, cls, 128)
            if cls.value == "Chrome_WidgetWin_1":
                out.append(h)
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)(cb), 0)
    return out


def find_edge():
    cands = [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ]
    for c in cands:
        if os.path.isfile(c):
            return c
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                           r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe")
        p = winreg.QueryValue(k, None)
        if p and os.path.isfile(p):
            return p
    except Exception:
        pass
    return None


def seed_profile(prof_dir):
    """预置 Edge profile：关掉同步 / 登录 / 首次运行引导弹窗"""
    try:
        os.makedirs(prof_dir, exist_ok=True)
    except Exception:
        pass
    try:
        fr = os.path.join(prof_dir, "First Run")
        if not os.path.isfile(fr):
            open(fr, "wb").close()
    except Exception:
        pass
    ddir = os.path.join(prof_dir, "Default")
    try:
        os.makedirs(ddir, exist_ok=True)
    except Exception:
        pass
    pref = os.path.join(ddir, "Preferences")
    if not os.path.isfile(pref):
        try:
            with open(pref, "w", encoding="utf-8") as f:
                json.dump({
                    "signin": {"allowed": False, "allowed_on_next_startup": False},
                    "sync": {"requested": False},
                    "browser": {"has_seen_welcome_page": True,
                                "check_default_browser": False},
                    "profile": {"exit_type": "Normal"},
                }, f)
        except Exception:
            pass


_PS_KILL = r"""
$prof = $args[0]
$list = Get-CimInstance Win32_Process -Filter "Name='msedge.exe'" |
        Where-Object { $_.CommandLine -and $_.CommandLine.Contains($prof) }
foreach ($p in $list) { try { Stop-Process -Id $p.ProcessId -Force -ErrorAction Stop } catch {} }
Write-Output ("killed=" + $list.Count)
"""


def kill_profile_edges(prof):
    """Edge 会复用同 profile 的已有进程（新进程秒退），导致宿主窗口被立即销毁。
    启动前先把占用该 profile 的 msedge 进程全部结束掉。"""
    try:
        import tempfile
        fd, path = tempfile.mkstemp(suffix=".ps1")
        os.close(fd)
        with io.open(path, "w", encoding="utf-8-sig", newline=NL) as f:
            f.write(_PS_KILL)
        r = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", path, prof],
            capture_output=True, timeout=25,
            creationflags=0x08000000)
        out = (r.stdout or b"").decode("utf-8", "replace").strip()
        log("kill_profile_edges -> %s" % (out or "no-output"))
        try:
            os.remove(path)
        except Exception:
            pass
        return out
    except Exception as e:
        log("kill_profile_edges failed: %s" % e)
        return ""


def find_app_window(pid=None, title_kw="搞机工具箱"):
    """先按 pid 找 Chrome_WidgetWin_1；找不到就按标题兜底认领。"""
    if pid:
        for h in _edge_hwnds(pid):
            return h
    found = []

    def _cb(h, _lp):
        try:
            if not user32.IsWindowVisible(h):
                return True
            cls = ctypes.create_unicode_buffer(128)
            user32.GetClassNameW(h, cls, 128)
            if "Chrome_WidgetWin" not in cls.value:
                return True
            n = user32.GetWindowTextLengthW(h)
            if n <= 0:
                return True
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(h, buf, n + 1)
            if title_kw and title_kw in buf.value:
                found.append(h)
                return False
            return True
        except Exception:
            return True

    user32.EnumWindows(_WNDENUMPROC(_cb), 0)
    return found[0] if found else None


def main():
    import tkinter as tk
    import server as S
    import main_api as A

    apidir = app_dir()
    S.UI_BASE = os.path.join(res_dir(), "ui")
    api = A.Api()
    port = S.find_port()
    S.serve(api, port)
    # cache-bust：Edge 会把 index.html 和 app.js 都缓存住。
    # 版本号取 ui/ 下所有文件的最新 mtime —— 只盯 index.html 的话，
    # 改了 app.js/style.css 版本号不变，浏览器还是跑旧代码。
    _v = 0
    try:
        _uidir = os.path.join(res_dir(), "ui")
        for _root, _dirs, _files in os.walk(_uidir):
            for _f in _files:
                try:
                    _v = max(_v, int(os.path.getmtime(os.path.join(_root, _f))))
                except Exception:
                    pass
    except Exception:
        _v = 0
    url = "http://127.0.0.1:%d/?v=%d" % (port, _v)
    log("server on %d" % port)

    edge = find_edge()
    if not edge:
        import tkinter.messagebox as mb
        r0 = tk.Tk()
        r0.withdraw()
        mb.showerror("启动失败", "未找到 Microsoft Edge，无法显示界面。")
        return

    prof = os.path.join(apidir, ".data", "edge")
    seed_profile(prof)

    scr = work_rect()
    ww = min(WIN_W, scr[2] - 80)
    wh = min(WIN_H, scr[3] - 80)
    x = scr[0] + max(20, (scr[2] - ww) // 2)
    y = scr[1] + max(20, (scr[3] - wh) // 2)

    root = tk.Tk()
    root.overrideredirect(True)
    root.configure(bg="#08090e")
    root.update_idletasks()
    hw = int(root.frame(), 16) if isinstance(root.frame(), str) else int(root.frame())
    user32.SetWindowPos(hw, 0, int(x), int(y), int(ww), int(wh),
                        SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED)
    root.update_idletasks()
    make_round(hw, ww, wh, CORNER_R)
    set_border_color(hw)
    try:
        v = ctypes.c_int(2)
        dwmapi.DwmSetWindowAttribute(hw, 33, ctypes.byref(v), 4)
        dm = ctypes.c_int(1)
        dwmapi.DwmSetWindowAttribute(hw, 20, ctypes.byref(dm), 4)
    except Exception:
        pass
    log("host hwnd=%s at %d,%d size=%dx%d" % (hw, x, y, ww, wh))

    args = [
        edge,
        "--app=" + url,
        "--window-size=%d,%d" % (ww, wh + CHROME_H + 8),
        "--window-position=%d,%d" % (x - 9000, y),
        "--user-data-dir=" + prof,
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-features=msEdgeSidebarV2,msImplicitSignin,msEdgeIdentityBubble,"
        "msEdgeSync,msEdgeSyncPromo,msEdgeSigninPromo,msEdgeFirstRunExperience,"
        "msEdgeWelcomePage,msEdgeAccountBubble",
        "--disable-sync",
        "--disable-extensions",
        "--disable-background-networking",
    ]
    proc = subprocess.Popen(args)

    child = {"hwnd": None, "chrome": CHROME_H,
             "inset": (0, CHROME_H, 0, 8), "probe": 0, "last_inset": None}
    state = {"mode": "normal", "normal": (x, y, ww, wh),
             "drag": None, "resize": None}

    def apply_child():
        chh = child["hwnd"]
        if not chh:
            return
        cw, ch = get_client(hw)
        if cw <= 0 or ch <= 0:
            return
        # Chromium 会在自己的窗口里画一圈「内边距」（左边框 + 标题栏 + 右侧 + 底部），
        # 不裁掉就会在顶部/左侧漏出白边。这里按实测内边距反向偏移并把窗口撑大，
        # 让网页内容刚好铺满宿主客户区。
        il, it, ir, ib = child["inset"]
        try:
            user32.MoveWindow(chh, -il, -it,
                              cw + il + ir, ch + it + ib, True)
        except Exception:
            pass

    def embed():
        deadline = time.time() + 45
        while time.time() < deadline and not child["hwnd"]:
            h0 = find_app_window(proc.pid)
            for h in ([h0] if h0 else []):
                try:
                    r = RECT()
                    c = RECT()
                    user32.GetWindowRect(h, ctypes.byref(r))
                    user32.GetClientRect(h, ctypes.byref(c))
                    diff = (r.bottom - r.top) - (c.bottom - c.top)
                    if 0 < diff < 160:
                        child["chrome"] = diff
                    st = user32.GetWindowLongW(h, GWL_STYLE)
                    user32.SetWindowLongW(
                        h, GWL_STYLE,
                        (st & ~WS_POPUP) | WS_CHILD | WS_VISIBLE | WS_CLIPCHILDREN)
                    user32.SetParent(h, hw)
                    child["hwnd"] = h
                    child["inset"] = measure_inset(h, r)
                    log("embedded hwnd=%s inset=%s" % (h, child["inset"]))
                    break
                except Exception as e:
                    log("embed err %s" % e)
            time.sleep(0.2)
        if child["hwnd"]:
            apply_child()

    threading.Thread(target=embed, daemon=True).start()

    # ---------- 主线程几何管理 ----------
    def win_rect():
        r = RECT()
        user32.GetWindowRect(hw, ctypes.byref(r))
        return (r.left, r.top, r.right - r.left, r.bottom - r.top)

    def move(x2, y2, w2, h2, rounded=True):
        # 夹紧：别让窗口跑到屏幕外（用户抱怨过「找不到程序」）
        sw3, sh3 = screen_rect()[2], screen_rect()[3]
        w2 = max(MIN_W, min(int(w2), sw3))
        h2 = max(MIN_H, min(int(h2), sh3))
        x2 = max(-w2 + 160, min(int(x2), sw3 - 160))
        y2 = max(0, min(int(y2), sh3 - 80))
        user32.SetWindowPos(hw, 0, int(x2), int(y2), int(w2), int(h2),
                            SWP_NOZORDER | SWP_NOACTIVATE)
        if rounded:
            make_round(hw, w2, h2, CORNER_R)
        else:
            clear_round(hw)
        set_border_color(hw)
        root.update_idletasks()
        apply_child()

    def tick():
        if state["drag"] is not None:
            p = PT()
            user32.GetCursorPos(ctypes.byref(p))
            sx, sy, wx0, wy0 = state["drag"]
            r = win_rect()
            move(wx0 + (p.x - sx), wy0 + (p.y - sy), r[2], r[3],
                 state["mode"] == "normal")
        elif state["resize"] is not None:
            p = PT()
            user32.GetCursorPos(ctypes.byref(p))
            edge_s, sx, sy, wx0, wy0, w0, h0 = state["resize"]
            dx = p.x - sx
            dy = p.y - sy
            nx, ny, nw, nh = wx0, wy0, w0, h0
            if "e" in edge_s:
                nw = max(MIN_W, w0 + dx)
            if "w" in edge_s:
                nw = max(MIN_W, w0 - dx)
                nx = wx0 + (w0 - nw)
            if "s" in edge_s:
                nh = max(MIN_H, h0 + dy)
            if "n" in edge_s:
                nh = max(MIN_H, h0 - dy)
                ny = wy0 + (h0 - nh)
            move(nx, ny, nw, nh, state["mode"] == "normal")
        else:
            # 前 ~10 秒反复测量内边距：Chromium 的渲染窗口比 Edge 窗口晚创建，
            # 一开始量不到，等它出现后再校正一次位置
            if child["hwnd"] and child["probe"] < 40:
                child["probe"] += 1
                if child["probe"] % 8 == 0:
                    r = RECT()
                    user32.GetWindowRect(child["hwnd"], ctypes.byref(r))
                    ins = measure_inset(child["hwnd"], r)
                    if ins[1] > 0:
                        if ins == child["last_inset"]:
                            # 连续两次一致，认定稳定，停止探测（避免每帧抖动）
                            if ins != child["inset"]:
                                child["inset"] = ins
                                log("inset fixed -> %s" % (ins,))
                            child["probe"] = 40
                        else:
                            child["last_inset"] = ins
            apply_child()
        root.after(16, tick)

    def win_drag_start():
        p = PT()
        user32.GetCursorPos(ctypes.byref(p))
        r = win_rect()
        state["drag"] = (p.x, p.y, r[0], r[1])
        return {"ok": True}

    def win_drag_end():
        state["drag"] = None
        return {"ok": True}

    def win_resize_start(edge_name="se"):
        p = PT()
        user32.GetCursorPos(ctypes.byref(p))
        r = win_rect()
        state["resize"] = (str(edge_name or "se"), p.x, p.y, r[0], r[1], r[2], r[3])
        return {"ok": True}

    def win_resize_end():
        state["resize"] = None
        return {"ok": True}

    def do_maximize():
        if state["mode"] == "normal":
            state["normal"] = win_rect()
            state["mode"] = "max"
            wx2, wy2, ww2, wh2 = work_rect()
            move(wx2, wy2, ww2, wh2, False)
        elif state["mode"] == "max":
            state["mode"] = "normal"
            nx, ny, nw, nh = state["normal"]
            move(nx, ny, nw, nh, True)
        else:
            state["mode"] = "max"
            wx2, wy2, ww2, wh2 = work_rect()
            move(wx2, wy2, ww2, wh2, False)
        return {"ok": True, "mode": state["mode"]}

    def do_fullscreen():
        if state["mode"] != "full":
            state["normal"] = win_rect()
            state["mode"] = "full"
            sx2, sy2, sw2, sh2 = screen_rect()
            move(sx2, sy2, sw2, sh2, False)
            try:
                user32.SetWindowPos(hw, HWND_TOPMOST, 0, 0, 0, 0,
                                    SWP_NOSIZE | SWP_NOMOVE)
            except Exception:
                pass
        else:
            state["mode"] = "normal"
            try:
                user32.SetWindowPos(hw, HWND_NOTOPMOST, 0, 0, 0, 0,
                                    SWP_NOSIZE | SWP_NOMOVE)
            except Exception:
                pass
            nx, ny, nw, nh = state["normal"]
            move(nx, ny, nw, nh, True)
        return {"ok": True, "mode": state["mode"]}

    def do_minimize():
        root.withdraw()
        root.after(320, lambda: (root.deiconify(), root.lift(),
                                 user32.SetForegroundWindow(hw)))
        return {"ok": True}

    def do_quit():
        root.after(0, lambda: (proc.terminate(), root.destroy()))  # noqa
        return {"ok": True}

    api.win_drag_start = win_drag_start
    api.win_drag_end = win_drag_end
    api.win_resize_start = win_resize_start
    api.win_resize_end = win_resize_end
    api.win_maximize = do_maximize
    api.win_fullscreen = do_fullscreen
    api.win_minimize = do_minimize
    api.quit_app = do_quit

    def watch():
        """不绑 Edge 进程（Edge 会把窗口交给老进程后自己秒退）。
        改为盯子窗口是否还活着；若一直没认领到窗口，30 秒后退出。"""
        t0 = time.time()
        while True:
            time.sleep(0.5)
            ch = child["hwnd"]
            if ch:
                if not user32.IsWindow(ch):
                    log("child window gone, quit")
                    try:
                        root.after(0, root.destroy)
                    except Exception:
                        pass
                    return
                continue
            if time.time() - t0 > 30:
                log("embed timeout, quit")
                try:
                    root.after(0, root.destroy)
                except Exception:
                    pass
                return

    threading.Thread(target=watch, daemon=True).start()
    root.after(16, tick)
    root.after(300, lambda: user32.SetForegroundWindow(hw))
    root.mainloop()
    try:
        proc.terminate()
    except Exception:
        pass


if __name__ == "__main__":
    main()
