# -*- coding: utf-8 -*-
"""RC 搞机工具箱 —— 原生安装程序（不依赖任何浏览器）

设计要点
- 纯 tkinter + Win32，不启动 Edge / WebView，任何 Windows 都能跑
- overrideredirect 无边框 + CreateRoundRectRgn 圆角 + DWMWA_BORDER_COLOR
  取底色，彻底没有白边
- 安装目标用 ASCII 文件名 RCGaojiToolbox.exe，避免中文路径在快捷方式/命令行
  里被编码破坏
- 快捷方式用「写 UTF-8 BOM 的 .ps1 + powershell -File」创建，不内联中文参数
"""
import ctypes
import ctypes.wintypes as wt
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import filedialog

APP_NAME = "RC 搞机工具箱"
APP_VER = "6.2"
AUTHOR = "软糖布丁"
EXE_NAME = "RCGaojiToolbox.exe"          # 安装后的 ASCII 文件名
UNINST_NAME = "卸载 RC 搞机工具箱.bat"

BG = "#0b0b0d"
CARD = "#151519"
CARD2 = "#1c1c21"
LINE = "#2a2a32"
TXT = "#f5f5f7"
TXT2 = "#a1a1a6"
TXT3 = "#6e6e73"
ACCENT = "#0a84ff"
GREEN = "#30d158"
RED = "#ff453a"

DISCLAIMER = """【第一部分 · 这是什么】

RC 搞机工具箱是给 DJI RC2 遥控器（型号 rc331 / Android 11 / SD 30，
高通 lahaina 平台）使用的第三方工具，作者：软糖布丁。

它不是大疆（DJI）官方软件，也未获得大疆任何形式的授权、许可或认可。
本软件与 DJI 公司没有任何关联，不是官方售后工具。

【第二部分 · 它具体会改什么】

本软件通过 adb 与 root 权限直接读写系统底层参数，涉及范围包括：

1. CPU：三个簇的上限频率、调度策略、温控开关
2. GPU：频率档位（315 / 450 / 550 / 608 / 700 / 812 MHz）
3. 虚拟内存：zram 大小、磁盘 swap 文件、swappiness、extra_free_kbytes、
   drop_caches
4. 系统属性与 Magisk 模块：setprop 写入、模块启用/停用
5. 分区镜像：boot_a / boot_b / dji_apk / vbmeta_a 的读取与刷写
6. Bootloader：仅查询状态与解锁，本工具不提供回锁功能
7. 开机动画与背光：生成/替换开机动画，背光仅做只读检测

【第三部分 · 可能导致的后果】

1. CPU / GPU 频率设置过高 → 设备过热、卡死、自动重启、电池加速老化
2. 刷写分区出错 → 系统无法启动（俗称变砖），只能用官方工具或送修恢复
3. 误操作 pwmchip0（屏幕背光）→ 直接黑屏。
   急救：sh /data/adb/modules/rc2_allscripts/scripts/fix_screen.sh
4. 关闭 zram 或写入超大 swap → 内存耗尽，系统卡死
5. 解锁 Bootloader → 官方保修失效；回锁会让遥控器直接变砖
   （本工具已永久移除该功能）
6. 分区写错 → 数据永久丢失，无法恢复

【第四部分 · 责任声明】

本软件为个人制作的自用工具，按「现状」提供，不附带任何明示或暗示的担保。
使用本软件所造成的任何直接或间接损失（包括但不限于设备损坏、数据丢失、
保修失效、无法开机），作者不承担任何责任。

请务必在操作前自行备份重要数据，并确认你了解自己在做什么。

【第五部分 · 绝对不要做的事】

1. 不要 unexport / 乱写 /sys/class/pwm/pwmchip0 —— 那是屏幕背光，会黑屏
2. 不要在关闭 zram 之后不重新开启就重启
3. 不要用 dd 一次写入超过 1GB 的 swap（本机总内存只有 1.7GB）
4. 不要在非 dji_apk 的数据分区上瞎刷
5. 不要把 swappiness 设成超过 100（内核上限）
6. 不要把 extra_free_kbytes 设成超过 32MB（会直接 OOM）
7. 不要试图回锁 Bootloader

【第六部分 · 使用建议】

- 第一次使用先看「总览」，确认设备已识别、Root 状态正常
- 改频率前先记下原值，改坏了能改回来
- 刷分区前一定先「备份」，备份文件保存在程序目录的 out 文件夹
- 遥控器电量低于 30% 时不要刷分区

【第七部分 · 同意】

点击「同意并继续」表示你已完整阅读上述内容，理解并接受所有风险，
并确认这是你自己的设备，或已获得设备所有者的明确授权。

如果你不同意，请点击「退出」关闭本程序。
"""


# ---------------------------------------------------------------- 工具函数
def res_dir():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def payload_exe():
    return os.path.join(res_dir(), "payload", EXE_NAME)


def default_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return os.path.join(base, "RC2DeviceToolbox")


def start_dpi():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
try:
    dwmapi = ctypes.windll.dwmapi
except Exception:
    dwmapi = None

GWL_EXSTYLE = -20
WS_EX_APPWINDOW = 0x00040000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020


def hwnd_of(win):
    try:
        f = win.frame()
        return int(f, 16) if isinstance(f, str) else int(f)
    except Exception:
        return 0


def make_round(win, w, h, r=16):
    hw = hwnd_of(win)
    if not hw:
        return
    try:
        rgn = gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, r * 2, r * 2)
        user32.SetWindowRgn(hw, rgn, True)
    except Exception:
        pass
    try:
        if dwmapi:
            v = ctypes.c_int(2)
            dwmapi.DwmSetWindowAttribute(hw, 33, ctypes.byref(v), 4)
            c = ctypes.c_int(0x000E0908)
            dwmapi.DwmSetWindowAttribute(hw, 34, ctypes.byref(c), 4)
    except Exception:
        pass


def rr(cv, x1, y1, x2, y2, r, **kw):
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2,
        x1 + r, y2, x1, y2, x1, y2 - r,
        x1, y1 + r, x1, y1,
    ]
    return cv.create_polygon(pts, smooth=True, **kw)


class RBtn(tk.Canvas):
    """圆角按钮（Canvas 自绘，避免 tkinter 直角）"""

    def __init__(self, master, text, cmd, width=132, height=40, bg=CARD,
                 fg=TXT, fill=ACCENT, kind="solid", font=("Microsoft YaHei UI", 10)):
        tk.Canvas.__init__(self, master, width=width, height=height,
                           bg=bg, highlightthickness=0, bd=0)
        self._bw, self._bh = width, height
        self._cmd = cmd
        self._fill = fill
        self._kind = kind
        self._fg = fg
        self._txt = text
        self._font = font
        self._hover = False
        self._draw()
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self.bind("<Button-1>", self._click)

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _click(self, _e):
        if callable(self._cmd):
            self._cmd()

    def set_text(self, t):
        self._txt = t
        self._draw()

    def _draw(self):
        self.delete("all")
        x1, y1 = 1, 1
        x2, y2 = self._bw - 1, self._bh - 1
        if self._kind == "solid":
            col = self._fill
            if self._hover:
                col = "#2f9bff" if self._fill == ACCENT else self._fill
            rr(self, x1, y1, x2, y2, 10, fill=col, outline="")
            fg = "#ffffff"
        elif self._kind == "ghost":
            rr(self, x1, y1, x2, y2, 10,
               fill=CARD2 if self._hover else CARD, outline=LINE)
            fg = self._fg
        else:  # danger
            rr(self, x1, y1, x2, y2, 10,
               fill="#3a1a1c" if self._hover else "#2a1416", outline="#5a2226")
            fg = RED
        self.create_text(self._bw // 2, self._bh // 2, text=self._txt,
                         fill=fg, font=self._font)


class App:
    W, H = 980, 700

    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.configure(bg=BG)
        self.root.title(APP_NAME + " 安装程序")
        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)
        x = max(0, (sw - self.W) // 2)
        y = max(0, (sh - self.H) // 2 - 30)
        self.root.geometry("%dx%d+%d+%d" % (self.W, self.H, x, y))
        self.root.update_idletasks()
        try:
            hw = hwnd_of(self.root)
            st = user32.GetWindowLongW(hw, GWL_EXSTYLE)
            user32.SetWindowLongW(hw, GWL_EXSTYLE, st | WS_EX_APPWINDOW)
            user32.SetWindowPos(hw, 0, 0, 0, 0, 0,
                                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED)
        except Exception:
            pass
        self.root.update_idletasks()
        make_round(self.root, self.W, self.H, 18)
        self.step = 0
        self.target = tk.StringVar(value=default_dir())
        self.launch_after = tk.BooleanVar(value=True)
        self._drag = None
        self._build()
        self.root.bind("<ButtonPress-1>", self._press)
        self.root.bind("<B1-Motion>", self._motion)
        self.root.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))

    # ---------------- 结构 ----------------
    def _build(self):
        # 顶部标题条（可拖动）
        top = tk.Frame(self.root, bg=BG, height=56)
        top.pack(fill="x")
        top.pack_propagate(False)
        dot = tk.Canvas(top, width=26, height=26, bg=BG, highlightthickness=0)
        dot.pack(side="left", padx=(18, 10))
        dot.create_oval(3, 3, 23, 23, fill=ACCENT, outline="")
        dot.create_text(13, 13, text="R", fill="#fff",
                        font=("Segoe UI", 12, "bold"))
        tk.Label(top, text="RC 搞机工具箱 · 安装程序", bg=BG, fg=TXT,
                 font=("Microsoft YaHei UI", 10)).pack(side="left")
        cls = tk.Canvas(top, width=34, height=34, bg=BG, highlightthickness=0,
                        cursor="hand2")
        cls.pack(side="right", padx=(0, 12))
        cls.create_text(17, 17, text="✕", fill=TXT3, font=("Segoe UI", 13))
        cls.bind("<Button-1>", lambda e: self.root.destroy())
        cls.bind("<Enter>", lambda e: cls.itemconfig(1, fill=RED))
        cls.bind("<Leave>", lambda e: cls.itemconfig(1, fill=TXT3))

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 14))

        # 左：品牌区
        left = tk.Canvas(body, width=250, bg=CARD, highlightthickness=0)
        left.pack(side="left", fill="y")
        self._paint_brand(left)

        # 右：内容区
        self.right = tk.Frame(body, bg=BG)
        self.right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        self._page_terms()

    def _paint_brand(self, cv):
        W = 250
        rr(cv, 0, 0, W, 760, 14, fill=CARD, outline=LINE)
        # logo 方块
        cv.create_rectangle(28, 34, 108, 114, fill=ACCENT, outline="")
        cv.create_text(68, 74, text="RC2", fill="#ffffff",
                       font=("Segoe UI", 22, "bold"))
        cv.create_text(28, 140, text=APP_NAME, fill=TXT, anchor="w",
                       font=("Microsoft YaHei UI", 13, "bold"))
        cv.create_text(28, 168, text="v" + APP_VER, fill=TXT2, anchor="w",
                       font=("Segoe UI", 10))
        cv.create_text(28, 194, text="作者：" + AUTHOR, fill=TXT3, anchor="w",
                       font=("Microsoft YaHei UI", 9))
        # 步骤
        steps = ["阅读条款", "选择位置", "安装", "完成"]
        y = 250
        for i, s in enumerate(steps):
            on = i == self.step
            done = i < self.step
            c = ACCENT if on else (GREEN if done else "#3a3a42")
            cv.create_oval(28, y - 6, 40, y + 6, fill=c, outline="")
            if done:
                cv.create_text(34, y, text="✓", fill="#fff", font=("Segoe UI", 7, "bold"))
            elif on:
                cv.create_text(34, y, text=str(i + 1), fill="#fff",
                               font=("Segoe UI", 7, "bold"))
            cv.create_text(52, y, text=s, fill=TXT if on else TXT3, anchor="w",
                           font=("Microsoft YaHei UI", 10, "bold" if on else "normal"))
            if i < 3:
                cv.create_line(34, y + 8, 34, y + 34, fill="#2e2e36", width=2)
            y += 42
        cv.create_text(28, 706, text="本程序不收集任何数据", fill=TXT3, anchor="w",
                       font=("Microsoft YaHei UI", 8))

    def _clear_right(self):
        for w in self.right.winfo_children():
            w.destroy()
        # 重画左侧步骤
        for w in self.root.pack_slaves()[1].winfo_children():
            if isinstance(w, tk.Canvas) and w.winfo_width() <= 260:
                w.delete("all")
                self._paint_brand(w)
                break

    def _title(self, text, sub=""):
        tk.Label(self.right, text=text, bg=BG, fg=TXT, anchor="w",
                 font=("Microsoft YaHei UI", 17, "bold")).pack(fill="x", pady=(6, 2))
        if sub:
            tk.Label(self.right, text=sub, bg=BG, fg=TXT3, anchor="w",
                     font=("Microsoft YaHei UI", 9)).pack(fill="x", pady=(0, 10))
        else:
            tk.Frame(self.right, bg=BG, height=10).pack(fill="x")

    def _bottom(self, buttons):
        bar = tk.Frame(self.right, bg=BG)
        bar.pack(side="bottom", fill="x", pady=(12, 0))
        for text, cmd, kind, fill in reversed(buttons):
            b = RBtn(bar, text, cmd, width=124, height=40, bg=BG,
                     fill=fill, kind=kind)
            b.pack(side="right", padx=(8, 0))

    # ---------------- 第 1 步：条款 ----------------
    def _page_terms(self):
        self.step = 0
        self._clear_right()
        self._title("使用前必读 · 免责声明",
                    "本软件会修改系统底层参数，可能损坏设备。请完整阅读后继续。")

        self._bottom([
            ("退出", self.root.destroy, "ghost", TXT2),
            ("同意并继续", self._page_path, "solid", ACCENT),
        ])

        wrap = tk.Frame(self.right, bg=CARD, highlightbackground=LINE,
                        highlightthickness=1)
        wrap.pack(fill="both", expand=True)
        bar = tk.Scrollbar(wrap, orient="vertical")
        txt = tk.Text(wrap, bg=CARD, fg=TXT2, bd=0, relief="flat",
                      wrap="word", yscrollcommand=bar.set, padx=16, pady=12,
                      insertwidth=0, font=("Microsoft YaHei UI", 9),
                      selectbackground="#2b2b33", cursor="arrow")
        bar.config(command=txt.yview)
        bar.pack(side="right", fill="y")
        txt.pack(side="left", fill="both", expand=True)
        txt.insert("1.0", DISCLAIMER)
        txt.config(state="disabled")
        txt.bind("<MouseWheel>", lambda e: txt.yview_scroll(int(-e.delta / 120), "units"))

    # ---------------- 第 2 步：选目录 ----------------
    def _page_path(self):
        self.step = 1
        self._clear_right()
        self._title("选择安装位置", "程序会被安装到这里，并自动创建桌面与开始菜单快捷方式。")
        card = tk.Frame(self.right, bg=CARD, highlightbackground=LINE,
                        highlightthickness=1)
        card.pack(fill="x", pady=(4, 6))
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=16)
        tk.Label(inner, text="安装目录", bg=CARD, fg=TXT2, anchor="w",
                 font=("Microsoft YaHei UI", 9)).pack(fill="x")
        row = tk.Frame(inner, bg=CARD)
        row.pack(fill="x", pady=(6, 0))
        ent = tk.Entry(row, textvariable=self.target, bg=CARD2, fg=TXT,
                       bd=0, relief="flat", insertbackground=TXT,
                       font=("Segoe UI", 10))
        ent.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        RBtn(row, "浏览…", self._browse, width=88, height=36, bg=CARD,
             kind="ghost").pack(side="right")

        info = tk.Frame(self.right, bg=BG)
        info.pack(fill="x", pady=(10, 0))
        for line in [
            "· 安装后的主程序文件名：%s" % EXE_NAME,
            "· 总大小约 30MB，不写注册表，卸载只需删除目录",
            "· 需要已安装 Microsoft Edge（调用系统浏览器渲染界面）",
        ]:
            tk.Label(info, text=line, bg=BG, fg=TXT3, anchor="w",
                     font=("Microsoft YaHei UI", 9)).pack(fill="x")

        self._bottom([
            ("返回", self._page_terms, "ghost", TXT2),
            ("开始安装", self._page_install, "solid", ACCENT),
        ])

    def _browse(self):
        d = filedialog.askdirectory(title="选择安装目录",
                                    initialdir=self.target.get())
        if d:
            self.target.set(os.path.join(d, "RC2DeviceToolbox")
                            if os.path.basename(d.rstrip("\\/")).lower() != "rc2devicetoolbox"
                            else d)

    # ---------------- 第 3 步：安装 ----------------
    def _page_install(self):
        self.step = 2
        self._clear_right()
        self._title("正在安装", "请稍候，不要关闭窗口。")
        card = tk.Frame(self.right, bg=CARD, highlightbackground=LINE,
                        highlightthickness=1)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=18)
        self.lbl = tk.Label(inner, text="准备中…", bg=CARD, fg=TXT2, anchor="w",
                            font=("Microsoft YaHei UI", 9))
        self.lbl.pack(fill="x")
        self.pb = tk.Canvas(inner, height=8, bg=CARD, highlightthickness=0)
        self.pb.pack(fill="x", pady=(10, 0))
        self._pb(0)

        self._bottom([("请稍候…", lambda: None, "ghost", TXT3)])
        self.out = tk.Text(self.right, height=9, bg=CARD2, fg=TXT3, bd=0,
                           relief="flat", padx=12, pady=10,
                           font=("Consolas", 9), insertwidth=0)
        self.out.pack(fill="both", expand=True, pady=(12, 0))
        self.out.config(state="disabled")
        threading.Thread(target=self._do_install, daemon=True).start()

    def _pb(self, frac):
        w = max(1, self.pb.winfo_width() or 640)
        self.pb.delete("all")
        rr(self.pb, 0, 0, w, 8, 4, fill="#232330", outline="")
        if frac > 0:
            rr(self.pb, 0, 0, max(10, int(w * frac)), 8, 4, fill=ACCENT, outline="")

    # tkinter 控件只能在主线程碰：工作线程统一用 after(0, ...) 回主线程
    def _ui(self, fn, *a):
        try:
            self.root.after(0, lambda: fn(*a))
        except Exception:
            pass

    def _say_now(self, text):
        try:
            self.out.config(state="normal")
            self.out.insert("end", text + "\n")
            self.out.see("end")
            self.out.config(state="disabled")
        except Exception:
            pass

    def _status_now(self, text, frac=None):
        try:
            self.lbl.config(text=text)
            if frac is not None:
                self._pb(frac)
        except Exception:
            pass

    def _say(self, text):
        self._ui(self._say_now, text)

    def _status(self, text, frac=None):
        self._ui(self._status_now, text, frac)

    def _do_install(self):
        try:
            dst_dir = self.target.get().strip() or default_dir()
            self._status("创建目录…", 0.08)
            self._say("目标目录: " + dst_dir)
            os.makedirs(dst_dir, exist_ok=True)

            src = payload_exe()
            if not os.path.isfile(src):
                self._say("!! 找不到内置主程序 payload: " + src)
                self._status("安装失败：安装包不完整", 0)
                return
            self._say("主程序大小: %d 字节" % os.path.getsize(src))

            self._status("复制主程序…", 0.35)
            dst_exe = os.path.join(dst_dir, EXE_NAME)
            shutil.copyfile(src, dst_exe)
            self._say("已复制 -> " + dst_exe)

            self._status("写卸载脚本…", 0.55)
            bat = os.path.join(dst_dir, "卸载 RC 搞机工具箱.bat")
            with io.open(bat, "w", encoding="gbk", newline="\r\n") as f:
                f.write("@echo off\r\n")
                f.write("chcp 65001 >nul\r\n")
                f.write("echo 正在卸载 RC 搞机工具箱…\r\n")
                f.write('del /f /q "%%USERPROFILE%%\\Desktop\\RC 搞机工具箱.lnk" 2>nul\r\n')
                f.write('del /f /q "%%APPDATA%%\\Microsoft\\Windows\\Start Menu\\Programs\\RC 搞机工具箱.lnk" 2>nul\r\n')
                f.write('echo 目录：%s\r\n' % dst_dir)
                f.write('echo 请手动删除该目录。\r\n')
                f.write("pause\r\n")
            self._say("已写卸载脚本")

            self._status("创建快捷方式…", 0.75)
            ok1 = self._shortcut(dst_exe, "desktop")
            ok2 = self._shortcut(dst_exe, "startmenu")
            self._say("桌面快捷方式: %s" % ("成功" if ok1 else "失败"))
            self._say("开始菜单快捷方式: %s" % ("成功" if ok2 else "失败"))

            self._status("完成", 1.0)
            self.link = dst_exe
            self.root.after(0, self._page_done)
        except Exception as e:
            self._say("!! 安装失败: %s" % e)
            self._status("安装失败", 0)

    def _shortcut(self, target_exe, where):
        """用 .ps1 文件（UTF-8 BOM）+ powershell -File 创建快捷方式，
        避免 -Command 内联中文被编码破坏。"""
        ps = r"""
$ErrorActionPreference = 'Stop'
$target = $args[0]
$where  = $args[1]
$W = New-Object -ComObject WScript.Shell
if ($where -eq 'desktop') {
  $dir = [Environment]::GetFolderPath('Desktop')
} else {
  $dir = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'
}
$lnk = Join-Path $dir 'RC 搞机工具箱.lnk'
$s = $W.CreateShortcut($lnk)
$s.TargetPath = $target
$s.WorkingDirectory = Split-Path -Parent $target
$s.IconLocation = "$target,0"
$s.Description = 'RC 搞机工具箱'
$s.Save()
if (Test-Path $lnk) { Write-Output 'OK' } else { Write-Output 'FAIL' }
"""
        try:
            fd, path = tempfile.mkstemp(suffix=".ps1")
            os.close(fd)
            with io.open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
                f.write(ps)
            r = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                 "-File", path, target_exe, where],
                capture_output=True, timeout=40, creationflags=0x08000000)
            out = (r.stdout or b"").decode("utf-8", "replace").strip()
            try:
                os.remove(path)
            except Exception:
                pass
            return "OK" in out
        except Exception as e:
            self._say("快捷方式异常: %s" % e)
            return False

    # ---------------- 第 4 步：完成 ----------------
    def _page_done(self):
        self.step = 3
        self._clear_right()
        self._title("安装完成", "程序已准备好，可以立即启动。")
        card = tk.Frame(self.right, bg=CARD, highlightbackground=LINE,
                        highlightthickness=1)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="x", padx=16, pady=18)
        ok = tk.Canvas(inner, width=44, height=44, bg=CARD, highlightthickness=0)
        ok.pack(side="left", padx=(0, 14))
        ok.create_oval(2, 2, 42, 42, fill=GREEN, outline="")
        ok.create_text(22, 22, text="✓", fill="#fff", font=("Segoe UI", 17, "bold"))
        box = tk.Frame(inner, bg=CARD)
        box.pack(side="left", fill="x", expand=True)
        tk.Label(box, text="全部完成", bg=CARD, fg=TXT, anchor="w",
                 font=("Microsoft YaHei UI", 12, "bold")).pack(fill="x")
        tk.Label(box, text=getattr(self, "link", ""), bg=CARD, fg=TXT3,
                 anchor="w", font=("Segoe UI", 9)).pack(fill="x", pady=(4, 0))

        cb = tk.Checkbutton(self.right, text="  立即启动 RC 搞机工具箱",
                            variable=self.launch_after, bg=BG, fg=TXT2,
                            activebackground=BG, activeforeground=TXT,
                            selectcolor=CARD2, bd=0, highlightthickness=0,
                            anchor="w", font=("Microsoft YaHei UI", 9))
        cb.pack(fill="x", pady=(14, 0))

        tips = tk.Frame(self.right, bg=BG)
        tips.pack(fill="x", pady=(14, 0))
        for line in [
            "· 首次启动会弹出免责声明，同意后不再提示",
            "· 需要遥控器用 USB 直连电脑，并已开启 USB 调试",
            "· 卸载：运行安装目录里的「卸载 RC 搞机工具箱.bat」",
        ]:
            tk.Label(tips, text=line, bg=BG, fg=TXT3, anchor="w",
                     font=("Microsoft YaHei UI", 9)).pack(fill="x")

        self._bottom([("完成", self._finish, "solid", ACCENT)])

    def _finish(self):
        if self.launch_after.get():
            try:
                subprocess.Popen([getattr(self, "link", ""), ],
                                 creationflags=0x00000008,
                                 cwd=os.path.dirname(getattr(self, "link", "")))
            except Exception:
                pass
        self.root.destroy()

    # ---------------- 拖动 ----------------
    def _press(self, e):
        self._drag = (e.x_root, e.y_root,
                      self.root.winfo_x(), self.root.winfo_y())

    def _motion(self, e):
        if not self._drag:
            return
        sx, sy, wx, wy = self._drag
        self.root.geometry("+%d+%d" % (wx + (e.x_root - sx), wy + (e.y_root - sy)))

    def run(self):
        self.root.mainloop()


def main():
    # 静默安装：RC搞机工具箱-安装程序.exe --silent [目标目录]
    if "--silent" in sys.argv:
        args = [a for a in sys.argv[1:] if not a.startswith("--")]
        target = args[0] if args else default_dir()
        print("payload:", payload_exe())
        print("payload exists:", os.path.isfile(payload_exe()))
        print("target:", target)
        os.makedirs(target, exist_ok=True)
        dst = os.path.join(target, EXE_NAME)
        shutil.copyfile(payload_exe(), dst)
        print("copied:", dst, os.path.getsize(dst))
        bat = os.path.join(target, "卸载 RC 搞机工具箱.bat")
        with io.open(bat, "w", encoding="gbk", newline="\r\n") as f:
            f.write("@echo off\r\n")
            f.write("chcp 65001 >nul\r\n")
            f.write("echo 正在卸载 RC 搞机工具箱…\r\n")
            f.write('del /f /q "%%USERPROFILE%%\\Desktop\\RC 搞机工具箱.lnk" 2>nul\r\n')
            f.write('del /f /q "%%APPDATA%%\\Microsoft\\Windows\\Start Menu\\Programs\\RC 搞机工具箱.lnk" 2>nul\r\n')
            f.write("echo 请手动删除本目录：%s\r\n" % target)
            f.write("pause\r\n")
        print("uninstall:", bat)
        app = App()
        print("desktop lnk:", app._shortcut(dst, "desktop"))
        print("startmenu lnk:", app._shortcut(dst, "startmenu"))
        try:
            app.root.destroy()
        except Exception:
            pass
        print("SILENT OK")
        return

    App().run()


if __name__ == "__main__":
    main()
