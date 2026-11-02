# -*- coding: utf-8 -*-
"""RC2 搞机工具箱 —— 功能模块（全部真机验证过的节点与命令）

所有功能都基于实测的路径：
  - su: /debug_ramdisk/su
  - 分区: /dev/block/bootdevice/by-name/
  - 电池: /sys/class/power_supply/aprimary-bat/
  - 温度: /sys/class/thermal/thermal_zone{40,44,16}
  - 风扇: pwmchip4 ch0 被内核独占，无用户空间出口（只读监控）
  - 背光: pwmchip0 ch3，★ 绝不动，unexport 会黑屏
"""

import os
import re
import time

from engine import (adb, adb_shell, sh, run_script, find_su, has_root,
                    ensure_out, human, kb_human, OUT, device_serial)

# 关键分区（★ 只有 dji_apk 可安全刷回，其余刷回会显示"损坏"）
BACKUP_PARTS = ["boot_a", "boot_b", "dji_apk", "dji_persist", "persist",
                "modem_a", "modem_b", "modemst1", "modemst2", "misc",
                "metadata", "abl_a", "xbl_a", "vbmeta_a"]

# 三簇 CPU（★ 旧版全写 cpu0 上限，浪费大核）
CPU_CLUSTERS = [0, 4, 7]


def list_partitions():
    """列出所有分区（多机型：动态解析 by-name 目录）"""
    names, _sizes, err = D.list_partitions(with_size=False)
    if err and not names:
        return []
    return names


def part_size(name):
    """分区大小（字节，多机型）"""
    return D.part_size(name)


def part_size_map():
    """{分区名: 字节}，一次取全，供界面显示"""
    names, sizes, err = D.list_partitions(with_size=True)
    return names, sizes, err


def backup_partition(name, on_progress=None, force=False):
    """备份单个分区（走 partops：精确 count + 大小/sha256 校验）"""
    ok, remote, size, sha, msg = PO.backup(name, force=force)
    if on_progress and size:
        on_progress(name, size)
    return ok, ("%s -> %s (%s)" % (name, remote, msg)) if ok else msg, size


def download_partition(name, force=False, on_log=None):
    """备份并把单个分区拉到电脑"""
    return PO.download(name, force=force, on_log=on_log)


def flash_partition(name, local_img, on_log=None):
    """adb 直刷分区（dd 写入，先自动备份，写完回读校验）"""
    return PO.flash(name, local_img, on_log=on_log)


def backup_all(on_progress=None, on_log=None):
    """备份全部关键分区：按机型档案 ∩ 设备真实分区 取交集"""
    ensure_out()
    det = D.detect()
    names, _sizes, _err = D.list_partitions(with_size=False)
    if not names:
        if on_log:
            on_log("拿不到分区列表：%s" % (_err or "设备未连接"))
        return [], 0
    wanted = [p for p in (det.get("partitions_hint") or BACKUP_PARTS) if p in names]
    if not wanted:
        wanted = [p for p in BACKUP_PARTS if p in names]
    results, total = [], 0
    for i, p in enumerate(wanted):
        if on_log:
            on_log("[%d/%d] 备份 %s ..." % (i + 1, len(wanted), p))
        ok, msg, size = backup_partition(p)
        results.append((p, ok, msg))
        total += size
        if on_log:
            on_log("   %s %s" % ("OK" if ok else "FAIL", msg))
    return results, total


def pull_backup(dest=None):
    """把设备上的备份拉到电脑"""
    dest = dest or os.path.join(ensure_out(), "backup_%s" % time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    r = adb("pull", "/data/local/tmp/rc2backup", dest, timeout=1800)
    return r.ok, dest, r.text()


# ---------------------------------------------------------------------------
# 性能控制（★ 三簇分别拉满，旧版只拉 cpu0 浪费大核）
# ---------------------------------------------------------------------------

def cpu_max_freqs():
    """读各簇最高频（KHz）"""
    d = {}
    for c in CPU_CLUSTERS:
        r = adb_shell("cat /sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq" % c,
                      timeout=10)
        if r.ok and r.out.strip().isdigit():
            d[c] = int(r.out.strip())
    return d


def cpu_avail_freqs(cpu=0):
    r = adb_shell("cat /sys/devices/system/cpu/cpu%d/cpufreq/scaling_available_frequencies" % cpu,
                  timeout=10)
    if r.ok:
        return sorted(int(x) for x in r.out.split() if x.isdigit())
    return []


def gpu_avail_freqs():
    r = adb_shell("cat /sys/class/kgsl/kgsl-3d0/gpu_available_frequencies", timeout=10)
    out = []
    if r.ok:
        for x in r.out.split():
            # 格式可能带 Hz 或 MHz
            digits = re.sub(r"\D", "", x)
            if digits:
                v = int(digits)
                out.append(v // 1000000 if v > 100000 else v)
    return sorted(set(out))


def _perf_script(governor, cpu_scale, gpu_mhz):
    """生成性能设置脚本。cpu_scale: 0~1 的比例，1=拉满"""
    lines = ["#!/system/bin/sh", "echo '=== RC2 性能设置 ==='"]
    lines.append("for c in 0 1 2 3 4 5 6 7; do")
    lines.append("  echo %s > /sys/devices/system/cpu/cpu$c/cpufreq/scaling_governor 2>/dev/null" % governor)
    lines.append("done")
    for c in CPU_CLUSTERS:
        lines.append(
            "MAXC=$(cat /sys/devices/system/cpu/cpu%d/cpufreq/cpuinfo_max_freq 2>/dev/null)" % c)
        lines.append(
            "echo $MAXC > /sys/devices/system/cpu/cpu%d/cpufreq/scaling_max_freq 2>/dev/null" % c)
        lines.append("echo \"cpu%d max=$MAXC\"" % c)
    if gpu_mhz:
        lines.append("echo %d > /sys/class/kgsl/kgsl-3d0/max_gpuclk 2>/dev/null" % (gpu_mhz * 1000000))
        lines.append("echo \"gpu=%s\" $(cat /sys/class/kgsl/kgsl-3d0/max_gpuclk 2>/dev/null)")
    lines.append("echo '=== done ==='")
    return "\n".join(lines) + "\n"


def set_performance(level="perf"):
    """
    性能模式：
      save  省电   schedutil + GPU 最低
      bal   均衡   schedutil + GPU 中
      perf  性能   performance + 全部拉满
      ext   极速   performance + 拉满 + 解温控
    """
    gpus = gpu_avail_freqs()
    gmin = min(gpus) if gpus else 315
    gmax = max(gpus) if gpus else 812
    if level == "save":
        gov, gpu = "schedutil", gmin
    elif level == "bal":
        gov, gpu = "schedutil", gmax
    elif level == "perf":
        gov, gpu = "performance", gmax
    else:  # ext
        gov, gpu = "performance", gmax

    r = run_script(_perf_script(gov, 1.0, gpu), "perf_%s.sh" % level, root=True, timeout=90)

    # 极速模式额外解温控（把 cooling_device 全写 0）
    if level == "ext":
        run_script("""#!/system/bin/sh
for i in $(seq 0 22); do
  echo 0 > /sys/class/thermal/cooling_device$i/cur_state 2>/dev/null
done
echo cooling_done
""", "perf_thermal.sh", root=True, timeout=60)

    ok = r.ok and "done" in r.out
    return ok, r.text()


def restore_balanced():
    return set_performance("bal")


def current_perf():
    """读当前性能状态"""
    from engine import cpu_governor, cpu_freq, gpu_freq
    d = {}
    for c in CPU_CLUSTERS:
        r = adb_shell("cat /sys/devices/system/cpu/cpu%d/cpufreq/scaling_max_freq" % c, timeout=10)
        d["cpu%d_max" % c] = int(r.out.strip()) // 1000 if r.out.strip().isdigit() else 0
    d["governor"] = cpu_governor()
    d["cur_freq"] = cpu_freq()
    d["gpu"] = gpu_freq()
    return d


# ---------------------------------------------------------------------------
# Root / Magisk
# ---------------------------------------------------------------------------

def root_status():
    """root 状态详情"""
    su = find_su()
    d = {"su_path": su, "has_root": su is not None, "uid": None,
         "magisk": None, "zygote": None}
    if su:
        r = adb_shell("%s -c id" % su, timeout=15)
        d["uid"] = r.out.strip()
        r2 = adb_shell("%s -c 'magisk -v' 2>/dev/null" % su, timeout=15)
        if r2.ok and r2.out:
            d["magisk"] = r2.out.strip().splitlines()[0]
        else:
            r3 = adb_shell("%s -c '/debug_ramdisk/magisk -v' 2>/dev/null" % su, timeout=15)
            d["magisk"] = r3.out.strip().splitlines()[0] if r3.ok and r3.out else None
        r4 = adb_shell("getprop persist.dji.zygote_policy", timeout=10)
        d["zygote"] = r4.out.strip()
    return d


def root_adb_enable():
    """
    一键开启 adb root（不需要重刷 boot）
    ★ 旧版 bug：su 不在 PATH，setprop 全失败
    """
    script = """#!/system/bin/sh
setprop service.adb.root 1
sleep 1
stop adbd
sleep 1
start adbd
sleep 2
echo "service.adb.root=$(getprop service.adb.root)"
echo "shell_uid=$(id)"
"""
    r = run_script(script, "rootadb.sh", root=True, timeout=60)
    # 等一下 adb 重连
    time.sleep(3)
    adb("wait-for-device", timeout=30)
    ok = "uid=0" in r.out or "uid=2000" in r.out
    return ok, r.text()


def list_modules():
    """列出 Magisk 模块"""
    r = sh("ls -1 /data/adb/modules/ 2>/dev/null")
    if not r.ok:
        return []
    mods = []
    for name in r.out.split():
        name = name.strip()
        if not name:
            continue
        disabled = sh("test -f /data/adb/modules/%s/disable && echo D || echo E" % name)
        mods.append({"name": name, "disabled": "D" in disabled.out})
    return mods


def toggle_module(name, enable):
    """启用/停用 Magisk 模块"""
    if enable:
        cmd = "rm -f /data/adb/modules/%s/disable" % name
    else:
        cmd = "touch /data/adb/modules/%s/disable" % name
    r = sh(cmd)
    return r.ok, r.text()


def install_module(zip_path):
    """安装 Magisk 模块 zip"""
    remote = "/data/local/tmp/" + os.path.basename(zip_path)
    r = adb("push", zip_path, remote, timeout=300)
    if not r.ok:
        return False, "推送失败: " + r.text()
    su = find_su()
    if not su:
        return False, "无 root"
    r2 = adb_shell("%s -c 'magisk --install-module %s' 2>&1" % (su, remote), timeout=180)
    return r2.ok or "Done" in r2.out, r2.text()


# ---------------------------------------------------------------------------
# 应用管理
# ---------------------------------------------------------------------------

def list_packages(third_party=True, include_disabled=True):
    """列出应用包名"""
    args = ["pm", "list", "packages"]
    if third_party:
        args.append("-3")
    if include_disabled:
        args.append("-u")
    r = adb_shell(" ".join(args), timeout=30)
    out = []
    for line in r.out.splitlines():
        if line.startswith("package:"):
            out.append(line[len("package:"):].strip())
    return sorted(out)


def package_detail(pkg):
    """应用详情：版本、是否禁用、安装路径"""
    r = adb_shell("dumpsys package %s" % pkg, timeout=20)
    d = {"pkg": pkg, "version": "-", "versionCode": "-", "disabled": False, "path": "-"}
    m = re.search(r"versionName=(\S+)", r.out)
    if m:
        d["version"] = m.group(1)
    m = re.search(r"versionCode=(\d+)", r.out)
    if m:
        d["versionCode"] = m.group(1)
    m = re.search(r"enabled=(\d)", r.out)
    if m:
        d["disabled"] = (m.group(1) == "2" or m.group(1) == "3")
    m = re.search(r"codePath=(\S+)", r.out)
    if m:
        d["path"] = m.group(1)
    # 中文应用名
    r2 = adb_shell("dumpsys package %s | grep -A2 'applicationInfo' | head -5" % pkg, timeout=15)
    return d


def app_label(pkg):
    """尝试获取应用显示名"""
    r = adb_shell(
        "dumpsys package %s 2>/dev/null | grep -m1 -oE 'nonLocalizedLabel=[^ ]+|labelRes=0x[0-9a-f]+'" % pkg,
        timeout=15)
    if "nonLocalizedLabel=" in r.out:
        v = r.out.split("nonLocalizedLabel=")[1].split()[0]
        if v and v != "null":
            return v
    return pkg.split(".")[-1]


def uninstall(pkg):
    return adb_shell("pm uninstall %s" % pkg, timeout=60)


def disable_app(pkg):
    return adb_shell("pm disable-user --user 0 %s" % pkg, timeout=30)


def enable_app(pkg):
    return adb_shell("pm enable %s" % pkg, timeout=30)


def force_stop(pkg):
    return adb_shell("am force-stop %s" % pkg, timeout=20)


def launch_app(pkg):
    r = adb_shell(
        "monkey -p %s -c android.intent.category.LAUNCHER 1" % pkg, timeout=30)
    if "No activities found" in r.text():
        return adb_shell("cmd package resolve-activity --brief %s" % pkg, timeout=20)
    return r


def pull_apk(pkg, dest_dir=None):
    """导出 APK"""
    dest_dir = dest_dir or ensure_out()
    r = adb_shell("pm path %s" % pkg, timeout=20)
    paths = [l.replace("package:", "").strip() for l in r.out.splitlines()
             if l.startswith("package:")]
    if not paths:
        return False, "找不到 APK 路径", None
    local = os.path.join(dest_dir, "%s.apk" % pkg)
    r2 = adb("pull", paths[0], local, timeout=300)
    return r2.ok, r2.text(), local


# ---------------------------------------------------------------------------
# 虚拟内存 / 内存
# ---------------------------------------------------------------------------

def swap_status():
    from engine import swaps, mem_info
    rows = swaps()
    mem = mem_info()
    zram = [r for r in rows if "zram" in r["file"]]
    disk = [r for r in rows if "zram" not in r["file"]]
    return {"all": rows, "zram": zram, "disk": disk, "mem": mem}


def set_swappiness(pct):
    """设置 swappiness（内核上限 100）"""
    pct = max(0, min(100, int(pct)))
    r = sh("echo %d > /proc/sys/vm/swappiness" % pct)
    cur = sh("cat /proc/sys/vm/swappiness")
    return cur.out.strip() == str(pct), cur.out.strip()


def get_swappiness():
    r = adb_shell("cat /proc/sys/vm/swappiness", timeout=10)
    return r.out.strip()


def drop_caches():
    r = sh("sync; echo 3 > /proc/sys/vm/drop_caches")
    return r.ok, r.text()


def zram_size_mb():
    r = sh("cat /sys/block/zram0/disksize 2>/dev/null")
    if r.ok and r.out.strip().isdigit():
        return int(r.out.strip()) // 1048576
    return 0


def resize_zram(mb, prio=32758):
    """调整 zram 容量（★ 铁律：绝不能 swapoff 后不重开）"""
    script = """#!/system/bin/sh
SIZE_B=$(expr %d '*' 1048576)
echo "target zram = %d MB"
swapoff /dev/block/zram0 2>/dev/null
echo 1 > /sys/block/zram0/reset
echo $SIZE_B > /sys/block/zram0/disksize
mkswap /dev/block/zram0
swapon -p %d /dev/block/zram0
echo "result:"
cat /proc/swaps
""" % (int(mb), int(mb), int(prio))
    r = run_script(script, "zram.sh", root=True, timeout=120)
    ok = r.ok and "zram0" in r.out
    return ok, r.text()


# ---------------------------------------------------------------------------
# 风扇 / 温度
# ---------------------------------------------------------------------------

def thermal_zones():
    """读实测可读的 thermal zone（40/44/16）"""
    out = []
    for z in ("40", "44", "16"):
        r = adb_shell("cat /sys/class/thermal/thermal_zone%s/temp 2>/dev/null" % z, timeout=8)
        if r.ok and r.out.strip().isdigit():
            v = int(r.out.strip())
            t = v / 1000.0 if v > 1000 else float(v)
            out.append((z, round(t, 1)))
    return out


def fan_status():
    """
    风扇状态。
    ★ 实测真相：pwmchip4 ch0 被内核 pwm-fan 驱动独占，export 返回 1；
      cooling_device 里没有 fan 类型。风扇由内核自动调速，无法直接设占空比。
      这里只如实报告。
    """
    d = {"driver": None, "temp": None, "zones": thermal_zones()}
    r2 = adb_shell("ls /sys/devices/platform/soc/soc:pwm-fan/ 2>/dev/null | head -5", timeout=8)
    d["driver"] = "已绑定内核 pwm-fan 驱动" if (r2.ok and r2.out) else "未检测到"
    d["temp"] = d["zones"][0][1] if d["zones"] else None
    return d


def backlight_fix():
    """黑屏急救（只能救 pwmchip0 被误 unexport）"""
    script = """#!/system/bin/sh
echo 3 > /sys/class/pwm/pwmchip0/export 2>/dev/null
echo 1000000 > /sys/class/pwm/pwmchip0/pwm3/period 2>/dev/null
echo 1000000 > /sys/class/pwm/pwmchip0/pwm3/duty_cycle 2>/dev/null
echo 1 > /sys/class/pwm/pwmchip0/pwm3/enable 2>/dev/null
echo 255 > /sys/class/backlight/panel0-backlight/brightness 2>/dev/null
echo "backlight=$(cat /sys/class/backlight/panel0-backlight/brightness 2>/dev/null)"
"""
    r = run_script(script, "fixscreen.sh", root=True, timeout=60)
    return r.ok, r.text()
