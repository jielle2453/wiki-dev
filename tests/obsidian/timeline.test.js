'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadMain } = require('./helpers/env');
const { byClass, byTag } = require('./helpers/fakedom');

const env = loadMain();
const lib = env.lib;
test.after(() => env.restore());

function mark(extra) {
  return Object.assign(
    {
      id: 'a-1', shape: 'bar', kind: 'period', start: '2026-10-01', end: '2026-11-20', time: null, text: '施工', status: 'open',
      late: false, inferred: false, repeat: null, hard: false, entities: ['信義王'],
      baseline: null, critical: false, slack: null, derived: false, children: [],
    },
    extra,
  );
}

function sample() {
  return {
    schema: 'willy-home/1',
    version: '0.28.0',
    today: '2026-10-30',
    cheer: '今天也辛苦了',
    counts: { overdue: 1, today: 1, week: 2, confirm: 1, other: 1 },
    timeline: {
      from: '2026-10-23',
      to: '2026-12-31',
      rows: [
        {
          key: 'e-1a2b3c4d', label: '信義王', type: '案子', progress: 'active',
          marks: [
            mark({ id: 'a-bar', start: '2026-10-25', end: '2026-11-20', text: '施工' }),
            mark({ id: 'a-pt', shape: 'point', kind: 'deadline', start: null, end: '2026-11-05', text: '交水電圖', late: true }),
            mark({ id: 'a-inf', shape: 'point', kind: 'meeting', start: null, end: '2026-11-08', text: '驗收會議', inferred: true }),
            mark({ id: 'a-late', shape: 'point', kind: 'promise', start: null, end: '2026-10-28', text: '回覆報價', late: true }), // #68 前的舊值：照到期畫
          ],
          pauses: [{ start: '2026-10-30', end: '2026-11-03' }],
          links: [],
        },
        {
          // 日程第二題的圖形：子項、連線、基準線、要徑
          key: 'e-2', label: '中山林', type: '案子', progress: 'active',
          marks: [
            mark({
              id: 'a-p', text: '裝修', start: '2026-11-01', end: '2026-12-01', critical: true, slack: 0,
              baseline: { start: '2026-10-28', end: '2026-11-25' },
              children: [
                mark({ id: 'a-c1', text: '水電', start: '2026-11-01', end: '2026-11-10', critical: true }),
                mark({ id: 'a-c2', text: '木工', start: '2026-11-08', end: '2026-11-20', derived: true }),
              ],
            }),
            mark({ id: 'a-after', text: '油漆', start: '2026-12-02', end: '2026-12-10', hard: true }),
          ],
          pauses: [],
          links: [
            { from: 'a-c1', to: 'a-c2', gap: -2, critical: true },
            { from: 'a-p', to: 'a-after', gap: 1, critical: false },
            { from: 'a-nope', to: 'a-after', gap: 0, critical: false }, // 找不到一端：不畫
          ],
        },
        {
          key: '_other', label: '其他', type: null, progress: null,
          marks: [
            mark({ id: 'a-x1', shape: 'diamond', text: '不認得的形狀' }), // 不認得的 shape：不畫
            mark({ id: 'a-x2', kind: 'milestone', text: '不認得的種類' }), // 不認得的 kind：不畫
            mark({ id: 'a-x3', shape: 'point', kind: 'reminder', start: null, end: 'not-a-date', text: '壞日期' }),
            mark({ id: 'a-ok', shape: 'point', kind: 'reminder', start: null, end: '2026-11-15', text: '繳費提醒' }),
          ],
          pauses: [],
          links: [],
        },
      ],
    },
    todo: {
      overdue: [{ id: 'a-late', kind: 'promise', end: '2026-10-28', text: '回覆報價', late: true, entities: ['信義王'] }],
      today: [{ id: 'a-t', kind: 'reminder', end: '2026-10-30', time: '10:00', text: '確認窗簾款式', entities: ['信義王'] }],
      week: [{ id: 'a-w', kind: 'meeting', end: '2026-11-02', text: '看工地', entities: [], inferred: true }],
    },
    confirm: [{ key: 'k1', text: '「王先生」是「王大明」嗎？', results: [{ label: '是，合併', argv: ['entity', 'merge', '王先生', '--into', '王大明'], fill: null }, { label: '跟 Claude 說', argv: null, fill: null }] }],
    others: [{ id: 'p-1', kind: 'missing_file', text: '有一份檔不見了', dismiss: true }],
    recent: [{ card: 'f-1a2b3c4d', title: '報價', type: '報價', date: '2026-10-02', why: 'opened', at: '2026-10-29T10:00:00', open: { path: 'C:/data/報價.xlsx' }, card_path: '檔案索引/報價-1a2b3c4d.md' }],
  };
}

test('時間軸：每個事類實體一列，bar 與點的位置照日期算', () => {
  const home = sample();
  const lay = lib.layoutTimeline(home.timeline, { today: home.today });
  assert.deepStrictEqual(lay.rows.map((r) => r.key), ['e-1a2b3c4d', 'e-2', '_other']);
  assert.strictEqual(lay.from, '2026-10-23');
  assert.strictEqual(lay.to, '2026-12-31');
  assert.strictEqual(lay.spanDays, 70);
  const row = lay.rows[0];
  const bar = row.marks.find((m) => m.id === 'a-bar');
  assert.strictEqual(bar.shape, 'bar');
  // 10/25 是第 3 天（from 之後 2 天），到 11/20 含當天共 27 天
  assert.ok(Math.abs(bar.leftPct - (2 / 70) * 100) < 1e-9);
  assert.ok(Math.abs(bar.widthPct - (27 / 70) * 100) < 1e-9);
  const pt = row.marks.find((m) => m.id === 'a-pt');
  assert.strictEqual(pt.shape, 'point');
  assert.strictEqual(pt.widthPct, 0);
  assert.ok(pt.late);
  assert.ok(row.marks.find((m) => m.id === 'a-inf').inferred);
  // 今天的線在 10/30
  assert.ok(Math.abs(lay.todayPct - ((7 + 0.5) / 70) * 100) < 1e-9);
  // 暫停的灰底
  assert.strictEqual(row.pauses.length, 1);
  assert.ok(Math.abs(row.pauses[0].leftPct - (7 / 70) * 100) < 1e-9);
  assert.ok(Math.abs(row.pauses[0].widthPct - (5 / 70) * 100) < 1e-9);
});

test('時間軸：重疊的 bar 疊成不同層，不重疊的共用一層', () => {
  const tl = {
    from: '2026-10-01', to: '2026-10-31',
    rows: [{ key: 'k', label: 'K', marks: [
      mark({ id: 'a', start: '2026-10-01', end: '2026-10-10', text: 'A' }),
      mark({ id: 'b', start: '2026-10-05', end: '2026-10-15', text: 'B' }),
      mark({ id: 'c', start: '2026-10-20', end: '2026-10-25', text: 'C' }),
    ] }],
  };
  const row = lib.layoutTimeline(tl).rows[0];
  const lane = (id) => row.marks.find((m) => m.id === id).lane;
  assert.notStrictEqual(lane('a'), lane('b'));
  assert.strictEqual(lane('c'), lane('a'));
  assert.strictEqual(row.lanes, 2);
});

test('時間軸：超出範圍的 bar 夾在邊上並標 clipped，完全在外面的不畫', () => {
  const tl = {
    from: '2026-10-10', to: '2026-10-20',
    rows: [{ key: 'k', label: 'K', marks: [
      mark({ id: 'wide', start: '2026-09-01', end: '2026-12-01' }),
      mark({ id: 'out', start: '2026-01-01', end: '2026-01-05' }),
    ] }],
  };
  const row = lib.layoutTimeline(tl).rows[0];
  assert.deepStrictEqual(row.marks.map((m) => m.id), ['wide']);
  assert.strictEqual(row.marks[0].leftPct, 0);
  assert.ok(Math.abs(row.marks[0].widthPct - 100) < 1e-9);
  assert.ok(row.marks[0].clippedLeft && row.marks[0].clippedRight);
});

test('日程第二題的圖形：子項、連線、基準線、要徑畫得出來', () => {
  const lay = lib.layoutTimeline(sample().timeline, { today: '2026-10-30' });
  const row = lay.rows[1];
  const p = row.marks.find((m) => m.id === 'a-p');
  const c1 = row.marks.find((m) => m.id === 'a-c1');
  const c2 = row.marks.find((m) => m.id === 'a-c2');
  assert.ok(p.critical && c1.critical && !c2.critical);
  assert.strictEqual(c1.depth, 1);
  assert.strictEqual(c1.parent, 'a-p');
  assert.ok(c1.lane > p.lane && c2.lane > c1.lane, '子項縮排畫在母項下面，各一層');
  assert.ok(p.baseline && p.baseline.widthPct > 0, '原定的基準線');
  assert.ok(c2.derived);
  // 連線：找不到一端的不畫
  assert.strictEqual(row.links.length, 2);
  const l = row.links.find((x) => x.from === 'a-c1');
  assert.strictEqual(l.to, 'a-c2');
  assert.strictEqual(l.gap, -2);
  assert.ok(l.critical);
  assert.ok(Math.abs(l.x1 - (c1.leftPct + c1.widthPct)) < 1e-9);
  assert.ok(Math.abs(l.x2 - c2.leftPct) < 1e-9);
  assert.strictEqual(l.y1, c1.lane);
  assert.strictEqual(l.y2, c2.lane);
});

test('時間軸：不認得的 shape、kind、壞日期不畫那筆、不報錯', () => {
  const lay = lib.layoutTimeline(sample().timeline, { today: '2026-10-30' });
  const other = lay.rows[2];
  assert.deepStrictEqual(other.marks.map((m) => m.id), ['a-ok']);
  assert.strictEqual(lib.markSpan({ shape: 'hexagon', end: '2026-10-01' }), null);
  assert.strictEqual(lib.markSpan({ shape: 'point', kind: 'whatever', end: '2026-10-01' }), null);
  assert.strictEqual(lib.markSpan(null), null);
  assert.doesNotThrow(() => lib.layoutTimeline({ rows: 'bad' }));
  assert.doesNotThrow(() => lib.layoutTimeline(null));
  assert.doesNotThrow(() => lib.layoutTimeline({ from: 'x', to: 'y', rows: [{ marks: [{ shape: 'bar' }] }] }));
});

test('月曆：點只在那天，期間是一週一條 bar，星期日起算', () => {
  const home = sample();
  const m = lib.layoutMonth(home.timeline, { today: home.today });
  assert.strictEqual(m.year, 2026);
  assert.strictEqual(m.month, 9); // 10 月
  assert.ok(m.weeks.every((w) => w.days.length === 7));
  const days = m.weeks.flatMap((w) => w.days);
  const day = (iso) => days.find((d) => d.date === iso);
  assert.ok(day('2026-10-30').isToday);
  assert.strictEqual(day('2026-10-28').marks.filter((x) => x.text === '回覆報價').length, 1);
  assert.strictEqual(day('2026-10-29').marks.some((x) => x.text === '回覆報價'), false);
  assert.ok(days.every((d) => d.marks.every((x) => x.text !== '施工')), '期間不進格子，畫成 bar');
  const week = m.weeks.find((w) => w.days.some((d) => d.date === '2026-10-25'));
  const bar = week.bars.find((b) => b.text === '施工');
  assert.deepStrictEqual([bar.col, bar.span, bar.continuesLeft, bar.continuesRight], [0, 7, false, true], '10/25 週日起、橫跨整週');
  assert.strictEqual(new Date(m.weeks[0].days[0].date + 'T00:00:00Z').getUTCDay(), 0);
  const next = lib.shiftMonth(2026, 11, 1);
  assert.deepStrictEqual(next, { year: 2027, month: 0 });
});

test('首頁畫出來：鼓勵句、時間軸列與 bar、待辦三組、要你確認的、小事那一行', () => {
  const plugin = { runner: {}, home: lib.normalizeHome(sample()), ui: lib.defaultUi(), loadedVersion: '0.28.0', homeError: null, needsReload: false, openEntity() {}, itemMenu() {}, entityMenu() {} };
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  const root = view.root;
  assert.match(byClass(root, 'wwh-cheer')[0].textContent, /今天也辛苦了/);
  // 三個事類實體（含「其他」）各一塊；預設收起，有逾期或今天那件的那塊（信義王）展開（裁定 28）
  assert.strictEqual(byClass(root, 'wwh-row').length, 3);
  assert.deepStrictEqual(byClass(root, 'wwh-row').map((b) => b.classList.contains('is-open')), [true, false, false]);
  assert.strictEqual(byClass(root, 'wwh-summary').length, 2, '收起來的兩塊各一列摘要');
  view.setAllRows(false); // 全部展開才看得到每件的記號
  // bar 與點
  const bars = byClass(root, 'is-bar').filter((e) => e.classList.contains('wwh-mark'));
  const points = byClass(root, 'is-point').filter((e) => e.classList.contains('wwh-mark'));
  assert.strictEqual(bars.length, 5, '施工、裝修、水電、木工、油漆');
  assert.ok(points.length >= 4);
  const late = byClass(root, 'is-late').filter((e) => e.classList.contains('wwh-mark'));
  assert.ok(late.length >= 2, '晚了的標橘');
  assert.ok(byClass(root, 'is-inferred').some((e) => e.classList.contains('wwh-mark')), '推測的虛線');
  assert.ok(byClass(root, 'wwh-pause').length === 1);
  assert.ok(byClass(root, 'wwh-baseline').length === 1);
  assert.ok(byClass(root, 'is-critical').length >= 2);
  assert.ok(byClass(root, 'wwh-links').length === 1, '連線畫在有 links 的那一列');
  // bar 的位置真的寫進 style
  const first = bars[0];
  assert.ok(first.styleMap.left.endsWith('%'));
  assert.ok(first.styleMap.width.endsWith('%'));
  // 待辦：三組，這週預設收起
  const heads = byClass(root, 'wwh-group-head').map((e) => e.textContent);
  assert.ok(heads.some((t) => t.includes('已經過了')));
  assert.ok(heads.some((t) => t.includes('今天')));
  assert.ok(heads.some((t) => t.includes('這週')));
  assert.strictEqual(byClass(root, 'wwh-todo').length, 2, '已經過了 1 件 + 今天 1 件；這週收起來不畫');
  // 要你確認的
  assert.strictEqual(byClass(root, 'wwh-confirm').length, 1);
  assert.strictEqual(byClass(root, 'wwh-confirm-buttons')[0].children.length, 1, '左邊只有點了就做的答案（裁定 39）');
  assert.strictEqual(byClass(root, 'wwh-others-line')[0].textContent, '還有 1 件要跟 Claude 一起看');
  // 最近：不整片列在頁面上，游標在搜尋框裡才出現（裁定 28）
  assert.strictEqual(byClass(root, 'wwh-recent-item').length, 0);
  plugin.ui.search.focused = true;
  view.render();
  assert.strictEqual(byClass(root, 'wwh-recent-item').length, 1);
});

test('首頁：時間軸切月曆、全部收起、這週展開', () => {
  const plugin = { runner: {}, home: lib.normalizeHome(sample()), ui: lib.defaultUi(), loadedVersion: '0.28.0', openEntity() {}, itemMenu() {}, entityMenu() {} };
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  view.setAllRows(true);
  assert.strictEqual(byClass(view.root, 'wwh-rows').length, 0);
  view.setAllRows(false);
  assert.strictEqual(byClass(view.root, 'wwh-rows').length, 3);
  view.setMode('month');
  assert.ok(byClass(view.root, 'wwh-month').length === 1);
  assert.ok(byClass(view.root, 'wwh-day').length >= 28);
  assert.match(byClass(view.root, 'wwh-month-title')[0].textContent, /2026 年 10 月/);
  plugin.ui.todoCollapsed.week = false;
  view.render();
  assert.strictEqual(byClass(view.root, 'wwh-todo').length, 3);
});

test('首頁：kb home 的 version 跟外掛版號不同，上方顯示一條提示，其餘照樣畫', () => {
  const raw = sample();
  raw.version = '0.29.0';
  const plugin = { runner: {}, home: lib.normalizeHome(raw), ui: lib.defaultUi(), loadedVersion: '0.28.0', openEntity() {}, itemMenu() {}, entityMenu() {} };
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  assert.ok(byClass(view.root, 'wwh-banner').some((e) => e.textContent === lib.VERSION_MISMATCH_TEXT));
  assert.strictEqual(byClass(view.root, 'wwh-row').length, 3);
  assert.strictEqual(lib.versionMismatch('0.28.0', '0.28.0'), false);
});

test('首頁：自己的檔換了，顯示「首頁更新了，按這裡重新載入」', () => {
  assert.strictEqual(lib.manifestChanged('0.28.0', '{"version":"0.29.0"}'), true);
  assert.strictEqual(lib.manifestChanged('0.28.0', '{"version":"0.28.0"}'), false);
  assert.strictEqual(lib.manifestChanged('0.28.0', 'broken'), false);
  let reloaded = 0;
  const plugin = { runner: {}, home: lib.normalizeHome(sample()), ui: lib.defaultUi(), loadedVersion: '0.28.0', needsReload: true, reloadSelf() { reloaded += 1; } };
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  const bar = byClass(view.root, 'wwh-banner-reload')[0];
  assert.strictEqual(bar.textContent, lib.RELOAD_TEXT);
  bar.fire('click');
  assert.strictEqual(reloaded, 1);
});

test('首頁：某一區出錯只有那一區顯示畫不出來，別區照畫', () => {
  const raw = sample();
  const plugin = { runner: {}, home: lib.normalizeHome(raw), ui: lib.defaultUi(), loadedVersion: '0.28.0' };
  plugin.home.confirm = null; // 弄壞「要你確認的」那一區
  const view = new lib.HomeView({}, plugin);
  view.build();
  const origError = console.error;
  console.error = () => {};
  try {
    view.render();
  } finally {
    console.error = origError;
  }
  assert.match(view.rightEl.textContent, /畫不出來/);
  assert.strictEqual(byClass(view.root, 'wwh-todo').length, 2);
  assert.strictEqual(byClass(view.root, 'wwh-row').length, 3);
});

function viewOf(raw, extra) {
  const plugin = Object.assign({ runner: {}, home: lib.normalizeHome(raw || sample()), ui: lib.defaultUi(), loadedVersion: '0.28.0', openEntity() {}, itemMenu() {}, entityMenu() {} }, extra);
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  return { view, plugin };
}

test('時間軸（裁定 28）：預設收起，只有有逾期或今天那件還沒做的那塊展開；使用者按過的照他按的', () => {
  const home = sample();
  const lay = lib.layoutTimeline(home.timeline, { today: home.today });
  assert.deepStrictEqual(lay.rows.map((r) => lib.rowDefaultCollapsed(r, lib.dayNumber(home.today))), [false, true, true]);
  // 今天到期、還沒做的那件也讓那塊展開
  home.timeline.rows[1].marks.push(mark({ id: 'a-today', shape: 'point', kind: 'deadline', start: null, end: '2026-10-30', text: '今天要交', children: [] }));
  const { view, plugin } = viewOf(home);
  assert.deepStrictEqual(byClass(view.root, 'wwh-row').map((b) => b.classList.contains('is-open')), [true, true, false]);
  plugin.ui.rowCollapsed['e-1a2b3c4d'] = true; // 她收起來的就收著
  view.render();
  assert.deepStrictEqual(byClass(view.root, 'wwh-row').map((b) => b.classList.contains('is-open')), [false, true, false]);
});

test('時間軸（裁定 28）：左欄一件一列（圖示、文字、日期），右邊同列只放記號；字不畫在圖上', () => {
  const { view } = viewOf();
  const row = byClass(view.root, 'wwh-row')[0];
  const lines = byClass(row, 'wwh-mark-line');
  assert.strictEqual(lines.length, 4, '信義王四件各一列');
  for (const line of lines) {
    const track = byClass(line, 'wwh-cell-track')[0];
    assert.strictEqual(track.textContent, '', '右邊只有記號、沒有字');
    assert.ok(byClass(line, 'wwh-mark-text')[0].textContent.length > 0);
  }
  const late = lines.find((l) => byClass(l, 'wwh-mark-text')[0].textContent === '回覆報價');
  assert.match(byClass(late, 'wwh-mark-when')[0].textContent, /^10\/28（週三） · 過了 2 天$/);
  const bar = lines.find((l) => byClass(l, 'wwh-mark-text')[0].textContent === '施工');
  assert.strictEqual(byClass(bar, 'wwh-mark-when')[0].textContent, '10/25～11/20');
  assert.ok(byClass(late, 'wwh-mark')[0].classList.contains('is-point'));
  assert.strictEqual(byTag(byClass(late, 'wwh-mark')[0], 'svg').length, 1, '點是帶種類圖示的小圓');
});

test('拿掉承諾（#68）：舊值 promise 畫到期的圖示；圖例沒有承諾；新增日程的種類只有四個', () => {
  const { view } = viewOf();
  const row = byClass(view.root, 'wwh-row')[0];
  const late = byClass(row, 'wwh-mark-line').find((l) => byClass(l, 'wwh-mark-text')[0].textContent === '回覆報價');
  const paths = (el) => byTag(el, 'path').map((p) => p.getAttribute('d'));
  const ico = byTag(byClass(late, 'wwh-kind-ico')[0], 'svg')[0];
  assert.deepStrictEqual(paths(ico), paths(lib.icon('deadline')));
  const legend = view.legend();
  assert.ok(!legend.textContent.includes('承諾'));
  assert.strictEqual(byClass(legend, 'wwh-legend-item').filter((x) => byTag(x, 'svg').length).length, 3, '會議、到期、提醒');
  let modal = null;
  const open = env.fake.Modal.prototype.open;
  env.fake.Modal.prototype.open = function () {
    modal = this;
    return open.call(this);
  };
  try {
    env.Plugin.prototype.addAgendaForm.call({ app: {}, home: { today: '2026-10-30' }, entityNames: () => [] });
  } finally {
    env.fake.Modal.prototype.open = open;
  }
  const select = byTag(modal.contentEl, 'select')[0];
  assert.deepStrictEqual(byTag(select, 'option').map((o) => o.textContent), ['到期', '會議', '提醒', '期間']);
});

test('時間軸（裁定 28）：收起來是摘要列，期間一條色條、每件一個點；推測的條不畫在摘要的色條裡', () => {
  const { view } = viewOf();
  const sums = byClass(view.root, 'wwh-summary');
  assert.strictEqual(sums.length, 2);
  const twoCollapsed = sums[0]; // 中山林：裝修（實心條）、油漆（實心條）
  assert.strictEqual(byClass(twoCollapsed, 'wwh-sum-bar').length, 2);
  const other = sums[1]; // 其他：只有繳費提醒一個點
  assert.strictEqual(byClass(other, 'wwh-sum-dot').length, 1);
  assert.ok(byClass(other, 'wwh-sum-dot')[0].styleMap.left.endsWith('%'));
});

test('時間軸（裁定 32）：軸頭上排月份、下排日期、畫週線；今天的旗子在日期那一排，附近的日期讓位', () => {
  const { view } = viewOf();
  const axis = byClass(view.root, 'wwh-axis')[0];
  const months = byClass(axis, 'is-month').filter((t) => !t.classList.contains('is-pinned')).map((t) => t.textContent);
  assert.deepStrictEqual(months, ['11月', '12月'], '每個月 1 號一個');
  const days = byClass(axis, 'is-day');
  assert.ok(days.length >= 8 && days.every((t) => /^\d{1,2}$/.test(t.textContent)), '下排是每週一個日期');
  const flagPct = parseFloat(byClass(axis, 'wwh-today-flag')[0].styleMap.left);
  assert.ok(days.every((t) => Math.abs(parseFloat(t.styleMap.left) - flagPct) > 6.4), '今天附近的日期讓位給旗子');
  assert.ok(byClass(axis, 'is-week').length >= 8, '每週一一條線');
  assert.strictEqual(byClass(axis, 'wwh-today-flag').length, 1);
  assert.ok(byClass(view.root, 'wwh-today-line').length >= 3, '每塊一條今天線');
});

test('時間軸（裁定 28）：「全部展開／全部收起」是同一顆，照現在的狀態換字', () => {
  const { view } = viewOf();
  const btn = () => byClass(view.timelineEl, 'wwh-text-btn')[0];
  assert.strictEqual(btn().textContent, '全部展開');
  btn().fire('click');
  assert.strictEqual(btn().textContent, '全部收起');
  assert.deepStrictEqual(byClass(view.root, 'wwh-row').map((b) => b.classList.contains('is-open')), [true, true, true]);
  btn().fire('click');
  assert.deepStrictEqual(byClass(view.root, 'wwh-row').map((b) => b.classList.contains('is-open')), [false, false, false]);
});

test('時間軸：子項縮排、連線與基準線在展開的那一塊裡畫（一件一列的座標）', () => {
  const { view } = viewOf();
  view.setAllRows(false);
  const row = byClass(view.root, 'wwh-row')[1];
  assert.strictEqual(byClass(row, 'wwh-mark-line').length, 4, '裝修、水電、木工、油漆');
  assert.strictEqual(byClass(row, 'is-child').length >= 2, true);
  assert.strictEqual(byClass(row, 'wwh-links').length, 1);
  assert.strictEqual(byClass(row, 'wwh-link-path').length, 2, '找不到一端的那條不畫');
  assert.strictEqual(byClass(row, 'wwh-baseline').length, 1);
});

// ---- 裁定 30（D-266）：首頁只放看與找，動作只留四個 ----

test('版面（裁定 32）：日期與問候 → 搜尋 → 日程 → 待辦｜要你確認的；最上面沒有數字', () => {
  const { view } = viewOf();
  const kids = Array.from(view.root.children);
  const order = [view.topRowEl, view.timelineEl, view.colsEl].map((e) => kids.indexOf(e));
  assert.ok(order.every((n) => n >= 0) && order.every((n, i) => i === 0 || n > order[i - 1]), order.join());
  assert.deepStrictEqual(Array.from(view.topLeftEl.children), [view.topEl, view.searchEl], '搜尋框在日期問候下面（裁定 40：左欄）');
  assert.strictEqual(byClass(view.topEl, 'wwh-count').length, 0, '數字全拿掉');
  assert.strictEqual(byClass(view.topEl, 'wwh-counts').length, 0);
  assert.strictEqual(byClass(view.topEl, 'wwh-cheer')[0].textContent, '今天也辛苦了', '一句話照 kb 給的畫');
  assert.strictEqual(byClass(view.timelineEl, 'wwh-section-head')[0].textContent.startsWith('日程'), true, '「手上的事」改叫「日程」');
});

test('份量（裁定 30）：沒有按鈕的框；收合是標題前的小箭頭，標題本身可點，不是 button', () => {
  const { view } = viewOf();
  assert.strictEqual(byClass(view.root, 'wwh-info-btn').length, 0, 'ⓘ 拿掉');
  assert.strictEqual(byClass(view.root, 'wwh-sq-btn').length, 0, '「⋯」拿掉');
  assert.strictEqual(byClass(view.root, 'wwh-card').length, 0, '卡片外框拿掉');
  const heads = byClass(view.colsEl, 'wwh-group-head').concat(byClass(view.root, 'wwh-fold'));
  assert.ok(heads.length >= 4);
  for (const hd of heads) {
    assert.notStrictEqual(hd.tagName.toLowerCase(), 'button');
    assert.strictEqual(byClass(hd, 'wwh-chev').length, 1, '標題前有小箭頭');
  }
  const toggles = byClass(view.timelineEl, 'wwh-text-btn').concat(byClass(view.timelineEl, 'wwh-seg'));
  assert.ok(toggles.every((t) => t.tagName.toLowerCase() !== 'button'), '「全部展開」與時間軸／月曆都不是按鈕');
});

test('待辦（裁定 30）：標題、案子·種類·推測一行淡小字、日期不加框；沒有「⋯」與「記成確認」', () => {
  const { view } = viewOf();
  view.plugin.ui.todoCollapsed.week = false;
  view.render();
  const rows = byClass(view.leftEl, 'wwh-todo');
  assert.strictEqual(rows.length, 3);
  const inferred = rows[2]; // 看工地：推測的、沒有案子
  assert.strictEqual(byClass(inferred, 'wwh-todo-text')[0].textContent, '看工地');
  assert.strictEqual(byClass(inferred, 'wwh-todo-meta')[0].textContent, '會議·推測');
  assert.strictEqual(byTag(inferred, 'button').length, 0, '沒有任何按鈕');
  const first = rows[0];
  assert.strictEqual(byClass(first, 'wwh-todo-meta')[0].textContent, '信義王·到期'); // 舊值 promise 照到期顯示（#68）
  assert.strictEqual(byClass(first, 'wwh-todo-when')[0].textContent, '10/28（週三）');
  assert.strictEqual(byTag(first, 'button').length, 0);
});

test('待辦（裁定 32、41）：「＋新增日程」在待辦標題旁；點日期改日期時間；點標題開相關的卡；點案子名開右邊總覽', () => {
  const calls = [];
  const { view } = viewOf(null, {
    addAgendaForm: () => calls.push('add'),
    editDateForm: (it) => calls.push('edit:' + it.id),
    openItem: (it) => calls.push('line:' + it.id),
    openEntity: (n) => calls.push('entity:' + n),
  });
  const add = byClass(view.leftEl, 'wwh-add-btn')[0];
  assert.strictEqual(add.textContent, '＋新增日程');
  add.fire('click');
  const row = byClass(view.leftEl, 'wwh-todo')[0];
  byClass(row, 'wwh-todo-when')[0].fire('click');
  byClass(row, 'wwh-todo-text')[0].fire('click');
  byClass(row, 'wwh-todo-entity')[0].fire('click', { stopPropagation() {} });
  assert.deepStrictEqual(calls, ['add', 'edit:a-late', 'line:a-late', 'entity:信義王']);
});

test('要你確認的（裁定 30）：答案是淡的文字選項，不是按鈕；點了照 argv 做', () => {
  const chosen = [];
  const { view } = viewOf(null, { chooseResult: (c, r) => chosen.push(r.label) });
  const answers = byClass(view.rightEl, 'wwh-answer');
  assert.deepStrictEqual(answers.map((a) => a.textContent), ['是，合併'], 'argv 是 null 的（只能在對話做的）不列');
  assert.ok(answers.every((a) => a.tagName.toLowerCase() !== 'button'));
  answers[0].fire('click');
  assert.deepStrictEqual(chosen, ['是，合併']);
});

test('時間軸（裁定 30）：做完的不畫；只有過期、今天的記號上色', () => {
  const raw = sample();
  raw.timeline.rows[0].marks.push(mark({ id: 'a-done', shape: 'point', kind: 'deadline', start: null, end: '2026-11-01', text: '已做完的事', status: 'done', children: [] }));
  raw.timeline.rows[0].marks.push(mark({ id: 'a-due', shape: 'point', kind: 'deadline', start: null, end: '2026-10-30', text: '今天到期的', children: [] }));
  const { view } = viewOf(raw);
  view.setAllRows(false);
  const names = byClass(view.timelineEl, 'wwh-mark-text').map((e) => e.textContent);
  assert.ok(!names.includes('已做完的事'), '做完的不畫');
  assert.ok(names.includes('今天到期的'));
  const line = (t) => byClass(view.timelineEl, 'wwh-mark-line').find((l) => byClass(l, 'wwh-mark-text')[0].textContent === t);
  assert.ok(line('今天到期的').classList.contains('is-today'));
  assert.ok(line('回覆報價').classList.contains('is-late'));
  assert.ok(!line('驗收會議').classList.contains('is-late') && !line('驗收會議').classList.contains('is-today'), '其他的不上色');
  const kept = lib.openMarksOnly(raw.timeline);
  assert.ok(kept.rows.every((r) => r.marks.every((m) => m.status === 'open')));
  assert.strictEqual(lib.openMarksOnly({ rows: [{ key: 'x', marks: [mark({ status: 'done' })] }] }).rows.length, 0, '整塊都做完了就不畫那一塊');
});

test('時間軸（裁定 41）：收合只靠名字前的小箭頭，名字本身開右邊總覽（「其他」那列不開）；點一件開相關的卡', () => {
  const calls = [];
  const { view, plugin } = viewOf(null, { openItem: (it) => calls.push('item:' + it.id), openEntity: (n) => calls.push('entity:' + n) });
  const rows = byClass(view.timelineEl, 'wwh-row');
  assert.deepStrictEqual(rows.map((r) => r.classList.contains('is-alt')), [false, true, false], '單雙數交替淡底');
  assert.strictEqual(byClass(view.timelineEl, 'wwh-row-link').length, 0);
  // 名字 → 總覽，不收合
  byClass(rows[0], 'wwh-row-name')[0].fire('click');
  assert.deepStrictEqual(calls, ['entity:信義王']);
  assert.ok(byClass(rows[0], 'wwh-row-name')[0].classList.contains('is-link'));
  assert.strictEqual(plugin.ui.rowCollapsed['e-1a2b3c4d'], undefined, '名字不收合');
  // 整條標題列、整個左欄的空白處也不收合
  byClass(rows[0], 'wwh-head-line')[0].fire('click');
  byClass(rows[0], 'wwh-fold')[0].fire('click');
  assert.strictEqual(plugin.ui.rowCollapsed['e-1a2b3c4d'], undefined);
  // 小箭頭收合
  const btn = byClass(rows[0], 'wwh-fold-btn')[0];
  assert.strictEqual(btn.attrs.role, 'button');
  assert.strictEqual(btn.attrs['aria-expanded'], 'true');
  assert.strictEqual(byClass(btn, 'wwh-chev').length, 1);
  btn.fire('click');
  assert.strictEqual(plugin.ui.rowCollapsed['e-1a2b3c4d'], true, '點小箭頭收合');
  plugin.ui.rowCollapsed['e-1a2b3c4d'] = false;
  view.render();
  // 「其他」那列：名字不開
  const other = byClass(view.timelineEl, 'wwh-row')[2];
  byClass(other, 'wwh-row-name')[0].fire('click');
  assert.deepStrictEqual(calls, ['entity:信義王'], '其他不開');
  assert.ok(!byClass(other, 'wwh-row-name')[0].classList.contains('is-link'));
  byClass(byClass(view.timelineEl, 'wwh-row')[0], 'wwh-mark-label')[0].fire('click');
  assert.match(calls[1], /^item:a-/, '開的是日程那一件');
});

test('點日程那件（裁定 32）：kb 給的 card 在就開那張卡；沒有才開日程.md 那一行', async () => {
  const opened = [];
  const lines = [];
  const app = { vault: { adapter: { getBasePath: () => '/v' } }, workspace: { openLinkText: async (l) => opened.push(l), getLeavesOfType: () => [] } };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.openAgendaLine = async (it) => lines.push(it.id);
  await plugin.openItem({ id: 'a-1', card: { path: '檔案索引/報價-1a2b3c4d.md', kind: 'origin' } });
  await plugin.openItem({ id: 'a-2', card: { path: '案子/信義王/信義王.md', kind: 'synthesis' } });
  await plugin.openItem({ id: 'a-3', card: null });
  await plugin.openItem({ id: 'a-4' });
  assert.deepStrictEqual(opened, ['檔案索引/報價-1a2b3c4d', '案子/信義王/信義王']);
  assert.deepStrictEqual(lines, ['a-3', 'a-4']);
});

test('月曆（裁定 30）：期間畫成橫跨那一週的一條 bar，每一週那段都寫名字，跨週接著畫；推測的淡色；做完的不畫', () => {
  const raw = sample();
  raw.timeline.rows = [
    {
      key: 'e-1', label: '信義王', type: '案子', progress: 'active', pauses: [], links: [],
      marks: [
        mark({ id: 'p1', start: '2026-10-05', end: '2026-10-16', text: '水電', children: [] }),
        mark({ id: 'p2', start: '2026-10-07', end: '2026-10-09', text: '放樣', inferred: true, children: [] }),
        mark({ id: 'p3', start: '2026-10-12', end: '2026-10-13', text: '做完的期間', status: 'done', children: [] }),
        mark({ id: 'p4', shape: 'bar', start: '2026-10-21', end: '2026-10-21', text: '單天', children: [] }),
        mark({ id: 'q1', shape: 'point', kind: 'deadline', start: null, end: '2026-10-20', text: '交圖', children: [] }),
      ],
    },
  ];
  const m = lib.layoutMonth(raw.timeline, { today: raw.today });
  const wk = (iso) => m.weeks.find((w) => w.days.some((d) => d.date === iso));
  const w1 = wk('2026-10-05'); // 10/4（日）起的一週
  const w2 = wk('2026-10-12');
  const pipe1 = w1.bars.find((b) => b.text === '水電');
  const pipe2 = w2.bars.find((b) => b.text === '水電');
  assert.deepStrictEqual([pipe1.col, pipe1.span, pipe1.continuesRight], [1, 6, true]);
  assert.deepStrictEqual([pipe2.col, pipe2.span, pipe2.continuesLeft], [0, 6, true], '下一週接著畫');
  assert.deepStrictEqual(w1.bars.map((b) => b.lane), [0, 1], '同一週重疊的 bar 疊在不同層');
  assert.ok(!m.weeks.some((w) => w.bars.some((b) => b.text === '做完的期間')), '做完的不畫');
  const cell = (iso) => m.weeks.flatMap((w) => w.days).find((d) => d.date === iso);
  assert.deepStrictEqual(cell('2026-10-21').marks.map((x) => x.text), ['單天'], '單天的才佔格子');
  assert.deepStrictEqual(cell('2026-10-20').marks.map((x) => x.text), ['交圖']);

  const { view } = viewOf(raw);
  view.setMode('month');
  const bars = byClass(view.timelineEl, 'wwh-mbar');
  assert.strictEqual(bars.length, 3, '水電兩週各一條、放樣一條');
  assert.deepStrictEqual(bars.map((b) => b.textContent), ['水電', '放樣', '水電'], '每一週那段都寫名字（裁定 31）');
  assert.ok(bars[1].classList.contains('is-inferred'), '推測的用淡色，不用虛線框');
  assert.strictEqual(bars[0].styleMap['grid-column'], '2 / span 6');
  assert.ok(bars[2].classList.contains('clip-left'));
  assert.strictEqual(byClass(view.timelineEl, 'wwh-day-mark').map((e) => e.textContent).sort().join(), '交圖,單天');
});

test('月曆（裁定 32）：點 bar 或單天的記號，開相關的卡', () => {
  const calls = [];
  const raw = sample();
  raw.timeline.rows = [{ key: 'e-1', label: '信義王', type: '案子', progress: 'active', pauses: [], links: [], marks: [mark({ id: 'p1', start: '2026-10-05', end: '2026-10-09', text: '水電', children: [] }), mark({ id: 'q1', shape: 'point', kind: 'deadline', start: null, end: '2026-10-20', text: '交圖', children: [] })] }];
  const { view } = viewOf(raw, { openItem: (it) => calls.push(it.id) });
  view.setMode('month');
  byClass(view.timelineEl, 'wwh-mbar')[0].fire('click');
  byClass(view.timelineEl, 'wwh-day-mark')[0].fire('click');
  assert.deepStrictEqual(calls, ['p1', 'q1']);
});

test('要你確認的（裁定 32）：一題一張卡', () => {
  const raw = sample();
  raw.confirm.push({ key: 'k2', text: '第二題', results: [{ label: '好', argv: null }] });
  const { view } = viewOf(raw);
  const cards = byClass(view.rightEl, 'wwh-confirm');
  assert.strictEqual(cards.length, 2);
  assert.ok(cards.every((c) => c.classList.contains('wwh-paper')), '白底淡陰影的卡');
});

// ---- 裁定 34：每個答案點了都有反應；待辦白卡；版面寬度；時間軸縮放與左右捲動 ----

const fs = require('node:fs');
const path = require('node:path');
const CSS = fs.readFileSync(path.join(__dirname, '..', '..', 'obsidian', 'styles.css'), 'utf8');

function confirmHome(results) {
  const raw = sample();
  raw.confirm = [{ key: 'q1', text: '12/3 王先生簽約過了，完成了嗎？', results }];
  return raw;
}

test('要你確認的（裁定 39）：左邊是答案（點了就做；要填的字後面有「…」）；右邊淡淡的「先放著」；首頁沒有「不處理」；argv 是 null 的不列', () => {
  const chosen = [];
  const raw = confirmHome([
    { label: '用新版', argv: ['agenda', 'edit', 'a-1', '--date', '2026-12-01'], fill: null },
    { label: '改到某天…', argv: ['agenda', 'edit', 'a-1', '--date', '{新日期}'], fill: { name: '新日期', rule: 'YYYY-MM-DD', input: 'date' } },
    { label: '改成別的名字', argv: ['entity', 'rename', 'X', '--to', '{新名字}'], fill: { name: '新名字', rule: 'x', input: 'text' } },
    { label: '照你改的做', argv: null, fill: null },
    { label: '先放著', argv: ['asks', 'set-aside', 'q1'], fill: null },
  ]);
  const { view } = viewOf(raw, { chooseResult: (c, r) => chosen.push(r.label) });
  const card = byClass(view.rightEl, 'wwh-confirm')[0];
  assert.deepStrictEqual(byClass(card, 'wwh-answer').map((a) => a.textContent), ['用新版', '改到某天…', '改成別的名字…'], '要填的字後面有「…」（kb 的字已經有就不再加），argv 是 null 的不列');
  assert.strictEqual(byClass(card, 'wwh-answer-chat').length, 0, '一個個答案旁沒有對話圖示');
  const quiet = byClass(card, 'wwh-confirm-quiet')[0];
  assert.strictEqual(byClass(quiet, 'is-aside')[0].textContent, '先放著');
  assert.strictEqual(byClass(quiet, 'is-dismiss').length, 0, '首頁沒有「不處理」');
  assert.ok(Array.from(quiet.children).indexOf(byClass(quiet, 'wwh-chat-btn')[0]) === quiet.children.length - 1, '對話圖示放最後');
  byClass(card, 'wwh-answer')[0].fire('click');
  byClass(quiet, 'is-aside')[0].fire('click');
  assert.deepStrictEqual(chosen, ['用新版', '先放著'], '不用填的點了照 argv 跑；要填的點了先展開，不直接跑');
  // 告知的：kb 給「知道了」（pending dismiss），算一般答案、沒有先放著
  const info = confirmHome([{ label: '知道了', argv: ['pending', 'dismiss', 'p-9'], fill: null }]);
  const c2 = byClass(viewOf(info).view.rightEl, 'wwh-confirm')[0];
  assert.deepStrictEqual(byClass(c2, 'wwh-answer').map((a) => a.textContent), ['知道了']);
  assert.strictEqual(byClass(c2, 'is-aside').length + byClass(c2, 'is-dismiss').length, 0);
  // 沒有先放著的題：圖示每張卡都有
  const none = confirmHome([{ label: '好', argv: ['x'], fill: null }]);
  const q3 = byClass(viewOf(none).view.rightEl, 'wwh-confirm-quiet')[0];
  assert.deepStrictEqual(Array.from(q3.children).map((e) => e.classList.contains('wwh-chat-btn')), [true]);
});

test('要你確認的（裁定 39）：splitAnswers 照 argv 認、不照字；pending dismiss 是一般答案；只取第一個先放著', () => {
  const r = (label, argv, fill) => ({ label, argv, fill: fill || null });
  const out = lib.splitAnswers({ results: [r('A', ['agenda', 'done', 'x']), r('先放著', ['asks', 'set-aside', 'k']), r('先放著', ['pending', 'set-aside', 'p']), r('B', ['agenda', 'edit', 'x', '--date', '{d}'], { name: 'd' }), r('C', null), r('知道了', ['pending', 'dismiss', 'p'])] });
  assert.deepStrictEqual(out.main.map((x) => x.label), ['A', 'B', '知道了']);
  assert.deepStrictEqual(out.aside.argv, ['asks', 'set-aside', 'k']);
  assert.deepStrictEqual(lib.splitAnswers(null), { main: [], aside: null });
  assert.deepStrictEqual(lib.splitAnswers({ results: [r('先放著', null)] }).aside, null, '字叫先放著、argv 是 null 的不算');
});

function fillHome() {
  return confirmHome([
    { label: '改到某天…', argv: ['agenda', 'edit', 'a-1', '--date', '{新日期}'], fill: { name: '新日期', rule: 'YYYY-MM-DD', input: 'date' } },
    { label: '改名…', argv: ['entity', 'rename', '王先生', '--to', '{新名字}'], fill: { name: '新名字', rule: 'x', input: 'text' }, after: ['entity', 'confirm', '{新名字}'] },
    {
      label: '放到…', argv: ['source-edit', 'move', '收件匣/a.pdf', '--to', '{放到}'],
      fill: { name: '放到', rule: 'x', input: 'select', options: [{ label: '客戶案件/王', value: '客戶案件/王', group: '常放' }, { label: '案子/李', value: '案子/李', group: '全部' }, { label: '案子/陳', value: '案子/陳', group: '全部' }] },
    },
  ]);
}

test('要你確認的（裁定 39）：要填的在卡上展開——日期用日期選擇、名字用文字框、選單用下拉；Enter 或選好就跑；一次只開一格', () => {
  const chosen = [];
  const { view, plugin } = viewOf(fillHome(), { chooseResult: (c, r, v) => chosen.push([r.label, v]) });
  const answers = () => byClass(view.rightEl, 'wwh-answer');
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill').length, 0, '沒點之前不展開');
  // 日期
  answers()[0].fire('click');
  assert.deepStrictEqual(plugin.ui.confirmFill, { key: 'q1', n: 0 });
  assert.ok(answers()[0].classList.contains('is-on'));
  let input = byClass(view.rightEl, 'wwh-fill-input')[0];
  assert.strictEqual(input.attrs.type, 'date');
  input.value = '明天';
  input.fire('change');
  input.fire('keydown', { key: 'Enter' });
  assert.deepStrictEqual(chosen, [], '不是 YYYY-MM-DD 不送');
  input.value = '2026-12-05';
  input.fire('change');
  input.fire('change'); // 同一格不送兩次
  assert.deepStrictEqual(chosen, [['改到某天…', '2026-12-05']]);
  assert.strictEqual(plugin.ui.confirmFill, null, '送出就收起');
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill').length, 0);
  // 名字：Enter 才送；注音選字中、空的不送；Esc 收起
  answers()[1].fire('click');
  input = byClass(view.rightEl, 'wwh-fill-input')[0];
  assert.strictEqual(input.attrs.type, 'text');
  assert.strictEqual(input.attrs.placeholder, '新名字');
  input.value = '王大明';
  input.fire('keydown', { key: 'a' });
  input.fire('keydown', { key: 'Enter', isComposing: true });
  input.fire('compositionstart');
  input.fire('keydown', { key: 'Enter' });
  input.fire('compositionend');
  input.value = '   ';
  input.fire('keydown', { key: 'Enter' });
  assert.strictEqual(chosen.length, 1, '打字中、選字中、空的都不送');
  input.value = '王大明';
  input.fire('keydown', { key: 'Enter' });
  assert.deepStrictEqual(chosen[1], ['改名…', '王大明']);
  answers()[1].fire('click');
  byClass(view.rightEl, 'wwh-fill-input')[0].fire('keydown', { key: 'Escape' });
  assert.strictEqual(plugin.ui.confirmFill, null, 'Esc 收起');
  // 點同一個答案再點一次收起；點別的換成別的格
  answers()[1].fire('click');
  answers()[1].fire('click');
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill').length, 0);
  answers()[0].fire('click');
  answers()[2].fire('click');
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill').length, 1, '一次只開一格');
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill-select').length, 1);
});

test('要你確認的（裁定 39）：下拉的內容——「選一個…」、候選的在前、分隔線、全部的在後；選好就跑，選「選一個…」不跑', () => {
  const chosen = [];
  const { view } = viewOf(fillHome(), { chooseResult: (c, r, v) => chosen.push([r.label, v]) });
  byClass(view.rightEl, 'wwh-answer')[2].fire('click');
  const sel = byClass(view.rightEl, 'wwh-fill-select')[0];
  assert.strictEqual(sel.tagName, 'SELECT');
  assert.ok(sel.classList.contains('dropdown'), 'Obsidian 的下拉樣子');
  const opts = byTag(sel, 'option');
  assert.deepStrictEqual(opts.map((o) => o.textContent), ['選一個…', '客戶案件/王', '──────', '案子/李', '案子/陳']);
  assert.strictEqual(opts[2].attrs.disabled, 'disabled', '分隔線不能選');
  assert.strictEqual(opts[1].attrs.value, '客戶案件/王');
  sel.value = '';
  sel.fire('change');
  assert.deepStrictEqual(chosen, []);
  sel.value = '案子/李';
  sel.fire('change');
  assert.deepStrictEqual(chosen, [['放到…', '案子/李']]);
  // kb 沒給 input 時看選項與規則
  assert.strictEqual(lib.fillKind({ options: [{ value: 'a' }] }), 'select');
  assert.strictEqual(lib.fillKind({ rule: 'YYYY-MM-DD' }), 'date');
  assert.strictEqual(lib.fillKind({ rule: '一句話' }), 'text');
  assert.strictEqual(lib.fillKind(null), null);
});

test('要你確認的（裁定 39）：填的值換進 argv 與接著要跑的 after；after 在第一個指令成功後才跑，失敗不跑', async () => {
  const a = lib.actions.result({ label: '改名…', argv: ['entity', 'rename', 'X', '--to', '{新名字}'], fill: { name: '新名字' }, after: ['entity', 'confirm', '{新名字}'] }, '王大明');
  assert.deepStrictEqual(a.args, ['entity', 'rename', 'X', '--to', '王大明']);
  assert.deepStrictEqual(a.then, ['entity', 'confirm', '王大明']);
  const calls = [];
  const toasts = [];
  const ctx = { kb: async (args) => { calls.push(args); return { code: 0, stdout: '好了\n', stderr: '' }; }, toast: (t) => toasts.push(t), refresh() {} };
  assert.deepStrictEqual((await lib.performAction(ctx, a)).ok, true);
  assert.deepStrictEqual(calls, [a.args, a.then]);
  const fail = { kb: async (args) => (args[1] === 'rename' ? { code: 3, stdout: '改不了\n', stderr: '' } : { code: 0, stdout: '', stderr: '' }), toast: (t) => toasts.push(t) };
  const seen = [];
  const ctx2 = { kb: async (args) => { seen.push(args[1]); return fail.kb(args); }, toast: (t) => toasts.push(t) };
  assert.strictEqual((await lib.performAction(ctx2, a)).ok, false);
  assert.deepStrictEqual(seen, ['rename'], '第一個沒成功就不跑 after');
  assert.strictEqual(lib.actions.result({ label: '好', argv: null }), null);
  assert.strictEqual(lib.answerLabel({ label: '改名…', fill: { name: 'x' } }), '改名…');
  assert.strictEqual(lib.answerLabel({ label: '改名', fill: { name: 'x' } }), '改名…');
  assert.strictEqual(lib.answerLabel({ label: '對', fill: null }), '對');
  assert.strictEqual(lib.cleanFill({ input: 'text' }, '  王 '), '王');
  assert.strictEqual(lib.cleanFill({ input: 'text' }, ''), null);
  assert.strictEqual(lib.cleanFill({ input: 'date' }, '2026-1-5'), null);
});

test('要你確認的（裁定 37）：對話圖示——message-circle、滑過提示「跟 Claude 說」，點了複製「關於「題目」：」', () => {
  const copied = [];
  const raw = confirmHome([{ label: '好', argv: ['x'], fill: null }]);
  const { view } = viewOf(raw, { copyAsk: (c) => copied.push(c.text) });
  const btn = byClass(view.rightEl, 'wwh-chat-btn')[0];
  assert.strictEqual(btn.attrs.title, '跟 Claude 說');
  assert.strictEqual(byTag(btn, 'svg').length, 1);
  btn.fire('click');
  assert.deepStrictEqual(copied, ['12/3 王先生簽約過了，完成了嗎？']);
  assert.strictEqual(lib.chatPhrase({ text: ' 這題？ ' }), '關於「這題？」：');
  assert.strictEqual(lib.chatPhrase({}), '關於這題：');
});

test('最下面一行（裁定 41）：移到右欄「要你確認的」卡片正下方（在「還有 N 題」下面），收起時照樣顯示；N = 移到這邊的題數加小事；0 不寫；點了複製「幫我看一下待處理」', () => {
  const copied = [];
  const raw = sample();
  raw.confirm = [1, 2, 3, 4, 5].map((n) => ({ key: `k${n}`, text: `第 ${n} 題`, results: [{ label: '好', argv: ['x'], fill: null }] }));
  raw.claude = [{ key: 'x1', kind: 'draft', text: '草稿還在等' }, { key: 'x2', kind: 'batch', text: '要整理 30 份' }];
  raw.others = [{ id: 'p-1', text: '有一份檔不見了' }];
  const { view, plugin } = viewOf(raw, { copyReview: () => copied.push('x') });
  assert.strictEqual(byClass(view.root, 'wwh-block-others').length + byClass(view.root, 'wwh-other').length, 0, '舊的區塊沒了');
  assert.ok(!Array.from(view.root.children).includes(view.claudeEl), '不在兩欄下面了');
  const kids = Array.from(view.rightEl.children);
  const sure = byClass(view.rightEl, 'wwh-block-confirm')[0];
  assert.ok(kids.indexOf(view.claudeEl) === kids.indexOf(sure) + 1, '右欄、要你確認的卡片正下方');
  assert.ok(byClass(sure, 'wwh-confirm-more').length === 1, '「還有 N 題」在上面');
  const line = byClass(view.claudeEl, 'wwh-others-line')[0];
  assert.strictEqual(line.textContent, '還有 3 件要跟 Claude 一起看');
  const btn = byClass(line, 'wwh-chat-btn')[0];
  assert.strictEqual(btn.attrs.title, '跟 Claude 說');
  btn.fire('click');
  assert.deepStrictEqual(copied, ['x']);
  // 收起時照樣顯示
  byClass(view.rightEl, 'is-confirm')[0].fire('click');
  assert.strictEqual(plugin.ui.confirmCollapsed, true);
  assert.strictEqual(byClass(view.rightEl, 'wwh-confirm').length, 0);
  assert.strictEqual(byClass(view.rightEl, 'wwh-others-line')[0].textContent, '還有 3 件要跟 Claude 一起看');
  // 0 件不寫
  raw.claude = [];
  raw.others = [];
  assert.strictEqual(byClass(viewOf(raw).view.rightEl, 'wwh-others-line').length, 0, '0 件不寫');
  assert.strictEqual(lib.REVIEW_PHRASE, '幫我看一下待處理');
});

test('案子名稱開總覽（裁定 41）：月曆點日期小框裡的案子名開右邊總覽，「其他」那列的不開；點事情本身照舊開卡', () => {
  const calls = [];
  const raw = monthRaw();
  raw.timeline.rows.push({ key: '_other', label: '其他', type: null, progress: null, pauses: [], links: [], marks: [mark({ id: 'o1', shape: 'point', kind: 'reminder', start: null, end: '2026-10-20', text: '繳費', children: [] })] });
  const { view } = viewOf(raw, { openEntity: (n) => calls.push('entity:' + n), openItem: (it) => calls.push('item:' + it.id) });
  view.setMode('month');
  const dayEl = byClass(view.timelineEl, 'wwh-day').find((d) => !d.classList.contains('is-out') && byClass(d, 'wwh-day-num')[0].textContent === '20');
  dayEl.fire('click');
  const names = byClass(view.pop, 'wwh-pop-row-name');
  const mine = names.find((n) => n.textContent === '信義王');
  assert.ok(mine.classList.contains('is-link'));
  mine.fire('click');
  assert.deepStrictEqual(calls, ['entity:信義王']);
  assert.strictEqual(view.pop, null, '開總覽就關小框');
  dayEl.fire('click');
  const other = byClass(view.pop, 'wwh-pop-row-name').find((n) => n.textContent === '其他');
  assert.ok(!other.classList.contains('is-link'));
  other.fire('click');
  assert.deepStrictEqual(calls, ['entity:信義王'], '其他不開');
  byClass(view.pop, 'wwh-pop-row')[0].fire('click');
  assert.match(calls[1], /^item:/, '點事情本身開卡');
});

test('案子名稱開總覽（裁定 41）：openEntity 開右邊抽屜；同一個名字已經在最上面不重疊', () => {
  const { plugin } = viewOf();
  const real = lib.HomeView; // 只確認 plugin 的行為，不叫 kb
  assert.ok(real);
  const calls = [];
  const fake = { ui: lib.defaultUi(), loadDrawer: (x) => calls.push(x) };
  env.Plugin.prototype.openEntity.call(fake, '信義王');
  env.Plugin.prototype.openEntity.call(fake, '信義王');
  assert.strictEqual(fake.ui.drawer.open, true);
  assert.deepStrictEqual(fake.ui.drawer.stack, ['信義王']);
  env.Plugin.prototype.openEntity.call(fake, '中山林');
  assert.deepStrictEqual(fake.ui.drawer.stack, ['信義王', '中山林']);
  assert.ok(plugin);
});

test('要你確認的（裁定 37）：整區可以收合（標題前小箭頭，收起時標題旁寫題數）；先顯示 3 題，其餘「還有 N 題」點了展開', () => {
  const raw = sample();
  raw.confirm = [1, 2, 3, 4, 5].map((n) => ({ key: `k${n}`, text: `第 ${n} 題`, results: [{ label: '好', argv: ['x'], fill: null }] }));
  const { view, plugin } = viewOf(raw);
  const head = () => byClass(view.rightEl, 'is-confirm')[0];
  assert.deepStrictEqual(byClass(view.rightEl, 'wwh-confirm-text').map((e) => e.textContent), ['第 1 題', '第 2 題', '第 3 題']);
  assert.strictEqual(byClass(view.rightEl, 'wwh-confirm-more')[0].textContent, '還有 2 題');
  assert.strictEqual(byClass(head(), 'wwh-chev').length, 1, '標題前小箭頭');
  assert.strictEqual(head().attrs['aria-expanded'], 'true');
  assert.strictEqual(byClass(head(), 'wwh-group-count').length, 0, '展開時不寫題數');
  byClass(view.rightEl, 'wwh-confirm-more')[0].fire('click');
  assert.strictEqual(byClass(view.rightEl, 'wwh-confirm').length, 5);
  assert.strictEqual(byClass(view.rightEl, 'wwh-confirm-more').length, 0);
  head().fire('click');
  assert.strictEqual(plugin.ui.confirmCollapsed, true);
  assert.strictEqual(byClass(view.rightEl, 'wwh-confirm').length, 0, '收起來不畫卡');
  assert.strictEqual(head().attrs['aria-expanded'], 'false');
  assert.strictEqual(byClass(head(), 'wwh-group-count')[0].textContent, '5', '收起時標題旁淡淡寫題數');
  head().fire('click');
  assert.strictEqual(byClass(view.rightEl, 'wwh-confirm').length, 5, '再點展開（已點過「還有」的維持全部）');
  // 三題以內沒有「還有」
  const small = viewOf(confirmHome([{ label: '好', argv: ['x'], fill: null }])).view;
  assert.strictEqual(byClass(small.rightEl, 'wwh-confirm-more').length, 0);
  // 沒有要確認的：標題還在，寫「沒有」
  const empty = viewOf(Object.assign(sample(), { confirm: [] })).view;
  assert.strictEqual(byClass(empty.rightEl, 'wwh-empty')[0].textContent, '沒有');
});

test('版面（裁定 34）：待辦整區也是白卡；版面放寬到 1600px；答案間距約 20px；兩欄空隙縮小', () => {
  const { view } = viewOf();
  assert.ok(view.leftEl.classList.contains('wwh-paper'), '待辦整區白卡淡陰影');
  assert.match(CSS, /\.wwh-root > \* \{[^}]*max-width: 1600px/);
  assert.match(CSS, /\.wwh-confirm-buttons \{[^}]*gap: 8px 20px/);
  assert.match(CSS, /\.wwh-cols \{[^}]*gap: 28px 20px/);
});

// ---- 時間軸縮放與左右捲動 ----

test('時間軸（裁定 34）：日期刻度跟著縮放——兩週內每天，其他每週一；點的字寬跟著畫面', () => {
  const tl = { from: '2026-10-23', to: '2026-12-31', rows: [] };
  const w = lib.layoutTimeline(tl, { today: '2026-10-30', visibleDays: 90 });
  const d = lib.layoutTimeline(tl, { today: '2026-10-30', visibleDays: 14 });
  assert.ok(w.ticks.every((t) => t.kind !== 'day') && w.ticks.some((t) => t.kind === 'week'));
  assert.strictEqual(d.ticks.filter((t) => t.kind === 'day').length, 70, '每天一格（1 號也有日期，月份另標）');
  assert.strictEqual(d.ticks.filter((t) => t.kind === 'week').length, 0);
  assert.strictEqual(w.visibleDays, 90);
  assert.ok(Math.abs(w.slidePct - (70 / 90) * 100) < 1e-9);
  assert.ok(Math.abs(d.slidePct - (70 / 14) * 100) < 1e-9);
  assert.strictEqual(lib.layoutTimeline(tl, { today: '2026-10-30' }).visibleDays, 70, '沒給就是整段');
});

test('時間軸（裁定 34）：起點、夾住、要不要多載', () => {
  const n = (s) => lib.dayNumber(s);
  assert.strictEqual(lib.defaultTimelineStart(n('2026-10-30'), 90), n('2026-10-30') - 9);
  assert.strictEqual(lib.defaultTimelineStart(n('2026-10-30'), 14), n('2026-10-30') - 1);
  const from = n('2026-10-23');
  const to = n('2026-12-31');
  assert.strictEqual(lib.clampTimelineStart(from - 50, 30, from, to), from);
  assert.strictEqual(lib.clampTimelineStart(to + 50, 30, from, to), to + 1 - 30);
  assert.strictEqual(lib.clampTimelineStart(from + 3, 200, from, to), from, '範圍比畫面窄就貼著起點');
  const today = n('2026-10-30');
  assert.strictEqual(lib.wantedTimelineRange(from + 20, 30, from, to, today, true), null, '離兩邊都夠遠');
  const right = lib.wantedTimelineRange(to - 40, 30, from, to, today, true);
  assert.deepStrictEqual(right, { from: '2026-10-23', to: lib.dayToIso(to - 40 + 60) });
  const left = lib.wantedTimelineRange(from + 5, 30, from, to, today, true);
  assert.deepStrictEqual(left, { from: lib.dayToIso(from + 5 - 30), to: '2026-12-31' });
  assert.strictEqual(lib.wantedTimelineRange(from, 30, from, to, today, false), null, '沒捲過不看左邊');
  assert.strictEqual(lib.wantedTimelineRange(today + 725, 30, from, today + 730, today, true), null, '載到上限就不再載');
  assert.strictEqual(lib.initialTimelineRange(30, '2026-10-30'), null);
  assert.deepStrictEqual(lib.initialTimelineRange(90, '2026-10-30'), { from: '2026-10-23', to: lib.dayToIso(n('2026-10-30') + 135) });
  assert.deepStrictEqual(lib.homeArgs(['f-1'], { from: '2026-10-23', to: '2027-03-01' }), ['home', '--json', '--opened', 'f-1', '--from', '2026-10-23', '--to', '2027-03-01']);
  assert.deepStrictEqual(lib.homeArgs([], null), ['home', '--json']);
});

test('時間軸（裁定 34）：滾輪橫著捲只認觸控板左右或 Shift＋滾輪，直著滾交給頁面', () => {
  assert.strictEqual(lib.horizontalWheel({ deltaX: 40, deltaY: 3 }), 40);
  assert.strictEqual(lib.horizontalWheel({ deltaX: 0, deltaY: 60, shiftKey: true }), 60);
  assert.strictEqual(lib.horizontalWheel({ deltaX: 0, deltaY: 60 }), 0);
  assert.strictEqual(lib.horizontalWheel({ deltaX: 2, deltaY: 60 }), 0);
  assert.strictEqual(lib.horizontalWheel({ deltaX: 0, deltaY: 3, shiftKey: true, deltaMode: 1 }), 48);
});

test('時間軸（裁定 34）：軸、每塊的記號與背景層都放在一層會平移的 slide 裡；左欄不動', () => {
  const { view } = viewOf();
  view.setAllRows(false);
  const slides = byClass(view.timelineEl, 'wwh-slide');
  assert.ok(slides.length >= 1 + 3 + 9, '軸一個、每塊的背景層與每件的記號各一個');
  const w = (70 / 90) * 100;
  assert.ok(slides.every((s) => Math.abs(parseFloat(s.styleMap.width) - w) < 1e-6), '寬度是整段除以畫面看的天數');
  for (const left of byClass(view.timelineEl, 'wwh-cell-left')) assert.strictEqual(byClass(left, 'wwh-slide').length, 0, '左欄不在 slide 裡');
  const gantt = byClass(view.timelineEl, 'wwh-gantt')[0];
  assert.strictEqual(Math.abs(parseFloat(gantt.styleMap['--wwh-tx'])), 0, '預設起點是起日，沒平移');
});

test('時間軸（裁定 34）：Shift＋滾輪、觸控板左右都會捲，軸與每一塊一起平移（只改一個變數，不重畫），夾在已載入的範圍內', () => {
  const { view, plugin } = viewOf(null, { ui: Object.assign(lib.defaultUi(), { timelineDays: 30 }) }); // 載到的 70 天比畫面看的長才捲得動
  const gantt = byClass(view.timelineEl, 'wwh-gantt')[0];
  const before = view.timelineEl.children.length;
  let prevented = 0;
  gantt.fire('wheel', { deltaX: 0, deltaY: 100, shiftKey: true, preventDefault: () => prevented++ });
  assert.strictEqual(prevented, 1);
  assert.ok(typeof plugin.ui.tlStart === 'number');
  const tx = parseFloat(gantt.styleMap['--wwh-tx']);
  assert.ok(tx < 0, '往右捲，軸往左平移');
  gantt.fire('wheel', { deltaX: 100, deltaY: 0, preventDefault: () => prevented++ });
  assert.ok(parseFloat(gantt.styleMap['--wwh-tx']) < tx);
  assert.strictEqual(view.timelineEl.children.length, before, '沒重畫');
  gantt.fire('wheel', { deltaX: 0, deltaY: 100, preventDefault: () => prevented++ });
  assert.strictEqual(prevented, 2, '直著滾不攔');
  gantt.fire('wheel', { deltaX: -99999, deltaY: 0, preventDefault() {} });
  assert.strictEqual(plugin.ui.tlStart, lib.dayNumber('2026-10-23'), '往左捲回去不超過起日');
  gantt.fire('wheel', { deltaX: 99999, deltaY: 0, preventDefault() {} });
  assert.strictEqual(plugin.ui.tlStart, lib.dayNumber('2026-12-31') + 1 - 30, '往右捲到底，最後一天剛好貼右邊');
});

test('時間軸（裁定 34）：按住拖背景捲；拖在記號或左欄上不算；拖完那下 click 吃掉', () => {
  const { view, plugin } = viewOf(null, { ui: Object.assign(lib.defaultUi(), { timelineDays: 30 }) });
  view.setAllRows(false);
  const gantt = byClass(view.timelineEl, 'wwh-gantt')[0];
  const left = byClass(view.timelineEl, 'wwh-cell-left')[0];
  const mark = byClass(view.timelineEl, 'wwh-mark')[0];
  gantt.fire('mousedown', { target: mark, clientX: 500, button: 0 });
  view.contentEl.fire('mousemove', { clientX: 300 });
  assert.strictEqual(plugin.ui.tlStart, null, '記號上不拖');
  gantt.fire('mousedown', { target: left, clientX: 500, button: 0 });
  view.contentEl.fire('mousemove', { clientX: 300 });
  assert.strictEqual(plugin.ui.tlStart, null, '左欄上不拖');
  const bg = byClass(view.timelineEl, 'wwh-cell-track')[0];
  gantt.fire('mousedown', { target: bg, clientX: 500, button: 0 });
  view.contentEl.fire('mousemove', { clientX: 498 });
  assert.strictEqual(plugin.ui.tlStart, null, '動不到 4px 不算拖');
  view.contentEl.fire('mousemove', { clientX: 350 });
  const s1 = plugin.ui.tlStart;
  assert.ok(typeof s1 === 'number' && s1 > lib.dayNumber('2026-10-23'), '往左拖 = 往後看');
  assert.ok(gantt.classList.contains('is-dragging'));
  view.contentEl.fire('mouseup');
  assert.ok(!gantt.classList.contains('is-dragging'));
  let stopped = 0;
  gantt.fire('click', { stopPropagation: () => stopped++ });
  assert.strictEqual(stopped, 1, '拖完那下 click 被吃掉');
  gantt.fire('click', { stopPropagation: () => stopped++ });
  assert.strictEqual(stopped, 1, '只吃一下');
  view.contentEl.fire('mousemove', { clientX: 100 });
  assert.strictEqual(plugin.ui.tlStart, s1, '放開後再動不捲');
});

test('時間軸（裁定 37）：一次看 14～365 天，預設三個月；壞值退回預設；data.json 只收 14～365 的整數', () => {
  assert.strictEqual(lib.DEFAULT_ZOOM, 90);
  assert.deepStrictEqual([lib.MIN_ZOOM, lib.MAX_ZOOM], [14, 365]);
  assert.strictEqual(lib.zoomOf(30), 30);
  assert.strictEqual(lib.zoomOf('180'), 180);
  assert.strictEqual(lib.zoomOf(61.5), 61.5, '縮放途中可以是小數');
  assert.strictEqual(lib.zoomOf(7), 14, '太小夾到兩週');
  assert.strictEqual(lib.zoomOf(900), 365, '太大夾到一年');
  assert.strictEqual(lib.zoomOf(undefined), 90);
  assert.strictEqual(lib.zoomOf('x'), 90);
  assert.strictEqual(lib.defaultUi().timelineDays, 90);
  assert.strictEqual(lib.savedZoom(30), 30);
  assert.strictEqual(lib.savedZoom(14), 14);
  assert.strictEqual(lib.savedZoom(365), 365);
  for (const bad of [13, 366, 30.5, '30', null, undefined, NaN]) assert.strictEqual(lib.savedZoom(bad), null, String(bad));
});

test('時間軸（裁定 37）：Ctrl＋滾輪的縮放量——往上滾拉近（天數少）、往下滾拉遠；以游標那天為中心', () => {
  assert.ok(lib.wheelZoomFactor({ deltaY: -100 }) < 1);
  assert.ok(lib.wheelZoomFactor({ deltaY: 100 }) > 1);
  assert.strictEqual(lib.wheelZoomFactor({ deltaY: 0 }), 1);
  assert.ok(Math.abs(lib.wheelZoomFactor({ deltaY: -2 }) - 1) < 0.01, '觸控板拉近拉遠一下的量小，乘得也小');
  assert.ok(lib.wheelZoomFactor({ deltaY: -3, deltaMode: 1 }) < lib.wheelZoomFactor({ deltaY: -3 }), '以行為單位的滾輪折成像素');
  assert.strictEqual(lib.wheelZoomFactor({ deltaY: 99999 }), lib.wheelZoomFactor({ deltaY: 400 }), '一下最多這麼多');
  const z = lib.zoomAround(1000, 90, 0.25, 0.5);
  assert.strictEqual(z.visible, 45);
  assert.strictEqual(z.start + 0.25 * z.visible, 1000 + 0.25 * 90, '游標底下還是同一天');
  assert.strictEqual(lib.zoomAround(1000, 20, 0.5, 0.1).visible, 14, '夾在 14');
  assert.strictEqual(lib.zoomAround(1000, 300, 0.5, 9).visible, 365, '夾在 365');
  assert.strictEqual(lib.zoomAround(1000, 90, -5, 0.5).start, 1000 - 0 * 45 + 0, '游標在時間格外也不跑掉（夾到 0）');
});

test('時間軸（裁定 37）：游標在時間軸上 Ctrl＋滾輪連續縮放、攔下預設（不讓整頁放大）、停手後存進 data.json；不帶 Ctrl 不攔', () => {
  const { mock } = test;
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const saved = [];
    const { view, plugin } = viewOf(null, { ui: Object.assign(lib.defaultUi(), { timelineDays: 30, tlStart: lib.dayNumber('2026-11-10') }), saveTimelineDays: (d) => saved.push(d) });
    const wheel = (extra) => {
      view.axisTrackEl.getBoundingClientRect = () => ({ left: 100, width: 800 });
      let prevented = 0;
      byClass(view.timelineEl, 'wwh-gantt')[0].fire('wheel', Object.assign({ clientX: 500, preventDefault: () => prevented++ }, extra));
      return prevented;
    };
    const center = () => plugin.ui.tlStart + 0.5 * plugin.ui.timelineDays;
    const day = center();
    assert.strictEqual(day, lib.dayNumber('2026-11-10') + 15);
    assert.strictEqual(wheel({ ctrlKey: true, deltaY: -100 }), 1, '攔下，Obsidian 不會整頁放大');
    assert.ok(plugin.ui.timelineDays < 30 && plugin.ui.timelineDays > 14, '往上滾拉近：天數變少，是連續的小數');
    assert.ok(Math.abs(center() - day) < 1e-9, '游標在正中間，中間那天不動');
    // 游標偏左四分之一：那天也不動
    const left = plugin.ui.tlStart + 0.25 * plugin.ui.timelineDays;
    assert.strictEqual(wheel({ ctrlKey: true, deltaY: 60, clientX: 300 }), 1);
    assert.ok(Math.abs(plugin.ui.tlStart + 0.25 * plugin.ui.timelineDays - left) < 1e-9, '以游標那天為中心');
    assert.ok(plugin.ui.timelineDays > 14);
    // 範圍：拉到底停在 14，拉遠到頂停在 365
    for (let i = 0; i < 40; i++) wheel({ ctrlKey: true, deltaY: -400 });
    assert.strictEqual(plugin.ui.timelineDays, 14);
    for (let i = 0; i < 40; i++) wheel({ ctrlKey: true, deltaY: 400 });
    assert.strictEqual(plugin.ui.timelineDays, 365);
    // 軸跟著重畫：看 365 天，寬度 = 整段 ÷ 365
    const slide = byClass(view.timelineEl, 'wwh-slide')[0];
    assert.ok(Math.abs(parseFloat(slide.styleMap.width) - (70 / 365) * 100) < 1e-6);
    // 不帶 Ctrl：直著滾不攔，天數不變
    const before = plugin.ui.timelineDays;
    assert.strictEqual(wheel({ deltaY: -100 }), 0, '不帶 Ctrl 的直著滾照常上下捲');
    assert.strictEqual(plugin.ui.timelineDays, before);
    // 停手 0.4 秒才存，一次，存整數
    assert.deepStrictEqual(saved, []);
    mock.timers.tick(399);
    assert.deepStrictEqual(saved, []);
    mock.timers.tick(1);
    assert.deepStrictEqual(saved, [365]);
    wheel({ ctrlKey: true, deltaY: -100 });
    mock.timers.tick(400);
    assert.strictEqual(saved.length, 2);
    assert.ok(Number.isInteger(saved[1]) && saved[1] >= 14 && saved[1] <= 365);
  } finally {
    mock.timers.reset();
  }
});

test('時間軸（裁定 34）：兩週的軸每天一格；釘在左邊的月份跟著捲動換', () => {
  const { view, plugin } = viewOf(null, { ui: Object.assign(lib.defaultUi(), { timelineDays: 14 }) });
  const axis = byClass(view.timelineEl, 'wwh-axis')[0];
  assert.ok(byClass(axis, 'is-day').length >= 60, '每天一個日期（今天旁邊那幾個讓位給旗子）');
  const pinned = byClass(axis, 'is-pinned')[0];
  plugin.ui.tlStart = lib.dayNumber('2026-11-12');
  view.applyScroll();
  assert.strictEqual(pinned.textContent, '2026/11月');
  assert.ok(!pinned.classList.contains('wwh-hidden'));
  plugin.ui.tlStart = lib.dayNumber('2026-11-01');
  view.applyScroll();
  assert.ok(pinned.classList.contains('wwh-hidden'), '剛好 1 號，月份就在軸上，不用釘');
  assert.deepStrictEqual(lib.pinnedMonth(lib.dayNumber('2026-11-30'), 14), { label: '2026/11月', hide: true }, '下個月 1 號就在左邊不遠，讓給它');
});

test('時間軸（裁定 34）：捲到快出範圍就跟 kb 要一段，記下範圍；同一段要過就不再要', async () => {
  const asked = [];
  const app = { vault: { adapter: { getBasePath: () => '/v' } }, workspace: { getLeavesOfType: () => [] } };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.ui = lib.defaultUi();
  plugin.home = lib.normalizeHome(sample());
  plugin.data = lib.sanitizeData(null);
  plugin.runner = {
    run: async (args) => {
      asked.push(args);
      return { code: 0, stdout: JSON.stringify(sample()), stderr: '' };
    },
  };
  plugin.renderAll = () => {};
  plugin.checkSelfUpdate = () => {};
  const t = (s) => lib.dayNumber(s);
  assert.strictEqual(plugin.ensureTimelineRange(t('2026-11-10'), 30, true), false, '離邊夠遠不要');
  assert.strictEqual(plugin.ensureTimelineRange(t('2026-12-20'), 30, true), true);
  await new Promise((r) => setImmediate(r));
  assert.deepStrictEqual(asked[0].slice(asked[0].indexOf('--from')), ['--from', '2026-10-23', '--to', lib.dayToIso(t('2026-12-20') + 60)]);
  assert.strictEqual(plugin.ensureTimelineRange(t('2026-12-20'), 30, true), false, '同一段要過了不再要（回來的範圍沒變也不會一直要）');
  assert.deepStrictEqual(plugin.ui.tlRange, { from: '2026-10-23', to: lib.dayToIso(t('2026-12-20') + 60) });
  await plugin.refresh();
  assert.ok(asked[asked.length - 1].includes('--to'), '之後每次重新整理都帶著這個範圍');
});

test('時間軸（裁定 37）：縮放的天數記在 data.json（14～365 的整數），開起來讀回；壞的照預設；其他欄位不被洗掉', async () => {
  assert.strictEqual(lib.sanitizeData({ opened: [], timelineDays: 30 }).timelineDays, 30);
  assert.strictEqual(lib.sanitizeData({ opened: [], timelineDays: 200 }).timelineDays, 200, '14～365 之間任何整數');
  for (const bad of [7, 400, 30.5, '30']) assert.strictEqual(lib.sanitizeData({ opened: [], timelineDays: bad }).timelineDays, undefined, String(bad));
  assert.strictEqual(lib.zoomOf(lib.sanitizeData({ opened: [], timelineDays: 200 }).timelineDays), 200, '開起來讀回');
  assert.strictEqual(lib.zoomOf(lib.sanitizeData({ opened: [], timelineDays: 7 }).timelineDays), 90, '壞的照預設');
  assert.deepStrictEqual(Object.keys(lib.sanitizeData({ opened: [], extra: 1 })), ['opened']);
  const kept = lib.recordOpened({ opened: [], timelineDays: 180 }, 'f-1a2b3c4d', '2026-10-30T10:00:00');
  assert.strictEqual(kept.timelineDays, 180, '記開過的卡不洗掉縮放');
  const saves = [];
  const app = { vault: { adapter: { getBasePath: () => '/v' } }, workspace: { getLeavesOfType: () => [] } };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.data = lib.sanitizeData({ opened: [{ card: 'f-1a2b3c4d', at: 't' }] });
  plugin.saveData = async (d) => saves.push(d);
  await plugin.saveTimelineDays(30);
  assert.deepStrictEqual(saves[0], { opened: [{ card: 'f-1a2b3c4d', at: 't' }], timelineDays: 30 });
  await plugin.saveTimelineDays(150.4);
  assert.strictEqual(saves[1].timelineDays, 150, '連續縮放的小數存整數');
  await plugin.saveTimelineDays(5);
  assert.strictEqual(saves[2].timelineDays, 14, '太小夾到 14');
});

// ---- 裁定 37：顏色（時間軸每一列一個淡色、月曆同色）、月曆時間字 ----

function colorHome() {
  const raw = sample();
  raw.timeline.from = '2026-10-01'; // 十月的事都在時間軸範圍裡
  raw.timeline.rows = [
    {
      key: 'e-1', label: '信義王', type: '案子', progress: 'active', pauses: [], links: [],
      marks: [
        mark({ id: 'p1', start: '2026-10-05', end: '2026-10-16', text: '水電', entities: ['信義王'], children: [] }),
        mark({ id: 'q1', shape: 'point', kind: 'deadline', start: null, end: '2026-10-20', text: '交圖', entities: ['信義王'], children: [] }),
        mark({ id: 'q2', shape: 'point', kind: 'deadline', start: null, end: '2026-10-27', text: '回報價', late: true, entities: ['信義王'], children: [] }),
      ],
    },
    {
      key: 'e-2', label: '中山林', type: '案子', progress: 'active', pauses: [], links: [],
      marks: [mark({ id: 'p2', start: '2026-10-06', end: '2026-10-08', text: '裝修', entities: ['中山林'], children: [] })],
    },
    {
      key: '_other', label: '其他', type: null, progress: null, pauses: [], links: [],
      marks: [
        mark({ id: 'o1', shape: 'point', kind: 'reminder', start: null, end: '2026-10-21', text: '寄發票', entities: ['王先生'], children: [] }),
        mark({ id: 'o2', shape: 'point', kind: 'reminder', start: null, end: '2026-10-22', text: '回電', entities: ['李小姐', '王先生'], children: [] }),
        mark({ id: 'o3', shape: 'point', kind: 'reminder', start: null, end: '2026-10-23', text: '送樣品', entities: ['王先生'], children: [] }),
        mark({ id: 'o4', shape: 'point', kind: 'reminder', start: null, end: '2026-10-24', text: '什麼都沒掛', entities: [], children: [] }),
      ],
    },
  ];
  return raw;
}

test('顏色（裁定 37）：時間軸每一列一個淡色，照列的順序；「其他」那列照 entities 第一個上色，同一個實體同色，沒掛的是 null', () => {
  const raw = colorHome();
  const c = lib.timelineColors(lib.openMarksOnly(raw.timeline));
  assert.strictEqual(c.row('e-1'), 0);
  assert.strictEqual(c.row('e-2'), 1);
  assert.strictEqual(c.row('_other'), null, '「其他」那列自己沒有顏色');
  const other = raw.timeline.rows[2].marks;
  assert.deepStrictEqual(other.map((m) => c.of('_other', m)), [2, 3, 2, null], '王先生 2、李小姐 3（第一個實體）、同一個實體同色、沒掛的淡灰');
  assert.strictEqual(c.of('e-1', raw.timeline.rows[0].marks[0]), 0, '案子那列的事都是那列的顏色，不看實體');
  assert.strictEqual(lib.toneCls(3), 'wwh-tone3');
  assert.strictEqual(lib.toneCls(null), '');
  // 超過 8 列輪流用
  const many = { rows: Array.from({ length: 10 }, (_, i) => ({ key: `r${i}`, label: `列${i}`, marks: [mark({ id: `m${i}` })] })) };
  const cm = lib.timelineColors(many);
  assert.strictEqual(cm.row('r8'), 0);
  assert.strictEqual(cm.row('r9'), 1);
  // 做完的事整列沒了，後面的列順序往前補（時間軸與月曆都先過 openMarksOnly，所以兩邊一致）
  raw.timeline.rows[0].marks.forEach((m) => { m.status = 'done'; });
  assert.strictEqual(lib.timelineColors(lib.openMarksOnly(raw.timeline)).row('e-2'), 0);
});

test('顏色（裁定 37）：時間軸的條、點、收起的摘要與列標題的色點都帶那一列的顏色；過期的橘色照舊壓過', () => {
  const { view } = viewOf(colorHome());
  view.setAllRows(false);
  const rows = byClass(view.timelineEl, 'wwh-row');
  const tone = (el) => (el.className.match(/wwh-tone([0-7])/) || [])[1] || null;
  assert.strictEqual(tone(byClass(rows[0], 'wwh-row-dot')[0]), '0', '列標題前的色點');
  assert.strictEqual(tone(byClass(rows[1], 'wwh-row-dot')[0]), '1');
  assert.strictEqual(byClass(rows[2], 'wwh-row-dot').length, 0, '其他那列沒有色點');
  const marks0 = byClass(rows[0], 'wwh-mark');
  assert.ok(marks0.length >= 3 && marks0.every((m) => tone(m) === '0'), '同列的條與點同色');
  assert.ok(marks0.some((m) => m.classList.contains('is-late')), '過期的仍標 is-late（CSS 讓橘色壓過顏色）');
  assert.deepStrictEqual(byClass(rows[2], 'wwh-mark').map(tone), ['2', '3', '2', null], '其他那列的點照實體第一個上色，沒掛的沒顏色');
  assert.ok(byClass(rows[1], 'wwh-mark').every((m) => tone(m) === '1'));
  // 收起來的摘要
  view.setAllRows(true);
  const sum = byClass(byClass(view.timelineEl, 'wwh-row')[0], 'wwh-summary')[0];
  assert.ok(byClass(sum, 'wwh-sum-bar').concat(byClass(sum, 'wwh-sum-dot')).every((e) => tone(e) === '0'));
});

test('顏色（裁定 37）：月曆用同一個對照——期間的條和單天的事都有顏色，同一列同色，時間軸和月曆同色；過期的自己的顏色加橘色字與外框', () => {
  const raw = colorHome();
  const m = lib.layoutMonth(raw.timeline, { today: raw.today });
  const bars = m.weeks.flatMap((w) => w.bars);
  const cells = m.weeks.flatMap((w) => w.days).flatMap((d) => d.marks);
  assert.ok(bars.filter((b) => b.text === '水電').length === 2 && bars.filter((b) => b.text === '水電').every((b) => b.color === 0));
  assert.strictEqual(bars.find((b) => b.text === '裝修').color, 1);
  const by = (t) => cells.find((x) => x.text === t);
  assert.deepStrictEqual(['交圖', '回報價', '寄發票', '回電', '送樣品', '什麼都沒掛'].map((t) => by(t).color), [0, 0, 2, 3, 2, null]);
  assert.ok(by('回報價').late && by('回報價').color === 0, '過期的也有自己的顏色');
  // 時間軸與月曆同一件事同一個顏色
  const c = lib.timelineColors(lib.openMarksOnly(raw.timeline));
  assert.strictEqual(by('回電').color, c.of('_other', raw.timeline.rows[2].marks[1]));
  // 畫出來
  const { view } = viewOf(raw);
  view.setMode('month');
  const tags = byClass(view.timelineEl, 'wwh-day-mark');
  const tag = (t) => tags.find((e) => e.textContent === t);
  assert.ok(tag('交圖').classList.contains('wwh-tone0') && tag('寄發票').classList.contains('wwh-tone2') && tag('回電').classList.contains('wwh-tone3'));
  assert.ok(!/wwh-tone/.test(tag('什麼都沒掛').className), '什麼都沒掛的用淡灰');
  assert.ok(tag('回報價').classList.contains('wwh-tone0') && tag('回報價').classList.contains('is-late'));
  assert.ok(byClass(view.timelineEl, 'wwh-mbar').filter((b) => b.textContent === '裝修').every((b) => b.classList.contains('wwh-tone1')));
  // CSS：每個顏色一組、過期是橘色字加外框、沒顏色有淡灰底
  for (let n = 0; n < 8; n++) assert.match(CSS, new RegExp(`\\.wwh-tone${n} \\{[^}]*--wwh-mark-c: var\\(--wwh-mt${n}\\)[^}]*--wwh-mark-bg: var\\(--wwh-mc${n}\\)`));
  assert.match(CSS, /\.wwh-day-mark \{[^}]*background: var\(--wwh-mark-bg, var\(--wwh-bar\)\)/);
  assert.match(CSS, /\.wwh-day-mark\.is-late \{[^}]*box-shadow: inset 0 0 0 1\.5px var\(--wwh-orange\)[^}]*color: var\(--wwh-orange\)/);
  assert.match(CSS, /\.wwh-mbar\.is-late \{[^}]*box-shadow: inset 0 0 0 1\.5px var\(--wwh-orange\)[^}]*color: var\(--wwh-orange\)/);
  assert.match(CSS, /\.theme-dark \.wwh-root \{[^}]*--wwh-mt0: rgba/, '深色主題另調');
});

test('月曆（裁定 37）：有時間的寫「14:00 丈量」（時間在前），沒時間的只寫事情；提示與開的卡照舊', () => {
  const raw = sample();
  raw.timeline.rows = [
    {
      key: 'e-1', label: '信義王', type: '案子', progress: 'active', pauses: [], links: [],
      marks: [
        mark({ id: 'q1', shape: 'point', kind: 'meeting', start: null, end: '2026-10-20', time: '14:00', text: '丈量', children: [] }),
        mark({ id: 'q2', shape: 'point', kind: 'deadline', start: null, end: '2026-10-21', text: '交圖', children: [] }),
        mark({ id: 'p1', start: '2026-10-12', end: '2026-10-14', time: '09:30', text: '放樣', children: [] }),
      ],
    },
  ];
  const m = lib.layoutMonth(raw.timeline, { today: raw.today });
  const cells = m.weeks.flatMap((w) => w.days).flatMap((d) => d.marks);
  assert.strictEqual(cells.find((x) => x.text === '丈量').label, '14:00 丈量');
  assert.strictEqual(cells.find((x) => x.text === '交圖').label, '交圖');
  assert.strictEqual(m.weeks.flatMap((w) => w.bars).find((b) => b.text === '放樣').label, '09:30 放樣');
  const { view } = viewOf(raw);
  view.setMode('month');
  const tags = byClass(view.timelineEl, 'wwh-day-mark');
  assert.deepStrictEqual(tags.map((e) => e.textContent).sort(), ['14:00 丈量', '交圖']);
  assert.strictEqual(tags.find((e) => e.textContent === '14:00 丈量').attrs.title, '信義王：丈量', '提示還是原本的字');
  assert.strictEqual(byClass(view.timelineEl, 'wwh-mbar')[0].textContent, '09:30 放樣');
});

// ---- 裁定 37：隨手記改成便條紙（D-267 修訂） ----

function makeNotePlugin(files, dirs) {
  const store = Object.assign({}, files);
  const folders = new Set(dirs || []);
  const writes = [];
  const made = [];
  const toasts = [];
  const adapter = {
    getBasePath: () => '/v',
    exists: async (p) => Object.prototype.hasOwnProperty.call(store, p) || folders.has(p),
    read: async (p) => store[p],
    write: async (p, t) => {
      if (adapter.failWrite) throw new Error('disk full');
      writes.push([p, t]);
      store[p] = t;
    },
    mkdir: async (p) => {
      made.push(p);
      folders.add(p);
    },
  };
  const app = { vault: { adapter }, workspace: { getLeavesOfType: () => [] } };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.ui = lib.defaultUi();
  plugin.vaultPath = '/v';
  plugin.data = lib.sanitizeData(null);
  plugin.home = lib.normalizeHome(sample());
  plugin.toast = (t) => toasts.push(t);
  plugin.scheduleRefresh = () => {};
  return { plugin, adapter, store, writes, made, toasts };
}

const tickNote = () => new Promise((r) => setImmediate(r));

test('便條（裁定 37）：重讀到的那一頁要不要換進便條——她正在打字（框有焦點、或還有沒存的字）就不蓋', () => {
  const note = lib.defaultNote();
  assert.deepStrictEqual(note, { text: '', saved: null, dirty: false, focused: false });
  assert.strictEqual(lib.noteIncoming(note, null), null, '沒有那一頁、便條也空的：不動');
  assert.strictEqual(lib.noteIncoming(note, '新的字'), '新的字');
  note.text = '新的字';
  assert.strictEqual(lib.noteIncoming(note, '新的字'), null, '一樣就不動');
  assert.strictEqual(lib.noteIncoming(note, '別處改過'), '別處改過');
  assert.strictEqual(lib.noteIncoming(note, null), '', '那一頁被刪了，便條就空白');
  note.focused = true;
  assert.strictEqual(lib.noteIncoming(note, '別處改過'), null, '正在打字不蓋');
  note.focused = false;
  note.dirty = true;
  assert.strictEqual(lib.noteIncoming(note, '別處改過'), null, '還有沒存的字不蓋');
  assert.strictEqual(lib.noteIncoming(null, 'x'), null);
  assert.strictEqual(lib.NOTE_REL, '系統/隨手記.md', '便條存在 系統/（#51 拿掉 _個人）');
  assert.strictEqual(lib.FREE_DIR, undefined);
  assert.strictEqual(lib.NOTE_DELAY_MS, 1500);
});

test('便條（裁定 37）：重畫不洗掉她打到一半的字、框還是同一個；沒在打字時換成讀到的新內容', () => {
  const { view, plugin } = viewOf();
  const box = byClass(view.noteEl, 'wwh-note-text')[0];
  box.value = '打到一半';
  plugin.ui.note.focused = true;
  plugin.ui.note.text = '打到一半';
  view.render();
  assert.strictEqual(byClass(view.noteEl, 'wwh-note-text')[0], box, '同一個框，游標不掉');
  assert.strictEqual(box.value, '打到一半');
  plugin.ui.note.focused = false;
  plugin.ui.note.text = '別處改過的新內容';
  view.render();
  assert.strictEqual(box.value, '別處改過的新內容');
});

test('便條（裁定 37）：框的 input、focus、blur 交給 plugin', () => {
  const log = [];
  const { view } = viewOf(null, { noteEdited: (t) => log.push(['edit', t]), noteFocus: (on) => log.push(['focus', on]) });
  const box = byClass(view.noteEl, 'wwh-note-text')[0];
  box.fire('focus');
  box.value = '一行';
  box.fire('input');
  box.fire('blur');
  assert.deepStrictEqual(log, [['focus', true], ['edit', '一行'], ['focus', false]]);
});

test('便條（裁定 37）：打開首頁時讀那一頁（沒有就空白）；重讀時她正在打字就不蓋；別處改了下次重畫讀到新的', async () => {
  const { plugin, store } = makeNotePlugin({ [lib.NOTE_REL]: '# 隨手記\n\n- 舊的\n' });
  await plugin.readNote();
  assert.strictEqual(plugin.ui.note.text, '# 隨手記\n\n- 舊的\n');
  assert.strictEqual(plugin.ui.note.saved, '# 隨手記\n\n- 舊的\n');
  store[lib.NOTE_REL] = '別處改的';
  await plugin.readNote();
  assert.strictEqual(plugin.ui.note.text, '別處改的', '沒在打字就換成新的');
  plugin.noteFocus(true);
  plugin.noteEdited('別處改的，我又打了幾個字');
  store[lib.NOTE_REL] = '又被別處改了';
  await plugin.readNote();
  assert.strictEqual(plugin.ui.note.text, '別處改的，我又打了幾個字', '正在打字不蓋');
  assert.strictEqual(plugin.ui.note.saved, '又被別處改了', '磁碟上的字照實記著');
  const empty = makeNotePlugin({});
  await empty.plugin.readNote();
  assert.strictEqual(empty.plugin.ui.note.text, '', '沒有那一頁就是空白');
  assert.strictEqual(empty.plugin.ui.note.saved, null);
  assert.strictEqual(empty.writes.length, 0, '讀不會建檔');
});

test('便條（裁定 37）：停手約 1.5 秒存回那一頁（連打只存最後一次），離開框立刻存；沒有就建（夾也沒有就建）；不加時間戳', async () => {
  const { mock } = test;
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const { plugin, writes, made } = makeNotePlugin({});
    plugin.noteFocus(true);
    plugin.noteEdited('第');
    mock.timers.tick(1000);
    plugin.noteEdited('第一行');
    mock.timers.tick(1499);
    await tickNote();
    assert.deepStrictEqual(writes, [], '沒滿 1.5 秒不存');
    mock.timers.tick(1);
    await tickNote();
    assert.deepStrictEqual(made, ['系統'], '系統夾沒有就先建');
    assert.deepStrictEqual(writes, [[lib.NOTE_REL, '第一行']], '一次、最後的字、原樣（沒有時間戳、沒有檔頭）');
    assert.strictEqual(plugin.ui.note.dirty, false);
    assert.strictEqual(plugin.ui.note.saved, '第一行');
    // 離開框立刻存，不等
    plugin.noteEdited('第一行\n第二行');
    plugin.noteFocus(false);
    await tickNote();
    assert.deepStrictEqual(writes[1], [lib.NOTE_REL, '第一行\n第二行']);
    mock.timers.tick(5000);
    await tickNote();
    assert.strictEqual(writes.length, 2, '排的計時被收掉，不重複存');
    assert.strictEqual(plugin.ui.note.focused, false);
  } finally {
    mock.timers.reset();
  }
});

test('便條（裁定 37）：沒變就不存；打了又改回原樣不存；全刪了存空檔、不刪檔', async () => {
  const { mock } = test;
  mock.timers.enable({ apis: ['setTimeout'] });
  try {
    const { plugin, writes, store, made } = makeNotePlugin({ [lib.NOTE_REL]: '舊的\n' }, ['系統']);
    await plugin.readNote();
    plugin.noteEdited('舊的\n');
    plugin.noteEdited('舊的\n加一行');
    plugin.noteEdited('舊的\n');
    mock.timers.tick(2000);
    await tickNote();
    await plugin.flushNote();
    assert.deepStrictEqual(writes, [], '改回原樣就不用存');
    plugin.noteEdited('');
    mock.timers.tick(1500);
    await tickNote();
    assert.deepStrictEqual(writes, [[lib.NOTE_REL, '']], '空的就存空檔');
    assert.strictEqual(store[lib.NOTE_REL], '', '檔還在，只是空的');
    assert.deepStrictEqual(made, [], '夾已經有就不建');
    // 本來就沒有那一頁，她也沒打字：不建空檔
    const none = makeNotePlugin({});
    none.plugin.noteEdited('');
    none.plugin.noteFocus(false);
    await tickNote();
    assert.deepStrictEqual(none.writes, []);
  } finally {
    mock.timers.reset();
  }
});

test('便條（裁定 37）：存不成就提示、字留著還沒存，之後再存；存的時候她又打了字不會被當成存好', async () => {
  const { plugin, adapter, writes, toasts } = makeNotePlugin({}, ['系統']);
  const origError = console.error;
  console.error = () => {};
  try {
    adapter.failWrite = true;
    plugin.noteEdited('寫不進去');
    assert.strictEqual(await plugin.flushNote(), false);
    assert.deepStrictEqual(toasts, ['隨手記沒存成']);
    assert.strictEqual(plugin.ui.note.dirty, true);
    assert.strictEqual(plugin.ui.note.text, '寫不進去', '字還在');
  } finally {
    console.error = origError;
  }
  adapter.failWrite = false;
  const slow = new Promise((resolve) => setImmediate(resolve));
  const orig = adapter.write;
  adapter.write = async (p, t) => {
    await slow;
    plugin.ui.note.text = t + '又打了';
    return orig(p, t);
  };
  await plugin.flushNote();
  assert.deepStrictEqual(writes[0], [lib.NOTE_REL, '寫不進去']);
  assert.strictEqual(plugin.ui.note.dirty, true, '存的時候又打了字，還沒完');
});

test('便條（裁定 37）：離開首頁（view 關掉）與外掛卸載都先存', async () => {
  let flushed = 0;
  const { view } = viewOf(null, { flushNote: () => { flushed += 1; } });
  await view.onClose();
  assert.strictEqual(flushed, 1);
  const { plugin, writes } = makeNotePlugin({}, ['系統']);
  plugin.noteEdited('卸載前的字');
  plugin.onunload();
  await tickNote();
  assert.deepStrictEqual(writes, [[lib.NOTE_REL, '卸載前的字']]);
});

test('便條（裁定 37）：kb jot 拿掉了——外掛沒有 jot 動作，也不叫 kb 存便條', () => {
  assert.strictEqual(lib.actions.jot, undefined);
  assert.ok(!/'jot'/.test(fs.readFileSync(path.join(__dirname, '..', '..', 'obsidian', 'main.js'), 'utf8')));
});

test('便條（裁定 39）：移到右上角、跟日期問候同一排；標題「隨手記」可點，開那一頁；滑鼠移入、打字時照樣淡黃', () => {
  const opened = [];
  const flushed = [];
  const { view } = viewOf(null, { openPathInVault: (r) => opened.push(r), flushNote: () => flushed.push(1) });
  assert.deepStrictEqual(Array.from(view.topRowEl.children), [view.topLeftEl, view.noteEl], '左欄（日期、問候、搜尋框）、右欄便條');
  assert.deepStrictEqual(Array.from(view.topLeftEl.children), [view.topEl, view.searchEl]);
  const kids = Array.from(view.root.children);
  assert.ok(kids.indexOf(view.topRowEl) >= 0 && kids.indexOf(view.noteEl) < 0, '便條不再單獨放在最底下');
  assert.ok(kids.indexOf(view.searchEl) < 0, '搜尋框進了左欄');
  assert.match(CSS, /\.wwh-search \{[^}]*max-width: 720px/, '搜尋框寬照舊、不跟著便條撐開');
  const box = byClass(view.noteEl, 'wwh-note-text')[0];
  assert.strictEqual(box.tagName, 'TEXTAREA');
  assert.strictEqual(box.attrs.rows, '5', '四五行高');
  const title = byClass(view.noteEl, 'wwh-note-title')[0];
  assert.strictEqual(title.textContent, '隨手記');
  title.fire('click');
  assert.deepStrictEqual(opened, ['系統/隨手記.md']);
  assert.strictEqual(flushed.length, 1, '開頁前先把打到一半的存下來');
  assert.match(CSS, /\.wwh-note \{[^}]*width: 240px/, '約 240px 寬');
  assert.match(CSS, /\.wwh-note \.wwh-note-text:hover,[^{]*\.wwh-note-text:focus,[^{]*\{[^}]*background: transparent/, 'hover、focus 不變白（蓋掉 Obsidian 的底色）');
  assert.match(CSS, /\.wwh-note \.wwh-note-text[^{]*\{[^}]*overflow-y: auto/, '內容多就在框裡捲');
  assert.match(CSS, /\.wwh-toprow \{[^}]*align-items: flex-start/, '日期與便條上緣對齊（裁定 40）');
  assert.ok(!/\.wwh-toprow \.wwh-top \{[^}]*align-self: flex-end/.test(CSS), '日期不再貼下緣被便條往下推');
  assert.match(CSS, /\.wwh-note \.wwh-note-text[^{]*\{[^}]*height: 8em/, '剛好 5 行，不切半行');
  assert.match(CSS, /\.wwh-note-text::-webkit-scrollbar \{[^}]*width: 6px/, '字多時看得出可以捲');
  assert.match(CSS, /--wwh-note-bg: #fff6c9/);
  assert.match(CSS, /\.theme-dark \.wwh-root \{[^}]*--wwh-note-bg: #3f3b24/, '深色主題調暗');
  const hidden = viewOf(null, { runner: null }).view;
  assert.ok(hidden.topRowEl.classList.contains('wwh-hidden'), '沒找到 kb 時跟其他區一起藏起來');
});

test('時間軸（裁定 39）：「Ctrl＋滾輪縮放」那行字拿掉（功能照留）；縮放的四段按鈕也沒有；回到今天把捲動歸零', () => {
  const { view, plugin } = viewOf();
  assert.strictEqual(byClass(view.timelineEl, 'wwh-zoom-hint').length, 0);
  assert.ok(!view.timelineEl.textContent.includes('Ctrl＋滾輪縮放'));
  assert.strictEqual(byClass(view.timelineEl, 'wwh-zoom').length, 0);
  assert.ok(!/wwh-zoom-hint/.test(CSS), '樣式也拿掉了');
  plugin.ui.tlStart = lib.dayNumber('2026-11-10');
  byClass(view.timelineEl, 'wwh-today-btn')[0].fire('click');
  assert.strictEqual(plugin.ui.tlStart, null);
  const gantt = byClass(view.timelineEl, 'wwh-gantt')[0];
  assert.ok(parseFloat(gantt.styleMap['--wwh-tx']) <= 0);
  // Ctrl＋滾輪照樣縮放
  view.axisTrackEl.getBoundingClientRect = () => ({ left: 100, width: 800 });
  let prevented = 0;
  gantt.fire('wheel', { ctrlKey: true, deltaY: -100, clientX: 500, preventDefault: () => prevented++ });
  assert.strictEqual(prevented, 1);
  assert.ok(plugin.ui.timelineDays < 90);
});

test('時間軸（裁定 39）：收起的列裡的記號用那一列的顏色——推測的空心圈也是（圈的顏色照那一列）', () => {
  const { view } = viewOf();
  view.setAllRows(true);
  const dots = byClass(view.timelineEl, 'wwh-sum-dot');
  assert.ok(dots.length > 0);
  const inferred = dots.filter((d) => d.classList.contains('is-inferred'));
  assert.ok(inferred.length > 0 && inferred.every((d) => /wwh-tone\d/.test(d.className)), '空心圈也帶那一列的色');
  assert.ok(dots.filter((d) => !d.classList.contains('is-late')).every((d) => /wwh-tone\d/.test(d.className)));
  assert.match(CSS, /\.wwh-sum-dot\.is-inferred \{[^}]*border: 1\.5px solid var\(--wwh-mark-c/, '圈不再是灰的');
});

// ---- 裁定 39：月曆 ----

function monthRaw() {
  const raw = sample();
  raw.timeline.rows = [
    {
      key: 'e-1', label: '信義王', type: '案子', progress: 'active', pauses: [], links: [],
      marks: [
        mark({ id: 'q2', shape: 'point', kind: 'deadline', start: null, end: '2026-10-20', text: '交圖', children: [] }),
        mark({ id: 'q1', shape: 'point', kind: 'meeting', start: null, end: '2026-10-20', time: '14:00', text: '丈量', children: [] }),
        mark({ id: 'p1', start: '2026-10-19', end: '2026-10-22', time: '09:30', text: '放樣', children: [] }),
        mark({ id: 'q-inf', shape: 'point', kind: 'meeting', start: null, end: '2026-10-21', text: '驗收', inferred: true, children: [] }),
        mark({ id: 'q-late', shape: 'point', kind: 'deadline', start: null, end: '2026-10-15', text: '回覆', late: true, children: [] }),
      ],
    },
  ];
  return raw;
}

test('月曆（裁定 39）：「回到今天」跟時間軸同一個位置（右上那排）、月份標題旁不另放；新增「全部收起／全部展開」同位置同字', () => {
  const { view, plugin } = viewOf(monthRaw());
  view.setMode('month');
  const tools = byClass(view.timelineEl, 'wwh-tools')[0];
  assert.deepStrictEqual(Array.from(tools.children).map((e) => e.textContent), ['全部收起', '回到今天', '時間軸月曆'], '順序跟時間軸那排一樣');
  assert.ok(!byClass(view.timelineEl, 'wwh-month-head')[0].textContent.includes('回到今天'), '月份標題旁不放');
  plugin.ui.month = { year: 2026, month: 5 };
  view.render();
  byClass(view.timelineEl, 'wwh-today-btn')[0].fire('click');
  assert.strictEqual(plugin.ui.month, null);
  assert.match(byClass(view.timelineEl, 'wwh-month-title')[0].textContent, /2026 年 10 月/);
});

test('月曆（裁定 39）：全部收起——期間變約 4px 細色線不寫字、單天的變色點；再按全部展開；記在 data.json', () => {
  const saved = [];
  const { view, plugin } = viewOf(monthRaw(), { saveMonthCollapsed: (on) => saved.push(on) });
  view.setMode('month');
  assert.strictEqual(byClass(view.timelineEl, 'wwh-mbar')[0].textContent, '09:30 放樣');
  assert.ok(byClass(view.timelineEl, 'wwh-day-mark').length >= 3);
  byClass(view.timelineEl, 'wwh-month-fold')[0].fire('click');
  assert.deepStrictEqual(saved, [true]);
  assert.strictEqual(plugin.ui.monthCollapsed, true);
  assert.strictEqual(byClass(view.timelineEl, 'wwh-month-fold')[0].textContent, '全部展開');
  assert.ok(byClass(view.timelineEl, 'wwh-month')[0].classList.contains('is-collapsed'));
  const bars = byClass(view.timelineEl, 'wwh-mbar');
  assert.ok(bars.length > 0 && bars.every((b) => b.classList.contains('is-thin') && b.textContent === ''), '細線不寫字');
  assert.ok(bars.every((b) => /wwh-tone\d/.test(b.className)), '照那一列的顏色');
  assert.ok(bars[0].attrs.title.includes('放樣'), '滑過去還看得到是什麼');
  assert.strictEqual(byClass(view.timelineEl, 'wwh-day-mark').length, 0);
  const dots = byClass(view.timelineEl, 'wwh-day-dot');
  assert.strictEqual(dots.length, 4, '單天的四件各一個色點');
  assert.ok(dots.every((d) => d.textContent === '' && /wwh-tone\d/.test(d.className)));
  assert.ok(dots.some((d) => d.classList.contains('is-late')) && dots.some((d) => d.classList.contains('is-inferred')), '過期、推測的點得出來');
  assert.match(CSS, /\.wwh-mbar\.is-thin \{[^}]*height: 4px/);
  assert.match(CSS, /\.wwh-day-dot \{[^}]*border-radius: 50%/);
  byClass(view.timelineEl, 'wwh-month-fold')[0].fire('click');
  assert.deepStrictEqual(saved, [true, false]);
  assert.strictEqual(byClass(view.timelineEl, 'wwh-day-dot').length, 0);
  assert.ok(byClass(view.timelineEl, 'wwh-day-mark').length >= 3, '展開回原樣');
});

test('月曆（裁定 39）：收起的狀態存在 data.json——sanitizeData 只收 true；plugin.saveMonthCollapsed 寫進去', async () => {
  assert.strictEqual(lib.sanitizeData({ monthCollapsed: true }).monthCollapsed, true);
  for (const bad of [false, 'yes', 1, null]) assert.ok(!('monthCollapsed' in lib.sanitizeData({ monthCollapsed: bad })), String(bad));
  assert.strictEqual(lib.defaultUi().monthCollapsed, false);
  const { plugin } = makeNotePlugin({});
  const written = [];
  plugin.saveData = async (d) => written.push(d);
  await plugin.saveMonthCollapsed(true);
  assert.strictEqual(written[0].monthCollapsed, true);
  await plugin.saveMonthCollapsed(false);
  assert.strictEqual(written[1].monthCollapsed, false);
  assert.ok(!('monthCollapsed' in lib.sanitizeData(written[1])));
});

test('月曆（裁定 39）：每天之間有淡的直線（跟橫線同色）——每週 7 個日期欄的底，第一欄不畫左線', () => {
  const { view } = viewOf(monthRaw());
  view.setMode('month');
  const weeks = byClass(view.timelineEl, 'wwh-week');
  assert.ok(weeks.length >= 4);
  for (const w of weeks) {
    const bgs = byClass(w, 'wwh-day-bg');
    assert.strictEqual(bgs.length, 7);
    assert.deepStrictEqual(bgs.map((b) => b.classList.contains('is-first')), [true, false, false, false, false, false, false]);
    assert.deepStrictEqual(bgs.map((b) => b.styleMap['grid-column']), ['1', '2', '3', '4', '5', '6', '7']);
  }
  assert.match(CSS, /\.wwh-day-bg \{[^}]*border-left: 1px solid var\(--wwh-line-soft\)/);
  assert.match(CSS, /\.wwh-week \{[^}]*border-top: 1px solid var\(--wwh-line-soft\)/, '橫線同一個顏色');
});

test('月曆（裁定 39）：點某天的日期數字或空白處跳出小框，列那天所有的事（時間、事情、案子名，有時間的在前）；點一件開相關的卡；「＋這天加一件」帶日期', () => {
  const opened = [];
  const added = [];
  const { view } = viewOf(monthRaw(), { openItem: (it) => opened.push(it.id), addAgendaForm: (p) => added.push(p) });
  view.setMode('month');
  const dayEl = (n) => byClass(view.timelineEl, 'wwh-day').find((d) => !d.classList.contains('is-out') && byClass(d, 'wwh-day-num')[0].textContent === String(n));
  assert.strictEqual(view.pop, null);
  dayEl(20).fire('click');
  const pop = view.pop;
  assert.ok(pop && pop.classList.contains('wwh-day-pop'));
  assert.strictEqual(byClass(pop, 'wwh-pop-title')[0].textContent, '10/20（週二）');
  const rows = byClass(pop, 'wwh-pop-row');
  assert.deepStrictEqual(rows.map((r) => [byClass(r, 'wwh-pop-time')[0].textContent, byClass(r, 'wwh-pop-text')[0].textContent, byClass(r, 'wwh-pop-row-name')[0].textContent]),
    [['09:30', '放樣', '信義王'], ['14:00', '丈量', '信義王'], ['', '交圖', '信義王']], '含跨天的期間；有時間的照時間在前');
  assert.ok(rows.every((r) => /wwh-tone\d/.test(byClass(r, 'wwh-pop-dot')[0].className)));
  rows[1].fire('click');
  assert.deepStrictEqual(opened, ['q1'], '點一件開它相關的卡');
  assert.strictEqual(view.pop, null, '點完關掉');
  // 空白處：整欄的底、有事的格子空白處、「還有 N 件」
  const wk = byClass(view.timelineEl, 'wwh-week').find((w) => byClass(w, 'wwh-day-num').some((n) => n.textContent === '20'));
  byClass(wk, 'wwh-day-bg')[2].fire('click');
  assert.ok(view.pop && byClass(view.pop, 'wwh-pop-row').length >= 1, '點格子的空白處也開');
  const marks = byClass(wk, 'wwh-day-marks')[0];
  marks.fire('click', { target: marks });
  assert.ok(view.pop);
  // 加一件
  byClass(view.pop, 'wwh-pop-add')[0].fire('click');
  assert.strictEqual(view.pop, null);
  assert.deepStrictEqual(added, [{ date: '2026-10-20' }], '日期填好那天');
});

test('月曆（裁定 39）：小框——這天沒有事寫「這天沒有事」仍有「＋這天加一件」（日期填好那天）；點框外、Esc、重畫都關', () => {
  const added = [];
  const { view } = viewOf(monthRaw(), { addAgendaForm: (p) => added.push(p) });
  view.setMode('month');
  const empty = byClass(view.timelineEl, 'wwh-day').find((d) => !d.classList.contains('is-out') && byClass(d, 'wwh-day-num')[0].textContent === '3');
  empty.fire('click');
  assert.strictEqual(byClass(view.pop, 'wwh-empty')[0].textContent, '這天沒有事');
  assert.strictEqual(byClass(view.pop, 'wwh-pop-title')[0].textContent, '10/3（週六）');
  byClass(view.pop, 'wwh-pop-add')[0].fire('click');
  assert.deepStrictEqual(added, [{ date: '2026-10-03' }]);
  // 點框外關
  empty.fire('click');
  assert.ok(view.pop);
  view.contentEl.fire('mousedown', { target: byClass(view.pop, 'wwh-pop-title')[0] });
  assert.ok(view.pop, '點框裡不關');
  view.contentEl.fire('mousedown', { target: view.searchEl });
  assert.strictEqual(view.pop, null, '點框外關');
  // Esc
  empty.fire('click');
  view.contentEl.fire('keydown', { key: 'a' });
  assert.ok(view.pop);
  view.contentEl.fire('keydown', { key: 'Escape' });
  assert.strictEqual(view.pop, null);
  // 重畫
  empty.fire('click');
  view.render();
  assert.strictEqual(view.pop, null);
  assert.strictEqual(byClass(view.root, 'wwh-pop').length, 0);
  assert.match(CSS, /\.wwh-pop \{[^}]*position: absolute/);
  assert.match(CSS, /\.wwh-root \{[^}]*position: relative/, '小框以首頁為底定位');
});

// ---- 裁定 39：推測的日程在日程確認 ----

function inferredTodo() {
  const raw = sample();
  raw.todo.today = [{ id: 'a-t', kind: 'reminder', end: '2026-10-30', time: '10:00', text: '確認窗簾款式', entities: ['信義王'], inferred: true }];
  return raw;
}

test('推測的日程（裁定 39）：待辦裡的「推測」小字可以點，跳小框「這條是我從檔案推測的，對嗎？」；答案對／改到某天…／不用了', () => {
  const ran = [];
  const opened = [];
  const { view } = viewOf(inferredTodo(), { runAction: (a) => ran.push(a), openItem: (it) => opened.push(it.id) });
  const tag = byClass(view.leftEl, 'wwh-tag-inferred')[0];
  assert.ok(tag.classList.contains('is-link'));
  tag.fire('click');
  const pop = view.pop;
  assert.ok(pop.classList.contains('wwh-infer-pop'));
  assert.strictEqual(byClass(pop, 'wwh-pop-title')[0].textContent, '確認窗簾款式');
  assert.strictEqual(byClass(pop, 'wwh-pop-ask')[0].textContent, '這條是我從檔案推測的，對嗎？');
  assert.deepStrictEqual(byClass(pop, 'wwh-answer').map((a) => a.textContent), ['對', '改到某天…', '不用了']);
  // 對 = agenda edit <id> 不帶欄位
  byClass(pop, 'wwh-answer')[0].fire('click');
  assert.deepStrictEqual(ran.map((a) => a.args), [['agenda', 'edit', 'a-t']]);
  assert.strictEqual(view.pop, null, '答完關小框');
  // 改到某天…：先展開日期，選好就跑
  tag.fire('click');
  const date = byClass(view.pop, 'wwh-fill-input')[0];
  assert.ok(date.classList.contains('wwh-hidden'), '點「改到某天…」才出現');
  byClass(view.pop, 'wwh-answer')[1].fire('click');
  assert.ok(!date.classList.contains('wwh-hidden'));
  date.value = '不是日期';
  date.fire('change');
  assert.strictEqual(ran.length, 1);
  date.value = '2026-12-05';
  date.fire('change');
  assert.deepStrictEqual(ran[1].args, ['agenda', 'edit', 'a-t', '--date', '2026-12-05']);
  assert.deepStrictEqual(ran[1].undo().args, ['agenda', 'edit', 'a-t', '--date', '2026-10-30'], '可以復原成原來的日期');
  // 不用了 = agenda cancel
  tag.fire('click');
  byClass(view.pop, 'wwh-answer')[2].fire('click');
  assert.deepStrictEqual(ran[2].args, ['agenda', 'cancel', 'a-t']);
  assert.deepStrictEqual(ran[2].undo().args, ['agenda', 'reopen', 'a-t']);
  // 開相關的卡
  tag.fire('click');
  byClass(view.pop, 'wwh-pop-open')[0].fire('click');
  assert.deepStrictEqual(opened, ['a-t']);
  assert.strictEqual(view.pop, null);
});

test('推測的日程（裁定 39）：時間軸與月曆點推測的那件跳同一個小框；不是推測的照舊直接開相關的卡', () => {
  const opened = [];
  const { view } = viewOf(null, { openItem: (it) => opened.push(it.id) });
  view.setAllRows(false);
  const inferred = byClass(view.timelineEl, 'wwh-mark').find((e) => e.classList.contains('is-inferred'));
  inferred.fire('click');
  assert.ok(view.pop && view.pop.classList.contains('wwh-infer-pop'), '時間軸的記號');
  assert.strictEqual(byClass(view.pop, 'wwh-pop-title')[0].textContent, '驗收會議');
  assert.deepStrictEqual(opened, []);
  view.closePop();
  const label = byClass(view.timelineEl, 'wwh-mark-label').find((e) => e.classList.contains('is-inferred'));
  label.fire('click');
  assert.ok(view.pop, '左欄那一列也是');
  view.closePop();
  const plain = byClass(view.timelineEl, 'wwh-mark').find((e) => e.classList.contains('is-point') && !e.classList.contains('is-inferred'));
  plain.fire('click');
  assert.strictEqual(view.pop, null);
  assert.strictEqual(opened.length, 1, '不是推測的直接開卡');
  // 月曆
  const m = viewOf(monthRaw(), { openItem: (it) => opened.push(it.id) }).view;
  m.setMode('month');
  byClass(m.timelineEl, 'wwh-day-mark').find((e) => e.classList.contains('is-inferred')).fire('click');
  assert.ok(m.pop && m.pop.classList.contains('wwh-infer-pop'), '月曆的單天');
  m.closePop();
  byClass(m.timelineEl, 'wwh-day-mark').find((e) => !e.classList.contains('is-inferred')).fire('click');
  assert.strictEqual(m.pop, null);
  assert.strictEqual(opened.length, 2);
  // 答完重畫（kb 把來源改成確認）：「推測」小字消失、虛線變實線
  const done = inferredTodo();
  done.todo.today[0].inferred = false;
  assert.strictEqual(byClass(viewOf(done).view.leftEl, 'wwh-tag-inferred').length, 0);
});

test('推測的日程（裁定 39）：actions.infer——對、改到某天、不用了的指令與復原', () => {
  const it = { id: 'a-7', end: '2026-11-05', text: '驗收' };
  assert.deepStrictEqual(lib.actions.infer(it, 'confirm').args, ['agenda', 'edit', 'a-7']);
  assert.strictEqual(lib.actions.infer(it, 'confirm').undo, null);
  assert.deepStrictEqual(lib.actions.infer(it, 'date', '2026-12-01').args, ['agenda', 'edit', 'a-7', '--date', '2026-12-01']);
  assert.deepStrictEqual(lib.actions.infer(it, 'cancel').args, ['agenda', 'cancel', 'a-7']);
  assert.strictEqual(typeof lib.actions.infer(it, 'cancel').undo, 'function');
});

test('顏色與間距（裁定 41）：要你確認的卡與推測小框——題目主文字色、答案淡灰（滑過才變主色）、題目與答案之間多 8px；小框的「開相關的卡」紫色', () => {
  assert.match(CSS, /\.wwh-confirm-text \{[^}]*color: var\(--text-normal\)/);
  assert.match(CSS, /\.wwh-answer \{[^}]*color: var\(--text-muted\)/);
  assert.match(CSS, /\.wwh-answer:hover \{[^}]*color: var\(--text-normal\)/);
  assert.match(CSS, /\.wwh-confirm-foot \{[^}]*margin-top: 8px/);
  assert.match(CSS, /\.wwh-infer-pop \.wwh-confirm-buttons \{[^}]*margin-top: 8px/);
  assert.match(CSS, /\.wwh-infer-pop \.wwh-pop-open \{[^}]*color: var\(--text-accent\)/);
});
