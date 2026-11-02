/* RC 搞机工具箱 - 前端逻辑 */
'use strict';

const API_BASE = '/api/';

/* ---------- 日志 ---------- */
const logBody = () => document.getElementById('logBody');
function log(msg, level = 'info') {
  const box = logBody();
  if (!box) return;
  const t = new Date().toTimeString().slice(0, 8);
  const div = document.createElement('div');
  div.className = 'log-line log-' + level;
  div.innerHTML = '<span class="log-ts">' + t + '</span>' + esc(msg);
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  while (box.childNodes.length > 500) box.removeChild(box.firstChild);
}
function esc(s) {
  return String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

/* ---------- Toast ---------- */
function toast(msg, kind = '') {
  let wrap = document.getElementById('toastWrap');
  if (!wrap) {
    wrap = document.createElement('div');
    wrap.id = 'toastWrap';
    document.body.appendChild(wrap);
  }
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.textContent = msg;
  wrap.appendChild(t);
  setTimeout(() => {
    t.classList.add('out');
    setTimeout(() => t.remove(), 320);
  }, 2600);
}

/* ---------- 工具 ---------- */
function kbHuman(kb) {
  kb = Number(kb) || 0;
  if (kb < 1024) return kb + ' KB';
  if (kb < 1048576) return (kb / 1024).toFixed(1) + ' MB';
  return (kb / 1048576).toFixed(2) + ' GB';
}
function tmpColor(t) {
  if (t == null) return 'green';
  if (t < 50) return 'green';
  if (t < 65) return 'orange';
  return 'red';
}
function pctColor(p) {
  if (p > 30) return 'green';
  if (p > 15) return 'orange';
  return 'red';
}
async function call(method, ...args) {
  // ★ 双通道：优先 pywebview 原生通道（file:// 下 fetch 会永久挂起导致卡死）
  try {
    const wv = window.pywebview && window.pywebview.api;
    if (wv && typeof wv[method] === 'function') {
      const raw = await wv[method](...args);
      return typeof raw === 'string' ? JSON.parse(raw) : raw;
    }
  } catch (e) {
    log('原生通道失败 ' + method + ': ' + e, 'err');
  }
  // 兜底：HTTP（仅 Edge --app 模式可用）
  try {
    const resp = await fetch(API_BASE + method, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ args: args }),
      signal: AbortSignal.timeout(20000)
    });
    const raw = await resp.text();
    return JSON.parse(raw);
  } catch (e) {
    log('调用失败 ' + method + ': ' + e, 'err');
    return null;
  }
}

/* ---------- 页面注册表 ---------- */
const PAGES = [
  { id: 'overview', name: '总览', ico: '◈', render: renderOverview },
  { id: 'perf', name: '性能', ico: '⚡', render: renderPerf },
  { id: 'memory', name: '内存/虚拟内存', ico: '▤', render: renderMemory },
  { id: 'fan', name: '风扇/温度', ico: '❄', render: renderFan },
  { id: 'root', name: 'Root/模块', ico: '⚿', render: renderRoot },
  { id: 'apps', name: '应用管理', ico: '▦', render: renderApps },
  { id: 'backup', name: '分区备份', ico: '⛁', render: renderBackup },
  { id: 'flash', name: '刷机/恢复', ico: '⚙', render: renderFlash },
  { id: 'screen', name: '投屏/截图', ico: '▣', render: renderMirrorV2 },
  { id: 'pad', name: '虚拟手柄', ico: '⊛', render: renderPad },
  { id: 'term', name: '命令终端', ico: '⌨', render: renderTerm },
  { id: 'tools', name: '实用工具', ico: '✳', render: renderTools },
  { id: 'about', name: '关于/免责', ico: 'ⓘ', render: renderAbout },
];

let curPage = 'overview';

/* ---------- 侧栏 ---------- */
function buildSidebar() {
  const sb = document.getElementById('sidebar');
  sb.innerHTML = '';
  PAGES.forEach(p => {
    const d = document.createElement('div');
    d.className = 'nav-item' + (p.id === curPage ? ' active' : '');
    d.innerHTML = '<span class="nav-ico">' + p.ico + '</span><span>' + p.name + '</span>';
    d.onclick = () => go(p.id);
    d.dataset.id = p.id;
    sb.appendChild(d);
  });
}

function go(id) {
  curPage = id;
  document.querySelectorAll('.nav-item').forEach(n => {
    n.classList.toggle('active', n.dataset.id === id);
  });
  const wrap = document.getElementById('pageWrap');
  wrap.innerHTML = '';
  const page = PAGES.find(p => p.id === id);
  if (page && page.render) {
    try { page.render(wrap); } catch (e) { wrap.innerHTML = '<div class="empty">页面渲染失败: ' + esc(e.message) + '</div>'; }
  }
}

/* ---------- 通用片段 ---------- */
function card(title, inner, extra = '') {
  return '<div class="glass card ' + extra + '">' +
    (title ? '<div class="card-title">' + title + '</div>' : '') +
    inner + '</div>';
}
function stat(label, value, sub = '', color = '') {
  return '<div class="stat">' +
    '<div class="stat-label">' + label + '</div>' +
    '<div class="stat-value ' + color + '">' + value + '</div>' +
    (sub ? '<div class="stat-sub">' + sub + '</div>' : '') +
    '</div>';
}
function pageHead(title, desc) {
  return '<div class="page-title">' + title + '</div>' +
    '<div class="page-desc">' + desc + '</div>';
}

/* ================= 页面：总览 ================= */
async function renderOverview(wrap) {
  wrap.innerHTML = pageHead('总览', '设备状态一览') +
    '<div id="ovBody"><div class="empty"><div class="empty-ico">◌</div>读取中…</div></div>';
  const d = await call('device_info');
  const box = document.getElementById('ovBody');
  if (!box) return;
  if (!d || !d.ok) {
    box.innerHTML = card('设备', '<div class="empty"><div class="empty-ico">⊘</div>' +
      '未检测到设备<br><span style="font-size:12px">请插 USB 并开启 USB 调试</span></div>');
    log('未检测到设备', 'warn');
    return;
  }
  const memPct = d.mem.total ? Math.round(d.mem.available * 100 / d.mem.total) : 0;
  const mc = pctColor(memPct);
  box.innerHTML =
    card('设备信息',
      '<div style="font-size:26px;font-weight:800;letter-spacing:-.6px;margin-bottom:6px">' +
        esc(d.model) + '</div>' +
      '<div style="font-size:12.5px;color:var(--txt2)">Android ' + esc(d.android) +
        ' &nbsp;·&nbsp; ' + esc(d.abi) + ' &nbsp;·&nbsp; ' + esc(d.serial) +
        ' &nbsp;·&nbsp; ' + (d.root ? '<span style="color:var(--green)">已 Root</span>'
                                    : '<span style="color:var(--red)">未 Root</span>') +
      '</div>') +
    card('实时状态',
      '<div class="stat-grid">' +
        stat('可用内存', kbHuman(d.mem.available), '共 ' + kbHuman(d.mem.total), mc) +
        stat('CPU', (d.cpu_freq || '-') + ' MHz',
             (d.cpu_temp ? d.cpu_temp + '℃' : '') , tmpColor(d.cpu_temp)) +
        stat('GPU', (d.gpu || '-') + ' MHz', '', 'purple') +
        stat('电池', (d.battery.pct || '-') + '%', d.battery.status || '', 'green') +
        stat('调度策略', d.governor || '-', '', 'cyan') +
      '</div>' +
      '<div style="margin-top:16px"><div class="bar"><div class="bar-fill ' + mc +
        '" style="width:' + memPct + '%"></div></div></div>') +
    card('快捷操作',
      '<div class="btn-row">' +
        '<button class="btn" onclick="scanDevice()">扫描设备</button>' +
        '<button class="btn" onclick="doRefresh()">刷新数据</button>' +
        '<button class="btn orange" onclick="perfSet(\'perf\')">性能模式</button>' +
        '<button class="btn green" onclick="doDropCaches()">释放内存</button>' +
        '<button class="btn red" onclick="doReboot()">重启设备</button>' +
      '</div>' +
      '<div class="tip info" style="margin-top:14px">CPU 三簇上限：小核 1.96G / 大核 2.40G / 超大核 2.71G</div>');
  log('总览已加载', 'ok');
}

async function scanDevice() {
  toast('正在扫描设备…');
  log('正在扫描设备（会重启 adb 服务）…', 'dim');
  const r = await call('scan_device');
  if (!r || !r.ok) {
    toast('扫描失败');
    log('扫描失败', 'err');
    return;
  }
  log(r.log || '', 'dim');
  if (r.mode === 'adb') {
    toast('已连接 ' + r.serial);
    log('ADB 已连接：' + r.serial, 'ok');
  } else if (r.mode === 'fastboot') {
    toast('Fastboot 模式：' + r.serial);
    log('Fastboot 已连接：' + r.serial, 'ok');
  } else {
    toast('没有发现设备');
    log('没有发现设备：请检查 USB 线、遥控器是否开机、USB 调试是否打开', 'err');
  }
  await pollStatus();
}

async function doRefresh() { go('overview'); toast('已刷新'); }
async function doDropCaches() {
  const r = await call('drop_caches');
  if (r && r.ok) { toast('内存缓存已释放', 'ok'); log('已释放内存缓存', 'ok'); }
  else { toast('释放失败', 'err'); log('释放失败: ' + (r ? r.msg : '?'), 'err'); }
}
async function doReboot() {
  if (!confirm('确定重启设备吗？')) return;
  await call('reboot_device');
  toast('已发送重启指令');
  log('已发送重启命令', 'warn');
}

/* ================= 页面：性能 ================= */
async function renderPerf(wrap) {
  wrap.innerHTML = pageHead('性能', 'CPU / GPU 频率与调度控制') +
    '<div id="perfBody"><div class="empty">读取中…</div></div>';
  const d = await call('perf_status');
  const box = document.getElementById('perfBody');
  if (!box) return;
  const p = (d && d.ok) ? d : {};
  box.innerHTML =
    card('当前状态',
      '<div class="stat-grid">' +
        stat('调度策略', p.governor || '-', '', 'cyan') +
        stat('小核上限', (p.cpu0 || '-') + ' MHz', '', 'blue') +
        stat('大核上限', (p.cpu4 || '-') + ' MHz', '', 'blue') +
        stat('超大核上限', (p.cpu7 || '-') + ' MHz', '', 'blue') +
        stat('当前频率', (p.cur || '-') + ' MHz', '', 'green') +
        stat('GPU 上限', (p.gpu || '-') + ' MHz', '', 'purple') +
      '</div>') +
    card('性能模式',
      '<div class="btn-row">' +
        '<button class="btn green" onclick="perfSet(\'save\')">省电</button>' +
        '<button class="btn" onclick="perfSet(\'bal\')">均衡</button>' +
        '<button class="btn orange" onclick="perfSet(\'perf\')">性能</button>' +
        '<button class="btn red" onclick="perfSet(\'ext\')">极速</button>' +
      '</div>' +
      '<div style="margin-top:14px;font-size:12px;color:var(--txt3);line-height:1.8">' +
        '省电：schedutil + GPU 最低 &nbsp;|&nbsp; 均衡：schedutil + GPU 最高<br>' +
        '性能：performance + 三簇拉满 &nbsp;|&nbsp; 极速：拉满 + 解温控（会热）' +
      '</div>' +
      '<div class="tip">极速模式会关闭温控保护，长时间使用请留意温度</div>');
  log('性能页已加载');
}

async function perfSet(level) {
  const names = { save: '省电', bal: '均衡', perf: '性能', ext: '极速' };
  log('切换「' + names[level] + '」模式…', 'hdr');
  toast('正在切换「' + names[level] + '」…');
  const r = await call('perf_set', level);
  if (r && r.ok) {
    toast('「' + names[level] + '」已生效', 'ok');
    log('  CPU: ' + (r.cpu0 || '?') + ' / ' + (r.cpu4 || '?') + ' / ' + (r.cpu7 || '?'), 'ok');
    log('  GPU: ' + (r.gpu || '?') + ' MHz', 'ok');
    if (curPage === 'perf') renderPerf(document.getElementById('pageWrap'));
  } else {
    toast('切换失败', 'err');
    log('切换失败: ' + (r ? r.msg : '未知'), 'err');
  }
}

/* ================= 页面：内存/虚拟内存 ================= */
async function renderMemory(wrap) {
  wrap.innerHTML = pageHead('内存 / 虚拟内存', '查看与调整内存策略') +
    '<div id="memBody"><div class="empty">读取中…</div></div>';
  const d = await call('mem_status');
  const box = document.getElementById('memBody');
  if (!box) return;
  const m = (d && d.ok) ? d : { mem: {}, swaps: [] };
  const mem = m.mem || {};
  const pct = mem.total ? Math.round(mem.available * 100 / mem.total) : 0;
  let swapRows = '';
  (m.swaps || []).forEach(s => {
    const up = s.size ? Math.round(s.used * 100 / s.size) : 0;
    swapRows += '<div class="list-row"><span class="name">' +
      (s.file.indexOf('zram') >= 0 ? 'zram（优先）' : '磁盘 swap') +
      '</span><span class="meta">' + kbHuman(s.size) + ' · 用 ' +
      kbHuman(s.used) + ' (' + up + '%) · 优先级 ' + s.prio + '</span></div>';
  });
  if (!swapRows) swapRows = '<div class="empty">未启用 swap</div>';

  box.innerHTML =
    card('内存', '<div class="stat-grid">' +
      stat('可用内存', kbHuman(mem.available),
           '共 ' + kbHuman(mem.total), pctColor(pct)) +
      stat('swap 总计', kbHuman(mem.swap_total), '', 'purple') +
      stat('swap 已用', kbHuman(mem.swap_total - mem.swap_free), '', 'orange') +
      '</div>' +
      '<div style="margin-top:16px"><div class="bar"><div class="bar-fill ' +
      pctColor(pct) + '" style="width:' + pct + '%"></div></div></div>') +
    card('swap 明细', swapRows) +
    card('虚拟内存使用倾向（swappiness）',
      '<div style="display:flex;align-items:baseline;gap:10px">' +
        '<div id="swVal" style="font-size:32px;font-weight:800;color:var(--orange)">' +
          (m.swappiness || 60) + '</div>' +
        '<div style="font-size:12px;color:var(--txt3)">/ 100（内核上限）</div>' +
      '</div>' +
      '<input type="range" class="slider" id="swSlider" min="0" max="100" value="' +
        (m.swappiness || 60) + '" oninput="document.getElementById(\'swVal\').textContent=this.value">' +
      '<div style="font-size:11.5px;color:var(--txt3);line-height:1.75;margin-top:6px">' +
        '低 = 少用虚拟内存，多用真实内存（更快，但内存紧张）<br>' +
        '高 = 积极换出到 swap（真实内存宽松，但 IO 增多）</div>' +
      '<div class="btn-row" style="margin-top:14px">' +
        '<button class="btn" onclick="applySwappiness()">应用并生效</button>' +
        '<button class="btn green" onclick="doDropCaches()">释放缓存</button>' +
      '</div>') +
    card('zram 容量',
      '<div style="font-size:16px;font-weight:700;color:var(--purple);margin-bottom:10px">' +
        (m.zram_mb || '-') + ' MB（当前）</div>' +
      '<input type="range" class="slider" id="zramSlider" min="256" max="6144" step="64" value="' +
        (m.zram_mb || 2048) + '" oninput="document.getElementById(\'zramVal\').textContent=this.value+\' MB\'">' +
      '<div id="zramVal" style="font-size:12px;color:var(--txt2)">' + (m.zram_mb || 2048) + ' MB</div>' +
      '<div class="btn-row" style="margin-top:12px">' +
        '<button class="btn purple" onclick="applyZram()">应用 zram 容量</button>' +
      '</div>' +
      '<div class="tip danger">★ 绝不要关闭 zram 后不重新开启，会导致系统卡死</div>');
  log('内存页已加载');

  const sl = document.getElementById('swSlider');
  if (sl) sl.oninput = function () {
    const v = document.getElementById('swVal');
    if (v) v.textContent = this.value;
  };
}

async function applySwappiness() {
  const el = document.getElementById('swSlider');
  if (!el) return;
  const v = parseInt(el.value, 10);
  log('设置 swappiness = ' + v + ' …', 'hdr');
  const r = await call('set_swappiness', v);
  if (r && r.ok) { toast('swappiness = ' + r.value, 'ok'); log('已生效: ' + r.value, 'ok'); }
  else { toast('设置失败', 'err'); log('设置失败: ' + (r ? r.msg : '?'), 'err'); }
}

async function applyZram() {
  const el = document.getElementById('zramSlider');
  if (!el) return;
  const mb = parseInt(el.value, 10);
  if (!confirm('调整 zram 到 ' + mb + ' MB？\n期间 swap 会短暂中断约 5-10 秒。')) return;
  log('调整 zram 到 ' + mb + ' MB …', 'hdr');
  toast('正在调整 zram…');
  const r = await call('resize_zram', mb);
  if (r && r.ok) { toast('zram 已设为 ' + r.mb + ' MB', 'ok'); log('zram OK: ' + r.mb + ' MB', 'ok'); }
  else { toast('zram 调整失败', 'err'); log('失败: ' + (r ? r.msg : '?'), 'err'); }
}

/* ================= 页面：风扇/温度 ================= */
async function renderFan(wrap) {
  wrap.innerHTML = pageHead('风扇 / 温度', '硬件温度监控') +
    '<div id="fanBody"><div class="empty">读取中…</div></div>';
  const d = await call('fan_status');
  const box = document.getElementById('fanBody');
  if (!box) return;
  let rows = '';
  ((d && d.zones) || []).forEach(z => {
    rows += '<div class="list-row"><span class="name">thermal_zone' + z[0] +
      '</span><span class="meta" style="color:var(--' + tmpColor(z[1]) +
      ');font-weight:700;font-size:15px">' + z[1] + '℃</span></div>';
  });
  if (!rows) rows = '<div class="empty">读不到温度传感器</div>';
  box.innerHTML =
    card('温度', rows) +
    card('风扇状态',
      '<div style="font-size:13px;line-height:2;color:var(--txt2)">' +
      '驱动：<span style="color:var(--green)">' + esc((d && d.driver) || '-') + '</span><br>' +
      '调速方式：<span style="color:var(--cyan)">内核 thermal-engine 自动</span>' +
      '</div>' +
      '<div class="tip" style="margin-top:14px">' +
        '实测结论：本机风扇由内核 pwm-fan 驱动独占控制。<br>' +
        '· pwmchip4 ch0（风扇）export 返回 1，用户空间无法操作<br>' +
        '· cooling_device 0-22 里没有 fan 类型<br>' +
        '· 风扇由内核根据温度自动调速<br><br>' +
        '所以本工具只做温度监控，不提供「手动调速」——因为做不到。' +
      '</div>' +
      '<div class="tip danger">★ pwmchip0 ch3 是屏幕背光，绝不能碰（unexport 会黑屏）</div>' +
      '<div class="btn-row" style="margin-top:14px">' +
        '<button class="btn" onclick="renderFan(document.getElementById(\'pageWrap\'))">刷新温度</button>' +
        '<button class="btn red" onclick="doFixScreen()">黑屏急救</button>' +
      '</div>');
  log('风扇页已加载');
}

async function doFixScreen() {
  if (!confirm('只有在屏幕黑掉（背光被误关）时才需要。继续？')) return;
  const r = await call('backlight_fix');
  if (r && r.ok) { toast('背光已恢复', 'ok'); log('背光已恢复: ' + (r.msg || ''), 'ok'); }
  else { toast('执行失败', 'err'); }
}

/* ================= 页面：Root/模块 ================= */
async function renderRoot(wrap) {
  wrap.innerHTML = pageHead('Root / 模块', '权限与 Magisk 管理') +
    '<div id="rootBody"><div class="empty">读取中…</div></div>';
  const [rs, ms] = await Promise.all([call('root_status'), call('list_modules')]);
  const box = document.getElementById('rootBody');
  if (!box) return;
  const r = (rs && rs.ok) ? rs : {};
  let modRows = '';
  ((ms && ms.modules) || []).forEach(m => {
    modRows += '<div class="list-row"><span class="name">' + esc(m.name) + '</span>' +
      '<span class="meta" style="color:var(--' + (m.disabled ? 'txt3' : 'green') + ')">' +
      (m.disabled ? '已停用' : '启用中') + '</span></div>';
  });
  if (!modRows) modRows = '<div class="empty">没有读到模块</div>';

  box.innerHTML =
    card('Root 状态',
      '<div class="stat-grid">' +
        stat('Root', r.has_root ? '可用' : '不可用', '', r.has_root ? 'green' : 'red') +
        stat('su 路径', '<span style="font-size:12px">' + esc(r.su_path || '未找到') + '</span>', '', 'cyan') +
        stat('Magisk', r.magisk || '-', '', 'purple') +
      '</div>' +
      '<div class="btn-row" style="margin-top:16px">' +
        '<button class="btn" onclick="renderRoot(document.getElementById(\'pageWrap\'))">重新检测</button>' +
        '<button class="btn orange" onclick="doRootAdb()">一键开启 adb root</button>' +
      '</div>') +
    card('Magisk 模块（' + ((ms && ms.modules) || []).length + '）', modRows) +
    card('说明',
      '<div style="font-size:12.5px;color:var(--txt2);line-height:1.9">' +
      '· 本工具用绝对路径 /debug_ramdisk/su —— 这是旧版所有功能失效的根因<br>' +
      '· 模块停用后需重启生效<br>' +
      '· 紧急时可在 recovery 里删 /data/adb/modules/模块名' +
      '</div>');
  log('Root 页已加载，root=' + (r.has_root ? '是' : '否'));
}

async function doRootAdb() {
  log('正在开启 adb root…', 'hdr');
  const r = await call('root_adb');
  if (r && r.ok) { toast('adb root 已开启', 'ok'); log(r.msg || 'OK', 'ok'); }
  else { toast('开启失败', 'err'); log((r && r.msg) || '失败', 'err'); }
}

/* ================= 页面：应用管理 ================= */
async function renderApps(wrap) {
  wrap.innerHTML = pageHead('应用管理', '第三方应用列表') +
    '<div id="appsBody"><div class="empty">读取中…</div></div>';
  const d = await call('list_apps');
  const box = document.getElementById('appsBody');
  if (!box) return;
  const apps = (d && d.apps) || [];
  let rows = '';
  apps.forEach(a => {
    rows += '<div class="list-row">' +
      '<span class="name">' + esc(a.pkg) + '</span>' +
      '<span style="display:flex;gap:8px;align-items:center">' +
      (a.disabled ? '<span class="meta" style="color:var(--txt3)">已停用</span>' : '') +
      '<span class="meta">v' + esc(a.version || '-') + '</span>' +
      '<button class="btn ghost sm" onclick="appPull(\'' + esc(a.pkg) + '\')">导出</button>' +
      '<button class="btn ghost sm" onclick="appUninstall(\'' + esc(a.pkg) + '\')">卸载</button>' +
      '</span></div>';
  });
  if (!rows) rows = '<div class="empty">没有第三方应用</div>';
  box.innerHTML = card('已安装应用（' + apps.length + '）',
    '<div class="list">' + rows + '</div>' +
    '<div class="btn-row" style="margin-top:14px">' +
      '<button class="btn" onclick="renderApps(document.getElementById(\'pageWrap\'))">刷新列表</button>' +
      '<button class="btn green" onclick="doInstallApk()">安装 APK</button>' +
    '</div>');
  log('应用列表: ' + apps.length + ' 个');
}

async function appPull(pkg) {
  log('导出 ' + pkg + ' …', 'hdr');
  const r = await call('pull_apk', pkg);
  if (r && r.ok) { toast('已导出', 'ok'); log('保存到: ' + r.path, 'ok'); }
  else { toast('导出失败', 'err'); log((r && r.msg) || '失败', 'err'); }
}

async function appUninstall(pkg) {
  if (!confirm('确定卸载 ' + pkg + ' ?')) return;
  const r = await call('uninstall_app', pkg);
  if (r && r.ok) { toast('已卸载', 'ok'); log('卸载成功: ' + pkg, 'ok');
    renderApps(document.getElementById('pageWrap')); }
  else { toast('卸载失败', 'err'); log((r && r.msg) || '失败', 'err'); }
}

async function doInstallApk() {
  const r = await call('pick_install_apk');
  if (!r || !r.ok) { if (r && r.msg) log(r.msg, 'warn'); return; }
  toast('正在安装…');
  log('安装: ' + r.path, 'hdr');
  const r2 = await call('install_apk', r.path);
  if (r2 && r2.ok) { toast('安装成功', 'ok'); log('安装成功', 'ok'); }
  else { toast('安装失败', 'err'); log((r2 && r2.msg) || '失败', 'err'); }
}

/* ================= 页面：分区备份（多机型 + adb 下载 + adb 直刷） ================= */
let partCache = [];

async function renderBackup(wrap) {
  wrap.innerHTML = pageHead('分区备份', '按机型识别分区，备份 / 下载 / 直刷') +
    '<div id="bakBody"><div class="empty">读取中…</div></div>';
  await bakRefresh();
}

function capRow(k, label, ok, hint) {
  const color = ok ? 'var(--green)' : 'var(--red)';
  const mark = ok ? '✓' : '✕';
  return '<div style="display:flex;gap:10px;align-items:baseline;font-size:13px;padding:3px 0">' +
    '<span style="color:' + color + ';width:14px">' + mark + '</span>' +
    '<span style="width:150px;color:var(--txt2)">' + esc(label) + '</span>' +
    '<span style="color:var(--txt3);font-size:12px">' + esc(hint || '') + '</span></div>';
}

async function bakRefresh() {
  const box = document.getElementById('bakBody');
  if (!box) return;
  const d = await call('partition_info');
  const prof = await call('device_profile');
  if (!d || !d.ok) {
    box.innerHTML = card('状态', '<div class="tip danger">' + esc((d && d.err) || '读取失败') + '</div>');
    return;
  }
  partCache = d.parts || [];
  const caps = d.caps || {};
  const model = d.model || ((prof && prof.model) || '未连接');

  if (!d.connected) {
    box.innerHTML = card('设备未连接',
      '<div class="tip danger">没有检测到遥控器。请用 USB 连接，或在遥控器上打开无线调试后点刷新。</div>' +
      '<div class="btn-row"><button class="btn" onclick="bakRefresh()">刷新</button></div>');
    return;
  }

  const fbName = (prof && prof.profile_name) || '';
  const soc = (prof && prof.soc) || '';
  const reasons = (d.reasons || []).map(r => '<div style="font-size:12.5px;color:var(--orange);padding:2px 0">· ' + esc(r) + '</div>').join('');

  const listRows = partCache.map(p => {
    const sz = p.size_h || (p.size ? kbHuman(p.size / 1024) : '');
    const star = p.key ? '<span style="color:var(--orange)">★</span> ' : '';
    const dlBtn = caps.backup
      ? '<button class="btn ghost" style="padding:3px 10px;font-size:12px" onclick="bakDownload(\'' + p.name + '\')">下载</button>'
      : '<span style="font-size:11.5px;color:var(--txt3)">无 root</span>';
    const flBtn = (caps.flash_adb && p.flashable)
      ? '<button class="btn red" style="padding:3px 10px;font-size:12px" onclick="bakFlash(\'' + p.name + '\')">刷入</button>'
      : '';
    return '<tr><td style="padding:5px 8px">' + star + esc(p.name) + '</td>' +
      '<td style="padding:5px 8px;color:var(--txt3);text-align:right">' + esc(sz) + '</td>' +
      '<td style="padding:5px 8px;text-align:right;white-space:nowrap">' + dlBtn + ' ' + flBtn + '</td></tr>';
  }).join('');

  box.innerHTML =
    card('机型与能力',
      '<div style="font-size:15px;font-weight:700;margin-bottom:2px">' + esc(model) + '</div>' +
      '<div style="font-size:12px;color:var(--txt3);margin-bottom:12px">' +
        esc([fbName, soc, d.byname].filter(Boolean).join(' · ')) + '</div>' +
      capRow('root', 'Root 权限', caps.root, caps.root ? '可以读写块设备' : '备份/刷写不可用') +
      capRow('by-name', '分区目录', caps.byname, d.byname || '未找到') +
      capRow('backup', '备份 / 下载分区', caps.backup, caps.backup ? 'dd 读取 + sha256 校验' : '需要 root') +
      capRow('flash_adb', 'ADB 直刷分区', caps.flash_adb, caps.flash_adb ? '不用切 fastboot，先自动备份' : '需要 root') +
      capRow('flash_fastboot', 'Fastboot 刷写', caps.flash_fastboot, caps.flash_fastboot ? 'BL 已解锁' : 'BL 未解锁，只能 getvar') +
      (reasons ? '<div style="margin-top:10px">' + reasons + '</div>' : '')) +
    card('批量操作',
      '<div class="btn-row">' +
        '<button class="btn blue" onclick="bakRefresh()">刷新</button>' +
        '<button class="btn" onclick="doBackup(false)">备份关键分区</button>' +
        '<button class="btn green" onclick="doBackup(true)">备份并拉到电脑</button>' +
        '<button class="btn ghost" onclick="openOutDir()">打开备份目录</button>' +
      '</div>' +
      '<div class="tip danger" style="margin-top:12px">' +
      '★ 每个分区都先算大小、dd 精确 count、再比 sha256，任何一步不对就报错，不会给你一个坏文件<br>' +
      '★ 下载的文件在 输出目录/partitions/，同名 .sha256 旁文件可用来以后校验</div>') +
    card('分区清单（' + partCache.length + ' 个，★=该机型关键分区）',
      '<div style="max-height:420px;overflow-y:auto">' +
      '<table style="width:100%;border-collapse:collapse;font-size:13px">' +
      '<thead><tr style="color:var(--txt3);font-size:12px">' +
      '<th style="text-align:left;padding:4px 8px">分区</th>' +
      '<th style="text-align:right;padding:4px 8px">大小</th>' +
      '<th style="text-align:right;padding:4px 8px">操作</th></tr></thead>' +
      '<tbody>' + listRows + '</tbody></table></div>' +
      (d.err ? '<div class="tip danger" style="margin-top:10px">' + esc(d.err) + '</div>' : ''));

  log('分区清单: ' + partCache.length + ' 个 · ' + model);
}

async function bakDownload(name) {
  toast('正在备份并下载 ' + name + ' …');
  log('===== 下载分区 ' + name + ' =====', 'hdr');
  const r = await call('download_partition', name, false);
  if (r && r.ok) {
    toast(name + ' 下载完成', 'ok');
    log('  ' + r.size_h + ' → ' + r.path, 'ok');
  } else {
    toast('下载失败', 'err');
    log('  失败: ' + ((r && r.msg) || '未知'), 'err');
  }
}

async function bakFlash(name) {
  const img = await call('pick_image');
  if (!img || !img.ok) return;
  if (!confirm('把\n' + img.path + '\n刷进 ' + name + ' 分区？\n\n会先自动备份原分区，写入后回读校验；校验不通过会自动刷回。')) return;
  toast('正在刷入 ' + name + ' …');
  log('===== adb 直刷 ' + name + ' =====', 'hdr');
  const r = await call('flash_partition_adb', name, img.path);
  if (r && r.ok) {
    toast(name + ' 刷写完成', 'ok');
    log('  ' + r.msg, 'ok');
  } else {
    toast('刷写失败', 'err');
    log('  ' + ((r && r.msg) || '未知'), 'err');
  }
  await bakRefresh();
}

/* ================= 页面：刷机/恢复 ================= */
async function renderFlash(wrap) {
  const cm = await call('conn_mode');
  const fb = await call('fastboot_devices');
  const mode = (cm && cm.mode) || 'none';
  const isFb = mode === 'fastboot';
  const fbCount = (fb && fb.count) || 0;

  const modeCard = isFb
    ? '<div style="display:flex;align-items:center;gap:12px;padding:14px 18px;' +
      'border-radius:14px;background:rgba(255,159,10,.12);border:1px solid rgba(255,159,10,.35);' +
      'margin-bottom:14px"><span style="font-size:24px">⚡</span>' +
      '<div><div style="font-weight:700;color:var(--orange);font-size:15px">Fastboot 模式已连接</div>' +
      '<div style="font-size:12px;color:var(--txt2)">设备 ' + fbCount + ' 台 · ' +
      esc((fb && fb.devices && fb.devices[0]) || '') + '</div></div></div>'
    : (mode === 'adb'
      ? '<div class="tip info">当前是 <b>ADB 模式</b>（系统已启动）。<br>' +
        '要刷分区 / 解 BL / 刷 Root，请先点下面「进入 Fastboot」。</div>'
      : '<div class="tip danger">未检测到设备。请插 USB 并开启调试。</div>');

  wrap.innerHTML = pageHead('刷机 / 恢复', 'Fastboot 刷写、解锁 BL、刷 Root') +
    card('连接模式', modeCard +
      '<div class="btn-row">' +
        '<button class="btn orange" onclick="toFastboot()">进入 Fastboot</button>' +
        '<button class="btn" onclick="fastbootRebootSys()">从 FB 重启到系统</button>' +
        '<button class="btn ghost" onclick="refreshFlash()">刷新状态</button>' +
      '</div>') +
    card('Bootloader 解锁',
      '<div class="btn-row">' +
        '<button class="btn" onclick="checkBL()">查询解锁状态</button>' +
        '<button class="btn red" onclick="doUnlock()">解锁 BL</button>' +
      '</div>' +
      '<div class="tip danger" style="margin-top:12px">' +
      '★ 解锁会清空全部数据（含照片、应用）<br>' +
      '★ 解锁后官方保修失效<br>' +
      '★ <b>本工具不提供「回锁 BL」功能</b>：DJI RC2 带大疆加密校验，' +
      '回锁会让遥控器直接变砖，只能用官方工具送修恢复。<br>' +
      '★ 如你确实需要回锁，请用 DJI 官方工具或送修，不要在本工具里尝试。</div>') +
    card('ADB 直刷分区（推荐，不用切 fastboot）',
      '<div style="font-size:12.5px;color:var(--txt2);line-height:1.9;margin-bottom:12px">' +
      '在 ADB 模式下直接 dd 写块设备：<b>先自动备份原分区 → 校验镜像大小 → 写入 → 回读 sha256 → 不一致自动刷回</b>。' +
      '需要 root。</div>' +
      '<div id="adbFlashCaps" style="font-size:12.5px;color:var(--txt3)">检查能力中…</div>' +
      '<div class="btn-row" style="margin-top:12px">' +
        '<select id="adbPart" style="width:220px;padding:9px 12px;border-radius:10px;' +
          'border:1px solid rgba(255,255,255,.1);background:rgba(0,0,0,.35);color:var(--txt);font-size:13px"></select>' +
        '<button class="btn ghost" onclick="pickImage()">选择镜像</button>' +
        '<button class="btn blue" onclick="adbFlashNow()">ADB 直刷</button>' +
        '<button class="btn ghost" onclick="initAdbFlash()">刷新</button>' +
      '</div>' +
      '<div id="imgName" style="margin-top:12px;font-size:12px;color:var(--txt3)">未选择镜像</div>' +
      '<div class="tip danger" style="margin-top:12px">' +
      '★ 镜像大小必须与分区完全一致，否则直接拒绝<br>' +
      '★ 刷 boot 会改启动链：确保镜像来自本机型，并已备份原 boot</div>') +
    card('Fastboot 刷写（需要 BL 已解锁）',
      '<div style="font-size:12.5px;color:var(--txt2);margin-bottom:12px">' +
      '选镜像 → 选目标分区 → 刷。需要设备处于 Fastboot 模式且 BL 已解锁。</div>' +
      '<div class="btn-row">' +
        '<button class="btn ghost" onclick="pickImage()">选择镜像</button>' +
        '<button class="btn red" onclick="flashBootB()">刷 boot_b</button>' +
        '<button class="btn red" onclick="flashBootA()">刷 boot_a</button>' +
        '<button class="btn orange" onclick="flashDjiApk()">刷 dji_apk</button>' +
        '<button class="btn ghost" onclick="flashVbmeta()">刷 vbmeta_a</button>' +
      '</div>' +
      '<div class="tip danger" style="margin-top:12px">' +
      '★ 刷错分区会让设备无法开机（变砖）<br>' +
      '★ 只有 dji_apk 可以安全刷回<br>' +
      '★ RC 系列 fastboot 基本只写不读，没有解锁时只能 getvar</div>') +
    card('刷 Root（Magisk 官方流程）',
      '<div style="font-size:12.5px;color:var(--txt2);margin-bottom:12px;line-height:1.9">' +
      'Magisk 的规矩是：<b>先把 boot 镜像提取出来 → 用 Magisk App 打补丁 → 再把补丁刷回去</b>。' +
      '工具帮你做第 1 步和第 4 步，第 2 步要你在遥控器上点几下。</div>' +
      '<div style="display:flex;flex-direction:column;gap:10px">' +
        '<div style="display:flex;gap:8px;align-items:center">' +
          '<span class="tag">1</span><button class="btn" onclick="rootExtract()">提取 boot 镜像</button>' +
          '<span id="rootStep1" style="font-size:12px;color:var(--txt3)">未提取</span></div>' +
        '<div style="font-size:12px;color:var(--txt3);margin-left:6px">把提取出来的 .img 传到遥控器，' +
          '打开 <b>Magisk App → 安装 → 选择并修补一个文件</b>，选它，等它生成 magisk_patched-*.img</div>' +
        '<div style="display:flex;gap:8px;align-items:center">' +
          '<span class="tag">2</span><button class="btn" onclick="rootPick()">选择补丁镜像</button>' +
          '<span id="rootStep2" style="font-size:12px;color:var(--txt3)">未选择</span></div>' +
        '<div style="display:flex;gap:8px;align-items:center">' +
          '<span class="tag">3</span><button class="btn blue" onclick="rootFlash()">刷入补丁</button>' +
          '<button class="btn red" onclick="rootRestoreNow()">恢复备份</button>' +
          '<button class="btn ghost" onclick="rootCheckEnv()">检查环境</button></div>' +
      '</div>' +
      '<div id="rootOut" style="margin-top:14px;font-size:12.5px;line-height:1.9;' +
      'color:var(--txt2)">第 1 步会顺便把原厂 boot 备份一份，变砖时能救回来。</div>' +
      '<div class="tip danger" style="margin-top:12px">' +
      '★ 刷错 boot 会无法开机：刷前一定要先「提取 boot 镜像」（同时就是备份）<br>' +
      '★ 变砖后按住返回键+电源键进 fastboot，用「恢复备份」或 fastboot 刷回<br>' +
      '★ 刷完必须重启，Magisk App 里能看到版本号才算成功</div>') +
    card('高级 Fastboot 命令',
      '<input id="fbCmd" type="text" placeholder="如：getvar all / oem device-info" ' +
        'style="width:100%;padding:12px 16px;border-radius:12px;border:1px solid rgba(255,255,255,.1);' +
        'background:rgba(0,0,0,.35);color:var(--txt);font-family:monospace;font-size:13px;outline:none">' +
      '<div class="btn-row" style="margin-top:12px">' +
        '<button class="btn" onclick="runFbCmd()">执行</button>' +
      '</div>');
  log('刷机页已加载，模式=' + mode);
  setTimeout(initAdbFlash, 120);
}

let flashImg = null;

function flashBootA() { flashPart('boot_a'); }
function flashBootB() { flashPart('boot_b'); }
function flashDjiApk() { flashPart('dji_apk'); }
function flashVbmeta() { flashPart('vbmeta_a'); }

function refreshFlash() {
  const w = document.getElementById('pageWrap');
  if (w) renderFlash(w);
}

async function toFastboot() {
  if (!confirm('重启到 Fastboot 模式？\n\n设备会断开并进入 bootloader。')) return;
  const r = await call('reboot_bootloader');
  toast(r && r.ok ? '已发送，等待设备进入 Fastboot' : '发送失败',
        r && r.ok ? 'ok' : 'err');
  log('已发送进入 fastboot 指令', 'warn');
  setTimeout(() => { if (curPage === 'flash') renderFlash(document.getElementById('pageWrap')); }, 6000);
}

async function fastbootRebootSys() {
  const r = await call('fastboot_reboot');
  toast(r && r.ok ? '已重启到系统' : '失败：' + ((r && r.msg) || ''),
        r && r.ok ? 'ok' : 'err');
}

async function checkBL() {
  const r = await call('check_bootloader');
  if (r && r.ok) {
    toast(r.unlocked ? 'BL 已解锁' : 'BL 未解锁', r.unlocked ? 'ok' : 'err');
    log('BL 状态: ' + (r.msg || ''), 'info');
  } else {
    toast('查询失败', 'err');
  }
}

async function doUnlock() {
  if (!confirm('解锁 Bootloader？\n\n⚠ 会清空设备全部数据！\n⚠ 保修失效！\n\n确定继续？')) return;
  if (!confirm('再确认一次：真的要解锁 BL 吗？')) return;
  log('正在解锁 BL…', 'hdr');
  const r = await call('fastboot_oem', 'unlock');
  toast(r && r.ok ? '已发送解锁指令' : '失败', r && r.ok ? 'ok' : 'err');
  log((r && r.msg) || '', 'info');
}

async function doLock() {
  toast('本工具已永久移除「回锁 BL」功能：DJI RC2 有大疆加密校验，回锁即变砖', 'err');
}

async function pickImage() {
  const r = await call('pick_image');
  if (r && r.ok) {
    flashImg = r.path;
    const el = document.getElementById('imgName');
    if (el) el.textContent = r.path;
    log('已选镜像: ' + r.path);
  }
}

async function flashPart(part) {
  if (!flashImg) { toast('请先选择镜像', 'err'); return; }
  if (!confirm('把镜像刷到 ' + part + ' ？\n\n刷错可能变砖！')) return;
  log('刷写 ' + part + ' …', 'hdr');
  toast('正在刷写…');
  const r = await call('fastboot_flash', part, flashImg);
  toast(r && r.ok ? '刷写完成' : '刷写失败', r && r.ok ? 'ok' : 'err');
  log((r && r.msg) || '', r && r.ok ? 'ok' : 'err');
}

async function runFbCmd() {
  const el = document.getElementById('fbCmd');
  if (!el || !el.value.trim()) return;
  const parts = el.value.trim().split(/ +/);
  log('$ fastboot ' + parts.join(' '), 'hdr');
  const r = await call('fastboot_command', ...parts);
  log((r && r.msg) || '(无输出)', 'dim');
}

/* ================= 页面：投屏（真机可用方案）================= */
let mirrorTimer = null;
let mirrorOn = false;

async function renderScreen(wrap) {
  const st = await call('scrcpy_status');
  let note = '';
  if (st && st.ok === false) note = st.msg || '';
  if (st && !st.scrcpy_usable && st.reason) {
    note = st.reason;
  }
  wrap.innerHTML = pageHead('投屏 / 截图', '实时画面与录屏') +
    card('实时画面（轮询截图方案）',
      '<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px">' +
        '<button class="btn green" id="mirrorBtn" onclick="toggleMirror()">开始画面</button>' +
        '<button class="btn" onclick="mirrorRefresh()">刷新一帧</button>' +
        '<button class="btn ghost" onclick="doScreenshot()">保存截图</button>' +
        '<button class="btn ghost" onclick="openOutDir()">输出目录</button>' +
      '</div>' +
      '<div id="mirrorBox" style="background:rgba(0,0,0,.35);border-radius:14px;' +
        'border:1px solid rgba(255,255,255,.08);min-height:280px;display:flex;' +
        'align-items:center;justify-content:center;overflow:hidden">' +
        '<span style="color:var(--txt3);font-size:13px">点「开始画面」预览设备屏幕</span>' +
      '</div>' +
      '<div id="mirrorHint" style="margin-top:10px;font-size:12px;color:var(--txt3)"></div>' +
      (note ? '<div class="tip">' + esc(note) + '</div>' : '')) +
    card('说明',
      '<div style="font-size:12.5px;color:var(--txt2);line-height:1.9">' +
      '· 本机实测：DJI ROM 拦截 app_process，scrcpy server 无法启动，所以不能直接用 scrcpy 投屏<br>' +
      '· 已改用 adb exec-out 轮询截图，约 0.8 秒一帧，够用于查看状态<br>' +
      '· 需要真正低延迟操控，建议用 USB 连接电脑后用电脑端工具' +
      '</div>');
  log('投屏页已加载');
}

async function fetchFrame() {
  const r = await call('screen_frame');
  const box = document.getElementById('mirrorBox');
  if (!box) return false;
  if (r && r.ok && r.data) {
    box.innerHTML = '<img src="data:image/png;base64,' + r.data +
      '" style="max-width:100%;max-height:520px;border-radius:10px;display:block">';
    const h = document.getElementById('mirrorHint');
    if (h) h.textContent = '帧大小 ' + Math.round(r.size / 1024) + ' KB · ' +
      new Date().toTimeString().slice(0, 8);
    return true;
  }
  const h = document.getElementById('mirrorHint');
  if (h) h.textContent = '取帧失败：' + ((r && r.msg) || '未知');
  return false;
}

async function mirrorRefresh() {
  await fetchFrame();
}

async function toggleMirror() {
  const btn = document.getElementById('mirrorBtn');
  if (mirrorOn) {
    mirrorOn = false;
    if (mirrorTimer) { clearTimeout(mirrorTimer); mirrorTimer = null; }
    if (btn) { btn.textContent = '开始画面'; btn.className = 'btn green'; }
    log('实时画面已停止');
    return;
  }
  mirrorOn = true;
  if (btn) { btn.textContent = '停止画面'; btn.className = 'btn red'; }
  log('实时画面已开始（约 0.8 秒一帧）', 'ok');
  const loop = async () => {
    if (!mirrorOn) return;
    await fetchFrame();
    if (mirrorOn) mirrorTimer = setTimeout(loop, 900);
  };
  loop();
}

async function stopMirrorTimer() {
  mirrorOn = false;
  if (mirrorTimer) { clearTimeout(mirrorTimer); mirrorTimer = null; }
}

async function startScrcpy(size, fps) {
  const r = await call('start_scrcpy', size, fps);
  if (r && r.ok) { toast('已启动', 'ok'); }
  else { toast((r && r.msg) || 'scrcpy 不可用', 'err'); }
}
async function recordScreen() { toast('录屏请用「保存截图」逐帧或用电脑端工具'); }
async function stopScrcpy() { await call('stop_scrcpy'); toast('已停止'); }
async function doScreenshot() {
  toast('正在截图…');
  const r = await call('screenshot');
  if (r && r.ok) { toast('已保存', 'ok'); log('截图: ' + r.path, 'ok'); }
  else { toast('截图失败', 'err'); }
}
async function openOutDir() { await call('open_out_dir'); }

/* ================= 页面：命令终端 ================= */
let termMode = 'adb';

const ADB_CMDS = [
  ['查看设备', 'devices'],
  ['设备信息', 'shell getprop ro.product.model'],
  ['内存情况', 'shell cat /proc/meminfo'],
  ['swap 列表', 'shell cat /proc/swaps'],
  ['CPU 频率', 'shell cat /sys/devices/system/cpu/cpu7/cpufreq/scaling_cur_freq'],
  ['CPU 调度', 'shell cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor'],
  ['温度', 'shell cat /sys/class/thermal/thermal_zone40/temp'],
  ['电池', 'shell dumpsys battery'],
  ['已装模块', 'shell ls /data/adb/modules'],
  ['重启设备', 'reboot'],
  ['重启到 bootloader', 'reboot bootloader'],
  ['重启到 recovery', 'reboot recovery'],
  ['安装 APK', 'install -r __APK__'],
  ['截图', 'shell screencap -p /sdcard/shot.png'],
  ['日志尾部', 'logcat -d -t 100'],
  ['当前应用', 'shell dumpsys activity activities | grep mResumedActivity'],
];

const FB_CMDS = [
  ['查看设备', 'devices'],
  ['查询解锁状态', 'getvar unlocked'],
  ['查询全部变量', 'getvar all'],
  ['解锁 BL', 'flashing unlock'],
  ['OEM 信息', 'oem device-info'],
  ['刷 boot_a', 'flash boot_a __IMG__'],
  ['刷 boot_b', 'flash boot_b __IMG__'],
  ['刷 dji_apk', 'flash dji_apk __IMG__'],
  ['刷 vbmeta_a', 'flash vbmeta_a __IMG__'],
  ['临时启动镜像', 'boot __IMG__'],
  ['重启到系统', 'reboot'],
  ['重启到 recovery', 'reboot recovery'],
  ['擦除 misc', 'erase misc'],
];

async function renderTerm(wrap) {
  wrap.innerHTML = pageHead('命令终端', '直接向遥控器发送 ADB / Fastboot 命令') +
    card('模式',
      '<div class="term-tabs">' +
        '<button class="term-tab' + (termMode === 'adb' ? ' on' : '') +
          '" id="tabAdb" onclick="setTermMode(\'adb\')">ADB 命令</button>' +
        '<button class="term-tab' + (termMode === 'fastboot' ? ' on' : '') +
          '" id="tabFb" onclick="setTermMode(\'fastboot\')">Fastboot 命令</button>' +
      '</div>' +
      '<div class="term-hint" id="termHint"></div>') +
    card('执行',
      '<textarea id="termInput" class="term-input" spellcheck="false" ' +
        'placeholder="在此输入命令，不用带 adb / fastboot 前缀…"></textarea>' +
      '<div class="btn-row" style="margin-top:12px">' +
        '<button class="btn blue" onclick="runTerm()">执行命令</button>' +
        '<button class="btn ghost" onclick="clearTermOut()">清空输出</button>' +
      '</div>' +
      '<pre id="termOut" class="term-out"></pre>') +
    card('常用命令',
      '<div id="termChips" class="term-chips"></div>');
  renderTermChips();
  updateTermHint();
}

function setTermMode(m) {
  termMode = m;
  const a = document.getElementById('tabAdb');
  const b = document.getElementById('tabFb');
  if (a) a.classList.toggle('on', m === 'adb');
  if (b) b.classList.toggle('on', m === 'fastboot');
  renderTermChips();
  updateTermHint();
}

function updateTermHint() {
  const el = document.getElementById('termHint');
  if (!el) return;
  el.innerHTML = termMode === 'adb'
    ? '当前：ADB 模式 · 设备需正常开机并被识别（adb devices 能看到）'
    : '当前：Fastboot 模式 · 设备需进入 bootloader（adb reboot bootloader）';
}

function renderTermChips() {
  const box = document.getElementById('termChips');
  if (!box) return;
  const list = termMode === 'adb' ? ADB_CMDS : FB_CMDS;
  box.innerHTML = list.map((it, i) =>
    '<button class="chip" onclick="useTermChip(' + i + ')">' +
      esc(it[0]) + '</button>').join('');
}

function useTermChip(i) {
  const list = termMode === 'adb' ? ADB_CMDS : FB_CMDS;
  const it = list[i];
  if (!it) return;
  const inp = document.getElementById('termInput');
  if (!inp) return;
  inp.value = it[1];
  inp.focus();
  toast('已填入：' + it[0], 'info');
}

async function runTerm() {
  const inp = document.getElementById('termInput');
  const out = document.getElementById('termOut');
  if (!inp || !out) return;
  const cmd = (inp.value || '').trim();
  if (!cmd) { toast('请输入命令', 'warn'); return; }
  out.textContent += '\n> ' + cmd + '\n';
  out.scrollTop = out.scrollHeight;
  out.textContent += '执行中…\n';
  const r = await call(termMode === 'adb' ? 'adb_cmd' : 'fb_cmd', cmd);
  let txt = '';
  if (r && r.ok) {
    txt = (r.out || '') + (r.err ? '\n[stderr] ' + r.err : '');
    if (!txt.trim()) txt = '(无输出，执行成功)';
  } else if (r) {
    txt = '退出码: ' + r.code + '\n' +
          (r.out || '') + (r.err ? '\n[stderr] ' + r.err : '');
    if (!(r.out || r.err)) txt += (r.msg || '(无输出)');
  } else {
    txt = '(调用失败)';
  }
  // 把"执行中…"替换掉
  out.textContent = out.textContent.replace(/执行中…\n$/, '');
  out.textContent += txt + '\n';
  out.scrollTop = out.scrollHeight;
}

function clearTermOut() {
  const out = document.getElementById('termOut');
  if (out) out.textContent = '';
}

/* ================= 页面：工具 ================= */
async function renderTools(wrap) {
  wrap.innerHTML = pageHead('实用工具', '常用调试功能') +
    card('快捷操作',
      '<div class="btn-row">' +
        '<button class="btn" onclick="dumpInfo()">导出系统信息</button>' +
        '<button class="btn green" onclick="showLogcat()">查看日志</button>' +
        '<button class="btn purple" onclick="wirelessAdb()">无线 ADB</button>' +
        '<button class="btn orange" onclick="stayAwake()">屏幕常亮</button>' +
        '<button class="btn ghost" onclick="cleanTmp()">清理临时文件</button>' +
      '</div>') +
    card('自定义命令',
      '<input id="cmdInput" type="text" placeholder="输入 shell 命令…" ' +
        'style="width:100%;padding:12px 16px;border-radius:12px;border:1px solid rgba(255,255,255,.1);' +
        'background:rgba(0,0,0,.35);color:var(--txt);font-family:monospace;font-size:13px;outline:none">' +
      '<div class="btn-row" style="margin-top:12px">' +
        '<button class="btn red" onclick="runCmd(true)">以 root 执行</button>' +
        '<button class="btn" onclick="runCmd(false)">普通执行</button>' +
      '</div>') +
    card('危险操作',
      '<div class="btn-row">' +
        '<button class="btn red" onclick="doReboot()">重启设备</button>' +
        '<button class="btn orange" onclick="toRecovery()">重启到 recovery</button>' +
      '</div>');
  log('工具页已加载');
  const inp = document.getElementById('cmdInput');
  if (inp) inp.addEventListener('keydown', e => { if (e.key === 'Enter') runCmd(true); });
}

async function runCmd(root) {
  const inp = document.getElementById('cmdInput');
  if (!inp || !inp.value.trim()) return;
  const cmd = inp.value.trim();
  log('$ ' + cmd, 'hdr');
  const r = await call('run_shell', cmd, root);
  if (r && r.out) {
    r.out.split('\n').slice(0, 40).forEach(l => log('  ' + l, 'dim'));
  } else {
    log('  (无输出)', 'dim');
  }
}
async function dumpInfo() {
  const r = await call('dump_info');
  if (r && r.ok) { toast('已保存', 'ok'); log('系统信息: ' + r.path, 'ok'); }
  else toast('导出失败', 'err');
}
async function showLogcat() {
  const r = await call('logcat_tail');
  if (r && r.out) r.out.split('\n').slice(-30).forEach(l => log(l, 'dim'));
  else toast('读取失败', 'err');
}
async function wirelessAdb() {
  const r = await call('wireless_adb');
  if (r && r.ok) { toast('IP: ' + r.ip, 'ok'); log('无线调试: adb connect ' + r.ip + ':5555', 'ok'); }
  else { toast('获取失败', 'err'); log((r && r.msg) || '失败', 'err'); }
}
async function stayAwake() {
  const r = await call('stay_awake');
  toast(r && r.ok ? '屏幕常亮已开启' : '失败', r && r.ok ? 'ok' : 'err');
}
async function cleanTmp() {
  const r = await call('clean_tmp');
  toast(r && r.ok ? '临时文件已清理' : '失败', r && r.ok ? 'ok' : 'err');
}
async function toRecovery() {
  if (!confirm('重启到 recovery？')) return;
  await call('reboot_recovery');
  toast('已发送');
}

/* ================= 页面：关于 ================= */
async function renderAbout(wrap) {
  const info = await call('hello');
  wrap.innerHTML = pageHead('关于', '版本信息与免责声明') +
    card('软件信息',
      '<div style="font-size:24px;font-weight:800;letter-spacing:-.5px;margin-bottom:8px">' +
        esc((info && info.name) || 'RC 搞机工具箱') + '</div>' +
      '<div style="font-size:13px;color:var(--txt2)">版本 v' + ((info && info.ver) || '4.0') +
      '&nbsp;&nbsp;·&nbsp;&nbsp;作者：' + esc((info && info.author) || '软糖布丁') + '</div>' +
      '<div style="font-size:12px;color:var(--txt3);margin-top:6px">' +
      '专为 DJI RC2 遥控器（rc331 / Android 11）打造</div>') +
    card('外观设置',
      '<div style="font-size:12.5px;color:var(--txt2);line-height:1.9;margin-bottom:12px">' +
      '给工具箱换一张自己的背景图，界面玻璃会实时透出壁纸，更有质感。' +
      '</div>' +
      '<div style="display:flex;gap:10px;flex-wrap:wrap">' +
        '<button class="btn blue" onclick="pickWallpaper()">选择壁纸图片</button>' +
        '<button class="btn ghost" onclick="clearWallpaper()">恢复默认背景</button>' +
      '</div>') +
    card('免责声明',
      '<div class="modal-body" style="max-height:340px;padding:0;background:transparent">' +
        esc(DISCLAIMER) + '</div>') +
    card('技术说明',
      '<div style="font-size:12.5px;color:var(--txt2);line-height:1.9">' +
      '· 界面：HTML/CSS/JS + WebView2 —— 真正的液态玻璃（backdrop-filter）与 60fps 动效<br>' +
      '· 后端：Python，直接调用 adb / fastboot / scrcpy<br>' +
      '· su 用绝对路径 /debug_ramdisk/su（旧版失效的根因）<br>' +
      '· 所有资源内嵌在 exe 里，不依赖外部安装' +
      '</div>');
  log('关于页已加载');
}

const DISCLAIMER = `【第一部分 · 这是什么】

本软件（RC 搞机工具箱）是给 DJI RC2 遥控器（型号 rc331，Android 11，SDK 30，
高通 lahaina 平台）使用的第三方工具，作者：软糖布丁。

它不是大疆（DJI）官方软件，也未获得大疆任何形式的授权、许可或认可。
本软件与 DJI 公司没有任何关联，不是官方售后工具，也不代表大疆立场。

【第二部分 · 它具体会改什么】

本软件通过 adb 与 root 权限直接读写系统底层参数，涉及范围包括：

  1. CPU
     · 三个簇的上限频率（小核 cpu0-3 / 大核 cpu4-6 / 超大核 cpu7）
     · 调度策略（powersave / schedutil / performance 等）
     · 温控开关（thermal zone 的 mode）
  2. GPU
     · 频率档位（315 / 450 / 550 / 608 / 700 / 812 MHz）
     · 调度模式
  3. 内存与虚拟内存
     · zram 压缩内存的大小与 swappiness
     · 磁盘 swap 文件的创建、启用、关闭
     · 内核内存管理参数（extra_free_kbytes、drop_caches）
  4. 系统与 Magisk
     · 系统属性（setprop）
     · Magisk 模块的启用 / 停用 / 安装 / 卸载
     · adb 的 root 权限开关
  5. 存储与分区
     · 分区镜像的读取备份（boot_a / boot_b / misc / dji_apk 等）
     · Fastboot 模式下刷写分区、解锁 Bootloader
  6. 显示与外观
     · 开机动画（bootanimation.zip 的替换）
     · 屏幕背光参数（只读监控，不会修改 pwmchip0）

【第三部分 · 可能导致的后果（请逐条阅读）】

  1. 设备过热、卡顿、应用闪退、自动重启
     —— 把 CPU / GPU 频率调到最高并关闭温控后，机身温度可能超过 70℃
  2. 系统无法启动（俗称「变砖」）
     —— 刷错分区、刷入不匹配的镜像、Magisk 模块冲突都可能导致
  3. 屏幕黑屏（有画面但背光不亮 / 完全无显示）
     —— 误操作 pwmchip0 背光节点会导致，需要用急救脚本或重刷恢复
  4. 数据永久丢失
     —— 分区刷写错误、格式化、解锁 BL 都会清空数据，且多数不可恢复
  5. 官方保修失效
     —— 解锁 Bootloader、刷入第三方分区会让大疆官方拒绝保修
  6. 无法回锁 Bootloader（重要）
     —— DJI RC2 带大疆加密校验，回锁会让遥控器直接变砖，
        只能通过官方渠道送修恢复。因此本工具**永久移除**了回锁功能。

【第四部分 · 责任声明】

作者（软糖布丁）不对以下任何情况承担责任：
  · 数据丢失、文件损坏、系统崩溃
  · 设备硬件损坏、变砖、黑屏、无法开机
  · 保修失效、官方拒保、维修费用
  · 因使用本工具导致的任何直接或间接损失

本软件按「现状」提供，不附带任何明示或暗示的担保，
包括但不限于适销性、特定用途适用性的担保。

使用本软件完全出于你本人的自愿选择。
请在操作前自行备份重要数据（照片、应用、分区镜像），
并确认你理解每一步在做什么。

【第五部分 · 绝对不要做的事】

  · 不要 unexport pwmchip0
    —— 那是屏幕背光控制，unexport 后会黑屏。急救：sh fix_screen.sh
  · 不要在关闭 zram 后不重新开启
    —— 内存会立刻耗尽，系统卡死
  · 不要用 dd 一口气写入超过 1GB 的文件
    —— 会挤爆 1.7GB 物理内存，触发 watchdog 重启
  · 不要刷回 dji_apk 以外的数据分区
    —— 会让系统显示「存储损坏」
  · 不要在非原厂状态下回锁 Bootloader
    —— DJI RC2 会直接变砖（本工具已移除该功能）
  · 不要把 swappiness 设成超过 100
    —— 内核上限就是 100，超了会报错或不生效
  · 不要把 extra_free_kbytes 设成超过 32MB
    —— 125MB 会直接 OOM

【第六部分 · 使用建议】

  · 第一次使用：先只读（看数据），不要改任何参数
  · 改参数：一次只改一项，改完观察 5 分钟
  · 刷分区前：先用「分区备份」把原镜像存到电脑
  · 装模块前：确认模块是给 Android 11 / arm64 准备的
  · 出问题时：先看「运行日志」，再用急救脚本

【第七部分 · 同意】

点「我已阅读并同意」表示：
  · 你已完整阅读并理解上述全部内容
  · 你知道这是一款有风险的「玩机工具」，不是官方软件
  · 你自愿承担使用本软件带来的一切后果

此同意只需一次，之后启动不再询问（可在「关于/免责」页重新查看）。
如果你不同意，请点「不同意并退出」。`;

/* ================= 免责声明 ================= */
async function showDisclaimer() {
  return new Promise(resolve => {
    const mask = document.createElement('div');
    mask.className = 'modal-mask';
    mask.innerHTML =
      '<div class="modal">' +
        '<div class="modal-head">' +
          '<h2>使用前必读 · 免责声明</h2>' +
          '<p>RC 搞机工具箱 v6.2 &nbsp;·&nbsp; 作者：软糖布丁</p>' +
        '</div>' +
        '<div class="modal-body">' + esc(DISCLAIMER) + '</div>' +
        '<div class="modal-foot">' +
          '<button class="btn ghost" id="disAgree">不同意并退出</button>' +
          '<button class="btn green" id="disOk">我已阅读并同意</button>' +
        '</div>' +
      '</div>';
    document.body.appendChild(mask);
    mask.querySelector('#disOk').onclick = async () => {
      await call('mark_agreed');
      mask.style.animation = 'maskIn .25s reverse';
      setTimeout(() => mask.remove(), 240);
      resolve(true);
    };
    mask.querySelector('#disAgree').onclick = async () => {
      await call('quit_app');
      resolve(false);
    };
  });
}

/* ================= 窗口按钮 ================= */
function bindWindow() {
  const bm = document.getElementById('btnMin');
  const bx = document.getElementById('btnMax');
  const bc = document.getElementById('btnClose');
  if (bm) bm.onclick = () => call('win_minimize');
  if (bx) bx.onclick = () => call('win_maximize');
  if (bc) bc.onclick = async () => {
    if (confirm('确定退出 RC 搞机工具箱？')) await call('quit_app');
  };

  // 拖动窗口：标题栏空白处按住拖动（Python 侧跟随鼠标移动真实窗口）
  const tb = document.getElementById('titlebar');
  if (tb) {
    tb.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      if (e.target.closest('button, .dev-badge, a, input')) return;
      call('win_drag_start');
      e.preventDefault();
    });
    // 双击标题栏 = 最大化切换
    tb.addEventListener('dblclick', e => {
      if (e.target.closest('button, .dev-badge, a, input')) return;
      call('win_maximize');
    });
    document.addEventListener('mouseup', () => call('win_drag_end'));
  }

  // 八向拖拽缩放
  document.querySelectorAll('.rz').forEach(el => {
    el.addEventListener('mousedown', e => {
      if (e.button !== 0) return;
      call('win_resize_start', el.dataset.edge || 'se');
      e.preventDefault();
      e.stopPropagation();
    });
  });
  document.addEventListener('mouseup', () => call('win_resize_end'));
  // F11 全屏切换
  document.addEventListener('keydown', e => {
    if (e.key === 'F11') { e.preventDefault(); call('win_fullscreen'); }
  });

  const cl = document.getElementById('btnClearLog');
  if (cl) cl.onclick = () => { logBody().innerHTML = ''; };
  const cp = document.getElementById('btnCopyLog');
  if (cp) cp.onclick = () => {
    const t = logBody().innerText || '';
    navigator.clipboard.writeText(t).then(() => toast('日志已复制', 'ok'));
  };
}

/* ================= 壁纸 ================= */
async function applyWallpaper() {
  const el = document.getElementById('wallpaper');
  if (!el) return;
  const info = await call('wallpaper_info');
  if (info && info.has && info.url) {
    el.style.backgroundImage = 'url("' + info.url + '")';
    el.classList.add('on');
    document.body.classList.add('has-wp');
  } else {
    el.style.backgroundImage = '';
    el.classList.remove('on');
    document.body.classList.remove('has-wp');
  }
}

async function pickWallpaper() {
  toast('正在打开文件选择…', 'info');
  const r = await call('pick_wallpaper');
  if (r && r.ok && r.url) {
    await applyWallpaper();
    toast('壁纸已更换', 'ok');
  } else if (r && r.msg) {
    toast(r.msg, 'warn');
  }
}

async function clearWallpaper() {
  await call('clear_wallpaper');
  await applyWallpaper();
  toast('已恢复默认背景', 'ok');
}

/* ================= 状态轮询 ================= */
let statusTimer = null;
async function pollStatus() {
  const cm = await call('conn_mode');
  if (cm && cm.ok) {
    const badge = document.getElementById('devBadge');
    const txt = document.getElementById('devText');
    if (badge && txt) {
      if (cm.mode === 'fastboot') {
        badge.classList.add('on');
        badge.style.borderColor = 'rgba(255,159,10,.5)';
        txt.textContent = '⚡ Fastboot · ' + cm.serial;
        txt.style.color = 'var(--orange)';
        return;
      } else if (cm.mode === 'adb') {
        badge.style.borderColor = '';
        txt.style.color = '';
      } else {
        badge.classList.remove('on');
        txt.textContent = '未连接';
        txt.style.color = '';
        return;
      }
    }
  }
  const d = await call('quick_stat');
  const badge = document.getElementById('devBadge');
  const txt = document.getElementById('devText');
  if (!badge || !txt) return;
  if (d && d.ok && d.model && d.model !== '/') {
    badge.classList.add('on');
    txt.textContent = d.model +
      (d.temp ? ' · ' + d.temp + '℃' : '') +
      (d.avail ? ' · ' + kbHuman(d.avail) : '');
  } else {
    badge.classList.remove('on');
    txt.textContent = '未连接';
  }
}

/* ================= 启动 ================= */
async function boot() {
  buildSidebar();
  bindWindow();
  bindBtnRipple();
  const _q = new URLSearchParams(location.search).get('page');

  go(_q && PAGES.some(p => p.id === _q) ? _q : 'overview');
  const _sc = parseInt(new URLSearchParams(location.search).get('scroll') || '0', 10);
  if (_sc) setTimeout(() => {
    const el = document.getElementById('pageWrap') || document.querySelector('.main');
    if (el) el.scrollTop = _sc; else window.scrollTo(0, _sc);
  }, 900);
  applyWallpaper();

  // ★ 状态轮询必须先起：以前它排在「等用户点同意」之后，
  //   没点同意就永远不轮询，顶栏一直停在默认文案「未连接」。
  pollStatus().catch(() => {});
  statusTimer = setInterval(() => pollStatus().catch(() => {}), 4000);

  const agreed = await call('has_agreed');
  if (!agreed || !agreed.agreed) {
    const ok = await showDisclaimer();
    if (!ok) return;
  }
  log('欢迎使用 RC 搞机工具箱 v6.2', 'hdr');
  log('作者：软糖布丁', 'dim');
}

function bindBtnRipple() {
  document.addEventListener('mousemove', e => {
    const b = e.target.closest && e.target.closest('.btn');
    if (b) {
      const r = b.getBoundingClientRect();
      b.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      b.style.setProperty('--my', (e.clientY - r.top) + 'px');
    }
  });
}

let __booted = false;
function tryBoot() {
  if (__booted) return;
  // 以前这里只认 pywebview 原生通道，Edge --app 模式下 window.pywebview
  // 永远不存在 → boot() 从来没跑过，全靠 2.6 秒兜底渲染一页，
  // 于是顶栏一直「未连接」、免责声明也不弹。
  const hasWV = window.pywebview && window.pywebview.api;
  const isHttp = location.protocol === 'http:' || location.protocol === 'https:';
  if (hasWV || isHttp) {
    __booted = true;
    boot().catch(e => log('启动失败: ' + e, 'err'));
  }
}
window.addEventListener('pywebviewready', () => {
  setTimeout(tryBoot, 50);
});

// ---------------- 刷 Root（Magisk 流程） ----------------
function rootLog(html) {
  const el = document.getElementById('rootOut');
  if (el) el.innerHTML = html;
}

async function rootCheckEnv() {
  rootLog('正在检查环境…');
  const r = await call('root_env');
  if (!r || !r.ok) {
    rootLog('<span style="color:#ff6961">' + esc((r && r.msg) || '检查失败') + '</span>');
    return;
  }
  const rows = [
    ['设备', r.device || '-'],
    ['su', r.su || '未找到'],
    ['Magisk', r.magisk_ver || '未检测到'],
    ['boot 分区', (r.boot_name || '-') + ' → ' + (r.boot_block || '-')],
    ['分区大小', r.boot_size ? (r.boot_size / 1048576).toFixed(1) + ' MB' : '-'],
    ['已有镜像', (r.backups && r.backups.length) ? r.backups.length + ' 个' : '无'],
  ];
  let h = '<div style="display:grid;grid-template-columns:100px 1fr;gap:6px 10px">';
  rows.forEach(([k, v]) => {
    h += '<div style="color:var(--txt3)">' + k + '</div><div>' + esc(v) + '</div>';
  });
  h += '</div>';
  rootLog(h);
}

async function rootExtract() {
  rootLog('正在提取 boot 镜像（约 10 秒）…');
  const r = await call('root_extract');
  if (r && r.ok) {
    const s1 = document.getElementById('rootStep1');
    if (s1) { s1.textContent = '已提取 ' + (r.size / 1048576).toFixed(1) + ' MB';
              s1.style.color = '#30d158'; }
    rootLog('<span style="color:#30d158">✓ 已提取并备份</span><br>' +
      '文件：' + esc(r.file) + '<br>大小：' + (r.size / 1048576).toFixed(1) + ' MB<br>' +
      '<div style="margin-top:10px;padding:12px;border-radius:10px;' +
      'background:rgba(10,132,255,.12);border:1px solid rgba(10,132,255,.3)">' +
      '<b>下一步：</b>' + esc(r.next) + '</div>');
    toast('boot 镜像已提取');
  } else {
    rootLog('<span style="color:#ff6961">提取失败：' +
      esc((r && r.msg) || '') + '</span>');
  }
}

async function rootPick() {
  rootLog('请在弹出的窗口里选择 Magisk 打好的 magisk_patched-*.img …');
  const r = await call('root_pick_patched');
  const s2 = document.getElementById('rootStep2');
  if (r && r.ok) {
    if (s2) { s2.textContent = '已选择 ' + (r.size / 1048576).toFixed(1) + ' MB';
              s2.style.color = '#30d158'; }
    rootLog('<span style="color:#30d158">✓ ' + esc(r.msg) + '</span><br>' +
      '文件：' + esc(r.file));
  } else {
    if (s2) { s2.textContent = '未通过校验'; s2.style.color = '#ff6961'; }
    rootLog('<span style="color:#ff6961">' + esc((r && r.msg) || '未选择') + '</span>' +
      (r && r.block_size ? '<br>分区大小 ' + (r.block_size / 1048576).toFixed(1) +
        ' MB，你选的 ' + (r.size / 1048576).toFixed(1) + ' MB' : ''));
  }
}

async function rootFlash() {
  if (!confirm('把补丁镜像刷进 boot 分区？\n\n刷完必须重启，中途别断电。')) return;
  rootLog('正在刷入…');
  const r = await call('root_flash_patched');
  if (r && r.ok) {
    rootLog('<span style="color:#30d158">✓ ' + esc(r.msg) + '</span><br>' +
      '<div style="margin-top:8px;color:var(--txt3)">备份：' + esc(r.backup || '') + '</div>' +
      '<div style="margin-top:6px;color:#ff9f0a">' + esc(r.note || '') + '</div>');
    toast('刷入完成，重启生效');
  } else {
    rootLog('<span style="color:#ff6961">刷入失败：' + esc((r && r.msg) || '') + '</span>' +
      (r && r.detail ? '<pre style="margin-top:8px;font-size:11.5px">' +
        esc(r.detail) + '</pre>' : ''));
  }
}

async function rootRestoreNow() {
  if (!confirm('把最近一次备份的 boot 镜像刷回去？\n\n用于刷 Root 失败后恢复。')) return;
  rootLog('正在恢复备份…');
  const r = await call('root_restore');
  if (r && r.ok) {
    rootLog('<span style="color:#30d158">✓ ' + esc(r.msg) + '</span>');
    toast('已恢复备份');
  } else {
    rootLog('<span style="color:#ff6961">恢复失败：' + esc((r && r.msg) || '') + '</span>');
  }
}

// ---------------- 投屏（实时画面 + 控制） ----------------

async function renderMirror(wrap) {
  wrap.innerHTML = pageHead('投屏 / 截图', '实时画面 + 点击控制（真注入触摸）') +
    card('实时画面',
      '<div style="font-size:12.5px;color:var(--txt2);margin-bottom:12px">' +
      '画面约 1-2 帧/秒（DJI ROM 封了 scrcpy 的 server，只能用截图推流）。' +
      '<b>点画面可以直接操作遥控器</b>，拖动就是滑动。</div>' +
      '<div style="display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap">' +
        '<button class="btn blue" onclick="mirrorStart()">开始投屏</button>' +
        '<button class="btn" onclick="mirrorStop()">停止</button>' +
        '<button class="btn ghost" onclick="shotNow()">截一张图</button>' +
        '<button class="btn ghost" onclick="keySend(\'home\')">Home</button>' +
        '<button class="btn ghost" onclick="keySend(\'back\')">返回</button>' +
        '<button class="btn ghost" onclick="keySend(\'menu\')">菜单</button>' +
      '</div>' +
      '<div id="mirrorBox" style="position:relative;border-radius:14px;overflow:hidden;' +
      'background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.09);' +
      'aspect-ratio:16/9;display:flex;align-items:center;justify-content:center">' +
      '<div id="mirrorHint" style="color:var(--txt3);font-size:13px">' +
      '点「开始投屏」后这里显示遥控器实时画面</div>' +
      '<img id="mirrorImg" style="display:none;width:100%;height:100%;object-fit:contain;cursor:crosshair">' +
      '</div>' +
      '<div style="margin-top:10px;font-size:12px;color:var(--txt3)" id="mirrorStat">未连接</div>');
  bindMirror();
}

function bindMirror() {
  const img = document.getElementById('mirrorImg');
  if (!img || img._bound) return;
  img._bound = true;
  let down = null;
  const toDisp = (e) => {
    const r = img.getBoundingClientRect();
    const vw = img.naturalWidth || 1920, vh = img.naturalHeight || 1080;
    // object-fit: contain 的实际显示区域
    const scale = Math.min(r.width / vw, r.height / vh);
    const dw = vw * scale, dh = vh * scale;
    const ox = (r.width - dw) / 2, oy = (r.height - dh) / 2;
    const x = (e.clientX - r.left - ox) / scale;
    const y = (e.clientY - r.top - oy) / scale;
    return [Math.max(0, Math.min(vw, x)), Math.max(0, Math.min(vh, y))];
  };
  img.addEventListener('mousedown', e => {
    down = toDisp(e);
    e.preventDefault();
  });
  img.addEventListener('mouseup', async e => {
    if (!down) return;
    const up = toDisp(e);
    const dx = Math.abs(up[0] - down[0]), dy = Math.abs(up[1] - down[1]);
    if (dx < 12 && dy < 12) {
      const r = await call('tap_xy', Math.round(down[0]), Math.round(down[1]));
      if (!r || !r.ok) toast('点击失败');
    } else {
      const r = await call('swipe_xy', Math.round(down[0]), Math.round(down[1]),
                           Math.round(up[0]), Math.round(up[1]), 320);
      if (!r || !r.ok) toast('滑动失败');
    }
    down = null;
  });
}

function mirrorStart() {
  const img = document.getElementById('mirrorImg');
  const hint = document.getElementById('mirrorHint');
  const stat = document.getElementById('mirrorStat');
  if (!img) return;
  img.src = '/stream?t=' + Date.now();
  img.style.display = 'block';
  if (hint) hint.style.display = 'none';
  mirrorOn = true;
  if (stat) stat.textContent = '已连接 · 点画面可直接操作（约 1-2 帧/秒）';
}

function mirrorStop() {
  const img = document.getElementById('mirrorImg');
  const hint = document.getElementById('mirrorHint');
  const stat = document.getElementById('mirrorStat');
  if (img) { img.src = ''; img.style.display = 'none'; }
  if (hint) hint.style.display = 'block';
  mirrorOn = false;
  if (stat) stat.textContent = '已停止';
}

async function shotNow() {
  const r = await call('screenshot');
  if (r && r.ok) toast('截图已保存：' + (r.path || ''));
  else toast('截图失败');
}

async function keySend(k) {
  const r = await call('key_press', k);
  if (!r || !r.ok) toast('按键失败：' + k);
}


/* ================= 启动引导 ================= */

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", tryBoot);
} else {
  tryBoot();
}

/* 兜底：2.6 秒后若还没渲染出侧栏，强制渲染一次 */
setTimeout(function () {
  if (!document.querySelector(".nav-item")) {
    buildSidebar();
    bindWindow();
    bindBtnRipple();
    go("overview");
  }
}, 2600);


/* ---- ADB 直刷（刷机页用） ---- */
async function initAdbFlash() {
  const capEl = document.getElementById('adbFlashCaps');
  const sel = document.getElementById('adbPart');
  if (!sel) return;
  const d = await call('partition_info');
  if (!d || !d.ok) {
    if (capEl) capEl.innerHTML = '<span style="color:var(--red)">读取失败：' + esc((d && d.err) || '未知') + '</span>';
    return;
  }
  const caps = d.caps || {};
  if (capEl) {
    if (caps.flash_adb) {
      capEl.innerHTML = '<span style="color:var(--green)">✓ 可以 ADB 直刷</span>' +
        '（机型 ' + esc(d.model || '?') + '，已识别 ' + (d.parts || []).length + ' 个分区）';
    } else {
      capEl.innerHTML = '<span style="color:var(--red)">✕ 当前不能 ADB 直刷</span>' +
        '：需要 root 权限。' + ((d.reasons || [])[0] ? esc(d.reasons[0]) : '') +
        '<br><span style="color:var(--txt3)">没有 root 时请用上面的 Fastboot 刷写（需 BL 已解锁）。</span>';
    }
  }
  const list = (d.parts || []).filter(p => p.flashable && p.name !== 'userdata');
  sel.innerHTML = list.map(p =>
    '<option value="' + p.name + '">' + p.name + (p.size_h ? '  ' + p.size_h : '') + '</option>'
  ).join('') || '<option value="">（无可用分区）</option>';
  if (!flashImg) flashImg = null;
}

async function adbFlashNow() {
  const sel = document.getElementById('adbPart');
  const part = sel && sel.value;
  if (!part) { toast('请选择目标分区', 'err'); return; }
  if (!flashImg) { toast('请先选择镜像', 'err'); return; }
  if (!confirm('用 ADB 直刷写 ' + part + ' ？\n\n会先自动备份原分区，写入后回读校验；不一致会自动刷回。\n镜像：' + flashImg)) return;
  log('===== ADB 直刷 ' + part + ' =====', 'hdr');
  toast('正在刷写，请勿拔线…');
  const r = await call('flash_partition_adb', part, flashImg);
  if (r && r.ok) {
    toast('刷写完成并校验通过', 'ok');
    log(r.msg, 'ok');
  } else {
    toast('刷写失败', 'err');
    log((r && r.msg) || '未知错误', 'err');
  }
}

/* ================= 投屏 v2（scrcpy 真视频流 / 截图推流 双模式）+ 虚拟手柄 ================= */
let mv2Mode = localStorage.getItem('mv2mode') || 'auto';
let mv2CapsCache = null;

async function renderMirrorV2(wrap) {
  wrap.innerHTML =
    pageHead('投屏 / 截图', '真视频流（scrcpy）或截图推流（兼容模式），都支持点击控制') +
    card('当前设备', '<div id="mv2Caps" class="sub">正在检测…</div>' +
      '<div class="btn-row" style="margin-top:10px">' +
      '<button class="btn blue" onclick="mv2Apply()">按检测结果启动</button>' +
      '<button class="btn ghost" onclick="mv2StopAll()">全部停止</button>' +
      '<button class="btn ghost" onclick="mv2Refresh()">重新检测</button>' +
      '</div>') +
    card('投屏方式', '<div class="term-tabs">' +
      '<button class="term-tab" id="mv2tAuto" onclick="mv2SetMode(\'auto\')">自动（推荐）</button>' +
      '<button class="term-tab" id="mv2tScr" onclick="mv2SetMode(\'scrcpy\')">scrcpy 真视频流</button>' +
      '<button class="term-tab" id="mv2tStream" onclick="mv2SetMode(\'stream\')">截图推流（兼容）</button>' +
      '</div>' +
      '<div id="mv2Hint" class="tip" style="margin-top:10px"></div>' +
      '<div class="sub" style="margin-top:8px">' +
      '· scrcpy：真视频流，流畅、延迟低、可以鼠标直接点画面，需要机型不拦 app_process（RC Pro / RC Pro 2 / RC Plus / RC1）。<br>' +
      '· 截图推流：DJI RC2 唯一可用的方式，约 1~2 帧/秒，但点击/滑动是真的。' +
      '</div>') +
    card('scrcpy 窗口', '<div id="mv2ScrBox" class="sub">未启动</div>' +
      '<div class="btn-row" style="margin-top:10px">' +
      '<button class="btn blue" onclick="mv2StartScrcpy()">启动 scrcpy</button>' +
      '<button class="btn ghost" onclick="mv2StopScrcpy()">停止 scrcpy</button>' +
      '<button class="btn ghost" onclick="mv2StartScrcpy(true)">启动并录制</button>' +
      '</div>') +
    card('截图推流画面', '<div class="btn-row">' +
      '<button class="btn blue" onclick="mv2StartStream()">开始</button>' +
      '<button class="btn ghost" onclick="mv2StopStream()">停止</button>' +
      '<button class="btn ghost" onclick="mv2Shot()">截一张图</button>' +
      '<button class="btn ghost" onclick="mv2Key(\'home\')">Home</button>' +
      '<button class="btn ghost" onclick="mv2Key(\'back\')">返回</button>' +
      '</div>' +
      '<div id="mv2Box" style="margin-top:12px"><div class="empty">点「开始」后这里显示遥控器画面（约 1~2 帧/秒）</div></div>');
  mv2UpdateTabs();
  await mv2Refresh();
}

function mv2UpdateTabs() {
  ['auto', 'scrcpy', 'stream'].forEach(m => {
    const el = document.getElementById('mv2t' + m.charAt(0).toUpperCase() + m.slice(1));
    if (el) el.classList.toggle('on', mv2Mode === m);
  });
  const hint = document.getElementById('mv2Hint');
  if (hint) {
    hint.textContent = mv2Mode === 'auto'
      ? '自动：能跑 scrcpy 就用 scrcpy，跑不了就退回截图推流。'
      : (mv2Mode === 'scrcpy' ? '强制 scrcpy：RC2 上会启动失败（app_process 被拦），失败后可手动切回截图推流。'
        : '强制截图推流：任何机型都能用，但只有 1~2 帧/秒。');
  }
}

function mv2SetMode(m) {
  mv2Mode = m;
  localStorage.setItem('mv2mode', m);
  mv2UpdateTabs();
}

async function mv2Refresh() {
  const box = document.getElementById('mv2Caps');
  if (box) box.textContent = '正在检测…';
  const d = await call('mirror_status');
  mv2CapsCache = d;
  if (!box) return;
  if (!d || !d.ok) { box.textContent = '检测失败：' + ((d && d.msg) || '接口无响应'); return; }
  box.innerHTML = '机型：<b>' + esc(d.model || '未连接') + '</b>' +
    (d.profile ? '（' + esc(d.profile) + '）' : '') +
    ' · scrcpy.exe：' + (d.scrcpy_exe ? '有' : '缺失') +
    ' · app_process：' + (d.app_process === true ? '可用' : (d.app_process === false ? '被拦' : '未知')) +
    '<br>' + esc(d.tip || '');
}

async function mv2Apply() {
  const d = mv2CapsCache || await call('mirror_status');
  if (!d || !d.connected) { toast('没检测到设备'); return; }
  const useScr = mv2Mode === 'scrcpy' || (mv2Mode === 'auto' && d.suggest_scrcpy);
  if (useScr) {
    const r = await call('mirror_scrcpy_start', 1920, 60, '8M', false);
    if (r && r.ok) { toast('scrcpy 已启动（独立窗口）'); mv2PaintScr(r); return; }
    toast('scrcpy 起不来，改用截图推流');
  }
  await mv2StartStream();
}

function mv2PaintScr(r) {
  const b = document.getElementById('mv2ScrBox');
  if (b) b.innerHTML = (r && r.ok) ? ('运行中 · pid ' + (r.pid || '') + ' · ' + esc(r.msg || '')) : '未启动';
}

async function mv2StartScrcpy(record) {
  const r = await call('mirror_scrcpy_start', 1920, 60, '8M', !!record);
  mv2PaintScr(r);
  toast(r && r.ok ? 'scrcpy 已启动（独立窗口）' : ('启动失败：' + ((r && (r.err || r.msg)) || '')));
}

async function mv2StopScrcpy() {
  const r = await call('mirror_scrcpy_stop');
  mv2PaintScr(null);
  toast(r && r.ok ? '已停止 scrcpy' : '停止失败');
}

function mv2StopAll() { mv2StopScrcpy(); mv2StopStream(); }

async function mv2StartStream() {
  const box = document.getElementById('mv2Box');
  if (box) box.innerHTML = '<img id="mv2Img" style="width:100%;border-radius:12px;display:block" src="/stream?t=' + Date.now() + '">' +
    '<div class="sub" style="margin-top:8px">点画面=点击遥控器，拖动=滑动</div>';
  const img = document.getElementById('mv2Img');
  if (img) {
    img.onload = () => { if (!img.dataset.w) { img.dataset.w = img.naturalWidth; img.dataset.h = img.naturalHeight; } };
    img.onmousedown = e => { img._sx = e.offsetX; img._sy = e.offsetY; };
    img.onmouseup = e => {
      const sx = img._sx, sy = img._sy, ex = e.offsetX, ey = e.offsetY;
      const w = parseInt(img.dataset.w || img.naturalWidth || 1920);
      const h = parseInt(img.dataset.h || img.naturalHeight || 1080);
      const kx = w / img.clientWidth, ky = h / img.clientHeight;
      const x1 = sx * kx, y1 = sy * ky, x2 = ex * kx, y2 = ey * ky;
      if (Math.hypot(ex - sx, ey - sy) < 12) call('tap_xy', Math.round(x2), Math.round(y2));
      else call('swipe_xy', Math.round(x1), Math.round(y1), Math.round(x2), Math.round(y2), 180);
    };
  }
  toast('截图推流已开始');
}

function mv2StopStream() {
  const box = document.getElementById('mv2Box');
  if (box) box.innerHTML = '<div class="empty">已停止</div>';
}

async function mv2Shot() {
  const r = await call('screenshot');
  toast((r && r.ok) ? ('已保存：' + (r.path || r.file || '')) : '截图失败');
}

async function mv2Key(k) { await call('key_press', k); }

/* ---------------- 虚拟手柄 ---------------- */
let padTimer = null;

async function renderPad(wrap) {
  wrap.innerHTML =
    pageHead('虚拟手柄', '把遥控器摇杆变成电脑上的 Xbox 360 手柄（ViGEm）') +
    card('状态', '<div id="padStat" class="sub">正在检测…</div>' +
      '<div class="btn-row" style="margin-top:10px">' +
      '<button class="btn blue" onclick="padStart()">开始</button>' +
      '<button class="btn ghost" onclick="padStop()">停止</button>' +
      '</div>') +
    card('实时轴值', '<div id="padAxes" class="sub">—</div>' +
      '<div class="sub" style="margin-top:8px">值域 0~2047，中点 1024。左摇杆 ← ax[3]/ax[2]，右摇杆 ← ax[0]/ax[1]。</div>') +
    card('怎么用', '<div class="sub">' +
      '1. 电脑装好 ViGEmBus 驱动（本机已装、vgamepad 已就绪）；<br>' +
      '2. 点「开始」→ 自动执行 <code>adb reverse tcp:9999 tcp:9999</code> 并监听 9999；<br>' +
      '3. 遥控器上跑发流的那一端（RC2ETX 的摇杆转发），把它指向 <code>127.0.0.1:9999</code>，每行一个 JSON：<code>{"ax":[1024,1024,1024,1024,1024,1024]}</code>；<br>' +
      '4. 电脑上会多出一个 Xbox 360 手柄，游戏里直接用。' +
      '</div>');
  await padRefresh();
  if (padTimer) clearInterval(padTimer);
  padTimer = setInterval(() => { if (curPage === 'pad') padRefresh(); }, 800);
}

async function padRefresh() {
  const d = await call('pad_state');
  const s = document.getElementById('padStat');
  if (s) {
    if (!d || !d.ok) s.textContent = '查询失败';
    else s.innerHTML = '运行中：<b>' + (d.running ? '是' : '否') + '</b>' +
      ' · 端口 ' + d.port + ' · ViGEm ' + (d.vgamepad ? '就绪' : '缺失') +
      ' · 连接 ' + esc(d.peer || '无') + ' · 速率 ' + (d.hz || 0) + ' Hz' +
      ' · 样本 ' + (d.count || 0) + (d.err ? '<br><span style="color:#ff453a">' + esc(d.err) + '</span>' : '');
  }
  const a = document.getElementById('padAxes');
  if (a && d && d.axes) {
    a.innerHTML = ['LV', 'LH', 'RV', 'RH', 'P1', 'P2'].map((k, i) =>
      '<div style="display:flex;align-items:center;gap:8px;margin:3px 0">' +
      '<span style="width:32px;color:#8e8e93">' + k + '</span>' +
      '<span style="width:56px;text-align:right">' + d.axes[i] + '</span>' +
      '<span style="flex:1;height:6px;background:rgba(255,255,255,.08);border-radius:3px;overflow:hidden">' +
      '<span style="display:block;height:100%;width:' + Math.round(d.axes[i] / 2047 * 100) + '%;background:#0a84ff"></span></span>' +
      '</div>').join('');
  }
}

async function padStart() {
  const r = await call('pad_start', 9999);
  toast(r && r.ok ? ('已开始（' + (r.msg || '') + '）') : ('启动失败：' + ((r && r.err) || '')));
  padRefresh();
}

async function padStop() {
  const r = await call('pad_stop');
  toast(r && r.ok ? '已停止' : '停止失败');
  padRefresh();
}
