'use strict';
/* 記帳 3（issue #27）：帳頁是受管頁、首頁的帳（到期件、庫存不足、公司還欠你、帳的連結）、綜合卡底下外掛畫的「日程與帳」（D-340）。 */
const test = require('node:test');
const assert = require('node:assert');
const { loadMain } = require('./helpers/env');
const { FakeEl, byClass, byText } = require('./helpers/fakedom');

const env = loadMain();
const lib = env.lib;
test.after(() => env.restore());

const tick = () => new Promise((r) => setImmediate(r));

test('帳頁與年頁是受管頁；money.json 變了也刷新', () => {
  assert.ok(lib.isManagedPage('系統/帳.md'));
  assert.ok(lib.isManagedPage('系統\\帳\\2026.md'));
  assert.ok(!lib.isManagedPage('系統/帳/備註.md'));
  assert.ok(lib.WATCH_FILES.includes('money.json'));
});

test('首頁資料：stock、owed、links 照收；舊版 kb 沒給也不壞', () => {
  const home = lib.normalizeHome({ todo: { stock: [{ entity: '精華液' }], owed: [{ id: 'm-1' }] }, links: { money: '系統/帳.md' } });
  assert.strictEqual(home.todo.stock.length, 1);
  assert.strictEqual(home.todo.owed.length, 1);
  assert.strictEqual(home.links.money, '系統/帳.md');
  const old = lib.normalizeHome({});
  assert.deepStrictEqual([old.todo.stock, old.todo.owed, old.links.money], [[], [], null]);
  const keys = lib.todoGroups(home).map((g) => g.key);
  assert.deepStrictEqual(keys, ['overdue', 'today', 'week', 'stock', 'owed']);
  assert.deepStrictEqual(lib.todoGroups(old).map((g) => g.key), ['overdue', 'today', 'week'], '沒有的組不畫');
});

test('帳的件：打勾叫 kb money settle、改日期叫 kb money edit --due', () => {
  const it = { id: 'm-1', source: 'money', end: '2026-11-20', date: '2026-11-20' };
  const a = lib.actions.done(it);
  assert.deepStrictEqual(a.args, ['money', 'settle', 'm-1']);
  assert.deepStrictEqual(a.undo().args, ['money', 'reopen', 'm-1']);
  const e = lib.actions.edit(it, { date: '2026-11-28' });
  assert.deepStrictEqual(e.args, ['money', 'edit', 'm-1', '--due', '2026-11-28']);
  assert.deepStrictEqual(e.undo().args, ['money', 'edit', 'm-1', '--due', '2026-11-20']);
  assert.strictEqual(lib.actions.edit(it, { date: '2026-11-20' }), null);
});

test('找頁上的那一行：整行一樣的先，再找包含的，找不到回頁頂', () => {
  const page = ['# 帳', '## 還沒收付的', '- 11/20（五）收 50,000 [[a|信義王]] 第二期　已過 3 天', '> - 10/30（五）收 5,000 李小姐'].join('\n');
  assert.strictEqual(lib.findPageLine(page, '- 11/20（五）收 50,000 [[a|信義王]] 第二期　已過 3 天'), 2);
  assert.strictEqual(lib.findPageLine(page, '> - 10/30（五）收 5,000 李小姐'), 3);
  assert.strictEqual(lib.findPageLine(page, '- 11/20（五）收 50,000 [[a|信義王]] 第二期'), 2, '過了幾天字變了也找得到');
  assert.strictEqual(lib.findPageLine(page, '不在頁上'), 0);
});

function makeHomePlugin(home) {
  const calls = [];
  const opened = [];
  const app = {
    vault: { adapter: { getBasePath: () => '/vault', read: async () => '' } },
    workspace: { getLeavesOfType: () => [], getActiveViewOfType: () => null, openLinkText: async (t) => opened.push(t) },
    metadataCache: { getFileCache: () => null },
  };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.ui = lib.defaultUi();
  plugin.runner = {
    run: async (args) => {
      calls.push(args);
      return { code: 0, stdout: '好', stderr: '' };
    },
  };
  plugin.toast = () => {};
  plugin.scheduleRefresh = () => {};
  plugin.openEntity = () => {};
  plugin.home = lib.normalizeHome(home);
  const view = new lib.HomeView({}, plugin);
  view.build();
  view.render();
  return { plugin, view, calls, opened };
}

const MONEY_HOME = {
  today: '2026-11-23',
  todo: {
    overdue: [
      { id: 'm-1', source: 'money', kind: 'deadline', end: '2026-11-20', date: '2026-11-20', text: '收 50,000 第二期', entities: ['信義王'], late: true, settle_ok: true, page: '系統/帳.md', match: '- 11/20（五）收 50,000' },
      { id: 'm-2', source: 'money', kind: 'deadline', end: '2026-11-21', date: '2026-11-21', text: '收 （金額未知） 尾款', entities: [], late: true, settle_ok: false, page: '系統/帳.md', match: '- （金額未知）收' },
    ],
    stock: [{ entity: '精華液', stock: 4, min: 5, unit: '瓶', places: {}, card: '03 產品/精華液/精華液.md' }],
    owed: [{ id: 'm-3', amount: 3200, text: '文具', date: null, page: '系統/帳.md', match: '- 付 3,200 文具（小王墊）' }],
  },
  links: { money: '系統/帳.md' },
};

test('首頁：帳的件打勾叫 kb money settle；金額未知的不給勾', async () => {
  const { view, calls } = makeHomePlugin(MONEY_HOME);
  const rows = byClass(view.root, 'wwh-todo');
  const boxes = byClass(view.root, 'wwh-check');
  assert.strictEqual(boxes.length, 1, '金額未知、庫存不足、公司還欠你都沒有勾選框');
  boxes[0].fire('click');
  await tick();
  assert.deepStrictEqual(calls[0], ['money', 'settle', 'm-1']);
  assert.strictEqual(rows.length, 4);
});

test('首頁：庫存不足點了開商品的卡、公司還欠你點了開帳頁、上方「帳」連結開帳頁', async () => {
  const { view, opened } = makeHomePlugin(MONEY_HOME);
  byText(view.root, '精華液剩 4 瓶（安全庫存 5）').pop().fire('click');
  await tick();
  assert.deepStrictEqual(opened, ['03 產品/精華液/精華液']);
  byText(view.root, '公司還欠你 3,200（文具）').pop().fire('click');
  await tick();
  await tick();
  assert.strictEqual(opened[1], '系統/帳');
  byClass(view.root, 'wwh-money-link').pop().fire('click');
  await tick();
  assert.strictEqual(opened[2], '系統/帳');
  const none = makeHomePlugin({ today: '2026-11-23', links: { money: null } });
  assert.strictEqual(byClass(none.view.root, 'wwh-money-link').length, 0, '帳關著而且沒有任何筆時不出');
});

test('首頁：庫存不足照 kb 給的 text 顯示，換不了的分開列（D-344 補）', () => {
  const split = { today: '2026-11-23', todo: { stock: [{ entity: '精華液', stock: 12, min: 20, unit: '瓶', text: '12 瓶＋2 箱（不知道一箱幾瓶）', places: {} }] } };
  const { view } = makeHomePlugin(split);
  assert.ok(byText(view.root, '精華液剩 12 瓶＋2 箱（不知道一箱幾瓶）（安全庫存 20）').length > 0);
});

const PANEL = {
  entity: '李小姐',
  type: '顧客',
  agenda: [{ id: 'a-1', date: '2026-11-05', kind: '會議', text: '見李小姐', late: false, line: '11/5（四）會議：見李小姐', page: '系統/日程.md', match: '- 2026-11-05（週四）會議 見李小姐' }],
  money: {
    head: '累計收 48,600｜未收 1,800',
    open: [{ id: 'm-1', line: '未收 1,800 月底付另一半（到期 11/30，已過 3 天）', page: '系統/帳.md', match: '- 11/30（一）收 1,800' }],
    recent: [{ id: 'm-2', line: '10/30（五）收 5,000 精華液 ×2、膠囊 ×1', page: '系統/帳/2026.md', match: '> - 10/30（五）收 5,000' }],
    total_n: 23,
    page: '系統/帳.md',
  },
  stock: null,
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

test('打開綜合卡：叫 kb entity panel，在閱讀與即時預覽兩邊的最後畫「日程與帳」；卡檔沒被寫', async () => {
  const c = makeCardPlugin(() => ({ code: 0, stdout: JSON.stringify(PANEL), stderr: '' }));
  await c.plugin.showPanel(c.file);
  assert.deepStrictEqual(c.calls, [['entity', 'panel', 'e-1234abcd', '--json']]);
  assert.strictEqual(c.footer.children[c.footer.children.length - 1], byClass(c.preview, 'wwh-panel')[0], '閱讀模式：接在 .mod-footer 裡（renderer 重畫也留著）');
  assert.strictEqual(c.source.children[1], byClass(c.source, 'wwh-panel')[0], '即時預覽：緊接在內容後面、反向連結前面（不在底部留白後面）');
  for (const box of [c.preview, c.source]) {
    const panel = byClass(box, 'wwh-panel');
    assert.strictEqual(panel.length, 1);
    const text = panel[0].textContent;
    for (const want of ['日程與帳', '11/5（四）會議：見李小姐', '帳：累計收 48,600｜未收 1,800', '未收 1,800 月底付另一半（到期 11/30，已過 3 天）', '10/30（五）收 5,000 精華液 ×2、膠囊 ×1', '…共 23 筆，看帳']) {
      assert.ok(text.includes(want), want);
    }
  }
  assert.strictEqual(c.writes(), 0, '卡檔沒被寫');
  await c.plugin.showPanel(c.file);
  assert.strictEqual(byClass(c.preview, 'wwh-panel').length, 1, '再開一次不重複畫');
  byText(c.preview, '10/30（五）收 5,000 精華液 ×2、膠囊 ×1').pop().fire('click');
  await tick();
  assert.deepStrictEqual(c.opened, ['系統/帳/2026'], '帳那行開帳頁');
  byText(c.preview, '11/5（四）會議：見李小姐').pop().fire('click');
  await tick();
  assert.strictEqual(c.opened[1], '系統/日程');
});

test('檔案卡、沒有日程也沒有帳的不畫；kb 失敗時不畫不報錯（記 console）', async () => {
  const empty = makeCardPlugin(() => ({ code: 0, stdout: JSON.stringify({ entity: '李小姐', type: '顧客', agenda: [], money: null, stock: null }), stderr: '' }));
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

test('商品卡：帳那行是庫存與各店；分店：畫那店的庫存', () => {
  const product = lib.panelModel({ agenda: [], money: { head: '庫存 17 瓶（北店 12、南店 5）｜賣出累計 2 瓶', open: [], recent: [], total_n: 0 }, stock: { name: '精華液', total: 17, line: '庫存 17 瓶（北店 12、南店 5）' } });
  assert.strictEqual(product.stockLine, null, '商品的庫存已經在帳那行');
  const place = lib.panelModel({ agenda: [], money: { head: '累計收 3,600', open: [], recent: [], total_n: 1 }, stock: { products: [], line: '庫存：精華液 12 瓶' } });
  assert.strictEqual(place.stockLine, '庫存：精華液 12 瓶');
  assert.strictEqual(lib.panelModel({ agenda: [], money: null, stock: null }), null);
});

test('styles.css 有記帳 3 的樣式（測試報告中 #2）：卡底下那段、庫存不足與公司還欠你兩組、金額未知、帳連結；帳連結不用時間軸那個 .wwh-links', () => {
  const css = require('fs').readFileSync(require('path').join(__dirname, '..', '..', 'obsidian', 'styles.css'), 'utf8');
  for (const sel of ['.wwh-panel {', '.wwh-panel-title', '.wwh-panel-line', '.wwh-panel-line:hover', '.wwh-group-head.is-stock', '.wwh-todo.is-stock', '.wwh-todo.is-owed', '.wwh-check-none', '.wwh-top-links']) {
    assert.ok(css.includes(sel), sel);
  }
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
    const money = { path: '系統/帳.md' };
    c.view.file = money; // 點那段的一行，同一分頁開帳頁
    if (how === 'file-open') c.plugin.onFileOpen(money);
    else if (how === 'layout-change') c.plugin.onLayoutChange();
    else c.plugin.onActiveChange();
    await tick();
    assert.strictEqual(byClass(c.preview, 'wwh-panel').length, 0, `${how}：閱讀模式那邊拿掉`);
    assert.strictEqual(byClass(c.source, 'wwh-panel').length, 0, `${how}：即時預覽那邊拿掉`);
    await new Promise((r) => setTimeout(r, 80));
    assert.strictEqual(byClass(c.preview, 'wwh-panel').length + byClass(c.source, 'wwh-panel').length, 0, `${how}：之後重接也不接回帳頁`);
  }
});

test('styles.css：即時預覽有那段時，內容底部的半頁留白收掉、留白改在那段後面（記帳 3 確認 #2）', () => {
  const css = require('fs').readFileSync(require('path').join(__dirname, '..', '..', 'obsidian', 'styles.css'), 'utf8');
  assert.ok(css.includes('.cm-sizer:has(> .wwh-panel) .cm-content'), '有那段才收內容的底部留白');
  assert.ok(css.includes('.cm-sizer > .wwh-panel'), '留白改在那段後面');
});
