'use strict';
/* 給外掛測試用的最小假 DOM：只做 main.js 用到的那幾個方法。 */

class FakeText {
  constructor(text) {
    this.nodeType = 3;
    this.nodeValue = String(text);
    this.parentNode = null;
  }

  get textContent() {
    return this.nodeValue;
  }
}

class FakeClassList {
  constructor(el) {
    this.el = el;
  }

  list() {
    return String(this.el.className || '').split(/\s+/).filter(Boolean);
  }

  add(...names) {
    const set = new Set(this.list());
    for (const n of names) set.add(n);
    this.el.className = [...set].join(' ');
  }

  remove(...names) {
    const set = new Set(this.list());
    for (const n of names) set.delete(n);
    this.el.className = [...set].join(' ');
  }

  contains(n) {
    return this.list().includes(n);
  }

  toggle(n, force) {
    const want = force === undefined ? !this.contains(n) : !!force;
    if (want) this.add(n);
    else this.remove(n);
    return want;
  }
}

class FakeEl {
  constructor(tag) {
    this.nodeType = 1;
    this.tagName = String(tag).toUpperCase();
    this.children = [];
    this.attrs = {};
    this.listeners = {};
    this.className = '';
    this.parentNode = null;
    this.styleMap = {};
    this.style = {
      setProperty: (k, v) => {
        this.styleMap[k] = v;
      },
      getPropertyValue: (k) => this.styleMap[k],
    };
    this.classList = new FakeClassList(this);
  }

  get firstChild() {
    return this.children[0] || null;
  }

  get textContent() {
    return this.children.map((c) => c.textContent).join('');
  }

  set textContent(v) {
    this.children = [];
    if (v !== '' && v !== null && v !== undefined) this.appendChild(new FakeText(v));
  }

  appendChild(c) {
    if (c.nodeType === 11) {
      for (const k of [...c.children]) this.appendChild(k);
      c.children = [];
      return c;
    }
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this;
    this.children.push(c);
    return c;
  }

  append(...cs) {
    for (const c of cs) this.appendChild(typeof c === 'string' ? new FakeText(c) : c);
  }

  insertBefore(c, ref) {
    if (c.parentNode) c.parentNode.removeChild(c);
    c.parentNode = this;
    const i = ref ? this.children.indexOf(ref) : -1;
    if (i < 0) this.children.push(c);
    else this.children.splice(i, 0, c);
    return c;
  }

  removeChild(c) {
    const i = this.children.indexOf(c);
    if (i >= 0) this.children.splice(i, 1);
    c.parentNode = null;
    return c;
  }

  setAttribute(k, v) {
    this.attrs[k] = String(v);
    if (k === 'class') this.className = String(v);
  }

  getAttribute(k) {
    return this.attrs[k] === undefined ? null : this.attrs[k];
  }

  addEventListener(ev, fn) {
    (this.listeners[ev] = this.listeners[ev] || []).push(fn);
  }

  /** 測試用：觸發事件。 */
  fire(ev, e) {
    const event = Object.assign({ preventDefault() {}, stopPropagation() {} }, e || {});
    for (const fn of this.listeners[ev] || []) fn(event);
  }

  /** 只支援 .class。 */
  querySelector(sel) {
    const cls = String(sel).replace(/^\./, '');
    let found = null;
    const visit = (e) => {
      if (found) return;
      for (const c of e.children || []) {
        if (c.nodeType === 1 && c.classList.contains(cls)) {
          found = c;
          return;
        }
        visit(c);
      }
    };
    visit(this);
    return found;
  }

  focus() {}
}

class FakeFragment extends FakeEl {
  constructor() {
    super('#fragment');
    this.nodeType = 11;
  }
}

function makeDocument() {
  return {
    createElement: (t) => new FakeEl(t),
    createTextNode: (t) => new FakeText(t),
    createDocumentFragment: () => new FakeFragment(),
  };
}

function walk(el, fn) {
  fn(el);
  for (const c of el.children || []) walk(c, fn);
}

/** 找 class 含 cls 的全部元素。 */
function byClass(root, cls) {
  const out = [];
  walk(root, (e) => {
    if (e.nodeType === 1 && e.classList.contains(cls)) out.push(e);
  });
  return out;
}

function byTag(root, tag) {
  const out = [];
  const T = tag.toUpperCase();
  walk(root, (e) => {
    if (e.nodeType === 1 && e.tagName === T) out.push(e);
  });
  return out;
}

function byText(root, text) {
  const out = [];
  walk(root, (e) => {
    if (e.nodeType === 1 && e.textContent === text) out.push(e);
  });
  return out;
}

module.exports = { FakeEl, FakeText, makeDocument, byClass, byTag, byText, walk };
