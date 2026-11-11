'use strict';
/* #66 乙（D-540、D-543～D-546）：外掛認子夾裡的知識庫、同一個 vault 好幾個知識庫時可以切換。
 * 編號對 design/specs/2026-11-11-外掛認子夾知識庫.md 的驗收準則。 */
const test = require('node:test');
const assert = require('node:assert');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { loadMain, fakeExecFile } = require('./helpers/env');
const { byClass, byTag } = require('./helpers/fakedom');

const env = loadMain();
const lib = env.lib;
test.after(() => env.restore());

const wait = (ms) => new Promise((r) => setTimeout(r, ms || 60));
const OPEN = 'wiki-with-willy-open';

function mark(dir) {
  fs.mkdirSync(path.join(dir, '.system'), { recursive: true });
  fs.writeFileSync(path.join(dir, '.system', 'sources.json'), '{}\n');
}

function homeOf(cwd) {
  return { schema: 'willy-home/1', version: '0.37.0', today: '2026-11-11', cheer: `這是 ${path.basename(cwd)}`, counts: {}, timeline: { from: '2026-11-01', to: '2026-12-31', rows: [] }, todo: {}, confirm: [], others: [], recent: [] };
}

/** 真的暫存夾當 vault（kbs 是知識庫的前綴）、假的 installed_plugins 與 kb、假的 Obsidian app；fs.watch 換成只記不看。 */
function setup(opts) {
  const o = opts || {};
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wwh-roots-'));
  const vault = path.join(root, 'vault');
  fs.mkdirSync(vault, { recursive: true });
  for (const kb of o.kbs || []) mark(kb ? path.join(vault, ...kb.split('/')) : vault);
  for (const d of o.dirs || []) fs.mkdirSync(path.join(vault, ...d.split('/')), { recursive: true });
  const cfg = path.join(root, 'cfg');
  const inst = path.join(root, 'inst');
  fs.mkdirSync(path.join(cfg, 'plugins'), { recursive: true });
  fs.mkdirSync(path.join(inst, 'scripts'), { recursive: true });
  fs.writeFileSync(path.join(inst, 'scripts', 'kb.py'), '# fake\n');
  const records = (o.records ? o.records(vault, root) : null) || [{ scope: 'user', installPath: inst, version: '0.37.0' }];
  for (const r of records) {
    fs.mkdirSync(path.join(r.installPath, 'scripts'), { recursive: true });
    fs.writeFileSync(path.join(r.installPath, 'scripts', 'kb.py'), '# fake\n');
  }
  fs.writeFileSync(path.join(cfg, 'plugins', 'installed_plugins.json'), JSON.stringify({ version: 2, plugins: { 'wiki-with-willy@m': records } }));
  const savedEnv = process.env.CLAUDE_CONFIG_DIR;
  process.env.CLAUDE_CONFIG_DIR = cfg;

  const watched = [];
  const closed = [];
  const origWatch = fs.watch;
  fs.watch = (dir) => {
    watched.push(dir);
    return { on() {}, close: () => closed.push(dir) };
  };

  const exec = fakeExecFile((file, argv, options) => {
    const args = argv.slice(argv.indexOf('obsidian') + 1);
    const r = o.reply ? o.reply(args, options.cwd) : undefined;
    return { code: 0, stdout: JSON.stringify(r === undefined ? homeOf(options.cwd) : r), stderr: '' };
  });
  const kbCalls = () => exec.calls.map((c) => ({ args: c.argv.slice(c.argv.indexOf('obsidian') + 1), cwd: c.options.cwd }));

  const store = Object.assign({}, o.store);
  const folders = new Set();
  const writes = [];
  const adapter = {
    getBasePath: () => vault,
    exists: async (p) => Object.prototype.hasOwnProperty.call(store, p) || folders.has(p),
    read: async (p) => store[p],
    write: async (p, t) => {
      writes.push([p, t]);
      store[p] = t;
    },
    mkdir: async (p) => folders.add(p),
  };
  const st = { opened: [], configs: {}, layoutCb: null, activated: 0, active: null, activeFile: null, files: o.files || [], caches: o.caches || {}, saves: [], toasts: [] };
  const leaves = { markdown: [], home: [] };
  const app = {
    vault: { adapter, setConfig: (k, v) => { st.configs[k] = v; }, on: () => ({}), getMarkdownFiles: () => st.files, cachedRead: async () => '' },
    workspace: {
      on: () => ({}),
      onLayoutReady: (cb) => { st.layoutCb = cb; },
      getLeavesOfType: (t) => (t === 'markdown' ? leaves.markdown : leaves.home),
      getActiveViewOfType: () => st.active,
      getActiveFile: () => st.activeFile,
      getLeaf: () => ({ setViewState: async () => { st.activated += 1; } }),
      revealLeaf() {},
      openLinkText: async (l) => { st.opened.push(l); },
    },
    metadataCache: { getFileCache: (f) => st.caches[f.path] || null },
  };

  function makePlugin(data) {
    const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.37.0', dir: '.obsidian/plugins/wiki-with-willy' });
    plugin.execFileOverride = exec;
    plugin.registerInterval = (id) => clearInterval(id);
    plugin.registerDomEvent = () => {};
    plugin.loadData = async () => (data === undefined ? null : data);
    plugin.saveData = async (d) => { st.saves.push(JSON.parse(JSON.stringify(d))); };
    plugin.toast = (t) => st.toasts.push(t);
    return plugin;
  }
  const plugin = makePlugin(o.data);

  /** onload、版面好了、開一個首頁分頁；回首頁的 view。 */
  async function start(p) {
    const pl = p || plugin;
    await pl.onload();
    const view = new lib.HomeView({}, pl);
    view.build();
    leaves.home.length = 0;
    if (st.layoutCb) st.layoutCb();
    leaves.home.push({ view });
    await wait();
    view.render();
    return view;
  }

  function cleanup() {
    if (plugin.ui) plugin.onunload(); // 沒載入過的不用卸
    fs.watch = origWatch;
    if (savedEnv === undefined) delete process.env.CLAUDE_CONFIG_DIR;
    else process.env.CLAUDE_CONFIG_DIR = savedEnv;
    fs.rmSync(root, { recursive: true, force: true });
  }

  return { root, vault, inst, plugin, makePlugin, start, cleanup, exec, kbCalls, store, writes, st, leaves, watched, closed };
}

async function withSetup(opts, fn) {
  const s = setup(opts);
  try {
    await fn(s);
  } finally {
    s.cleanup();
  }
}

function editorAt(line) {
  return { getCursor: () => ({ line, ch: 0 }) };
}

/** 開著那一頁、改一行、Obsidian 視窗失去焦點（＝離開那一行）。 */
async function editAndLeave(s, vaultRel) {
  const file = { path: vaultRel };
  s.leaves.markdown.push({ view: { file, save: async () => {} } });
  s.plugin.onEditorChange(editorAt(4), { file });
  s.plugin.onWindowBlur();
  await wait();
}

// ---- 找知識庫 ----

test('驗收 1：vault 根有記號就是 [\'\']，子夾裡還有別的知識庫也不往下找', () => {
  const s = setup({ kbs: ['', 'willy'] });
  try {
    assert.deepStrictEqual(lib.findKbRoots({ vaultPath: s.vault }), ['']);
  } finally {
    s.cleanup();
  }
});

test('驗收 2：vault 根沒有，第一、二層有的都收，排序固定', () => {
  const s = setup({ kbs: ['客戶B/知識庫', 'willy'] });
  try {
    assert.deepStrictEqual(lib.findKbRoots({ vaultPath: s.vault }), ['willy', '客戶B/知識庫']);
  } finally {
    s.cleanup();
  }
});

test('驗收 3：第三層、.開頭的夾、node_modules 不算；只有來源流水檔夾的算；有記號的夾不再往裡找；讀不了的略過', () => {
  const s = setup({ kbs: ['a/b/c', '.hidden/x', 'node_modules/x', 'k/內層'], dirs: ['流水/.system/streams/sources', '空流水/.system/streams/sources', 'a/b'] });
  try {
    fs.writeFileSync(path.join(s.vault, '流水', '.system', 'streams', 'sources', 'm-1.jsonl'), '{}\n');
    fs.writeFileSync(path.join(s.vault, '不是夾.md'), 'x');
    mark(path.join(s.vault, 'k')); // k 自己是知識庫：k/內層 不再算
    assert.deepStrictEqual(lib.findKbRoots({ vaultPath: s.vault }), ['k', '流水']);
  } finally {
    s.cleanup();
  }
  // 可換的 exists／readdir／isDir；讀不了的夾略過
  const tree = { '/v': ['壞', '好'], '/v/好': ['.system'] };
  const norm = (q) => q.replace(/\\/g, '/');
  const got = lib.findKbRoots({
    vaultPath: '/v',
    exists: (q) => norm(q) === '/v/好/.system/sources.json',
    isDir: () => true,
    readdir: (q) => {
      if (norm(q) === '/v/壞') throw new Error('EACCES');
      if (!tree[norm(q)]) throw new Error('ENOENT');
      return tree[norm(q)];
    },
  });
  assert.deepStrictEqual(got, ['好']);
  assert.deepStrictEqual(lib.findKbRoots({ vaultPath: '' }), []);
});

test('驗收 4：一個知識庫都沒有，首頁只有那一句、沒有叫任何 kb', async () => {
  await withSetup({ kbs: [], dirs: ['舊筆記'] }, async (s) => {
    const view = await s.start();
    assert.deepStrictEqual(s.plugin.roots, []);
    assert.strictEqual(s.plugin.current, null);
    const box = byClass(view.root, 'wwh-nokb');
    assert.strictEqual(box.length, 1);
    assert.strictEqual(box[0].textContent, '這個資料夾裡沒有找到 willy 的知識庫（找了這一層與下面兩層）');
    assert.ok(view.topRowEl.classList.contains('wwh-hidden') && view.timelineEl.classList.contains('wwh-hidden'));
    assert.strictEqual(s.exec.calls.length, 0);
    assert.deepStrictEqual(s.watched, [], '沒有知識庫就不看任何夾');
  });
});

// ---- 單一知識庫在子夾（前綴 willy）----

test('驗收 5：kb 的 cwd 是 <vault>/willy；findKb 拿知識庫根比 projectPath', async () => {
  const records = (vault, root) => [
    { scope: 'user', installPath: path.join(root, 'inst-user'), version: '0.37.0' },
    { scope: 'project', installPath: path.join(root, 'inst-proj'), version: '0.37.0', projectPath: path.join(vault, 'willy') },
  ];
  await withSetup({ kbs: ['willy'], records }, async (s) => {
    await s.start();
    assert.deepStrictEqual(s.plugin.roots, ['willy']);
    assert.strictEqual(s.plugin.current, 'willy');
    assert.strictEqual(s.plugin.kbInfo.projectPath, path.join(s.vault, 'willy'), 'findKb 收到的 vaultPath 是知識庫根');
    const calls = s.kbCalls();
    assert.ok(calls.length >= 1);
    assert.deepStrictEqual(calls[0].args.slice(0, 2), ['home', '--json']);
    for (const c of calls) assert.strictEqual(c.cwd, path.join(s.vault, 'willy'));
    assert.strictEqual(s.plugin.home.cheer, '這是 willy');
  });
});

test('驗收 6：kb 回的庫內路徑交給 Obsidian 前加上前綴', async () => {
  const reply = (args) => (args[0] === 'lookup' ? { synthesis: '01 顧客/王先生/王先生.md' } : undefined);
  await withSetup({ kbs: ['willy'], reply, store: { 'willy/系統/日程.md': '# 日程\n- a\n- 2026-11-20 到期 交屋\n', 'willy/系統/帳.md': '# 帳\n- x\n- 收 100\n' } }, async (s) => {
    await s.start();
    await s.plugin.openItem({ card: { path: '01 顧客/李小姐/李小姐.md' } });
    s.plugin.openCard({ card: 'f-1a2b', card_path: '檔案索引/報價/報價-1a2b.md' });
    await s.plugin.openSynthesis('王先生');
    await s.plugin.openPageLine('系統/帳.md', '收 100');
    await s.plugin.openAgendaLine({ date: '2026-11-20', text: '交屋', kind: 'deadline' });
    assert.deepStrictEqual(s.st.opened, ['willy/01 顧客/李小姐/李小姐', 'willy/檔案索引/報價/報價-1a2b', 'willy/01 顧客/王先生/王先生', 'willy/系統/帳', 'willy/系統/日程']);
  });
});

test('驗收 7：便條讀寫的是 willy/系統/隨手記.md', async () => {
  await withSetup({ kbs: ['willy'], store: { 'willy/系統/隨手記.md': '庫裡的便條', '系統/隨手記.md': '她自己根目錄的' } }, async (s) => {
    const view = await s.start();
    assert.strictEqual(s.plugin.ui.note.text, '庫裡的便條');
    assert.strictEqual(view.noteTextEl.value, '庫裡的便條');
    s.plugin.noteEdited('改過的');
    assert.strictEqual(await s.plugin.flushNote(), true);
    assert.deepStrictEqual(s.writes, [['willy/系統/隨手記.md', '改過的']]);
    assert.strictEqual(s.store['系統/隨手記.md'], '她自己根目錄的');
  });
});

test('驗收 8：改 willy/系統/日程.md 一行後離開 → renders apply 系統/日程.md，cwd 是 <vault>/willy', async () => {
  await withSetup({ kbs: ['willy'], reply: (args) => (args[0] === 'renders' ? { applied: [], carried: [] } : undefined) }, async (s) => {
    await s.start();
    await editAndLeave(s, 'willy/系統/日程.md');
    const applies = s.kbCalls().filter((c) => c.args[0] === 'renders');
    assert.deepStrictEqual(applies, [{ args: ['renders', 'apply', '系統/日程.md', '--json'], cwd: path.join(s.vault, 'willy') }]);
    // 她自己 vault 根的 系統/日程.md 不是任何知識庫的頁：不叫 kb
    await editAndLeave(s, '系統/日程.md');
    assert.strictEqual(s.kbCalls().filter((c) => c.args[0] === 'renders').length, 1);
  });
});

test('驗收 9：willy/總目錄.md 變唯讀；vault 根她自己的 總目錄.md 不會，也不叫 kb', async () => {
  await withSetup({ kbs: ['willy'] }, async (s) => {
    await s.start();
    const made = [];
    s.plugin.makeReadOnly = (p) => made.push(p);
    const before = s.exec.calls.length;
    s.plugin.onFileOpen({ path: '總目錄.md' });
    s.plugin.onFileOpen({ path: '系統/工作日誌/2026-11.md' });
    assert.deepStrictEqual(made, []);
    s.plugin.onFileOpen({ path: 'willy/總目錄.md' });
    s.plugin.onFileOpen({ path: 'willy/系統/工作日誌/2026-11.md' });
    assert.deepStrictEqual(made, ['willy/總目錄.md', 'willy/系統/工作日誌/2026-11.md']);
    await wait();
    assert.strictEqual(s.exec.calls.length, before);
    // 「這頁剛被更新了」的提示也只給知識庫裡的頁
    s.leaves.markdown.push({ view: { file: { path: '總目錄.md' } } }, { view: { file: { path: 'willy/總目錄.md' } } });
    s.plugin.lastKbAt = 0; // 不是外掛自己剛叫 kb 改的
    s.plugin.onVaultModify({ path: '總目錄.md' });
    s.plugin.onVaultModify({ path: 'willy/總目錄.md' });
    await wait();
    assert.deepStrictEqual(s.st.toasts, [lib.UPDATED_TEXT]);
  });
});

test('驗收 10：知識庫裡的綜合卡叫 entity panel；vault 根檔頭剛好有 編號: e-1 的筆記不叫', async () => {
  const caches = {
    'willy/01 顧客/李小姐/李小姐.md': { frontmatter: { 編號: 'e-1a2b' } },
    '筆記.md': { frontmatter: { 編號: 'e-1' } },
    'willy/系統/日程.md': { frontmatter: { 編號: 'e-2' } },
  };
  const reply = (args) => (args[0] === 'entity' ? { agenda: [{ line: '11/20 到期：交屋', page: '系統/日程.md', match: '交屋' }], money: null } : undefined);
  await withSetup({ kbs: ['willy'], caches, reply, store: { 'willy/系統/日程.md': '# 日程\n- 交屋\n' } }, async (s) => {
    await s.start();
    await s.plugin.showPanel({ path: '筆記.md' });
    await s.plugin.showPanel({ path: 'willy/系統/日程.md' });
    assert.strictEqual(s.kbCalls().filter((c) => c.args[0] === 'entity').length, 0);
    await s.plugin.showPanel({ path: 'willy/01 顧客/李小姐/李小姐.md' });
    assert.deepStrictEqual(s.kbCalls().filter((c) => c.args[0] === 'entity'), [{ args: ['entity', 'panel', 'e-1a2b', '--json'], cwd: path.join(s.vault, 'willy') }]);
    // 點那段的一行：開的是同一個庫的頁
    const box = s.plugin.buildPanel(s.plugin.panels.get('willy/01 顧客/李小姐/李小姐.md'));
    byClass(box, 'wwh-panel-line')[0].fire('click');
    await wait();
    assert.deepStrictEqual(s.st.opened, ['willy/系統/日程']);
  });
});

test('驗收 11：只有一個知識庫沒有下拉選單；開在上層不開「偵測所有副檔名」、不自動開首頁', async () => {
  await withSetup({ kbs: ['willy'] }, async (s) => {
    const view = await s.start();
    assert.strictEqual(byTag(view.root, 'select').length, 0);
    assert.deepStrictEqual(s.st.configs, {});
    assert.strictEqual(s.st.activated, 0);
    assert.strictEqual(s.plugin.atVaultRoot(), false);
  });
});

test('驗收 12：document.head 多一個 <style> 藏 willy/檔案索引 與 willy/CLAUDE.md；卸載後拿掉', async () => {
  await withSetup({ kbs: ['willy'] }, async (s) => {
    const head = globalThis.document.head;
    const before = head.children.length;
    await s.start();
    const styles = byTag(head, 'style');
    assert.strictEqual(head.children.length, before + 1);
    const css = styles[styles.length - 1].textContent;
    assert.ok(css.includes('.nav-folder-title[data-path="willy/檔案索引"]'));
    assert.ok(css.includes('.nav-file-title[data-path="willy/CLAUDE.md"]'));
    assert.ok(!css.includes('data-path="檔案索引"'), '完全相符，不藏她自己別處同名的夾');
    s.plugin.onunload();
    assert.strictEqual(head.children.length, before);
  });
  assert.strictEqual(lib.treeHideCss(['']), '');
  assert.ok(lib.treeHideCss(['a/b', 'c']).includes('data-path="a/b/CLAUDE.md"') && lib.treeHideCss(['a/b', 'c']).includes('data-path="c/檔案索引"'));
});

test('驗收 13：看的是 <vault>/willy/.system 與 <vault>/willy/.git；上層的 .git 不看', async () => {
  await withSetup({ kbs: ['willy'], dirs: ['.git'] }, async (s) => {
    await s.start();
    assert.deepStrictEqual(s.watched, [path.join(s.vault, 'willy', '.system')], '<vault>/.git 在、willy/.git 不在：不看任何 .git');
  });
  await withSetup({ kbs: ['willy'], dirs: ['.git', 'willy/.git'] }, async (s) => {
    await s.start();
    assert.deepStrictEqual(s.watched, [path.join(s.vault, 'willy', '.system'), path.join(s.vault, 'willy', '.git')]);
  });
});

// ---- 兩個知識庫（A、B）----

const NOTES = { 'A/系統/隨手記.md': 'A 的便條', 'B/系統/隨手記.md': 'B 的便條' };

async function pick(view, value) {
  const sel = byTag(view.root, 'select')[0];
  sel.value = value;
  sel.fire('change');
  await wait(120);
}

test('驗收 14：兩個知識庫有下拉選單、兩個選項；data.json 沒記時選 A', async () => {
  await withSetup({ kbs: ['B', 'A'], store: NOTES }, async (s) => {
    const view = await s.start();
    const sels = byTag(view.root, 'select');
    assert.strictEqual(sels.length, 1);
    assert.strictEqual(view.topEl.children[0], sels[0], '在最上面那一列的最左邊');
    assert.deepStrictEqual(byTag(sels[0], 'option').map((x) => [x.value, x.textContent]), [['A', 'A'], ['B', 'B']]);
    assert.strictEqual(sels[0].value, 'A');
    assert.strictEqual(s.plugin.current, 'A');
    assert.strictEqual(s.plugin.home.cheer, '這是 A');
    assert.deepStrictEqual(s.st.configs, {});
    assert.strictEqual(s.st.activated, 0);
  });
});

test('驗收 15：選 B 之後 kb home 的 cwd 是 <vault>/B、data.json 記 current、重新載入還是 B；監看跟著換', async () => {
  await withSetup({ kbs: ['A', 'B'], store: NOTES }, async (s) => {
    const view = await s.start();
    s.plugin.ui.drawer.open = true;
    s.plugin.ui.drawer.stack = ['王先生'];
    s.plugin.ui.search.active = true;
    s.plugin.ui.search.q = '報價';
    const n = s.exec.calls.length;
    await pick(view, 'B');
    const after = s.kbCalls().slice(n);
    assert.ok(after.length >= 1);
    for (const c of after) assert.strictEqual(c.cwd, path.join(s.vault, 'B'));
    assert.strictEqual(after[0].args[0], 'home');
    assert.strictEqual(s.plugin.home.cheer, '這是 B');
    assert.strictEqual(s.st.saves[s.st.saves.length - 1].current, 'B');
    assert.deepStrictEqual([s.plugin.ui.drawer.open, s.plugin.ui.drawer.stack, s.plugin.ui.search.active, s.plugin.ui.search.q], [false, [], false, '']);
    assert.deepStrictEqual(s.closed, [path.join(s.vault, 'A', '.system')]);
    assert.strictEqual(s.watched[s.watched.length - 1], path.join(s.vault, 'B', '.system'));
    assert.strictEqual(byTag(view.root, 'select')[0].value, 'B');
    const again = s.makePlugin(s.st.saves[s.st.saves.length - 1]);
    await again.onload();
    assert.strictEqual(again.current, 'B');
    again.onunload();
  });
});

test('驗收 16：在 A 的便條打了字還沒存就切到 B：字寫進 A，B 的便條是 B 自己的', async () => {
  await withSetup({ kbs: ['A', 'B'], store: NOTES }, async (s) => {
    const view = await s.start();
    assert.strictEqual(view.noteTextEl.value, 'A 的便條');
    s.plugin.noteEdited('在 A 打到一半');
    await pick(view, 'B');
    assert.deepStrictEqual(s.writes, [['A/系統/隨手記.md', '在 A 打到一半']]);
    assert.strictEqual(s.store['B/系統/隨手記.md'], 'B 的便條');
    assert.strictEqual(s.plugin.ui.note.text, 'B 的便條');
    assert.strictEqual(view.noteTextEl.value, 'B 的便條');
    assert.strictEqual(s.plugin.ui.note.dirty, false);
  });
});

test('驗收 17：切換當下 A 的 kb home 還沒回來，回來之後畫面仍是 B 的', async () => {
  await withSetup({ kbs: ['A', 'B'], store: NOTES }, async (s) => {
    const view = await s.start();
    let release = null;
    s.plugin.runner.run = () => new Promise((r) => { release = () => r({ code: 0, stdout: JSON.stringify(Object.assign(homeOf('/x/A'), { cheer: 'A 的舊結果' })), stderr: '' }); });
    const slow = s.plugin.refresh();
    await wait(20);
    assert.ok(release, 'A 的 kb home 還在路上');
    const switching = s.plugin.switchRoot('B');
    await wait(20);
    release();
    await slow;
    await switching;
    await wait();
    assert.strictEqual(s.plugin.current, 'B');
    assert.strictEqual(s.plugin.home.cheer, '這是 B');
    assert.match(view.root.textContent, /這是 B/);
    assert.doesNotMatch(view.root.textContent, /A 的舊結果/);
  });
});

test('驗收 18：首頁選 A、改 B/系統/日程.md → renders apply 的 cwd 是 <vault>/B', async () => {
  await withSetup({ kbs: ['A', 'B'], reply: (args) => (args[0] === 'renders' ? { applied: [], carried: [] } : undefined) }, async (s) => {
    await s.start();
    assert.strictEqual(s.plugin.current, 'A');
    await editAndLeave(s, 'B/系統/日程.md');
    assert.deepStrictEqual(s.kbCalls().filter((c) => c.args[0] === 'renders'), [{ args: ['renders', 'apply', '系統/日程.md', '--json'], cwd: path.join(s.vault, 'B') }]);
    assert.strictEqual(s.plugin.current, 'A', '首頁看的不變');
  });
});

test('驗收 19：首頁選 A、作用中的檔在 B，從協定進來開原檔 → lookup 的 cwd 是 B、「最近」記在 roots.B', async () => {
  const reply = (args) => (args[0] === 'lookup' ? { card_path: '檔案索引/報價/x-1a2b.md' } : undefined);
  await withSetup({ kbs: ['A', 'B'], reply }, async (s) => {
    await s.start();
    s.st.activeFile = { path: 'B/檔案索引/報價/x-1a2b.md' };
    await s.plugin.protocols[OPEN]({ id: 'f-1a2b' });
    await wait();
    assert.deepStrictEqual(s.kbCalls().filter((c) => c.args[0] === 'lookup'), [{ args: ['lookup', '--id', 'f-1a2b', '--json'], cwd: path.join(s.vault, 'B') }]);
    assert.deepStrictEqual(s.plugin.data.roots.B.opened.map((x) => x.card), ['f-1a2b']);
    assert.ok(!s.plugin.data.roots.A || s.plugin.data.roots.A.opened.length === 0);
    assert.ok(!('opened' in s.st.saves[s.st.saves.length - 1]), '最上層不再寫 opened');
    assert.deepStrictEqual(s.st.opened, ['B/檔案索引/報價/x-1a2b'], '沒有原檔可開，退一步開 B 的卡');
    // 作用中的檔不在任何庫裡、或沒有作用中的檔：用首頁目前看的
    s.st.activeFile = { path: '她的筆記.md' };
    await s.plugin.protocols[OPEN]({ id: 'f-1a2b' });
    s.st.activeFile = null;
    await s.plugin.protocols[OPEN]({ id: 'f-1a2b' });
    await wait();
    assert.deepStrictEqual(s.kbCalls().filter((c) => c.args[0] === 'lookup').map((c) => path.basename(c.cwd)), ['B', 'A', 'A']);
    // 首頁自己叫的用目前看的
    await s.plugin.openById('f-1a2b');
    assert.strictEqual(path.basename(s.kbCalls().filter((c) => c.args[0] === 'lookup').pop().cwd), 'A');
    assert.deepStrictEqual(s.plugin.data.roots.A.opened.map((x) => x.card), ['f-1a2b']);
  });
});

test('驗收 20：A、B 各有一張 f-1a2b：〔f-1a2b〕只連到同一個庫的 檔案索引/；不在任何庫裡的頁不動', async () => {
  const files = [{ path: 'A/檔案索引/報價/甲-1a2b.md' }, { path: 'B/檔案索引/合約/乙-1a2b.md' }, { path: '檔案索引/她的-1a2b.md' }];
  const caches = {
    'A/檔案索引/報價/甲-1a2b.md': { frontmatter: { 編號: 'f-1a2b', 標題: '甲' } },
    'B/檔案索引/合約/乙-1a2b.md': { frontmatter: { 編號: 'f-1a2b', 標題: '乙' } },
    '檔案索引/她的-1a2b.md': { frontmatter: { 編號: 'f-1a2b', 標題: '她的' } },
  };
  await withSetup({ kbs: ['A', 'B'], files, caches }, async (s) => {
    await s.start();
    const p = s.plugin;
    assert.strictEqual(p.cardPathOf('f-1a2b', p.rootOf('A/01 顧客/李/李.md')), 'A/檔案索引/報價/甲-1a2b.md');
    assert.strictEqual(p.cardPathOf('f-1a2b', p.rootOf('B/01 顧客/李/李.md')), 'B/檔案索引/合約/乙-1a2b.md');
    assert.strictEqual(p.cardTitleOf('f-1a2b', 'B'), '乙');
    assert.strictEqual(p.rootOf('她的筆記.md'), null);
    // 閱讀模式的後處理：照那一頁（ctx.sourcePath）所在的庫
    const { FakeEl, FakeText } = require('./helpers/fakedom');
    const linkify = (sourcePath) => {
      const para = new FakeEl('p');
      const t = new FakeText('見〔f-1a2b〕');
      para.appendChild(t);
      para.replaceChild = function (frag, node) {
        const i = this.children.indexOf(node);
        this.children.splice(i, 1, ...frag.children);
        for (const k of frag.children) k.parentNode = this;
      };
      para.closest = () => null;
      const root = new FakeEl('div');
      root.appendChild(para);
      root.ownerDocument = { createTreeWalker: () => { const list = [t]; return { nextNode: () => list.shift() || null }; }, createDocumentFragment: () => globalThis.document.createDocumentFragment(), createTextNode: (x) => new FakeText(x) };
      p.linkifyCardRefs(root, { sourcePath });
      return para.children.map((c) => (c.nodeType === 3 ? c.nodeValue : c.attrs.href));
    };
    assert.deepStrictEqual(linkify('A/01 顧客/李/李.md'), ['見', 'A/檔案索引/報價/甲-1a2b.md']);
    assert.deepStrictEqual(linkify('B/01 顧客/李/李.md'), ['見', 'B/檔案索引/合約/乙-1a2b.md']);
    assert.deepStrictEqual(linkify('她的筆記.md'), ['見〔f-1a2b〕']);
    // 點圖示：target 已經是 vault 路徑，不再加一次前綴
    p.cardRefIcon('f-1a2b', 'B/檔案索引/合約/乙-1a2b.md', false, 'B').fire('click');
    assert.deepStrictEqual(s.st.opened, ['B/檔案索引/合約/乙-1a2b']);
  });
});

test('驗收 21：兩個知識庫的夾名最後一段一樣，選單顯示整個前綴', async () => {
  assert.deepStrictEqual(lib.rootLabels(['willy', '客戶B/知識庫']), ['willy', '知識庫']);
  await withSetup({ kbs: ['甲/知識庫', '乙/知識庫'] }, async (s) => {
    const view = await s.start();
    assert.deepStrictEqual(byTag(byTag(view.root, 'select')[0], 'option').map((x) => x.textContent), ['乙/知識庫', '甲/知識庫']);
    assert.strictEqual(s.plugin.current, '乙/知識庫');
  });
});

// ---- vault 根就是知識庫（現況）----

test('驗收 22：vault 根就是知識庫：setConfig 有叫、首頁自動打開、沒有選單、沒有多的 <style>、路徑不加前綴', async () => {
  await withSetup({ kbs: [''], dirs: ['.git'], store: { '系統/隨手記.md': '根的便條' } }, async (s) => {
    const head = globalThis.document.head;
    const before = head.children.length;
    const view = await s.start();
    assert.deepStrictEqual(s.plugin.roots, ['']);
    assert.strictEqual(s.plugin.current, '');
    assert.strictEqual(s.st.configs.showUnsupportedFiles, true);
    assert.ok(s.st.activated >= 1, '首頁自動打開');
    assert.strictEqual(byTag(view.root, 'select').length, 0);
    assert.strictEqual(head.children.length, before);
    assert.strictEqual(s.kbCalls()[0].cwd, s.vault);
    assert.deepStrictEqual(s.watched, [path.join(s.vault, '.system'), path.join(s.vault, '.git')]);
    assert.strictEqual(s.plugin.ui.note.text, '根的便條');
    s.plugin.openPathInVault('01 顧客/李小姐/李小姐.md');
    assert.deepStrictEqual(s.st.opened, ['01 顧客/李小姐/李小姐']);
  });
});

test('開首頁時再找一次：多了一個知識庫才重畫；目前看的不見了換成第一個', async () => {
  await withSetup({ kbs: ['A'] }, async (s) => {
    const view = await s.start();
    assert.strictEqual(byTag(view.root, 'select').length, 0);
    const n = s.exec.calls.length;
    await s.plugin.activateHome();
    await wait();
    assert.strictEqual(s.exec.calls.length, n, '沒變不重畫');
    mark(path.join(s.vault, 'B'));
    await s.plugin.activateHome();
    await wait();
    assert.deepStrictEqual(s.plugin.roots, ['A', 'B']);
    assert.ok(s.exec.calls.length > n);
    view.render();
    assert.strictEqual(byTag(view.root, 'select').length, 1);
    assert.ok(globalThis.document.head.children.some((c) => c.textContent.includes('data-path="B/檔案索引"')));
    fs.rmSync(path.join(s.vault, 'A'), { recursive: true, force: true });
    await s.plugin.activateHome();
    await wait(120);
    assert.deepStrictEqual(s.plugin.roots, ['B']);
    assert.strictEqual(s.plugin.current, 'B');
    assert.strictEqual(s.plugin.home.cheer, '這是 B');
  });
});

// ---- data.json ----

test('驗收 23：舊格式讀進來，存檔寫出新格式，那幾筆在 roots[current].opened、timelineDays 還在', async () => {
  const old = { opened: [{ card: 'f-1a2b', at: '2026-11-01T00:00:00.000Z' }, { card: 'f-3c4d', at: 't' }], timelineDays: 14 };
  const got = lib.sanitizeStore(old, ['willy']);
  assert.deepStrictEqual(got, { roots: { willy: { opened: old.opened } }, current: 'willy', timelineDays: 14 });
  assert.deepStrictEqual(lib.openedOf(got, 'willy'), ['f-1a2b', 'f-3c4d']);
  assert.deepStrictEqual(lib.openedOf(got, '別的'), []);
  await withSetup({ kbs: ['willy'], data: old }, async (s) => {
    await s.start();
    const home = s.kbCalls().find((c) => c.args[0] === 'home');
    assert.deepStrictEqual(home.args.slice(home.args.indexOf('--opened'), home.args.indexOf('--opened') + 2), ['--opened', 'f-1a2b,f-3c4d']);
    await s.plugin.recordOpened('f-5e6f');
    const saved = s.st.saves[s.st.saves.length - 1];
    assert.deepStrictEqual(Object.keys(saved).sort(), ['current', 'roots', 'timelineDays']);
    assert.deepStrictEqual(saved.roots.willy.opened.map((x) => x.card), ['f-5e6f', 'f-1a2b', 'f-3c4d']);
    assert.strictEqual(saved.timelineDays, 14);
    assert.ok(!JSON.stringify(saved).includes(s.vault.replace(/\\/g, '\\\\')), '不存絕對路徑（D-019）');
  });
  // 已經不在清單裡的鍵留著；記進一個庫不動別的庫
  const two = lib.sanitizeStore({ current: 'B', roots: { A: { opened: [{ card: 'f-aa', at: 't' }] }, 搬走的: { opened: [{ card: 'f-bb', at: 't' }] } }, monthCollapsed: true }, ['A', 'B']);
  assert.strictEqual(two.current, 'B');
  assert.deepStrictEqual(Object.keys(two.roots), ['A', '搬走的']);
  assert.strictEqual(two.monthCollapsed, true);
  const rec = lib.recordOpenedIn(two, 'B', 'f-cc', 'now');
  assert.deepStrictEqual(rec.roots.B.opened, [{ card: 'f-cc', at: 'now' }]);
  assert.deepStrictEqual(rec.roots.A, two.roots.A);
  assert.strictEqual(rec.current, 'B');
});

test('驗收 24：壞資料不丟例外，當成沒有', () => {
  for (const bad of [null, 5, 'x', [], { roots: 7, current: 3, opened: 'no' }, { roots: [1, 2], current: null }, { roots: { A: 5, B: { opened: [{ card: '../x' }, 7, { card: 'f-1a', at: 3, path: 'C:/secret' }] } }, current: 9 }]) {
    const got = lib.sanitizeStore(bad, ['A', 'B']);
    assert.strictEqual(got.current, 'A', JSON.stringify(bad));
    assert.ok(got.roots && typeof got.roots === 'object' && !Array.isArray(got.roots));
    for (const k of Object.keys(got.roots)) for (const x of got.roots[k].opened) assert.match(x.card, /^f-[0-9a-f]+$/);
  }
  const got = lib.sanitizeStore({ roots: { A: 5, B: { opened: [{ card: '../x' }, 7, { card: 'f-1a', at: 3, path: 'C:/secret' }] } }, current: 9 }, ['A', 'B']);
  assert.deepStrictEqual(got, { roots: { A: { opened: [] }, B: { opened: [{ card: 'f-1a', at: '' }] } }, current: 'A' });
  assert.deepStrictEqual(lib.sanitizeStore({ current: '不在了' }, []), { roots: {} });
  assert.deepStrictEqual(lib.sanitizeStore({ current: '不在了', opened: [{ card: 'f-1a', at: 't' }] }, ['x']), { roots: { x: { opened: [{ card: 'f-1a', at: 't' }] } }, current: 'x' });
  assert.deepStrictEqual(lib.openedOf(null, 'A'), []);
  assert.deepStrictEqual(lib.recordOpenedIn({ roots: {} }, 'A', 'C:/x.pdf', 'now').roots.A.opened, []);
});

test('路徑換算：joinRoot、stripRoot、rootOfPath', () => {
  assert.strictEqual(lib.joinRoot('', '系統/日程.md'), '系統/日程.md');
  assert.strictEqual(lib.joinRoot('客戶B/知識庫', '系統/日程.md'), '客戶B/知識庫/系統/日程.md');
  assert.strictEqual(lib.stripRoot('willy', 'willy/系統/日程.md'), '系統/日程.md');
  assert.strictEqual(lib.stripRoot('willy', 'willy2/系統/日程.md'), null);
  assert.strictEqual(lib.stripRoot('', '系統\\日程.md'), '系統/日程.md');
  assert.strictEqual(lib.rootOfPath(['willy', '客戶B/知識庫'], '客戶B/知識庫/總目錄.md'), '客戶B/知識庫');
  assert.strictEqual(lib.rootOfPath(['willy'], 'willy2/總目錄.md'), null);
  assert.strictEqual(lib.rootOfPath(['willy'], 'willy'), null, '夾自己不是庫裡的檔');
  assert.strictEqual(lib.rootOfPath([''], '隨便/哪裡.md'), '');
  assert.strictEqual(lib.rootOfPath([], 'a.md'), null);
});
