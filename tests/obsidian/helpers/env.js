'use strict';
/* 載入 obsidian/main.js 用的假環境：攔掉 require('obsidian')、裝假 DOM。 */

const Module = require('node:module');
const path = require('node:path');
const { makeDocument } = require('./fakedom');

const MAIN = path.join(__dirname, '..', '..', '..', 'obsidian', 'main.js');

function makeFakeObsidian() {
  const notices = [];

  class Plugin {
    constructor(app, manifest) {
      this.app = app;
      this.manifest = manifest;
    }

    async loadData() {
      return null;
    }

    async saveData() {}

    registerView() {}

    addRibbonIcon() {}

    addCommand() {}

    registerMarkdownPostProcessor() {}

    registerEvent() {}

    registerDomEvent() {}

    registerInterval() {}
  }

  class ItemView {
    constructor(leaf) {
      this.leaf = leaf;
      this.contentEl = globalThis.document.createElement('div');
    }
  }

  class Modal {
    constructor(app) {
      this.app = app;
      this.contentEl = globalThis.document.createElement('div');
      this.titleEl = globalThis.document.createElement('div');
    }

    open() {
      this.onOpen();
    }

    close() {
      this.onClose();
    }
  }

  class Menu {
    constructor() {
      this.items = [];
    }

    addItem(fn) {
      const item = {
        title: '',
        setTitle(t) {
          this.title = t;
          return this;
        },
        onClick(f) {
          this.run = f;
          return this;
        },
      };
      fn(item);
      this.items.push(item);
      return this;
    }

    showAtMouseEvent() {}

    showAtPosition() {}
  }

  class Notice {
    constructor(message) {
      this.message = message;
      notices.push(this);
    }

    hide() {}
  }

  class MarkdownView {}

  return { Plugin, ItemView, Modal, Menu, Notice, MarkdownView, editorLivePreviewField: { name: 'editorLivePreviewField' }, notices };
}

/** 回 {lib, Plugin, fake, restore}：lib 是 main.js 匯出的純函式與類別。 */
function loadMain() {
  const prev = globalThis.document;
  globalThis.document = makeDocument();
  const fake = makeFakeObsidian();
  const origLoad = Module._load;
  Module._load = function (request, parent, isMain) {
    if (request === 'obsidian') return fake;
    return origLoad.call(this, request, parent, isMain);
  };
  delete require.cache[MAIN];
  let Plugin;
  try {
    Plugin = require(MAIN);
  } finally {
    Module._load = origLoad;
  }
  return {
    Plugin,
    lib: Plugin.lib,
    fake,
    restore() {
      globalThis.document = prev;
      delete require.cache[MAIN];
    },
  };
}

/** 假的 execFile：記每次呼叫，回應由 handler(file, argv, options) 決定 → {code, stdout, stderr} 或丟 {code:'ENOENT'}。 */
function fakeExecFile(handler) {
  const calls = [];
  function execFile(file, argv, options, cb) {
    calls.push({ file, argv, options });
    let r;
    try {
      r = handler(file, argv, options) || { code: 0, stdout: '', stderr: '' };
    } catch (e) {
      r = { error: e };
    }
    setImmediate(() => {
      if (r.error) return cb(r.error, '', '');
      if (r.code === 0 || r.code === undefined) return cb(null, r.stdout || '', r.stderr || '');
      const err = new Error('Command failed');
      err.code = r.code;
      cb(err, r.stdout || '', r.stderr || '');
    });
  }
  execFile.calls = calls;
  return execFile;
}

module.exports = { loadMain, fakeExecFile, MAIN };
