'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadMain } = require('./helpers/env');

const env = loadMain();
const lib = env.lib;
const A = lib.actions;
test.after(() => env.restore());

function makeCtx(handler) {
  const ctx = {
    calls: [],
    toasts: [],
    refreshes: 0,
    logs: [],
    kb: async (args) => {
      ctx.calls.push(args);
      return handler(args) || { code: 0, stdout: '', stderr: '' };
    },
    toast: (text, extra) => {
      ctx.toasts.push({ text, undo: extra && extra.undo });
    },
    refresh: () => {
      ctx.refreshes += 1;
    },
    log: (m) => ctx.logs.push(m),
  };
  return ctx;
}

const ok = (stdout) => ({ code: 0, stdout: stdout || '', stderr: '' });

test('打勾 done，復原 reopen', async () => {
  const ctx = makeCtx(() => ok('已記成完成：交水電圖'));
  const r = await lib.performAction(ctx, A.done({ id: 'a-1', end: '2026-11-05' }));
  assert.deepStrictEqual(ctx.calls[0], ['agenda', 'done', 'a-1']);
  assert.strictEqual(ctx.toasts[0].text, '已記成完成：交水電圖');
  assert.ok(r.ok && ctx.toasts[0].undo);
  await ctx.toasts[0].undo();
  assert.deepStrictEqual(ctx.calls[1], ['agenda', 'reopen', 'a-1']);
});

test('重複日程打勾會跳到下一次，復原改回原日期', async () => {
  const ctx = makeCtx(() => ok('已記成完成這一次：繳費，下次 2026-12-05'));
  await lib.performAction(ctx, A.done({ id: 'a-r', end: '2026-11-05', repeat: '每月' }));
  await ctx.toasts[0].undo();
  assert.deepStrictEqual(ctx.calls[1], ['agenda', 'edit', 'a-r', '--date', '2026-11-05']);
});

test('改日期、時間：只送有變的欄位，復原改回原值', async () => {
  const item = { id: 'a-2', end: '2026-11-10', time: '09:00' };
  const a = A.edit(item, { date: '2026-11-17', time: '09:00' });
  assert.deepStrictEqual(a.args, ['agenda', 'edit', 'a-2', '--date', '2026-11-17']);
  const ctx = makeCtx(() => ok('已改：…'));
  await lib.performAction(ctx, a);
  await ctx.toasts[0].undo();
  assert.deepStrictEqual(ctx.calls[1], ['agenda', 'edit', 'a-2', '--date', '2026-11-10']);

  const both = A.edit(item, { date: '2026-11-17', time: '14:30' });
  assert.deepStrictEqual(both.args, ['agenda', 'edit', 'a-2', '--date', '2026-11-17', '--time', '14:30']);
  assert.deepStrictEqual(both.undo().args, ['agenda', 'edit', 'a-2', '--date', '2026-11-10', '--time', '09:00']);

  assert.strictEqual(A.edit(item, { date: '2026-11-10', time: '09:00' }), null, '沒變就不送');
  // 原本沒有時間：加上時間沒辦法用 edit 清掉，那一項不復原
  const noTime = A.edit({ id: 'a-3', end: '2026-11-10' }, { time: '10:00' });
  assert.strictEqual(noTime.undo, null);
});

test('新增日程：復原 = 取消新的那一條', async () => {
  const ctx = makeCtx(() => ok(JSON.stringify({ item: { id: 'a-new', text: '訂窗簾' }, created: true })));
  await lib.performAction(ctx, A.add({ kind: '到期', date: '2026-11-12', text: '訂窗簾', time: '10:00', entities: ['信義王'] }));
  assert.deepStrictEqual(ctx.calls[0], ['agenda', 'add', '--kind', '到期', '--date', '2026-11-12', '--text', '訂窗簾', '--time', '10:00', '--entity', '信義王', '--json']);
  assert.match(ctx.toasts[0].text, /訂窗簾/);
  await ctx.toasts[0].undo();
  assert.deepStrictEqual(ctx.calls[1], ['agenda', 'cancel', 'a-new']);
});

test('新增日程：kb 說已經有這一條（created:false）就不給復原', async () => {
  const ctx = makeCtx(() => ok(JSON.stringify({ item: { id: 'a-old', text: 'x' }, created: false })));
  await lib.performAction(ctx, A.add({ kind: '提醒', date: '2026-11-12', text: 'x' }));
  assert.strictEqual(ctx.toasts[0].undo, null);
});

test('要你確認的選結果：照 argv 做，{name} 換成她填的，argv 是 null 的不是指令', async () => {
  assert.strictEqual(A.result({ label: '跟 Claude 說', argv: null }), null);
  const plain = A.result({ label: '是，合併', argv: ['entity', 'merge', '王先生', '--into', '王大明'], fill: null });
  assert.deepStrictEqual(plain.args, ['entity', 'merge', '王先生', '--into', '王大明']);
  assert.strictEqual(plain.undo, null);
  const filled = A.result({ label: '改叫…', argv: ['entity', 'rename', '王先生', '--to', '{name}'], fill: { name: 'name', rule: '新名字' } }, '王大明');
  assert.deepStrictEqual(filled.args, ['entity', 'rename', '王先生', '--to', '王大明']);
  const named = A.result({ argv: ['x', '{who}', '{name}'], fill: { name: 'who' } }, 'V');
  assert.deepStrictEqual(named.args, ['x', 'V', 'V']);
});

test('失敗：exit 3 把 kb 的句子原樣 toast；其他失敗 toast「沒做成：…」並寫 console', async () => {
  const refused = makeCtx(() => ({ code: 3, stdout: '日程裡沒有這一條：a-x\n', stderr: '' }));
  await lib.performAction(refused, A.done({ id: 'a-x' }));
  assert.strictEqual(refused.toasts[0].text, '日程裡沒有這一條：a-x');
  assert.strictEqual(refused.logs.length, 0);

  const broken = makeCtx(() => ({ code: 1, stdout: '', stderr: 'Traceback (most recent call last):\nKeyError\n' }));
  const r = await lib.performAction(broken, A.done({ id: 'a-x' }));
  assert.strictEqual(r.ok, false);
  assert.strictEqual(broken.toasts[0].text, '沒做成：Traceback (most recent call last):');
  assert.strictEqual(broken.logs.length, 1);
});

test('成功後重畫首頁（refresh）', async () => {
  const ctx = makeCtx(() => ok('好'));
  await lib.performAction(ctx, A.done({ id: 'a-1' }));
  assert.strictEqual(ctx.refreshes, 1);
});


test('首頁只留四個動作（D-266）：打勾、改日期時間、新增日程、回答要你確認的', () => {
  assert.deepStrictEqual(Object.keys(A).sort(), ['add', 'done', 'edit', 'result']);
  assert.strictEqual(lib.interpretCheck, undefined, '確認框拿掉，--check 的結果不再讀');
});
