# RC 搞机工具箱

插上 USB，把 DJI 遥控器当一台安卓机用：看分区、备份镜像、直接刷回去、投屏点着操作、调无人机的飞控参数。

[![release](https://img.shields.io/github/v/release/456erddgr/rc-gaoji-toolbox?label=release&color=2f81f7)](https://github.com/456erddgr/rc-gaoji-toolbox/releases/latest)
[![downloads](https://img.shields.io/github/downloads/456erddgr/rc-gaoji-toolbox/total?color=3fb950)](https://github.com/456erddgr/rc-gaoji-toolbox/releases)
[![stars](https://img.shields.io/github/stars/456erddgr/rc-gaoji-toolbox?color=f0b400)](https://github.com/456erddgr/rc-gaoji-toolbox/stargazers)
[![Windows](https://img.shields.io/badge/Windows-10%20%2F%2011-0078d4)](#)

**root 还没搞？** 那先去另一个仓库：[RC2 破解](https://github.com/456erddgr/rc2-unlock-toolkit) ——
Root ADB、9 个 Magisk 模块、原厂分区镜像都在那边。这边负责「装好之后怎么折腾」。

**[下载 v6.16](https://github.com/456erddgr/rc-gaoji-toolbox/releases/latest)** ·
[之前的版本](https://github.com/456erddgr/rc-gaoji-toolbox/releases) ·
[碰到问题](https://github.com/456erddgr/rc-gaoji-toolbox/issues) ·
[机型支持](#机型支持) ·
[图文教程](#-图文教程)

> **丑话说在前面。** 这软件会用 adb 和 root 直接改设备底层参数：CPU/GPU 频率、温控、zram 和 swap、
> 分区镜像、Magisk 模块、开机动画、飞控参数。改错了会变砖、黑屏、丢数据、失去保修。
> 每个会动系统的按钮旁边都写了后果，动手前先看完软件里的免责声明。
>
> 不碰的东西也说清楚：**改固件、去限飞、改发射功率**要重签 DJI 的包，做不到就是做不到，这里不做也不会假装做。

---

## 机型支持

| 机型 | 型号 | 平台 | 识别 | adb 备份/直刷 | fastboot 刷写 |
| --- | --- | --- | --- | --- | --- |
| DJI RC 2 | rc331 | 骁龙 778G (lahaina) | ✅ | ✅（有 root 时） | ✅（BL 已解锁） |
| DJI RC Pro | RM510 | 骁龙 865 (kona) | ✅ | 需先有 root | BL 通常锁定，只能 getvar |
| DJI RC | RM520/RM500 | 骁龙 845 | ✅ | 需先有 root | ✅（BL 已解锁） |
| DJI RC Plus | RM700/RM701 | 骁龙 865 | ✅ | 需先有 root | BL 通常锁定 |
| DJI RC Pro 2 | RM510B/RM530 | 骁龙 8 Gen1 | ✅ | 需先有 root | BL 通常锁定 |

**所有机型都是先探测再下结论**：分区目录（`/dev/block/bootdevice/by-name` 或 `/dev/block/by-name`）、root 是否存在、BL 是否解锁，全部运行时实测。某个能力不具备时会直接告诉你中文原因，不会给你一个空列表假装"功能坏了"。

---

## 🎮 v6.16：虚拟手柄真·丝滑（顺手修掉「连上却一动不动」）

### 一、先说那个更严重的 bug

以前虚拟手柄经常**连上了却一动不动**、`pad_status` 里 `count=0`、`peer=""`。
根因不在算法，在监听循环：

```python
srv.settimeout(0.5)
...
except Exception:
    break          # socket.timeout 也是 Exception → 半秒没人连，监听线程自杀
```

线程一退，内核照样完成三次握手（连接躺在 backlog 里），但永远没人 `recv`。
`netstat` 看到的就是 `LISTENING` + `CLOSE_WAIT`。修法一行：`except socket.timeout: continue`。
修完立刻 `count=48 / push_hz=227.1 / hz=9.55`。

### 二、为什么以前那么卡

老的 `_predict()` 是**三点外推**：`OVER=1.25` 允许 25% 过冲、`cap = abs(step)*0.25 + 6` 根本没钳住，
而摇杆源是 **9.6Hz 硬上限**（实测 median 102ms）。于是：外推冲出 → 回拉 → 冻住 → 下一个点瞬移，
偶尔还因为 `age > 135ms` 直接回中。离线对拍量化下来，单拍最大跳变 **539.3**。

### 三、照着你那套「遥感监测」重写

`OpenRC2-OneClick.zip` 里那套丝滑的遥感监测，**1.41 → 1.42 恰恰把三点外推废弃掉了**
（源码注释原话：会冲出、会打回）。它靠的是：

| 机制 | 参考实现 | 我们现在的做法 |
| --- | --- | --- |
| 帧间线性插值，窗口 20~45ms，走完停在真值上 | `StickSmooth.java:221-256` | `_value()`：`win` 钳 [20,60]，`u>=1` 返回最新真值 |
| 三段低通：`dd<0.004` 或 `dd>0.05` 直通，中间 `+=0.80` | `StickSmooth.java:183-188` | `_lowpass()`：同口径，零滞后但小抖不抖 |
| 三层频率解耦：9.6Hz → 控制 100Hz → 推 PC 250Hz → UI | `Radio.java:20` / `PadStream.java:26` / `RadioView.java:59` | 控制环 10ms 算低通、推流环 4ms 发手柄 |
| 断流 250ms 重置历史，不拿旧值插值 | `StickSmooth.java:147` | `GAP_RESET_MS = 250` |
| 快照原子发布，不撕裂 | `volatile int[]` 整体换引用 | `_feed()` 整帧换引用 |
| 高精度定时器 | 安卓 HandlerThread | `timeBeginPeriod(1)`（以前没有 → 实际 15.6ms 抖动） |

### 四、实测（不是估计）

真 ViGEm 虚拟手柄，源 9.6Hz 推 5 秒：

- 推流 **227Hz**（间隔 median 4.38ms / p99 5.00ms）
- **单拍最大跳变 539 → 70.7**（p99 59.6），加速度尖峰 260 → 9.70

三档预设可现场切：

| 档位 | 窗口 | 单拍最大跳变 | 与真值错位 |
| --- | --- | --- | --- |
| 低延迟 | 35ms | 169 | 107ms |
| **均衡（默认）** | 60ms | **98.4** | 124ms |
| 高平滑 | 90ms | 65.6 | 142ms |

### 五、诚实说明

- 遥控器端 `toolbox2` **目前没有 9999 发送端**（只有 40007 读 + 40008 注入）。现在流畅跑的是
  「遥控器上的 ETX 推流 + 我们 PC 端平滑」。
- 40007 的 9~10Hz 是**物理上限**，没找到更高频旁路（UDP 40009 / binder / `/dev/input` 均无证据）。

---

## 🎯 v6.15：按机型自动选参数表 + 连接体检（"真能调出数据"的版本）

### 为什么之前"显示未识别到飞机 / 能连上调不了"

真机取证找到了根子：我们原来内置的参数表是**另一台飞机**的。

- 你的飞机（DJI Mini 4 Pro）回表属性为 `crc = 0xB9B2B16E`，条数 `1433`；
- 老的内置表 `dji_params.json` 是 Lito X1（`crc = 0x5F8B2AE1`，条数 `1593`）；
- **索引全部错位** —— 同一个 index 在两张表里是完全不同的参数。所以读回来是乱值、写入更危险。

### 这一版怎么修的

1. **14 张机型参数表内置**：Mini 4 Pro / Mini 3 Pro / Mini 5 Pro / Air 2S / Air 3 / Air 3S / Mavic 3 / Mavic 3 Pro / Mavic 4 / Neo / Neo 2 / Flip / Avata 360 / 通用表。
2. **连上先读机型**：发 `0xE0` 拿到 `(crc, 条数)`，用这两个值匹配机型表，**唯一命中才用**；不确定就明确告诉你"按通用表"，绝不瞎猜。
3. **按名字解析索引**：开关、滑块、FCC 地区、恢复出厂全部改成"先按参数名在当前机型表里查索引"，查不到就**拒绝写**并如实说明，不再写死某个数字。
4. **缺项如实列出**：你这台 Mini 4 Pro 的表里没有的项（`EU_CE_Reg_MxSpeedLimit_Enable`、`support_unlimit_height` 等 7 项）会单独列在「本机型不适用的项」，**不给假开关**。
5. **连接体检**：调参前检查 `dji_link` 在不在、DJI Fly 有没有开、EdgeTX 有没有占着 40007 读口；占用了会提示"请先关掉 EdgeTX"。
6. **写入前名字核对**：写之前先用 4 字节 `0xE1` 把板子上的参数名读回来比对（板子回的是 `短名|全名`，只比 `|` 前半段），名字不一致直接拒写。

### 遥控器版 v2.28（同一个根因，一起修）

- **页面能滑动了** —— 之前整个内容区是裸 `LinearLayout`，没有 `ScrollView`。
- **不再写错参数** —— 原来把 `ce_country_type` 写死在 index 239（那是 Lito X1 的位置），Mini 4 Pro 是 509；现在按机型表解析。
- **名字核对真的生效了** —— `getInfoName()` 之前发 6 字节 payload，本飞控只认 4 字节、多出来的字节被静默忽略；已改成 4 字节。
- 参数表按机型自动切换；本机型没有的项隐藏并列出。

> ⚠️ 这一版构建、安装、API、离线选表全部验过，但飞机当时是关着的，所以"开关真读真写 / 恢复出厂 / 切 FCC 回读"要等飞机开机对频后再跑一遍。调参前请把 **DJI Fly 关掉、EdgeTX 关掉**（两者都抢 40007）。

---

## 🛰 v6.14：无人机调参（合并成一个页 · 纯电脑直连飞机 · 全中文）

侧边栏里「电脑调参」「简易调参」已经**合并**成一个页面 **「无人机调参」**，里面三个标签：

| 标签 | 做什么 |
| --- | --- |
| ① 连接飞机 | **纯电脑路线**：飞机用 USB 线**直接插电脑**就能读写飞控参数，不用遥控器、不用在遥控器上装 App |
| ② 简易调参（开关） | **59 个开关 + 20 个滑块**，分 12 组，一点就开、一关就关、一拉就变 |
| ③ 全部参数（专业） | 952 条飞控参数，可搜索、按分类筛选、批量读写 |

### 全中文（英文残留 0）
参数表来自 MIT 项目 [djiparam](https://github.com/lmdegreeds/djiparam) v0.16，原始分类是**俄文**，所以本工具自建了中文词表（15 类分类映射 + 535 个词条 + 常用短语），把参数名、分类、备注全部汉化。经自动化检查（剥掉 FCC/CE/LED/GPS/ATTI/RID 等本就该保留的缩写后查剩余英文），**残留 0 条**。

### 打开 FCC
「地区与法规」卡一键切 **美国 FCC(840) / 中国香港(344) / 俄罗斯(643)** —— 写的是飞控里的 ISO 国家码参数 `ce_country_type`。
依据是 djiparam 的 `known_toggles.tsv`：`ce_country_type`，on=840(US)、off=344(HK)/643(RU)。
⚠️ 能不能真生效取决于固件与飞机自身判定，工具写完会回读显示实际值，你自己判断。**工具不会改固件、不会伪造签名。**

### 一键恢复出厂参数
「恢复出厂参数」按钮会逐项读回当前值，**只把和默认值不一样的写回去**，然后告诉你：写回几项、几项本来就是默认、几项失败、几项没有默认值跳过。只恢复飞控参数，**不碰激活状态 / 账号 / 校准数据**。

诚实披露：`max_height` 这个参数在原表里**根本不存在**，只能用 `g_config.flying_limit.max_height` 顶替（已记在 `fc_extras.MISSING_REQUIRED`）；`EU_CE_Reg_MxSpeedLimit_Enable` 表里 `min=0/max=0`（没声明可写范围），标为**高风险**，写完必须回读确认。

### 滑块不再写坏小数
原来滑块按 1000 格线性映射，F32 小数参数（比如 `brake_sensitive_fc` 默认 0.6）一格就是 0.08 —— 轻碰一下抬手就会把 0.6 写成 0.64。现在：步长按类型选（F32 用 0.01/0.05…，整数至少 1），总量不超过 2000 格；**写入前先读回比对**，差值不足一格就跳过不写。

### 写入三重保护（一直没变）
写前核对飞机回报的参数名（不一致直接拒写）→ 原值自动备份 `out/fcparam/orig.json` → 写完回读显示实际值；`-1` 是没回包、非 0 是飞控拒绝，从不假装成功。

---

## 🎛 v6.10：飞机直连电脑调参 + 固件仓库含飞机

### 电脑调参（两条链路，页面可切换）

| 链路 | 怎么接 | 说明 |
| --- | --- | --- |
| **USB 直连飞机** | 飞机 USB 线直插电脑 → 点「扫描串口」→「直连」 | 不用经过遥控器 |
| 经遥控器 DUML 回环口 | 遥控器连电脑（开 USB 调试）→ 点「连接」 | 自动 `adb forward tcp:40007/40008` |

> ⚠️ 实测更正：飞机在 Windows 上**不是串口设备**（注册表 `SERIALCOMM` 里只有蓝牙 COM），它是 `VID_2CA3&PID_0020` 的复合设备（MI_02 = 大容量存储，MI_03~MI_07 = libusb-win32 设备），走 libusb bulk。所以「扫描串口 → 直连」这条路径在真机上找不到飞机，本工具会如实报错而不是假成功。**目前可用的稳定链路是「经遥控器 DUML 回环口」，并且需要遥控器上 DJI Fly 已连上飞机。**

- 写入三重保护：**写前核对名字**、原值自动备份、**写完回读**；`-1` 无回包 / 非 0 飞控拒绝，从不假装成功。

### 固件仓库：飞机 + 遥控器都在
- 默认列出**全部 160 个 DJI 机型条目**（Inspire 1 68 版、Phantom 3 Advanced 36、Mavic Air 2 34、Matrice 600 33、Mini 3 Pro 24……），遥控器排在前面；「只看遥控器」变成可选项。
- 「刷新目录」强制重取（缓存 12 小时）；下载前显示 SHA256 / Anti-Rollback / 更新说明，下完自带校验。
- 数据源是第三方归档站 DDD（dankdronedownloader），**不是 DJI 官方**；能否被机型接受取决于签名与 Anti-Rollback，工具只做「拿文件 + 校验 SHA256」。

---

## 🛩️ v6.5：穿越机（FPV）调参 + 驱动内置

### FPV 调参（虚拟手柄页）
- **死区**：摇杆离中点不到这个比例就回中，0.02~0.05 适合多数摇杆。
- **曲线 EXP**：中点附近变软、两端变陡；0 是线性，0.3~0.5 接近飞手手感。
- **油门限位**：右摇杆纵向最大行程，限到 0.6 就是 60% 油门。
- **一键自检**：驱动 / 端口 / 遥控器连接 / 数据速率 / 样本数 / 补帧延迟 / 调参是否生效，逐项给 ✅ 或 ⚠️。
- 说明：遥控器 DUML 侧摇杆数据上限约 9~10 Hz（实测 8.85 Hz），这是设备物理限制，工具只压缩「补帧 + 推送」这一段。

### 驱动内置（安装包自带，不用再上网找）
- 安装包内置 **ViGEmBus 1.22.0**（虚拟手柄驱动）与 **DJI 航拍驱动**（`Drivers_Win10`，含 FTDI / VCOM / WinUSB / RNDIS / RockUSB / CP210x 等 INF）。
- 装主程序时自动：**ViGEmBus 缺失就静默安装**；DJI 驱动复制到安装目录 `drivers\Drivers_Win10`。
- 跑 `RCGaojiToolbox-Setup-*.exe --drivers`（或安装完成页的按钮）会弹 UAC 提权，`pnputil /add-driver … /install`。

---

## ⚒️ v6.4：遥控器调参 / 固件信息

- **遥控器调参**（可回读、可还原）：屏幕亮度、亮度模式、息屏时间、动画倍速、触感、`adb_wifi`、常亮、`wm density`、`wm size`。每次写入前都会把原值记到 `out/rctune/orig.json`，点「全部还原」回到原样。
- **机型与固件信息**：读 `ro.product.model` / `ro.build.display.id` / `ro.build.fingerprint` / `ro.boot.slot_suffix` / `ro.boot.verifiedbootstate` 等，判断机型与固件版本、槽位、BL 锁状态。
- **固件说明（重要）**：DJI 固件是签名包，第三方无法重新签名，所以本工具**不代刷固件**。我们做的是：① 显示当前机型与固件版本 ② 一键打开对应机型的官方下载页 ③ 校验你手上的固件包（大小 / sha256 / 头部 magic）。
- 官方固件接口 `firmware-dl.djicorp.com` 在本机网络下 DNS 无法解析（2026-11-02 实测），所以没有走「直接拉固件列表」这条路。

---

## 🔧 两个核心功能（v6.2 重做）

### 分区备份 / 下载
- 按机型列出该设备的**真实分区表**（含每个分区字节数）
- 单分区「下载」：`dd bs=4096 count=<精确块数>` → 校验大小 → `sha256sum` → `adb pull` → 本地再校验一次
- 生成同名 `.sha256` 旁文件，以后随时能验证镜像有没有坏
- 批量：只备份该机型的**关键分区**（比如 RC2 有 `dji_apk`，RC Pro 没有）

### ADB 直刷（不用切 fastboot）
- 需要 root（RC2 可用 adb-root 方案）
- 流程：**自动备份原分区 → 校验镜像大小必须等于分区大小 → `dd conv=fsync` 写入 → 回读 sha256 比对 → 不一致自动刷回备份**
- 大小不匹配直接拒绝，绝不"写一半"

其它页面：总览 / 性能（三簇分别拉满）/ 内存与虚拟内存 / 风扇温度 / Root 与模块 / 应用管理 / 刷机恢复（Fastboot + Magisk 刷 Root 四步）/ 投屏与点击控制 / 命令终端（ADB + Fastboot）/ 实用工具。

### 为什么投屏只有 1~2 帧/秒
DJI ROM 从 SELinux 层拦截了 `app_process`，scrcpy 的服务端起不来（实测连 `app_process /system/bin T` 都跑不出输出）。所以 RC2 只能用 `adb exec-out screencap -p` 逐帧推 PNG，延迟约 0.5~1 秒。

**但点击/滑动是真的**：直接往 `/dev/input/event2`（himax-touchscreen）写 `sendevent` 事件，坐标映射 `tx = y_disp, ty = 1919 - x_disp`（实测唯一正确的映射）。`input tap` 在 DJI ROM 上被静默吞掉，不可用。

---

## 📖 图文教程

### 1. 分区备份（ADB 就能用，不用切 fastboot）
![分区备份](docs/screens/partition.png)

1. USB 连上遥控器，确认「设备状态」显示已连接、有 root；
2. 进「分区备份」页，会按机型自动列出分区（带大小）；
3. 点某个分区的「备份」→ 写到遥控器 `/data/local/tmp/rc2part/`，再用「下载」拉到电脑；
4. 每个备份都会生成同名 `.sha256`，方便校验。

### 2. ADB 直刷分区
同一个分区行上点「刷入」→ 选镜像 → 工具会：先自动备份 → 校验「镜像大小 == 分区大小」→ 写入 → 回读 sha256 → 不一致自动刷回备份。

### 3. 投屏（两种模式）
![投屏](docs/screens/mirror.png)

- **scrcpy 真视频流**：RC Pro / RC Pro 2 / RC Plus / RC1 可用（这些机型不拦 `app_process`）；
- **截图推流（兼容）**：RC2 只能用这个，约 1~2 帧/秒，但点击、滑动是真的注入（`/dev/input/event2`）。
- 「自动」模式会先探测，能 scrcpy 就用 scrcpy，不能用就退回推流。

### 4. 虚拟手柄（遥控器变 Xbox 360 手柄）
![虚拟手柄](docs/screens/pad.png)

1. 电脑装 **ViGEmBus** 驱动（安装程序会检测；没有会提示下载地址）；
2. 点「开始」→ 自动 `adb reverse tcp:9999 tcp:9999` 并监听 127.0.0.1:9999；
3. 遥控器端把摇杆流指向 `127.0.0.1:9999`，每行一个 JSON：`{"ax":[1024,1024,1024,1024,1024,1024]}`；
4. 电脑上出现一个 Xbox 360 手柄，游戏里直接用。
5. 延迟档位：LOW / MID / HIGH（外推补偿不同，源是 9~10Hz 的 DUML 摇杆帧，一拍约 100ms，本工具只压补帧与推送段）。

### 5. ADB Root（只把 adb 提权，不改任何分区、不动数据）
「Root/模块」页 → 「ADB Root」卡 → 开启：把 `adbd-root` 与注入脚本推到 `/data/adb-persist/rc-adbroot` 并执行，让 adbd 以 root 身份跑（`--root_seclabel=u:r:su:s0`）；完全不动 boot / dji_apk / super 等任何分区，「恢复」按钮一键回到原状。

---

## 目录

```
app/           引擎与功能（engine / devices / partops / features / fcparam / fcquick / fc_models / duml）
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
copy dist\RC搞机工具箱.exe payload_build\RCGaojiToolbox.exe
python -m PyInstaller build_installer.spec --noconfirm
```

需要 Python 3.12 + PyInstaller 6.x；运行需要 Microsoft Edge（Windows 10/11 自带）。

## 已知限制

- 投屏是"截图推流"，不是 60fps 视频流（原因见上）
- 没有 root 且 BL 锁定的机型（如未解锁的 RC Pro）只能查询，不能备份/刷写 —— 这是设备限制，不是软件 bug
- RC 系列 fastboot 基本"只写不读"（`fetch`/`oem dump`/`get_staged` 全部 unknown command），所以没法用 fastboot 抽镜像
- 飞机 USB 直连（libusb bulk）尚未跑通，目前请走"经遥控器 DUML 回环口"
- 不提供「回锁 BL」：DJI 遥控器回锁会直接变砖

## 免责声明

非官方工具，与 DJI 无任何关系。改机有风险，后果自负。请先备份、先看条款、先想清楚。
