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
  assert.deepStrictEqual([bar.col, bar.span, bar.continuesLeft, bar.continuesRight], [0, 7, false, true], '10/25 週日起、橫跨整週');
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
  const order = [view.topEl, view.searchEl, view.timelineEl, view.colsEl].map((e) => kids.indexOf(e));
  assert.ok(order.every((n) => n >= 0) && order.every((n, i) => i === 0 || n > order[i - 1]), order.join());
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
  assert.strictEqual(byClass(first, 'wwh-todo-meta')[0].textContent, '信義王·承諾');
  assert.strictEqual(byClass(first, 'wwh-todo-when')[0].textContent, '10/28（週三）');
  assert.strictEqual(byTag(first, 'button').length, 0);
});

test('待辦（裁定 32）：「＋新增日程」在待辦標題旁；點日期改日期時間；點標題開相關的卡；點案子開綜合卡', () => {
  const calls = [];
  const { view } = viewOf(null, {
    addAgendaForm: () => calls.push('add'),
    editDateForm: (it) => calls.push('edit:' + it.id),
    openItem: (it) => calls.push('line:' + it.id),
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

test('時間軸（裁定 32）：點名字收合（單雙數交替淡底）；點一件開相關的卡', () => {
  const calls = [];
  const { view, plugin } = viewOf(null, { openItem: (it) => calls.push('item:' + it.id) });
  const rows = byClass(view.timelineEl, 'wwh-row');
  assert.deepStrictEqual(rows.map((r) => r.classList.contains('is-alt')), [false, true, false], '單雙數交替淡底');
  assert.strictEqual(byClass(view.timelineEl, 'wwh-row-link').length, 0, '名字不再是連結');
  byClass(rows[0], 'wwh-fold')[0].fire('click'); // 名字在標題列裡，點到名字就是點到標題列
  assert.strictEqual(plugin.ui.rowCollapsed['e-1a2b3c4d'], true, '點名字收合');
  plugin.ui.rowCollapsed['e-1a2b3c4d'] = false;
  view.render();
  byClass(byClass(view.timelineEl, 'wwh-row')[0], 'wwh-mark-label')[0].fire('click');
  assert.match(calls[0], /^item:a-/, '開的是日程那一件');
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

test('月曆（裁定 32）：期間每件事一個淡色，同一件跨週同色，不同件不同色', () => {
  const raw = sample();
  raw.timeline.rows = [
    {
      key: 'e-1', label: '信義王', type: '案子', progress: 'active', pauses: [], links: [],
      marks: [
        mark({ id: 'p1', start: '2026-10-05', end: '2026-10-16', text: '水電', children: [] }),
        mark({ id: 'p2', start: '2026-10-07', end: '2026-10-09', text: '放樣', children: [] }),
      ],
    },
  ];
  const m = lib.layoutMonth(raw.timeline, { today: raw.today });
  const colorOf = (text) => m.weeks.flatMap((w) => w.bars).filter((b) => b.text === text).map((b) => b.color);
  assert.strictEqual(colorOf('水電').length, 2, '水電跨兩週');
  assert.strictEqual(new Set(colorOf('水電')).size, 1, '同一件跨週同色');
  assert.notStrictEqual(colorOf('水電')[0], colorOf('放樣')[0], '不同件不同色');
  assert.ok(m.weeks.flatMap((w) => w.bars).every((b) => b.color >= 0 && b.color < lib.MONTH_COLORS));
  const { view } = viewOf(raw);
  view.setMode('month');
  const bars = byClass(view.timelineEl, 'wwh-mbar');
  assert.ok(bars.every((b) => /wwh-mc[0-7]/.test(b.className)), '每條 bar 帶自己的顏色 class');
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

test('要你確認的（裁定 34）：答案分三種——有 argv 的跑、有 argv 又要填的先填、只能在對話做的複製一句話', () => {
  assert.strictEqual(lib.answerKind({ label: '是', argv: ['a'], fill: null }), 'run');
  assert.strictEqual(lib.answerKind({ label: '先放著', argv: ['asks', 'set-aside', 'k'], fill: null }), 'run');
  assert.strictEqual(lib.answerKind({ label: '改到某天', argv: ['agenda', 'edit', 'a-1', '--date', '{新日期}'], fill: { name: '新日期', rule: 'YYYY-MM-DD' } }), 'fill');
  assert.strictEqual(lib.answerKind({ label: '名字改成別的', argv: null, fill: { name: '新名字', rule: 'x' } }), 'chat', '兩條指令的（有 fill 但 argv 是 null）也是對話');
  assert.strictEqual(lib.answerKind({ label: '照你改的做', argv: null, fill: null }), 'chat');
  assert.strictEqual(lib.answerKind(null), 'chat');
});

test('要你確認的（裁定 34）：只能在對話做的答案，字旁有小對話圖示；點了呼叫 chooseResult（複製一句話）', () => {
  const chosen = [];
  const raw = confirmHome([{ label: '是', argv: ['x'], fill: null }, { label: '照你改的做', argv: null, fill: null }]);
  const { view } = viewOf(raw, { chooseResult: (c, r) => chosen.push(r.label) });
  const answers = byClass(view.rightEl, 'wwh-answer');
  assert.deepStrictEqual(answers.map((a) => a.classList.contains('is-chat')), [false, true]);
  assert.strictEqual(byClass(answers[0], 'wwh-answer-chat').length, 0);
  assert.strictEqual(byClass(answers[1], 'wwh-answer-chat').length, 1);
  assert.strictEqual(byTag(answers[1], 'svg').length, 1, '小對話圖示');
  assert.strictEqual(answers[1].textContent, '照你改的做', '圖示不佔字');
  answers[1].fire('click');
  assert.deepStrictEqual(chosen, ['照你改的做']);
});

test('要你確認的（裁定 34）：要填的答案點了在卡上展開小輸入，日期用日期選擇、名字用文字框，Enter 才跑、Esc 取消', () => {
  const chosen = [];
  const raw = confirmHome([
    { label: '還沒，改到某天', argv: ['agenda', 'edit', 'a-1', '--date', '{新日期}'], fill: { name: '新日期', rule: 'YYYY-MM-DD' } },
    { label: '跟已有的另一個是同一個', argv: ['entity', 'merge', '王先生', '--into', '{同一個}'], fill: { name: '同一個', rule: '一個名字' } },
    { label: '不用了', argv: ['agenda', 'cancel', 'a-1'], fill: null },
  ]);
  const { view, plugin } = viewOf(raw, { chooseResult: (c, r, v) => chosen.push([r.label, v]) });
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill').length, 0, '沒點之前不展開');
  byClass(view.rightEl, 'wwh-answer')[0].fire('click');
  const input = byClass(view.rightEl, 'wwh-fill-input')[0];
  assert.strictEqual(input.attrs.type, 'date');
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill-label')[0].textContent, '新日期：');
  assert.ok(byClass(view.rightEl, 'wwh-answer')[0].classList.contains('is-on'));
  // 沒填就按 Enter：不跑
  input.value = '';
  input.fire('keydown', { key: 'Enter', target: input });
  assert.deepStrictEqual(chosen, []);
  // 填好按 Enter：跑，帶著填的值，展開收起
  input.value = '2026-11-20';
  input.fire('keydown', { key: 'Enter', target: input });
  assert.deepStrictEqual(chosen, [['還沒，改到某天', '2026-11-20']]);
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill').length, 0);
  assert.strictEqual(plugin.ui.confirmFill, null);
  // 名字：文字框；注音選字中的 Enter 不跑；Esc 取消
  byClass(view.rightEl, 'wwh-answer')[1].fire('click');
  const text = byClass(view.rightEl, 'wwh-fill-input')[0];
  assert.strictEqual(text.attrs.type, 'text');
  text.value = '王大明';
  text.fire('compositionstart');
  text.fire('keydown', { key: 'Enter', target: text });
  assert.strictEqual(chosen.length, 1, '選字中不跑');
  text.fire('compositionend');
  text.fire('keydown', { key: 'Escape', target: text });
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill').length, 0, 'Esc 收起');
  assert.strictEqual(chosen.length, 1);
  // 沒有 fill 的照舊一點就跑
  byClass(view.rightEl, 'wwh-answer')[2].fire('click');
  assert.deepStrictEqual(chosen[1], ['不用了', undefined]);
});

test('要你確認的（裁定 34）：填空的小輸入在重畫之後還在（記著填到一半的字），換一題就收起', () => {
  const raw = confirmHome([{ label: '改到某天', argv: ['a', '{d}'], fill: { name: 'd', rule: 'YYYY-MM-DD' } }]);
  const { view, plugin } = viewOf(raw, {});
  byClass(view.rightEl, 'wwh-answer')[0].fire('click');
  const input = byClass(view.rightEl, 'wwh-fill-input')[0];
  input.value = '2026-12-01';
  input.fire('input', { target: input });
  view.render();
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill-input')[0].value, '2026-12-01');
  plugin.home = lib.normalizeHome(Object.assign(sample(), { confirm: [{ key: 'other', text: '別題', results: [{ label: 'x', argv: null }] }] }));
  view.render();
  assert.strictEqual(byClass(view.rightEl, 'wwh-fill').length, 0);
});

test('要你確認的（裁定 34）：fillDecision 與 chatPhrase', () => {
  assert.deepStrictEqual(lib.fillDecision({ key: 'Enter', value: ' 王大明 ' }), { run: true, value: '王大明' });
  assert.deepStrictEqual(lib.fillDecision({ key: 'Enter', value: '  ' }), {});
  assert.deepStrictEqual(lib.fillDecision({ key: 'Enter', value: 'x', isComposing: true }), {});
  assert.deepStrictEqual(lib.fillDecision({ key: 'Enter', value: 'x', keyCode: 229 }), {});
  assert.deepStrictEqual(lib.fillDecision({ key: 'Enter', value: '明天', type: 'date' }), {}, '日期格式不對不跑');
  assert.deepStrictEqual(lib.fillDecision({ key: 'Escape' }), { cancel: true });
  assert.strictEqual(lib.fillInputType({ name: '新日期', rule: 'YYYY-MM-DD' }), 'date');
  assert.strictEqual(lib.fillInputType({ name: '新名字', rule: '一個名字' }), 'text');
  assert.strictEqual(lib.chatPhrase({ text: '這題？' }, { label: '照你改的做' }), '關於「這題？」，我選「照你改的做」');
  assert.strictEqual(lib.chatPhrase({ text: '這題？' }, { label: '名字改成別的', fill: { name: '新名字' } }), '關於「這題？」，我選「名字改成別的」，新名字是：');
});

test('版面（裁定 34）：待辦整區也是白卡；版面放寬到 1600px；答案間距約 20px；兩欄空隙縮小', () => {
  const { view } = viewOf();
  assert.ok(view.leftEl.classList.contains('wwh-paper'), '待辦整區白卡淡陰影');
  assert.match(CSS, /\.wwh-root > \* \{[^}]*max-width: 1600px/);
  assert.match(CSS, /\.wwh-confirm-buttons \{[^}]*gap: 8px 20px/);
  assert.match(CSS, /\.wwh-cols \{[^}]*gap: 28px 20px/);
});

// ---- 時間軸縮放與左右捲動 ----

test('時間軸（裁定 34）：縮放四段、預設三個月；壞值退回預設', () => {
  assert.deepStrictEqual(lib.TIMELINE_ZOOMS.map((z) => [z.days, z.label]), [[14, '兩週'], [30, '一個月'], [90, '三個月'], [180, '半年']]);
  assert.strictEqual(lib.DEFAULT_ZOOM, 90);
  assert.strictEqual(lib.zoomOf(30), 30);
  assert.strictEqual(lib.zoomOf('180'), 180);
  assert.strictEqual(lib.zoomOf(7), 90);
  assert.strictEqual(lib.zoomOf(undefined), 90);
  assert.strictEqual(lib.defaultUi().timelineDays, 90);
});

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

test('時間軸（裁定 34）：四段縮放按下去換、記起來；「回到今天」把捲動歸零', () => {
  const saved = [];
  const { view, plugin } = viewOf(null, { saveTimelineDays: (d) => saved.push(d) });
  const segs = () => byClass(view.timelineEl, 'wwh-zoom')[0];
  assert.deepStrictEqual(byClass(segs(), 'wwh-seg').map((s) => s.textContent), ['兩週', '一個月', '三個月', '半年']);
  assert.deepStrictEqual(byClass(segs(), 'wwh-seg').map((s) => s.classList.contains('is-on')), [false, false, true, false]);
  byClass(segs(), 'wwh-seg')[1].fire('click');
  assert.strictEqual(plugin.ui.timelineDays, 30);
  assert.deepStrictEqual(saved, [30]);
  assert.deepStrictEqual(byClass(segs(), 'wwh-seg').map((s) => s.classList.contains('is-on')), [false, true, false, false]);
  const slide = byClass(view.timelineEl, 'wwh-slide')[0];
  assert.ok(Math.abs(parseFloat(slide.styleMap.width) - (70 / 30) * 100) < 1e-6, '看得少，軸拉得長');
  plugin.ui.tlStart = lib.dayNumber('2026-11-10');
  byClass(segs(), 'wwh-seg')[0].fire('click'); // 30 -> 14
  assert.strictEqual(plugin.ui.tlStart, lib.dayNumber('2026-11-10') + 15 - 7, '捲過的，換縮放留在看著的中間');
  byClass(view.timelineEl, 'wwh-today-btn')[0].fire('click');
  assert.strictEqual(plugin.ui.tlStart, null);
  const gantt = byClass(view.timelineEl, 'wwh-gantt')[0];
  assert.ok(parseFloat(gantt.styleMap['--wwh-tx']) <= 0);
});

test('時間軸（裁定 34）：兩週的軸每天一格；釘在左邊的月份跟著捲動換', () => {
  const { view, plugin } = viewOf();
  byClass(byClass(view.timelineEl, 'wwh-zoom')[0], 'wwh-seg')[0].fire('click');
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

test('時間軸（裁定 34）：縮放記在 data.json，開起來讀回；其他欄位不被洗掉', async () => {
  assert.strictEqual(lib.sanitizeData({ opened: [], timelineDays: 30 }).timelineDays, 30);
  assert.strictEqual(lib.sanitizeData({ opened: [], timelineDays: 7 }).timelineDays, undefined);
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
  await plugin.saveTimelineDays(5);
  assert.strictEqual(saves[1].timelineDays, 90, '壞值存預設');
});

// ---- 裁定 35（D-267）：首頁最底下的隨手記 ----

test('隨手記（裁定 35）：最近 3 則從那一頁最後幾行讀，新到舊；檔頭與不是「- 日期 時間 內容」的行略過', () => {
  const text = ['# 隨手記', '', '- 2026-10-01 08:00 最舊的', '她自己加的一行', '- 2026-10-02 09:30 第二', '- 2026-10-30 10:05 含 - 與 空白  的 一則', '- 2026-10-30 17:27 最新'].join('\n');
  assert.deepStrictEqual(lib.jotRecent(text, 3), [
    { date: '2026-10-30', time: '17:27', text: '最新' },
    { date: '2026-10-30', time: '10:05', text: '含 - 與 空白  的 一則' },
    { date: '2026-10-02', time: '09:30', text: '第二' },
  ]);
  assert.strictEqual(lib.jotRecent(text, 10).length, 4, '不足就有幾則給幾則');
  assert.deepStrictEqual(lib.jotRecent('', 3), []);
  assert.deepStrictEqual(lib.jotRecent(null, 3), []);
  assert.deepStrictEqual(lib.jotRecent('# 隨手記\r\n\r\n- 2026-10-30 17:27 CRLF 的檔\r\n', 3), [{ date: '2026-10-30', time: '17:27', text: 'CRLF 的檔' }]);
  assert.strictEqual(lib.JOT_REL, `${lib.FREE_DIR}/隨手記.md`);
});

test('隨手記（裁定 35）：Enter 才存；注音選字中不存；空的不存', () => {
  assert.deepStrictEqual(lib.jotDecision({ key: 'Enter', value: '  記一下  ' }), { save: true, text: '記一下' });
  assert.deepStrictEqual(lib.jotDecision({ key: 'Enter', value: '   ' }), {});
  assert.deepStrictEqual(lib.jotDecision({ key: 'Enter', value: 'x', composing: true }), {});
  assert.deepStrictEqual(lib.jotDecision({ key: 'Enter', value: 'x', isComposing: true }), {});
  assert.deepStrictEqual(lib.jotDecision({ key: 'Enter', value: 'x', keyCode: 229 }), {});
  assert.deepStrictEqual(lib.jotDecision({ key: 'a', value: 'x' }), {});
});

test('隨手記（裁定 35）：動作是 kb jot（內容前面隔 --），復原退回 kb 回的那個回合', () => {
  const a = lib.actions.jot('-開頭的字');
  assert.deepStrictEqual(a.args, ['jot', '--json', '--', '-開頭的字']);
  assert.strictEqual(a.toastText(), '記下了');
  assert.deepStrictEqual(a.undo({ path: '_extras/隨手記.md', line: '- x', turn: '20261030-172756-obsd' }), { args: ['versions', 'revert', '20261030-172756-obsd'] });
  assert.strictEqual(a.undo({ path: 'x' }), null, 'kb 沒回回合代號就不給復原');
  assert.strictEqual(a.undo(null), null);
});

test('隨手記（裁定 35）：在首頁最底下，有輸入框；最近 3 則淡淡列，下面「看全部」開那一頁', () => {
  const opened = [];
  const { view, plugin } = viewOf(null, { jotLines: [{ date: '2026-10-30', time: '17:27', text: '最新' }, { date: '2026-10-29', time: '09:00', text: '前一則' }], openPathInVault: (r) => opened.push(r) });
  const kids = Array.from(view.root.children);
  assert.strictEqual(kids[kids.length - 1], view.jotEl, '最底下');
  assert.ok(kids.indexOf(view.colsEl) < kids.indexOf(view.jotEl));
  assert.ok(view.jotEl.classList.contains('wwh-paper'));
  const input = byClass(view.jotEl, 'wwh-jot-input')[0];
  assert.strictEqual(input.attrs.placeholder, '隨手記一下…');
  const rows = byClass(view.jotEl, 'wwh-jot-row');
  assert.deepStrictEqual(rows.map((r) => byClass(r, 'wwh-jot-text')[0].textContent), ['最新', '前一則']);
  assert.deepStrictEqual(rows.map((r) => byClass(r, 'wwh-jot-when')[0].textContent), ['10/30 17:27', '10/29 09:00']);
  byClass(view.jotEl, 'wwh-jot-all')[0].fire('click');
  assert.deepStrictEqual(opened, ['_extras/隨手記.md']);
  assert.ok(plugin);
});

test('隨手記（裁定 35）：讀不到那一頁就不列，也不顯示「看全部」', () => {
  const { view } = viewOf(null, { jotLines: [] });
  assert.strictEqual(byClass(view.jotEl, 'wwh-jot-row').length, 0);
  assert.strictEqual(byClass(view.jotEl, 'wwh-jot-all').length, 0);
  assert.strictEqual(byClass(view.jotEl, 'wwh-jot-input').length, 1, '輸入框還在');
});

test('隨手記（裁定 35）：Enter 存（去頭尾空白）、存成功才清空；注音選字中、空的不存；沒存成字留著', async () => {
  const saved = [];
  let result = { ok: true };
  const { view, plugin } = viewOf(null, { saveJot: async (t) => { saved.push(t); return result; } });
  const input = byClass(view.jotEl, 'wwh-jot-input')[0];
  input.value = '  11 月談保固  ';
  input.fire('input');
  assert.strictEqual(plugin.ui.jotDraft, '  11 月談保固  ');
  input.fire('compositionstart');
  input.fire('keydown', { key: 'Enter' });
  assert.deepStrictEqual(saved, [], '選字中不存');
  input.fire('compositionend');
  input.fire('keydown', { key: 'Enter' });
  await new Promise((r) => setImmediate(r));
  assert.deepStrictEqual(saved, ['11 月談保固']);
  assert.strictEqual(input.value, '', '存成功清空');
  assert.strictEqual(plugin.ui.jotDraft, '');
  input.value = '   ';
  input.fire('keydown', { key: 'Enter' });
  assert.strictEqual(saved.length, 1, '空的不存');
  result = { ok: false };
  input.value = '被擋下的';
  input.fire('keydown', { key: 'Enter' });
  await new Promise((r) => setImmediate(r));
  assert.strictEqual(saved.length, 2);
  assert.strictEqual(input.value, '被擋下的', '沒存成字留著');
});

test('隨手記（裁定 35）：重畫不洗掉打到一半的字，輸入框還是同一個（游標不掉）', () => {
  const { view, plugin } = viewOf();
  const input = byClass(view.jotEl, 'wwh-jot-input')[0];
  input.value = '打到一半';
  input.fire('input');
  view.render();
  plugin.jotLines = [{ date: '2026-10-30', time: '17:27', text: '新的一則' }];
  view.render();
  assert.strictEqual(byClass(view.jotEl, 'wwh-jot-input')[0], input);
  assert.strictEqual(input.value, '打到一半');
  assert.strictEqual(byClass(view.jotEl, 'wwh-jot-row').length, 1);
});

test('隨手記（裁定 35）：plugin 存一則——叫 kb jot、跳「記下了」加復原；復原走 versions revert 那一個回合；存完重讀最近幾則', async () => {
  const os = require('node:os');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'wwh-jot-'));
  try {
    const { plugin, calls, toasts } = makeJotPlugin(dir);
    fs.mkdirSync(path.join(dir, lib.FREE_DIR), { recursive: true });
    plugin.runner.run = async (args) => {
      calls.push(args);
      if (args[0] === 'jot') {
        fs.writeFileSync(path.join(dir, lib.JOT_REL), '# 隨手記\n\n- 2026-10-30 17:27 存進去的\n', 'utf8');
        return { code: 0, stdout: JSON.stringify({ path: lib.JOT_REL, line: '- 2026-10-30 17:27 存進去的', turn: '20261030-172756-obsd' }), stderr: '' };
      }
      return { code: 0, stdout: '退回了', stderr: '' };
    };
    const r = await plugin.saveJot('存進去的');
    assert.strictEqual(r.ok, true);
    assert.deepStrictEqual(calls[0], ['jot', '--json', '--', '存進去的']);
    assert.strictEqual(toasts[0].t, '記下了');
    assert.ok(toasts[0].undo, '有復原');
    assert.deepStrictEqual(plugin.jotLines, [{ date: '2026-10-30', time: '17:27', text: '存進去的' }]);
    await toasts[0].undo();
    assert.deepStrictEqual(calls[1], ['versions', 'revert', '20261030-172756-obsd']);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

test('隨手記（裁定 35）：kb 擋了（exit 3）不重讀、不當成存成功', async () => {
  const { plugin, toasts } = makeJotPlugin('/不存在');
  plugin.runner.run = async () => ({ code: 3, stdout: '沒有內容可以記', stderr: '' });
  const r = await plugin.saveJot('x');
  assert.strictEqual(r.ok, false);
  assert.ok(toasts.length >= 1);
});

test('隨手記（裁定 35）：讀不到檔（沒建過、沒權限）jotLines 是空的，不丟錯', () => {
  const { plugin } = makeJotPlugin('/一定不存在的路徑');
  plugin.jotLines = [{ date: 'x', time: 'y', text: 'z' }];
  plugin.readJot();
  assert.deepStrictEqual(plugin.jotLines, []);
});

function makeJotPlugin(dir) {
  const calls = [];
  const toasts = [];
  const app = { vault: { adapter: { getBasePath: () => dir } }, workspace: { getLeavesOfType: () => [] } };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.ui = lib.defaultUi();
  plugin.vaultPath = dir;
  plugin.data = lib.sanitizeData(null);
  plugin.home = lib.normalizeHome(sample());
  plugin.runner = { run: async (args) => { calls.push(args); return { code: 0, stdout: '', stderr: '' }; } };
  plugin.toast = (t, o) => toasts.push({ t, undo: o && o.undo });
  plugin.scheduleRefresh = () => {};
  plugin.renderAll = () => {};
  return { plugin, calls, toasts };
}
