'use strict';
/*
 * wiki-with-willy 的 Obsidian 外掛（D-252～D-265，issue #22）。
 *
 * 純 CommonJS、不打包、不加依賴。要算的都在 kb（kb home / kb find / kb renders apply …），這裡只負責：
 * 找 kb、叫 kb（一律帶 --via obsidian）、把 kb 給的 JSON 畫出來、把按鈕變成 kb 指令（和反悔的相反指令）。
 * 要測的純函式都從 module.exports 的 `lib` 匯出（tests/obsidian/*.test.js 用假的 obsidian 模組載入）。
 * 不把任何路徑寫進設定（D-019）：每次載入照 installed_plugins.json 找 kb.py。
 */

const obsidian = require('obsidian');
const fs = require('fs');
const os = require('os');
const path = require('path');
const childProcess = require('child_process');

const { Plugin, ItemView, Modal, Menu, Notice, MarkdownView } = obsidian;

// ---------------------------------------------------------------------------------------------------------------
// 常數
// ---------------------------------------------------------------------------------------------------------------

const PLUGIN_ID = 'wiki-with-willy';
const VIEW_TYPE = 'wiki-with-willy-home';
const WATCH_FILES = ['agenda.json', 'pending.json', 'entities.json', 'inventory.json', 'profile.json'];
const DEBOUNCE_MS = 300;
const OPENED_MAX = 30;
const KB_TIMEOUT_MS = 120000;
const LANE_HEIGHT = 26;
const KIND_LABEL = { deadline: '到期', meeting: '會議', promise: '承諾', reminder: '提醒', period: '期間' };
const KNOWN_KINDS = Object.keys(KIND_LABEL);
const KIND_BY_LABEL = { 到期: 'deadline', 會議: 'meeting', 承諾: 'promise', 提醒: 'reminder', 期間: 'period' };
const KNOWN_SHAPES = ['bar', 'point'];
const WEEKDAY = ['日', '一', '二', '三', '四', '五', '六'];
const MANAGED_PAGES = ['系統/日程.md', '系統/待處理.md', '系統/裁示.md'];
const GENERATED_BANNER = '這頁由程式產生；要改請在首頁改，或直接跟 Claude 說';
const NO_KB_TEXT = '找不到 wiki-with-willy：先在 Claude 裡打開這個知識庫一次';
const VERSION_MISMATCH_TEXT = '首頁跟 wiki-with-willy 版本不同，先在 Claude 裡打開這個知識庫一次';
const RELOAD_TEXT = '首頁更新了，按這裡重新載入';
const COPIED_TEXT = '已複製，貼到 Claude 的對話裡';
const NEED_CLAUDE_TEXT = '到對話跟 Claude 說';
const CARRIED_TEXT = '你剛在這頁改的我留在最下面『你加的』';
const UNRECOGNIZED_TEXT = '這頁你改的我沒認出來，記在待處理了';
const UPDATED_TEXT = '這頁剛被更新了';
const CARD_REF_RE = /〔(f-[0-9a-f]{4,})〕/g;

// ---------------------------------------------------------------------------------------------------------------
// 小工具
// ---------------------------------------------------------------------------------------------------------------

/** setTimeout，但不拖住 node（測試用）；Obsidian 裡回的是數字，沒有 unref。 */
function softTimeout(fn, ms) {
  const t = setTimeout(fn, ms);
  if (t && typeof t.unref === 'function') t.unref();
  return t;
}

function firstLine(text) {
  for (const line of String(text == null ? '' : text).split(/\r?\n/)) {
    const t = line.trim();
    if (t) return t;
  }
  return '';
}

function asArray(v) {
  return Array.isArray(v) ? v : [];
}

function isObject(v) {
  return v !== null && typeof v === 'object' && !Array.isArray(v);
}

function parseJson(text) {
  const t = String(text == null ? '' : text).trim();
  if (!t) return null;
  try {
    return JSON.parse(t);
  } catch (e) {
    // 前面若有別的輸出，取最後一行像 JSON 的
    const lines = t.split(/\r?\n/).reverse();
    for (const line of lines) {
      const s = line.trim();
      if (s.startsWith('{') || s.startsWith('[')) {
        try {
          return JSON.parse(s);
        } catch (e2) {
          // 繼續找
        }
      }
    }
  }
  return null;
}

function samePath(a, b, platform) {
  const plat = platform || process.platform;
  const norm = (p) => {
    let s = String(p == null ? '' : p).replace(/\\/g, '/').replace(/\/+$/, '');
    if (plat === 'win32' || plat === 'darwin') s = s.toLowerCase();
    return s;
  };
  return norm(a) !== '' && norm(a) === norm(b);
}

function isNetworkPath(p) {
  const s = String(p == null ? '' : p);
  if (s.startsWith('\\\\?\\')) return false; // 本機長路徑前綴
  return s.startsWith('\\\\') || /^\/\/[^/]/.test(s);
}

function nativePath(p, platform) {
  const plat = platform || process.platform;
  const s = String(p == null ? '' : p);
  if (plat === 'win32' && !isNetworkPath(s)) return s.replace(/\//g, '\\');
  return s;
}

// ---------------------------------------------------------------------------------------------------------------
// 日期與時間軸的幾何（kb 算好什麼時候、哪一列；這裡只換成畫面上的位置）
// ---------------------------------------------------------------------------------------------------------------

const DATE_RE = /^(\d{4})-(\d{2})-(\d{2})/;

function dayNumber(s) {
  const m = DATE_RE.exec(String(s == null ? '' : s));
  if (!m) return null;
  const n = Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return Number.isNaN(n) ? null : Math.round(n / 86400000);
}

function dayToIso(n) {
  return new Date(n * 86400000).toISOString().slice(0, 10);
}

function weekdayOf(n) {
  return new Date(n * 86400000).getUTCDay();
}

function shortDate(iso) {
  const n = dayNumber(iso);
  if (n === null) return '';
  const d = new Date(n * 86400000);
  return `${d.getUTCMonth() + 1}/${d.getUTCDate()}`;
}

function formatWhen(item) {
  const date = itemDate(item);
  const n = dayNumber(date);
  if (n === null) return '';
  let text = `${shortDate(date)}（週${WEEKDAY[weekdayOf(n)]}）`;
  if (item.time) text += ` ${item.time}`;
  return text;
}

function itemDate(m) {
  return (m && (m.end || m.date || m.ended || m.start)) || '';
}

/** 期間：時間軸的 mark 是英文 period，kb lookup 的日程是中文「期間」。 */
function isPeriodKind(kind) {
  return kind === 'period' || kind === '期間';
}

function kindLabel(kind) {
  return KIND_LABEL[kind] || KIND_LABEL[KIND_BY_LABEL[kind]] || String(kind || '');
}

/** 一筆 mark 在時間軸上的起訖（天數）；不認得的 shape／kind、日期壞掉回 null（不畫那筆、不報錯）。 */
function markSpan(m) {
  if (!isObject(m)) return null;
  if (m.shape !== undefined && m.shape !== null && !KNOWN_SHAPES.includes(m.shape)) return null;
  if (m.kind !== undefined && m.kind !== null && !KNOWN_KINDS.includes(m.kind)) return null;
  const s = dayNumber(m.start);
  const e = dayNumber(m.end || m.date || m.ended);
  const shape = m.shape || (s !== null && e !== null && s !== e ? 'bar' : 'point');
  if (s === null && e === null) return null;
  if (shape === 'point') {
    const at = e !== null ? e : s;
    return { shape, first: at, last: at };
  }
  const a = s !== null ? s : e;
  const b = e !== null ? e : s;
  return { shape, first: Math.min(a, b), last: Math.max(a, b) };
}

function baselineSpan(b) {
  if (!b) return null;
  if (typeof b === 'string') {
    const n = dayNumber(b);
    return n === null ? null : { first: n, last: n };
  }
  if (!isObject(b)) return null;
  const s = dayNumber(b.start);
  const e = dayNumber(b.end || b.date);
  if (s === null && e === null) return null;
  const a = s !== null ? s : e;
  const z = e !== null ? e : s;
  return { first: Math.min(a, z), last: Math.max(a, z) };
}

/**
 * 時間軸資料 → 每一列的 bar／點的位置（百分比）與 lane（同一列疊幾層）。
 * 回 {fromN, toN, spanDays, ticks, todayPct, rows:[{key,label,type,progress,lanes,marks,pauses,links}]}。
 * 不認得的 shape／kind、壞日期的那筆不畫；children 縮排畫在母項下面；links 回兩端的位置；baseline 回原定的位置。
 */
function layoutTimeline(timeline, opts) {
  const options = opts || {};
  const tl = isObject(timeline) ? timeline : {};
  const rowsIn = asArray(tl.rows).filter(isObject);
  let fromN = dayNumber(tl.from);
  let toN = dayNumber(tl.to);
  const todayN = dayNumber(options.today);
  if (fromN === null || toN === null || toN < fromN) {
    const all = [];
    for (const r of rowsIn) {
      for (const m of asArray(r.marks)) {
        const sp = markSpan(m);
        if (sp) all.push(sp.first, sp.last);
      }
    }
    const base = todayN !== null ? todayN : Math.floor(Date.now() / 86400000);
    all.push(base - 7, base + 60);
    fromN = Math.min(...all);
    toN = Math.max(...all);
  }
  const span = toN - fromN + 1;
  const pct = (n) => ((n - fromN) / span) * 100;
  const minWidth = Math.max(0.5, 100 / span);

  function geom(sp) {
    const lo = Math.max(sp.first, fromN);
    const hi = Math.min(sp.last, toN);
    if (hi < lo) return null;
    const left = pct(lo);
    const width = Math.max(pct(hi + 1) - left, minWidth);
    return {
      leftPct: left,
      widthPct: Math.min(width, 100 - left),
      clippedLeft: sp.first < fromN,
      clippedRight: sp.last > toN,
    };
  }

  function drawMark(m, depth) {
    const sp = markSpan(m);
    if (!sp) return null;
    const g = geom(sp);
    if (!g) return null;
    const out = {
      id: m.id || null,
      shape: sp.shape,
      kind: m.kind || null,
      text: m.text || '',
      status: m.status || 'open',
      late: m.late === true,
      inferred: m.inferred === true,
      critical: m.critical === true,
      hard: m.hard === true,
      derived: m.derived === true,
      slack: m.slack === undefined ? null : m.slack,
      time: m.time || null,
      start: m.start || null,
      end: m.end || m.date || null,
      repeat: m.repeat || null,
      entities: asArray(m.entities),
      depth,
      lane: 0,
      leftPct: g.leftPct,
      widthPct: sp.shape === 'point' ? 0 : g.widthPct,
      clippedLeft: g.clippedLeft,
      clippedRight: g.clippedRight,
      baseline: null,
      raw: m,
    };
    if (sp.shape === 'point') {
      out.leftPct = pct(Math.max(sp.first, fromN)) + 0.5 * (100 / span);
    }
    const bl = baselineSpan(m.baseline);
    if (bl) {
      const bg = geom(bl);
      if (bg) out.baseline = { leftPct: bg.leftPct, widthPct: bg.widthPct };
    }
    return out;
  }

  const rows = [];
  for (const r of rowsIn) {
    const tops = [];
    for (const m of asArray(r.marks)) {
      const d = drawMark(m, 0);
      if (!d) continue;
      const kids = [];
      for (const c of asArray(m.children)) {
        const cd = drawMark(c, 1);
        if (cd) kids.push(cd);
      }
      tops.push({ mark: d, kids, sort: markSpan(m).first });
    }
    tops.sort((a, b) => a.sort - b.sort);
    const lanes = []; // 每層最後佔到的位置（百分比）；exclusive 的層不再放別人
    const placed = [];
    const labelReserve = 14; // 點的字大約佔的寬度（百分比）
    for (const t of tops) {
      const m = t.mark;
      const need = m.shape === 'point' ? m.leftPct + labelReserve : m.leftPct + m.widthPct;
      if (t.kids.length === 0) {
        let lane = lanes.findIndex((l) => !l.exclusive && l.end <= m.leftPct - 0.2);
        if (lane < 0) {
          lanes.push({ end: 0, exclusive: false });
          lane = lanes.length - 1;
        }
        lanes[lane].end = need;
        m.lane = lane;
        placed.push(m);
      } else {
        lanes.push({ end: need, exclusive: true });
        m.lane = lanes.length - 1;
        placed.push(m);
        for (const k of t.kids) {
          lanes.push({ end: 100, exclusive: true });
          k.lane = lanes.length - 1;
          k.parent = m.id;
          placed.push(k);
        }
      }
    }
    const byId = {};
    for (const m of placed) if (m.id) byId[m.id] = m;
    const links = [];
    for (const l of asArray(r.links)) {
      if (!isObject(l)) continue;
      const a = byId[l.from];
      const b = byId[l.to];
      if (!a || !b) continue;
      links.push({
        from: l.from,
        to: l.to,
        gap: l.gap === undefined ? null : l.gap,
        critical: l.critical === true,
        x1: a.shape === 'point' ? a.leftPct : a.leftPct + a.widthPct,
        y1: a.lane,
        x2: b.leftPct,
        y2: b.lane,
      });
    }
    const pauses = [];
    for (const p of asArray(r.pauses)) {
      if (!isObject(p)) continue;
      const s = dayNumber(p.start);
      const e = dayNumber(p.end);
      if (s === null && e === null) continue;
      const g = geom({ first: s !== null ? s : e, last: e !== null ? e : s });
      if (g) pauses.push({ leftPct: g.leftPct, widthPct: g.widthPct });
    }
    rows.push({
      key: r.key || r.label || '',
      label: r.label || r.key || '',
      type: r.type || null,
      progress: r.progress || null,
      lanes: Math.max(1, lanes.length),
      marks: placed,
      pauses,
      links,
    });
  }

  // 軸上的刻度：每個月 1 號、每週一
  const ticks = [];
  for (let n = fromN; n <= toN; n++) {
    const d = new Date(n * 86400000);
    if (d.getUTCDate() === 1) {
      const label = d.getUTCMonth() === 0 || n === fromN ? `${d.getUTCFullYear()}/${d.getUTCMonth() + 1}月` : `${d.getUTCMonth() + 1}月`;
      ticks.push({ date: dayToIso(n), pct: pct(n), label, kind: 'month' });
    } else if (d.getUTCDay() === 1 && span <= 120) {
      ticks.push({ date: dayToIso(n), pct: pct(n), label: String(d.getUTCDate()), kind: 'week' });
    }
  }
  const todayPct = todayN !== null && todayN >= fromN && todayN <= toN ? pct(todayN) + 0.5 * (100 / span) : null;
  return { fromN, toN, from: dayToIso(fromN), to: dayToIso(toN), spanDays: span, ticks, todayPct, rows };
}

/** 月曆：回 {year, month, weeks:[[{date, day, inMonth, isToday, marks:[…]}]×7]}。bar 每天都列，點只在那天。 */
function layoutMonth(timeline, opts) {
  const options = opts || {};
  const todayN = dayNumber(options.today);
  const base = todayN !== null ? new Date(todayN * 86400000) : new Date();
  const year = options.year !== undefined ? options.year : base.getUTCFullYear();
  const month = options.month !== undefined ? options.month : base.getUTCMonth(); // 0~11
  const first = Math.round(Date.UTC(year, month, 1) / 86400000);
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const startN = first - weekdayOf(first); // 星期日起算
  const endN = first + lastDay - 1;
  const gridEnd = endN + (6 - weekdayOf(endN));
  const flat = [];
  for (const r of asArray(isObject(timeline) ? timeline.rows : [])) {
    if (!isObject(r)) continue;
    const stack = [];
    for (const m of asArray(r.marks)) {
      stack.push(m);
      for (const c of asArray(m.children)) stack.push(c);
    }
    for (const m of stack) {
      const sp = markSpan(m);
      if (sp) flat.push({ m, sp, row: r.label || r.key || '' });
    }
  }
  const weeks = [];
  for (let n = startN; n <= gridEnd; n += 7) {
    const week = [];
    for (let i = 0; i < 7; i++) {
      const day = n + i;
      const inMonth = day >= first && day <= endN;
      const marks = [];
      for (const f of flat) {
        if (day < f.sp.first || day > f.sp.last) continue;
        marks.push({
          id: f.m.id || null,
          text: f.m.text || '',
          kind: f.m.kind || null,
          row: f.row,
          late: f.m.late === true,
          inferred: f.m.inferred === true,
          status: f.m.status || 'open',
          continues: f.sp.shape === 'bar' && day > f.sp.first,
          raw: f.m,
        });
      }
      week.push({
        date: dayToIso(day),
        day: new Date(day * 86400000).getUTCDate(),
        inMonth,
        isToday: todayN === day,
        marks,
      });
    }
    weeks.push(week);
  }
  return { year, month, weeks };
}

function shiftMonth(year, month, delta) {
  const d = new Date(Date.UTC(year, month + delta, 1));
  return { year: d.getUTCFullYear(), month: d.getUTCMonth() };
}

function describeMark(m) {
  const kind = kindLabel(m.kind);
  let when = '';
  if (m.start && m.end && m.start !== m.end) when = `${m.start}～${m.end}`;
  else when = m.end || m.start || '';
  const bits = [`${kind ? kind + ' ' : ''}${m.text || ''}`.trim()];
  if (when) bits.push(`${when}${m.time ? ' ' + m.time : ''}`);
  if (m.late) bits.push('已經晚了');
  if (m.inferred) bits.push('推測的，還沒確認');
  if (m.status === 'done') bits.push('已完成');
  if (m.critical) bits.push('要徑');
  return bits.join('\n');
}

// ---------------------------------------------------------------------------------------------------------------
// kb home 的資料整理
// ---------------------------------------------------------------------------------------------------------------

function normalizeHome(raw) {
  const r = isObject(raw) ? raw : {};
  const todo = isObject(r.todo) ? r.todo : {};
  const counts = isObject(r.counts) ? r.counts : {};
  return {
    schema: r.schema || null,
    version: r.version || null,
    today: r.today || null,
    cheer: typeof r.cheer === 'string' ? r.cheer : '',
    counts: {
      overdue: Number(counts.overdue) || 0,
      today: Number(counts.today) || 0,
      week: Number(counts.week) || 0,
      confirm: Number(counts.confirm) || 0,
      other: Number(counts.other) || 0,
    },
    timeline: isObject(r.timeline) ? r.timeline : { rows: [] },
    todo: { overdue: asArray(todo.overdue), today: asArray(todo.today), week: asArray(todo.week) },
    confirm: asArray(r.confirm).filter(isObject),
    others: asArray(r.others).filter(isObject),
    recent: asArray(r.recent).filter(isObject),
  };
}

function todoGroups(home) {
  const t = home && home.todo ? home.todo : {};
  return [
    { key: 'overdue', label: '已經過了', items: asArray(t.overdue), defaultCollapsed: false },
    { key: 'today', label: '今天', items: asArray(t.today), defaultCollapsed: false },
    { key: 'week', label: '這週', items: asArray(t.week), defaultCollapsed: true },
  ];
}

function versionMismatch(homeVersion, pluginVersion) {
  return !!homeVersion && !!pluginVersion && String(homeVersion) !== String(pluginVersion);
}

function manifestChanged(loadedVersion, diskText) {
  const m = parseJson(diskText);
  return !!(m && m.version && loadedVersion && String(m.version) !== String(loadedVersion));
}

function sanitizeData(raw) {
  const opened = [];
  const seen = new Set();
  for (const o of asArray(isObject(raw) ? raw.opened : [])) {
    if (!isObject(o) || typeof o.card !== 'string' || !/^f-[0-9a-f]+$/.test(o.card)) continue;
    if (seen.has(o.card)) continue;
    seen.add(o.card);
    opened.push({ card: o.card, at: typeof o.at === 'string' ? o.at : '' });
  }
  return { opened: opened.slice(0, OPENED_MAX) };
}

/** 開過的卡編號放最前面、不重複、最多 30 筆；只存編號與時間（D-262）。 */
function recordOpened(data, card, nowIso) {
  const base = sanitizeData(data);
  if (typeof card !== 'string' || !/^f-[0-9a-f]+$/.test(card)) return base;
  const rest = base.opened.filter((o) => o.card !== card);
  return { opened: [{ card, at: nowIso || new Date().toISOString() }, ...rest].slice(0, OPENED_MAX) };
}

function openedIds(data) {
  return sanitizeData(data).opened.map((o) => o.card);
}

function homeArgs(ids) {
  const args = ['home', '--json'];
  if (ids && ids.length) args.push('--opened', ids.join(','));
  return args;
}

// ---------------------------------------------------------------------------------------------------------------
// 找 kb、叫 kb
// ---------------------------------------------------------------------------------------------------------------

function claudeDir(env, home) {
  const c = env && env.CLAUDE_CONFIG_DIR;
  return c ? c : path.join(home, '.claude');
}

/**
 * 照 installed_plugins.json 找 wiki-with-willy 的 kb.py（D-258）。
 * 多筆時先挑 projectPath 是這個知識庫的，再挑 scope user 的，最後一筆。回 {ok, kbPath, …} 或 {ok:false, reason}。
 */
function findKb(opts) {
  const o = opts || {};
  const env = o.env || process.env;
  const home = o.home || os.homedir();
  const readFile = o.readFile || ((p) => fs.readFileSync(p, 'utf8'));
  const exists = o.exists || ((p) => fs.existsSync(p));
  const platform = o.platform || process.platform;
  const file = path.join(claudeDir(env, home), 'plugins', 'installed_plugins.json');
  let data;
  try {
    data = JSON.parse(readFile(file, 'utf8'));
  } catch (e) {
    return { ok: false, reason: 'no-installed-file' };
  }
  const plugins = isObject(data) && isObject(data.plugins) ? data.plugins : {};
  const records = [];
  for (const key of Object.keys(plugins)) {
    if (key !== PLUGIN_ID && !key.startsWith(PLUGIN_ID + '@')) continue;
    for (const rec of asArray(plugins[key])) {
      if (isObject(rec) && typeof rec.installPath === 'string' && rec.installPath) records.push(Object.assign({ key }, rec));
    }
  }
  if (!records.length) return { ok: false, reason: 'not-installed' };
  const withKb = records
    .map((r) => ({ rec: r, kbPath: path.join(r.installPath, 'scripts', 'kb.py') }))
    .filter((x) => exists(x.kbPath));
  if (!withKb.length) return { ok: false, reason: 'no-kb' };
  const mine = withKb.find((x) => x.rec.projectPath && o.vaultPath && samePath(x.rec.projectPath, o.vaultPath, platform));
  const user = withKb.find((x) => (x.rec.scope || 'user') === 'user');
  const pick = mine || user || withKb[withKb.length - 1];
  return {
    ok: true,
    kbPath: pick.kbPath,
    installPath: pick.rec.installPath,
    version: pick.rec.version || null,
    scope: pick.rec.scope || 'user',
    projectPath: pick.rec.projectPath || null,
  };
}

function pythonCandidates(platform) {
  const plat = platform || process.platform;
  if (plat === 'win32') return [{ cmd: 'python', pre: [] }, { cmd: 'py', pre: ['-3'] }];
  return [{ cmd: 'python3', pre: [] }, { cmd: 'python', pre: [] }];
}

/** 整個 argv：[…pre, kb.py, '--via', 'obsidian', …子命令與參數]（--via 一定緊接 kb.py）。 */
function buildKbArgs(kbPath, args, pre) {
  return [...asArray(pre), kbPath, '--via', 'obsidian', ...asArray(args).map(String)];
}

function createKbRunner(cfg) {
  const execFile = cfg.execFile || childProcess.execFile;
  const pythons = cfg.pythons || pythonCandidates(cfg.platform);
  let chosen = null;

  function once(py, args) {
    return new Promise((resolve) => {
      const argv = buildKbArgs(cfg.kbPath, args, py.pre);
      const options = {
        cwd: cfg.cwd,
        env: Object.assign({}, cfg.env || process.env, { PYTHONIOENCODING: 'utf-8' }),
        windowsHide: true,
        encoding: 'utf8',
        maxBuffer: 64 * 1024 * 1024,
        timeout: cfg.timeoutMs || KB_TIMEOUT_MS,
      };
      try {
        execFile(py.cmd, argv, options, (err, stdout, stderr) => {
          if (!err) return resolve({ code: 0, stdout: String(stdout || ''), stderr: String(stderr || '') });
          const missing = err.code === 'ENOENT' || err.code === 9009;
          const code = typeof err.code === 'number' ? err.code : err.killed ? -2 : -1;
          resolve({
            code,
            stdout: String(stdout || ''),
            stderr: String(stderr || '') || (missing ? '' : String(err.message || '')),
            missing,
          });
        });
      } catch (e) {
        resolve({ code: -1, stdout: '', stderr: String(e && e.message), missing: e && e.code === 'ENOENT' });
      }
    });
  }

  async function run(args) {
    const order = chosen ? [chosen] : pythons;
    let last = null;
    for (const py of order) {
      const res = await once(py, args);
      if (res.missing) {
        last = res;
        continue;
      }
      chosen = py;
      return res;
    }
    return { code: -1, stdout: '', stderr: '找不到 Python（試過 ' + pythons.map((p) => p.cmd).join('、') + '）', missing: true, last };
  }

  return { run, buildArgs: (args, py) => buildKbArgs(cfg.kbPath, args, (py || pythons[0]).pre) };
}

/** exit 0 = ok；exit 3 = kb 的拒絕句原樣；其他 = 「沒做成：<stderr 第一行>」。 */
function classify(res) {
  if (res.code === 0) return { kind: 'ok' };
  if (res.code === 3) {
    return { kind: 'refused', message: firstLine(res.stdout) || firstLine(res.stderr) || '沒做成' };
  }
  return { kind: 'failed', message: '沒做成：' + (firstLine(res.stderr) || firstLine(res.stdout) || `結束碼 ${res.code}`) };
}

/** `--check --json` 的結果：{error} | {refuse} | {effects}。refuse 有字時 kb 會 exit 3，但 JSON 照印。 */
function interpretCheck(res) {
  const j = parseJson(res.stdout);
  if (isObject(j) && (Array.isArray(j.effects) || j.refuse !== undefined)) {
    if (j.refuse) return { refuse: String(j.refuse) };
    if (res.code === 0 || res.code === 3) return { effects: asArray(j.effects).map(String) };
  }
  const c = classify(res);
  if (c.kind === 'ok') return { effects: [] };
  return c.kind === 'refused' ? { refuse: c.message } : { error: c.message };
}

// ---------------------------------------------------------------------------------------------------------------
// 動作（D-254、D-256）：每個動作 = 指令 + 反悔的相反指令；有連帶影響的先 --check 跳確認框
// ---------------------------------------------------------------------------------------------------------------

const PROGRESS_WORD = { ongoing: '進行中', active: '進行中', closed: '結案', paused: '擱置', 進行中: '進行中', 結案: '結案', 擱置: '擱置' };

function progressWord(p) {
  return PROGRESS_WORD[p] || null;
}

function putFlag(args, flag, value) {
  if (value !== undefined && value !== null && value !== '') args.push(flag, String(value));
}

const actions = {
  /** 打勾：done；復原 reopen（重複的日程完成會跳到下一次，復原改回原日期）。 */
  done(item) {
    const id = item.id;
    return {
      id: 'done',
      args: ['agenda', 'done', id],
      undo: () => {
        if (item.repeat && itemDate(item)) return { args: ['agenda', 'edit', id, '--date', itemDate(item)] };
        return { args: ['agenda', 'reopen', id] };
      },
    };
  },

  /** 改日期、時間：只送有變的；復原改回原值（原本沒有時間的沒辦法清掉，那一項不復原）。 */
  edit(item, change) {
    const id = item.id;
    const args = ['agenda', 'edit', id];
    const back = ['agenda', 'edit', id];
    const orig = { date: itemDate(item), start: item.start || '', time: item.time || '' };
    let backable = false;
    let any = false;
    for (const [key, flag] of [['date', '--date'], ['start', '--start'], ['time', '--time']]) {
      const v = change[key];
      if (v === undefined || v === null || v === '' || v === orig[key]) continue;
      args.push(flag, v);
      any = true;
      if (orig[key]) {
        back.push(flag, orig[key]);
        backable = true;
      }
    }
    if (!any) return null;
    return { id: 'edit', args, undo: backable ? () => ({ args: back }) : null };
  },

  /** 推測的記成確認：不帶欄位；不給復原。 */
  confirmInferred(item) {
    return { id: 'confirm-inferred', args: ['agenda', 'edit', item.id], undo: null };
  },

  /** 新增日程；復原 = 取消新的那一條。 */
  add(form) {
    const args = ['agenda', 'add'];
    putFlag(args, '--kind', form.kind);
    putFlag(args, '--date', form.date);
    putFlag(args, '--text', form.text);
    putFlag(args, '--start', form.start);
    putFlag(args, '--time', form.time);
    for (const e of asArray(form.entities)) putFlag(args, '--entity', e);
    args.push('--json');
    return {
      id: 'add',
      args,
      json: true,
      toastText: (j) => (j && j.item ? `已加進日程：${j.item.text || form.text}` : '已加進日程'),
      undo: (j) => (j && j.created !== false && j.item && j.item.id ? { args: ['agenda', 'cancel', j.item.id] } : null),
    };
  },

  /** 取消；有期間的先 --check 跳確認框。復原 reopen。 */
  cancel(item) {
    const a = {
      id: 'cancel',
      args: ['agenda', 'cancel', item.id],
      undo: () => ({ args: ['agenda', 'reopen', item.id] }),
    };
    if (isPeriodKind(item.kind)) {
      a.check = {
        args: ['agenda', 'cancel', item.id, '--check', '--json'],
        title: `取消「${item.text || ''}」？`,
        okText: '取消這件',
      };
    }
    return a;
  },

  /** 其他要處理的「不用管」；不給復原。 */
  dismiss(pendingId) {
    return { id: 'dismiss', args: ['pending', 'dismiss', pendingId], undo: null };
  },

  /** 「要你確認的」選一個結果：照 argv；`{name}` 換成她填的；不給復原。argv 是 null 的不是指令（回 null）。 */
  result(result, fillValue) {
    if (!isObject(result) || !Array.isArray(result.argv)) return null;
    const fill = result.fill;
    const tokens = ['{name}'];
    if (isObject(fill) && fill.name) tokens.push(`{${fill.name}}`);
    const args = result.argv.map((a) => {
      let s = String(a);
      if (fillValue !== undefined && fillValue !== null) for (const t of tokens) s = s.split(t).join(fillValue);
      return s;
    });
    return { id: 'result', args, undo: null };
  },

  /** 結案、擱置、改回進行中；先 --check。復原 = 改回原狀態。 */
  progress(name, state, oldState) {
    const word = progressWord(state);
    const oldWord = progressWord(oldState);
    return {
      id: 'progress',
      check: { args: ['entity', 'progress', name, word, '--check', '--json'], title: `${name}記成${word}？`, okText: `記成${word}` },
      args: ['entity', 'progress', name, word],
      undo: oldWord ? () => ({ args: ['entity', 'progress', name, oldWord] }) : null,
    };
  },

  /** 改名；先 --check。復原 = 改回原名。 */
  rename(oldName, newName) {
    return {
      id: 'rename',
      check: { args: ['entity', 'rename', oldName, '--to', newName, '--check', '--json'], title: `把「${oldName}」改名叫「${newName}」？`, okText: '改名' },
      args: ['entity', 'rename', oldName, '--to', newName],
      undo: () => ({ args: ['entity', 'rename', newName, '--to', oldName] }),
    };
  },

  /** 合併；先 --check。復原 = kb versions revert（只挑 Obsidian 那組，D-255）；被擋就把拒絕句印在框裡。 */
  merge(source, target) {
    return {
      id: 'merge',
      check: { args: ['entity', 'merge', source, '--into', target, '--check', '--json'], title: `把「${source}」併進「${target}」？`, okText: '合併' },
      args: ['entity', 'merge', source, '--into', target],
      undo: () => ({ args: ['versions', 'revert'], refusalModal: true }),
    };
  },

  /** 加、拿掉別名；復原 = 相反。 */
  alias(name, word, mode) {
    const adding = mode !== 'remove';
    return {
      id: adding ? 'alias-add' : 'alias-remove',
      args: ['entity', 'alias', name, adding ? '--add' : '--remove', word],
      undo: () => ({ args: ['entity', 'alias', name, adding ? '--remove' : '--add', word] }),
    };
  },

  /** 改標籤；復原 = 改回原標籤（原本空的 = 欄=）。 */
  tag(name, field, words, oldWords) {
    return {
      id: 'tag',
      args: ['entity', 'tag', name, `${field}=${asArray(words).join(',')}`, '--said'],
      undo: () => ({ args: ['entity', 'tag', name, `${field}=${asArray(oldWords).join(',')}`, '--said'] }),
    };
  },
};

async function runUndo(ctx, u) {
  const res = await ctx.kb(u.args);
  const c = classify(res);
  if (c.kind === 'ok') {
    ctx.toast(firstLine(res.stdout) || '已復原');
    if (ctx.refresh) ctx.refresh();
    return { ok: true };
  }
  if (c.kind === 'refused' && u.refusalModal && ctx.info) {
    await ctx.info({ title: '退不了', lines: [c.message] });
    return { ok: false, refused: true };
  }
  ctx.toast(c.message);
  if (c.kind === 'failed' && ctx.log) ctx.log(res.stderr || res.stdout);
  return { ok: false };
}

/**
 * 執行一個動作：有 check 先問；成功 toast kb 的那句（原樣）加「復原」；失敗照 exit 3／其他分。
 * ctx：{kb(args)→res, toast(text, {undo}), confirm({title, lines, okText})→bool, info?, refresh?, log?}
 */
async function performAction(ctx, action) {
  if (!action) return { ok: false };
  if (action.check) {
    const res = await ctx.kb(action.check.args);
    const chk = interpretCheck(res);
    if (chk.error) {
      ctx.toast(chk.error);
      if (ctx.log) ctx.log(res.stderr || res.stdout);
      return { ok: false };
    }
    if (chk.refuse) {
      ctx.toast(chk.refuse);
      return { ok: false, refused: true };
    }
    const yes = await ctx.confirm({ title: action.check.title, lines: chk.effects, okText: action.check.okText || '好，做' });
    if (!yes) return { ok: false, cancelled: true };
  }
  const res = await ctx.kb(action.args);
  const c = classify(res);
  if (c.kind !== 'ok') {
    ctx.toast(c.message);
    if (c.kind === 'failed' && ctx.log) ctx.log(res.stderr || res.stdout);
    return { ok: false, refused: c.kind === 'refused' };
  }
  const json = action.json ? parseJson(res.stdout) : null;
  const text = (action.toastText ? action.toastText(json) : '') || firstLine(res.stdout) || '好了';
  const u = action.undo ? action.undo(json, res) : null;
  ctx.toast(text, { undo: u ? () => runUndo(ctx, u) : null });
  if (ctx.refresh) ctx.refresh();
  return { ok: true, json, undo: u };
}

// ---------------------------------------------------------------------------------------------------------------
// 搜尋
// ---------------------------------------------------------------------------------------------------------------

/** Enter 才搜；注音選字中（compositionstart～compositionend、isComposing、keyCode 229）不搜；空字串不搜。 */
function searchDecision(ev) {
  if (!ev || ev.key !== 'Enter') return { search: false };
  if (ev.composing || ev.isComposing || ev.keyCode === 229) return { search: false };
  const q = String(ev.value == null ? '' : ev.value).trim();
  if (!q) return { search: false, clear: true };
  return { search: true, query: q };
}

function findArgs(q) {
  return q.startsWith('-') ? ['find', '--json', '--', q] : ['find', q, '--json'];
}

/** 點掉「照這樣找」的一個：把那段字從原字串拿掉。 */
function removeChipText(q, text) {
  const s = String(q == null ? '' : q);
  const t = String(text == null ? '' : text);
  if (!t) return s.trim();
  const i = s.indexOf(t);
  const out = i < 0 ? s : s.slice(0, i) + ' ' + s.slice(i + t.length);
  return out.replace(/\s+/g, ' ').trim();
}

function askClaudeText(q) {
  return `幫我找：${q}`;
}

/** 「到對話問 Claude」：把「幫我找：<字>」複製到剪貼簿。 */
async function copyAskClaude(ctx, q) {
  const text = askClaudeText(q);
  try {
    await ctx.writeClipboard(text);
    ctx.toast(COPIED_TEXT);
    return true;
  } catch (e) {
    ctx.toast(`沒辦法複製，請自己複製：${text}`);
    return false;
  }
}

/** 開原檔：網路路徑不呼叫 openPath（B-050 第 7 列）；link 條目開網址。 */
async function openOriginal(ctx, open) {
  if (!isObject(open) || (!open.path && !open.url)) {
    ctx.toast('這份沒有原檔可以開');
    return false;
  }
  if (open.url) {
    ctx.openUrl(open.url);
    return true;
  }
  if (isNetworkPath(open.path)) {
    ctx.toast(`這份在網路磁碟上，從這裡開不了；到檔案總管開：${open.path}`);
    return false;
  }
  let err = '';
  try {
    err = await ctx.openPath(nativePath(open.path, ctx.platform));
  } catch (e) {
    err = String(e && e.message ? e.message : e);
  }
  if (err) {
    ctx.toast(`開不了這份：${err}`);
    return false;
  }
  return true;
}

// ---------------------------------------------------------------------------------------------------------------
// 程式產生的頁（D-263）
// ---------------------------------------------------------------------------------------------------------------

function isManagedPage(p) {
  return MANAGED_PAGES.includes(String(p || '').replace(/\\/g, '/'));
}

function isGeneratedPage(p) {
  const s = String(p || '').replace(/\\/g, '/');
  return s === '總目錄.md' || s.startsWith('系統/工作日誌/') || s.startsWith('系統/健檢報告/');
}

/** 離開被改的那一行（游標換行）、或切到別頁，才叫 kb renders apply。 */
function createApplyTracker() {
  const dirty = new Map();
  const lastEdit = new Map();
  const ignoreUntil = new Map();
  return {
    /** 她改了 page 的第 line 行；回 true = 她已經離開前一個被改的行。 */
    edited(page, line, now) {
      if (now < (ignoreUntil.get(page) || 0)) return false; // kb 剛改寫這頁，編輯器重載不算她打的
      lastEdit.set(page, now);
      const d = dirty.get(page);
      dirty.set(page, { line });
      return !!d && d.line !== line;
    },
    /** 游標移到第 line 行（沒打字）；回 true = 離開了被改的那一行。 */
    cursor(page, line) {
      const d = dirty.get(page);
      if (d && d.line !== line) {
        dirty.delete(page);
        return true;
      }
      return false;
    },
    /** 切到別頁、關掉；回 true = 這頁有沒套用的修改。 */
    leave(page) {
      return dirty.delete(page);
    },
    applied(page) {
      dirty.delete(page);
    },
    external(page, now) {
      dirty.delete(page);
      ignoreUntil.set(page, now + 800);
    },
    isDirty(page) {
      return dirty.has(page);
    },
    isTyping(page, now, windowMs) {
      const t = lastEdit.get(page);
      return t !== undefined && now - t <= (windowMs === undefined ? 5000 : windowMs);
    },
  };
}

/** 她開著的頁被外部改寫才 toast：不是她在打字、不是外掛自己叫 kb 剛改的。 */
function shouldToastModified(s) {
  if (!s.open) return false;
  if (s.applying) return false;
  if (s.typing) return false;
  if (s.lastKbAt && s.now - s.lastKbAt < 2500) return false;
  return true;
}

/** renders apply 的回傳（形狀是外掛這邊的假設）：{applied:[…]|數字, carried:[…]|數字}。 */
function summarizeApply(json, pageName) {
  const count = (v) => (Array.isArray(v) ? v.length : Number(v) || 0);
  const j = isObject(json) ? json : {};
  const applied = count(j.applied);
  const carried = count(j.carried);
  const parts = [];
  if (j.unrecognized) parts.push(UNRECOGNIZED_TEXT);
  if (applied) parts.push(`照你在${pageName || '這頁'}改的做了 ${applied} 件`);
  if (carried) parts.push(CARRIED_TEXT);
  return { applied, carried, text: parts.join('；') };
}

function pageName(p) {
  return String(p || '').split('/').pop().replace(/\.md$/, '');
}

/** 內文有「你加的（還沒處理）」那段（kb 剛把她的字搬進去）。 */
function hasCarriedSection(text) {
  return /^##\s*你加的（還沒處理）/m.test(String(text || ''));
}

// ---------------------------------------------------------------------------------------------------------------
// 出處〔f-…〕變連結（閱讀模式）
// ---------------------------------------------------------------------------------------------------------------

function splitCardRefs(text) {
  const out = [];
  const s = String(text == null ? '' : text);
  let last = 0;
  CARD_REF_RE.lastIndex = 0;
  let m;
  while ((m = CARD_REF_RE.exec(s)) !== null) {
    if (m.index > last) out.push({ text: s.slice(last, m.index) });
    out.push({ ref: m[1] });
    last = m.index + m[0].length;
  }
  if (last < s.length) out.push({ text: s.slice(last) });
  return out;
}

// ---------------------------------------------------------------------------------------------------------------
// DOM 小幫手（只用 createElement／setAttribute／addEventListener／appendChild，方便測試用假 DOM）
// ---------------------------------------------------------------------------------------------------------------

const dom = {
  doc() {
    return globalThis.document;
  },
};

function kebab(s) {
  return s.startsWith('--') ? s : s.replace(/[A-Z]/g, (c) => '-' + c.toLowerCase());
}

function applyKids(el, kids) {
  for (const k of kids) {
    if (k === null || k === undefined || k === false) continue;
    if (Array.isArray(k)) applyKids(el, k);
    else if (typeof k === 'string' || typeof k === 'number') el.appendChild(dom.doc().createTextNode(String(k)));
    else el.appendChild(k);
  }
}

function applyProps(el, props) {
  if (!props) return;
  for (const k of Object.keys(props)) {
    const v = props[k];
    if (v === null || v === undefined || v === false) continue;
    if (k === 'cls') el.className = Array.isArray(v) ? v.filter(Boolean).join(' ') : String(v);
    else if (k === 'text') el.textContent = String(v);
    else if (k === 'title') el.setAttribute('title', String(v));
    else if (k === 'style') for (const sk of Object.keys(v)) el.style.setProperty(kebab(sk), String(v[sk]));
    else if (k === 'on') for (const ev of Object.keys(v)) el.addEventListener(ev, v[ev]);
    else if (k === 'attrs') for (const ak of Object.keys(v)) el.setAttribute(ak, String(v[ak]));
    else el[k] = v; // value、checked、disabled、id …
  }
}

function h(tag, props, ...kids) {
  const el = dom.doc().createElement(tag);
  applyProps(el, props);
  applyKids(el, kids);
  return el;
}

const SVG_NS = 'http://www.w3.org/2000/svg';
function hs(tag, attrs, ...kids) {
  const doc = dom.doc();
  const el = doc.createElementNS ? doc.createElementNS(SVG_NS, tag) : doc.createElement(tag);
  for (const k of Object.keys(attrs || {})) el.setAttribute(k, String(attrs[k]));
  applyKids(el, kids);
  return el;
}

function clear(el) {
  while (el.firstChild) el.removeChild(el.firstChild);
}

// ---------------------------------------------------------------------------------------------------------------
// 對話框
// ---------------------------------------------------------------------------------------------------------------

/**
 * 通用表單／確認框。opts：{title, lines:[], fields:[{key,label,type,value,options,placeholder,list}], okText, cancelText, hideCancel}
 * 回 Promise：按確定 = 欄位值的物件（沒有欄位就是 {}），其他 = null。
 */
class FormModal extends Modal {
  constructor(app, opts, resolve) {
    super(app);
    this.opts = opts || {};
    this.resolve = resolve;
    this.settled = false;
    this.inputs = {};
  }

  onOpen() {
    const o = this.opts;
    if (this.titleEl) this.titleEl.textContent = o.title || '';
    const root = this.contentEl;
    for (const line of asArray(o.lines)) root.appendChild(h('p', { cls: 'wwh-modal-line', text: line }));
    for (const f of asArray(o.fields)) {
      let input;
      if (f.type === 'select') {
        input = h('select', { cls: 'wwh-input' });
        for (const opt of asArray(f.options)) {
          const value = isObject(opt) ? opt.value : opt;
          const label = isObject(opt) ? opt.label : opt;
          input.appendChild(h('option', { value, text: label, selected: value === f.value }));
        }
        input.value = f.value === undefined ? '' : f.value;
      } else if (f.type === 'textarea') {
        input = h('textarea', { cls: 'wwh-input', value: f.value || '', attrs: { rows: 3, placeholder: f.placeholder || '' } });
      } else {
        const attrs = { type: f.type || 'text' };
        if (f.placeholder) attrs.placeholder = f.placeholder;
        if (f.list) attrs.list = `wwh-list-${f.key}`;
        input = h('input', {
          cls: 'wwh-input',
          value: f.value || '',
          attrs,
          on: {
            keydown: (e) => {
              if (e.key === 'Enter' && !e.isComposing && e.keyCode !== 229 && f.type !== 'textarea') {
                e.preventDefault();
                this.submit();
              }
            },
          },
        });
      }
      this.inputs[f.key] = input;
      const row = h('label', { cls: 'wwh-field' }, h('span', { cls: 'wwh-field-label', text: f.label || '' }), input);
      if (f.list) {
        const dl = h('datalist', { attrs: { id: `wwh-list-${f.key}` } });
        for (const v of f.list) dl.appendChild(h('option', { value: v }));
        row.appendChild(dl);
      }
      root.appendChild(row);
    }
    const buttons = h('div', { cls: 'wwh-modal-buttons' });
    if (!o.hideCancel) buttons.appendChild(h('button', { text: o.cancelText || '不要', on: { click: () => this.finish(null) } }));
    buttons.appendChild(h('button', { cls: 'mod-cta', text: o.okText || '好', on: { click: () => this.submit() } }));
    root.appendChild(buttons);
    const first = Object.values(this.inputs)[0];
    if (first && first.focus) first.focus();
  }

  values() {
    const out = {};
    for (const k of Object.keys(this.inputs)) out[k] = String(this.inputs[k].value == null ? '' : this.inputs[k].value).trim();
    return out;
  }

  submit() {
    for (const f of asArray(this.opts.fields)) {
      if (f.required && !this.values()[f.key]) {
        if (this.inputs[f.key] && this.inputs[f.key].focus) this.inputs[f.key].focus();
        return;
      }
    }
    this.finish(this.values());
  }

  finish(v) {
    if (this.settled) return;
    this.settled = true;
    this.resolve(v);
    this.close();
  }

  onClose() {
    if (!this.settled) {
      this.settled = true;
      this.resolve(null);
    }
    clear(this.contentEl);
  }
}

function openForm(app, opts) {
  return new Promise((resolve) => {
    new FormModal(app, opts, resolve).open();
  });
}

// ---------------------------------------------------------------------------------------------------------------
// 首頁分頁
// ---------------------------------------------------------------------------------------------------------------

function defaultUi() {
  return {
    timelineMode: 'timeline', // timeline | month
    month: null, // {year, month}
    rowCollapsed: {},
    todoCollapsed: {},
    othersOpen: false,
    search: { q: '', active: false, focused: false, loading: false, result: null, error: null },
    drawer: { open: false, stack: [], data: null, loading: false, error: null },
  };
}

// ---------------------------------------------------------------------------------------------------------------
// 首頁的圖示、欄寬（設計稿 design/mockups/Obsidian首頁-設計稿.dc.html，裁定 28）
// ---------------------------------------------------------------------------------------------------------------

const HEAD_H = 48; // 時間軸每一塊（事類實體）標題列的高度
const ROW_H = 40; // 展開後每件一列的高度
const RECENT_MAX = 8;
const ICON_SHAPES = {
  meeting: [
    ['circle', { cx: 6, cy: 5.5, r: 2.4 }],
    ['circle', { cx: 11.6, cy: 6.2, r: 1.9 }],
    ['path', { d: 'M1.6 13.5c.4-2.4 2.2-4 4.4-4s4 1.6 4.4 4M10.6 9.4c1.9-.3 3.5.9 3.9 3.4' }],
  ],
  promise: [
    ['circle', { cx: 8, cy: 8, r: 6 }],
    ['path', { d: 'm5.3 8.2 2 2 3.5-4' }],
  ],
  deadline: [['path', { d: 'M3.5 14.5V2M3.5 2.5h8.5l-2.2 3 2.2 3H3.5' }]],
  reminder: [
    ['path', { d: 'M4 11V7.5a4 4 0 0 1 8 0V11l1.2 1.5H2.8z' }],
    ['path', { d: 'M6.7 14.2a1.4 1.4 0 0 0 2.6 0' }],
  ],
  period: [['path', { d: 'M4.5 1.8h7M4.5 14.2h7M5 1.8c0 3.6 6 3.6 6 6.2s-6 2.6-6 6.2M11 1.8c0 3.6-6 3.6-6 6.2s6 2.6 6 6.2' }]],
  card: [
    ['rect', { x: 2.5, y: 2, width: 11, height: 12, rx: 1.5 }],
    ['path', { d: 'M5 5.5h6M5 8h6M5 10.5h3.5' }],
  ],
  info: [
    ['circle', { cx: 8, cy: 8, r: 6 }],
    ['path', { d: 'M8 7.2V11M8 5v.1' }],
  ],
  chevron: [['path', { d: 'M6 3.5 10.5 8 6 12.5' }]],
  dots: [
    ['circle', { cx: 3.5, cy: 8, r: 1 }],
    ['circle', { cx: 8, cy: 8, r: 1 }],
    ['circle', { cx: 12.5, cy: 8, r: 1 }],
  ],
};

/** 小圖示（SVG，顏色跟著文字）；不認得的名字回 null。 */
function icon(name, size, width) {
  const shapes = ICON_SHAPES[name];
  if (!shapes) return null;
  const px = size || 14;
  return hs(
    'svg',
    {
      class: 'wwh-ico',
      width: px,
      height: px,
      viewBox: '0 0 16 16',
      fill: 'none',
      stroke: 'currentColor',
      'stroke-width': width || 1.6,
      'stroke-linecap': 'round',
      'stroke-linejoin': 'round',
      'aria-hidden': 'true',
    },
    ...shapes.map(([tag, attrs]) => hs(tag, attrs)),
  );
}

/** 搜尋結果與「最近」那一列前面的小方塊：看原檔的副檔名（連結條目是 ↗）。 */
function fileExt(f) {
  const open = isObject(f) && isObject(f.open) ? f.open : {};
  if (open.url) return { label: '↗', cls: 'ext-link' };
  const m = /\.([A-Za-z0-9]{1,5})$/.exec(String(open.path || ''));
  const ext = m ? m[1].toLowerCase() : '';
  let cls = 'ext-other';
  if (['xls', 'xlsx', 'xlsm', 'csv'].includes(ext)) cls = 'ext-xls';
  else if (['doc', 'docx', 'txt', 'md'].includes(ext)) cls = 'ext-doc';
  else if (['ppt', 'pptx'].includes(ext)) cls = 'ext-ppt';
  else if (ext === 'pdf') cls = 'ext-pdf';
  else if (['png', 'jpg', 'jpeg', 'gif', 'heic', 'webp'].includes(ext)) cls = 'ext-img';
  return { label: (ext.length > 3 ? ext.slice(0, 3) : ext || '檔').toUpperCase(), cls }; // xlsx → XLS、docx → DOC：小方塊裡放得下
}

/** 「10 月 30 日 星期五」。 */
function longDate(iso) {
  const n = dayNumber(iso);
  if (n === null) return '';
  const d = new Date(n * 86400000);
  return `${d.getUTCMonth() + 1} 月 ${d.getUTCDate()} 日 星期${WEEKDAY[d.getUTCDay()]}`;
}

/** 這一塊預設收起；有逾期或今天那件還沒做的才預設展開（裁定 28）。 */
function rowDefaultCollapsed(row, todayN) {
  const marks = asArray(row && row.marks);
  return !marks.some((m) => m.status === 'open' && (m.late || (todayN !== null && m.shape === 'point' && dayNumber(m.end) === todayN)));
}

function rowIsCollapsed(ui, row, todayN) {
  const set = ui.rowCollapsed[row.key];
  return set !== undefined ? !!set : rowDefaultCollapsed(row, todayN);
}

/** 展開後左欄第二行：點是「10/30（週五）· 過了 2 天」，期間是「9/1～11/30」。 */
function markWhen(m, todayN) {
  if (m.shape === 'bar') {
    const a = shortDate(m.start);
    const b = shortDate(m.end);
    return a && b ? `${a}～${b}` : a || b;
  }
  const n = dayNumber(m.end);
  if (n === null) return '';
  let text = `${shortDate(m.end)}（週${WEEKDAY[weekdayOf(n)]}）`;
  if (m.time) text += ` ${m.time}`;
  if (m.status === 'done') text += ' · 完成了';
  else if (m.status === 'open' && todayN !== null && n < todayN) text += ` · 過了 ${todayN - n} 天`;
  return text;
}

class HomeView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
    this.composing = false;
  }

  getViewType() {
    return VIEW_TYPE;
  }

  getDisplayText() {
    return '首頁';
  }

  getIcon() {
    return 'home';
  }

  async onOpen() {
    this.contentEl.classList.add('wwh-view');
    this.build();
    this.render();
    this.plugin.refresh();
  }

  async onClose() {
    clear(this.contentEl);
  }

  build() {
    this.root = h('div', { cls: 'wwh-root' });
    this.bannerEl = h('div', { cls: 'wwh-banners' });
    this.topEl = h('div', { cls: 'wwh-top' });
    this.searchEl = h('div', { cls: 'wwh-search' });
    this.dropdownEl = h('div', { cls: 'wwh-dropdown' });
    this.recentEl = h('div', { cls: 'wwh-dropdown wwh-recent' });
    this.timelineEl = h('section', { cls: 'wwh-section wwh-timeline-section' });
    this.leftEl = h('div', { cls: 'wwh-col wwh-col-left' });
    this.rightEl = h('div', { cls: 'wwh-col wwh-col-right' });
    this.colsEl = h('div', { cls: 'wwh-cols' }, this.leftEl, this.rightEl);
    this.drawerEl = h('aside', { cls: 'wwh-drawer' });
    this.inputEl = h('input', {
      cls: 'wwh-search-input',
      attrs: { type: 'search', placeholder: '找檔案、人、案子，打完按 Enter（例：王先生 報價 上個月）' },
      on: {
        compositionstart: () => {
          this.composing = true;
        },
        compositionend: () => {
          this.composing = false;
        },
        keydown: (e) => {
          const d = searchDecision({
            key: e.key,
            isComposing: e.isComposing,
            keyCode: e.keyCode,
            composing: this.composing,
            value: this.inputEl.value,
          });
          if (d.search) {
            if (e.preventDefault) e.preventDefault();
            this.doSearch(d.query);
          } else if (d.clear) {
            this.clearSearch();
          }
        },
        input: () => {
          if (!String(this.inputEl.value || '').trim() && this.plugin.ui.search.active) this.clearSearch();
        },
        focus: () => {
          this.plugin.ui.search.focused = true;
          this.renderSearchPanels();
        },
        blur: () => {
          this.plugin.ui.search.focused = false;
          this.renderSearchPanels();
        },
      },
    });
    this.searchEl.appendChild(this.inputEl);
    this.searchEl.appendChild(this.dropdownEl);
    this.searchEl.appendChild(this.recentEl);
    for (const box of [this.dropdownEl, this.recentEl]) {
      box.addEventListener('mousedown', (e) => {
        if (e && e.preventDefault) e.preventDefault(); // 點下拉裡的列，不讓搜尋框先失去游標（失去了「最近」就收起來）
      });
    }
    this.root.appendChild(this.bannerEl);
    this.root.appendChild(this.topEl);
    this.root.appendChild(this.searchEl);
    this.root.appendChild(this.timelineEl);
    this.root.appendChild(this.colsEl);
    clear(this.contentEl);
    this.contentEl.appendChild(this.root);
    this.contentEl.appendChild(this.drawerEl); // 抽屜蓋在首頁右邊，不跟著首頁捲動
  }

  safe(name, el, fn) {
    clear(el);
    try {
      fn(el);
    } catch (e) {
      console.error(`[wiki-with-willy] 畫「${name}」出錯`, e);
      el.appendChild(h('div', { cls: 'wwh-empty', text: `這一區畫不出來（${name}）` }));
    }
  }

  render() {
    if (!this.root) return;
    const p = this.plugin;
    if (!p.runner) {
      for (const el of [this.topEl, this.searchEl, this.recentEl, this.timelineEl, this.colsEl, this.drawerEl, this.bannerEl]) {
        el.classList.add('wwh-hidden');
      }
      if (!this.noKbEl) this.noKbEl = h('div', { cls: 'wwh-nokb', text: NO_KB_TEXT });
      if (!this.noKbEl.parentNode) this.root.insertBefore(this.noKbEl, this.root.firstChild);
      return;
    }
    if (this.noKbEl && this.noKbEl.parentNode) this.root.removeChild(this.noKbEl);
    for (const el of [this.topEl, this.searchEl, this.recentEl, this.timelineEl, this.colsEl, this.drawerEl, this.bannerEl]) {
      el.classList.remove('wwh-hidden');
    }
    this.safe('提示', this.bannerEl, (el) => this.renderBanners(el));
    this.safe('今天', this.topEl, (el) => this.renderTop(el));
    this.renderSearchPanels();
    this.safe('時間軸', this.timelineEl, (el) => this.renderTimeline(el));
    this.safe('待辦', this.leftEl, (el) => this.renderTodo(el));
    this.safe('要你確認的', this.rightEl, (el) => this.renderRight(el));
    this.safe('總覽', this.drawerEl, (el) => this.renderDrawer(el));
  }

  // ---- 提示條 ----
  renderBanners(el) {
    const p = this.plugin;
    if (p.needsReload) {
      el.appendChild(h('button', { cls: 'wwh-banner wwh-banner-reload', text: RELOAD_TEXT, on: { click: () => p.reloadSelf() } }));
    }
    if (p.home && versionMismatch(p.home.version, p.loadedVersion)) {
      el.appendChild(h('div', { cls: 'wwh-banner wwh-banner-warn', text: VERSION_MISMATCH_TEXT }));
    }
    if (p.homeError) {
      el.appendChild(h('div', { cls: 'wwh-banner wwh-banner-warn', text: `首頁的資料讀不到：${p.homeError}` }));
    }
  }

  // ---- 鼓勵句與件數 ----
  renderTop(el) {
    const home = this.plugin.home;
    if (!home) {
      el.appendChild(h('div', { cls: 'wwh-cheer', text: '載入中……' }));
      return;
    }
    el.appendChild(
      h('div', { cls: 'wwh-greet' }, h('p', { cls: 'wwh-date', text: longDate(home.today) }), h('h1', { cls: 'wwh-cheer', text: home.cheer || '' })),
    );
    const c = home.counts;
    const chip = (label, n, cls) => h('span', { cls: ['wwh-count', cls, n ? 'has' : ''], text: `${label} ${n}` });
    el.appendChild(
      h(
        'div',
        { cls: 'wwh-counts' },
        chip('已經過了', c.overdue, 'overdue'),
        chip('今天', c.today, 'today'),
        chip('這週', c.week, 'week'),
        chip('要你確認', c.confirm, 'confirm'),
        chip('其他要處理', c.other, 'other'),
        h('button', { cls: 'wwh-small-btn wwh-add-btn', text: '＋ 新增日程', on: { click: () => this.plugin.addAgendaForm() } }),
      ),
    );
  }

  // ---- 搜尋 ----
  async doSearch(q) {
    const ui = this.plugin.ui.search;
    ui.q = q;
    ui.active = true;
    ui.loading = true;
    ui.error = null;
    this.inputEl.value = q;
    ui.seq = (ui.seq || 0) + 1; // 請求編號跟搜尋狀態放同一處：重開分頁（新的 view）也只認最新那次
    const seq = ui.seq;
    this.renderSearchPanels();
    const res = await this.plugin.runner.run(findArgs(q));
    if (seq !== ui.seq) return; // 後面又搜了（或清掉了）：這個舊的結果丟掉
    const c = classify(res);
    ui.loading = false;
    if (c.kind === 'ok') {
      const j = parseJson(res.stdout);
      ui.result = isObject(j) ? j : { parsed: [], entities: [], files: [], total: 0, more: false };
    } else {
      ui.result = null;
      ui.error = c.message;
      if (c.kind === 'failed') console.error('[wiki-with-willy] kb find 失敗', res.stderr || res.stdout);
    }
    this.renderSearchPanels();
  }

  clearSearch() {
    const ui = this.plugin.ui.search;
    ui.seq = (ui.seq || 0) + 1; // 還在路上的查詢回來不算數
    ui.q = '';
    ui.active = false;
    ui.result = null;
    ui.error = null;
    ui.loading = false;
    this.inputEl.value = '';
    this.renderSearchPanels();
  }

  renderSearchPanels() {
    if (!this.dropdownEl) return;
    this.safe('搜尋結果', this.dropdownEl, (el) => this.renderDropdown(el));
    this.safe('最近', this.recentEl, (el) => this.renderRecent(el));
  }

  renderDropdown(el) {
    const ui = this.plugin.ui.search;
    el.classList.toggle('is-open', !!ui.active);
    if (!ui.active) return;
    if (ui.loading) {
      el.appendChild(h('div', { cls: 'wwh-dd-row wwh-muted', text: '找找看……' }));
      return;
    }
    if (ui.error) {
      el.appendChild(h('div', { cls: 'wwh-dd-row wwh-muted', text: ui.error }));
    }
    const r = ui.result;
    if (r) {
      const parsed = asArray(r.parsed).filter(isObject);
      if (parsed.length) {
        const chips = h('div', { cls: 'wwh-dd-row wwh-chips' }, h('span', { cls: 'wwh-muted', text: '照這樣找：' }));
        for (const p of parsed) {
          chips.appendChild(
            h(
              'button',
              {
                cls: ['wwh-chip', `wwh-chip-${p.kind || 'word'}`],
                title: '點一下就不用這一項，重新找',
                on: { click: () => this.doSearchAfterChip(ui.q, p) },
              },
              p.label || p.text || '',
              h('span', { cls: 'wwh-chip-x', text: ' ✕' }),
            ),
          );
        }
        el.appendChild(chips);
      }
      const ents = asArray(r.entities).filter(isObject);
      if (ents.length) {
        el.appendChild(h('div', { cls: 'wwh-dd-head', text: '案子、人、事' }));
        for (const e of ents) {
          el.appendChild(
            h(
              'div',
              { cls: 'wwh-dd-row wwh-dd-entity', on: { click: () => this.plugin.openEntity(e.name) } },
              h('span', { cls: 'wwh-dd-title', text: e.name || '' }),
              h('span', { cls: 'wwh-muted', text: e.type ? `　${e.type}` : '' }),
            ),
          );
        }
      }
      const files = asArray(r.files).filter(isObject);
      if (files.length) {
        el.appendChild(h('div', { cls: 'wwh-dd-head', text: r.more ? `檔案（${files.length} 份以上）` : `檔案（${files.length} 份）` }));
        for (const f of files) el.appendChild(this.fileRow(f));
      }
      if (!ents.length && !files.length) el.appendChild(h('div', { cls: 'wwh-dd-row wwh-muted', text: '沒有找到' }));
    }
    el.appendChild(
      h('div', { cls: 'wwh-dd-row wwh-dd-ask', on: { click: () => this.plugin.askClaude(ui.q) } }, '💬 到對話問 Claude'),
    );
  }

  doSearchAfterChip(q, chip) {
    const next = removeChipText(q, chip.text);
    if (!next) {
      this.clearSearch();
      return;
    }
    this.doSearch(next);
  }

  fileRow(f) {
    const meta = [f.type, f.date, asArray(f.entities).join('、')].filter(Boolean).join('　');
    const ext = fileExt(f);
    const main = h(
      'div',
      { cls: 'wwh-file-main', on: { click: () => this.plugin.openFile(f) } },
      h('span', { cls: ['wwh-ext', ext.cls], text: ext.label }),
      h('span', { cls: 'wwh-file-text' }, h('span', { cls: 'wwh-dd-title', text: f.title || f.card || '' }), h('span', { cls: 'wwh-muted wwh-file-meta', text: meta })),
    );
    return h('div', { cls: 'wwh-dd-row wwh-file' }, main, f.card_path ? this.cardButton(f) : null);
  }

  cardButton(f) {
    return h(
      'button',
      {
        cls: 'wwh-icon-btn wwh-card-btn',
        title: '開檔案卡',
        on: {
          click: (e) => {
            if (e && e.stopPropagation) e.stopPropagation();
            this.plugin.openCard(f);
          },
        },
      },
      icon('card', 15, 1.5),
    );
  }

  /** 「最近」：游標在搜尋框裡、還沒打字時從框下面掉下來，一列一份，最多 8 列（裁定 28）。 */
  renderRecent(el) {
    const ui = this.plugin.ui.search;
    const home = this.plugin.home;
    const show = !!(ui.focused && !ui.active && home && home.recent.length);
    el.classList.toggle('wwh-hidden', !show);
    el.classList.toggle('is-open', show);
    if (!show) return;
    el.appendChild(h('div', { cls: 'wwh-dd-head', text: '最近' }));
    for (const f of home.recent.slice(0, RECENT_MAX)) {
      const meta = [f.type, f.date, f.why === 'added' ? '剛放進來' : '你開過'].filter(Boolean).join('　');
      const ext = fileExt(f);
      el.appendChild(
        h(
          'div',
          { cls: ['wwh-dd-row', 'wwh-file', 'wwh-recent-item', f.why === 'added' ? 'is-added' : 'is-opened'] },
          h(
            'div',
            { cls: 'wwh-file-main', on: { click: () => this.plugin.openFile(f) } },
            h('span', { cls: ['wwh-ext', ext.cls], text: ext.label }),
            h('span', { cls: 'wwh-file-text' }, h('span', { cls: 'wwh-dd-title', text: f.title || f.card || '' }), h('span', { cls: 'wwh-muted wwh-file-meta', text: meta })),
          ),
          f.card_path ? this.cardButton(f) : null,
        ),
      );
    }
  }

  // ---- 時間軸 ----
  renderTimeline(el) {
    const p = this.plugin;
    const home = p.home;
    const ui = p.ui;
    const head = h('div', { cls: 'wwh-section-head' }, h('h2', { text: '手上的事' }));
    const tools = h('div', { cls: 'wwh-tools' });
    if (home && ui.timelineMode === 'timeline') { // kb home 還沒回來時不畫，按了也沒東西可展開
      const layout = layoutTimeline(home.timeline, { today: home.today });
      const todayN = dayNumber(home.today);
      const allOpen = layout.rows.length > 0 && layout.rows.every((r) => !rowIsCollapsed(ui, r, todayN));
      tools.appendChild(
        h('button', { cls: 'wwh-text-btn', text: allOpen ? '全部收起' : '全部展開', on: { click: () => this.setAllRows(allOpen) } }),
      );
    }
    tools.appendChild(
      h(
        'span',
        { cls: 'wwh-toggle' },
        h('button', { cls: ['wwh-seg', ui.timelineMode === 'timeline' ? 'is-on' : ''], text: '時間軸', on: { click: () => this.setMode('timeline') } }),
        h('button', { cls: ['wwh-seg', ui.timelineMode === 'month' ? 'is-on' : ''], text: '月曆', on: { click: () => this.setMode('month') } }),
      ),
    );
    head.appendChild(tools);
    el.appendChild(head);
    if (!home) return;
    if (ui.timelineMode === 'month') {
      this.renderMonth(el, home);
      return;
    }
    const layout = layoutTimeline(home.timeline, { today: home.today });
    if (!layout.rows.length) {
      el.appendChild(h('div', { cls: 'wwh-empty', text: '手上沒有排日期的事' }));
      return;
    }
    const todayN = dayNumber(home.today);
    const table = h('div', { cls: 'wwh-gantt' }, this.axis(layout));
    layout.rows.forEach((row, i) => table.appendChild(this.timelineBlock(layout, row, i, todayN)));
    el.appendChild(table);
    el.appendChild(this.legend());
  }

  setMode(mode) {
    this.plugin.ui.timelineMode = mode;
    this.safe('時間軸', this.timelineEl, (el) => this.renderTimeline(el));
  }

  setAllRows(collapsed) {
    if (!this.plugin.home) return;
    const layout = layoutTimeline(this.plugin.home.timeline, { today: this.plugin.home.today });
    for (const r of layout.rows) this.plugin.ui.rowCollapsed[r.key] = collapsed;
    this.safe('時間軸', this.timelineEl, (el) => this.renderTimeline(el));
  }

  legend() {
    const kind = (name, text) => h('span', { cls: 'wwh-legend-item' }, icon(name, 13), text);
    const swatch = (cls, text) => h('span', { cls: 'wwh-legend-item' }, h('i', { cls: ['wwh-legend-swatch', cls] }), text);
    return h(
      'div',
      { cls: 'wwh-legend' },
      kind('meeting', '會議'),
      kind('promise', '承諾'),
      kind('deadline', '到期'),
      kind('reminder', '提醒'),
      swatch('is-bar', '期間'),
      swatch('is-inferred', '推測的'),
      swatch('is-late', '過了還沒收尾'),
      swatch('is-pause', '暫停'),
      swatch('is-today', '今天'),
    );
  }

  /** 軸頭：只標月份、畫週線；今天的旗子放在月份下面一行，不壓到月份的字。 */
  axis(layout) {
    const track = h('div', { cls: 'wwh-axis-track' });
    const months = layout.ticks.filter((t) => t.kind === 'month');
    if (!months.length || months[0].pct > 8) {
      const d = new Date(layout.fromN * 86400000);
      track.appendChild(h('span', { cls: 'wwh-tick is-month', style: { left: '0%' }, text: `${d.getUTCMonth() + 1}月` }));
    }
    for (const t of layout.ticks) {
      if (t.kind === 'month') track.appendChild(h('span', { cls: 'wwh-tick is-month', style: { left: `${t.pct}%` }, text: t.label }));
      else track.appendChild(h('i', { cls: 'wwh-grid is-week', style: { left: `${t.pct}%` } }));
    }
    if (layout.todayPct !== null) track.appendChild(h('span', { cls: 'wwh-today-flag', style: { left: `${layout.todayPct}%` }, text: '今天' }));
    return h('div', { cls: 'wwh-axis' }, h('div', { cls: 'wwh-cell-left' }), track);
  }

  timelineBlock(layout, row, index, todayN) {
    const ui = this.plugin.ui;
    const collapsed = rowIsCollapsed(ui, row, todayN);
    const isOther = row.key === '_other';
    const open = row.marks.filter((m) => m.status === 'open').length;
    const toggle = () => {
      ui.rowCollapsed[row.key] = !collapsed;
      this.safe('時間軸', this.timelineEl, (el) => this.renderTimeline(el));
    };
    const left = h(
      'div',
      { cls: 'wwh-cell-left wwh-row-head' },
      h(
        'button',
        { cls: 'wwh-fold', title: collapsed ? '展開' : '收起', attrs: { 'aria-expanded': collapsed ? 'false' : 'true' }, on: { click: toggle } },
        h('span', { cls: ['wwh-chev', collapsed ? '' : 'is-open'] }, icon('chevron', 14, 2)),
        h('span', { cls: 'wwh-row-name', text: row.label }),
        h('span', { cls: 'wwh-muted wwh-row-count', text: open ? `${open} 件` : '' }),
        row.progress && progressWord(row.progress) !== '進行中'
          ? h('span', { cls: ['wwh-badge', `is-${row.progress}`], text: progressWord(row.progress) || row.progress })
          : null,
      ),
      isOther
        ? null
        : h(
            'button',
            { cls: 'wwh-sq-btn wwh-info-btn', title: `看「${row.label}」的總覽`, on: { click: () => this.plugin.openEntity(row.label) } },
            icon('info', 14, 1.7),
          ),
      isOther
        ? null
        : h(
            'button',
            { cls: 'wwh-sq-btn', title: '這件事可以做的', on: { click: (e) => this.plugin.entityMenu(e, row.label, row.progress) } },
            icon('dots', 14, 1.7),
          ),
    );
    const headLine = h('div', { cls: 'wwh-line wwh-head-line' }, left, h('div', { cls: 'wwh-cell-track' }, collapsed ? this.summary(row) : null));
    const block = h('div', { cls: ['wwh-row', collapsed ? 'is-collapsed' : 'is-open', index % 2 ? 'is-alt' : ''] }, headLine);
    if (!collapsed) {
      const rows = h('div', { cls: 'wwh-rows' });
      row.marks.forEach((m) => rows.appendChild(this.markLine(m, todayN)));
      block.appendChild(rows);
    }
    block.appendChild(this.overlay(layout, row, collapsed));
    return block;
  }

  /** 收起來的摘要：期間（實心）的色條加每件一個點。 */
  summary(row) {
    const box = h('div', { cls: 'wwh-summary' });
    for (const m of row.marks) {
      if (m.depth) continue;
      if (m.shape === 'bar' && !m.inferred) {
        box.appendChild(
          h('span', { cls: ['wwh-sum-bar', m.late ? 'is-late' : '', m.status === 'done' ? 'is-done' : ''], style: { left: `${m.leftPct}%`, width: `${m.widthPct}%` }, title: describeMark(m) }),
        );
        continue;
      }
      const at = m.shape === 'bar' ? Math.min(100, m.leftPct + m.widthPct) : m.leftPct;
      box.appendChild(
        h('span', {
          cls: ['wwh-sum-dot', m.late ? 'is-late' : '', m.inferred ? 'is-inferred' : '', m.status === 'done' ? 'is-done' : ''],
          style: { left: `${at}%` },
          title: describeMark(m),
        }),
      );
    }
    return box;
  }

  /** 每塊的背景層：週線、暫停、連線、今天線；蓋在右邊那欄上、不吃點擊。 */
  overlay(layout, row, collapsed) {
    const lay = h('div', { cls: 'wwh-overlay' });
    const rows = collapsed ? 0 : row.marks.length;
    const height = HEAD_H + rows * ROW_H;
    for (const t of layout.ticks) lay.appendChild(h('i', { cls: ['wwh-grid', `is-${t.kind}`], style: { left: `${t.pct}%` } }));
    for (const p of row.pauses) lay.appendChild(h('i', { cls: 'wwh-pause', style: { left: `${p.leftPct}%`, width: `${p.widthPct}%` } }));
    if (!collapsed && row.links.length) lay.appendChild(this.linksSvg(row, height));
    if (layout.todayPct !== null) lay.appendChild(h('i', { cls: 'wwh-today-line', style: { left: `${layout.todayPct}%` } }));
    return lay;
  }

  linksSvg(row, height) {
    const index = {};
    row.marks.forEach((m, i) => {
      if (m.id) index[m.id] = i;
    });
    const svg = hs('svg', { class: 'wwh-links', viewBox: `0 0 100 ${height}`, preserveAspectRatio: 'none' });
    for (const l of row.links) {
      if (index[l.from] === undefined || index[l.to] === undefined) continue;
      const y1 = HEAD_H + index[l.from] * ROW_H + ROW_H / 2;
      const y2 = HEAD_H + index[l.to] * ROW_H + ROW_H / 2;
      const mid = Math.min(Math.max(l.x1 + 0.6, (l.x1 + l.x2) / 2), Math.max(l.x2 - 0.4, l.x1 + 0.6));
      const d = `M ${l.x1} ${y1} H ${mid} V ${y2} H ${l.x2}`;
      svg.appendChild(hs('path', { d, class: l.critical ? 'wwh-link-path is-critical' : 'wwh-link-path', fill: 'none' }));
    }
    return svg;
  }

  /** 展開後的一件一列：左欄圖示、文字、日期；右邊同一列只放記號（期間是色條、點是帶種類圖示的小圓）。 */
  markLine(m, todayN) {
    const state = [
      m.late ? 'is-late' : '',
      m.inferred ? 'is-inferred' : '',
      m.critical ? 'is-critical' : '',
      m.status === 'done' ? 'is-done' : '',
      m.status === 'cancelled' ? 'is-cancelled' : '',
    ];
    const onClick = (e) => this.plugin.itemMenu(e, m.raw);
    const kind = m.kind && ICON_SHAPES[m.kind] ? m.kind : m.shape === 'bar' ? 'period' : null;
    const left = h(
      'div',
      { cls: ['wwh-cell-left', 'wwh-mark-label', m.depth ? 'is-child' : '', ...state], title: describeMark(m), on: { click: onClick } },
      h('span', { cls: ['wwh-kind-ico', m.kind ? `kind-${m.kind}` : ''] }, kind ? icon(kind, 15, 1.5) : null),
      h('span', { cls: 'wwh-mark-lines' }, h('span', { cls: 'wwh-mark-text', text: m.text }), h('span', { cls: 'wwh-mark-when', text: markWhen(m, todayN) })),
    );
    const track = h('div', { cls: 'wwh-cell-track' });
    if (m.baseline) {
      track.appendChild(h('i', { cls: 'wwh-baseline', style: { left: `${m.baseline.leftPct}%`, width: `${m.baseline.widthPct}%` }, title: '原定' }));
    }
    track.appendChild(this.markEl(m, state, kind, onClick));
    return h('div', { cls: ['wwh-line', 'wwh-mark-line', ...state] }, left, track);
  }

  markEl(m, state, kind, onClick) {
    const cls = ['wwh-mark', `is-${m.shape}`, m.kind ? `kind-${m.kind}` : '', ...state, m.depth ? 'is-child' : '', m.clippedLeft ? 'clip-left' : '', m.clippedRight ? 'clip-right' : ''];
    if (m.shape === 'point') {
      return h('span', { cls, style: { left: `${m.leftPct}%` }, title: describeMark(m), on: { click: onClick } }, kind ? icon(kind, 13, 1.7) : null);
    }
    return h('span', { cls, style: { left: `${m.leftPct}%`, width: `${m.widthPct}%` }, title: describeMark(m), on: { click: onClick } });
  }

  renderMonth(el, home) {
    const ui = this.plugin.ui;
    const today = dayNumber(home.today);
    const base = today !== null ? new Date(today * 86400000) : new Date();
    const cur = ui.month || { year: base.getUTCFullYear(), month: base.getUTCMonth() };
    const m = layoutMonth(home.timeline, { today: home.today, year: cur.year, month: cur.month });
    const go = (delta) => {
      ui.month = shiftMonth(cur.year, cur.month, delta);
      this.safe('時間軸', this.timelineEl, (e2) => this.renderTimeline(e2));
    };
    el.appendChild(
      h(
        'div',
        { cls: 'wwh-month-head' },
        h('button', { cls: 'wwh-small-btn', text: '‹', on: { click: () => go(-1) } }),
        h('span', { cls: 'wwh-month-title', text: `${m.year} 年 ${m.month + 1} 月` }),
        h('button', { cls: 'wwh-small-btn', text: '›', on: { click: () => go(1) } }),
        h('button', {
          cls: 'wwh-small-btn',
          text: '回到今天',
          on: {
            click: () => {
              ui.month = null;
              this.safe('時間軸', this.timelineEl, (e2) => this.renderTimeline(e2));
            },
          },
        }),
      ),
    );
    const grid = h('div', { cls: 'wwh-month' });
    for (const w of WEEKDAY) grid.appendChild(h('div', { cls: 'wwh-month-dow', text: w }));
    for (const week of m.weeks) {
      for (const d of week) {
        const cell = h('div', { cls: ['wwh-day', d.inMonth ? '' : 'is-out', d.isToday ? 'is-today' : ''] }, h('div', { cls: 'wwh-day-num', text: String(d.day) }));
        const shown = d.marks.slice(0, 3);
        for (const mk of shown) {
          cell.appendChild(
            h('div', {
              cls: ['wwh-day-mark', mk.kind ? `kind-${mk.kind}` : '', mk.late ? 'is-late' : '', mk.inferred ? 'is-inferred' : '', mk.status === 'done' ? 'is-done' : ''],
              text: `${mk.continues ? '↳ ' : ''}${mk.text}`,
              title: `${mk.row ? mk.row + '：' : ''}${mk.text}`,
              on: { click: (e) => this.plugin.itemMenu(e, mk.raw) },
            }),
          );
        }
        if (d.marks.length > shown.length) cell.appendChild(h('div', { cls: 'wwh-muted wwh-day-more', text: `還有 ${d.marks.length - shown.length} 件` }));
        grid.appendChild(cell);
      }
    }
    el.appendChild(grid);
  }

  // ---- 待辦 ----
  renderTodo(el) {
    const p = this.plugin;
    el.appendChild(h('h2', { text: '待辦' }));
    if (!p.home) return;
    const ui = p.ui;
    for (const g of todoGroups(p.home)) {
      const collapsed = ui.todoCollapsed[g.key] !== undefined ? ui.todoCollapsed[g.key] : g.defaultCollapsed;
      const head = h(
        'button',
        {
          cls: ['wwh-group-head', `is-${g.key}`],
          attrs: { 'aria-expanded': collapsed ? 'false' : 'true' },
          on: {
            click: () => {
              ui.todoCollapsed[g.key] = !collapsed;
              this.safe('待辦', this.leftEl, (e2) => this.renderTodo(e2));
            },
          },
        },
        h('span', { cls: ['wwh-chev', collapsed ? '' : 'is-open'] }, icon('chevron', 14, 2)),
        h('span', { text: g.label }),
        h('span', { cls: 'wwh-pill', text: String(g.items.length) }),
      );
      const box = h('div', { cls: 'wwh-group' }, head);
      el.appendChild(box);
      if (collapsed) continue;
      if (!g.items.length) {
        box.appendChild(h('div', { cls: 'wwh-empty', text: '沒有' }));
        continue;
      }
      for (const it of g.items) box.appendChild(this.todoRow(it, g.key));
    }
  }

  todoRow(it, groupKey) {
    const row = h('div', { cls: ['wwh-todo', groupKey === 'overdue' || it.late ? 'is-late' : '', it.inferred ? 'is-inferred' : ''] });
    const box = h('input', {
      cls: 'wwh-check',
      attrs: { type: 'checkbox' },
      title: '打勾 = 完成',
      on: {
        click: () => {
          row.classList.add('is-done');
          this.plugin.runAction(actions.done(it));
        },
      },
    });
    const names = asArray(it.entities);
    const kind = it.kind && ICON_SHAPES[KIND_BY_LABEL[it.kind] || it.kind] ? KIND_BY_LABEL[it.kind] || it.kind : null;
    const meta = h('div', { cls: 'wwh-todo-meta' }, h('span', { cls: 'wwh-todo-kind' }, kind ? icon(kind, 13) : null, kindLabel(it.kind) || ''));
    if (names.length) meta.appendChild(h('a', { cls: 'wwh-todo-entity wwh-link', text: names[0], on: { click: () => this.plugin.openEntity(names[0]) } }));
    if (it.inferred) {
      meta.appendChild(h('span', { cls: 'wwh-tag-inferred', text: '推測' }));
      meta.appendChild(h('button', { cls: 'wwh-small-btn wwh-soft-btn', text: '推測的，記成確認', on: { click: () => this.plugin.runAction(actions.confirmInferred(it)) } }));
    }
    row.appendChild(box);
    row.appendChild(h('div', { cls: 'wwh-todo-body' }, h('span', { cls: 'wwh-todo-text', text: it.text || '' }), meta));
    row.appendChild(h('button', { cls: 'wwh-todo-when', title: '改日期、時間', text: formatWhen(it) || '（沒日期）', on: { click: () => this.plugin.editDateForm(it) } }));
    row.appendChild(h('button', { cls: 'wwh-sq-btn', title: '更多', on: { click: (e) => this.plugin.itemMenu(e, it) } }, icon('dots', 14, 1.7)));
    return row;
  }

  // ---- 要你確認的、其他要處理的 ----
  renderRight(el) {
    const p = this.plugin;
    const sure = h('section', { cls: 'wwh-card wwh-card-confirm' }, h('h2', { text: '要你確認的' }));
    el.appendChild(sure);
    if (!p.home) return;
    if (!p.home.confirm.length) sure.appendChild(h('div', { cls: 'wwh-empty', text: '沒有' }));
    for (const c of p.home.confirm) {
      const card = h('div', { cls: 'wwh-confirm' }, h('div', { cls: 'wwh-confirm-text', text: c.text || '' }));
      const btns = h('div', { cls: 'wwh-confirm-buttons' });
      asArray(c.results)
        .filter(isObject)
        .forEach((r, i) => {
          btns.appendChild(h('button', { cls: ['wwh-small-btn', i === 0 ? 'is-primary' : ''], text: r.label || '', on: { click: () => p.chooseResult(c, r) } }));
        });
      card.appendChild(btns);
      sure.appendChild(card);
    }
    const open = p.ui.othersOpen;
    const others = h('section', { cls: 'wwh-card wwh-card-others' });
    others.appendChild(
      h(
        'button',
        {
          cls: 'wwh-group-head is-others',
          attrs: { 'aria-expanded': open ? 'true' : 'false' },
          on: {
            click: () => {
              p.ui.othersOpen = !open;
              this.safe('要你確認的', this.rightEl, (e2) => this.renderRight(e2));
            },
          },
        },
        h('span', { cls: ['wwh-chev', open ? 'is-open' : ''] }, icon('chevron', 14, 2)),
        h('span', { text: '其他要處理的' }),
        h('span', { cls: 'wwh-pill', text: String(p.home.others.length) }),
      ),
    );
    el.appendChild(others);
    if (!open) return;
    if (!p.home.others.length) others.appendChild(h('div', { cls: 'wwh-empty', text: '沒有' }));
    for (const o of p.home.others) {
      others.appendChild(
        h(
          'div',
          { cls: 'wwh-other' },
          h('span', { cls: 'wwh-other-text', text: o.text || '' }),
          o.dismiss ? h('button', { cls: 'wwh-small-btn', text: '不用管', on: { click: () => p.runAction(actions.dismiss(o.id)) } }) : null,
        ),
      );
    }
  }

  // ---- 實體總覽（右側抽屜）----
  renderDrawer(el) {
    const d = this.plugin.ui.drawer;
    el.classList.toggle('is-open', !!d.open);
    if (!d.open) return;
    const head = h(
      'div',
      { cls: 'wwh-drawer-head' },
      h('button', { cls: 'wwh-small-btn', text: '← 回上一頁', on: { click: () => this.plugin.drawerBack() } }),
      h('button', { cls: 'wwh-icon-btn', text: '✕', title: '關掉', on: { click: () => this.plugin.drawerClose() } }),
    );
    el.appendChild(head);
    if (d.loading && !d.data) {
      el.appendChild(h('div', { cls: 'wwh-empty', text: '讀取中……' }));
      return;
    }
    if (d.error) {
      el.appendChild(h('div', { cls: 'wwh-empty', text: d.error }));
      return;
    }
    if (d.data) this.drawerBody(el, d.data);
  }

  drawerBody(el, got) {
    const p = this.plugin;
    const e = got.entity;
    if (!e) {
      el.appendChild(h('h3', { text: got.query || '' }));
      el.appendChild(h('div', { cls: 'wwh-empty', text: asArray(got.mentions).length ? '沒有登記這個名稱；有這些卡提到它：' : '沒有登記這個名稱，也沒有卡提到它' }));
      for (const m of asArray(got.mentions)) el.appendChild(h('div', { cls: 'wwh-drawer-line', text: m.title || '' }));
      return;
    }
    const prog = e.progress ? progressWord(e.progress) : null;
    el.appendChild(
      h(
        'div',
        { cls: 'wwh-drawer-title' },
        h('h3', { text: e.name }),
        h('span', { cls: 'wwh-muted', text: [e.type, prog && prog !== '進行中' ? prog : ''].filter(Boolean).join('，') }),
        h('button', { cls: 'wwh-icon-btn', text: '⋯', title: '這件事可以做的', on: { click: (ev) => p.entityMenu(ev, e.name, e.progress) } }),
      ),
    );
    // 別名
    const aliasBox = h('div', { cls: 'wwh-drawer-aliases' }, h('span', { cls: 'wwh-muted', text: '也叫：' }));
    for (const a of asArray(e.aliases)) {
      aliasBox.appendChild(
        h(
          'span',
          { cls: 'wwh-alias' },
          a,
          h('button', { cls: 'wwh-icon-btn', text: '✕', title: '拿掉這個別名', on: { click: () => p.runAction(actions.alias(e.name, a, 'remove')) } }),
        ),
      );
    }
    aliasBox.appendChild(h('button', { cls: 'wwh-small-btn', text: '＋別名', on: { click: () => p.aliasForm(e.name) } }));
    el.appendChild(aliasBox);
    // 標籤
    const tags = asArray(got.tags).filter(isObject);
    if (tags.length) {
      const box = h('div', { cls: 'wwh-drawer-tags' });
      for (const t of tags) {
        box.appendChild(
          h(
            'div',
            { cls: 'wwh-drawer-line' },
            h('span', { cls: 'wwh-muted', text: `${t.field}：` }),
            asArray(t.words).join('、') || '（沒有）',
            h('button', { cls: 'wwh-icon-btn', text: '✎', title: '改標籤', on: { click: () => p.tagForm(e.name, t.field, asArray(t.words)) } }),
          ),
        );
      }
      el.appendChild(box);
    }
    if (got.synthesis) {
      el.appendChild(h('div', { cls: 'wwh-drawer-line' }, h('a', { cls: 'wwh-link', text: '開綜合卡', on: { click: () => p.openPathInVault(got.synthesis) } })));
    }
    const section = (title, items, render) => {
      if (!items.length) return;
      el.appendChild(h('h4', { text: `${title}（${items.length}）` }));
      for (const it of items) el.appendChild(render(it));
    };
    section('日程', asArray(got.agenda), (a) =>
      h(
        'div',
        { cls: 'wwh-drawer-line' },
        h('input', { attrs: { type: 'checkbox' }, title: '打勾 = 完成', on: { click: () => p.runAction(actions.done(a)) } }),
        h('a', { cls: 'wwh-link', text: `${formatWhen(a) || ''} `, on: { click: () => p.editDateForm(a) } }),
        `${a.kind || ''} ${a.text || ''}`,
      ),
    );
    section('檔案卡', asArray(got.cards), (c) =>
      h(
        'div',
        { cls: ['wwh-drawer-line', c.ruled_out ? 'is-cancelled' : ''] },
        h('a', { cls: 'wwh-link', text: c.title || c.id, on: { click: () => p.openLookupCard(c) } }),
        h('span', { cls: 'wwh-muted', text: `　${[c.card_type, c.date].filter(Boolean).join('　')}${c.stale ? '　原檔改過' : ''}` }),
      ),
    );
    section('你說過的', asArray(got.statements), (s) => h('div', { cls: 'wwh-drawer-line', text: `${s.date ? s.date + ' ' : ''}${s.text || ''}` }));
    section('裁示', asArray(got.rulings), (r) => h('div', { cls: 'wwh-drawer-line', text: r.text || '' }));
    section('推算', asArray(got.findings), (f) => h('div', { cls: 'wwh-drawer-line', text: f.text ? `${f.text}` : f.redo || '' }));
  }
}

// ---------------------------------------------------------------------------------------------------------------
// 外掛本體
// ---------------------------------------------------------------------------------------------------------------

class WikiWithWillyPlugin extends Plugin {
  async onload() {
    this.ui = defaultUi();
    this.home = null;
    this.homeError = null;
    this.needsReload = false;
    this.refreshing = false;
    this.refreshAgain = false;
    this.lastKbAt = 0;
    this.applying = new Set();
    this.tracker = createApplyTracker();
    this.cardIndex = null;
    this.cardIndexAt = 0;
    this.activePath = null;
    this.loadedVersion = this.manifest && this.manifest.version;
    this.vaultPath = this.basePath();
    this.data = sanitizeData(await this.loadData());
    this.kbInfo = findKb({ vaultPath: this.vaultPath });
    this.runner = null;
    if (this.kbInfo.ok) {
      this.runner = createKbRunner({ kbPath: this.kbInfo.kbPath, cwd: this.vaultPath, execFile: this.execFileOverride });
      const inner = this.runner.run;
      this.runner.run = async (args) => {
        try {
          return await inner(args);
        } finally {
          this.lastKbAt = Date.now();
        }
      };
    }
    try {
      this.app.vault.setConfig('showUnsupportedFiles', true);
    } catch (e) {
      console.error('[wiki-with-willy] 沒辦法開「偵測所有副檔名」', e);
    }

    this.registerView(VIEW_TYPE, (leaf) => new HomeView(leaf, this));
    this.addRibbonIcon('home', '開啟首頁', () => this.activateHome());
    this.addCommand({ id: 'open-home', name: '開啟首頁', callback: () => this.activateHome() });
    this.registerMarkdownPostProcessor((el) => this.linkifyCardRefs(el));

    const ws = this.app.workspace;
    this.registerEvent(ws.on('file-open', (file) => this.onFileOpen(file)));
    this.registerEvent(ws.on('active-leaf-change', () => this.onActiveChange()));
    this.registerEvent(ws.on('editor-change', (editor, info) => this.onEditorChange(editor, info)));
    this.registerEvent(this.app.vault.on('modify', (file) => this.onVaultModify(file)));
    this.registerDomEvent(document, 'selectionchange', () => this.onSelection());
    this.registerInterval(setInterval(() => this.checkSelfUpdate(), 60000));

    ws.onLayoutReady(() => {
      this.startWatch();
      this.refresh();
      this.ensureHomeOpen();
    });
  }

  onunload() {
    if (this.watcher) {
      try {
        this.watcher.close();
      } catch (e) {
        // 關不掉也沒關係
      }
    }
    if (this.debounceTimer) clearTimeout(this.debounceTimer);
  }

  basePath() {
    const a = this.app.vault.adapter;
    if (a && typeof a.getBasePath === 'function') return a.getBasePath();
    return (a && a.basePath) || '';
  }

  // ---- 分頁 ----
  views() {
    return this.app.workspace
      .getLeavesOfType(VIEW_TYPE)
      .map((l) => l.view)
      .filter((v) => v && typeof v.render === 'function');
  }

  renderAll() {
    for (const v of this.views()) v.render();
  }

  ensureHomeOpen() {
    if (this.app.workspace.getLeavesOfType(VIEW_TYPE).length === 0) this.activateHome();
  }

  async activateHome() {
    const ws = this.app.workspace;
    let leaf = ws.getLeavesOfType(VIEW_TYPE)[0];
    if (!leaf) {
      leaf = ws.getLeaf('tab');
      await leaf.setViewState({ type: VIEW_TYPE, active: true });
    }
    ws.revealLeaf(leaf);
  }

  // ---- 叫 kb ----
  async kb(args) {
    if (!this.runner) return { code: -1, stdout: '', stderr: NO_KB_TEXT };
    return this.runner.run(args);
  }

  toast(text, opts) {
    const o = opts || {};
    if (!o.undo) return new Notice(text, o.timeout || 6000);
    const frag = document.createDocumentFragment();
    frag.appendChild(h('span', { text: `${text}　` }));
    let notice = null;
    frag.appendChild(
      h('button', {
        cls: 'wwh-undo',
        text: '復原',
        on: {
          click: () => {
            if (notice && notice.hide) notice.hide();
            o.undo();
          },
        },
      }),
    );
    notice = new Notice(frag, o.timeout || 10000);
    return notice;
  }

  actionCtx() {
    return {
      kb: (args) => this.kb(args),
      toast: (t, o) => this.toast(t, o),
      confirm: async (o) => !!(await openForm(this.app, Object.assign({ okText: '好，做' }, o))),
      info: (o) => openForm(this.app, Object.assign({ hideCancel: true, okText: '知道了' }, o)),
      refresh: () => this.scheduleRefresh(),
      log: (m) => console.error('[wiki-with-willy]', m),
    };
  }

  runAction(action) {
    return performAction(this.actionCtx(), action);
  }

  // ---- 首頁資料 ----
  scheduleRefresh() {
    if (this.debounceTimer) clearTimeout(this.debounceTimer);
    this.debounceTimer = softTimeout(() => {
      this.debounceTimer = null;
      this.refresh();
    }, DEBOUNCE_MS);
  }

  async refresh() {
    if (!this.runner) {
      this.renderAll();
      return;
    }
    if (this.refreshing) {
      this.refreshAgain = true;
      return;
    }
    this.refreshing = true;
    try {
      do {
        this.refreshAgain = false;
        const res = await this.runner.run(homeArgs(openedIds(this.data)));
        const c = classify(res);
        if (c.kind === 'ok') {
          const j = parseJson(res.stdout);
          if (isObject(j)) {
            this.home = normalizeHome(j);
            this.homeError = null;
          } else {
            this.homeError = 'kb 回的不是首頁資料';
          }
        } else {
          this.homeError = c.message;
          if (c.kind === 'failed') console.error('[wiki-with-willy] kb home 失敗', res.stderr || res.stdout);
        }
        this.checkSelfUpdate();
        this.renderAll();
        if (this.ui.drawer.open && this.ui.drawer.stack.length) this.loadDrawer(false);
      } while (this.refreshAgain);
    } finally {
      this.refreshing = false;
    }
  }

  startWatch() {
    const dir = path.join(this.vaultPath, '.system');
    try {
      this.watcher = fs.watch(dir, { persistent: false }, (evt, name) => {
        if (name && !WATCH_FILES.includes(String(name))) return;
        this.scheduleRefresh();
      });
      this.watcher.on('error', (e) => console.error('[wiki-with-willy] 看 .system 出錯', e));
    } catch (e) {
      console.error('[wiki-with-willy] 沒辦法看 .system 的變動', e);
    }
  }

  checkSelfUpdate() {
    if (this.needsReload || !this.manifest || !this.manifest.dir) return;
    try {
      const text = fs.readFileSync(path.join(this.vaultPath, this.manifest.dir, 'manifest.json'), 'utf8');
      if (manifestChanged(this.loadedVersion, text)) {
        this.needsReload = true;
        this.renderAll();
      }
    } catch (e) {
      // 讀不到就不提示
    }
  }

  async reloadSelf() {
    const plugins = this.app.plugins;
    try {
      await plugins.disablePlugin(PLUGIN_ID);
      await plugins.enablePlugin(PLUGIN_ID);
    } catch (e) {
      console.error('[wiki-with-willy] 重新載入失敗', e);
      new Notice('重新載入沒成功，請到設定裡把這個外掛關掉再打開');
    }
  }

  // ---- 開檔 ----
  openCtx() {
    let shell = null;
    try {
      shell = require('electron').shell;
    } catch (e) {
      shell = null;
    }
    return {
      platform: process.platform,
      toast: (t) => this.toast(t),
      openPath: (p) => (shell ? shell.openPath(p) : Promise.resolve('這台電腦沒辦法從 Obsidian 開檔')),
      openUrl: (u) => {
        if (shell && shell.openExternal) shell.openExternal(u);
        else if (typeof window !== 'undefined') window.open(u);
      },
    };
  }

  async recordOpened(card) {
    if (!card) return;
    this.data = recordOpened(this.data, card, new Date().toISOString());
    try {
      await this.saveData(this.data);
    } catch (e) {
      console.error('[wiki-with-willy] 存不了最近開過的', e);
    }
  }

  async openFile(f) {
    if (f.card) this.recordOpened(f.card);
    const hasOpen = isObject(f.open) && (f.open.path || f.open.url);
    if (!hasOpen && f.card_path) {
      this.openPathInVault(f.card_path); // 沒有原檔可開，退一步開卡
      return;
    }
    await openOriginal(this.openCtx(), f.open);
  }

  openCard(f) {
    if (f.card) this.recordOpened(f.card);
    if (f.card_path) this.openPathInVault(f.card_path);
  }

  openLookupCard(c) {
    if (c.id) this.recordOpened(c.id);
    if (c.path) this.openPathInVault(c.path);
  }

  openPathInVault(rel) {
    this.app.workspace.openLinkText(String(rel).replace(/\.md$/, ''), '', false);
  }

  async askClaude(q) {
    return copyAskClaude(
      {
        toast: (t) => this.toast(t),
        writeClipboard: async (t) => {
          try {
            await navigator.clipboard.writeText(t);
          } catch (e) {
            require('electron').clipboard.writeText(t);
          }
        },
      },
      q,
    );
  }

  // ---- 實體抽屜 ----
  openEntity(name) {
    const d = this.ui.drawer;
    d.open = true;
    d.stack.push(name);
    d.data = null;
    d.error = null;
    this.loadDrawer(true);
  }

  drawerBack() {
    const d = this.ui.drawer;
    d.stack.pop();
    if (!d.stack.length) {
      this.drawerClose();
      return;
    }
    d.data = null;
    this.loadDrawer(true);
  }

  drawerClose() {
    const d = this.ui.drawer;
    d.open = false;
    d.stack = [];
    d.data = null;
    d.error = null;
    this.renderAll();
  }

  async loadDrawer(showLoading) {
    const d = this.ui.drawer;
    const name = d.stack[d.stack.length - 1];
    if (!name) return;
    d.loading = true;
    if (showLoading) this.renderAll();
    const res = await this.kb(['lookup', name, '--json']);
    if (d.stack[d.stack.length - 1] !== name) return; // 她已經點去別的
    const c = classify(res);
    d.loading = false;
    if (c.kind === 'ok') {
      d.data = parseJson(res.stdout);
      d.error = d.data ? null : 'kb 回的不是總覽資料';
      if (d.data && d.data.entity && d.data.entity.name) d.stack[d.stack.length - 1] = d.data.entity.name; // 改名、別名查到現在的名字
    } else {
      d.error = c.message;
    }
    this.renderAll();
  }

  // ---- 選單與表單 ----
  showMenu(ev, entries) {
    const menu = new Menu();
    for (const e of entries) menu.addItem((it) => it.setTitle(e.title).onClick(e.run));
    if (ev && ev.clientX !== undefined) menu.showAtMouseEvent(ev);
    else menu.showAtPosition({ x: 0, y: 0 });
  }

  /** 一筆日程（時間軸的 mark、待辦的項目）能做的事。 */
  itemMenu(ev, it) {
    const entries = [];
    if (it.status === 'done' || it.status === 'cancelled') {
      entries.push({ title: '重新打開', run: () => this.runAction({ id: 'reopen', args: ['agenda', 'reopen', it.id], undo: () => ({ args: ['agenda', it.status === 'done' ? 'done' : 'cancel', it.id] }) }) });
    } else {
      entries.push({ title: '打勾，完成了', run: () => this.runAction(actions.done(it)) });
      entries.push({ title: '改日期、時間', run: () => this.editDateForm(it) });
      if (it.inferred) entries.push({ title: '推測的，記成確認', run: () => this.runAction(actions.confirmInferred(it)) });
      entries.push({ title: '取消這件', run: () => this.runAction(actions.cancel(it)) });
    }
    const names = asArray(it.entities);
    if (names.length) entries.push({ title: `看「${names[0]}」`, run: () => this.openEntity(names[0]) });
    this.showMenu(ev, entries);
  }

  entityMenu(ev, name, progress) {
    const entries = [{ title: '看總覽', run: () => this.openEntity(name) }];
    const cur = progressWord(progress);
    if (cur) {
      if (cur !== '結案') entries.push({ title: '記成結案', run: () => this.runAction(actions.progress(name, 'closed', progress)) });
      if (cur !== '擱置') entries.push({ title: '記成擱置', run: () => this.runAction(actions.progress(name, 'paused', progress)) });
      if (cur !== '進行中') entries.push({ title: '改回進行中', run: () => this.runAction(actions.progress(name, 'active', progress)) });
    }
    entries.push({ title: '改名', run: () => this.renameForm(name) });
    entries.push({ title: '合併到另一個……', run: () => this.mergeForm(name) });
    entries.push({ title: '加別名', run: () => this.aliasForm(name) });
    this.showMenu(ev, entries);
  }

  entityNames() {
    const rows = this.home && this.home.timeline ? asArray(this.home.timeline.rows) : [];
    return rows.filter((r) => r && r.key !== '_other' && r.label).map((r) => r.label);
  }

  async addAgendaForm(prefill) {
    const p = prefill || {};
    const today = (this.home && this.home.today) || '';
    const v = await openForm(this.app, {
      title: '新增日程',
      okText: '加進日程',
      fields: [
        { key: 'kind', label: '種類', type: 'select', options: ['到期', '會議', '承諾', '提醒', '期間'], value: p.kind || '到期' },
        { key: 'date', label: '日期（期間是結束日）', type: 'date', value: p.date || today, required: true },
        { key: 'start', label: '開始日（期間才填）', type: 'date', value: p.start || '' },
        { key: 'time', label: '時間（可不填）', type: 'time', value: p.time || '' },
        { key: 'text', label: '要做什麼', type: 'text', value: p.text || '', required: true },
        { key: 'entity', label: '哪件事（可不填）', type: 'text', value: p.entity || '', list: this.entityNames() },
      ],
    });
    if (!v) return null;
    const r = await this.runAction(
      actions.add({ kind: v.kind, date: v.date, start: v.start, time: v.time, text: v.text, entities: v.entity ? [v.entity] : [] }),
    );
    return r;
  }

  async editDateForm(it) {
    const isPeriod = isPeriodKind(it.kind);
    const fields = [{ key: 'date', label: isPeriod ? '結束日' : '日期', type: 'date', value: itemDate(it), required: true }];
    if (isPeriod) fields.unshift({ key: 'start', label: '開始日', type: 'date', value: it.start || '' });
    fields.push({ key: 'time', label: '時間（可不填）', type: 'time', value: it.time || '' });
    const v = await openForm(this.app, { title: `改「${it.text || ''}」的日期`, okText: '改', fields });
    if (!v) return null;
    const a = actions.edit(it, v);
    if (!a) {
      this.toast('沒有要改的');
      return null;
    }
    return this.runAction(a);
  }

  async chooseResult(item, result) {
    if (!Array.isArray(result.argv)) {
      this.toast(NEED_CLAUDE_TEXT);
      return null;
    }
    const argv = result.argv;
    // 「加成日程」這類只給了原文的：開新增表單，原文填進「要做什麼」，存了再接著做 result.after
    if (argv[0] === 'agenda' && argv[1] === 'add' && !argv.includes('--date')) {
      const at = argv.indexOf('--text');
      const text = (isObject(result.fill) && result.fill.value) || (at >= 0 ? argv[at + 1] : '') || '';
      const r = await this.addAgendaForm({ text });
      if (r && r.ok && Array.isArray(result.after)) await this.kb(result.after);
      return r;
    }
    let fillValue;
    if (result.fill) {
      const f = isObject(result.fill) ? result.fill : { label: String(result.fill) };
      const v = await openForm(this.app, {
        title: result.label || '請填',
        okText: '好',
        fields: [{ key: 'value', label: f.label || f.rule || f.name || '請填', type: 'text', value: f.value || '', required: true }],
      });
      if (!v) return null;
      fillValue = v.value;
    }
    return this.runAction(actions.result(result, fillValue));
  }

  async renameForm(name) {
    const v = await openForm(this.app, {
      title: `把「${name}」改名`,
      okText: '下一步',
      fields: [{ key: 'name', label: '新名字', type: 'text', value: name, required: true }],
    });
    if (!v || v.name === name) return null;
    const r = await this.runAction(actions.rename(name, v.name));
    if (r && r.ok && this.ui.drawer.open) {
      this.ui.drawer.stack[this.ui.drawer.stack.length - 1] = v.name;
    }
    return r;
  }

  async mergeForm(name) {
    const v = await openForm(this.app, {
      title: `把「${name}」併進哪一個？`,
      okText: '下一步',
      fields: [{ key: 'into', label: '併進（目標的名字）', type: 'text', value: '', required: true, list: this.entityNames() }],
    });
    if (!v || v.into === name) return null;
    const r = await this.runAction(actions.merge(name, v.into));
    if (r && r.ok && this.ui.drawer.open) this.ui.drawer.stack[this.ui.drawer.stack.length - 1] = v.into;
    return r;
  }

  async aliasForm(name) {
    const v = await openForm(this.app, {
      title: `給「${name}」加別名`,
      okText: '加',
      fields: [{ key: 'word', label: '別名', type: 'text', value: '', required: true }],
    });
    if (!v) return null;
    return this.runAction(actions.alias(name, v.word, 'add'));
  }

  async tagForm(name, field, words) {
    const v = await openForm(this.app, {
      title: `改「${name}」的「${field}」`,
      okText: '改',
      fields: [{ key: 'words', label: '多個詞用逗號分開；空著是沒有', type: 'text', value: words.join('、') }],
    });
    if (!v) return null;
    const next = v.words.split(/[,，、]/).map((s) => s.trim()).filter(Boolean);
    return this.runAction(actions.tag(name, field, next, words));
  }

  // ---- 程式產生的頁 ----
  filePathOf(file) {
    return file && file.path ? String(file.path).replace(/\\/g, '/') : '';
  }

  onFileOpen(file) {
    const p = this.filePathOf(file);
    this.switchedTo(p);
    if (p && isGeneratedPage(p)) this.makeReadOnly(p);
  }

  onActiveChange() {
    const view = this.app.workspace.getActiveViewOfType ? this.app.workspace.getActiveViewOfType(MarkdownView) : null;
    this.switchedTo(view && view.file ? this.filePathOf(view.file) : null);
  }

  switchedTo(now) {
    const prev = this.activePath;
    this.activePath = now || null;
    if (prev && prev !== now && isManagedPage(prev) && this.tracker.leave(prev)) this.applyPage(prev);
  }

  makeReadOnly(p) {
    const leaf = this.app.workspace.getLeavesOfType('markdown').find((l) => l.view && l.view.file && this.filePathOf(l.view.file) === p);
    if (!leaf) return;
    const view = leaf.view;
    const finish = () => this.addGeneratedBanner(view);
    try {
      const state = leaf.getViewState();
      if (state && state.state && state.state.mode !== 'preview') {
        const next = Object.assign({}, state, { state: Object.assign({}, state.state, { mode: 'preview' }) });
        Promise.resolve(leaf.setViewState(next)).then(() => setTimeout(finish, 50), finish);
        return;
      }
    } catch (e) {
      console.error('[wiki-with-willy] 切不了閱讀模式', e);
    }
    finish();
  }

  addGeneratedBanner(view) {
    try {
      const root = view && view.contentEl;
      if (!root || (root.querySelector && root.querySelector('.wwh-generated'))) return;
      const bar = h('div', { cls: 'wwh-generated', text: GENERATED_BANNER });
      root.insertBefore(bar, root.firstChild);
    } catch (e) {
      console.error('[wiki-with-willy] 加不了提示條', e);
    }
  }

  onEditorChange(editor, info) {
    const p = this.filePathOf(info && info.file);
    if (!p || !isManagedPage(p)) return;
    const line = editor.getCursor().line;
    if (this.tracker.edited(p, line, Date.now())) this.applyPage(p);
  }

  onSelection() {
    const view = this.app.workspace.getActiveViewOfType ? this.app.workspace.getActiveViewOfType(MarkdownView) : null;
    if (!view || !view.file || !view.editor) return;
    const p = this.filePathOf(view.file);
    if (!isManagedPage(p)) return;
    if (this.tracker.cursor(p, view.editor.getCursor().line)) this.applyPage(p);
  }

  async saveOpen(p) {
    for (const leaf of this.app.workspace.getLeavesOfType('markdown')) {
      const v = leaf.view;
      if (v && v.file && this.filePathOf(v.file) === p && typeof v.save === 'function') {
        try {
          await v.save();
        } catch (e) {
          console.error('[wiki-with-willy] 存不了開著的頁', e);
        }
      }
    }
  }

  async applyPage(p) {
    if (!this.runner || this.applying.has(p)) return;
    this.applying.add(p);
    try {
      await this.saveOpen(p);
      const res = await this.runner.run(['renders', 'apply', p, '--json']);
      this.tracker.applied(p);
      const c = classify(res);
      if (c.kind !== 'ok') {
        this.toast(c.message);
        if (c.kind === 'failed') console.error('[wiki-with-willy] kb renders apply 失敗', res.stderr || res.stdout);
        return;
      }
      const sum = summarizeApply(parseJson(res.stdout), pageName(p));
      if (sum.text) this.toast(sum.text);
      this.scheduleRefresh();
    } finally {
      // kb 改寫檔案的 modify 事件會晚一點才到，多擋一下
      softTimeout(() => this.applying.delete(p), 1500);
    }
  }

  onVaultModify(file) {
    const p = this.filePathOf(file);
    if (!p || !(isManagedPage(p) || isGeneratedPage(p))) return;
    const open = this.app.workspace.getLeavesOfType('markdown').some((l) => l.view && l.view.file && this.filePathOf(l.view.file) === p);
    const now = Date.now();
    const typing = this.tracker.isTyping(p, now);
    if (!shouldToastModified({ open, applying: this.applying.has(p), typing, lastKbAt: this.lastKbAt, now })) return;
    this.tracker.external(p, now);
    const reading = this.app.vault.cachedRead ? this.app.vault.cachedRead(file) : Promise.resolve('');
    Promise.resolve(reading).then(
      (text) => this.toast(hasCarriedSection(text) && this.tracker.isTyping(p, now, 60000) ? `${UPDATED_TEXT}；${CARRIED_TEXT}` : UPDATED_TEXT),
      () => this.toast(UPDATED_TEXT),
    );
  }

  // ---- 〔f-…〕變連結 ----
  cardPathOf(id) {
    const now = Date.now();
    if (!this.cardIndex || (!this.cardIndex.has(id) && now - this.cardIndexAt > 10000)) {
      const map = new Map();
      for (const f of this.app.vault.getMarkdownFiles()) {
        if (!String(f.path).startsWith('檔案索引/')) continue;
        const cache = this.app.metadataCache.getFileCache(f);
        const fm = cache && cache.frontmatter;
        const cid = fm && (fm['編號'] || fm.id);
        if (typeof cid === 'string') map.set(cid, f.path);
      }
      this.cardIndex = map;
      this.cardIndexAt = now;
    }
    return this.cardIndex.get(id) || null;
  }

  linkifyCardRefs(el) {
    const doc = el.ownerDocument || document;
    const walker = doc.createTreeWalker(el, 4 /* NodeFilter.SHOW_TEXT */);
    const texts = [];
    let n = walker.nextNode();
    while (n) {
      if (n.nodeValue && n.nodeValue.indexOf('〔f-') >= 0) texts.push(n);
      n = walker.nextNode();
    }
    for (const node of texts) {
      const parent = node.parentNode;
      if (!parent || (parent.closest && parent.closest('a, code, pre'))) continue;
      const parts = splitCardRefs(node.nodeValue);
      if (!parts.some((x) => x.ref)) continue;
      const frag = doc.createDocumentFragment();
      for (const part of parts) {
        if (part.text !== undefined) {
          frag.appendChild(doc.createTextNode(part.text));
          continue;
        }
        const target = this.cardPathOf(part.ref);
        if (!target) {
          frag.appendChild(doc.createTextNode(`〔${part.ref}〕`));
          continue;
        }
        const a = doc.createElement('a');
        a.className = 'internal-link wwh-cardref';
        a.setAttribute('href', target);
        a.setAttribute('data-href', target);
        a.textContent = `〔${part.ref}〕`;
        a.addEventListener('click', (e) => {
          e.preventDefault();
          this.openPathInVault(target);
        });
        frag.appendChild(a);
      }
      parent.replaceChild(frag, node);
    }
  }
}

module.exports = WikiWithWillyPlugin;
module.exports.default = WikiWithWillyPlugin;
module.exports.lib = {
  PLUGIN_ID,
  VIEW_TYPE,
  WATCH_FILES,
  OPENED_MAX,
  GENERATED_BANNER,
  NO_KB_TEXT,
  VERSION_MISMATCH_TEXT,
  RELOAD_TEXT,
  COPIED_TEXT,
  CARRIED_TEXT,
  UPDATED_TEXT,
  NEED_CLAUDE_TEXT,
  firstLine,
  parseJson,
  samePath,
  isNetworkPath,
  nativePath,
  dayNumber,
  formatWhen,
  markSpan,
  layoutTimeline,
  layoutMonth,
  shiftMonth,
  describeMark,
  normalizeHome,
  todoGroups,
  versionMismatch,
  manifestChanged,
  sanitizeData,
  recordOpened,
  openedIds,
  homeArgs,
  findKb,
  pythonCandidates,
  buildKbArgs,
  createKbRunner,
  classify,
  interpretCheck,
  progressWord,
  actions,
  performAction,
  runUndo,
  searchDecision,
  findArgs,
  removeChipText,
  askClaudeText,
  copyAskClaude,
  openOriginal,
  isManagedPage,
  isGeneratedPage,
  createApplyTracker,
  shouldToastModified,
  summarizeApply,
  hasCarriedSection,
  splitCardRefs,
  rowDefaultCollapsed,
  rowIsCollapsed,
  markWhen,
  fileExt,
  longDate,
  icon,
  RECENT_MAX,
  HomeView,
  FormModal,
  defaultUi,
  h,
};
