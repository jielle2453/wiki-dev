'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadMain } = require('./helpers/env');
const { byClass, byTag } = require('./helpers/fakedom');

const env = loadMain();
const lib = env.lib;
test.after(() => env.restore());

test('Enter 才搜；其他鍵不搜', () => {
  assert.deepStrictEqual(lib.searchDecision({ key: 'Enter', value: '王先生 報價' }), { search: true, query: '王先生 報價' });
  assert.deepStrictEqual(lib.searchDecision({ key: 'a', value: '王先生' }), { search: false });
  assert.deepStrictEqual(lib.searchDecision({ key: 'ArrowDown', value: '王先生' }), { search: false });
});

test('空字串按 Enter 不搜（只清掉結果）', () => {
  assert.deepStrictEqual(lib.searchDecision({ key: 'Enter', value: '   ' }), { search: false, clear: true });
  assert.deepStrictEqual(lib.searchDecision({ key: 'Enter', value: '' }), { search: false, clear: true });
});

test('注音選字中（compositionstart 到 compositionend）按 Enter 不搜', () => {
  assert.strictEqual(lib.searchDecision({ key: 'Enter', value: 'ㄨㄤˊ', composing: true }).search, false);
  assert.strictEqual(lib.searchDecision({ key: 'Enter', value: '王', isComposing: true }).search, false);
  assert.strictEqual(lib.searchDecision({ key: 'Enter', value: '王', keyCode: 229 }).search, false);
  assert.strictEqual(lib.searchDecision({ key: 'Enter', value: '王', composing: false, isComposing: false, keyCode: 13 }).search, true);
});

function makeView(extra) {
  const calls = [];
  const plugin = Object.assign(
    {
      runner: {
        run: async (args) => {
          calls.push(args);
          return { code: 0, stdout: JSON.stringify({ q: args[1], parsed: [], entities: [], files: [], total: 0, more: false }), stderr: '' };
        },
      },
      home: lib.normalizeHome({ recent: [] }),
      ui: lib.defaultUi(),
      loadedVersion: '0.28.0',
      askClaude() {},
      openEntity() {},
      openFile() {},
      openCard() {},
    },
    extra,
  );
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  return { view, plugin, calls };
}

test('搜尋框：選字中按 Enter 不叫 kb find，compositionend 之後的 Enter 才叫', async () => {
  const { view, calls } = makeView();
  view.inputEl.value = 'ㄨㄤˊ';
  view.inputEl.fire('compositionstart');
  view.inputEl.fire('keydown', { key: 'Enter' });
  assert.strictEqual(calls.length, 0);
  view.inputEl.value = '王先生';
  view.inputEl.fire('compositionend');
  view.inputEl.fire('keydown', { key: 'Enter', isComposing: true }); // 選字確認的那一下 Enter
  assert.strictEqual(calls.length, 0);
  view.inputEl.fire('keydown', { key: 'Enter' });
  await new Promise((r) => setImmediate(r));
  assert.deepStrictEqual(calls, [['find', '王先生', '--json']]);
});

test('搜尋框：打字時不搜、空字串 Enter 不搜', async () => {
  const { view, calls } = makeView();
  view.inputEl.value = '王';
  view.inputEl.fire('input');
  view.inputEl.fire('keydown', { key: 'a' });
  view.inputEl.value = '';
  view.inputEl.fire('keydown', { key: 'Enter' });
  await new Promise((r) => setImmediate(r));
  assert.strictEqual(calls.length, 0);
});

test('kb find 的參數：字開頭是 - 時用 -- 隔開', () => {
  assert.deepStrictEqual(lib.findArgs('王先生 報價'), ['find', '王先生 報價', '--json']);
  assert.deepStrictEqual(lib.findArgs('-5 度'), ['find', '--json', '--', '-5 度']);
});

const FOUND = {
  q: '王先生 報價 上個月',
  parsed: [
    { kind: 'entity', text: '王先生', label: '實體 王先生', value: '王大明' },
    { kind: 'type', text: '報價', label: '卡型 報價', value: '報價' },
    { kind: 'time', text: '上個月', label: '時間 9/1～9/30', value: ['2026-09-01', '2026-09-30'] },
  ],
  entities: [{ name: '王大明', type: '業主', why: '名稱' }],
  files: [
    { card: 'f-1a2b3c4d', title: '王大明報價 v2', type: '報價', date: '2026-09-12', entities: ['王大明'], open: { path: 'C:/data/報價.xlsx' }, card_path: '檔案索引/報價-1a2b3c4d.md', hit: 'title' },
    { card: 'f-5e6f7a8b', title: '線上報價單', type: '報價', date: '2026-09-02', entities: ['王大明'], open: { url: 'https://claude.ai/x' }, card_path: '檔案索引/線上-5e6f7a8b.md', hit: 'body' },
  ],
  total: 2,
  more: false,
};

test('搜尋結果：照這樣找的 chip、實體、檔、最後一列到對話問 Claude', async () => {
  const asked = [];
  const { view, calls } = makeView({ askClaude: (q) => asked.push(q) });
  view.plugin.runner.run = async (args) => {
    calls.push(args);
    return { code: 0, stdout: JSON.stringify(FOUND), stderr: '' };
  };
  await view.doSearch('王先生 報價 上個月');
  const dd = view.dropdownEl;
  assert.ok(dd.classList.contains('is-open'));
  assert.strictEqual(byClass(dd, 'wwh-chip').length, 3);
  assert.strictEqual(byClass(dd, 'wwh-dd-entity').length, 1);
  assert.strictEqual(byClass(dd, 'wwh-file').length, 2);
  assert.strictEqual(byClass(dd, 'wwh-icon-btn').length, 2, '每個檔列尾一個開檔案卡的小圖示');
  const ask = byClass(dd, 'wwh-dd-ask')[0];
  assert.match(ask.textContent, /到對話問 Claude/);
  ask.fire('click');
  assert.deepStrictEqual(asked, ['王先生 報價 上個月']);
  // 最近那一列在搜尋時藏起來
  assert.ok(view.recentEl.classList.contains('wwh-hidden'));
});

test('點掉一個「照這樣找」就把那段字拿掉重搜；拿光了就清掉結果', async () => {
  assert.strictEqual(lib.removeChipText('王先生 報價 上個月', '報價'), '王先生 上個月');
  assert.strictEqual(lib.removeChipText('王先生 報價 上個月', '王先生'), '報價 上個月');
  assert.strictEqual(lib.removeChipText('王先生報價', '報價'), '王先生');
  assert.strictEqual(lib.removeChipText('王先生', '王先生'), '');
  const { view, calls } = makeView();
  view.plugin.runner.run = async (args) => {
    calls.push(args);
    return { code: 0, stdout: JSON.stringify(FOUND), stderr: '' };
  };
  await view.doSearch('王先生 報價 上個月');
  const typeChip = byClass(view.dropdownEl, 'wwh-chip')[1];
  typeChip.fire('click');
  await new Promise((r) => setImmediate(r));
  assert.deepStrictEqual(calls[1], ['find', '王先生 上個月', '--json']);
  assert.strictEqual(view.inputEl.value, '王先生 上個月');
  // 只剩一段時點掉，就回到沒搜尋的樣子
  view.plugin.ui.search.q = '上個月';
  view.doSearchAfterChip('上個月', { text: '上個月' });
  assert.strictEqual(view.plugin.ui.search.active, false);
  assert.strictEqual(view.inputEl.value, '');
});

test('找不到：顯示沒有找到，還是有「到對話問 Claude」', async () => {
  const { view } = makeView();
  await view.doSearch('不存在的東西');
  assert.match(view.dropdownEl.textContent, /沒有找到/);
  assert.strictEqual(byClass(view.dropdownEl, 'wwh-dd-ask').length, 1);
});

test('kb find 失敗：顯示 kb 的句子', async () => {
  const { view } = makeView();
  view.plugin.runner.run = async () => ({ code: 3, stdout: '這個知識庫還沒有卡\n', stderr: '' });
  await view.doSearch('x');
  assert.match(view.dropdownEl.textContent, /這個知識庫還沒有卡/);
});

function openCtx(over) {
  const out = { toasts: [], paths: [], urls: [] };
  const ctx = Object.assign(
    {
      platform: 'win32',
      toast: (t) => out.toasts.push(t),
      openPath: async (p) => {
        out.paths.push(p);
        return '';
      },
      openUrl: (u) => out.urls.push(u),
    },
    over,
  );
  return { ctx, out };
}

test('點檔開原檔：shell.openPath，Windows 路徑換成反斜線', async () => {
  const { ctx, out } = openCtx();
  assert.strictEqual(await lib.openOriginal(ctx, { path: 'C:/data/報價.xlsx' }), true);
  assert.deepStrictEqual(out.paths, ['C:\\data\\報價.xlsx']);
});

test('link 條目開網址', async () => {
  const { ctx, out } = openCtx();
  await lib.openOriginal(ctx, { url: 'https://claude.ai/doc/1' });
  assert.deepStrictEqual(out.urls, ['https://claude.ai/doc/1']);
  assert.strictEqual(out.paths.length, 0);
});

test('網路路徑的原檔：toast 說開不了，不呼叫 openPath', async () => {
  const { ctx, out } = openCtx();
  const p = '\\\\nas\\share\\報價.xlsx';
  assert.strictEqual(lib.isNetworkPath(p), true);
  assert.strictEqual(lib.isNetworkPath('\\\\?\\C:\\long\\path.xlsx'), false);
  assert.strictEqual(lib.isNetworkPath('C:/data/a.xlsx'), false);
  assert.strictEqual(await lib.openOriginal(ctx, { path: p }), false);
  assert.strictEqual(out.paths.length, 0);
  assert.strictEqual(out.toasts[0], `這份在網路磁碟上，從這裡開不了；到檔案總管開：${p}`);
});

test('openPath 回錯誤字串、沒有原檔：toast', async () => {
  const bad = openCtx({ openPath: async () => '找不到檔案' });
  assert.strictEqual(await lib.openOriginal(bad.ctx, { path: 'C:/a.xlsx' }), false);
  assert.match(bad.out.toasts[0], /找不到檔案/);
  const none = openCtx();
  assert.strictEqual(await lib.openOriginal(none.ctx, null), false);
  assert.strictEqual(none.out.toasts.length, 1);
});

test('到對話問 Claude：把「幫我找：<字>」複製到剪貼簿，toast 已複製', async () => {
  const written = [];
  const toasts = [];
  await lib.copyAskClaude({ writeClipboard: async (t) => written.push(t), toast: (t) => toasts.push(t) }, '王先生 報價');
  assert.deepStrictEqual(written, ['幫我找：王先生 報價']);
  assert.deepStrictEqual(toasts, ['已複製，貼到 Claude 的對話裡']);
  const fail = [];
  const r = await lib.copyAskClaude({ writeClipboard: async () => { throw new Error('no'); }, toast: (t) => fail.push(t) }, 'x');
  assert.strictEqual(r, false);
  assert.match(fail[0], /幫我找：x/);
});

test('最近：記開過的卡編號，最多 30 筆、不重複、只存編號與時間', () => {
  let data = { opened: [] };
  for (let i = 0; i < 35; i++) data = lib.recordOpened(data, `f-${String(i).padStart(8, '0')}`, `2026-10-30T10:${String(i).padStart(2, '0')}:00`);
  assert.strictEqual(data.opened.length, 30);
  assert.strictEqual(data.opened[0].card, 'f-00000034');
  data = lib.recordOpened(data, 'f-00000010', '2026-10-30T12:00:00');
  assert.strictEqual(data.opened.length, 30);
  assert.strictEqual(data.opened[0].card, 'f-00000010');
  assert.strictEqual(data.opened.filter((o) => o.card === 'f-00000010').length, 1);
  for (const o of data.opened) assert.deepStrictEqual(Object.keys(o).sort(), ['at', 'card']);
  // 不是卡編號的不記
  assert.strictEqual(lib.recordOpened({ opened: [] }, 'C:/x/報價.xlsx').opened.length, 0);
  assert.strictEqual(lib.sanitizeData({ opened: [{ card: 'f-1a', at: 't', path: 'C:/secret' }, { card: '../x' }, 5], other: 1 }).opened.length, 1);
  assert.deepStrictEqual(Object.keys(lib.sanitizeData({ opened: [], extra: 1 })), ['opened']);
});

test('叫 kb home 帶 --opened 的卡編號', () => {
  assert.deepStrictEqual(lib.homeArgs([]), ['home', '--json']);
  assert.deepStrictEqual(lib.homeArgs(['f-1a2b3c4d', 'f-5e6f7a8b']), ['home', '--json', '--opened', 'f-1a2b3c4d,f-5e6f7a8b']);
  assert.deepStrictEqual(lib.openedIds({ opened: [{ card: 'f-aa', at: 't' }, { card: 'f-bb', at: 't' }] }), ['f-aa', 'f-bb']);
});

test('最近那一列：沒打字時顯示，來自 kb home 的 recent', () => {
  const home = lib.normalizeHome({ recent: [{ card: 'f-1a2b3c4d', title: '報價', why: 'opened', open: { path: 'C:/a.xlsx' }, card_path: '檔案索引/a.md' }, { card: 'f-5e', title: '新來的', why: 'added', open: { path: 'C:/b.docx' } }] });
  const { view } = makeView({ home });
  view.render();
  assert.strictEqual(byClass(view.recentEl, 'wwh-recent-item').length, 2);
  assert.strictEqual(byTag(view.recentEl, 'button').length, 1, '只有有卡路徑的有開卡小圖示');
  assert.ok(!view.recentEl.classList.contains('wwh-hidden'));
});

test('搜尋：先送的慢查詢比後送的晚回來，不會蓋掉後面的結果（請求編號，裁定 14）', async () => {
  const waits = {};
  const { view, plugin } = makeView();
  plugin.runner.run = (args) =>
    new Promise((resolve) => {
      waits[args[1]] = () => resolve({ code: 0, stdout: JSON.stringify({ q: args[1], parsed: [], entities: [], files: [], total: 0, more: false }), stderr: '' });
    });
  const slow = view.doSearch('慢的');
  const fast = view.doSearch('快的');
  waits['快的']();
  await fast;
  assert.strictEqual(plugin.ui.search.q, '快的');
  assert.strictEqual(plugin.ui.search.result.q, '快的');
  assert.strictEqual(plugin.ui.search.loading, false);
  waits['慢的']();
  await slow;
  assert.strictEqual(plugin.ui.search.q, '快的', '舊的回來不改搜尋字');
  assert.strictEqual(plugin.ui.search.result.q, '快的', '舊的回來不蓋結果');
});

test('搜尋：清掉之後才回來的舊結果丟掉', async () => {
  let release;
  const { view, plugin } = makeView();
  plugin.runner.run = () =>
    new Promise((resolve) => {
      release = () => resolve({ code: 0, stdout: JSON.stringify({ q: 'x', parsed: [], entities: [], files: [], total: 0, more: false }), stderr: '' });
    });
  const pending = view.doSearch('x');
  view.clearSearch();
  release();
  await pending;
  assert.strictEqual(plugin.ui.search.active, false);
  assert.strictEqual(plugin.ui.search.result, null);
});

test('時間軸：kb home 還沒回來（home 是空的）時不畫「全部展開／收起」，按不到就不會出錯', () => {
  const { view } = makeView({ home: null });
  const labels = byClass(view.timelineEl, 'wwh-small-btn').map((b) => b.textContent);
  assert.ok(!labels.includes('全部展開'), labels.join());
  assert.ok(!labels.includes('全部收起'), labels.join());
  assert.doesNotThrow(() => view.setAllRows(false));
});

test('時間軸：有資料時照常有「全部展開／收起」', () => {
  const { view } = makeView();
  const labels = byClass(view.timelineEl, 'wwh-small-btn').map((b) => b.textContent);
  assert.ok(labels.includes('全部展開') && labels.includes('全部收起'), labels.join());
});
