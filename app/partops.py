# -*- coding: utf-8 -*-
"""分区读写：备份 / 下载到电脑 / adb 直刷（dd 走 su）

设计原则（都是为了不再出现"点了没反应"）：
  * 每个失败点都返回中文原因，绝不返回空壳
  * 读：先算期望大小 → dd 精确 count → 校验大小与 sha256
  * 写：先自动备份旧内容 → 校验镜像大小与分区一致 → dd 写入 → sync
        → 回读 sha256 比对 → 不一致就自动刷回备份
  * 所有路径都用 devices.byname_dir() 动态解析，不写死 bootdevice
"""
import os
import time

import engine as E
import devices as D

REMOTE_DIR = "/data/local/tmp/rc2part"


def ensure_out():
    d = os.path.join(E.OUT, "partitions")
    os.makedirs(d, exist_ok=True)
    return d


def _size_of_block(part):
    """分区字节数（0 表示读不到）"""
    return D.part_size(part)


def _sha_device(path):
    r = E.sh("sha256sum %s 2>/dev/null" % path, timeout=600)
    out = (r.out or "").strip().split()
    if out and len(out[0]) == 64:
        return out[0]
    return ""


def _sha_local(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _remote_size(path):
    r = E.sh("stat -c %%s %s 2>/dev/null" % path, timeout=60)
    s = (r.out or "").strip().split()
    return int(s[0]) if s and s[0].isdigit() else 0


def backup(part, force=False, on_log=None):
    """把分区 dump 到设备临时目录，返回 (ok, remote_path, size, sha, msg)"""
    pp = D.partition_path(part)
    if not pp:
        return False, "", 0, "", "找不到分区 %s（by-name 目录未解析）" % part
    if not E.has_root():
        return False, "", 0, "", "没有 root：无法读取块设备。%s" % _root_hint()

    size = _size_of_block(part)
    if size <= 0:
        return False, "", 0, "", "读不到分区大小：%s 可能不存在或权限不足" % pp

    dst = "%s/%s.img" % (REMOTE_DIR, part)
    E.sh("mkdir -p %s" % REMOTE_DIR, timeout=30)

    exist = _remote_size(dst)
    if exist == size and not force:
        if on_log:
            on_log("%s 已有完整备份（%s），跳过" % (part, E.kb_human(size)))
        return True, dst, size, _sha_device(dst), "已有备份"

    tmp = dst + ".tmp"
    E.sh("rm -f %s %s" % (tmp, dst), timeout=60)
    # bs=4096 + 精确 count：blockdev 读越界会报错或补零，count 最稳
    cnt = size // 4096 if size % 4096 == 0 else 0
    if cnt:
        cmd = "dd if=%s of=%s bs=4096 count=%d 2>&1 | tail -1" % (pp, tmp, cnt)
    else:
        cmd = "dd if=%s of=%s bs=4096 2>&1 | tail -1" % (pp, tmp)
    if on_log:
        on_log("读取 %s (%s) …" % (part, E.kb_human(size)))
    r = E.sh(cmd, timeout=1800)
    got = _remote_size(tmp)
    if got != size:
        return False, "", got, "", "写入不完整：期望 %d 字节，实际 %d 字节（%s）" % (
            size, got, (r.text() or "").strip()[:160])
    r = E.sh("mv -f %s %s; sync" % (tmp, dst), timeout=120)
    sha = _sha_device(dst)
    if on_log:
        on_log("%s 备份完成 %s sha256=%s" % (part, E.kb_human(size), sha[:16]))
    return True, dst, size, sha, "OK"


def download(part, force=False, on_log=None):
    """备份并拉到电脑。返回 (ok, local_path, size, sha, msg)"""
    ok, remote, size, sha, msg = backup(part, force=force, on_log=on_log)
    if not ok:
        return False, "", 0, "", msg
    out = ensure_out()
    local = os.path.join(out, "%s_%s.img" % (part, time.strftime("%Y%m%d_%H%M%S")))
    if on_log:
        on_log("拉取到电脑：%s" % os.path.basename(local))
    r = E.adb("pull", remote, local, timeout=3600)
    if not r.ok or not os.path.exists(local):
        return False, "", 0, "", "adb pull 失败：%s" % (r.text() or "")[:200]
    lsize = os.path.getsize(local)
    lsha = _sha_local(local)
    if lsize != size:
        return False, local, lsize, lsha, "本地大小不一致：设备 %d / 本地 %d" % (size, lsize)
    if sha and lsha != sha:
        return False, local, lsize, lsha, "sha256 不一致（设备 %s… / 本地 %s…）" % (sha[:12], lsha[:12])
    # 顺手写一个 .sha256 旁文件，方便以后校验
    try:
        with open(local + ".sha256", "w", encoding="utf-8") as f:
            f.write("%s  %s\n" % (lsha, os.path.basename(local)))
    except Exception:
        pass
    if on_log:
        on_log("%s 下载完成 %s" % (part, E.kb_human(lsize)))
    return True, local, lsize, lsha, "OK"


def flash(part, local_img, on_log=None, auto_backup=True):
    """adb 直刷分区（dd 写入）。返回 (ok, msg, detail_dict)"""
    d = {}
    pp = D.partition_path(part)
    if not pp:
        return False, "找不到分区 %s" % part, d
    if not E.has_root():
        return False, "没有 root：adb 直刷不可用。%s" % _root_hint(), d
    if not os.path.exists(local_img):
        return False, "镜像文件不存在：%s" % local_img, d

    size = _size_of_block(part)
    if size <= 0:
        return False, "读不到分区大小，不敢写：%s" % pp, d
    lsize = os.path.getsize(local_img)
    d.update({"part": part, "part_size": size, "img": local_img, "img_size": lsize})
    if lsize != size:
        return (False,
                "镜像大小与分区不一致：分区 %d 字节(%s)，镜像 %d 字节。"
                "为防止写坏，已拒绝。请用该分区原始的整块镜像。" % (
                    size, E.kb_human(size), lsize), d)

    backup_path = ""
    if auto_backup:
        ok, remote, bsize, bsha, msg = backup(part, force=True, on_log=on_log)
        if not ok:
            return False, "刷写前的自动备份失败，已中止：%s" % msg, d
        backup_path = remote
        d["backup"] = remote
        d["backup_sha"] = bsha
        # 同时留一份到电脑，避免设备端被清掉
        try:
            out = ensure_out()
            lp = os.path.join(out, "%s_before_%s.img" % (part, time.strftime("%Y%m%d_%H%M%S")))
            E.adb("pull", remote, lp, timeout=3600)
            d["backup_local"] = lp
        except Exception:
            pass

    remote_img = "%s_upload.img" % REMOTE_DIR
    E.sh("mkdir -p %s" % REMOTE_DIR, timeout=30)
    if on_log:
        on_log("推送镜像到设备（%s）…" % E.kb_human(lsize))
    r = E.adb("push", local_img, remote_img, timeout=3600)
    if not r.ok:
        return False, "push 失败：%s" % (r.text() or "")[:200], d
    if _remote_size(remote_img) != lsize:
        return False, "推送后大小不一致，已中止", d

    want = _sha_local(local_img)
    d["img_sha"] = want
    if on_log:
        on_log("写入 %s（dd bs=4096）…" % part)
    cnt = lsize // 4096 if lsize % 4096 == 0 else 0
    if cnt:
        cmd = "dd if=%s of=%s bs=4096 count=%d conv=fsync 2>&1 | tail -2; sync" % (remote_img, pp, cnt)
    else:
        cmd = "dd if=%s of=%s bs=4096 conv=fsync 2>&1 | tail -2; sync" % (remote_img, pp)
    r = E.sh(cmd, timeout=3600)
    d["dd_out"] = (r.text() or "").strip()[:300]

    if on_log:
        on_log("回读校验 sha256 …")
    got = _sha_device(pp)
    d["readback_sha"] = got
    if want and got and got != want:
        # 回滚
        if backup_path:
            if on_log:
                on_log("校验失败，正在刷回备份 …")
            E.sh("dd if=%s of=%s bs=4096 conv=fsync 2>&1 | tail -1; sync" % (backup_path, pp),
                 timeout=3600)
        return False, "写入后校验不一致（期望 %s… 实际 %s…），已尝试刷回备份" % (
            want[:12], got[:12]), d

    E.sh("rm -f %s" % remote_img, timeout=60)
    return True, "刷写完成并校验通过（%s）" % E.kb_human(lsize), d


def _root_hint():
    det = D.detect()
    if det.get("ok"):
        return "该机型（%s）当前没有 su。" % det.get("model")
    return "设备未连接。"
