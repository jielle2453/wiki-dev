'use strict';
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const path = require('node:path');
const { loadMain, MAIN } = require('./helpers/env');
const { byClass, byTag } = require('./helpers/fakedom');

const env = loadMain();
const lib = env.lib;
test.after(() => env.restore());

const ROOT = path.join(__dirname, '..', '..');
const tick = () => new Promise((r) => setImmediate(r));

test('manifest.json：id、桌面版限定、版號跟 plugin.json 一樣', () => {
  const m = JSON.parse(fs.readFileSync(path.join(ROOT, 'obsidian', 'manifest.json'), 'utf8'));
  const p = JSON.parse(fs.readFileSync(path.join(ROOT, '.claude-plugin', 'plugin.json'), 'utf8'));
  assert.strictEqual(m.id, 'wiki-with-willy');
  assert.strictEqual(m.isDesktopOnly, true);
  assert.strictEqual(m.minAppVersion, '1.5.0');
  assert.strictEqual(m.version, p.version);
  assert.ok(m.name && m.description);
});

test('styles.css：藏「檔案索引」夾的規則在，顏色用 Obsidian 的變數', () => {
  const css = fs.readFileSync(path.join(ROOT, 'obsidian', 'styles.css'), 'utf8');
  assert.match(css, /\.nav-folder-title\[data-path="檔案索引"\]/);
  assert.match(css, /\.nav-file-title\[data-path="CLAUDE\.md"\]\s*\{\s*display: none;/, '知識庫根的 CLAUDE.md 也藏（D-266）');
  assert.match(css, /var\(--background-primary\)/);
  assert.match(css, /var\(--text-normal\)/);
});

test('三個檔：UTF-8 無 BOM、LF、檔尾一個換行、不含開發機路徑', () => {
  const devA = 'C:' + '\\' + 'Users';
  const devB = 'C:' + '/Users';
  for (const f of ['manifest.json', 'main.js', 'styles.css']) {
    const raw = fs.readFileSync(path.join(ROOT, 'obsidian', f));
    assert.notDeepStrictEqual([...raw.subarray(0, 3)], [0xef, 0xbb, 0xbf], `${f} 有 BOM`);
    const text = raw.toString('utf8');
    assert.ok(!text.includes('\r'), `${f} 含 CR`);
    assert.ok(text.endsWith('\n') && !text.endsWith('\n\n'), `${f} 檔尾換行不對`);
    assert.ok(!text.includes(devA) && !text.includes(devB), `${f} 含開發機路徑`);
  }
});

test('main.js 沒有寫死 plugin 的路徑，也不把路徑寫進設定', () => {
  const text = fs.readFileSync(MAIN, 'utf8');
  assert.ok(!/cache[\\/]/.test(text.replace(/\/\/.*$/gm, '')), '不該寫死 plugin cache 路徑');
  assert.ok(text.includes('installed_plugins.json'));
  assert.ok(!/saveData\([^)]*kbPath/.test(text));
});

test('〔f-…〕拆成文字與出處', () => {
  assert.deepStrictEqual(lib.splitCardRefs('水電完工〔f-1a2b3c4d〕，後續〔s-11223344〕〔f-5e6f7a8b〕'), [
    { text: '水電完工' },
    { ref: 'f-1a2b3c4d' },
    { text: '，後續〔s-11223344〕' },
    { ref: 'f-5e6f7a8b' },
  ]);
  assert.deepStrictEqual(lib.splitCardRefs('沒有出處'), [{ text: '沒有出處' }]);
  assert.deepStrictEqual(lib.splitCardRefs(''), []);
});

test('出處編號對到檔案索引裡的卡（讀檔頭的編號）', () => {
  const files = [{ path: '檔案索引/報價-1a2b3c4d.md' }, { path: '01 案子/信義王/信義王.md' }];
  const app = {
    vault: { adapter: { getBasePath: () => '/v' }, getMarkdownFiles: () => files },
    metadataCache: { getFileCache: (f) => (f.path.startsWith('檔案索引/') ? { frontmatter: { 編號: 'f-1a2b3c4d' } } : { frontmatter: { 編號: 'e-xx' } }) },
  };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  assert.strictEqual(plugin.cardPathOf('f-1a2b3c4d'), '檔案索引/報價-1a2b3c4d.md');
  assert.strictEqual(plugin.cardPathOf('f-ffffffff'), null);
});

function makeDrawerPlugin(lookups) {
  const calls = [];
  const app = { vault: { adapter: { getBasePath: () => '/v' } }, workspace: { getLeavesOfType: () => [] } };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.ui = lib.defaultUi();
  plugin.home = lib.normalizeHome({});
  plugin.runner = {
    run: async (args) => {
      calls.push(args);
      const name = args[1];
      return { code: 0, stdout: JSON.stringify(lookups[name] || { query: name, entity: null, mentions: [] }), stderr: '' };
    },
  };
  return { plugin, calls };
}

const WANG = {
  query: '王先生',
  entity: { name: '王大明', type: '業主', category: '人', self: false, aliases: ['王先生', '大明'], progress: null },
  synthesis: '02 業主/王大明/王大明.md',
  tags: [{ field: '階段', words: ['簽約'] }],
  cards: [{ id: 'f-1a2b3c4d', title: '報價 v2', card_type: '報價', date: '2026-09-12', path: '檔案索引/報價-1a2b3c4d.md', stale: false, redo: false, ruled_out: false, entities: ['王大明'] }],
  statements: [{ date: '2026-10-01', text: '他說下週簽約' }],
  rulings: [],
  findings: [],
  agenda: [{ id: 'a-1', kind: '到期', date: '2026-11-05', text: '交圖', status: 'open' }],
};

test('實體總覽：叫 kb lookup（帶 --json），抽屜畫出別名、標籤、卡、日程；← 回上一頁', async () => {
  const { plugin, calls } = makeDrawerPlugin({ 王先生: WANG, 王大明: WANG, 信義王: { query: '信義王', entity: { name: '信義王', type: '案子', aliases: [], progress: 'active' }, cards: [], agenda: [] } });
  plugin.openEntity('王先生');
  await tick();
  await tick();
  assert.deepStrictEqual(calls[0], ['lookup', '王先生', '--json']);
  assert.deepStrictEqual(plugin.ui.drawer.stack, ['王大明'], '別名查到現在的名字');
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  const d = view.drawerEl;
  assert.ok(d.classList.contains('is-open'));
  assert.match(d.textContent, /← 回上一頁/);
  assert.match(d.textContent, /王大明/);
  assert.match(d.textContent, /也叫：王先生、大明/);
  assert.strictEqual(byTag(d, 'button').filter((b) => b.textContent !== '← 回上一頁' && b.textContent !== '✕').length, 0, '小預覽只看：沒有改名、別名、標籤、結案的按鈕（D-266）');
  assert.match(d.textContent, /階段/);
  assert.match(d.textContent, /報價 v2/);
  assert.match(d.textContent, /交圖/);
  assert.match(d.textContent, /他說下週簽約/);
  assert.ok(byTag(d, 'a').some((a) => a.textContent === '開綜合卡'));

  // 再點進另一個實體，← 回到前一個；再按一次關掉
  plugin.openEntity('信義王');
  await tick();
  await tick();
  assert.deepStrictEqual(plugin.ui.drawer.stack, ['王大明', '信義王']);
  plugin.drawerBack();
  await tick();
  await tick();
  assert.deepStrictEqual(plugin.ui.drawer.stack, ['王大明']);
  assert.strictEqual(plugin.ui.drawer.data.entity.name, '王大明');
  plugin.drawerBack();
  assert.strictEqual(plugin.ui.drawer.open, false);
});

test('實體總覽：沒登記的名字列出提到它的卡', async () => {
  const { plugin } = makeDrawerPlugin({ 路人: { query: '路人', entity: null, mentions: [{ title: '會議紀錄', where: '檔案索引/x.md' }], mentions_total: 1 } });
  plugin.openEntity('路人');
  await tick();
  await tick();
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  assert.match(view.drawerEl.textContent, /沒有登記這個名稱/);
  assert.match(view.drawerEl.textContent, /會議紀錄/);
});

function makeActionPlugin() {
  const calls = [];
  const toasts = [];
  const app = { vault: { adapter: { getBasePath: () => '/v' } }, workspace: { getLeavesOfType: () => [] } };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.ui = lib.defaultUi();
  plugin.home = lib.normalizeHome({ today: '2026-10-30', timeline: { rows: [{ key: 'e-1', label: '信義王', marks: [] }] } });
  plugin.runner = {
    run: async (args) => {
      calls.push(args);
      return { code: 0, stdout: '好', stderr: '' };
    },
  };
  plugin.toast = (t, o) => toasts.push({ t, undo: o && o.undo });
  plugin.scheduleRefresh = () => {};
  return { plugin, calls, toasts };
}

test('要你確認的：argv 是 null 的結果提示到對話跟 Claude 說；有 argv 的照做', async () => {
  const { plugin, calls, toasts } = makeActionPlugin();
  await plugin.chooseResult({}, { label: '跟 Claude 說', argv: null });
  assert.strictEqual(toasts[0].t, '到對話跟 Claude 說');
  assert.strictEqual(calls.length, 0);
  await plugin.chooseResult({}, { label: '是，合併', argv: ['entity', 'merge', '王先生', '--into', '王大明'], fill: null });
  assert.deepStrictEqual(calls[0], ['entity', 'merge', '王先生', '--into', '王大明']);
});

test('首頁按鈕接到動作：打勾的 checkbox 叫 kb agenda done', async () => {
  const { plugin, calls } = makeActionPlugin();
  plugin.home = lib.normalizeHome({ today: '2026-10-30', todo: { today: [{ id: 'a-9', kind: 'reminder', end: '2026-10-30', text: '確認窗簾款式', entities: ['信義王'] }] } });
  plugin.openEntity = () => {};
  plugin.itemMenu = () => {};
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  const box = byClass(view.root, 'wwh-check')[0];
  box.fire('click');
  await tick();
  assert.deepStrictEqual(calls[0], ['agenda', 'done', 'a-9']);
  assert.ok(byClass(view.root, 'wwh-todo')[0].classList.contains('is-done'));
});

test('其他要處理的：只列出來，沒有按鈕（D-266 拿掉「不用管」）', () => {
  const { plugin } = makeActionPlugin();
  plugin.home = lib.normalizeHome({ others: [{ id: 'p-3', kind: 'missing_file', text: '有一份檔不見了', dismiss: true }, { id: 'p-4', text: '不能不管', dismiss: false }] });
  plugin.ui.othersOpen = true;
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  const rows = byClass(view.root, 'wwh-other');
  assert.strictEqual(rows.length, 2);
  for (const r of rows) assert.strictEqual(byTag(r, 'button').length, 0);
});

test('日程.md 的哪一行：先找文字加日期都有的，再找文字，找不到回頁頂', () => {
  const page = ['# 日程', '## 逾期', '- 2026-10-28（週三）提醒 看工地', '## 今天', '- 2026-10-30（週五）提醒 看工地', '- 2026-10-30（週五）到期 訂窗簾'].join('\n');
  assert.strictEqual(lib.findAgendaLine(page, { text: '訂窗簾', end: '2026-10-30' }), 5);
  assert.strictEqual(lib.findAgendaLine(page, { text: '看工地', end: '2026-10-30' }), 4, '同樣的字看日期挑');
  assert.strictEqual(lib.findAgendaLine(page, { text: '看工地', end: '2026-12-01' }), 2, '日期對不上就用第一個有字的');
  assert.strictEqual(lib.findAgendaLine(page, { text: '不在頁上', end: '2026-10-30' }), 0);
  assert.strictEqual(lib.findAgendaLine('', { text: 'x' }), 0);
  assert.strictEqual(lib.findAgendaLine(page, {}), 0);
});

test('點日程那件：開日程.md，游標跳到那一行', async () => {
  const opened = [];
  const cursor = [];
  const editor = { setCursor: (pos) => cursor.push(pos), scrollIntoView: () => {} };
  const app = {
    vault: { adapter: { getBasePath: () => '/v', read: async (rel) => (rel === '系統/日程.md' ? '# 日程\n- 2026-10-30（週五）到期 訂窗簾\n' : '') } },
    workspace: { openLinkText: async (link) => opened.push(link), getActiveViewOfType: () => ({ editor }), getLeavesOfType: () => [] },
  };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  await plugin.openAgendaLine({ id: 'a-1', text: '訂窗簾', end: '2026-10-30' });
  assert.deepStrictEqual(opened, ['系統/日程']);
  assert.deepStrictEqual(cursor, [{ line: 1, ch: 0 }]);
});

test('點案子名稱：開它的綜合卡；還沒有綜合卡就開旁邊的小預覽', async () => {
  const { plugin, calls } = makeDrawerPlugin({ 信義王: { query: '信義王', entity: { name: '信義王', type: '案子' }, synthesis: '01 案子/信義王/信義王.md' }, 新案: { query: '新案', entity: { name: '新案', type: '案子' }, synthesis: null } });
  const opened = [];
  plugin.openPathInVault = (rel) => opened.push(rel);
  await plugin.openSynthesis('信義王');
  assert.deepStrictEqual(calls[0], ['lookup', '信義王', '--json']);
  assert.deepStrictEqual(opened, ['01 案子/信義王/信義王.md']);
  plugin.openEntity = (n) => opened.push('drawer:' + n);
  await plugin.openSynthesis('新案');
  assert.strictEqual(opened[1], 'drawer:新案');
});

test('表單：必填空著不送出，填了才算數；Enter 送出；關掉 = null', async () => {
  const modal = (opts) => {
    let result;
    const m = new lib.FormModal({}, opts, (v) => {
      result = v;
    });
    m.open();
    return { m, get: () => result };
  };
  const a = modal({ title: 't', fields: [{ key: 'name', label: '名字', type: 'text', required: true }] });
  a.m.submit();
  assert.strictEqual(a.get(), undefined);
  a.m.inputs.name.value = '  王大明 ';
  a.m.inputs.name.fire('keydown', { key: 'Enter', isComposing: true });
  assert.strictEqual(a.get(), undefined, '選字中的 Enter 不送出');
  a.m.inputs.name.fire('keydown', { key: 'Enter' });
  assert.deepStrictEqual(a.get(), { name: '王大明' });

  const confirmOnly = modal({ title: '確認', lines: ['會搬夾'] });
  assert.match(confirmOnly.m.contentEl.textContent, /會搬夾/);
  confirmOnly.m.submit();
  assert.deepStrictEqual(confirmOnly.get(), {});

  const closed = modal({ title: 'x', fields: [{ key: 'v', label: 'v', type: 'text' }] });
  closed.m.close();
  assert.strictEqual(closed.get(), null);
});

test('home 資料缺欄位也畫得出來（保守）', () => {
  const home = lib.normalizeHome({});
  assert.deepStrictEqual(home.todo, { overdue: [], today: [], week: [] });
  assert.deepStrictEqual(home.confirm, []);
  const plugin = { runner: {}, home, ui: lib.defaultUi(), loadedVersion: '0.28.0' };
  const view = new lib.HomeView({}, plugin);
  view.build();
  assert.doesNotThrow(() => view.render());
  assert.doesNotThrow(() => view.setMode('month'));
});

test('日期顯示：11/5（週四）10:00', () => {
  assert.strictEqual(lib.formatWhen({ end: '2026-11-05', time: '10:00' }), '11/5（週四） 10:00');
  assert.strictEqual(lib.formatWhen({ date: '2026-10-30' }), '10/30（週五）');
  assert.strictEqual(lib.formatWhen({}), '');
});
