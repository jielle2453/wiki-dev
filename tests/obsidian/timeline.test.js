'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadMain } = require('./helpers/env');
const { byClass } = require('./helpers/fakedom');

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

test('月曆：bar 每天都列，點只在那天，星期日起算', () => {
  const home = sample();
  const m = lib.layoutMonth(home.timeline, { today: home.today });
  assert.strictEqual(m.year, 2026);
  assert.strictEqual(m.month, 9); // 10 月
  assert.ok(m.weeks.every((w) => w.length === 7));
  const day = (iso) => m.weeks.flat().find((d) => d.date === iso);
  assert.ok(day('2026-10-30').isToday);
  assert.strictEqual(day('2026-10-25').marks.some((x) => x.text === '施工'), true);
  assert.strictEqual(day('2026-10-24').marks.some((x) => x.text === '施工'), false);
  assert.strictEqual(day('2026-10-28').marks.filter((x) => x.text === '回覆報價').length, 1);
  assert.strictEqual(day('2026-10-29').marks.some((x) => x.text === '回覆報價'), false);
  assert.strictEqual(new Date(m.weeks[0][0].date + 'T00:00:00Z').getUTCDay(), 0);
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
  // 三個事類實體（含「其他」）各一塊
  assert.strictEqual(byClass(root, 'wwh-row').length, 3);
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
  const first = bars.find((b) => b.textContent === '施工');
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
  // 最近
  assert.strictEqual(byClass(root, 'wwh-recent-item').length, 1);
});

test('首頁：時間軸切月曆、全部收起、這週展開', () => {
  const plugin = { runner: {}, home: lib.normalizeHome(sample()), ui: lib.defaultUi(), loadedVersion: '0.28.0', openEntity() {}, itemMenu() {}, entityMenu() {} };
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  view.setAllRows(true);
  assert.strictEqual(byClass(view.root, 'wwh-track').length, 0);
  view.setAllRows(false);
  assert.strictEqual(byClass(view.root, 'wwh-track').length, 3);
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
