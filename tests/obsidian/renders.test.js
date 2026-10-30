'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadMain } = require('./helpers/env');
const { FakeEl } = require('./helpers/fakedom');

const env = loadMain();
const lib = env.lib;
test.after(() => env.restore());

const PAGE = '系統/日程.md';

test('追蹤器：離開被改的那一行（游標換行）才算要套用', () => {
  const t = lib.createApplyTracker();
  assert.strictEqual(t.edited(PAGE, 5, 1000), false, '剛打字，還在同一行');
  assert.strictEqual(t.edited(PAGE, 5, 1100), false);
  assert.strictEqual(t.cursor(PAGE, 5), false, '游標還在那一行');
  assert.strictEqual(t.cursor(PAGE, 8), true, '游標移到別行 = 離開了');
  assert.strictEqual(t.isDirty(PAGE), false);
  assert.strictEqual(t.cursor(PAGE, 9), false, '套用過了，沒有東西要套');
});

test('追蹤器：打完按 Enter（編輯事件的游標已在下一行）也算離開', () => {
  const t = lib.createApplyTracker();
  t.edited(PAGE, 10, 1000);
  assert.strictEqual(t.edited(PAGE, 11, 1200), true);
});

test('追蹤器：切到別頁才套用；沒改過的頁不套用', () => {
  const t = lib.createApplyTracker();
  assert.strictEqual(t.leave(PAGE), false);
  t.edited(PAGE, 3, 1000);
  assert.strictEqual(t.leave(PAGE), true);
  assert.strictEqual(t.leave(PAGE), false);
});

test('追蹤器：kb 剛改寫這頁，編輯器重載不算她打的', () => {
  const t = lib.createApplyTracker();
  t.edited(PAGE, 3, 1000);
  t.external(PAGE, 2000);
  assert.strictEqual(t.isDirty(PAGE), false);
  assert.strictEqual(t.edited(PAGE, 0, 2100), false);
  assert.strictEqual(t.isDirty(PAGE), false);
  assert.strictEqual(t.edited(PAGE, 4, 3000), false, '過了緩衝期她打的字照常追蹤');
  assert.strictEqual(t.isDirty(PAGE), true);
});

test('哪些頁是她能改的、哪些是記錄', () => {
  for (const p of ['系統/日程.md', '系統/待處理.md', '系統/裁示.md']) assert.ok(lib.isManagedPage(p));
  assert.ok(lib.isManagedPage('系統\\日程.md'));
  assert.ok(!lib.isManagedPage('系統/客戶設定檔.md'));
  for (const p of ['總目錄.md', '系統/工作日誌/2026-10.md', '系統/健檢報告/2026-10.md']) assert.ok(lib.isGeneratedPage(p), p);
  for (const p of ['系統/日程.md', '01 案子/信義王/信義王.md', '檔案索引/a.md']) assert.ok(!lib.isGeneratedPage(p), p);
});

test('她開著的頁被外部改寫才 toast：不是她在打字、不是外掛自己剛叫 kb', () => {
  const base = { open: true, applying: false, typing: false, lastKbAt: 0, now: 100000 };
  assert.strictEqual(lib.shouldToastModified(base), true);
  assert.strictEqual(lib.shouldToastModified(Object.assign({}, base, { open: false })), false);
  assert.strictEqual(lib.shouldToastModified(Object.assign({}, base, { typing: true })), false);
  assert.strictEqual(lib.shouldToastModified(Object.assign({}, base, { applying: true })), false);
  assert.strictEqual(lib.shouldToastModified(Object.assign({}, base, { lastKbAt: 99000 })), false);
  assert.strictEqual(lib.shouldToastModified(Object.assign({}, base, { lastKbAt: 90000 })), true);
});

test('renders apply 的回報：套用了幾件、搬進「你加的」就說在哪', () => {
  assert.deepStrictEqual(lib.summarizeApply({ applied: [], carried: [] }, '日程'), { applied: 0, carried: 0, text: '' });
  assert.strictEqual(lib.summarizeApply({ applied: [{}, {}], carried: [] }, '日程').text, '照你在日程改的做了 2 件');
  assert.strictEqual(lib.summarizeApply({ applied: [], carried: [{ id: 'c-1' }] }, '日程').text, '你剛在這頁改的我留在最下面『你加的』');
  assert.strictEqual(lib.summarizeApply({ applied: 1, carried: 1 }, '待處理').text, '照你在待處理改的做了 1 件；你剛在這頁改的我留在最下面『你加的』');
  assert.strictEqual(lib.summarizeApply(null, '日程').text, '');
  assert.strictEqual(lib.summarizeApply({ applied: [], carried: [], unrecognized: true }, '日程').text, '這頁你改的我沒認出來，記在待處理了');
  assert.ok(lib.hasCarriedSection('# 日程\n\n## 你加的（還沒處理）\n- 測試\n'));
  assert.ok(!lib.hasCarriedSection('# 日程\n'));
});

function makePlugin() {
  const out = { runs: [], toasts: [], saves: 0, refreshes: 0, notified: [] };
  const leaves = [];
  const app = {
    vault: { adapter: { getBasePath: () => '/vault' }, cachedRead: async () => '', getMarkdownFiles: () => [] },
    workspace: {
      getLeavesOfType: (t) => (t === 'markdown' ? leaves : []),
      getActiveViewOfType: () => null,
    },
    metadataCache: { getFileCache: () => null },
  };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.tracker = lib.createApplyTracker();
  plugin.applying = new Set();
  plugin.lastKbAt = 0;
  plugin.activePath = null;
  plugin.runner = {
    run: async (args) => {
      out.runs.push(args);
      return { code: 0, stdout: JSON.stringify({ applied: [{ kind: 'done' }], carried: [{ id: 'c-1' }] }), stderr: '' };
    },
  };
  plugin.toast = (t) => out.toasts.push(t);
  plugin.scheduleRefresh = () => {
    out.refreshes += 1;
  };
  return { plugin, out, leaves, app };
}

function editorAt(line) {
  return { getCursor: () => ({ line, ch: 0 }) };
}

const tick = () => new Promise((r) => setImmediate(r));

test('離開那一行才叫 kb renders apply；叫的時候帶 --json 和頁路徑', async () => {
  const { plugin, out } = makePlugin();
  const info = { file: { path: PAGE } };
  plugin.onEditorChange(editorAt(6), info);
  plugin.onEditorChange(editorAt(6), info);
  await tick();
  assert.strictEqual(out.runs.length, 0, '還在同一行，不叫');
  plugin.onEditorChange(editorAt(7), info); // 打完 Enter，換到下一行
  await tick();
  await tick();
  assert.deepStrictEqual(out.runs, [['renders', 'apply', PAGE, '--json']]);
  assert.deepStrictEqual(out.toasts, ['照你在日程改的做了 1 件；你剛在這頁改的我留在最下面『你加的』']);
});

test('游標移到別行（沒打字）才叫；切到別頁也叫；不是這三頁的不叫', async () => {
  const { plugin, out, app } = makePlugin();
  plugin.onEditorChange(editorAt(2), { file: { path: PAGE } });
  const view = { file: { path: PAGE }, editor: editorAt(2) };
  app.workspace.getActiveViewOfType = () => view;
  plugin.onSelection();
  await tick();
  assert.strictEqual(out.runs.length, 0);
  view.editor = editorAt(9);
  plugin.onSelection();
  await tick();
  await tick();
  assert.strictEqual(out.runs.length, 1);

  // 切到別頁
  const other = makePlugin();
  other.plugin.activePath = '系統/待處理.md';
  other.plugin.onEditorChange(editorAt(1), { file: { path: '系統/待處理.md' } });
  other.plugin.switchedTo('01 案子/信義王/信義王.md');
  await tick();
  await tick();
  assert.deepStrictEqual(other.out.runs, [['renders', 'apply', '系統/待處理.md', '--json']]);

  // 設定檔、綜合卡不套用
  const none = makePlugin();
  none.plugin.onEditorChange(editorAt(1), { file: { path: '系統/客戶設定檔.md' } });
  none.plugin.onEditorChange(editorAt(5), { file: { path: '系統/客戶設定檔.md' } });
  none.plugin.switchedTo('x.md');
  await tick();
  assert.strictEqual(none.out.runs.length, 0);
});

test('套用時先把開著的頁存檔，再叫 kb', async () => {
  const { plugin, out, leaves } = makePlugin();
  const order = [];
  leaves.push({ view: { file: { path: PAGE }, save: async () => order.push('save') } });
  plugin.runner.run = async (args) => {
    order.push('kb');
    out.runs.push(args);
    return { code: 0, stdout: '{}', stderr: '' };
  };
  await plugin.applyPage(PAGE);
  assert.deepStrictEqual(order, ['save', 'kb']);
  assert.strictEqual(out.toasts.length, 0, '沒有套用也沒有搬走，安靜');
});

test('renders apply 被拒絕：toast kb 的句子', async () => {
  const { plugin, out } = makePlugin();
  plugin.runner.run = async () => ({ code: 3, stdout: '現在有別的健檢在改這一頁，等一下再說\n', stderr: '' });
  await plugin.applyPage(PAGE);
  assert.deepStrictEqual(out.toasts, ['現在有別的健檢在改這一頁，等一下再說']);
});

test('頁被外部改寫：開著而且她沒在打字就 toast「這頁剛被更新了」', async () => {
  const { plugin, out, leaves } = makePlugin();
  leaves.push({ view: { file: { path: PAGE } } });
  plugin.onVaultModify({ path: PAGE });
  await tick();
  await tick();
  assert.deepStrictEqual(out.toasts, ['這頁剛被更新了']);

  // 她剛打過字：那是她自己存檔，不提示
  const typed = makePlugin();
  typed.leaves.push({ view: { file: { path: PAGE } } });
  typed.plugin.tracker.edited(PAGE, 2, Date.now());
  typed.plugin.onVaultModify({ path: PAGE });
  await tick();
  assert.strictEqual(typed.out.toasts.length, 0);

  // 沒開著
  const closed = makePlugin();
  closed.plugin.onVaultModify({ path: PAGE });
  await tick();
  assert.strictEqual(closed.out.toasts.length, 0);
});

test('頁被外部改寫、而且她剛在這頁打過字、內文多了「你加的」：說她改的留在最下面', async () => {
  const { plugin, out, leaves, app } = makePlugin();
  leaves.push({ view: { file: { path: PAGE } } });
  app.vault.cachedRead = async () => '# 日程\n\n## 你加的（還沒處理）\n- 測試\n';
  plugin.tracker.edited(PAGE, 2, Date.now() - 20000); // 20 秒前打的，不在 5 秒的「正在打字」裡
  plugin.onVaultModify({ path: PAGE });
  await tick();
  await tick();
  assert.deepStrictEqual(out.toasts, ['這頁剛被更新了；你剛在這頁改的我留在最下面『你加的』']);
});

test('外掛自己叫 kb 剛改的頁不重複 toast', async () => {
  const { plugin, out, leaves } = makePlugin();
  leaves.push({ view: { file: { path: PAGE } } });
  plugin.lastKbAt = Date.now();
  plugin.onVaultModify({ path: PAGE });
  await tick();
  assert.strictEqual(out.toasts.length, 0);
});

test('總目錄、工作日誌、健檢報告：切成閱讀模式，最上面一條提示', async () => {
  const { plugin, leaves } = makePlugin();
  const contentEl = new FakeEl('div');
  contentEl.appendChild(new FakeEl('div'));
  const states = [];
  const leaf = {
    view: { file: { path: '總目錄.md' }, contentEl },
    getViewState: () => ({ type: 'markdown', state: { file: '總目錄.md', mode: 'source' } }),
    setViewState: async (s) => {
      states.push(s);
    },
  };
  leaves.push(leaf);
  plugin.onFileOpen({ path: '總目錄.md' });
  await new Promise((r) => setTimeout(r, 100));
  assert.strictEqual(states.length, 1);
  assert.strictEqual(states[0].state.mode, 'preview');
  assert.strictEqual(contentEl.children[0].textContent, lib.GENERATED_BANNER);
  assert.strictEqual(contentEl.children.length, 2);
  // 再開一次不重複加
  plugin.addGeneratedBanner(leaf.view);
  assert.strictEqual(contentEl.children.length, 2);
});

test('日程、設定檔不切閱讀模式', async () => {
  const { plugin, leaves } = makePlugin();
  const states = [];
  leaves.push({
    view: { file: { path: PAGE }, contentEl: new FakeEl('div') },
    getViewState: () => ({ type: 'markdown', state: { mode: 'source' } }),
    setViewState: async (s) => states.push(s),
  });
  plugin.onFileOpen({ path: PAGE });
  plugin.onFileOpen({ path: '系統/客戶設定檔.md' });
  await new Promise((r) => setTimeout(r, 80));
  assert.strictEqual(states.length, 0);
});
