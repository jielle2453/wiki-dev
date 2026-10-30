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
            mark({ id: 'a-late', shape: 'point', kind: 'promise', start: null, end: '2026-10-28', text: '回覆報價', late: true }),
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
  assert.deepStrictEqual([bar.col, bar.span, bar.label, bar.continuesLeft, bar.continuesRight], [0, 7, true, false, true], '10/25 週日起、橫跨整週');
  assert.strictEqual(new Date(m.weeks[0].days[0].date + 'T00:00:00Z').getUTCDay(), 0);
  const next = lib.shiftMonth(2026, 11, 1);
  assert.deepStrictEqual(next, { year: 2027, month: 0 });
});

test('首頁畫出來：鼓勵句、件數、時間軸列與 bar、待辦三組、要你確認的、其他要處理的', () => {
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
  assert.strictEqual(byClass(root, 'wwh-confirm-buttons')[0].children.length, 2);
  // 其他要處理的預設收起
  assert.strictEqual(byClass(root, 'wwh-other').length, 0);
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
  plugin.home.counts = null; // 弄壞件數那一區
  const view = new lib.HomeView({}, plugin);
  view.build();
  const origError = console.error;
  console.error = () => {};
  try {
    view.render();
  } finally {
    console.error = origError;
  }
  assert.match(byClass(view.root, 'wwh-top')[0].textContent, /畫不出來/);
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

test('時間軸（裁定 28）：軸頭只標月份、畫週線；今天的旗子與月份各在自己那一行', () => {
  const { view } = viewOf();
  const axis = byClass(view.root, 'wwh-axis')[0];
  const labels = byClass(axis, 'wwh-tick').map((t) => t.textContent);
  assert.ok(labels.length >= 2 && labels.every((t) => /月$/.test(t)), labels.join());
  assert.strictEqual(labels[0], '10月', '起點那個月也標');
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

test('版面（裁定 30）：數字 → 搜尋 → 待辦｜要你確認的 → 手上的事', () => {
  const { view } = viewOf();
  const kids = Array.from(view.root.children);
  const order = [view.topEl, view.searchEl, view.colsEl, view.timelineEl].map((e) => kids.indexOf(e));
  assert.ok(order.every((n) => n >= 0) && order.every((n, i) => i === 0 || n > order[i - 1]), order.join());
  const counts = byClass(view.topEl, 'wwh-count').map((c) => c.textContent);
  assert.deepStrictEqual(counts, ['1已經過了', '1今天', '1要你確認'], '大數字只有三個');
  assert.match(byClass(view.topEl, 'wwh-counts-minor')[0].textContent, /這週 2.*其他要處理 1/, '這週、其他要處理是淡的小字');
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
  assert.strictEqual(byClass(first, 'wwh-todo-meta')[0].textContent, '信義王·承諾');
  assert.strictEqual(byClass(first, 'wwh-todo-when')[0].textContent, '10/28（週三）');
  assert.strictEqual(byTag(first, 'button').length, 0);
});

test('待辦（裁定 30）：「＋新增日程」在待辦標題旁；點日期改日期時間；點標題開日程.md；點案子開綜合卡', () => {
  const calls = [];
  const { view } = viewOf(null, {
    addAgendaForm: () => calls.push('add'),
    editDateForm: (it) => calls.push('edit:' + it.id),
    openAgendaLine: (it) => calls.push('line:' + it.id),
    openSynthesis: (n) => calls.push('card:' + n),
  });
  const add = byClass(view.leftEl, 'wwh-add-btn')[0];
  assert.strictEqual(add.textContent, '＋新增日程');
  add.fire('click');
  const row = byClass(view.leftEl, 'wwh-todo')[0];
  byClass(row, 'wwh-todo-when')[0].fire('click');
  byClass(row, 'wwh-todo-text')[0].fire('click');
  byClass(row, 'wwh-todo-entity')[0].fire('click', { stopPropagation() {} });
  assert.deepStrictEqual(calls, ['add', 'edit:a-late', 'line:a-late', 'card:信義王']);
});

test('要你確認的（裁定 30）：答案是淡的文字選項，不是按鈕；點了照 argv 做', () => {
  const chosen = [];
  const { view } = viewOf(null, { chooseResult: (c, r) => chosen.push(r.label) });
  const answers = byClass(view.rightEl, 'wwh-answer');
  assert.deepStrictEqual(answers.map((a) => a.textContent), ['是，合併', '跟 Claude 說']);
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

test('時間軸（裁定 30）：名稱開綜合卡、標題列收合；點一件開日程.md 那一行', () => {
  const calls = [];
  const { view, plugin } = viewOf(null, { openSynthesis: (n) => calls.push('card:' + n), openAgendaLine: (it) => calls.push('line:' + it.id) });
  const row = byClass(view.timelineEl, 'wwh-row')[0];
  byClass(row, 'wwh-row-name')[0].fire('click', { stopPropagation() {} });
  assert.deepStrictEqual(calls, ['card:信義王']);
  assert.strictEqual(plugin.ui.rowCollapsed['e-1a2b3c4d'], undefined, '點名稱不收合');
  byClass(row, 'wwh-mark-label')[0].fire('click');
  assert.match(calls[1], /^line:a-/, '開的是日程那一件');
});

test('月曆（裁定 30）：期間畫成橫跨那一週的一條 bar，名字只在開頭寫，跨週接著畫；推測的淡色；做完的不畫', () => {
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
  assert.deepStrictEqual([pipe1.col, pipe1.span, pipe1.label, pipe1.continuesRight], [1, 6, true, true]);
  assert.deepStrictEqual([pipe2.col, pipe2.span, pipe2.label, pipe2.continuesLeft], [0, 6, false, true], '下一週接著畫、不重寫名字');
  assert.deepStrictEqual(w1.bars.map((b) => b.lane), [0, 1], '同一週重疊的 bar 疊在不同層');
  assert.ok(!m.weeks.some((w) => w.bars.some((b) => b.text === '做完的期間')), '做完的不畫');
  const cell = (iso) => m.weeks.flatMap((w) => w.days).find((d) => d.date === iso);
  assert.deepStrictEqual(cell('2026-10-21').marks.map((x) => x.text), ['單天'], '單天的才佔格子');
  assert.deepStrictEqual(cell('2026-10-20').marks.map((x) => x.text), ['交圖']);

  const { view } = viewOf(raw);
  view.setMode('month');
  const bars = byClass(view.timelineEl, 'wwh-mbar');
  assert.strictEqual(bars.length, 3, '水電兩週各一條、放樣一條');
  assert.deepStrictEqual(bars.map((b) => b.textContent), ['水電', '放樣', ''], '第二週那條不寫名字');
  assert.ok(bars[1].classList.contains('is-inferred'), '推測的用淡色，不用虛線框');
  assert.strictEqual(bars[0].styleMap['grid-column'], '2 / span 6');
  assert.ok(bars[2].classList.contains('clip-left'));
  assert.strictEqual(byClass(view.timelineEl, 'wwh-day-mark').map((e) => e.textContent).sort().join(), '交圖,單天');
});

test('月曆（裁定 30）：點 bar 或單天的記號，開日程.md 那一行', () => {
  const calls = [];
  const raw = sample();
  raw.timeline.rows = [{ key: 'e-1', label: '信義王', type: '案子', progress: 'active', pauses: [], links: [], marks: [mark({ id: 'p1', start: '2026-10-05', end: '2026-10-09', text: '水電', children: [] }), mark({ id: 'q1', shape: 'point', kind: 'deadline', start: null, end: '2026-10-20', text: '交圖', children: [] })] }];
  const { view } = viewOf(raw, { openAgendaLine: (it) => calls.push(it.id) });
  view.setMode('month');
  byClass(view.timelineEl, 'wwh-mbar')[0].fire('click');
  byClass(view.timelineEl, 'wwh-day-mark')[0].fire('click');
  assert.deepStrictEqual(calls, ['p1', 'q1']);
});
