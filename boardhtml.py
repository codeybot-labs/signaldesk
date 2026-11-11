"""Self-contained, interactive HTML pipeline board."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from models import STAGES
from paths import data_root
from store import counts_by_stage, list_leads

STAGE_LABELS = {
    "new": "New",
    "qualified": "Qualified",
    "drafted": "Drafted",
    "approved": "Approved",
    "sent": "Sent",
    "replied": "Replied",
    "won": "Won",
    "lost": "Lost",
}

_PAGE_JS = r"""
(function () {
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));
  const hasApi = location.protocol !== "file:";
  let state = window.__SIGNALDESK__ || { leads: [], counts: {}, icp: {}, sources: [] };
  let selectedId = null;
  let filters = { q: "", source: "all", signal: "all", minScore: 0 };

  function leads() { return state.leads || []; }
  function leadById(id) { return leads().find(l => l.id === id); }

  async function refresh() {
    if (!hasApi) return;
    try {
      const r = await fetch("/api/state", { cache: "no-store" });
      if (r.ok) state = await r.json();
    } catch (err) { /* stay with bootstrap */ }
  }

  async function post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {})
    });
    const data = await r.json().catch(() => ({ ok: false, error: "bad response" }));
    if (!r.ok || data.ok === false) throw new Error(data.error || "request failed");
    return data;
  }

  function visible(lead) {
    if (filters.signal !== "all" && lead.signal_type !== filters.signal) return false;
    if (filters.source !== "all") {
      const src = (lead.provenance && lead.provenance.source) || "";
      const tags = lead.tags || [];
      if (src !== filters.source && !tags.includes(filters.source)) return false;
    }
    if ((lead.score || 0) < filters.minScore) return false;
    const q = filters.q.trim().toLowerCase();
    if (q) {
      const blob = [lead.company, lead.role, lead.location, lead.domain, lead.signal_quote, lead.contact].join(" ").toLowerCase();
      if (!blob.includes(q)) return false;
    }
    return true;
  }

  function scoreClass(score) {
    if (score >= 60) return "high";
    if (score >= 35) return "mid";
    return "low";
  }

  function esc(v) {
    return String(v == null ? "" : v)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function renderHeader() {
    const icp = state.icp || {};
    const kws = (icp.keywords || []).slice(0, 6);
    const offer = icp.offer || "No offer set yet";
    const sources = state.sources || [];
    const counts = state.counts || {};
    const total = Object.values(counts).reduce((a, b) => a + (b || 0), 0);
    const motion = (counts.qualified || 0) + (counts.drafted || 0) + (counts.approved || 0);
    const srcPills = sources.map(s => {
      const on = s.enabled ? "on" : "off";
      const key = s.key_required ? "key" : "no-key";
      return `<span class="pill src ${on}" title="${esc(s.message || "")}"><i class="dot"></i>${esc(s.name)} <em class="${key}">${s.key_required ? "key" : "no key"}</em></span>`;
    }).join("");
    const kw = kws.map(k => `<span class="pill">${esc(k)}</span>`).join("");
    $("#kpis").innerHTML = `
      <div><strong>${total}</strong> leads</div>
      <div><strong>${motion}</strong> in motion</div>
      <div><strong>${counts.approved || 0}</strong> approved</div>`;
    $("#icp-line").innerHTML = `<span class="offer">${esc(offer)}</span>${kw}`;
    $("#src-line").innerHTML = srcPills || `<span class="muted">No sources listed</span>`;
  }

  function renderBoard() {
    if (view === "map") { renderTable(); if (pinSrc) pinSrc.changed(); }
    const counts = { ...Object.fromEntries((state.stages || Object.keys(STAGE)).map(s => [s, 0])) };
    const vis = leads().filter(visible);
    vis.forEach(l => { counts[l.stage] = (counts[l.stage] || 0) + 1; });
    $$(".col").forEach(col => {
      const stage = col.dataset.stage;
      const stack = $(".stack", col);
      const items = vis.filter(l => l.stage === stage)
        .sort((a, b) => (b.score || 0) - (a.score || 0));
      $(".count", col).textContent = items.length;
      if (!items.length) {
        stack.innerHTML = `<p class="empty">No leads</p>`;
        return;
      }
      stack.innerHTML = items.map(lead => {
        const loc = [lead.location, lead.remote === true ? "Remote" : lead.remote === false ? "Onsite" : ""].filter(Boolean).join(" · ");
        const active = lead.id === selectedId ? " active" : "";
        return `<article class="card${active}" data-id="${esc(lead.id)}" tabindex="0">
          <header><span class="co">${esc(lead.company)}</span>
            <span class="score ${scoreClass(lead.score)}">${esc(lead.score)}</span></header>
          <div class="sig">${esc(lead.signal_type || "")}</div>
          <p class="quote">${esc(lead.signal_quote || "")}</p>
          ${loc ? `<div class="meta">${esc(loc)}</div>` : ""}
          ${lead.role ? `<div class="meta">${esc(lead.role)}</div>` : ""}
        </article>`;
      }).join("");
    });
  }

  function localDetails(lead) {
    const p = lead.provenance || {};
    const row = (k, v, link) => v ? `<div class="kv"><span>${k}</span>${link ? `<a href="${esc(link)}" target="_blank" rel="noopener">${esc(v)}</a>` : esc(v)}</div>` : "";
    return `<section><h3>OpenStreetMap details</h3>
      ${row("Type", p.business_type)}${row("Address", p.address)}
      ${row("Website", p.website, p.website)}${row("Email", lead.contact)}${row("Phone", p.phone)}
      ${row("Hours", p.opening_hours)}
      <p class="attrib">© OpenStreetMap contributors, ODbL</p></section>`;
  }

  function renderPanel() {
    const panel = $("#panel");
    const lead = selectedId ? leadById(selectedId) : null;
    if (!lead) {
      panel.classList.remove("open");
      panel.setAttribute("aria-hidden", "true");
      const footer = $("#panel-footer");
      if (footer) footer.innerHTML = "";
      return;
    }
    panel.classList.add("open");
    panel.setAttribute("aria-hidden", "false");
    const reasons = (lead.score_reasons || []).map(r => `<li>${esc(r)}</li>`).join("");
    const loc = [lead.location, lead.remote === true ? "Remote" : lead.remote === false ? "Onsite" : ""].filter(Boolean).join(" · ");
    const hasDraft = !!(lead.draft_subject || lead.draft_body);
    const canApprove = hasDraft && lead.stage !== "approved" && lead.stage !== "sent" && lead.stage !== "won";
    const canDraft = lead.stage !== "sent" && lead.stage !== "won" && lead.stage !== "lost";
    const canEml = lead.stage === "approved" || lead.stage === "sent" || lead.stage === "replied" || lead.stage === "won" || canApprove;
    $("#panel-body").innerHTML = `
      <div class="p-head">
        <div>
          <div class="p-kicker">${esc(lead.signal_type)} · ${esc(lead.stage)}</div>
          <h2>${esc(lead.company)}</h2>
          <div class="meta">${esc(loc)}</div>
          ${lead.role ? `<div class="meta">${esc(lead.role)}</div>` : ""}
          ${lead.domain ? `<div class="meta">${esc(lead.domain)}</div>` : ""}
          ${lead.contact ? `<div class="meta">${esc(lead.contact)}</div>` : ""}
        </div>
        <span class="score ${scoreClass(lead.score)} big">${esc(lead.score)}</span>
      </div>
      <section>
        <h3>Signal</h3>
        <p class="quote">${esc(lead.signal_quote || "")}</p>
        ${lead.source_url ? `<a class="src" href="${esc(lead.source_url)}" target="_blank" rel="noopener">${lead.signal_type === "local" ? "Open on OpenStreetMap" : "Open source"}</a>` : ""}
      </section>
      ${lead.signal_type === "local" ? localDetails(lead) : ""}
      <section>
        <h3>Why this score</h3>
        ${reasons ? `<ul class="reasons">${reasons}</ul>` : `<p class="muted">No reasons recorded.</p>`}
      </section>
      <section>
        <h3>Draft</h3>
        ${hasDraft ? `<div class="draft"><div class="draft-sub">${esc(lead.draft_subject)}</div><pre>${esc(lead.draft_body)}</pre></div>` : `<p class="muted">No draft yet. Write one without sending.</p>`}
      </section>
    `;
    const footer = $("#panel-footer");
    if (footer) footer.innerHTML = `
      <div class="actions" id="panel-actions">
        ${canDraft && !hasDraft ? `<button data-act="draft" class="btn">Draft</button>` : ""}
        ${canApprove ? `<button data-act="approve" class="btn primary">Approve</button>` : ""}
        ${hasDraft ? `<button data-act="copy" class="btn">Copy</button>` : ""}
        ${canEml && hasDraft ? `<button data-act="eml" class="btn">Open .eml</button>` : ""}
        ${lead.stage !== "lost" && lead.stage !== "won" ? `<button data-act="reject" class="btn ghost">Reject</button>` : ""}
      </div>
      <p class="footnote" id="panel-msg">Nothing sends itself. Approve is the in-plugin gate; .eml stays on this machine.</p>`;
  }

  function toast(msg, ok) {
    const el = $("#toast");
    el.textContent = msg;
    el.className = "toast show " + (ok ? "ok" : "err");
    setTimeout(() => el.classList.remove("show"), 2600);
  }

  function setSelected(id) {
    selectedId = id;
    if (id) history.replaceState(null, "", "#lead=" + encodeURIComponent(id));
    else history.replaceState(null, "", location.pathname + location.search);
    renderBoard();
    renderPanel();
    if (view === "map") { renderTable(); if (pinSrc) pinSrc.changed(); focusPin(id); }
  }

  async function act(name) {
    const lead = leadById(selectedId);
    if (!lead) return;
    const msg = $("#panel-msg");
    try {
      if (name === "copy") {
        const text = (lead.draft_subject ? lead.draft_subject + "\n\n" : "") + (lead.draft_body || "");
        await navigator.clipboard.writeText(text);
        toast("Draft copied to the clipboard", true);
        return;
      }
      if (hasApi) {
        if (name === "draft") await post("/api/draft", { lead_id: lead.id });
        if (name === "approve") {
          if (!lead.draft_body) await post("/api/draft", { lead_id: lead.id });
          await post("/api/approve", { lead_id: lead.id });
        }
        if (name === "reject") await post("/api/mark", { lead_id: lead.id, stage: "lost" });
        if (name === "eml") {
          if (lead.stage !== "approved" && lead.stage !== "sent" && lead.stage !== "replied" && lead.stage !== "won") {
            if (!lead.draft_body) await post("/api/draft", { lead_id: lead.id });
            await post("/api/approve", { lead_id: lead.id });
          }
          const res = await post("/api/prepare", { lead_id: lead.id });
          await refresh();
          renderHeader();
          renderBoard();
          renderPanel();
          if (res.eml_path) window.location.href = "/exports/" + encodeURIComponent(res.eml_path.split(/[\\/]/).pop());
          toast("Wrote a local .eml — SignalDesk did not send it", true);
          return;
        }
        await refresh();
        renderHeader();
        renderBoard();
        renderPanel();
        if (name === "approve") toast("Approved. Still not sent.", true);
        if (name === "draft") toast("Draft written", true);
        if (name === "reject") toast("Marked lost", true);
        return;
      }
      // file:// simulation
      if (name === "draft" || (name === "approve" && !lead.draft_body)) {
        lead.draft_subject = lead.draft_subject || ("Re: " + lead.company);
        lead.draft_body = lead.draft_body || ("Hi " + lead.company + " team,\n\n(demo draft)\n");
        if (lead.stage === "new" || lead.stage === "qualified") lead.stage = "drafted";
      }
      if (name === "approve") lead.stage = "approved";
      if (name === "reject") lead.stage = "lost";
      if (name === "eml") {
        toast("Open this board via the demo server to download a real .eml", false);
        return;
      }
      renderHeader();
      renderBoard();
      renderPanel();
      toast(name === "approve" ? "Approved in this demo view" : "Updated in this demo view", true);
    } catch (err) {
      toast(err.message || String(err), false);
      if (msg) msg.textContent = err.message || String(err);
    }
  }

  function bind() {
    $("#q").addEventListener("input", e => { filters.q = e.target.value; renderBoard(); });
    $("#source").addEventListener("change", e => { filters.source = e.target.value; renderBoard(); });
    $("#signal").addEventListener("change", e => { filters.signal = e.target.value; renderBoard(); });
    $("#minscore").addEventListener("input", e => {
      filters.minScore = Number(e.target.value) || 0;
      $("#minscore-val").textContent = filters.minScore;
      renderBoard();
    });
    $(".board").addEventListener("click", e => {
      const card = e.target.closest(".card");
      if (card) setSelected(card.dataset.id);
    });
    $(".board").addEventListener("keydown", e => {
      if (e.key === "Enter" || e.key === " ") {
        const card = e.target.closest(".card");
        if (card) { e.preventDefault(); setSelected(card.dataset.id); }
      }
    });
    $("#panel").addEventListener("click", e => {
      if (e.target.dataset.close != null) setSelected(null);
      const btn = e.target.closest("[data-act]");
      if (btn) act(btn.dataset.act);
    });
    document.addEventListener("keydown", e => {
      if (e.key === "Escape") setSelected(null);
    });
  }

  // ---------- LocalLead Map (OpenLayers) ----------
  const OSM_ATTR = 'Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors, ODbL';
  let view = "board";
  let map = null, pinSrc = null, boxSrc = null, drawInt = null, tip = null;
  function localLeads() {
    return leads().filter(l => l.signal_type === "local" && l.provenance && l.provenance.lat != null && visible(l))
      .sort((a, b) => (b.score || 0) - (a.score || 0));
  }
  function pinColor(score) { return score >= 60 ? "#3ee0a4" : score >= 35 ? "#fbbf24" : "#fb7185"; }
  function pinStyle(f) {
    const lead = leadById(f.get("id"));
    const sel = f.get("id") === selectedId;
    return new ol.style.Style({
      image: new ol.style.Circle({
        radius: sel ? 11 : 7,
        fill: new ol.style.Fill({ color: pinColor(lead ? lead.score : 0) }),
        stroke: new ol.style.Stroke({ color: sel ? "#ffffff" : "#0a0e14", width: sel ? 3 : 2 })
      }),
      zIndex: sel ? 10 : 1
    });
  }
  function initMap() {
    if (map) return true;
    if (!window.ol) { $("#m-status").textContent = "OpenLayers failed to load (vendor/ol/ol.js)."; return false; }
    pinSrc = new ol.source.Vector();
    boxSrc = new ol.source.Vector();
    const defaults = (ol.control.defaults && ol.control.defaults.defaults) || ol.control.defaults;
    map = new ol.Map({
      target: "map",
      layers: [
        new ol.layer.Tile({ source: new ol.source.OSM({ attributions: OSM_ATTR }), className: "osm-tiles" }),
        new ol.layer.Vector({ source: boxSrc, style: new ol.style.Style({
          stroke: new ol.style.Stroke({ color: "#7dd3fc", width: 2, lineDash: [6, 6] }),
          fill: new ol.style.Fill({ color: "rgba(125,211,252,.08)" }) }) }),
        new ol.layer.Vector({ source: pinSrc, style: pinStyle })
      ],
      view: new ol.View({ center: ol.proj.fromLonLat([8.54, 47.375]), zoom: 12 }),
      controls: defaults({ attribution: false }).extend([new ol.control.Attribution({ collapsible: false })])
    });
    tip = document.createElement("div");
    tip.className = "map-tip";
    const tipOv = new ol.Overlay({ element: tip, offset: [12, -12], positioning: "bottom-left" });
    map.addOverlay(tipOv);
    map.on("pointermove", e => {
      const f = map.forEachFeatureAtPixel(e.pixel, x => x, { layerFilter: l => l.getSource() === pinSrc });
      map.getTargetElement().style.cursor = f ? "pointer" : "";
      if (f) {
        const lead = leadById(f.get("id"));
        tip.innerHTML = lead ? `<b>${esc(lead.company)}</b> <span class="score ${scoreClass(lead.score)}">${esc(lead.score)}</span>` : "";
        tipOv.setPosition(e.coordinate);
      } else tipOv.setPosition(undefined);
    });
    map.on("singleclick", e => {
      if (drawInt) return;
      const f = map.forEachFeatureAtPixel(e.pixel, x => x, { layerFilter: l => l.getSource() === pinSrc });
      if (f) setSelected(f.get("id"));
    });
    return true;
  }
  function renderPins(fit) {
    if (!map) return;
    pinSrc.clear();
    const rows = localLeads();
    pinSrc.addFeatures(rows.map(l => {
      const f = new ol.Feature(new ol.geom.Point(ol.proj.fromLonLat([Number(l.provenance.lon), Number(l.provenance.lat)])));
      f.set("id", l.id);
      return f;
    }));
    if (fit && rows.length) {
      map.getView().fit(pinSrc.getExtent(), { padding: [50, 50, 50, 50], maxZoom: 15, duration: 700 });
    }
  }
  function renderTable() {
    const rows = localLeads();
    const tb = $("#m-table tbody");
    if (!tb) return;
    $("#m-count").textContent = rows.length ? `${rows.length} businesses` : "";
    if (!rows.length) {
      tb.innerHTML = `<tr><td colspan="6" class="muted">No map leads yet. Enter a city and a business type, or draw an area.</td></tr>`;
      return;
    }
    const yes = v => v ? `<span class="yes" title="${esc(v)}">✓</span>` : `<span class="no">–</span>`;
    tb.innerHTML = rows.map(l => {
      const p = l.provenance || {};
      return `<tr data-id="${esc(l.id)}" class="${l.id === selectedId ? "active" : ""}">
        <td><div class="m-name">${esc(l.company)}</div><div class="m-sub">${esc(p.address || p.business_type || "")}</div></td>
        <td><span class="score ${scoreClass(l.score)}">${esc(l.score)}</span></td>
        <td>${yes(p.website)}</td><td>${yes(l.contact)}</td><td>${yes(p.phone)}</td>
        <td><span class="m-stage">${esc(l.stage)}</span></td></tr>`;
    }).join("");
    const active = $("#m-table tr.active");
    if (active) active.scrollIntoView({ block: "nearest" });
  }
  function renderMapView(fit) {
    if (view !== "map") return;
    if (!initMap()) return;
    renderPins(fit);
    renderTable();
    map.updateSize();
  }
  function setView(v) {
    view = v;
    $$(".view-toggle button").forEach(b => b.classList.toggle("on", b.dataset.view === v));
    $(".board").hidden = v !== "board";
    $("#mapview").hidden = v !== "map";
    if (v === "map") {
      if (filters.signal !== "all" && filters.signal !== "local") { filters.signal = "all"; $("#signal").value = "all"; }
      setTimeout(() => renderMapView(true), 30);
    }
  }
  async function mapScan(body) {
    const status = $("#m-status");
    if (!hasApi) { toast("Map scans need the SignalDesk server (Hermes Desktop or demo/serve_demo.py)", false); return; }
    status.textContent = "Asking OpenStreetMap… (Nominatim 1 req/s, Overpass one query at a time, cached)";
    $("#m-go").disabled = true;
    try {
      const res = await post("/api/map_scan", body);
      await refresh();
      renderHeader(); renderBoard();
      const src = { live: "live OpenStreetMap", cache: "cached OpenStreetMap results", demo: "bundled OSM demo extract (offline)" }[res.mode] || res.mode;
      status.innerHTML = `Found <b>${res.found}</b> ${esc(res.business_type)} · <b>${res.qualified}</b> qualified · ${esc(src)}`;
      renderMapView(true);
    } catch (err) {
      status.textContent = err.message || String(err);
      toast(err.message || String(err), false);
    } finally {
      $("#m-go").disabled = false;
    }
  }
  function startDraw() {
    if (!initMap()) return;
    if (drawInt) { map.removeInteraction(drawInt); drawInt = null; $("#m-draw").classList.remove("on"); return; }
    const createBox = (ol.interaction.draw && ol.interaction.draw.createBox) || (ol.interaction.Draw && ol.interaction.Draw.createBox);
    boxSrc.clear();
    drawInt = new ol.interaction.Draw({ source: boxSrc, type: "Circle", geometryFunction: createBox() });
    $("#m-draw").classList.add("on");
    $("#m-status").textContent = "Drag a rectangle on the map to scan just that area.";
    drawInt.on("drawend", e => {
      const ext = ol.proj.transformExtent(e.feature.getGeometry().getExtent(), "EPSG:3857", "EPSG:4326");
      setTimeout(() => { map.removeInteraction(drawInt); drawInt = null; $("#m-draw").classList.remove("on"); }, 0);
      const bbox = [ext[1], ext[0], ext[3], ext[2]].map(v => Number(v.toFixed(5))).join(",");
      mapScan({ bbox, business_type: $("#m-type").value });
    });
    map.addInteraction(drawInt);
  }
  function bindMap() {
    $$(".view-toggle button").forEach(b => b.addEventListener("click", () => setView(b.dataset.view)));
    $("#mapform").addEventListener("submit", e => {
      e.preventDefault();
      const city = $("#m-city").value.trim();
      if (!city) { toast("Type a city, or use Draw area", false); return; }
      boxSrc && boxSrc.clear();
      mapScan({ city, business_type: $("#m-type").value });
    });
    $("#m-draw").addEventListener("click", startDraw);
    $("#m-table").addEventListener("click", e => {
      const tr = e.target.closest("tr[data-id]");
      if (tr) setSelected(tr.dataset.id);
    });
    window.addEventListener("resize", () => map && map.updateSize());
    $("#panel").addEventListener("transitionend", () => map && map.updateSize());
  }
  function focusPin(id) {
    if (!map || view !== "map") return;
    const lead = leadById(id);
    if (!lead || lead.signal_type !== "local" || !lead.provenance) return;
    const c = ol.proj.fromLonLat([Number(lead.provenance.lon), Number(lead.provenance.lat)]);
    map.getView().animate({ center: c, zoom: Math.max(map.getView().getZoom() || 12, 14), duration: 500 });
  }

  const STAGE = { new:1, qualified:1, drafted:1, approved:1, sent:1, replied:1, won:1, lost:1 };

  async function init() {
    bind();
    bindMap();
    const srcSel = $("#source");
    const seen = new Set();
    (state.sources || []).forEach(s => {
      if (!seen.has(s.id)) {
        seen.add(s.id);
        const opt = document.createElement("option");
        opt.value = s.id; opt.textContent = s.name;
        srcSel.appendChild(opt);
      }
    });
    await refresh();
    const hash = (location.hash || "").replace(/^#/, "");
    if (hash.startsWith("lead=")) selectedId = decodeURIComponent(hash.slice(5));
    renderHeader();
    renderBoard();
    renderPanel();
    if (location.search.includes("view=map")) setView("map");
  }
  init();
})();
"""

_PAGE_CSS = r"""
:root {
  --bg: #0a0e14;
  --bg2: #10161e;
  --card: #171e28;
  --card-hover: #1d2632;
  --line: rgba(230, 240, 250, 0.08);
  --text: #e8eef6;
  --muted: #8b98a8;
  --accent: #3ee0a4;
  --accent-dim: #113328;
  --amber: #fbbf24;
  --amber-dim: #3a2e10;
  --rose: #fb7185;
  --rose-dim: #3a1820;
  --blue: #7dd3fc;
  --shadow: 0 16px 40px rgba(0,0,0,.35);
  --panel-w: 400px;
  --header-h: 118px;
}
* { box-sizing: border-box; }
html, body { height: 100%; }
body {
  margin: 0;
  font-family: "Segoe UI", "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
  background:
    radial-gradient(900px 420px at 0% -10%, #14362c 0%, transparent 55%),
    radial-gradient(800px 360px at 100% 0%, #152033 0%, transparent 50%),
    var(--bg);
  color: var(--text);
  overflow: hidden;
}
header.top {
  height: var(--header-h);
  padding: 12px 20px 10px;
  display: grid;
  grid-template-columns: 1fr auto;
  grid-template-areas:
    "brand kpis"
    "icp icp"
    "srcs filters";
  gap: 6px 20px;
  align-items: center;
  border-bottom: 1px solid var(--line);
  background: color-mix(in srgb, var(--bg) 78%, transparent);
  backdrop-filter: blur(10px);
}
.brand { grid-area: brand; }
.kpis { grid-area: kpis; justify-self: end; padding-top: 0; }
.filters { grid-area: filters; }
.icp { grid-area: icp; }
.srcs { grid-area: srcs; }
.brand { display: flex; flex-direction: column; gap: 2px; } /* grid-area set above */
.brand h1 { margin: 0; font-size: 20px; letter-spacing: .04em; font-weight: 650; }
.brand h1 span { color: var(--accent); }
.sub { color: var(--muted); font-size: 12px; }
.kpis { display: flex; gap: 18px; font-size: 12px; color: var(--muted); align-items: start; padding-top: 4px; }
.kpis strong { color: var(--text); font-size: 16px; margin-right: 4px; font-variant-numeric: tabular-nums; }
.icp, .srcs { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; min-height: 22px; }
.offer { color: var(--text); font-size: 12px; margin-right: 8px; max-width: 520px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pill { font-size: 11px; color: var(--muted); border: 1px solid var(--line); background: #151c25; border-radius: 999px; padding: 1px 8px; }
.pill.src { display: inline-flex; align-items: center; gap: 6px; }
.pill.src .dot { width: 6px; height: 6px; border-radius: 99px; background: var(--muted); display: inline-block; }
.pill.src.on .dot { background: var(--accent); }
.pill em { font-style: normal; font-size: 9px; letter-spacing: .06em; text-transform: uppercase; padding: 0 5px; border-radius: 999px; }
.pill em.no-key { background: var(--accent-dim); color: var(--accent); }
.pill em.key { background: var(--amber-dim); color: var(--amber); }
.filters { display: flex; gap: 8px; align-items: center; justify-self: end; }
.filters input[type="search"], .filters select, .filters input[type="range"] {
  background: #121821; color: var(--text); border: 1px solid var(--line); border-radius: 8px; padding: 5px 8px; font: inherit; font-size: 12px;
}
.filters input[type="search"] { width: 180px; }
.filters label { font-size: 11px; color: var(--muted); display: flex; align-items: center; gap: 6px; }
.board-wrap { height: calc(100vh - var(--header-h)); display: flex; position: relative; }
.board {
  display: flex; gap: 10px; padding: 12px 14px 20px; overflow-x: auto; overflow-y: hidden;
  flex: 1; scroll-snap-type: x proximity;
}
.col {
  flex: 0 0 220px; width: 220px; max-width: 220px; min-width: 220px;
  scroll-snap-align: start;
  background: color-mix(in srgb, var(--bg2) 92%, black);
  border: 1px solid var(--line); border-radius: 14px;
  padding: 10px 8px; display: flex; flex-direction: column;
  min-height: 0; overflow: hidden;
}
.col h2 {
  margin: 0 4px 8px; font-size: 11px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--muted); display: flex; justify-content: space-between; align-items: center;
}
.col h2 em, .count {
  font-style: normal; color: var(--text); background: #242c38; padding: 1px 7px; border-radius: 999px; font-size: 11px;
}
.stack { display: flex; flex-direction: column; gap: 8px; overflow-y: auto; padding: 0 2px 6px; min-height: 0; flex: 1; }
.card {
  background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 9px 10px;
  cursor: pointer; outline: none;
}
.card:hover, .card:focus { background: var(--card-hover); border-color: color-mix(in srgb, var(--accent) 35%, var(--line)); }
.card.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.card header { display: flex; justify-content: space-between; gap: 8px; align-items: start; }
.co { font-weight: 600; font-size: 13px; line-height: 1.25; }
.score {
  font-variant-numeric: tabular-nums; font-size: 11px; font-weight: 700;
  border-radius: 999px; padding: 1px 7px; background: #2a3340; color: var(--muted); flex: 0 0 auto;
}
.score.high { background: var(--accent-dim); color: var(--accent); }
.score.mid { background: var(--amber-dim); color: var(--amber); }
.score.low { background: var(--rose-dim); color: var(--rose); }
.score.big { font-size: 16px; padding: 4px 10px; margin-top: 4px; }
.sig {
  display: inline-block; margin: 5px 0 3px; font-size: 9px; letter-spacing: .07em;
  text-transform: uppercase; color: var(--blue); border: 1px solid #1e3a4c;
  border-radius: 999px; padding: 0 6px;
}
.quote { margin: 3px 0; font-size: 12px; color: #c9d4e0; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  overflow-wrap: anywhere; word-break: break-word; }
#panel .quote { -webkit-line-clamp: 8; }
.meta { font-size: 11px; color: var(--muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.empty { color: var(--muted); font-size: 12px; padding: 8px; }
#panel {
  width: 0; overflow: hidden; border-left: 0 solid var(--line);
  background: #0e141c; box-shadow: none; transition: width .18s ease;
}
#panel.open { width: var(--panel-w); border-left-width: 1px; box-shadow: var(--shadow); }
#panel-inner { width: var(--panel-w); height: 100%; display: flex; flex-direction: column; padding: 16px 16px 16px; overflow: hidden; }
.p-close { position: absolute; right: 10px; top: 10px; background: transparent; color: var(--muted); border: 0; font-size: 18px; cursor: pointer; }
#panel-inner { position: relative; }
#panel-body { overflow-y: auto; flex: 1; padding-right: 4px; }
.p-head { display: flex; justify-content: space-between; gap: 10px; margin: 8px 0 12px; padding-right: 18px; align-items: start; }
.p-kicker { font-size: 10px; letter-spacing: .08em; text-transform: uppercase; color: var(--blue); }
#panel h2 { margin: 2px 0 6px; font-size: 20px; }
#panel h3 { margin: 14px 0 6px; font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: var(--muted); }
.reasons { margin: 0; padding-left: 16px; color: var(--muted); font-size: 12px; line-height: 1.45; }
.draft { margin-top: 4px; background: #12181f; border-radius: 8px; padding: 10px; border: 1px solid var(--line); }
.draft-sub { font-size: 12px; color: var(--accent); font-weight: 600; }
.draft pre { white-space: pre-wrap; margin: 6px 0 0; font: 12px/1.45 ui-monospace, "SF Mono", Menlo, monospace; color: #d5deea; }
a.src { display: inline-block; margin-top: 6px; font-size: 12px; color: var(--blue); }
#panel-footer { flex: 0 0 auto; padding-top: 10px; border-top: 1px solid var(--line); background: #0e141c; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.footnote { margin-top: 8px; }
.btn {
  appearance: none; border: 1px solid var(--line); background: #1a222d; color: var(--text);
  border-radius: 8px; padding: 7px 12px; font: 12px/1 inherit; cursor: pointer;
}
.btn:hover { border-color: color-mix(in srgb, var(--accent) 40%, var(--line)); }
.btn.primary { background: var(--accent-dim); border-color: color-mix(in srgb, var(--accent) 50%, transparent); color: var(--accent); font-weight: 650; }
.btn.ghost { background: transparent; color: var(--rose); }
.footnote { font-size: 11px; color: var(--muted); margin-top: 8px; }
.toast {
  position: fixed; bottom: 18px; left: 50%; transform: translateX(-50%) translateY(20px);
  background: #1a222d; color: var(--text); border: 1px solid var(--line); border-radius: 999px;
  padding: 8px 14px; font-size: 12px; opacity: 0; pointer-events: none; transition: .2s ease; z-index: 20;
}
.toast.show { opacity: 1; transform: translateX(-50%) translateY(0); }
.toast.ok { border-color: color-mix(in srgb, var(--accent) 50%, var(--line)); }
.toast.err { border-color: color-mix(in srgb, var(--rose) 50%, var(--line)); }
.muted { color: var(--muted); font-size: 12px; }
.view-toggle { display: inline-flex; gap: 2px; margin-left: 14px; vertical-align: middle; background: #121821; border: 1px solid var(--line); border-radius: 9px; padding: 2px; }
.view-toggle button { appearance: none; border: 0; background: transparent; color: var(--muted); font: 600 11px/1 inherit; letter-spacing: .04em; padding: 5px 11px; border-radius: 7px; cursor: pointer; }
.view-toggle button.on { background: var(--accent-dim); color: var(--accent); }
.brand h1 { display: flex; align-items: center; }
#mapview { flex: 1; display: flex; min-width: 0; padding: 12px 14px 16px; gap: 12px; }
#mapview[hidden], .board[hidden] { display: none; }
.map-side { flex: 0 0 470px; width: 470px; display: flex; flex-direction: column; min-height: 0; background: color-mix(in srgb, var(--bg2) 92%, black); border: 1px solid var(--line); border-radius: 14px; padding: 12px; }
#mapform { display: grid; grid-template-columns: 1fr 130px; gap: 8px; }
#mapform input, #mapform select { background: #121821; color: var(--text); border: 1px solid var(--line); border-radius: 8px; padding: 8px 10px; font: inherit; font-size: 13px; }
#mapform .row { grid-column: 1 / -1; display: flex; gap: 8px; }
#mapform .btn { padding: 8px 12px; }
.btn.on { border-color: var(--blue); color: var(--blue); }
#m-status { margin: 10px 2px 6px; font-size: 12px; color: var(--muted); min-height: 16px; }
#m-status b { color: var(--text); }
.m-head { display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; margin: 4px 2px 6px; }
.m-table-wrap { flex: 1; overflow-y: auto; min-height: 0; border-top: 1px solid var(--line); }
#m-table { width: 100%; border-collapse: collapse; font-size: 12px; }
#m-table th { position: sticky; top: 0; background: #0f151d; color: var(--muted); font-weight: 600; font-size: 10px; text-transform: uppercase; letter-spacing: .07em; text-align: left; padding: 7px 6px; }
#m-table td { padding: 7px 6px; border-bottom: 1px solid var(--line); vertical-align: middle; }
#m-table tr[data-id] { cursor: pointer; }
#m-table tr[data-id]:hover { background: var(--card-hover); }
#m-table tr.active { background: var(--accent-dim); }
.m-name { font-weight: 600; font-size: 12.5px; }
.m-sub { color: var(--muted); font-size: 11px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 230px; }
.yes { color: var(--accent); font-weight: 700; } .no { color: #4b5563; }
.m-stage { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--blue); }
.attrib { font-size: 11px; color: var(--muted); margin: 8px 2px 0; }
.attrib a, .ol-attribution a { color: var(--blue); }
#map { flex: 1; min-width: 0; border-radius: 14px; overflow: hidden; border: 1px solid var(--line); position: relative; background: #0d131a; }
.osm-tiles { filter: invert(1) hue-rotate(180deg) brightness(.92) contrast(.88) saturate(.6); }
#map .ol-attribution { background: rgba(10,14,20,.82); color: var(--text); border-radius: 8px 0 0 0; font-size: 12px; padding: 3px 8px; right: 0; bottom: 0; }
#map .ol-attribution ul { margin: 0; padding: 0; } #map .ol-attribution button { display: none; }
#map .ol-zoom { top: 10px; left: 10px; } #map .ol-zoom button { background: #1a222d; color: var(--text); }
.map-tip { background: #0e141c; border: 1px solid var(--line); color: var(--text); padding: 4px 8px; border-radius: 8px; font-size: 12px; white-space: nowrap; box-shadow: var(--shadow); }
.kv { display: flex; gap: 10px; font-size: 12px; padding: 2px 0; } .kv span { color: var(--muted); flex: 0 0 64px; } .kv a { color: var(--blue); overflow-wrap: anywhere; }
@media (max-width: 1360px) {
  :root { --panel-w: 360px; --header-h: 126px; }
  .filters input[type="search"] { width: 130px; }
  .col { flex: 0 0 200px; width: 200px; max-width: 200px; min-width: 200px; }
  .offer { max-width: 360px; }
}
@media (max-height: 850px) {
  :root { --header-h: 108px; }
  header.top { padding: 8px 16px; gap: 4px 16px; }
  .brand h1 { font-size: 18px; }
  .sub { display: none; }
}
"""


def board_payload() -> dict[str, Any]:
    try:
        from icp import load_icp
        icp = load_icp().to_dict()
    except Exception:
        icp = {}
    try:
        from sources import list_source_info
        sources = list_source_info()
    except Exception:
        sources = []
    leads = [lead.to_public_dict() for lead in list_leads(limit=400)]
    return {
        "icp": icp,
        "sources": sources,
        "counts": counts_by_stage(),
        "stages": list(STAGES),
        "leads": leads,
    }


def render_board(path: Path | None = None, title: str = "SignalDesk") -> Path:
    payload = board_payload()
    bootstrap = json.dumps(payload, default=str).replace("<", "\\u003c")
    columns = []
    for stage in STAGES:
        columns.append(
            f'<section class="col" data-stage="{stage}">'
            f'<h2>{STAGE_LABELS.get(stage, stage)} <em class="count">0</em></h2>'
            f'<div class="stack"><p class="empty">No leads</p></div>'
            f"</section>"
        )
    sources_opts = '<option value="all">All sources</option>'
    try:
        from geo import BUSINESS_TYPES
        type_opts = "".join(f'<option value="{t}">{t.replace("_", " ")}</option>' for t in BUSINESS_TYPES)
    except Exception:
        type_opts = '<option value="dentist">dentist</option>'
    doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{title} — pipeline board</title>
<link rel="stylesheet" href="vendor/ol/ol.css"/>
<style>{_PAGE_CSS}</style>
</head>
<body>
  <header class="top">
    <div class="brand">
      <h1><span>Signal</span>Desk<span class="view-toggle" role="tablist"><button type="button" data-view="board" class="on">Pipeline</button><button type="button" data-view="map">Map</button></span></h1>
      <div class="sub">Public hiring and launch signals, scored against your ICP. Draft-first — nothing sends itself.</div>
    </div>
    <div class="filters">
      <input id="q" type="search" placeholder="Filter companies…" autocomplete="off"/>
      <select id="signal" aria-label="Signal type">
        <option value="all">All signals</option>
        <option value="hiring">Hiring</option>
        <option value="launch">Launches</option>
        <option value="local">Local (map)</option>
      </select>
      <select id="source" aria-label="Source">{sources_opts}</select>
      <label>Min score <input id="minscore" type="range" min="0" max="80" step="5" value="0"/> <span id="minscore-val">0</span></label>
    </div>
    <div class="icp" id="icp-line"></div>
    <div class="srcs" id="src-line"></div>
    <div class="kpis" id="kpis" style="display:none"></div>
  </header>
  <div class="board-wrap">
    <div class="board">{''.join(columns)}</div>
    <section id="mapview" hidden>
      <div class="map-side">
        <form id="mapform" autocomplete="off">
          <input id="m-city" placeholder="City, e.g. Zürich" aria-label="City"/>
          <select id="m-type" aria-label="Business type">{type_opts}</select>
          <div class="row"><button id="m-go" class="btn primary" type="submit">Scan OpenStreetMap</button>
          <button id="m-draw" class="btn" type="button">Draw area</button></div>
        </form>
        <div id="m-status"></div>
        <div class="m-head"><span>Local businesses</span><span id="m-count"></span></div>
        <div class="m-table-wrap"><table id="m-table"><thead><tr><th>Business</th><th>Score</th><th>Web</th><th>Email</th><th>Phone</th><th>Stage</th></tr></thead><tbody></tbody></table></div>
        <p class="attrib">Map data © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors, ODbL. Geocoding: Nominatim. POIs: Overpass API.</p>
      </div>
      <div id="map"></div>
    </section>
    <aside id="panel" aria-hidden="true">
      <div id="panel-inner">
        <button class="p-close" data-close type="button" aria-label="Close">×</button>
        <div id="panel-body"></div>
        <div id="panel-footer"></div>
      </div>
    </aside>
  </div>
  <div id="toast" class="toast"></div>
  <script src="vendor/ol/ol.js"></script>
  <script>window.__SIGNALDESK__ = {bootstrap};</script>
  <script>{_PAGE_JS}</script>
</body>
</html>
"""
    # Put KPIs back in the header visually — hidden above was a mistake if CSS grid overflows.
    # Re-inject kpis into the header via JS already; unhide.
    doc = doc.replace('id="kpis" style="display:none"', 'id="kpis"')
    dest = path or (data_root() / "board.html")
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(doc, encoding="utf-8")
    _copy_vendor(dest.parent)
    return dest


VENDOR_OL = Path(__file__).resolve().parent / "assets" / "vendor" / "ol"


def _copy_vendor(folder: Path) -> None:
    """Place OpenLayers (BSD-2) next to the board so it works from file:// and offline."""
    try:
        target = folder / "vendor" / "ol"
        target.mkdir(parents=True, exist_ok=True)
        for name in ("ol.js", "ol.css", "NOTICE"):
            src = VENDOR_OL / name
            dst = target / name
            if src.is_file() and (not dst.is_file() or dst.stat().st_size != src.stat().st_size):
                dst.write_bytes(src.read_bytes())
    except Exception:
        pass
