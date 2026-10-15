(function () {
  'use strict';
  var key = 'information-appearance-v1';
  var defaults = {color:'#409eff', size:13, font:'system', mode:'light'};
  var fonts = {
    system:'-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif',
    yahei:'"Microsoft YaHei","PingFang SC",sans-serif',
    song:'SimSun,"Songti SC",serif',
    kai:'KaiTi,STKaiti,serif'
  };
  var state;
  function read() {
    var saved = {};
    try { saved = JSON.parse(localStorage.getItem(key)) || {}; } catch (ignore) {}
    return {
      color:/^#[0-9a-f]{6}$/i.test(saved.color) ? saved.color : defaults.color,
      size:[12,13,15,17].indexOf(saved.size) >= 0 ? saved.size : defaults.size,
      font:Object.prototype.hasOwnProperty.call(fonts, saved.font) ? saved.font : defaults.font,
      mode:saved.mode === 'dark' ? 'dark' : 'light'
    };
  }
  function rgb(hex) { return [1,3,5].map(function (i) { return parseInt(hex.slice(i,i+2),16); }); }
  function paint(doc) {
    var root = doc.documentElement, c = rgb(state.color);
    // Keep custom accents readable against either surface, including black/white selections.
    var accent = c.map(function (v) { return Math.round(state.mode === 'dark' ? 90 + v * 0.64 : v * 0.66); });
    root.dataset.mode = state.mode;
    root.style.colorScheme = state.mode;
    root.style.setProperty('--primary', state.color);
    root.style.setProperty('--primary-hover', 'rgb(' + c.map(function (v) { return Math.round(v * 0.85); }).join(',') + ')');
    root.style.setProperty('--accent', 'rgb(' + accent.join(',') + ')');
    root.style.setProperty('--primary-soft', 'rgba(' + c.join(',') + ',0.13)');
    var luminance = c.reduce(function (sum, v, i) {
      v /= 255;
      return sum + (v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055,2.4)) * [0.2126,0.7152,0.0722][i];
    },0);
    root.style.setProperty('--on-primary', luminance > 0.179 ? '#15202b' : '#ffffff');
    root.style.setProperty('--font-size', state.size + 'px');
    root.style.setProperty('--font-family', fonts[state.font]);
    var mode = doc.getElementById('mode-toggle');
    if (mode) {
      mode.setAttribute('aria-pressed', String(state.mode === 'dark'));
      mode.title = state.mode === 'dark' ? '切换至亮色模式' : '切换至暗色模式';
      mode.setAttribute('aria-label', mode.title);
      mode.querySelector('i').className = 'fas fa-' + (state.mode === 'dark' ? 'sun' : 'moon');
    }
    ['font-size','font-family','theme-color'].forEach(function (id) {
      var field = doc.getElementById(id);
      if (field) { field.value = state[{ 'font-size':'size','font-family':'font','theme-color':'color' }[id]]; }
    });
    var value = doc.getElementById('theme-color-value');
    if (value) { value.textContent = state.color; }
    doc.querySelectorAll('[data-theme-color]').forEach(function (el) { el.setAttribute('aria-pressed', String(el.dataset.themeColor === state.color.toLowerCase())); });
    doc.querySelectorAll('iframe').forEach(function (frame) { try { paint(frame.contentDocument); } catch (ignore) {} });
  }
  function refresh() { state = read(); paint(document); }
  function save(values) {
    Object.assign(state, values);
    try { localStorage.setItem(key, JSON.stringify(state)); } catch (ignore) {}
    paint(document);
  }
  refresh();
  window.addEventListener('storage', function (event) { if (event.key === key || event.key === null) { refresh(); } });
  document.addEventListener('DOMContentLoaded', function () {
    paint(document);
    // Capture loads so newly opened/reloaded workspace frames inherit the current appearance.
    document.addEventListener('load', function (event) {
      if (event.target.tagName === 'IFRAME') { try { paint(event.target.contentDocument); } catch (ignore) {} }
    }, true);
    var toggle = document.getElementById('appearance-toggle'), panel = document.getElementById('appearance-panel');
    if (!toggle) { return; }
    var backdrop = document.getElementById('appearance-backdrop');
    function close() { panel.hidden = backdrop.hidden = true; toggle.setAttribute('aria-expanded','false'); toggle.focus(); }
    toggle.addEventListener('click', function () {
      if (!panel.hidden) { close(); return; }
      panel.hidden = backdrop.hidden = false;
      toggle.setAttribute('aria-expanded','true');
      document.getElementById('appearance-close').focus();
    });
    backdrop.addEventListener('click', close);
    document.getElementById('appearance-close').addEventListener('click', close);
    panel.addEventListener('keydown', function (event) {
      if (event.key === 'Escape') { close(); }
      if (event.key === 'Tab') {
        var items = panel.querySelectorAll('button,input,select'), first = items[0], last = items[items.length-1];
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });
    document.getElementById('mode-toggle').addEventListener('click', function () { save({mode:state.mode === 'dark' ? 'light' : 'dark'}); });
    panel.querySelectorAll('[data-theme-color]').forEach(function (button) { button.addEventListener('click', function () { save({color:button.dataset.themeColor}); }); });
    document.getElementById('theme-color').addEventListener('input', function (event) { save({color:event.target.value}); });
    document.getElementById('font-size').addEventListener('change', function (event) { save({size:Number(event.target.value)}); });
    document.getElementById('font-family').addEventListener('change', function (event) { save({font:event.target.value}); });
    document.getElementById('appearance-reset').addEventListener('click', function () { save(defaults); });
  });
}());
