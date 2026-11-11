'use strict';
const test = require('node:test');
const assert = require('node:assert');
const path = require('node:path');
const { loadMain, fakeExecFile } = require('./helpers/env');

const env = loadMain();
const lib = env.lib;
test.after(() => env.restore());

function installedFile(plugins) {
  return JSON.stringify({ version: 2, plugins });
}

function rec(extra) {
  return Object.assign({ scope: 'user', installPath: '/plugins/wiki-with-willy/0.28.0', version: '0.28.0' }, extra);
}

test('找 kb：讀 CLAUDE_CONFIG_DIR 底下的 installed_plugins.json', () => {
  let asked = null;
  const got = lib.findKb({
    env: { CLAUDE_CONFIG_DIR: '/cfg' },
    home: '/home/u',
    vaultPath: '/vault',
    readFile: (p) => {
      asked = p;
      return installedFile({ 'wiki-with-willy@market': [rec()] });
    },
    exists: () => true,
  });
  assert.strictEqual(asked, path.join('/cfg', 'plugins', 'installed_plugins.json'));
  assert.strictEqual(got.ok, true);
  assert.strictEqual(got.kbPath, path.join('/plugins/wiki-with-willy/0.28.0', 'scripts', 'kb.py'));
});

test('找 kb：沒有 CLAUDE_CONFIG_DIR 就看家目錄的 .claude', () => {
  let asked = null;
  lib.findKb({
    env: {},
    home: '/home/u',
    vaultPath: '/vault',
    readFile: (p) => {
      asked = p;
      return installedFile({});
    },
    exists: () => true,
  });
  assert.strictEqual(asked, path.join('/home/u', '.claude', 'plugins', 'installed_plugins.json'));
});

test('找 kb：多筆時先挑 projectPath 等於知識庫的', () => {
  const plugins = {
    'wiki-with-willy@market': [
      rec({ scope: 'user', installPath: '/p/user' }),
      rec({ scope: 'local', installPath: '/p/other', projectPath: '/other/vault' }),
      rec({ scope: 'local', installPath: '/p/mine', projectPath: 'C:\\Data\\Vault' }),
    ],
  };
  const got = lib.findKb({
    env: {},
    home: '/h',
    vaultPath: 'c:/data/vault/',
    platform: 'win32',
    readFile: () => installedFile(plugins),
    exists: () => true,
  });
  assert.strictEqual(got.installPath, '/p/mine');
});

test('找 kb：沒有對上知識庫的就挑 scope user，再沒有就挑最後一筆', () => {
  const plugins = {
    'wiki-with-willy@market': [
      rec({ scope: 'local', installPath: '/p/a', projectPath: '/x' }),
      rec({ scope: 'user', installPath: '/p/user' }),
      rec({ scope: 'local', installPath: '/p/b', projectPath: '/y' }),
    ],
  };
  const base = { env: {}, home: '/h', vaultPath: '/vault', readFile: () => installedFile(plugins), exists: () => true };
  assert.strictEqual(lib.findKb(base).installPath, '/p/user');

  const noUser = { 'wiki-with-willy@market': [rec({ scope: 'local', installPath: '/p/a', projectPath: '/x' }), rec({ scope: 'local', installPath: '/p/b', projectPath: '/y' })] };
  assert.strictEqual(lib.findKb(Object.assign({}, base, { readFile: () => installedFile(noUser) })).installPath, '/p/b');
});

test('找 kb：kb.py 不在的那筆跳過；都不在回 no-kb', () => {
  const plugins = { 'wiki-with-willy@m': [rec({ installPath: '/gone' }), rec({ installPath: '/here' })] };
  const exists = (p) => p.includes('here');
  const got = lib.findKb({ env: {}, home: '/h', vaultPath: '/v', readFile: () => installedFile(plugins), exists });
  assert.strictEqual(got.installPath, '/here');
  const none = lib.findKb({ env: {}, home: '/h', vaultPath: '/v', readFile: () => installedFile(plugins), exists: () => false });
  assert.deepStrictEqual([none.ok, none.reason], [false, 'no-kb']);
});

test('找 kb：讀不到檔、沒裝 wiki-with-willy 都回 ok:false', () => {
  const missing = lib.findKb({ env: {}, home: '/h', vaultPath: '/v', readFile: () => { throw new Error('ENOENT'); }, exists: () => true });
  assert.strictEqual(missing.ok, false);
  const other = lib.findKb({ env: {}, home: '/h', vaultPath: '/v', readFile: () => installedFile({ 'other@m': [rec()] }), exists: () => true });
  assert.deepStrictEqual([other.ok, other.reason], [false, 'not-installed']);
  const broken = lib.findKb({ env: {}, home: '/h', vaultPath: '/v', readFile: () => 'not json', exists: () => true });
  assert.strictEqual(broken.ok, false);
});

test('每個 kb 呼叫都是 kb.py 後面緊接 --via obsidian', () => {
  const argv = lib.buildKbArgs('/k/kb.py', ['agenda', 'done', 'a-1'], []);
  assert.deepStrictEqual(argv, ['/k/kb.py', '--via', 'obsidian', 'agenda', 'done', 'a-1']);
  assert.deepStrictEqual(lib.buildKbArgs('/k/kb.py', ['x'], ['-3']), ['-3', '/k/kb.py', '--via', 'obsidian', 'x']);
});

test('叫 kb：execFile、windowsHide、cwd 是知識庫、PYTHONIOENCODING=utf-8、--via obsidian', async () => {
  const exec = fakeExecFile(() => ({ code: 0, stdout: '{"schema":"willy-home/1"}', stderr: '' }));
  const runner = lib.createKbRunner({ execFile: exec, kbPath: '/k/kb.py', cwd: '/vault', env: { PATH: 'x' }, platform: 'win32' });
  // 首頁、查實體、搜尋、一般動作：全部都帶 --via obsidian
  for (const args of [lib.homeArgs([]), ['lookup', '王先生', '--json'], lib.findArgs('王先生 報價'), ['agenda', 'done', 'a-1']]) {
    await runner.run(args);
  }
  assert.strictEqual(exec.calls.length, 4);
  for (const c of exec.calls) {
    assert.strictEqual(c.file, 'python');
    assert.strictEqual(c.argv[0], '/k/kb.py');
    assert.deepStrictEqual(c.argv.slice(1, 3), ['--via', 'obsidian']);
    assert.strictEqual(c.options.windowsHide, true);
    assert.strictEqual(c.options.cwd, '/vault');
    assert.strictEqual(c.options.env.PYTHONIOENCODING, 'utf-8');
    assert.strictEqual(c.options.env.PATH, 'x');
  }
  assert.deepStrictEqual(exec.calls[0].argv.slice(3), ['home', '--json']);
  assert.deepStrictEqual(exec.calls[2].argv.slice(3), ['find', '王先生 報價', '--json']);
});

test('python 找不到就換 py -3，之後記住用哪個', async () => {
  const exec = fakeExecFile((file) => {
    if (file === 'python') throw Object.assign(new Error('spawn python ENOENT'), { code: 'ENOENT' });
    return { code: 0, stdout: 'ok', stderr: '' };
  });
  const runner = lib.createKbRunner({ execFile: exec, kbPath: '/k/kb.py', cwd: '/v', env: {}, platform: 'win32' });
  const r1 = await runner.run(['version']);
  assert.strictEqual(r1.code, 0);
  assert.deepStrictEqual(exec.calls.map((c) => c.file), ['python', 'py']);
  assert.deepStrictEqual(exec.calls[1].argv.slice(0, 4), ['-3', '/k/kb.py', '--via', 'obsidian']);
  await runner.run(['version']);
  assert.deepStrictEqual(exec.calls.map((c) => c.file), ['python', 'py', 'py']);
});

test('兩個 Python 都沒有：回一句白話、不丟錯', async () => {
  const exec = fakeExecFile(() => {
    throw Object.assign(new Error('x'), { code: 'ENOENT' });
  });
  const runner = lib.createKbRunner({ execFile: exec, kbPath: '/k/kb.py', cwd: '/v', env: {}, platform: 'win32' });
  const r = await runner.run(['version']);
  assert.notStrictEqual(r.code, 0);
  assert.match(r.stderr, /找不到 Python/);
});

test('結果分三種：exit 0、exit 3（kb 的句子原樣）、其他（沒做成：stderr 第一行）', () => {
  assert.deepStrictEqual(lib.classify({ code: 0, stdout: '', stderr: '' }), { kind: 'ok' });
  assert.deepStrictEqual(lib.classify({ code: 3, stdout: '\n日程裡沒有這一條\n多的行\n', stderr: '' }), { kind: 'refused', message: '日程裡沒有這一條' });
  assert.deepStrictEqual(lib.classify({ code: 3, stdout: '', stderr: 'stderr 的句子\n' }), { kind: 'refused', message: 'stderr 的句子' });
  assert.deepStrictEqual(lib.classify({ code: 1, stdout: '', stderr: 'Traceback…\nValueError: x\n' }), { kind: 'failed', message: '沒做成：Traceback…' });
});

test('Plugin 載入：找到 kb 就建 runner，叫 kb home 把首頁畫出來', async () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wwh-'));
  const vault = path.join(root, 'vault');
  const cfg = path.join(root, 'cfg');
  const inst = path.join(root, 'inst');
  fs.mkdirSync(path.join(vault, '.system'), { recursive: true });
  fs.writeFileSync(path.join(vault, '.system', 'sources.json'), '{}\n'); // 知識庫的記號（#66 乙：vault 根有記號才是知識庫）
  fs.mkdirSync(path.join(cfg, 'plugins'), { recursive: true });
  fs.mkdirSync(path.join(inst, 'scripts'), { recursive: true });
  fs.writeFileSync(path.join(inst, 'scripts', 'kb.py'), '# fake\n');
  fs.writeFileSync(path.join(cfg, 'plugins', 'installed_plugins.json'), installedFile({ 'wiki-with-willy@m': [rec({ installPath: inst })] }));
  const saved = process.env.CLAUDE_CONFIG_DIR;
  process.env.CLAUDE_CONFIG_DIR = cfg;
  const homeJson = { schema: 'willy-home/1', version: '0.28.0', today: '2026-10-30', cheer: '今天也辛苦了', counts: {}, timeline: { from: '2026-10-23', to: '2026-12-31', rows: [] }, todo: {}, confirm: [], others: [], recent: [] };
  const exec = fakeExecFile(() => ({ code: 0, stdout: JSON.stringify(homeJson), stderr: '' }));
  const configs = {};
  let layoutCb = null;
  const leaves = [];
  const app = {
    vault: { adapter: { getBasePath: () => vault }, setConfig: (k, v) => { configs[k] = v; }, on: () => ({}), getMarkdownFiles: () => [] },
    workspace: { on: () => ({}), onLayoutReady: (cb) => { layoutCb = cb; }, getLeavesOfType: () => leaves, getActiveViewOfType: () => null, getLeaf: () => ({ setViewState: async () => {} }), revealLeaf: () => {} },
    metadataCache: {},
  };
  const origReg = env.Plugin.prototype.registerInterval;
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0', dir: '.obsidian/plugins/wiki-with-willy' });
  plugin.execFileOverride = exec;
  plugin.registerInterval = (id) => clearInterval(id);
  plugin.registerDomEvent = () => {};
  try {
    await plugin.onload();
    assert.strictEqual(plugin.kbInfo.ok, true);
    assert.strictEqual(configs.showUnsupportedFiles, true);
    const view = new lib.HomeView({}, plugin);
    view.build();
    leaves.push({ view });
    layoutCb();
    await new Promise((r) => setTimeout(r, 80));
    assert.ok(exec.calls.length >= 1);
    assert.deepStrictEqual(exec.calls[0].argv.slice(1, 5), ['--via', 'obsidian', 'home', '--json']);
    assert.strictEqual(plugin.home.cheer, '今天也辛苦了');
    assert.match(view.root.textContent, /今天也辛苦了/);
    plugin.onunload();
  } finally {
    if (saved === undefined) delete process.env.CLAUDE_CONFIG_DIR;
    else process.env.CLAUDE_CONFIG_DIR = saved;
    env.Plugin.prototype.registerInterval = origReg;
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('Plugin 載入：找不到 kb，首頁只印一句、其他區不畫', async () => {
  const fs = require('node:fs');
  const os = require('node:os');
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'wwh-'));
  const cfg = path.join(root, 'cfg');
  fs.mkdirSync(path.join(cfg, 'plugins'), { recursive: true });
  fs.writeFileSync(path.join(cfg, 'plugins', 'installed_plugins.json'), installedFile({}));
  fs.mkdirSync(path.join(root, '.system'), { recursive: true });
  fs.writeFileSync(path.join(root, '.system', 'sources.json'), '{}\n'); // 是知識庫，只是找不到 kb（#66 乙）
  const saved = process.env.CLAUDE_CONFIG_DIR;
  process.env.CLAUDE_CONFIG_DIR = cfg;
  const app = {
    vault: { adapter: { getBasePath: () => root }, setConfig() {}, on: () => ({}), getMarkdownFiles: () => [] },
    workspace: { on: () => ({}), onLayoutReady() {}, getLeavesOfType: () => [] },
  };
  const plugin = new env.Plugin(app, { id: 'wiki-with-willy', version: '0.28.0' });
  plugin.registerInterval = (id) => clearInterval(id);
  plugin.registerDomEvent = () => {};
  try {
    await plugin.onload();
    assert.strictEqual(plugin.runner, null);
    const view = new lib.HomeView({}, plugin);
    view.build();
    view.render();
    const { byClass } = require('./helpers/fakedom');
    assert.strictEqual(byClass(view.root, 'wwh-nokb')[0].textContent, lib.NO_KB_TEXT);
    for (const cls of ['wwh-toprow', 'wwh-search', 'wwh-timeline-section', 'wwh-cols']) {
      assert.ok(byClass(view.root, cls)[0].classList.contains('wwh-hidden'), `${cls} 要藏起來`);
    }
  } finally {
    if (saved === undefined) delete process.env.CLAUDE_CONFIG_DIR;
    else process.env.CLAUDE_CONFIG_DIR = saved;
    fs.rmSync(root, { recursive: true, force: true });
  }
});
