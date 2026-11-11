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

// ---- 裁定 41：出處〔f-…〕顯示成小檔案圖示 ----

function makeRefPlugin() {
  const files = [{ path: '檔案索引/報價-1a2b3c4d.md' }, { path: '檔案索引/合約-5e6f7a8b.md' }];
  const fms = { '檔案索引/報價-1a2b3c4d.md': { 編號: 'f-1a2b3c4d', 標題: '信義王報價' }, '檔案索引/合約-5e6f7a8b.md': { 編號: 'f-5e6f7a8b' } };
  const app = {
    vault: { adapter: { getBasePath: () => '/v' }, getMarkdownFiles: () => files },
    metadataCache: { getFileCache: (f) => ({ frontmatter: fms[f.path] }) },
  };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  const opened = [];
  plugin.openPathInVault = (r) => opened.push(r);
  return { plugin, opened };
}

test('出處（裁定 41）：小檔案圖示——file-text、滑過提示那張卡的標題（沒標題用檔名），點了開那張卡；存的字不變', () => {
  const { plugin, opened } = makeRefPlugin();
  assert.strictEqual(plugin.cardTitleOf('f-1a2b3c4d'), '信義王報價');
  const a = plugin.cardRefIcon('f-1a2b3c4d', plugin.cardPathOf('f-1a2b3c4d'));
  assert.ok(a.classList.contains('wwh-cardref'));
  assert.strictEqual(a.attrs.title, '信義王報價');
  assert.strictEqual(a.attrs['aria-label'], '出處：信義王報價');
  assert.strictEqual(byTag(a, 'svg').length, 1, '小圖示');
  assert.strictEqual(a.textContent, '', '畫面上不寫〔f-…〕');
  let stopped = 0;
  a.fire('click', { stopPropagation: () => stopped++ });
  assert.deepStrictEqual(opened, ['檔案索引/報價-1a2b3c4d.md']);
  const b = plugin.cardRefIcon('f-5e6f7a8b', plugin.cardPathOf('f-5e6f7a8b'));
  assert.strictEqual(b.attrs.title, '合約-5e6f7a8b', '沒標題用檔名');
  assert.strictEqual(plugin.cardTitleOf('f-ffffffff'), null);
  assert.ok(lib.icon('file-text', 14), 'file-text 圖示有定義');
  assert.deepStrictEqual(lib.splitCardRefs('水電〔f-1a2b3c4d〕'), [{ text: '水電' }, { ref: 'f-1a2b3c4d' }], '檔案裡存的字照舊是〔f-…〕');
});

test('出處（裁定 41）：閱讀模式後處理——找得到卡換成圖示、找不到卡照舊顯示原字、連結與程式碼裡不動', () => {
  const { plugin } = makeRefPlugin();
  const { FakeEl, FakeText } = require('./helpers/fakedom');
  const para = new FakeEl('p');
  const t = new FakeText('水電完工〔f-1a2b3c4d〕，另見〔f-ffffffff〕');
  para.appendChild(t);
  const code = new FakeEl('code');
  const ct = new FakeText('〔f-1a2b3c4d〕');
  code.appendChild(ct);
  const root = new FakeEl('div');
  root.appendChild(para);
  root.appendChild(code);
  para.replaceChild = function (frag, node) {
    const i = this.children.indexOf(node);
    this.children.splice(i, 1, ...frag.children);
    for (const k of frag.children) k.parentNode = this;
  };
  code.closest = () => code;
  t.parentNode.closest = () => null;
  root.ownerDocument = { createTreeWalker: () => { const list = [t, ct]; return { nextNode: () => list.shift() || null }; }, createDocumentFragment: () => globalThis.document.createDocumentFragment(), createTextNode: (x) => globalThis.document.createTextNode(x), createElement: (x) => globalThis.document.createElement(x) };
  plugin.linkifyCardRefs(root);
  const kinds = para.children.map((c) => (c.nodeType === 3 ? c.nodeValue : c.className));
  assert.deepStrictEqual(kinds, ['水電完工', 'wwh-cardref', '，另見', '〔f-ffffffff〕'], '找不到那張卡的照舊顯示原字');
  assert.strictEqual(code.textContent, '〔f-1a2b3c4d〕', '程式碼裡不動');
});

test('出處（裁定 41）：編輯模式——cardRefRanges 找位置；裝飾把找得到的〔f-…〕換成小圖示，游標進到那段、找不到卡、原始碼模式顯示原字', () => {
  assert.deepStrictEqual(lib.cardRefRanges('a〔f-1a2b3c4d〕b〔s-11223344〕〔f-5e6f7a8b〕', 10), [
    { from: 11, to: 23, ref: 'f-1a2b3c4d' },
    { from: 36, to: 48, ref: 'f-5e6f7a8b' },
  ]);
  assert.deepStrictEqual(lib.cardRefRanges('沒有', 0), []);
  const Module = require('node:module');
  const fakeView = {
    WidgetType: class {},
    Decoration: { none: [], replace: (o) => ({ range: (from, to) => ({ from, to, widget: o.widget }) }), set: (arr) => arr },
    ViewPlugin: { fromClass: (cls, spec) => ({ cls, spec }) },
  };
  const orig = Module._load;
  Module._load = function (request, parent, isMain) {
    if (request === '@codemirror/view') return fakeView;
    if (request === '@codemirror/state') return {};
    return orig.call(this, request, parent, isMain);
  };
  let ext;
  const { plugin } = makeRefPlugin();
  try {
    ext = plugin.cardRefExtension();
  } finally {
    Module._load = orig;
  }
  const text = '水電〔f-1a2b3c4d〕完工〔f-ffffffff〕';
  const viewOf2 = (cursor, live) => ({
    state: {
      doc: { sliceString: (a, b) => text.slice(a, b) },
      selection: { ranges: [{ from: cursor, to: cursor }] },
      field: () => live,
    },
    visibleRanges: [{ from: 0, to: text.length }],
  });
  const decos = (v) => new ext.cls(v).decorations;
  const got = decos(viewOf2(0, true));
  assert.strictEqual(got.length, 1, '找不到卡的那個不換');
  assert.deepStrictEqual([got[0].from, got[0].to], [2, 14]);
  const dom = got[0].widget.toDOM();
  assert.ok(dom.classList.contains('wwh-cardref') && byTag(dom, 'svg').length === 1);
  assert.ok(got[0].widget.eq(new (got[0].widget.constructor)('f-1a2b3c4d', '檔案索引/報價-1a2b3c4d.md')));
  // 裁定 43：編輯模式 mousedown 在圖示上就開卡、不動游標（編輯器不接這個事件）
  assert.strictEqual(got[0].widget.ignoreEvent(), true, '編輯器不處理圖示上的事件');
  const opened43 = [];
  plugin.openPathInVault = (r) => opened43.push(r);
  const w43 = new (got[0].widget.constructor)('f-1a2b3c4d', '檔案索引/報價-1a2b3c4d.md');
  const icon43 = w43.toDOM();
  let prevented = 0;
  let stopped = 0;
  icon43.fire('mousedown', { button: 0, preventDefault: () => prevented++, stopPropagation: () => stopped++ });
  assert.deepStrictEqual(opened43, ['檔案索引/報價-1a2b3c4d.md'], 'mousedown 就開卡');
  assert.ok(prevented >= 1 && stopped >= 1, 'preventDefault 擋掉游標進去');
  icon43.fire('click', { preventDefault: () => prevented++, stopPropagation: () => stopped++ });
  assert.strictEqual(opened43.length, 1, '後面的 click 不再開第二次');
  icon43.fire('mousedown', { button: 2, preventDefault: () => {}, stopPropagation: () => {} });
  assert.strictEqual(opened43.length, 1, '右鍵不開');
  assert.strictEqual(decos(viewOf2(5, true)).length, 0, '游標進到那段顯示原字照常改');
  assert.strictEqual(decos(viewOf2(0, false)).length, 0, '原始碼模式不改');
  assert.strictEqual(typeof ext.spec.decorations, 'function');
  // 讀不到 CodeMirror 就不加（不能讓外掛載入失敗）
  assert.deepStrictEqual(plugin.cardRefExtension(), []);
});

test('出處（裁定 41）：小圖示的樣式——跟字同高、淡色', () => {
  const css = require('node:fs').readFileSync(require('node:path').join(__dirname, '..', '..', 'obsidian', 'styles.css'), 'utf8');
  assert.match(css, /\.wwh-cardref \{[^}]*color: var\(--text-faint\)/);
  assert.match(css, /\.wwh-cardref \.wwh-ico \{[^}]*height: 1em/);
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

test('要你確認的：有 argv 的照做（argv 是 null 的見裁定 34 那幾個測試）', async () => {
  const { plugin, calls } = makeActionPlugin();
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

test('要你確認的（裁定 37）：對話圖示複製「關於「題目」：」並提示，不叫 kb；argv 是 null 的答案首頁不列，真的被叫到也不跑', async () => {
  const { plugin, calls, toasts } = makeActionPlugin();
  const clip = [];
  plugin.clipCtx = () => ({ toast: (t) => plugin.toast(t), writeClipboard: async (t) => clip.push(t) });
  await plugin.copyAsk({ text: '「王先生」是新的名字嗎？' });
  assert.deepStrictEqual(clip, ['關於「「王先生」是新的名字嗎？」：']);
  assert.strictEqual(toasts[0].t, '已複製，貼到對話跟 Claude 說');
  assert.strictEqual(calls.length, 0);
  assert.strictEqual(await plugin.chooseResult({ text: '名字？' }, { label: '照你改的做', argv: null, fill: null }), null);
  assert.strictEqual(calls.length, 0, 'argv 是 null 不叫 kb');
});

test('最下面一行（裁定 39）：copyReview 複製「幫我看一下待處理」並提示，不叫 kb', async () => {
  const { plugin, calls, toasts } = makeActionPlugin();
  const clip = [];
  plugin.clipCtx = () => ({ toast: (t) => plugin.toast(t), writeClipboard: async (t) => clip.push(t) });
  await plugin.copyReview();
  assert.deepStrictEqual(clip, ['幫我看一下待處理']);
  assert.strictEqual(toasts[0].t, '已複製，貼到對話跟 Claude 說');
  assert.strictEqual(calls.length, 0);
});

test('要你確認的（裁定 34）：複製不了就把那句話顯示出來讓她自己複製', async () => {
  const toasts = [];
  const ok = await lib.copyForChat({ toast: (t) => toasts.push(t), writeClipboard: async () => { throw new Error('no'); } }, '那句話');
  assert.strictEqual(ok, false);
  assert.match(toasts[0], /請自己複製：那句話$/);
});

test('要你確認的（裁定 34）：「先放著」的 argv 照跑；要填的把填的值換進 argv', async () => {
  const { plugin, calls } = makeActionPlugin();
  await plugin.chooseResult({}, { label: '先放著', argv: ['asks', 'set-aside', 'inbox:x@1'], fill: null });
  assert.deepStrictEqual(calls[0], ['asks', 'set-aside', 'inbox:x@1']);
  await plugin.chooseResult({}, { label: '還沒，改到某天', argv: ['agenda', 'edit', 'a-1', '--date', '{新日期}'], fill: { name: '新日期', rule: 'YYYY-MM-DD' } }, '2026-11-20');
  assert.deepStrictEqual(calls[1], ['agenda', 'edit', 'a-1', '--date', '2026-11-20']);
});

function makeOpenPlugin(reply) {
  const calls = [];
  const toasts = [];
  const opened = [];
  const orig = [];
  const app = { vault: { adapter: { getBasePath: () => '/v' } }, workspace: { getLeavesOfType: () => [], openLinkText: (p) => opened.push(p) } };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.data = {};
  plugin.runner = { run: async (args) => { calls.push(args); return { code: 0, stdout: JSON.stringify(reply), stderr: '' }; } };
  plugin.toast = (t) => toasts.push(t);
  plugin.recordOpened = async () => {};
  plugin.openCtx = () => ({ platform: 'linux', toast: (t) => toasts.push(t), openPath: async (p) => { orig.push(p); return ''; }, openUrl: (u) => orig.push(u) });
  return { plugin, calls, toasts, opened, orig };
}

test('開原檔連結（D-328）：協定處理器叫 kb lookup --id 查位置再開原檔', async () => {
  const { plugin, calls, orig, opened } = makeOpenPlugin({ id: 'f-1', open: { path: '/data/報價.docx' }, card_path: '檔案索引/客戶/報價-1.md' });
  assert.strictEqual(await plugin.openById('f-1'), true);
  assert.deepStrictEqual(calls[0], ['lookup', '--id', 'f-1', '--json']);
  assert.deepStrictEqual(orig, ['/data/報價.docx']);
  assert.deepStrictEqual(opened, []);
});

test('開原檔連結（D-328）：這台找不到原檔，說一句、退一步開卡', async () => {
  const { plugin, toasts, orig, opened } = makeOpenPlugin({ id: 'f-1', open: null, card_path: '檔案索引/客戶/報價-1.md' });
  assert.strictEqual(await plugin.openById('f-1'), false);
  assert.deepStrictEqual(toasts, ['這份沒有原檔可以開']);
  assert.deepStrictEqual(orig, []);
  assert.deepStrictEqual(opened, ['檔案索引/客戶/報價-1']);
});

test('開原檔連結（D-328）：onload 登記 wiki-with-willy-open 協定', () => {
  const { plugin } = makeOpenPlugin({});
  plugin.registerObsidianProtocolHandler('wiki-with-willy-open', () => {});
  assert.ok(plugin.protocols['wiki-with-willy-open']);
  assert.strictEqual(lib.OPEN_ACTION, 'wiki-with-willy-open');
});

// ---- 多人共用 3：看 .git 的 HEAD 變動，2 秒去抖後叫 kb refresh ----

test('gitRefreshNotice：有衝突或 rebase 到一半才提示', () => {
  assert.strictEqual(lib.gitRefreshNotice({ conflicts: [], rebase: false }), null);
  assert.strictEqual(lib.gitRefreshNotice(null), null);
  assert.match(lib.gitRefreshNotice({ conflicts: [{ path: 'a' }], rebase: false }), /同步有衝突/);
  assert.match(lib.gitRefreshNotice({ conflicts: [], rebase: true }), /同步有衝突/);
  assert.strictEqual(lib.isGitWatchFile('HEAD'), true);
  assert.strictEqual(lib.isGitWatchFile('FETCH_HEAD'), true);
  assert.strictEqual(lib.isGitWatchFile('index'), false);
  assert.strictEqual(lib.GIT_DEBOUNCE_MS, 2000);
});

test('.git/HEAD 改了（模擬）：2 秒內叫一次 kb refresh、再刷新首頁；回 conflicts 時首頁有提示', async () => {
  const os = require('node:os');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wwh-git-'));
  fs.mkdirSync(path.join(root, '.git'));
  try {
    const plugin = new env.Plugin({ vault: { adapter: { getBasePath: () => root } }, metadataCache: {} }, { id: 'wiki-with-willy', version: '0.28.0' });
    plugin.vaultPath = root;
    const calls = [];
    let refreshed = 0;
    plugin.kb = async (args) => {
      calls.push(args.join(' '));
      return { code: 0, stdout: JSON.stringify({ conflicts: [{ path: '卡.md', kind: 'card' }], rebase: false }), stderr: '' };
    };
    plugin.scheduleRefresh = () => {
      refreshed += 1;
    };
    plugin.startGitWatch();
    fs.writeFileSync(path.join(root, '.git', 'index'), 'x'); // 不是看的檔，不算
    fs.writeFileSync(path.join(root, '.git', 'HEAD'), 'a');
    fs.writeFileSync(path.join(root, '.git', 'HEAD'), 'b');
    await new Promise((r) => setTimeout(r, 2600));
    assert.deepStrictEqual(calls, ['refresh --json']);
    assert.strictEqual(refreshed, 1);
    assert.match(plugin.gitNotice, /同步有衝突/);
    plugin.gitWatcher.close();
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
