'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { loadMain } = require('./helpers/env');

const env = loadMain();
const lib = env.lib;
const A = lib.actions;
test.after(() => env.restore());

function makeCtx(handler, opts) {
  const o = opts || {};
  const ctx = {
    calls: [],
    toasts: [],
    confirms: [],
    infos: [],
    refreshes: 0,
    logs: [],
    kb: async (args) => {
      ctx.calls.push(args);
      return handler(args) || { code: 0, stdout: '', stderr: '' };
    },
    toast: (text, extra) => {
      ctx.toasts.push({ text, undo: extra && extra.undo });
    },
    confirm: async (c) => {
      ctx.confirms.push(c);
      return o.answer !== false;
    },
    info: async (c) => {
      ctx.infos.push(c);
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

test('推測的記成確認：不帶欄位、不給復原', async () => {
  const ctx = makeCtx(() => ok('記成確認了：看工地'));
  await lib.performAction(ctx, A.confirmInferred({ id: 'a-4' }));
  assert.deepStrictEqual(ctx.calls[0], ['agenda', 'edit', 'a-4']);
  assert.strictEqual(ctx.toasts[0].undo, null);
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

test('取消：復原 reopen；有期間的先 --check --json 跳確認框', async () => {
  const plain = makeCtx(() => ok('已取消：11/5 交水電圖'));
  await lib.performAction(plain, A.cancel({ id: 'a-5', kind: 'deadline', text: '交水電圖' }));
  assert.strictEqual(plain.confirms.length, 0);
  assert.deepStrictEqual(plain.calls[0], ['agenda', 'cancel', 'a-5']);
  await plain.toasts[0].undo();
  assert.deepStrictEqual(plain.calls[1], ['agenda', 'reopen', 'a-5']);

  const period = makeCtx((args) => (args.includes('--check') ? ok(JSON.stringify({ effects: ['取消「施工」：連它的 2 件子項一起取消'], refuse: null })) : ok('已取消：施工')));
  await lib.performAction(period, A.cancel({ id: 'a-6', kind: 'period', text: '施工' }));
  assert.deepStrictEqual(period.calls[0], ['agenda', 'cancel', 'a-6', '--check', '--json']);
  assert.deepStrictEqual(period.confirms[0].lines, ['取消「施工」：連它的 2 件子項一起取消']);
  assert.deepStrictEqual(period.calls[1], ['agenda', 'cancel', 'a-6']);
});

test('確認框按「不要」就什麼都不做', async () => {
  const ctx = makeCtx(() => ok(JSON.stringify({ effects: ['會搬夾'], refuse: null })), { answer: false });
  const r = await lib.performAction(ctx, A.rename('王宅', '王大明宅'));
  assert.ok(r.cancelled);
  assert.strictEqual(ctx.calls.length, 1, '只跑了 --check');
  assert.strictEqual(ctx.toasts.length, 0);
});

test('--check 回 refuse：toast 那句，不跳確認框、不做', async () => {
  const ctx = makeCtx(() => ({ code: 3, stdout: JSON.stringify({ effects: [], refuse: '實體清單沒有：王宅' }), stderr: '' }));
  const r = await lib.performAction(ctx, A.rename('王宅', 'x'));
  assert.ok(r.refused);
  assert.strictEqual(ctx.toasts[0].text, '實體清單沒有：王宅');
  assert.strictEqual(ctx.confirms.length, 0);
  assert.strictEqual(ctx.calls.length, 1);
});

test('其他要處理的「不用管」：dismiss、不給復原', async () => {
  const ctx = makeCtx(() => ok('已記成不用管'));
  await lib.performAction(ctx, A.dismiss('p-9'));
  assert.deepStrictEqual(ctx.calls[0], ['pending', 'dismiss', 'p-9']);
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

test('結案、擱置、改回進行中：先 --check，復原改回原狀態', async () => {
  const ctx = makeCtx((args) => (args.includes('--check') ? ok(JSON.stringify({ effects: ['信義王記成結案：「施工」這段期間會在今天結束'], refuse: null })) : ok('已記成結案：信義王')));
  await lib.performAction(ctx, A.progress('信義王', 'closed', 'active'));
  assert.deepStrictEqual(ctx.calls[0], ['entity', 'progress', '信義王', '結案', '--check', '--json']);
  assert.ok(ctx.confirms[0].lines[0].includes('今天結束'));
  assert.deepStrictEqual(ctx.calls[1], ['entity', 'progress', '信義王', '結案']);
  await ctx.toasts[0].undo();
  assert.deepStrictEqual(ctx.calls[2], ['entity', 'progress', '信義王', '進行中']);

  const back = A.progress('信義王', 'active', 'closed');
  assert.deepStrictEqual(back.args, ['entity', 'progress', '信義王', '進行中']);
  assert.deepStrictEqual(back.undo().args, ['entity', 'progress', '信義王', '結案']);
  const paused = A.progress('信義王', 'paused', 'ongoing');
  assert.deepStrictEqual(paused.undo().args, ['entity', 'progress', '信義王', '進行中']);
});

test('改名：先 --check，復原改回原名', async () => {
  const ctx = makeCtx((args) => (args.includes('--check') ? ok(JSON.stringify({ effects: ['王先生改名叫王大明：夾、綜合卡、12 張檔案卡跟著改'], refuse: null })) : ok('已改名：王先生 → 王大明')));
  await lib.performAction(ctx, A.rename('王先生', '王大明'));
  assert.deepStrictEqual(ctx.calls[0], ['entity', 'rename', '王先生', '--to', '王大明', '--check', '--json']);
  assert.deepStrictEqual(ctx.calls[1], ['entity', 'rename', '王先生', '--to', '王大明']);
  await ctx.toasts[0].undo();
  assert.deepStrictEqual(ctx.calls[2], ['entity', 'rename', '王大明', '--to', '王先生']);
});

test('合併：先 --check，復原叫 kb versions revert（不是相反的指令）', async () => {
  const ctx = makeCtx((args) => {
    if (args.includes('--check')) return ok(JSON.stringify({ effects: ['王先生併進王大明'], refuse: null }));
    if (args[0] === 'versions') return ok('已退回');
    return ok('已合併：王先生 併進 王大明（王先生記成別名）');
  });
  await lib.performAction(ctx, A.merge('王先生', '王大明'));
  assert.deepStrictEqual(ctx.calls[0], ['entity', 'merge', '王先生', '--into', '王大明', '--check', '--json']);
  assert.deepStrictEqual(ctx.calls[1], ['entity', 'merge', '王先生', '--into', '王大明']);
  await ctx.toasts[0].undo();
  assert.deepStrictEqual(ctx.calls[2], ['versions', 'revert']);
  assert.strictEqual(ctx.toasts[1].text, '已退回');
});

test('合併的復原被 D-508 擋住：拒絕句印在框裡，不是 toast', async () => {
  const refusal = '王大明這一頁之後又被改過，不能整個退回';
  const ctx = makeCtx((args) => {
    if (args[0] === 'versions') return { code: 3, stdout: `${refusal}\n`, stderr: '' };
    if (args.includes('--check')) return ok(JSON.stringify({ effects: ['x'], refuse: null }));
    return ok('已合併');
  });
  await lib.performAction(ctx, A.merge('王先生', '王大明'));
  const before = ctx.toasts.length;
  await ctx.toasts[0].undo();
  assert.strictEqual(ctx.infos.length, 1);
  assert.deepStrictEqual(ctx.infos[0].lines, [refusal]);
  assert.strictEqual(ctx.toasts.length, before);
});

test('加、拿掉別名：復原是相反', async () => {
  const add = A.alias('王大明', '王先生', 'add');
  assert.deepStrictEqual(add.args, ['entity', 'alias', '王大明', '--add', '王先生']);
  assert.deepStrictEqual(add.undo().args, ['entity', 'alias', '王大明', '--remove', '王先生']);
  const rm = A.alias('王大明', '王先生', 'remove');
  assert.deepStrictEqual(rm.args, ['entity', 'alias', '王大明', '--remove', '王先生']);
  assert.deepStrictEqual(rm.undo().args, ['entity', 'alias', '王大明', '--add', '王先生']);
});

test('改標籤：復原改回原標籤；原本沒有的 = 欄=', async () => {
  const t = A.tag('王大明', '階段', ['施工中', '請款'], ['簽約']);
  assert.deepStrictEqual(t.args, ['entity', 'tag', '王大明', '階段=施工中,請款', '--said']);
  assert.deepStrictEqual(t.undo().args, ['entity', 'tag', '王大明', '階段=簽約', '--said']);
  const fromEmpty = A.tag('王大明', '階段', ['施工中'], []);
  assert.deepStrictEqual(fromEmpty.undo().args, ['entity', 'tag', '王大明', '階段=', '--said']);
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

test('取消「期間」：時間軸的 period 與 kb lookup 的中文「期間」都先 --check', () => {
  assert.ok(A.cancel({ id: 'a-1', kind: 'period' }).check);
  assert.ok(A.cancel({ id: 'a-1', kind: '期間' }).check);
  assert.strictEqual(A.cancel({ id: 'a-1', kind: '到期' }).check, undefined);
});
