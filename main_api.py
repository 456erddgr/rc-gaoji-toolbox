# -*- coding: utf-8 -*-
"""RC 搞机工具箱 - JS API 实现"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import tkinter as tk
from tkinter import filedialog

_HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(_HERE, "app"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import engine as E
import features as F
import devices as D
import mirror as M
import gamepad as GP


def app_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return _HERE


AGREE_FILE = os.path.join(app_dir(), ".rc2_agreed")


def _j(obj):
    return json.dumps(obj, ensure_ascii=False)


def _err(msg):
    return _j({"ok": False, "msg": str(msg)})


class Api:
    def __init__(self):
        self.window = None

    # ---- 基础 ----
    def hello(self):
        return _j({"name": "RC 搞机工具箱", "ver": "6.2", "author": "软糖布丁"})

    def has_agreed(self):
        return _j({"agreed": os.path.isfile(AGREE_FILE)})

    def mark_agreed(self):
        try:
            with open(AGREE_FILE, "w", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass
        return _j({"ok": True})

    def quit_app(self):
        if self.window:
            try:
                self.window.destroy()
            except Exception:
                pass
        return _j({"ok": True})

    def win_minimize(self):
        if self.window:
            try:
                self.window.minimize()
            except Exception:
                pass
        return _j({"ok": True})

    def win_maximize(self):
        if self.window:
            try:
                if getattr(self, "_maxed", False):
                    self.window.restore()
                    self._maxed = False
                else:
                    self.window.maximize()
                    self._maxed = True
            except Exception:
                pass
        return _j({"ok": True})

    # ---- 自定义壁纸 ----
    def wallpaper_info(self):
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
            p = os.path.join(app_dir(), ".data", "wallpaper" + ext)
            if os.path.isfile(p):
                return _j({"ok": True, "has": True, "ext": ext,
                           "size": os.path.getsize(p),
                           "url": "/wallpaper?v=" + str(int(os.path.getmtime(p)))})
        return _j({"ok": True, "has": False, "url": ""})

    def pick_wallpaper(self):
        try:
            import tkinter as tk
            from tkinter import filedialog
            r = tk.Tk()
            r.withdraw()
            r.attributes("-topmost", True)
            path = filedialog.askopenfilename(
                title="选择壁纸图片",
                filetypes=[("图片", "*.jpg *.jpeg *.png *.webp *.bmp *.gif"),
                           ("所有文件", "*.*")])
            r.destroy()
        except Exception as e:
            return _err("打开文件选择器失败: " + str(e))
        if not path:
            return _j({"ok": False, "msg": "已取消"})
        try:
            d = os.path.join(app_dir(), ".data")
            os.makedirs(d, exist_ok=True)
            for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
                old = os.path.join(d, "wallpaper" + ext)
                if os.path.isfile(old):
                    try:
                        os.remove(old)
                    except Exception:
                        pass
            ext = os.path.splitext(path)[1].lower()
            if ext not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
                ext = ".jpg"
            dst = os.path.join(d, "wallpaper" + ext)
            shutil.copy2(path, dst)
            return _j({"ok": True, "url": "/wallpaper?v=" + str(int(time.time())),
                       "size": os.path.getsize(dst)})
        except Exception as e:
            return _err("设置壁纸失败: " + str(e))

    def clear_wallpaper(self):
        d = os.path.join(app_dir(), ".data")
        for ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"):
            p = os.path.join(d, "wallpaper" + ext)
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        return _j({"ok": True})

    # ---- 窗口拖动 ----
    def win_drag_start(self):
        return _j({"ok": True})

    def win_drag_end(self):
        return _j({"ok": True})

    # ---- 命令终端：adb / fastboot 自定义命令 ----
    def adb_cmd(self, *parts):
        text = " ".join(str(p) for p in parts).strip()
        if not text:
            return _err("命令为空")
        if text.lower().startswith("adb "):
            text = text[4:].strip()
        try:
            import shlex
            args = shlex.split(text, posix=True)
        except Exception:
            args = text.split()
        if not args:
            return _err("命令为空")
        r = E._run([E.ADB] + args, timeout=240)
        return _j({"ok": r.ok, "code": r.code,
                   "out": r.out, "err": r.err,
                   "cmd": "adb " + " ".join(args)})

    def fb_cmd(self, *parts):
        text = " ".join(str(p) for p in parts).strip()
        if not text:
            return _err("命令为空")
        if text.lower().startswith("fastboot "):
            text = text[9:].strip()
        try:
            import shlex
            args = shlex.split(text, posix=True)
        except Exception:
            args = text.split()
        if not args:
            return _err("命令为空")
        # fastboot 在没有设备时会无限等待，先探一下设备
        probe = E._run([E.FASTBOOT, "devices"], timeout=12)
        if not (probe.out or "").strip():
            return _err("未检测到 Fastboot 设备。请先让遥控器进入 bootloader："
                        "adb reboot bootloader（或关机后按住返回键+电源键）。"
                        "当前 USB 也需直连电脑。")
        r = E._run([E.FASTBOOT] + args, timeout=240)
        return _j({"ok": r.ok, "code": r.code,
                   "out": r.out, "err": r.err,
                   "cmd": "fastboot " + " ".join(args)})

    # ---- 连接模式：自动识别 adb / fastboot ----
    def conn_mode(self):
        """自动识别当前连接模式：adb / fastboot / 无"""
        try:
            # 先查 adb（毫秒级）；adb 没有设备时才去问 fastboot。
            # 反过来会让每次轮询白白等 fastboot 超时 10 秒，顶栏一直是「未连接」。
            adb_serial = E.device_serial()
            if adb_serial:
                return _j({"ok": True, "mode": "adb", "serial": adb_serial,
                           "desc": "ADB 模式（系统已启动）"})
            fb_ok = False
            fb_serial = ""
            try:
                r = E._run([E.FASTBOOT, "devices"], timeout=3)
                lines = [x.strip() for x in (r.out or "").splitlines() if x.strip()]
                if lines:
                    fb_ok = True
                    fb_serial = lines[0].split()[0]
            except Exception:
                pass
            if fb_ok:
                return _j({"ok": True, "mode": "fastboot", "serial": fb_serial,
                           "desc": "Fastboot 模式（可刷分区 / 解 BL / 刷 Root）"})
            return _j({"ok": True, "mode": "none", "serial": "",
                       "desc": "未连接（请插 USB 并开启调试）"})
        except Exception as e:
            return _err(e)

    def scan_device(self):
        """扫描设备：重启 adb 服务 + 列出 adb / fastboot 设备。
        用来解决「插着 USB 但显示未连接」—— adb 服务偶发假死时重起一次就好。"""
        steps = []
        try:
            r1 = E._run([E.ADB, "kill-server"], timeout=8)
            steps.append("kill-server rc=%s" % r1.code)
        except Exception as e:
            steps.append("kill-server 失败: %s" % e)
        try:
            r2 = E._run([E.ADB, "start-server"], timeout=20)
            steps.append("start-server rc=%s" % r2.code)
        except Exception as e:
            steps.append("start-server 失败: %s" % e)
        try:
            r3 = E._run([E.ADB, "devices"], timeout=12)
            lines = [x.strip() for x in (r3.out or "").splitlines()
                     if x.strip() and "List of devices" not in x]
            adb_list = lines
            steps.append("adb devices: %d 条" % len(lines))
        except Exception as e:
            adb_list = []
            steps.append("adb devices 失败: %s" % e)

        serial = ""
        for ln in adb_list:
            parts = ln.split()
            if len(parts) >= 2 and parts[1] == "device":
                serial = parts[0]
                break

        fb_list = []
        if not serial:
            try:
                r4 = E._run([E.FASTBOOT, "devices"], timeout=3)
                fb_list = [x.strip() for x in (r4.out or "").splitlines() if x.strip()]
            except Exception:
                pass

        if serial:
            mode, out_serial = "adb", serial
        elif fb_list:
            mode, out_serial = "fastboot", fb_list[0].split()[0]
        else:
            mode, out_serial = "none", ""
        steps.append("结果: %s %s" % (mode, out_serial))
        return _j({"ok": True, "mode": mode, "serial": out_serial,
                   "adb": adb_list, "fastboot": fb_list,
                   "log": " ｜ ".join(steps)})

    def fastboot_devices(self):
        try:
            r = E._run([E.FASTBOOT, "devices"], timeout=15)
            lines = [x.strip() for x in (r.out or "").splitlines() if x.strip()]
            return _j({"ok": True, "count": len(lines), "devices": lines,
                       "raw": (r.out or "")[:400]})
        except Exception as e:
            return _err(e)

    # ================== 刷 Root（Magisk 正确流程） ==================
    # Magisk 的官方做法就是「App 给 boot.img 打补丁 → 刷回去」。
    # 所以这里分四步：
    #   1) 提取 boot 镜像 → 保存到电脑
    #   2) 用户把文件传到遥控器，用 Magisk App → 安装 → 选择并修补一个文件
    #   3) 把 Magisk 生成的 magisk_patched-xxxxx.img 拉回电脑并选择
    #   4) 校验大小后 dd 刷入 boot 分区
    # 这样不依赖设备端 magiskboot，兼容所有 Magisk 版本。

    def _boot_block(self):
        for name in ("boot_a", "boot", "boot_b"):
            r = E.sh("ls -l /dev/block/bootdevice/by-name/%s 2>/dev/null" % name)
            if r.ok and "->" in (r.out or ""):
                tgt = r.out.split("->")[-1].strip()
                if tgt.startswith("/dev/block"):
                    return name, tgt
        return None, None

    def _backup_dir(self):
        bk = os.path.join(app_dir(), "out", "backup")
        os.makedirs(bk, exist_ok=True)
        return bk

    def _push_file(self, local, remote):
        try:
            r = E._run([E.ADB, "push", local, remote], timeout=420)
            return bool(r.ok)
        except Exception:
            return False

    def _pull_boot_to(self, dst):
        """把当前 boot 分区读出来存到 dst（电脑路径）"""
        name, blk = self._boot_block()
        if not blk:
            return None, "找不到 boot 分区"
        if not E.find_su():
            return None, "需要 root 才能读取 boot 分区"
        cmd = [E.ADB, "exec-out", E.find_su(), "-c",
               "dd if=%s bs=4096 2>/dev/null" % blk]
        try:
            with open(dst, "wb") as f:
                subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE,
                               timeout=420,
                               creationflags=0x08000000 if os.name == "nt" else 0)
        except Exception as e:
            return None, "读取失败：%s" % e
        size = os.path.getsize(dst) if os.path.isfile(dst) else 0
        return (dst if size > 524288 else None), "%d 字节" % size

    def root_env(self):
        dev = E.device_serial()
        if not dev:
            return _j({"ok": False,
                       "msg": "未检测到设备。请用 USB 线把遥控器连到电脑（要能传数据）"})
        su = E.find_su()
        if not su:
            return _j({"ok": False, "msg": "设备上没有可用的 su"})
        name, blk = self._boot_block()
        size = 0
        if blk:
            rs = E.sh("blockdev --getsize64 %s 2>/dev/null" % blk)
            try:
                size = int((rs.out or "0").strip())
            except Exception:
                size = 0
        mv = E.sh("/data/adb/magisk/magisk -v 2>/dev/null")
        bk = self._backup_dir()
        files = []
        for f in sorted(os.listdir(bk), reverse=True):
            if f.endswith(".img"):
                files.append({"name": f,
                              "size": os.path.getsize(os.path.join(bk, f))})
        return _j({"ok": True, "device": dev, "su": su,
                   "magisk_ver": (mv.out or "").strip(),
                   "boot_name": name, "boot_block": blk, "boot_size": size,
                   "backup_dir": bk, "backups": files[:10],
                   "state": self._root_state})

    _root_state = {"patched": "", "backup": ""}

    def root_extract(self):
        """第 1 步：提取当前 boot 镜像（同时留一份备份）"""
        bk = self._backup_dir()
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = (self._boot_block()[0] or "boot")
        dst = os.path.join(bk, "%s_%s.img" % (name, stamp))
        path, info = self._pull_boot_to(dst)
        if not path:
            try:
                os.remove(dst)
            except Exception:
                pass
            return _j({"ok": False, "msg": "提取失败：" + info})
        import hashlib
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1048576), b""):
                h.update(chunk)
        sha = h.hexdigest()
        with open(path + ".sha256", "w", encoding="utf-8") as f:
            f.write(sha)
        self._root_state["backup"] = path
        return _j({"ok": True, "file": path, "size": os.path.getsize(path),
                   "sha256": sha,
                   "next": "把这个文件传到遥控器（或用微信/QQ传），"
                           "打开 Magisk App → 安装 → 选择并修补一个文件 → "
                           "选中它，等它生成 magisk_patched-xxxxx.img"})

    def root_pick_patched(self):
        """第 3 步：选择 Magisk 打好的补丁镜像"""
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            p = filedialog.askopenfilename(
                title="选择 Magisk 打好的镜像（magisk_patched-*.img）",
                filetypes=[("镜像文件", "*.img"), ("所有文件", "*.*")])
            root.destroy()
        except Exception as e:
            return _err(e)
        if not p:
            return _j({"ok": False, "msg": "已取消"})
        size = os.path.getsize(p)
        _, blk = self._boot_block()
        block = 0
        if blk:
            rs = E.sh("blockdev --getsize64 %s 2>/dev/null" % blk)
            try:
                block = int((rs.out or "0").strip())
            except Exception:
                block = 0
        ok = (size == block) if block else True
        if ok:
            self._root_state["patched"] = p
        return _j({"ok": ok, "file": p, "size": size, "block_size": block,
                   "msg": "镜像大小正确，可以刷入" if ok else
                          "镜像大小 %d 与分区 %d 不一致，请确认选的是正确的补丁文件"
                          % (size, block)})

    def root_flash_patched(self, path=""):
        """第 4 步：把补丁镜像刷进 boot 分区"""
        src = path or self._root_state.get("patched")
        if not src or not os.path.isfile(src):
            return _err("还没有选择补丁镜像，请先点「选择补丁镜像」")
        name, blk = self._boot_block()
        if not blk:
            return _err("找不到 boot 分区")
        rsz = E.sh("blockdev --getsize64 %s 2>/dev/null" % blk)
        try:
            block = int((rsz.out or "0").strip())
        except Exception:
            block = 0
        size = os.path.getsize(src)
        if block and size != block:
            return _j({"ok": False,
                       "msg": "镜像大小 %d ≠ 分区大小 %d，已拒绝刷入（防止变砖）"
                              % (size, block)})
        if not self._root_state.get("backup"):
            bk = self._backup_dir()
            stamp = time.strftime("%Y%m%d_%H%M%S")
            dst = os.path.join(bk, "auto_before_flash_%s.img" % stamp)
            got, info = self._pull_boot_to(dst)
            if not got:
                return _j({"ok": False,
                           "msg": "刷入前自动备份失败（" + info + "），已中止"})
            self._root_state["backup"] = got
        tmp = "/data/local/tmp/rc2_patched.img"
        if not self._push_file(src, tmp):
            return _err("推送补丁镜像失败")
        r = E.sh("dd if=%s of=%s bs=4096 2>&1 && sync" % (tmp, blk))
        E.sh("rm -f %s" % tmp)
        if not r.ok:
            return _j({"ok": False, "msg": "刷入失败，可用「恢复备份」救回",
                       "detail": (r.out or "")[-400:]})
        return _j({"ok": True,
                   "msg": "刷入完成，重启后生效（Magisk App 里能看到版本就说明成功）",
                   "backup": self._root_state.get("backup"),
                   "note": "重启卡在开机画面时：按住返回键+电源键进 fastboot，"
                           "再 fastboot flash boot_a 把备份刷回去"})

    def root_restore(self, filename=""):
        bk = self._backup_dir()
        if not filename:
            imgs = sorted([f for f in os.listdir(bk) if f.endswith(".img")],
                          reverse=True)
            if not imgs:
                return _err("备份目录里没有 boot 镜像")
            filename = imgs[0]
        src = os.path.join(bk, filename)
        if not os.path.isfile(src):
            return _err("找不到备份文件：%s" % filename)
        name, blk = self._boot_block()
        if not blk:
            return _err("找不到 boot 分区")
        tmp = "/data/local/tmp/rc2_restore.img"
        if not self._push_file(src, tmp):
            return _err("推送备份失败")
        r = E.sh("dd if=%s of=%s bs=4096 2>&1 && sync && rm -f %s"
                 % (tmp, blk, tmp))
        return _j({"ok": r.ok,
                   "msg": "已恢复备份，重启后生效" if r.ok else "恢复失败",
                   "detail": (r.out or "")[-400:]})

    # ================== 投屏控制（sendevent 真注入） ==================
    # `input tap` 会被 DJI ROM 静默吞掉（返回 0 但屏幕不动），
    # 所以这里直接写 /dev/input/event2，实测有效。
    # 屏幕是竖屏面板 1080x1920 旋转成 1920x1080 显示，
    # 实测映射：tx = y_disp，ty = 1919 - x_disp

    _TOUCH_SCRIPT = """#!/system/bin/sh
D=/dev/input/event2
TAP () {
  sendevent $D 3 57 1
  sendevent $D 3 53 $1
  sendevent $D 3 54 $2
  sendevent $D 3 48 8
  sendevent $D 3 58 60
  sendevent $D 1 330 1
  sendevent $D 0 0 0
  sendevent $D 3 57 -1
  sendevent $D 1 330 0
  sendevent $D 0 0 0
}
SWIPE () {
  X1=$1; Y1=$2; X2=$3; Y2=$4; STEPS=$5
  sendevent $D 3 57 1
  sendevent $D 1 330 1
  i=0
  while [ $i -le $STEPS ]; do
    X=$(( X1 + (X2 - X1) * i / STEPS ))
    Y=$(( Y1 + (Y2 - Y1) * i / STEPS ))
    sendevent $D 3 53 $X
    sendevent $D 3 54 $Y
    sendevent $D 3 48 8
    sendevent $D 3 58 60
    sendevent $D 0 0 0
    i=$(( i + 1 ))
  done
  sendevent $D 3 57 -1
  sendevent $D 1 330 0
  sendevent $D 0 0 0
}
case "$1" in
  tap)   TAP "$2" "$3" ;;
  swipe) SWIPE "$2" "$3" "$4" "$5" "${6:-12}" ;;
esac
"""

    def _ensure_touch(self):
        if self._touch_ready:
            return True
        try:
            p = os.path.join(app_dir(), "out", "rc2_touch.sh")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(self._TOUCH_SCRIPT)
            if not self._push_file(p, "/data/local/tmp/rc2_touch.sh"):
                return False
            self._touch_ready = True
            return True
        except Exception:
            return False

    _touch_ready = False

    def _touch(self, *args):
        if not self._ensure_touch():
            return False
        cmd = "sh /data/local/tmp/rc2_touch.sh " + " ".join(str(x) for x in args)
        r = E.sh(cmd)
        return bool(r.ok)

    def screen_size(self):
        r = E.sh("wm size 2>/dev/null")
        txt = (r.out or "")
        w = h = 0
        if "x" in txt:
            try:
                part = txt.split(":")[-1].strip().split("x")
                w, h = int(part[0]), int(part[1])
            except Exception:
                pass
        return _j({"ok": w > 0, "w": w or 1920, "h": h or 1080})

    def tap_xy(self, x, y):
        """点屏幕（坐标是显示坐标，1920x1080）"""
        try:
            dx, dy = float(x), float(y)
        except Exception:
            return _err("坐标不合法")
        tx = int(round(dy * 1079.0 / 1080.0))
        ty = int(round(1919 - dx * 1919.0 / 1920.0))
        tx = max(0, min(1079, tx))
        ty = max(0, min(1919, ty))
        ok = self._touch("tap", tx, ty)
        return _j({"ok": ok, "x": dx, "y": dy, "tx": tx, "ty": ty})

    def swipe_xy(self, x1, y1, x2, y2, ms="300"):
        """滑动"""
        try:
            dx1, dy1 = float(x1), float(y1)
            dx2, dy2 = float(x2), float(y2)
        except Exception:
            return _err("坐标不合法")
        t1x = int(round(dy1 * 1079.0 / 1080.0))
        t1y = int(round(1919 - dx1 * 1919.0 / 1920.0))
        t2x = int(round(dy2 * 1079.0 / 1080.0))
        t2y = int(round(1919 - dx2 * 1919.0 / 1920.0))
        steps = max(4, min(40, int(int(ms) / 25)))
        ok = self._touch("swipe", t1x, t1y, t2x, t2y, steps)
        return _j({"ok": ok})

    def key_press(self, code):
        """发送按键：home/back/menu/power"""
        m = {"home": "3", "back": "4", "menu": "82", "power": "26",
             "up": "19", "down": "20", "left": "21", "right": "22",
             "enter": "66", "volup": "24", "voldown": "25"}
        k = m.get(str(code).lower())
        if not k:
            return _err("不支持的按键")
        r = E.sh("input keyevent %s" % k)
        return _j({"ok": bool(r.ok), "code": code})

    def fastboot_oem(self, action):
        """解 BL：fastboot oem unlock / flashing unlock

        注意：**故意不实现 lock（回锁）**。
        DJI RC2 带大疆加密校验，回锁会导致遥控器直接变砖，
        只能用官方工具送修恢复。这里硬性拒绝，避免误操作。
        """
        action = (action or "").strip().lower()
        if action in ("lock", "flashing lock", "relock"):
            return _err("本工具已永久移除「回锁 BL」功能："
                        "DJI RC2 带大疆加密校验，回锁会让遥控器直接变砖。"
                        "如确实需要回锁，请使用 DJI 官方工具或送修。")
        try:
            cmd = [E.FASTBOOT]
            if action == "unlock":
                cmd += ["flashing", "unlock"]
            elif action == "getvar":
                cmd += ["getvar", "unlocked"]
            else:
                cmd += ["oem", action]
            r = E._run(cmd, timeout=90)
            return _j({"ok": r.ok, "msg": (r.out + " " + r.err)[:600]})
        except Exception as e:
            return _err(e)

    def fastboot_command(self, *args):
        """执行任意 fastboot 命令（高级）"""
        try:
            r = E._run([E.FASTBOOT] + [str(a) for a in args], timeout=300)
            return _j({"ok": r.ok, "msg": (r.out + " " + r.err)[:800]})
        except Exception as e:
            return _err(e)

    # ---- 轻量状态（供顶栏轮询，快速）----
    def quick_stat(self):
        try:
            r = E.adb_shell(
                "cat /proc/meminfo | grep MemAvailable; "
                "cat /sys/class/thermal/thermal_zone40/temp 2>/dev/null; "
                "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq 2>/dev/null; "
                "getprop ro.product.model", timeout=12)
            avail = temp = freq = 0
            model = "/"
            lines = r.out.splitlines()
            for l in lines:
                l = l.strip()
                if l.startswith("MemAvailable:"):
                    parts = l.split()
                    if len(parts) > 1 and parts[1].isdigit():
                        avail = int(parts[1])
                elif l.isdigit():
                    v = int(l)
                    if v > 100000:
                        freq = v // 1000
                    elif v > 1000:
                        temp = round(v / 1000.0, 1)
                    else:
                        temp = float(v)
                elif l and not l.isdigit() and "/" != l and len(l) < 40:
                    model = l
            return _j({"ok": True, "model": model, "avail": avail,
                       "temp": temp, "freq": freq})
        except Exception as e:
            return _j({"ok": False, "msg": str(e)})

    # ---- 设备信息 ----
    def device_info(self):
        try:
            info = E.DeviceInfo()
            m = E.mem_info()
            b = E.battery()
            return _j({
                "ok": True,
                "serial": info.serial, "model": info.model,
                "brand": info.brand, "android": info.android,
                "sdk": info.sdk, "abi": info.abi, "kernel": info.kernel,
                "slot": info.slot, "root": info.root,
                "mem": {"total": m["total"], "available": m["available"],
                        "swap_total": m["swap_total"], "swap_free": m["swap_free"]},
                "gpu": E.gpu_freq(), "cpu_freq": E.cpu_freq(),
                "cpu_temp": E.cpu_temp(), "governor": E.cpu_governor(),
                "battery": {"pct": b.get("capacity"), "status": b.get("status")},
            })
        except Exception as e:
            return _err(e)

    # ---- 性能 ----
    def perf_status(self):
        try:
            d = F.current_perf()
            return _j({"ok": True, "governor": d.get("governor"),
                       "cpu0": d.get("cpu0_max"), "cpu4": d.get("cpu4_max"),
                       "cpu7": d.get("cpu7_max"), "cur": d.get("cur_freq"),
                       "gpu": d.get("gpu")})
        except Exception as e:
            return _err(e)

    def perf_set(self, level):
        try:
            ok, txt = F.set_performance(level)
            d = F.current_perf()
            return _j({"ok": bool(ok), "msg": txt[-400:],
                       "cpu0": d.get("cpu0_max"), "cpu4": d.get("cpu4_max"),
                       "cpu7": d.get("cpu7_max"), "gpu": d.get("gpu")})
        except Exception as e:
            return _err(e)

    # ---- 内存 ----
    def mem_status(self):
        try:
            st = F.swap_status()
            return _j({
                "ok": True,
                "mem": st["mem"],
                "swaps": st["all"],
                "swappiness": F.get_swappiness(),
                "zram_mb": F.zram_size_mb(),
            })
        except Exception as e:
            return _err(e)

    def set_swappiness(self, pct):
        try:
            ok, cur = F.set_swappiness(pct)
            return _j({"ok": bool(ok), "value": cur})
        except Exception as e:
            return _err(e)

    def resize_zram(self, mb):
        try:
            ok, txt = F.resize_zram(int(mb))
            return _j({"ok": bool(ok), "mb": F.zram_size_mb(), "msg": txt[-300:]})
        except Exception as e:
            return _err(e)

    def drop_caches(self):
        try:
            ok, _ = F.drop_caches()
            return _j({"ok": bool(ok)})
        except Exception as e:
            return _err(e)

    # ---- 风扇 ----
    def fan_status(self):
        try:
            d = F.fan_status()
            return _j({"ok": True, "driver": d.get("driver"),
                       "zones": d.get("zones") or []})
        except Exception as e:
            return _err(e)

    def backlight_fix(self):
        try:
            ok, txt = F.backlight_fix()
            return _j({"ok": bool(ok), "msg": txt})
        except Exception as e:
            return _err(e)

    # ---- Root ----
    def root_status(self):
        try:
            d = F.root_status()
            return _j({"ok": True, "has_root": d.get("has_root"),
                       "su_path": d.get("su_path"), "magisk": d.get("magisk"),
                       "zygote": d.get("zygote")})
        except Exception as e:
            return _err(e)

    def root_adb(self):
        try:
            ok, txt = F.root_adb_enable()
            return _j({"ok": bool(ok), "msg": txt})
        except Exception as e:
            return _err(e)

    def list_modules(self):
        try:
            mods = F.list_modules()
            return _j({"ok": True, "modules": mods})
        except Exception as e:
            return _err(e)

    # ---- 应用 ----
    def list_apps(self):
        try:
            pkgs = F.list_packages(True, True)
            apps = []
            for p in pkgs[:120]:
                d = F.package_detail(p)
                apps.append({"pkg": p, "version": d.get("version"),
                             "disabled": d.get("disabled", False)})
            return _j({"ok": True, "apps": apps})
        except Exception as e:
            return _err(e)

    def uninstall_app(self, pkg):
        try:
            r = F.uninstall(pkg)
            return _j({"ok": "Success" in r.text(), "msg": r.text()[:200]})
        except Exception as e:
            return _err(e)

    def pull_apk(self, pkg):
        try:
            ok, msg, path = F.pull_apk(pkg)
            return _j({"ok": bool(ok), "msg": msg, "path": path})
        except Exception as e:
            return _err(e)

    def pick_install_apk(self):
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            p = filedialog.askopenfilename(
                title="选择 APK", filetypes=[("APK", "*.apk")])
            root.destroy()
            if not p:
                return _j({"ok": False, "msg": "未选择"})
            return _j({"ok": True, "path": p})
        except Exception as e:
            return _err(e)

    def install_apk(self, path):
        try:
            r = E.adb("install", "-r", "--abi", "arm64-v8a", path, timeout=600)
            return _j({"ok": "Success" in r.text(), "msg": r.text()[-300:]})
        except Exception as e:
            return _err(e)

    # ---- 机型 / 分区 ----
    def device_profile(self, refresh=False):
        """机型识别 + 能力矩阵（界面据此决定哪些按钮可用）"""
        try:
            det = D.detect(refresh=bool(refresh))
            if not det.get("ok"):
                return _j({"ok": False, "why": det.get("why", "")})
            prof = det.get("profile") or {}
            return _j({
                "ok": True,
                "model": det.get("model"),
                "profile_id": det.get("profile_id"),
                "is_dji": det.get("is_dji", True),
                "profile_name": prof.get("name", ""),
                "platform": det.get("platform"),
                "android": det.get("android"),
                "soc": prof.get("soc", ""),
                "fingerprint": det.get("fingerprint"),
                "slot": det.get("slot"),
                "crypto": det.get("crypto"),
                "byname": det.get("byname"),
                "su": det.get("su"),
                "bl_unlocked": det.get("bl_unlocked"),
                "caps": det.get("caps"),
                "reasons": det.get("reasons"),
                "notes": det.get("notes"),
                "partitions_hint": det.get("partitions_hint"),
                "flashable_hint": det.get("flashable_hint"),
            })
        except Exception as e:
            return _err(e)

    def partition_info(self):
        """分区清单（含大小）＋机型能力，一次拿全给界面"""
        try:
            det = D.detect()
            names, sizes, err = D.list_partitions(with_size=True)
            hint = det.get("partitions_hint") or []
            flashable = det.get("flashable_hint") or []
            parts = []
            for n in names:
                parts.append({
                    "name": n,
                    "size": sizes.get(n, 0),
                    "size_h": E.kb_human(sizes.get(n, 0)) if sizes.get(n) else "",
                    "key": n in hint,
                    "flashable": n in flashable,
                })
            return _j({
                "ok": True,
                "connected": E.is_connected(),
                "model": det.get("model", ""),
                "caps": det.get("caps", {}),
                "is_dji": det.get("is_dji", True),
                "reasons": det.get("reasons", []),
                "byname": det.get("byname", ""),
                "parts": parts,
                "err": err,
            })
        except Exception as e:
            return _err(e)

    def list_partitions(self):
        try:
            return _j({"ok": True, "parts": F.list_partitions()})
        except Exception as e:
            return _err(e)

    def backup_all(self, and_pull):
        try:
            results, total = F.backup_all()
            okn = sum(1 for _, ok, _ in results if ok)
            out = {"ok": okn > 0, "count": okn, "total": len(results),
                   "size": E.human(total)}
            if and_pull:
                ok2, dest, _ = F.pull_backup()
                out["pulled"] = bool(ok2)
                out["dest"] = dest
            return _j(out)
        except Exception as e:
            return _err(e)

    def download_partition(self, name, force=False):
        """备份单个分区并拉到电脑（返回本地路径）"""
        try:
            ok, local, size, sha, msg = F.download_partition(name, force=bool(force))
            return _j({"ok": ok, "path": local if ok else "",
                       "size": size, "sha256": sha,
                       "msg": msg, "size_h": E.kb_human(size) if size else ""})
        except Exception as e:
            return _err(e)

    def flash_partition_adb(self, part, img):
        """adb 直刷（dd 写入）：先自动备份 → 校验大小 → 写入 → 回读校验 → 失败回滚"""
        try:
            ok, msg, detail = F.flash_partition(part, img)
            return _j({"ok": ok, "msg": msg, "detail": detail})
        except Exception as e:
            return _err(e)

    # ---- 刷机 ----
    def pick_image(self):
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            p = filedialog.askopenfilename(
                title="选择镜像", filetypes=[("镜像", "*.img"), ("所有", "*.*")])
            root.destroy()
            if not p:
                return _j({"ok": False})
            return _j({"ok": True, "path": p})
        except Exception as e:
            return _err(e)

    def fastboot_flash(self, part, img):
        try:
            r = E._run([E.FASTBOOT, "flash", part, img], timeout=900)
            return _j({"ok": r.ok, "msg": r.text()[-300:]})
        except Exception as e:
            return _err(e)

    def fastboot_reboot(self):
        try:
            r = E._run([E.FASTBOOT, "reboot"], timeout=60)
            return _j({"ok": r.ok, "msg": r.text()})
        except Exception as e:
            return _err(e)

    def check_bootloader(self):
        """BL 解锁状态：用 adb 属性判断（fastboot getvar 在设备未进 bootloader 时读不到）"""
        try:
            r = E.adb_shell(
                "getprop ro.boot.verifiedbootstate; "
                "getprop ro.boot.flash.locked; "
                "getprop ro.secureboot.lockstate", timeout=15)
            vals = [x.strip() for x in r.out.splitlines() if x.strip()]
            state = vals[0] if len(vals) > 0 else ""
            locked = vals[1] if len(vals) > 1 else ""
            unlocked = (state == "orange") or (locked == "0")
            msg = ("BL 已解锁" if unlocked else "BL 未解锁")
            msg += "  (verifiedbootstate=" + (state or "?") + ", flash.locked=" + (locked or "?") + ")"
            return _j({"ok": True, "unlocked": unlocked, "msg": msg,
                       "state": state, "locked": locked})
        except Exception as e:
            return _err(e)

    def reboot_bootloader(self):
        try:
            E.adb("reboot", "bootloader", timeout=30)
            return _j({"ok": True})
        except Exception as e:
            return _err(e)

    def reboot_recovery(self):
        try:
            E.adb("reboot", "recovery", timeout=30)
            return _j({"ok": True})
        except Exception as e:
            return _err(e)

    def reboot_device(self):
        try:
            E.adb("reboot", timeout=30)
            return _j({"ok": True})
        except Exception as e:
            return _err(e)

    # ---- 投屏 ----
    def mirror_status(self):
        """投屏能力：能不能用 scrcpy 真视频流 / 只能用截图推流"""
        try:
            prof = D.detect()
            caps = (prof.get("caps") or {}) if prof.get("ok") else {}
            probe = M.probe_app_process()
            scrcpy_ok = bool(caps.get("mirror_scrcpy")) and (probe.get("ok") is not False)
            model = prof.get("model") or ""
            if probe.get("ok") is False:
                tip = "这台机型（%s）的 app_process 被 SELinux 拦了，只能用截图推流（1~2 帧/秒）。" % (model or "未知")
            elif probe.get("ok") is True:
                tip = "app_process 可用，建议用 scrcpy 真视频流（流畅、可鼠标操作）。"
            else:
                tip = "没检测到设备。插上遥控器后可以自动判断用哪种投屏。"
            return _j({"ok": True, "scrcpy_exe": M.scrcpy_ready(),
                       "app_process": probe.get("ok"), "probe_msg": probe.get("msg", ""),
                       "model": model, "profile": (prof.get("profile") or {}).get("name", ""),
                       "suggest_scrcpy": bool(scrcpy_ok), "connected": bool(prof.get("ok")),
                       "tip": tip})
        except Exception as e:
            return _err("mirror_status: %s" % e)

    def mirror_scrcpy_start(self, size=1920, fps=60, bitrate="8M", record=False):
        try:
            return _j(M.start(max_size=int(size or 1920), max_fps=int(fps or 60),
                              bitrate=(bitrate or "8M"), record=bool(record)))
        except Exception as e:
            return _err("启动 scrcpy 失败: %s" % e)

    def mirror_scrcpy_stop(self):
        try:
            return _j(M.stop())
        except Exception as e:
            return _err("停止 scrcpy 失败: %s" % e)

    def mirror_scrcpy_status(self):
        try:
            return _j(M.status())
        except Exception as e:
            return _err("查询 scrcpy 状态失败: %s" % e)

    def pad_status(self):
        st = GP.state()
        st.update(GP.available())
        return _j(st)

    def pad_start(self, port=9999):
        try:
            return _j(GP.start(port=int(port or 9999)))
        except Exception as e:
            return _err("启动虚拟手柄失败: %s" % e)

    def pad_stop(self):
        try:
            return _j(GP.stop())
        except Exception as e:
            return _err("停止虚拟手柄失败: %s" % e)

    def pad_state(self):
        try:
            return _j(GP.state())
        except Exception as e:
            return _err("查询虚拟手柄状态失败: %s" % e)

    def scrcpy_status(self):
        """投屏能力检测。★ 实测本机 app_process 被 DJI ROM 拦截，
        scrcpy 的 server 端无法运行，只能用 exec-out 轮询截图方案。"""
        try:
            r = E.adb_shell("echo ok", timeout=8)
            connected = ("ok" in r.out) or E.is_connected()
        except Exception:
            connected = False
        return _j({"ok": True,
                   "exists": os.path.isfile(E.SCRCPY),
                   "path": E.SCRCPY,
                   "connected": bool(connected),
                   "scrcpy_usable": False,
                   "reason": "本机 DJI ROM 拦截 app_process，scrcpy server 无法启动；" +
                             "已改用 exec-out 轮询截图方案"})

    def start_scrcpy(self, size, fps):
        try:
            if not os.path.isfile(E.SCRCPY):
                return _j({"ok": False, "msg": "找不到 scrcpy.exe"})
            if not E.is_connected():
                return _j({"ok": False, "msg": "未连接设备"})
            args = ["--max-size=%d" % int(size), "--max-fps=%d" % int(fps),
                    "--window-title=RC2 遥控器"]
            kw = {}
            if os.name == "nt":
                kw["creationflags"] = 0x00000008
            subprocess.Popen([E.SCRCPY] + args, cwd=E.SCRCPY_DIR, **kw)
            return _j({"ok": True})
        except Exception as e:
            return _err(e)

    def screen_frame(self):
        """实时画面的一帧（base64 PNG）。用 exec-out 直读，绕开 app_process。"""
        try:
            import base64
            r = E._run([E.ADB, "exec-out", "screencap", "-p"], timeout=12)
            if not r.ok:
                return _j({"ok": False, "msg": "截图失败"})
            # _run 用 utf-8 解码会损坏二进制，这里重新直接取
            import subprocess
            p = subprocess.run([E.ADB, "exec-out", "screencap", "-p"],
                               capture_output=True, timeout=15,
                               creationflags=0x08000000 if os.name == "nt" else 0)
            data = p.stdout or b""
            if len(data) < 100:
                return _j({"ok": False, "msg": "画面为空"})
            b64 = base64.b64encode(data).decode("ascii")
            return _j({"ok": True, "data": b64, "size": len(data)})
        except Exception as e:
            return _err(e)

    def input_tap(self, x, y):
        """远程点击（部分 ROM 会拦截，返回真实结果）"""
        try:
            r = E.adb_shell("input tap %d %d" % (int(x), int(y)), timeout=15)
            return _j({"ok": r.ok, "msg": r.text()[:120]})
        except Exception as e:
            return _err(e)

    def input_key(self, code):
        try:
            r = E.adb_shell("input keyevent %s" % code, timeout=15)
            return _j({"ok": r.ok, "msg": r.text()[:120]})
        except Exception as e:
            return _err(e)

    def record_scrcpy(self):
        try:
            if not os.path.isfile(E.SCRCPY):
                return _j({"ok": False, "msg": "找不到 scrcpy.exe"})
            E.ensure_out()
            dst = os.path.join(E.OUT, "rec_" + time.strftime("%Y%m%d_%H%M%S") + ".mp4")
            kw = {}
            if os.name == "nt":
                kw["creationflags"] = 0x00000008
            subprocess.Popen([E.SCRCPY, "--record=" + dst, "--max-size=1280"],
                             cwd=E.SCRCPY_DIR, **kw)
            return _j({"ok": True, "path": dst})
        except Exception as e:
            return _err(e)

    def stop_scrcpy(self):
        try:
            E._run(["taskkill", "/F", "/IM", "scrcpy.exe"], timeout=30)
            return _j({"ok": True})
        except Exception as e:
            return _err(e)

    def screenshot(self):
        try:
            E.ensure_out()
            name = "shot_" + time.strftime("%Y%m%d_%H%M%S") + ".png"
            remote = "/data/local/tmp/" + name
            r = E.adb_shell("screencap -p " + remote, timeout=60)
            if not r.ok:
                return _j({"ok": False, "msg": r.text()})
            local = os.path.join(E.OUT, name)
            r2 = E.adb("pull", remote, local, timeout=120)
            E.adb_shell("rm -f " + remote, timeout=15)
            return _j({"ok": r2.ok, "path": local})
        except Exception as e:
            return _err(e)

    def open_out_dir(self):
        try:
            E.ensure_out()
            os.startfile(E.OUT)
            return _j({"ok": True})
        except Exception as e:
            return _err(e)

    # ---- 工具 ----
    def run_shell(self, cmd, root):
        try:
            r = E.sh(cmd, timeout=120) if root else E.adb_shell(cmd, timeout=120)
            return _j({"ok": r.ok, "out": r.text()[:8000]})
        except Exception as e:
            return _err(e)

    def dump_info(self):
        try:
            info = E.DeviceInfo()
            m = E.mem_info()
            b = E.battery()
            lines = [
                "===== RC2 设备信息 =====",
                "型号: " + info.model, "品牌: " + info.brand,
                "系统: Android " + info.android + " (SDK " + info.sdk + ")",
                "ABI: " + info.abi, "内核: " + info.kernel,
                "序列号: " + info.serial, "槽位: " + info.slot,
                "Root: " + ("是" if info.root else "否"),
                "zygote_policy: " + info.zygote_policy,
                "--- 内存 ---",
                "总内存: " + E.kb_human(m["total"]),
                "可用: " + E.kb_human(m["available"]),
                "swap 总: " + E.kb_human(m["swap_total"]),
                "--- 状态 ---",
                "CPU: %s MHz  %s℃  %s" % (E.cpu_freq(), E.cpu_temp(), E.cpu_governor()),
                "GPU: %s MHz" % E.gpu_freq(),
                "电池: %s%% %s" % (b.get("capacity"), b.get("status")),
            ]
            E.ensure_out()
            p = os.path.join(E.OUT, "device_info_" + time.strftime("%Y%m%d_%H%M%S") + ".txt")
            with open(p, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            return _j({"ok": True, "path": p, "lines": lines})
        except Exception as e:
            return _err(e)

    def logcat_tail(self):
        try:
            r = E.adb_shell("logcat -d -t 80", timeout=40)
            return _j({"ok": True, "out": r.out[:8000]})
        except Exception as e:
            return _err(e)

    def wireless_adb(self):
        try:
            E.adb("tcpip", "5555", timeout=30)
            r = E.adb_shell("ip addr show wlan0 2>/dev/null | grep inet | head -1", timeout=20)
            import re as _re
            m = _re.search(r"inet (\d+\.\d+\.\d+\.\d+)", r.out)
            if m:
                return _j({"ok": True, "ip": m.group(1)})
            return _j({"ok": False, "msg": "取不到 WiFi IP"})
        except Exception as e:
            return _err(e)

    def stay_awake(self):
        try:
            E.adb_shell("svc power stayon true", timeout=20)
            return _j({"ok": True})
        except Exception as e:
            return _err(e)

    def clean_tmp(self):
        try:
            r = E.sh("rm -f /data/local/tmp/*.png /data/local/tmp/*.log "
                     "/data/local/tmp/rc2task.sh 2>/dev/null; echo done")
            return _j({"ok": r.ok})
        except Exception as e:
            return _err(e)
