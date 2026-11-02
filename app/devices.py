# -*- coding: utf-8 -*-
"""机型识别 + 分区路径发现 + 能力矩阵

为什么单独一个模块：
  旧版把「/dev/block/bootdevice/by-name」「boot_a」「dji_apk」这些全写死，
  RC2 上能用，换 RC Pro(RM510)/RC1/RC Plus 就全瞎：路径不存在、分区名不同、
  没有 root 也不说，最后只给用户一个空列表 —— 看起来像"备份功能坏了"。

本模块只做三件事，且全部"先探测再下结论"：
  1) detect()       读 getprop / root / BL / slot，得出确切机型与能力
  2) byname_dir()   在多个候选路径里找出真实存在的 by-name 目录
  3) list_partitions() 真实分区清单（含大小）
"""
import engine as E

# by-name 目录候选（按命中概率排序）
BYNAME_CANDIDATES = [
    "/dev/block/bootdevice/by-name",
    "/dev/block/by-name",
    "/dev/block/platform/soc/1d84000.ufshc/by-name",
    "/dev/block/platform/soc/8804000.sdhci/by-name",
    "/dev/block/platform/msm_sdcc.1/by-name",
]

# 已知机型档案：靠 model / platform 关键字匹配，按顺序取第一个命中的
PROFILES = [
    {
        "id": "rc2",
        "name": "DJI RC 2",
        "match": ["DJI RC 2", "rc331"],
        "platform": "lahaina",
        "android": "11",
        "soc": "骁龙 778G (SM7325-AD)",
        "scrcpy_ok": False,
        "partitions": ["boot_a", "boot_b", "dji_apk", "dji_persist", "persist",
                       "misc", "metadata", "vbmeta_a", "vbmeta_b", "dtbo_a", "dtbo_b",
                       "super", "modem_a", "modem_b", "userdata"],
        "flashable": ["boot_a", "boot_b", "dji_apk", "vbmeta_a", "vbmeta_b",
                      "dtbo_a", "dtbo_b", "misc", "metadata"],
        "notes": [
            "本机可用 adb-root 方案拿到 su（/debug_ramdisk/su），因此 adb 模式下即可 dd 备份与刷写。",
            "dji_apk 分区是 DJI Fly 的加密 app.img（IM*H / PRAKTBIE / flyapp），能备份能整块刷回，但改内容解不开。",
            "boot 分区 96MB，刷错会开不了机；刷前务必先备份，变砖可按返回键+电源进 fastboot 刷回。",
        ],
    },
    {
        "id": "rcpro",
        "name": "DJI RC Pro",
        "match": ["DJI RC Pro", "RM510"],
        "platform": "kona",
        "android": "10",
        "soc": "骁龙 865 (SM8250)",
        "scrcpy_ok": True,
        "partitions": ["boot_a", "boot_b", "dji_persist", "persist", "misc", "metadata",
                       "vbmeta_a", "vbmeta_b", "vbmeta_system_a", "vbmeta_system_b",
                       "dtbo_a", "dtbo_b", "super", "modem_a", "modem_b", "userdata"],
        "flashable": ["boot_a", "boot_b", "vbmeta_a", "vbmeta_b", "dtbo_a", "dtbo_b",
                      "misc", "metadata"],
        "notes": [
            "RC Pro 的 fastboot 只支持写(flash/erase)、不支持读：fetch / oem dump / get_staged 全部 unknown command。",
            "bootloader 通常锁着（unlocked:no），没有 root 时拿不到分区内容 —— 这不是本工具的 bug，是设备限制。",
            "要备份只能先有 root 或 EDL 9008+签名 firehose，两者都有变砖风险。",
            "该机型没有 dji_apk 分区，DJI Fly 装在 super 的逻辑分区里。",
        ],
    },
    {
        "id": "rc1",
        "name": "DJI RC",
        "match": ["DJI RC", "RM520", "RM500"],
        "platform": "sdm845",
        "android": "9",
        "soc": "骁龙 845 (SDM845)",
        "scrcpy_ok": True,
        "partitions": ["boot_a", "boot_b", "persist", "misc", "vbmeta_a", "vbmeta_b",
                       "dtbo_a", "dtbo_b", "system_a", "vendor_a", "userdata"],
        "flashable": ["boot_a", "boot_b", "vbmeta_a", "vbmeta_b", "dtbo_a", "dtbo_b", "misc"],
        "notes": [
            "老机型，system/vendor 是独立分区（没有 super 动态分区）。",
            "Android 9 的 su 生态与 RC2 完全不同，优先走 fastboot 刷写。",
        ],
    },
    {
        "id": "rcplus",
        "name": "DJI RC Plus",
        "match": ["RC Plus", "RM700", "RM701"],
        "platform": "kona",
        "android": "10",
        "soc": "骁龙 865 (SM8250)",
        "scrcpy_ok": True,
        "partitions": ["boot_a", "boot_b", "persist", "misc", "metadata",
                       "vbmeta_a", "vbmeta_b", "dtbo_a", "dtbo_b", "super", "userdata"],
        "flashable": ["boot_a", "boot_b", "vbmeta_a", "vbmeta_b", "dtbo_a", "dtbo_b", "misc"],
        "notes": [
            "与 RC Pro 同代高通平台，fastboot 同样是只写不读。",
            "分区名以实测 getvar all 为准，本表是常见集合，界面会用设备真实列表覆盖。",
        ],
    },
    {
        "id": "rcpro2",
        "name": "DJI RC Pro 2",
        "match": ["RC Pro 2", "RM510B", "RM530"],
        "platform": "taro",
        "android": "12",
        "soc": "骁龙 8 Gen1 (SM8450)",
        "scrcpy_ok": True,
        "partitions": ["boot_a", "boot_b", "persist", "misc", "metadata",
                       "vbmeta_a", "vbmeta_b", "dtbo_a", "dtbo_b", "super", "userdata"],
        "flashable": ["boot_a", "boot_b", "vbmeta_a", "vbmeta_b", "dtbo_a", "dtbo_b", "misc"],
        "notes": [
            "新平台默认开 verity/AVB，改 boot 前先确认 vbmeta 是否要一起处理。",
            "分区表未在本项目实测过，界面以设备真实 by-name 列表为准。",
        ],
    },
]

GENERIC = {
    "id": "generic",
    "name": "未知 DJI 遥控器",
    "match": [],
    "platform": "",
    "android": "",
    "soc": "",
    "partitions": ["boot_a", "boot_b", "persist", "misc", "metadata",
                   "vbmeta_a", "vbmeta_b", "userdata"],
    "flashable": ["boot_a", "boot_b", "vbmeta_a", "vbmeta_b", "misc"],
    "notes": ["未识别的机型：分区清单以设备真实 by-name 为准，刷写前请务必先备份。"],
}

_cache = {}


def _props():
    keys = ["ro.product.model", "ro.board.platform", "ro.boot.hardware",
            "ro.build.version.release", "ro.build.version.sdk",
            "ro.build.fingerprint", "ro.boot.verifiedbootstate",
            "ro.boot.flash.locked", "ro.secureboot.lockstate",
            "ro.boot.slot_suffix", "ro.crypto.state", "ro.debuggable", "ro.secure",
            "ro.product.device", "ro.boot.vbmeta.device_state"]
    cmd = ";".join("getprop %s" % k for k in keys)
    r = E.adb_shell(cmd, timeout=20)
    vals = [x.strip() for x in (r.out or "").splitlines()]
    d = {}
    if len(vals) >= len(keys):
        for k, v in zip(keys, vals[:len(keys)]):
            d[k] = v
    else:
        for k in keys:
            rr = E.adb_shell("getprop %s" % k, timeout=8)
            d[k] = (rr.out or "").strip()
    return d


def match_profile(model, platform="", device=""):
    blob = " ".join([model or "", platform or "", device or ""]).upper()
    for p in PROFILES:
        for kw in p["match"]:
            if kw.upper() in blob:
                return p
    return GENERIC


def byname_dir(refresh=False):
    """找出真实存在的 by-name 目录；无 root 时先试普通 shell（大多数机型可读）"""
    if not refresh and _cache.get("byname") is not None:
        return _cache["byname"]
    found = None
    for d in BYNAME_CANDIDATES:
        r = E.adb_shell("ls -d %s 2>/dev/null" % d, timeout=10)
        if d in (r.out or ""):
            found = d
            break
    if not found and E.has_root():
        for d in BYNAME_CANDIDATES:
            r = E.sh("ls -d %s 2>/dev/null" % d, timeout=10)
            if d in (r.out or ""):
                found = d
                break
    _cache["byname"] = found
    return found


def detect(refresh=False):
    """机型识别 + 能力矩阵。失败也给出可读原因，绝不返回空壳。"""
    if not refresh and _cache.get("detect"):
        return _cache["detect"]

    if not E.is_connected():
        res = {
            "ok": False,
            "why": "没有检测到设备。请用 USB 连接遥控器，或在遥控器上打开无线调试。",
            "model": "", "profile": GENERIC, "caps": {}, "props": {},
        }
        _cache["detect"] = res
        return res

    p = _props()
    model = p.get("ro.product.model") or p.get("ro.product.device") or "未知"
    prof = match_profile(model, p.get("ro.board.platform"), p.get("ro.product.device"))

    root_path = E.find_su()
    byname = byname_dir(refresh=True)
    vbs = (p.get("ro.boot.verifiedbootstate") or "").lower()
    locked = (p.get("ro.boot.flash.locked") or "").strip()
    vb = (p.get("ro.boot.vbmeta.device_state") or "").lower()
    bl_unlocked = None
    if vbs:
        bl_unlocked = vbs in ("orange", "yellow")
    if locked in ("0", "1"):
        bl_unlocked = (locked == "0")
    if vb in ("unlocked", "locked"):
        bl_unlocked = (vb == "unlocked")

    # 非 DJI 设备（插着的手机/平板）要明确说出来，别让人以为识别错了机型
    is_dji = (prof["id"] != "generic") or ("DJI" in (p.get("ro.build.fingerprint") or "").upper())
    caps = {
        "adb": True,
        "root": bool(root_path),
        "byname": bool(byname),
        "backup": bool(root_path and byname),
        "flash_adb": bool(root_path and byname),
        "flash_fastboot": bool(bl_unlocked),
        "fastboot_read": False,
        # 能不能跑 scrcpy 真视频流（DJI RC2 被 SELinux 拦 app_process，只能用截图推流）
        "mirror_scrcpy": bool(prof.get("scrcpy_ok", True)),
    }
    if not is_dji:
        caps["backup"] = False
        caps["flash_adb"] = False
        caps["flash_fastboot"] = False

    reasons = []
    if not is_dji:
        reasons.append("这台设备不是 DJI 遥控器（型号 %s）。本工具只对 DJI RC 系列负责，"
                       "请不要在上面刷分区。" % model)
    if not root_path:
        reasons.append("没有 root：分区备份/下载、adb 直刷都做不了（只能做只读查询）。")
    if not byname:
        reasons.append("找不到 by-name 分区目录：该机型路径与已知候选都不同。")
    if bl_unlocked is False:
        reasons.append("Bootloader 锁定：fastboot 只能 getvar，不能刷写。")
    if bl_unlocked is None:
        reasons.append("未能判定 Bootloader 状态（属性缺失）。")

    res = {
        "ok": True,
        "is_dji": is_dji,
        "model": model,
        "profile": prof,
        "profile_id": prof["id"],
        "platform": p.get("ro.board.platform", ""),
        "android": p.get("ro.build.version.release", ""),
        "sdk": p.get("ro.build.version.sdk", ""),
        "fingerprint": p.get("ro.build.fingerprint", ""),
        "slot": p.get("ro.boot.slot_suffix", ""),
        "crypto": p.get("ro.crypto.state", ""),
        "debuggable": p.get("ro.debuggable", ""),
        "secure": p.get("ro.secure", ""),
        "byname": byname or "",
        "su": root_path or "",
        "bl_unlocked": bl_unlocked,
        "verifiedbootstate": vbs,
        "flash_locked": locked,
        "caps": caps,
        "reasons": reasons,
        "partitions_hint": prof["partitions"],
        "flashable_hint": prof["flashable"],
        "notes": prof["notes"],
    }
    _cache["detect"] = res
    return res


def clear_cache():
    _cache.clear()


def list_partitions(with_size=True):
    """真实分区列表（含大小）。返回 (names, sizes, err)"""
    d = byname_dir()
    if not d:
        return [], {}, "找不到 by-name 目录（设备未连接或无权限）"
    r = E.adb_shell("ls %s" % d, timeout=20)
    names = sorted([x.strip() for x in (r.out or "").split() if x.strip()])
    if not names and E.has_root():
        r = E.sh("ls %s" % d, timeout=20)
        names = sorted([x.strip() for x in (r.out or "").split() if x.strip()])
    if not names:
        return [], {}, "分区列表为空：%s" % ((r.text() or "").strip()[:200])
    sizes = {}
    if with_size:
        cmd = ("for p in %s; do echo $p $(blockdev --getsize64 %s/$p 2>/dev/null); done"
               % (" ".join(names), d))
        rr = E.adb_shell(cmd, timeout=40)
        if not rr.ok or not (rr.out or "").strip():
            rr = E.sh(cmd, timeout=40)
        for line in (rr.out or "").splitlines():
            ps = line.split()
            if len(ps) == 2 and ps[1].isdigit():
                sizes[ps[0]] = int(ps[1])
        if not sizes:
            for n in names:
                rr2 = E.adb_shell("blockdev --getsize64 %s/%s 2>/dev/null" % (d, n), timeout=8)
                if (rr2.out or "").strip().isdigit():
                    sizes[n] = int((rr2.out or "").strip())
    return names, sizes, ""


def partition_path(name):
    d = byname_dir()
    return ("%s/%s" % (d, name)) if d else None


def part_size(name):
    p = partition_path(name)
    if not p:
        return 0
    r = E.adb_shell("blockdev --getsize64 %s 2>/dev/null" % p, timeout=10)
    if not (r.out or "").strip().isdigit() and E.has_root():
        r = E.sh("blockdev --getsize64 %s 2>/dev/null" % p, timeout=10)
    return int((r.out or "").strip()) if (r.out or "").strip().isdigit() else 0
