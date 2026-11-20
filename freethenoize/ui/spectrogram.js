/* Spectrogram renderer.
 *
 * Python sends uint8 images (0..255 ↔ dbFloor..0 dB, row 0 = lowest
 * frequency) for a log and a linear frequency axis. Colormap and contrast are
 * applied here, so changing them never goes back to Python.
 */
(function () {
  const STOPS = {
    inferno: [[0,0,4],[40,11,84],[101,21,110],[159,42,99],[212,72,66],[245,125,21],[250,193,39],[252,255,164]],
    magma:   [[0,0,4],[28,16,68],[79,18,123],[129,37,129],[181,54,122],[229,80,100],[251,135,97],[254,194,135],[252,253,191]],
    viridis: [[68,1,84],[72,40,120],[62,74,137],[49,104,142],[38,130,142],[31,158,137],[53,183,121],[109,205,89],[180,222,44],[253,231,37]],
    turbo:   [[48,18,59],[70,107,227],[40,187,236],[49,242,153],[162,252,60],[237,208,58],[251,128,34],[210,48,5],[122,4,3]],
    gris:    [[0,0,0],[255,255,255]],
    acido:   [[0,0,0],[10,22,0],[40,70,0],[110,160,0],[198,255,0],[240,255,190]],
  };
  const CMAP_NAMES = Object.keys(STOPS);

  function lut(name, floorDb, dataFloorDb) {
    const stops = STOPS[name] || STOPS.inferno;
    const out = new Uint8ClampedArray(256 * 4);
    for (let v = 0; v < 256; v++) {
      const db = dataFloorDb + (v / 255) * -dataFloorDb;
      let t = (db - floorDb) / -floorDb;
      t = Math.min(1, Math.max(0, t));
      const pos = t * (stops.length - 1);
      const i = Math.min(stops.length - 2, Math.floor(pos));
      const f = pos - i;
      for (let c = 0; c < 3; c++) out[v * 4 + c] = stops[i][c] + (stops[i + 1][c] - stops[i][c]) * f;
      out[v * 4 + 3] = 255;
    }
    return out;
  }

  function decodeB64(b64) {
    const bin = atob(b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    return arr;
  }

  function fmtHz(hz) {
    return hz >= 1000 ? (hz / 1000).toFixed(hz >= 10000 ? 0 : 1).replace(/\.0$/, '') + 'k' : Math.round(hz) + '';
  }
  function fmtTime(s) {
    const m = Math.floor(s / 60);
    return m + ':' + String(Math.floor(s % 60)).padStart(2, '0');
  }

  const PAD_L = 38, PAD_B = 20;

  class SpectrogramView {
    constructor(container, opts = {}) {
      this.el = container;
      this.el.innerHTML = '';
      this.canvas = document.createElement('canvas');
      this.overlay = document.createElement('canvas');
      this.readout = document.createElement('div');
      this.readout.className = 'readout';
      this.readout.hidden = true;
      this.el.append(this.canvas, this.overlay, this.readout);
      this.scale = opts.scale || 'log';
      this.cmap = opts.cmap || 'inferno';
      this.floor = opts.floor ?? -100;
      this.playhead = null;
      this.markHz = null;
      this.onSeek = null;
      this.data = null;
      this._images = {};

      new ResizeObserver(() => this.draw()).observe(this.el);
      this.overlay.addEventListener('mousemove', (e) => this._hover(e));
      this.overlay.addEventListener('mouseleave', () => { this.readout.hidden = true; });
      this.overlay.addEventListener('click', (e) => {
        const p = this._toData(e);
        if (p && this.onSeek) this.onSeek(p.time);
      });
    }

    setData(spec) {
      this.data = spec;
      this._raw = { log: decodeB64(spec.log), linear: decodeB64(spec.linear) };
      this._images = {};
      this.draw();
    }
    set(opts) {
      let rebuild = false;
      for (const k of ['scale', 'cmap', 'floor']) {
        if (k in opts && opts[k] !== this[k]) { this[k] = opts[k]; rebuild = rebuild || k !== 'scale'; }
      }
      if (rebuild) this._images = {};
      this.draw();
    }
    setPlayhead(t) { this.playhead = t; this._drawOverlay(); }
    setMarker(hz) { this.markHz = hz; this._drawOverlay(); }

    _image() {
      const key = this.scale;
      if (this._images[key]) return this._images[key];
      const { width: w, height: h, db_floor } = this.data;
      const src = this._raw[key];
      const table = lut(this.cmap, this.floor, db_floor);
      const off = document.createElement('canvas');
      off.width = w; off.height = h;
      const ctx = off.getContext('2d');
      const img = ctx.createImageData(w, h);
      const px = img.data;
      // src is (h, w) with row 0 = lowest frequency; canvas row 0 is the top.
      for (let y = 0; y < h; y++) {
        const srcRow = (h - 1 - y) * w;
        let o = y * w * 4;
        for (let x = 0; x < w; x++, o += 4) {
          const v = src[srcRow + x] * 4;
          px[o] = table[v]; px[o + 1] = table[v + 1]; px[o + 2] = table[v + 2]; px[o + 3] = 255;
        }
      }
      ctx.putImageData(img, 0, 0);
      return (this._images[key] = off);
    }

    _geom() {
      const dpr = window.devicePixelRatio || 1;
      const W = this.el.clientWidth, H = this.el.clientHeight;
      return { dpr, W, H, x0: PAD_L, y0: 0, pw: W - PAD_L, ph: H - PAD_B };
    }

    _yForHz(hz, g) {
      const { f_min, f_max } = this.data;
      const t = this.scale === 'log'
        ? (Math.log(hz / f_min) / Math.log(f_max / f_min))
        : hz / f_max;
      return g.y0 + g.ph * (1 - t);
    }
    _hzForY(y, g) {
      const { f_min, f_max } = this.data;
      const t = 1 - (y - g.y0) / g.ph;
      return this.scale === 'log' ? f_min * Math.pow(f_max / f_min, t) : t * f_max;
    }
    _toData(e) {
      if (!this.data) return null;
      const g = this._geom();
      const r = this.el.getBoundingClientRect();
      const x = e.clientX - r.left, y = e.clientY - r.top;
      if (x < g.x0 || y > g.ph) return null;
      return { time: ((x - g.x0) / g.pw) * this.data.duration, hz: this._hzForY(y, g) };
    }
    _hover(e) {
      const p = this._toData(e);
      if (!p) { this.readout.hidden = true; return; }
      this.readout.hidden = false;
      this.readout.textContent = `${fmtTime(p.time)} · ${fmtHz(p.hz)}Hz`;
    }

    draw() {
      const g = this._geom();
      for (const c of [this.canvas, this.overlay]) {
        c.width = Math.round(g.W * g.dpr); c.height = Math.round(g.H * g.dpr);
      }
      const ctx = this.canvas.getContext('2d');
      ctx.setTransform(g.dpr, 0, 0, g.dpr, 0, 0);
      ctx.fillStyle = '#050505';
      ctx.fillRect(0, 0, g.W, g.H);
      if (!this.data) return;

      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(this._image(), g.x0, g.y0, g.pw, g.ph);

      // Axes
      ctx.font = '10px "JetBrains Mono", ui-monospace, Menlo, monospace';
      ctx.fillStyle = 'rgba(255,255,255,.72)';
      ctx.strokeStyle = 'rgba(255,255,255,.14)';
      ctx.lineWidth = 1;
      const ticks = this.scale === 'log'
        ? [50, 100, 200, 500, 1000, 2000, 5000, 10000, 16000, 20000]
        : [2000, 4000, 6000, 8000, 10000, 12000, 14000, 16000, 18000, 20000, 22000, 24000, 30000, 40000];
      ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
      for (const hz of ticks) {
        if (hz < this.data.f_min || hz > this.data.f_max) continue;
        const y = Math.round(this._yForHz(hz, g)) + 0.5;
        ctx.beginPath(); ctx.moveTo(g.x0, y); ctx.lineTo(g.W, y); ctx.stroke();
        ctx.fillText(fmtHz(hz), g.x0 - 5, y);
      }
      const dur = this.data.duration;
      const step = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600].find((s) => (dur / s) <= 10) || 600;
      ctx.textAlign = 'center'; ctx.textBaseline = 'top';
      for (let t = step; t < dur; t += step) {
        const x = g.x0 + (t / dur) * g.pw;
        ctx.fillText(fmtTime(t), x, g.ph + 5);
      }
      this._drawOverlay();
    }

    _drawOverlay() {
      const g = this._geom();
      const ctx = this.overlay.getContext('2d');
      ctx.setTransform(g.dpr, 0, 0, g.dpr, 0, 0);
      ctx.clearRect(0, 0, g.W, g.H);
      if (!this.data) return;
      if (this.markHz) {
        const y = Math.round(this._yForHz(this.markHz, g)) + 0.5;
        ctx.setLineDash([4, 4]);
        ctx.strokeStyle = 'rgba(198,255,0,.95)';
        ctx.beginPath(); ctx.moveTo(g.x0, y); ctx.lineTo(g.W, y); ctx.stroke();
        ctx.setLineDash([]);
        ctx.fillStyle = 'rgba(198,255,0,1)';
        ctx.font = '10px "JetBrains Mono", ui-monospace, Menlo, monospace';
        ctx.textAlign = 'left'; ctx.textBaseline = 'bottom';
        ctx.fillText('corte ' + fmtHz(this.markHz) + 'Hz', g.x0 + 6, y - 3);
      }
      if (this.playhead != null) {
        const x = g.x0 + Math.min(1, this.playhead / this.data.duration) * g.pw;
        ctx.strokeStyle = 'rgba(255,255,255,.9)';
        ctx.lineWidth = 1.5;
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, g.ph); ctx.stroke();
      }
    }
  }

  window.Spectro = { SpectrogramView, CMAP_NAMES, fmtHz, fmtTime };
})();
