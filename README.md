# RC 搞机工具箱（RC Gaoji Toolbox）

给 **DJI RC 系列遥控器**用的电脑端搞机工具。开源、离线、绿色（可选安装包）。

> 本工具会修改设备底层参数（CPU/GPU 频率、温控、zram/swap、分区镜像、Magisk 模块、开机动画等），
> **用错会让遥控器变砖、黑屏、丢数据、失保**。请先看完软件里的免责声明再动手。

## 机型支持

| 机型 | 型号 | 平台 | 识别 | adb 备份/直刷 | fastboot 刷写 |
|---|---|---|---|---|---|
| DJI RC 2 | rc331 | 骁龙 778G (lahaina) | ✅ | ✅（有 root 时） | ✅（BL 已解锁） |
| DJI RC Pro | RM510 | 骁龙 865 (kona) | ✅ | 需先有 root | BL 通常锁定，只能 getvar |
| DJI RC | RM520/RM500 | 骁龙 845 | ✅ | 需先有 root | ✅（BL 已解锁） |
| DJI RC Plus | RM700/RM701 | 骁龙 865 | ✅ | 需先有 root | BL 通常锁定 |
| DJI RC Pro 2 | RM510B/RM530 | 骁龙 8 Gen1 | ✅ | 需先有 root | BL 通常锁定 |

**所有机型都是先探测再下结论**：分区目录（`/dev/block/bootdevice/by-name` 或 `/dev/block/by-name`）、
root 是否存在、BL 是否解锁，全部运行时实测。某个能力不具备时会直接告诉你中文原因，
不会给你一个空列表假装"功能坏了"。

## 两个核心功能（v6.2 重做）

### 分区备份 / 下载
- 按机型列出该设备的**真实分区表**（含每个分区字节数）
- 单分区「下载」：`dd bs=4096 count=<精确块数>` → 校验大小 → `sha256sum` → `adb pull` → 本地再校验一次
- 生成同名 `.sha256` 旁文件，以后随时能验证镜像有没有坏
- 批量：只备份该机型的**关键分区**（比如 RC2 有 `dji_apk`，RC Pro 没有）

### ADB 直刷（不用切 fastboot）
- 需要 root（RC2 可用 adb-root 方案）
- 流程：**自动备份原分区 → 校验镜像大小必须等于分区大小 → `dd conv=fsync` 写入 → 回读 sha256 比对 → 不一致自动刷回备份**
- 大小不匹配直接拒绝，绝不"写一半"

其它页面：总览 / 性能（三簇分别拉满）/ 内存与虚拟内存 / 风扇温度 / Root 与模块 / 应用管理 /
刷机恢复（Fastboot + Magisk 刷 Root 四步）/ 投屏与点击控制（截图推流 + 真实触摸注入）/ 命令终端（ADB + Fastboot）/ 实用工具。

## 为什么投屏只有 1~2 帧/秒

DJI ROM 从 SELinux 层拦截了 `app_process`，scrcpy 的服务端起不来（实测连 `app_process /system/bin T` 都跑不出输出）。
所以本工具用 `adb exec-out screencap -p` 逐帧推 PNG（MJPEG），延迟约 0.5~1 秒。
**但点击/滑动是真的**：直接往 `/dev/input/event2`（himax-touchscreen）写 `sendevent` 事件，
坐标映射 `tx = y_disp, ty = 1919 - x_disp`（实测唯一正确的映射）。`input tap` 在 DJI ROM 上被静默吞掉，不可用。

## 目录

```
app/           引擎与功能（engine / devices / partops / features）
main_api.py    给界面的 HTTP API
server.py      本地 HTTP 服务（只监听 127.0.0.1）
run_app.py     启动器：tkinter 无边框宿主 + Edge --app 内嵌（去标题栏/白边）
ui/            HTML/CSS/JS 界面（真 backdrop-filter 液态玻璃）
installer/     安装程序（纯 tkinter，不依赖浏览器）
build_v4.spec  主程序打包配置
build_installer.spec  安装包配置
```

## 自己编译

```bat
python -m PyInstaller build_v4.spec --noconfirm
copy dist\\RC搞机工具箱.exe payload_build\\RCGaojiToolbox.exe
python -m PyInstaller build_installer.spec --noconfirm
```

需要 Python 3.12 + PyInstaller 6.x；运行需要 Microsoft Edge（Windows 10/11 自带）。

## 已知限制

- 投屏是"截图推流"，不是 60fps 视频流（原因见上）
- 没有 root 且 BL 锁定的机型（如未解锁的 RC Pro）只能查询，不能备份/刷写 —— 这是设备限制，不是软件 bug
- RC 系列 fastboot 基本"只写不读"（`fetch`/`oem dump`/`get_staged` 全部 unknown command），所以没法用 fastboot 抽镜像
- 不提供「回锁 BL」：DJI 遥控器回锁会直接变砖

## 免责声明

非官方工具，与 DJI 无任何关系。改机有风险，后果自负。请先备份、先看条款、先想清楚。
