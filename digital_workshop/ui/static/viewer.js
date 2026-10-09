/* Pan / zoom / pointer handling for the DXF SVG viewer.
 *
 * This file contains view concerns only. Selection rules live in Python: the
 * browser reports clicks and rectangles in drawing coordinates and Python replies
 * with the ids to highlight via DigitalWorkshop.setSelection().
 */
window.DigitalWorkshop = (function () {
  const HOST = 'dxf-host';
  const CLICK_PIXELS = 4;
  const PICK_PIXELS = 5;
  let mode = 'select';
  let drag = null;
  let attached = false;
  let box = null;

  const host = () => document.getElementById(HOST);
  const svg = () => document.getElementById('dxf-svg');

  function viewBox() {
    const v = svg().viewBox.baseVal;
    return { x: v.x, y: v.y, w: v.width, h: v.height };
  }
  function setViewBox(v) {
    svg().setAttribute('viewBox', `${v.x} ${v.y} ${v.w} ${v.h}`);
  }
  function toWorld(evt) {
    const s = svg();
    const pt = s.createSVGPoint();
    pt.x = evt.clientX;
    pt.y = evt.clientY;
    const p = pt.matrixTransform(s.getScreenCTM().inverse());
    return { x: p.x, y: -p.y };
  }
  function unitsPerPixel() {
    const s = svg();
    return s.viewBox.baseVal.width / s.getBoundingClientRect().width;
  }
  function drawBox(a, b) {
    const el = host();
    if (!box) {
      box = document.createElement('div');
      box.style.cssText =
        'position:absolute;border:1px dashed #1c7ed6;background:rgba(28,126,214,.12);pointer-events:none';
      el.appendChild(box);
    }
    const r = el.getBoundingClientRect();
    box.style.left = Math.min(a.clientX, b.clientX) - r.left + 'px';
    box.style.top = Math.min(a.clientY, b.clientY) - r.top + 'px';
    box.style.width = Math.abs(a.clientX - b.clientX) + 'px';
    box.style.height = Math.abs(a.clientY - b.clientY) + 'px';
  }
  function clearBox() {
    if (box) { box.remove(); box = null; }
  }

  function onDown(evt) {
    if (!svg()) return;
    const panning = evt.button === 1 || (evt.button === 0 && mode === 'pan');
    if (evt.button !== 0 && evt.button !== 1) return;
    evt.preventDefault();
    drag = { panning, start: evt, vb: viewBox(), last: evt };
  }
  function onMove(evt) {
    if (!drag) return;
    drag.last = evt;
    if (drag.panning) {
      const k = unitsPerPixel();
      setViewBox({
        x: drag.vb.x - (evt.clientX - drag.start.clientX) * k,
        y: drag.vb.y - (evt.clientY - drag.start.clientY) * k,
        w: drag.vb.w, h: drag.vb.h,
      });
    } else {
      drawBox(drag.start, evt);
    }
  }
  function onUp(evt) {
    if (!drag) return;
    const d = drag;
    drag = null;
    clearBox();
    if (d.panning) return;
    const moved = Math.hypot(evt.clientX - d.start.clientX, evt.clientY - d.start.clientY);
    const mods = { shift: evt.shiftKey, ctrl: evt.ctrlKey || evt.metaKey };
    if (moved < CLICK_PIXELS) {
      const p = toWorld(evt);
      emitEvent('dxf_click', { x: p.x, y: p.y, tol: PICK_PIXELS * unitsPerPixel(), ...mods });
    } else {
      const a = toWorld(d.start);
      const b = toWorld(evt);
      emitEvent('dxf_box', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, ...mods });
    }
  }
  function onWheel(evt) {
    if (!svg()) return;
    evt.preventDefault();
    const factor = evt.deltaY < 0 ? 0.85 : 1 / 0.85;
    const s = svg();
    const pt = s.createSVGPoint();
    pt.x = evt.clientX;
    pt.y = evt.clientY;
    const p = pt.matrixTransform(s.getScreenCTM().inverse());
    const v = viewBox();
    setViewBox({
      x: p.x - (p.x - v.x) * factor,
      y: p.y - (p.y - v.y) * factor,
      w: v.w * factor,
      h: v.h * factor,
    });
  }

  return {
    attach() {
      if (attached) return;
      const el = host();
      if (!el) return;
      attached = true;
      el.style.position = 'relative';
      el.addEventListener('mousedown', onDown);
      window.addEventListener('mousemove', onMove);
      window.addEventListener('mouseup', onUp);
      el.addEventListener('wheel', onWheel, { passive: false });
      el.addEventListener('contextmenu', (e) => e.preventDefault());
    },
    fit() {
      const s = svg();
      if (s && s.dataset.home) s.setAttribute('viewBox', s.dataset.home);
    },
    setMode(m) { mode = m; },
    setSelection(ids) {
      const wanted = new Set(ids.map(String));
      document.querySelectorAll('#dxf-svg .obj').forEach((g) => {
        g.classList.toggle('sel', wanted.has(g.dataset.id));
      });
    },
    setHiddenLayers(layers) {
      const hidden = new Set(layers);
      document.querySelectorAll('#dxf-svg .obj').forEach((g) => {
        g.classList.toggle('hidden', hidden.has(g.dataset.layer));
      });
    },
  };
})();
