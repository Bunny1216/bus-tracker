/**
 * app.js - City Bus Tracker (Leaflet.js front end, live API version)
 *
 * Data flow:
 *   ApiClient.loadRoute()  -> GET /api/routes/1/   (path + ordered stops)
 *   MapView                -> map, polyline, fit bounds, stop markers
 *   BusLayer               -> one marker per bus, updated from GET /api/buses/ every 4 s
 *
 * Classic script (not an ES module) so the file:// error banner can still run.
 */
(() => {
  'use strict';

  // VS Code Live Server (port 5500/5501) serves only /web, so point API calls at Django.
  const isDevServer = ['5500', '5501'].includes(location.port);

  const CONFIG = {
    apiBase: window.API_BASE ?? (isDevServer ? 'http://127.0.0.1:8000' : ''),
    routeId: 1,
    pollMs: 4000,          // delay between /api/buses/ polls
    staleAfterS: 60,       // grey the marker after this many seconds without a report
    timeoutMs: 8000,       // per-request timeout
    routeStyle: { color: '#1d6fe8', weight: 5, opacity: 0.85 },
    tileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '&copy; OpenStreetMap contributors'
  };

  const esc = s => String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const formatAge = seconds => {
    const s = Math.max(0, Math.round(seconds));
    if (s < 120) return `${s} s ago`;
    const m = Math.floor(s / 60);
    return m < 120 ? `${m} min ago` : `${Math.floor(m / 60)} h ago`;
  };

  /** Small JSON client with timeout and status-carrying errors. */
  class ApiClient {
    static async getJson(path) {
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), CONFIG.timeoutMs);
      try {
        const res = await fetch(CONFIG.apiBase + path, {
          signal: ctrl.signal, cache: 'no-store', headers: { Accept: 'application/json' }
        });
        if (!res.ok) {
          const err = new Error(`HTTP ${res.status} while loading ${path}`);
          err.status = res.status;
          throw err;
        }
        return await res.json();
      } catch (err) {
        if (err.name === 'AbortError') throw new Error(`Request timed out (${path})`);
        throw err;
      } finally {
        clearTimeout(timer);
      }
    }
    static async loadRoute() {
      const route = await ApiClient.getJson(`/api/routes/${CONFIG.routeId}/`);
      route.stops.sort((a, b) => a.order - b.order);
      return route;
    }
    static loadBuses() { return ApiClient.getJson('/api/buses/'); }
  }

  /** Owns the Leaflet map and static layers. */
  class MapView {
    constructor(elId) {
      this.map = L.map(elId, { zoomControl: false });
      L.control.zoom({ position: 'bottomright' }).addTo(this.map);
      L.tileLayer(CONFIG.tileUrl, { maxZoom: 19, attribution: CONFIG.attribution }).addTo(this.map);
    }
    drawRoute(path) {
      const line = L.polyline(path, CONFIG.routeStyle).addTo(this.map);
      this.map.fitBounds(line.getBounds(), { paddingTopLeft: [20, 110], paddingBottomRight: [20, 30] });
    }
    drawStops(stops) {
      stops.forEach(s => {
        const icon = L.divIcon({
          className: '', iconSize: [26, 26], iconAnchor: [13, 13],
          html: `<div class="stop-marker">${s.order}</div>`
        });
        L.marker([s.lat, s.lng], { icon, title: s.name })
          .addTo(this.map)
          .bindPopup(`<strong>${esc(s.name)}</strong><br>Stop ${s.order}${s.code ? ' &middot; ID ' + esc(s.code) : ''}`);
      });
    }
  }

  /**
   * Live bus markers. Age is computed from the server's `seconds_ago` plus local elapsed time,
   * so it ticks every second between polls and is immune to phone/server clock differences.
   */
  class BusLayer {
    constructor(map) { this.map = map; this.items = new Map(); }

    update(list) {
      const now = Date.now();
      const seen = new Set();
      for (const b of list) {
        seen.add(b.code);
        const latlng = [b.lat, b.lng];
        let it = this.items.get(b.code);
        if (!it) {
          const marker = L.marker(latlng, {
            zIndexOffset: 1000, title: b.code,
            icon: L.divIcon({ className: '', iconSize: [34, 34], iconAnchor: [17, 17],
                              html: '<div class="bus-marker">B</div>' })
          }).addTo(this.map).bindPopup('');
          it = { marker };
          this.items.set(b.code, it);
        } else {
          it.marker.setLatLng(latlng);
        }
        it.code = b.code;
        it.secondsAgo = b.seconds_ago;
        it.receivedAt = now;
        it.marker.setPopupContent(`<strong>${esc(b.code)}</strong><br>${Math.round(b.speed)} km/h`);
      }
      for (const [code, it] of this.items) {
        if (!seen.has(code)) { it.marker.remove(); this.items.delete(code); }
      }
      this.refreshStale();
    }

    age(it) { return it.secondsAgo + (Date.now() - it.receivedAt) / 1000; }

    refreshStale() {
      for (const it of this.items.values()) {
        const el = it.marker.getElement()?.querySelector('.bus-marker');
        if (el) el.classList.toggle('stale', this.age(it) > CONFIG.staleAfterS);
      }
    }

    /** Freshest bus, for the header status line (or null if none has reported). */
    summary() {
      let best = null;
      for (const it of this.items.values()) {
        const age = this.age(it);
        if (!best || age < best.age) best = { code: it.code, age, stale: age > CONFIG.staleAfterS };
      }
      return best;
    }
  }

  /** Friendly banner; special-cases file:// where fetch() is blocked. */
  function showError(err) {
    const banner = document.getElementById('error-banner');
    const isFile = location.protocol === 'file:';
    if (isFile) {
      banner.innerHTML = '<strong>Open via a local server.</strong> Browsers block data loading from <code>file://</code>. ' +
        'Run <code>python manage.py runserver</code> and open <code>http://127.0.0.1:8000/</code> ' +
        '(or use VS Code Live Server with the backend running).';
    } else {
      const hint = err.status === 404 ? ' Did you run <code>python manage.py seed_data</code>?' : '';
      banner.innerHTML = `<strong>Could not load route data.</strong> ${esc(err.message)}${hint}`;
    }
    banner.hidden = false;
    document.getElementById('bus-status').textContent = 'Data unavailable';
  }

  async function main() {
    const statusEl = document.getElementById('bus-status');
    const setStatus = (text, kind = '') => { statusEl.textContent = text; statusEl.className = 'status' + (kind ? ' ' + kind : ''); };

    const view = new MapView('map');
    view.map.setView([23.94, 90.405], 11);   // neutral fallback view

    let route;
    try {
      route = await ApiClient.loadRoute();
    } catch (err) {
      console.error(err);
      showError(err);
      return;
    }
    view.drawRoute(route.path);
    view.drawStops(route.stops);

    const layer = new BusLayer(view.map);
    let online = true;

    const render = () => {
      const s = layer.summary();
      if (!online) {
        setStatus(s ? `Connection lost, retrying... (${s.code} last seen ${formatAge(s.age)})`
                    : 'Connection lost, retrying...', 'error');
      } else if (!s) {
        setStatus('Waiting for a bus to report...');
      } else {
        setStatus(`${s.code} \u00b7 Updated ${formatAge(s.age)}${s.stale ? ' (no recent signal)' : ''}`,
                  s.stale ? 'stale' : '');
      }
    };

    // Chained setTimeout (not setInterval) so slow responses never overlap.
    const poll = async () => {
      try {
        layer.update(await ApiClient.loadBuses());
        online = true;
      } catch (err) {
        console.warn(err);
        online = false;
      }
      render();
      setTimeout(poll, CONFIG.pollMs);
    };

    setInterval(() => { layer.refreshStale(); render(); }, 1000);   // tick "X s ago" and stale colour
    poll();
  }

  document.addEventListener('DOMContentLoaded', main);
})();