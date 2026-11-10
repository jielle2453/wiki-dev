'use strict';
/* 綜合卡底下外掛畫的「日程」（D-340；#65 拿掉記帳：帳頁、首頁的帳、庫存不足、公司還欠你都不畫，舊版 kb 給了也不壞）。 */
const test = require('node:test');
const assert = require('node:assert');
const { loadMain } = require('./helpers/env');
const { FakeEl, byClass, byText } = require('./helpers/fakedom');

const env = loadMain();
const lib = env.lib;
test.after(() => env.restore());

const tick = () => new Promise((r) => setImmediate(r));

test('帳頁與年頁不是受管頁（#65）；money.json 變了不刷新；舊版 kb 的 MONEY_PAGE 不再匯出', () => {
  assert.ok(!lib.isManagedPage('系統/帳.md'));
  assert.ok(!lib.isManagedPage('系統\\帳\\2026.md'));
  assert.ok(lib.isManagedPage('系統/日程.md'));
  assert.ok(!lib.WATCH_FILES.includes('money.json'));
  assert.strictEqual(lib.MONEY_PAGE, undefined);
});

test('首頁資料：舊版 kb 給 stock、owed、links 也不畫、不壞（#65）', () => {
  const home = lib.normalizeHome({ todo: { stock: [{ entity: '精華液' }], owed: [{ id: 'm-1' }] }, links: { money: '系統/帳.md' } });
  assert.deepStrictEqual(Object.keys(home.todo).sort(), ['overdue', 'today', 'week']);
  assert.strictEqual(home.links, undefined);
  assert.deepStrictEqual(lib.todoGroups(home).map((g) => g.key), ['overdue', 'today', 'week']);
  assert.deepStrictEqual(lib.todoGroups(lib.normalizeHome({})).map((g) => g.key), ['overdue', 'today', 'week']);
});

test('找頁上的那一行：整行一樣的先，再找包含的，找不到回頁頂', () => {
  const page = ['# 日程', '## 已經過了', '- 11/20（五）交件 [[a|信義王]] 第二期　已過 3 天', '> - 10/30（五）開會 李小姐'].join('\n');
  assert.strictEqual(lib.findPageLine(page, '- 11/20（五）交件 [[a|信義王]] 第二期　已過 3 天'), 2);
  assert.strictEqual(lib.findPageLine(page, '> - 10/30（五）開會 李小姐'), 3);
  assert.strictEqual(lib.findPageLine(page, '- 11/20（五）交件 [[a|信義王]] 第二期'), 2, '過了幾天字變了也找得到');
  assert.strictEqual(lib.findPageLine(page, '不在頁上'), 0);
});

const PANEL = {
  entity: '李小姐',
  type: '顧客',
  agenda: [{ id: 'a-1', date: '2026-11-05', kind: '會議', text: '見李小姐', late: false, line: '11/5（四）會議：見李小姐', page: '系統/日程.md', match: '- 2026-11-05（週四）會議 見李小姐' }],
};

function makeCardPlugin(handler) {
  const calls = [];
  const opened = [];
  const errors = [];
  const toasts = [];
  // 照 Obsidian 1.15 的 DOM：閱讀模式 .markdown-preview-sizer 裡最後是 .mod-footer（renderer.footer.el，反向連結也接這裡）；
  // 即時預覽 .cm-sizer 裡是 .cm-contentContainer（內容，底部留白是它裡面 .cm-content 的 padding）、再來 .embedded-backlinks
  const preview = new FakeEl('div');
  preview.classList.add('markdown-preview-sizer');
  const footer = new FakeEl('div');
  footer.classList.add('mod-footer');
  preview.appendChild(new FakeEl('div'));
  preview.appendChild(footer);
  const source = new FakeEl('div');
  source.classList.add('cm-sizer');
  const content = new FakeEl('div');
  content.classList.add('cm-contentContainer');
  const backlinks = new FakeEl('div');
  backlinks.classList.add('embedded-backlinks');
  source.appendChild(content);
  source.appendChild(backlinks);
  const containerEl = new FakeEl('div');
  containerEl.appendChild(preview);
  containerEl.appendChild(source);
  const file = { path: '02 顧客/李小姐/李小姐.md' };
  const view = { file, containerEl };
  const leaves = [{ view }];
  let writes = 0;
  const app = {
    vault: { adapter: { getBasePath: () => '/vault', read: async () => '' }, modify: async () => (writes += 1), process: async () => (writes += 1) },
    workspace: { getLeavesOfType: (t) => (t === 'markdown' ? leaves : []), getActiveViewOfType: () => null, openLinkText: async (t) => opened.push(t) },
    metadataCache: { getFileCache: (f) => (f.path === file.path ? { frontmatter: { 編號: 'e-1234abcd' } } : { frontmatter: { 編號: 'f-1234' } }) },
  };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.ui = lib.defaultUi();
  plugin.tracker = lib.createApplyTracker();
  plugin.applying = new Set();
  plugin.activePath = null;
  plugin.panels = new Map();
  plugin.runner = {
    run: async (args) => {
      calls.push(args);
      return handler(args);
    },
  };
  plugin.toast = (t) => toasts.push(t);
  const origError = console.error;
  return {
    plugin, file, view, preview, footer, source, content, backlinks, calls, opened, toasts, errors,
    writes: () => writes,
    quiet(fn) {
      console.error = (...a) => errors.push(a.join(' '));
      return Promise.resolve(fn()).finally(() => {
        console.error = origError;
      });
    },
  };
}

test('打開綜合卡：叫 kb entity panel，在閱讀與即時預覽兩邊的最後畫「日程」；卡檔沒被寫', async () => {
  const c = makeCardPlugin(() => ({ code: 0, stdout: JSON.stringify(PANEL), stderr: '' }));
  await c.plugin.showPanel(c.file);
  assert.deepStrictEqual(c.calls, [['entity', 'panel', 'e-1234abcd', '--json']]);
  assert.strictEqual(c.footer.children[c.footer.children.length - 1], byClass(c.preview, 'wwh-panel')[0], '閱讀模式：接在 .mod-footer 裡（renderer 重畫也留著）');
  assert.strictEqual(c.source.children[1], byClass(c.source, 'wwh-panel')[0], '即時預覽：緊接在內容後面、反向連結前面（不在底部留白後面）');
  for (const box of [c.preview, c.source]) {
    const panel = byClass(box, 'wwh-panel');
    assert.strictEqual(panel.length, 1);
    const text = panel[0].textContent;
    assert.ok(text.includes('日程'));
    assert.ok(text.includes('11/5（四）會議：見李小姐'));
    for (const gone of ['帳', '未收', '庫存']) assert.ok(!text.includes(gone), `不畫${gone}`);
  }
  assert.strictEqual(c.writes(), 0, '卡檔沒被寫');
  await c.plugin.showPanel(c.file);
  assert.strictEqual(byClass(c.preview, 'wwh-panel').length, 1, '再開一次不重複畫');
  byText(c.preview, '11/5（四）會議：見李小姐').pop().fire('click');
  await tick();
  assert.strictEqual(c.opened[0], '系統/日程');
});

test('檔案卡、沒有日程的不畫；kb 失敗時不畫不報錯（記 console）', async () => {
  const empty = makeCardPlugin(() => ({ code: 0, stdout: JSON.stringify({ entity: '李小姐', type: '顧客', agenda: []}), stderr: '' }));
  await empty.plugin.showPanel(empty.file);
  assert.strictEqual(byClass(empty.preview, 'wwh-panel').length, 0);
  await empty.plugin.showPanel({ path: '檔案索引/a-1234.md' });
  assert.strictEqual(empty.calls.length, 1, '不是綜合卡不叫 kb');
  const bad = makeCardPlugin(() => ({ code: 1, stdout: '', stderr: 'Traceback' }));
  await bad.quiet(() => bad.plugin.showPanel(bad.file));
  assert.strictEqual(byClass(bad.preview, 'wwh-panel').length, 0);
  assert.deepStrictEqual(bad.toasts, []);
  assert.ok(bad.errors.length >= 1);
});

test('舊版 kb 的 panel 給了 money、stock 也不畫；沒有日程回 null', () => {
  const old = lib.panelModel({ agenda: [], money: { head: '累計收 3,600', open: [], recent: [], total_n: 1 }, stock: { products: [], line: '庫存：精華液 12 瓶' } });
  assert.strictEqual(old, null);
  const withAgenda = lib.panelModel({ agenda: [{ id: 'a-1', line: 'x' }], money: { head: 'h' }, stock: { line: 'l' } });
  assert.deepStrictEqual(Object.keys(withAgenda), ['agenda']);
  assert.strictEqual(lib.panelModel({ agenda: [] }), null);
});

test('styles.css（#65）：卡底下那段的樣式留著；帳的樣式（庫存不足、公司還欠你、金額未知、帳連結、庫存行）拿掉', () => {
  const css = require('fs').readFileSync(require('path').join(__dirname, '..', '..', 'obsidian', 'styles.css'), 'utf8');
  for (const sel of ['.wwh-panel {', '.wwh-panel-title', '.wwh-panel-line', '.wwh-panel-line:hover']) assert.ok(css.includes(sel), sel);
  for (const sel of ['is-stock', 'is-owed', '.wwh-check-none', '.wwh-top-links', '.wwh-panel-stock']) assert.ok(!css.includes(sel), sel);
});

test('同一分頁切閱讀模式／即時預覽（layout-change）：那段重接、不重複、不再叫 kb（測試報告中 #3）', async () => {
  const c = makeCardPlugin(() => ({ code: 0, stdout: JSON.stringify(PANEL), stderr: '' }));
  await c.plugin.showPanel(c.file);
  // 模擬 Obsidian 切到閱讀模式時重畫了那一邊（舊的段被清掉）
  for (const k of [...c.footer.children]) c.footer.removeChild(k);
  c.plugin.onLayoutChange();
  c.plugin.onLayoutChange();
  await new Promise((r) => setTimeout(r, 80));
  assert.strictEqual(byClass(c.preview, 'wwh-panel').length, 1, '閱讀模式那邊接回來');
  assert.strictEqual(byClass(c.source, 'wwh-panel').length, 1, '即時預覽那邊沒有重複');
  assert.strictEqual(c.calls.length, 1, '切模式不再叫 kb');
});

test('閱讀模式 renderer 重排 sizer 裡的段：那段在 .mod-footer 裡跟著留著（記帳 3 確認 #1）', async () => {
  const c = makeCardPlugin(() => ({ code: 0, stdout: JSON.stringify(PANEL), stderr: '' }));
  await c.plugin.showPanel(c.file);
  for (const k of [...c.preview.children]) c.preview.removeChild(k); // renderer 清掉、重接每一段
  c.preview.appendChild(new FakeEl('div'));
  c.preview.appendChild(c.footer);
  assert.strictEqual(byClass(c.preview, 'wwh-panel').length, 1);
});

test('有 renderer.footer 就接那裡（.mod-footer 這時不在 DOM 也接得上）', async () => {
  const c = makeCardPlugin(() => ({ code: 0, stdout: JSON.stringify(PANEL), stderr: '' }));
  const el = new FakeEl('div');
  let updated = 0;
  c.view.previewMode = { renderer: { footer: { el }, updateFooter: () => (updated += 1) } };
  c.preview.removeChild(c.footer);
  await c.plugin.showPanel(c.file);
  assert.strictEqual(byClass(el, 'wwh-panel').length, 1);
  assert.ok(updated >= 1, '叫 renderer 重算 footer 的高');
});

test('同一分頁從卡換到別頁（file-open／layout-change／active-leaf-change）：卡的那段拿掉（記帳 3 確認 #3）', async () => {
  for (const how of ['file-open', 'layout-change', 'active-leaf-change']) {
    const c = makeCardPlugin(() => ({ code: 0, stdout: JSON.stringify(PANEL), stderr: '' }));
    await c.plugin.showPanel(c.file);
    assert.strictEqual(byClass(c.preview, 'wwh-panel').length + byClass(c.source, 'wwh-panel').length, 2);
    const page = { path: '系統/日程.md' };
    c.view.file = page; // 點那段的一行，同一分頁開日程頁
    if (how === 'file-open') c.plugin.onFileOpen(page);
    else if (how === 'layout-change') c.plugin.onLayoutChange();
    else c.plugin.onActiveChange();
    await tick();
    assert.strictEqual(byClass(c.preview, 'wwh-panel').length, 0, `${how}：閱讀模式那邊拿掉`);
    assert.strictEqual(byClass(c.source, 'wwh-panel').length, 0, `${how}：即時預覽那邊拿掉`);
    await new Promise((r) => setTimeout(r, 80));
    assert.strictEqual(byClass(c.preview, 'wwh-panel').length + byClass(c.source, 'wwh-panel').length, 0, `${how}：之後重接也不接回日程頁`);
  }
});

test('styles.css：即時預覽有那段時，內容底部的半頁留白收掉、留白改在那段後面（記帳 3 確認 #2）', () => {
  const css = require('fs').readFileSync(require('path').join(__dirname, '..', '..', 'obsidian', 'styles.css'), 'utf8');
  assert.ok(css.includes('.cm-sizer:has(> .wwh-panel) .cm-content'), '有那段才收內容的底部留白');
  assert.ok(css.includes('.cm-sizer > .wwh-panel'), '留白改在那段後面');
});
