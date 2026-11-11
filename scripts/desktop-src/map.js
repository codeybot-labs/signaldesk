// ---------- LocalLead Map (OpenLayers, bundled above) ----------
const OSM_ATTRIBUTION =
  'Map data © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, ODbL'
const BUSINESS_TYPES = [
  'dentist', 'doctor', 'clinic', 'pharmacy', 'veterinary', 'cafe', 'restaurant', 'bar', 'coworking',
  'bakery', 'hairdresser', 'beauty', 'florist', 'bicycle', 'gym', 'lawyer', 'accountant',
  'estate_agent', 'it', 'hotel'
]
let olCssInjected = false

function injectOlCss() {
  if (olCssInjected || typeof document === 'undefined') return
  const style = document.createElement('style')
  style.setAttribute('data-signaldesk-ol', '1')
  style.textContent = OL_CSS
  document.head.appendChild(style)
  olCssInjected = true
}

function themeColor(el, name, fallback) {
  try {
    const v = getComputedStyle(el).getPropertyValue(name).trim()
    return v || fallback
  } catch (e) {
    return fallback
  }
}

function MapPanel(props) {
  const { ctx, leads, selectedId, onSelect } = props
  const qc = useQueryClient()
  const hostRef = useRef(null)
  const mapRef = useRef(null)
  const [city, setCity] = useState('')
  const [btype, setBtype] = useState('dentist')
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)

  const local = useMemo(
    () =>
      leads
        .filter((l) => l.signal_type === 'local' && l.provenance && l.provenance.lat != null)
        .slice()
        .sort((a, b) => (b.score || 0) - (a.score || 0)),
    [leads]
  )

  useEffect(() => {
    const el = hostRef.current
    if (!el || mapRef.current) return undefined
    injectOlCss()
    const pins = new ol.source.Vector()
    const box = new ol.source.Vector()
    const colors = {
      high: themeColor(el, '--ui-success', '#3ee0a4'),
      mid: themeColor(el, '--ui-warning', '#fbbf24'),
      low: themeColor(el, '--ui-danger', '#fb7185'),
      ring: themeColor(el, '--ui-text-primary', '#ffffff'),
      accent: themeColor(el, '--ui-accent', '#7dd3fc')
    }
    const defaults = (ol.control.defaults && ol.control.defaults.defaults) || ol.control.defaults
    const map = new ol.Map({
      target: el,
      layers: [
        new ol.layer.Tile({ source: new ol.source.OSM({ attributions: OSM_ATTRIBUTION }) }),
        new ol.layer.Vector({
          source: box,
          style: new ol.style.Style({ stroke: new ol.style.Stroke({ color: colors.accent, width: 2, lineDash: [6, 6] }) })
        }),
        new ol.layer.Vector({
          source: pins,
          style: (f) => {
            const s = f.get('score') || 0
            const sel = f.get('selected')
            return new ol.style.Style({
              image: new ol.style.Circle({
                radius: sel ? 10 : 7,
                fill: new ol.style.Fill({ color: s >= 60 ? colors.high : s >= 35 ? colors.mid : colors.low }),
                stroke: new ol.style.Stroke({ color: colors.ring, width: sel ? 3 : 1 })
              }),
              zIndex: sel ? 10 : 1
            })
          }
        })
      ],
      view: new ol.View({ center: ol.proj.fromLonLat([8.54, 47.375]), zoom: 12 }),
      controls: defaults({ attribution: false }).extend([new ol.control.Attribution({ collapsible: false })])
    })
    map.on('singleclick', (e) => {
      const f = map.forEachFeatureAtPixel(e.pixel, (x) => x, { layerFilter: (l) => l.getSource() === pins })
      if (f) onSelect(f.get('id'))
    })
    const ro = new ResizeObserver(() => map.updateSize())
    ro.observe(el)
    mapRef.current = { map, pins, box, fitted: false }
    return () => {
      ro.disconnect()
      map.setTarget(undefined)
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const m = mapRef.current
    if (!m) return
    m.pins.clear()
    m.pins.addFeatures(
      local.map((l) => {
        const f = new ol.Feature(new ol.geom.Point(ol.proj.fromLonLat([Number(l.provenance.lon), Number(l.provenance.lat)])))
        f.setProperties({ id: l.id, score: l.score, selected: l.id === selectedId })
        return f
      })
    )
    if (!m.fitted && local.length) {
      m.map.getView().fit(m.pins.getExtent(), { padding: [40, 40, 40, 40], maxZoom: 15 })
      m.fitted = true
    }
  }, [local, selectedId])

  const scan = async (body) => {
    setBusy(true)
    setStatus('Asking OpenStreetMap (Nominatim 1 req/s, Overpass one query at a time, cached)…')
    try {
      const res = await ctx.rest('/map/scan', { method: 'POST', body, timeoutMs: 90000 })
      const label = { live: 'live OpenStreetMap', cache: 'cached OSM results', demo: 'bundled OSM demo extract' }[res.mode] || res.mode
      setStatus(`Found ${res.found} ${res.business_type} · ${res.qualified} qualified · ${label}`)
      if (mapRef.current) mapRef.current.fitted = false
      await qc.invalidateQueries({ queryKey: [ctx.source, 'state'] })
    } catch (err) {
      setStatus((err && err.message) || 'Map scan failed')
    } finally {
      setBusy(false)
    }
  }

  const drawArea = () => {
    const m = mapRef.current
    if (!m) return
    const createBox = (ol.interaction.draw && ol.interaction.draw.createBox) || ol.interaction.Draw.createBox
    m.box.clear()
    const draw = new ol.interaction.Draw({ source: m.box, type: 'Circle', geometryFunction: createBox() })
    setStatus('Drag a rectangle on the map.')
    draw.on('drawend', (e) => {
      const ext = ol.proj.transformExtent(e.feature.getGeometry().getExtent(), 'EPSG:3857', 'EPSG:4326')
      setTimeout(() => m.map.removeInteraction(draw), 0)
      scan({ bbox: [ext[1], ext[0], ext[3], ext[2]].map((v) => v.toFixed(5)).join(','), business_type: btype })
    })
    m.map.addInteraction(draw)
  }

  const tick = (v) => jsx('span', { style: { color: v ? scoreColor(70) : undefined }, children: v ? '✓' : '–' })

  return jsxs('div', {
    className: 'flex min-h-0 flex-1 gap-2',
    children: [
      jsxs('div', {
        className: 'flex w-[420px] shrink-0 flex-col gap-2 rounded-xl border p-2',
        children: [
          jsxs('form', {
            className: 'flex flex-wrap gap-2',
            onSubmit: (e) => {
              e.preventDefault()
              if (city.trim()) scan({ city: city.trim(), business_type: btype })
            },
            children: [
              jsx('input', {
                className: 'h-7 flex-1 rounded-md border bg-transparent px-2 text-xs',
                placeholder: 'City, e.g. Zürich',
                value: city,
                onChange: (e) => setCity(e.target.value)
              }),
              jsx('select', {
                className: 'h-7 rounded-md border bg-transparent px-2 text-xs',
                value: btype,
                onChange: (e) => setBtype(e.target.value),
                children: BUSINESS_TYPES.map((t) => jsx('option', { value: t, children: t.replace('_', ' ') }, t))
              }),
              jsx(Button, { size: 'sm', type: 'submit', disabled: busy, children: 'Scan OpenStreetMap' }),
              jsx(Button, { size: 'sm', variant: 'secondary', type: 'button', onClick: drawArea, children: 'Draw area' })
            ]
          }),
          jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: status }),
          jsx(ScrollArea, {
            className: 'min-h-0 flex-1',
            children: jsxs('table', {
              className: 'w-full text-xs',
              children: [
                jsx('thead', {
                  children: jsxs('tr', {
                    className: 'text-left text-[10px] uppercase text-(--ui-text-tertiary)',
                    children: ['Business', 'Score', 'Web', 'Email', 'Phone', 'Stage'].map((h) => jsx('th', { className: 'p-1', children: h }, h))
                  })
                }),
                jsx('tbody', {
                  children: local.map((l) =>
                    jsxs(
                      'tr',
                      {
                        className: cn('cursor-pointer border-t', l.id === selectedId ? 'bg-(--ui-bg-secondary)' : ''),
                        onClick: () => onSelect(l.id),
                        children: [
                          jsxs('td', {
                            className: 'p-1',
                            children: [
                              jsx('div', { className: 'font-medium', children: l.company }),
                              jsx('div', { className: 'text-[10px] text-(--ui-text-tertiary)', children: l.provenance.address || '' })
                            ]
                          }),
                          jsx('td', { className: 'p-1 font-semibold', style: { color: scoreColor(l.score) }, children: l.score }),
                          jsx('td', { className: 'p-1', children: tick(l.provenance.website) }),
                          jsx('td', { className: 'p-1', children: tick(l.contact) }),
                          jsx('td', { className: 'p-1', children: tick(l.provenance.phone) }),
                          jsx('td', { className: 'p-1 text-[10px] uppercase', children: l.stage })
                        ]
                      },
                      l.id
                    )
                  )
                })
              ]
            })
          }),
          jsx('div', {
            className: 'text-[11px] text-(--ui-text-tertiary)',
            children: 'Map data © OpenStreetMap contributors, ODbL. Geocoding: Nominatim. POIs: Overpass API.'
          })
        ]
      }),
      jsx('div', { ref: hostRef, className: 'relative min-h-[320px] min-w-0 flex-1 overflow-hidden rounded-xl border' })
    ]
  })
}
