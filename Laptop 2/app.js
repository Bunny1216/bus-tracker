/**
 * app.js - City Bus Tracker (Leaflet.js front end)
 *
 * Live mode (Django reachable):
 *   GET /api/routes/<id>/  -> polyline + stops (with database ids)
 *   GET /api/buses/        -> polled every 4 s, markers grey out after 60 s of silence
 *   tap a stop             -> bottom sheet with GET /api/stops/<id>/etas/, refreshed every 5 s
 * Preview mode (file:// or no API): static ../data/*.json plus the simulated bus, as before.
 *
 * Classic script (not an ES module) so the file:// error banner can still display.
 */
(() => {
  'use strict';

  const CONFIG = {
    // Same origin as the page by default. For Live Server on another port set, before app.js:
    //   <script>window.BUS_API_BASE = 'http://127.0.0.1:8000';</script>  (and enable CORS on Django)
    apiBase: window.BUS_API_BASE || '',
    routeId: window.BUS_ROUTE_ID || 1,
    pollBusesMs: 4000,
    etaRefreshMs: 5000,
    staleAfterS: 60,
    staticRouteUrl: '../data/route.json',
    staticStopsUrl: '../data/stops.json',
    tickMs: 400,
    pointsPerTick: 1,
    routeStyle: { color: '#1d6fe8', weight: 5, opacity: 0.85 },
    tileUrl: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors'
  };

  const $ = id => document.getElementById(id);

  /** Geospatial helpers (used by the preview simulator). */
  const Geo = {
    EARTH_RADIUS_M: 6371000,
    haversine(a, b) {
      const rad = Math.PI / 180;
      const dLat = (b[0] - a[0]) * rad, dLng = (b[1] - a[1]) * rad;
      const h = Math.sin(dLat / 2) ** 2 +
                Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLng / 2) ** 2;
      return 2 * Geo.EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
    },
    nearestIndex(route, target) {
      let best = 0, bestD = Infinity;
      route.forEach((p, i) => {
        const d = Geo.haversine(p, target);
        if (d < bestD) { bestD = d; best = i; }
      });
      return best;
    }
  };

  const Fmt = {
    distance: m => (m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`),
    eta: s => (s < 60 ? '< 1 min' : `${Math.round(s / 60)} min`),
    ago: s => (s < 60 ? `${Math.round(s)} s ago` : `${Math.round(s / 60)} min ago`)
  };

  /** Loads route + stops: live API first, static preview files as fallback. */
  class DataService {
    static async fetchJson(url) {
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status} while loading ${url}`);
      return res.json();
    }
    static async loadLive() {
      const r = await DataService.fetchJson(`${CONFIG.apiBase}/api/routes/${CONFIG.routeId}/`);
      if (!Array.isArray(r.path) || r.path.length < 2) throw new Error('Route has no path yet');
      r.stops.sort((a, b) => a.order - b.order);
      return { route: r.path, stops: r.stops, live: true };
    }
    static async loadStatic() {
      const [route, stops] = await Promise.all([
        DataService.fetchJson(CONFIG.staticRouteUrl),
        DataService.fetchJson(CONFIG.staticStopsUrl)
      ]);
      stops.sort((a, b) => a.order - b.order);
      return { route, stops, live: false };
    }
    static async load() {
      if (location.protocol !== 'file:') {
        try { return await DataService.loadLive(); }
        catch (err) { console.warn('Live API unavailable, using preview data:', err); }
      }
      return DataService.loadStatic();
    }
  }

  /** Owns the Leaflet map and static layers. */
  class MapView {
    constructor(elId) {
      this.map = L.map(elId, { zoomControl: false });
      L.control.zoom({ position: 'bottomright' }).addTo(this.map);
      L.tileLayer(CONFIG.tileUrl, { maxZoom: 19, attribution: CONFIG.attribution }).addTo(this.map);
    }
    drawRoute(route) {
      const line = L.polyline(route, CONFIG.routeStyle).addTo(this.map);
      this.map.fitBounds(line.getBounds(), { paddingTopLeft: [20, 110], paddingBottomRight: [20, 30] });
    }
    /** Numbered stop markers; tapping one calls onSelect(stop). */
    drawStops(stops, onSelect) {
      stops.forEach(s => {
        const icon = L.divIcon({
          className: '', iconSize: [26, 26], iconAnchor: [13, 13],
          html: `<div class="stop-marker">${Number(s.order)}</div>`
        });
        L.marker([s.lat, s.lng], { icon, title: s.name, keyboard: true })
          .addTo(this.map)
          .on('click', () => onSelect(s));
      });
    }
  }

  /** Bottom sheet that shows approaching buses for the selected stop. */
  class StopSheet {
    constructor(live) {
      this.live = live;
      this.stop = null;
      this.timer = null;
      this.token = 0;       // bumps on open/close so late responses for an old stop are ignored
      this.busy = false;
      this.el = $('stop-sheet');
      $('sheet-close').addEventListener('click', () => this.close());
      document.addEventListener('keydown', e => { if (e.key === 'Escape') this.close(); });
      document.addEventListener('visibilitychange', () => { if (!document.hidden && this.stop) this.refresh(); });
    }
    message(text, isError = false) {
      const m = $('sheet-msg');
      m.textContent = text;
      m.classList.toggle('error', isError);
    }
    open(stop) {
      clearInterval(this.timer);
      this.stop = stop;
      this.token++;
      this.busy = false;
      $('sheet-title').textContent = stop.name;
      $('sheet-sub').textContent = `Stop ${stop.order}`;
      $('sheet-list').replaceChildren();
      $('sheet-updated').textContent = '';
      this.el.classList.add('open');
      this.el.setAttribute('aria-hidden', 'false');
      if (!this.live) {
        this.message('Live arrival times need the server. This is the offline preview.');
        return;
      }
      this.message('Loading arrival times…');
      this.refresh();
      this.timer = setInterval(() => { if (!document.hidden) this.refresh(); }, CONFIG.etaRefreshMs);
    }
    close() {
      clearInterval(this.timer);
      this.stop = null;
      this.token++;
      this.el.classList.remove('open');
      this.el.setAttribute('aria-hidden', 'true');
    }
    async refresh() {
      if (!this.stop || this.busy) return;
      const stop = this.stop, token = this.token;
      this.busy = true;
      try {
        const res = await fetch(`${CONFIG.apiBase}/api/stops/${encodeURIComponent(stop.id)}/etas/`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const etas = await res.json();
        if (token === this.token) this.render(etas);
      } catch (err) {
        console.error(err);
        if (token === this.token) this.message("Can't reach the server. Retrying…", true);
      } finally {
        if (token === this.token) this.busy = false;
      }
    }
    render(etas) {
      const list = $('sheet-list');
      list.replaceChildren();
      this.message(etas.length ? '' : 'No buses approaching');
      etas.forEach(e => {
        const atStop = e.status === 'At Stop';
        const li = document.createElement('li');
        if (atStop) li.className = 'at-stop';
        const code = Object.assign(document.createElement('span'), { className: 'bus-code', textContent: e.bus_code });
        const when = Object.assign(document.createElement('span'), { className: 'bus-eta', textContent: atStop ? 'At stop' : Fmt.eta(e.eta_seconds) });
        const dist = Object.assign(document.createElement('span'), { className: 'bus-dist', textContent: Fmt.distance(e.distance_m) });
        li.append(code, when, dist);                     // textContent only: no HTML injection from API data
        list.appendChild(li);
      });
      $('sheet-updated').textContent = 'Updated ' +
        new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
  }

  /** Polls /api/buses/ and keeps one marker per bus; stale buses turn grey. */
  class LiveBuses {
    constructor(map, statusEl) {
      this.map = map; this.statusEl = statusEl; this.markers = new Map();
    }
    start() {
      this.poll();
      setInterval(() => { if (!document.hidden) this.poll(); }, CONFIG.pollBusesMs);
    }
    async poll() {
      try {
        const res = await fetch(`${CONFIG.apiBase}/api/buses/`, { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const buses = await res.json();
        const seen = new Set();
        buses.forEach(b => { seen.add(b.code); this.upsert(b); });
        this.markers.forEach((m, code) => { if (!seen.has(code)) { m.remove(); this.markers.delete(code); } });
        this.statusEl.textContent = buses.length
          ? buses.map(b => `${b.code} ${Fmt.ago(b.age_s)}`).join(' · ')
          : 'No buses reporting yet';
      } catch (err) {
        console.error(err);
        this.statusEl.textContent = "Can't reach the server";
      }
    }
    upsert(b) {
      let m = this.markers.get(b.code);
      if (!m) {
        m = L.marker([b.lat, b.lng], {
          zIndexOffset: 1000, title: b.code,
          icon: L.divIcon({ className: '', iconSize: [34, 34], iconAnchor: [17, 17], html: '<div class="bus-marker">B</div>' })
        }).addTo(this.map);
        this.markers.set(b.code, m);
      } else {
        m.setLatLng([b.lat, b.lng]);
      }
      const inner = m.getElement() && m.getElement().firstElementChild;
      if (inner) inner.classList.toggle('stale', b.age_s > CONFIG.staleAfterS);
    }
  }

  /** Preview-only simulated bus that loops along the route (unchanged behaviour). */
  class BusSimulator {
    constructor(map, route, stops, onUpdate) {
      this.route = route;
      this.index = 0;
      this.stopIdx = stops.map(s => ({ ...s, routeIndex: Geo.nearestIndex(route, [s.lat, s.lng]) }));
      this.onUpdate = onUpdate;
      this.marker = L.marker(route[0], {
        zIndexOffset: 1000,
        icon: L.divIcon({ className: '', iconSize: [34, 34], iconAnchor: [17, 17], html: '<div class="bus-marker">B</div>' })
      }).addTo(map);
    }
    start() { this.timer = setInterval(() => this.tick(), CONFIG.tickMs); }
    tick() {
      this.index = (this.index + CONFIG.pointsPerTick) % this.route.length;
      this.marker.setLatLng(this.route[this.index]);
      const next = this.stopIdx.find(s => s.routeIndex >= this.index) || this.stopIdx[0];
      const metres = Math.round(Geo.haversine(this.route[this.index], [next.lat, next.lng]));
      this.onUpdate(`Preview bus -> ${next.name} (${metres} m)`);
    }
  }

  function showError(err) {
    const banner = $('error-banner');
    const isFile = location.protocol === 'file:';
    banner.innerHTML = isFile
      ? '<strong>Open via a local server.</strong> Browsers block data loading from <code>file://</code>. ' +
        'Run the Django server and open <code>http://127.0.0.1:8000/</code>, or use VS Code <em>Live Server</em>.'
      : `<strong>Could not load route data.</strong> ${String(err.message).replace(/</g, '&lt;')}`;
    banner.hidden = false;
    $('bus-status').textContent = 'Data unavailable';
  }

  async function main() {
    const statusEl = $('bus-status');
    const view = new MapView('map');
    view.map.setView([23.94, 90.405], 11);
    try {
      const { route, stops, live } = await DataService.load();
      const sheet = new StopSheet(live);
      view.drawRoute(route);
      view.drawStops(stops, s => sheet.open(s));
      view.map.on('click', () => sheet.close());
      if (live) {
        new LiveBuses(view.map, statusEl).start();
      } else {
        new BusSimulator(view.map, route, stops, t => { statusEl.textContent = t; }).start();
      }
    } catch (err) {
      console.error(err);
      showError(err);
    }
  }

  document.addEventListener('DOMContentLoaded', main);
})();
