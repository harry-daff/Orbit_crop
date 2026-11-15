import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, AlertTriangle, CalendarDays, Check, ChevronDown, CircleHelp, CloudRain, Compass, Download, Droplets, ExternalLink, Leaf, LocateFixed, MapPin, Menu, RotateCcw, Search, ShieldAlert, Sprout, Sun, Thermometer, Wheat, X } from 'lucide-react'
import ClearableInput from './components/ClearableInput.jsx'
const FarmMap = lazy(() => import('./components/FarmMap.jsx'))
const CropDetail = lazy(() => import('./components/CropDetail.jsx'))
const CropSuitabilityPanel = lazy(() => import('./components/CropSuitabilityPanel.jsx'))
const SoilProfilePanel = lazy(() => import('./components/SoilProfilePanel.jsx'))
const DisasterAlerts = lazy(() => import('./components/DisasterAlerts.jsx'))

const API = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')
const NAV = [
  { id: 'overview', label: 'Field overview', icon: Compass, group: 'FIELD' },
  { id: 'calendar', label: 'Crop calendar', icon: CalendarDays, group: 'PLAN' },
  { id: 'rotation', label: 'Rotation planner', icon: RotateCcw, group: 'PLAN' },
  { id: 'weather', label: 'Weather history', icon: CloudRain, group: 'INSIGHTS' },
  { id: 'soil', label: 'Soil health', icon: Droplets, group: 'INSIGHTS' },
  { id: 'alerts', label: 'Disaster Alerts', icon: ShieldAlert, group: 'SAFETY' },
]
const PREVIEW = [
  { crop: 'Pulses', score: 78, family: 'legume', season: 'Kharif or Rabi', risk_profile: 'Low–medium', water: [1.2, 5], temp: [18, 34], soils: ['Loamy', 'Clay', 'Sandy', 'Laterite'], ph: [5.5, 7.5], yield: 'Varies by pulse', market: 'Regional demand', pros: ['Nitrogen fixation', 'Rotation value'], cons: ['Flowering-stage drought risk'], actions: ['Use locally adapted seed.', 'Prepare a well-drained seedbed.', 'Apply nutrients from a soil test.', 'Scout regularly for pests.', 'Harvest at maturity.'] },
  { crop: 'Groundnut', score: 72, family: 'legume', season: 'Kharif or Rabi', risk_profile: 'Medium', water: [2, 6], temp: [20, 32], soils: ['Loamy', 'Sandy', 'Laterite'], ph: [5.8, 7], yield: 'Varies by region', market: 'Oilseed and food', pros: ['Legume rotation', 'Oilseed markets'], cons: ['Requires good drainage'], actions: ['Select tested seed.', 'Maintain drainage.', 'Use soil-test nutrition.', 'Monitor pests.', 'Dry pods safely.'] },
  { crop: 'Millets', score: 68, family: 'cereal', season: 'Kharif', risk_profile: 'Low–medium', water: [0.8, 4], temp: [20, 35], soils: ['Loamy', 'Sandy', 'Laterite'], ph: [5, 7.5], yield: 'Varies by species', market: 'Regional and specialty', pros: ['Diversification', 'Drought tolerance in adapted varieties'], cons: ['Market access varies'], actions: ['Select local species.', 'Sow after effective rain.', 'Weed early.', 'Scout pests.', 'Harvest and dry fully.'] },
]
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function SectionTitle({ eyebrow, title, detail, action }) { return <div className="mb-6 flex min-w-0 flex-wrap items-end justify-between gap-4"><div className="min-w-0 flex-1"><div className="mb-2 text-[10px] font-extrabold uppercase tracking-[.18em] text-field">{eyebrow}</div><h1 className="break-words font-display text-[27px] font-extrabold tracking-[-.04em] sm:text-[32px]">{title}<span className="text-[#a3b875]">.</span></h1>{detail && <p className="mb-0 mt-1.5 max-w-3xl text-[13px] leading-relaxed text-[#829084]">{detail}</p>}</div>{action}</div> }
function Card({ children, className = '' }) { return <section className={`rounded-[20px] border border-[#e8ece3] bg-white p-5 sm:p-6 ${className}`}>{children}</section> }
function CardTitle({ children, sub, action }) { return <div className="mb-4 flex flex-wrap items-center justify-between gap-2"><div><h2 className="mb-0 font-display text-[15px] font-extrabold tracking-tight">{children}</h2>{sub && <p className="mb-0 mt-1 text-[11px] text-[#879387]">{sub}</p>}</div>{action}</div> }
function Metric({ icon: Icon, label, value, unit, tone = 'green', note }) {
  const toneClass = tone === 'blue' ? 'bg-blue-50 text-blue-600' : tone === 'amber' ? 'bg-amber-50 text-amber-600' : 'bg-[#eef5e8] text-field'
  return <div className="rounded-[17px] border border-[#e8ece3] bg-white p-4"><div className={"grid h-9 w-9 place-items-center rounded-xl " + toneClass}><Icon size={17}/></div><div className="mt-3 flex items-baseline gap-1"><strong className="font-display text-[23px] font-extrabold">{value == null ? 'N/A' : value}</strong><span className="text-[11px] text-[#829084]">{unit}</span></div><div className="mt-0.5 text-[11px] font-bold text-[#526455]">{label}</div>{note && <div className="mt-1 text-[10px] text-[#98a398]">{note}</div>}</div>
}
function EmptyPanel({ icon: Icon = CircleHelp, title, children }) { return <div className="flex min-h-[190px] flex-col items-center justify-center rounded-2xl border border-dashed border-[#dfe5dc] bg-[#fafbf9] p-6 text-center"><Icon className="mb-3 text-[#91a386]" size={23}/><h3 className="font-display text-sm font-extrabold">{title}</h3><p className="mb-0 mt-1 max-w-md text-xs leading-relaxed text-[#819082]">{children}</p></div> }

export default function App() {
  const [active, setActive] = useState('overview')
  const [mobileNav, setMobileNav] = useState(false)
  const [installPrompt, setInstallPrompt] = useState(null)
  const [installHelpOpen, setInstallHelpOpen] = useState(false)
  const [isInstalled, setIsInstalled] = useState(() => window.matchMedia?.('(display-mode: standalone)').matches || window.navigator.standalone === true)
  const [accountOpen, setAccountOpen] = useState(false)
  const [helpOpen, setHelpOpen] = useState(false)
  const [coordinates, setCoordinates] = useState({ latitude: 20.5937, longitude: 78.9629 })
  const [polygon, setPolygon] = useState([])
  const [soilType, setSoilType] = useState('')
  const [previousCrop, setPreviousCrop] = useState('Rice')
  const [geoStatus, setGeoStatus] = useState('detecting')
  const [placeQuery, setPlaceQuery] = useState('')
  const [placeResults, setPlaceResults] = useState([])
  const [placeOpen, setPlaceOpen] = useState(false)
  const [customCategory, setCustomCategory] = useState('field_crop')
  const [years, setYears] = useState(3)
  const [calendarStart, setCalendarStart] = useState('recommended')
  const [calendarSeason, setCalendarSeason] = useState('current')
  const [payload, setPayload] = useState(null)
  const [cropCatalog, setCropCatalog] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [selectedCrop, setSelectedCrop] = useState(null)
  const [rotation, setRotation] = useState(['Pulses', 'Groundnut', 'Millets'])
  const [countryOptions, setCountryOptions] = useState([])
  const [adaptCountry, setAdaptCountry] = useState(false)
  const [countryCode, setCountryCode] = useState('IN')
  const [customName, setCustomName] = useState('')
  const [customFamily, setCustomFamily] = useState('')
  const [customCrops, setCustomCrops] = useState([])
  const [rotationWarnings, setRotationWarnings] = useState([])
  const [disasterReport, setDisasterReport] = useState(null)
  const [disasterLoading, setDisasterLoading] = useState(false)
  const [disasterError, setDisasterError] = useState('')
  const [disasterOffline, setDisasterOffline] = useState(false)
  const allCrops = useMemo(() => [...(cropCatalog.length ? cropCatalog : PREVIEW), ...customCrops], [cropCatalog, customCrops])
  const autoLocationStarted = useRef(false)

  useEffect(() => {
    fetch(`${API}/api/crops`).then(r => r.ok ? r.json() : Promise.reject()).then(data => setCropCatalog(data.crops || [])).catch(() => {})
    fetch(`${API}/api/countries`).then(r => r.ok ? r.json() : Promise.reject()).then(data => setCountryOptions(data.countries || [])).catch(() => {})
  }, [])
  useEffect(() => {
    const onBeforeInstall = event => { event.preventDefault(); setInstallPrompt(event) }
    const onInstalled = () => { setIsInstalled(true); setInstallPrompt(null) }
    window.addEventListener('beforeinstallprompt', onBeforeInstall)
    window.addEventListener('appinstalled', onInstalled)
    return () => {
      window.removeEventListener('beforeinstallprompt', onBeforeInstall)
      window.removeEventListener('appinstalled', onInstalled)
    }
  }, [])
  useEffect(() => {
    if (autoLocationStarted.current) return
    autoLocationStarted.current = true
    if (!navigator.geolocation) { setGeoStatus('GPS is unavailable in this browser. Search for a place or enter coordinates.'); return }
    setGeoStatus('Requesting device location…')
    navigator.geolocation.getCurrentPosition(position => {
      const point = { latitude: Number(position.coords.latitude.toFixed(6)), longitude: Number(position.coords.longitude.toFixed(6)) }
      setCoordinates(point); setPolygon([]); setGeoStatus('Location detected'); analyze(null, point, [])
    }, error => {
      setGeoStatus(error.code === 1 ? 'Location permission denied. Search for a place or enter coordinates.' : 'Could not detect location. Search for a place or enter coordinates.')
    }, { enableHighAccuracy: false, maximumAge: 120000, timeout: 12000 })
  }, [])
  useEffect(() => {
    if (placeQuery.trim().length < 2) { setPlaceResults([]); return }
    let mounted = true
    const timer = setTimeout(() => fetch(`${API}/api/geocode?q=${encodeURIComponent(placeQuery.trim())}`)
      .then(response => response.json())
      .then(result => { if (mounted) { setPlaceResults(result.results || []); setPlaceOpen(true) } })
      .catch(() => { if (mounted) setPlaceResults([]) }), 350)
    return () => { mounted = false; clearTimeout(timer) }
  }, [placeQuery])
  useEffect(() => {
    let mounted = true
    const loadAlerts = async () => {
      const key = `orbit:disaster:v1:${coordinates.latitude.toFixed(3)}:${coordinates.longitude.toFixed(3)}:${countryCode}`
      let saved = null
      try { saved = JSON.parse(window.localStorage.getItem(key) || 'null') } catch { saved = null }
      if (mounted) { setDisasterReport(saved); setDisasterOffline(Boolean(saved)) }
      setDisasterLoading(true)
      try {
        const query = new URLSearchParams({ lat: String(coordinates.latitude), lon: String(coordinates.longitude), country: countryCode || '' })
        if (rotation[0]) query.set('crop', rotation[0])
        const response = await fetch(`${API}/api/disaster-alerts?${query}`, { signal: AbortSignal.timeout(14000) })
        const result = await response.json().catch(() => ({}))
        if (!response.ok) throw new Error(result.detail || 'Disaster outlook could not be loaded.')
        if (!mounted) return
        setDisasterReport(result); setDisasterOffline(false); setDisasterError('')
        window.localStorage.setItem(key, JSON.stringify(result))
        window.localStorage.setItem('orbit:last-disaster-report:v1', JSON.stringify(result))
      } catch (exception) {
        if (!mounted || exception.name === 'AbortError') return
        setDisasterError(exception.message || 'Could not connect to the alert service.')
        if (!saved) setDisasterOffline(false)
      } finally { if (mounted) setDisasterLoading(false) }
    }
    loadAlerts()
    const interval = window.setInterval(loadAlerts, 15 * 60 * 1000)
    return () => { mounted = false; window.clearInterval(interval) }
  }, [coordinates.latitude, coordinates.longitude, countryCode, rotation[0]])
  useEffect(() => {
    let active = true
    if (!rotation.length) {
      setRotationWarnings([])
      return () => { active = false }
    }
    const sequence = rotation.map(name => allCrops.find(crop => crop.crop === name) || { crop: name, family: 'custom', botanical_family: 'Unknown' })
    fetch(`${API}/api/rotation/validate`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sequence, previous_crop: previousCrop }) })
      .then(response => response.ok ? response.json() : Promise.reject())
      .then(result => { if (active) setRotationWarnings(result.warnings || []) })
      .catch(() => { if (active) setRotationWarnings(validateRotation(rotation, allCrops, previousCrop)) })
    return () => { active = false }
  }, [rotation, allCrops, previousCrop])
  const monthly = payload?.monthly || []
  const daily = payload?.daily || []
  const recommendations = payload?.analysis?.recommendations || PREVIEW
  const sections = { overview: 'Field overview', calendar: 'Crop calendar', rotation: 'Rotation planner', weather: 'Weather history', soil: 'Soil health', alerts: 'Disaster Alerts' }
  const latest = daily[daily.length - 1]
  const latestWithWetness = daily.slice().reverse().find(d => d.GWETROOT != null) || latest
  const currentAlertLocation = disasterReport?.location && Math.abs(disasterReport.location.latitude - coordinates.latitude) < 0.002 && Math.abs(disasterReport.location.longitude - coordinates.longitude) < 0.002
  const activeDisasterCount = currentAlertLocation ? (disasterReport?.active_count || 0) : 0
  const previousDates = payload?.data_source ? `${payload.data_source.start} – ${payload.data_source.end}` : 'NASA POWER daily history'

  async function analyze(event, point = coordinates, selectedPolygon = polygon) {
    event?.preventDefault?.()
    const lat = Number(point.latitude)
    const lng = Number(point.longitude)
    if (!Number.isFinite(lat) || !Number.isFinite(lng) || lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      setError('Please enter valid numeric latitude (-90 to 90) and longitude (-180 to 180).')
      return
    }
    if (selectedPolygon.length > 0 && selectedPolygon.length < 3) { setError('A field boundary needs at least three points. Add more vertices or clear the partial boundary.'); return }
    setLoading(true); setError('')
    const closedPolygon = selectedPolygon.length >= 3 ? [...selectedPolygon, selectedPolygon[0]] : null
    const body = { ...point, latitude: lat, longitude: lng, soil_type: soilType || null, previous_crop: previousCrop, years, adapt_to_country: adaptCountry, country_code: countryCode || null, custom_crop_name: customName.trim() || null, custom_crop_category: customCategory, field_geojson: closedPolygon ? { type: 'Feature', properties: { name: 'Farm boundary' }, geometry: { type: 'Polygon', coordinates: [closedPolygon] } } : null }
    try {
      const response = await fetch(`${API}/api/full-soil-report`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The soil and climate report could not be loaded. Check coordinates and try again.')
      setPayload(result)
      setCoordinates(point); setGeoStatus('Field report ready')
    } catch (exception) {
      setError(exception.message || 'Could not reach Orbit_crop API. Check that the backend is running and try again.')
    } finally { setLoading(false) }
  }

  function pickCrop(name) {
    const fromMatches = recommendations.find(item => item.crop === name)
    const fromCatalog = allCrops.find(item => item.crop === name)
    const customMatch = payload?.crop_suitability?.custom_crop_check?.crop === name ? payload.crop_suitability.custom_crop_check : null
    setSelectedCrop(fromMatches || customMatch || fromCatalog || customCrops.find(item => item.crop === name) || null)
  }

  async function addCustomCrop(event) {
    event.preventDefault()
    if (!customName.trim()) return
    try {
      const response = await fetch(`${API}/api/crops/custom`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: customName.trim(), botanical_family: customFamily }) })
      const item = await response.json()
      if (!response.ok) throw new Error(item.detail || 'Could not create this crop profile.')
      setCustomCrops(items => items.some(crop => crop.crop.toLowerCase() === item.crop.toLowerCase()) ? items : [...items, item])
      setRotation(items => [...items, item.crop])
      setCustomName('')
    } catch (exception) { setError(exception.message || 'Custom crop could not be added.') }
  }

  function detectMyLocation() {
    if (!navigator.geolocation) { setGeoStatus('GPS is unavailable in this browser.'); return }
    setGeoStatus('Requesting device location…')
    navigator.geolocation.getCurrentPosition(position => {
      const point = { latitude: Number(position.coords.latitude.toFixed(6)), longitude: Number(position.coords.longitude.toFixed(6)) }
      setCoordinates(point); setPolygon([]); setGeoStatus('Location detected'); analyze(null, point, [])
    }, error => setGeoStatus(error.code === 1 ? 'Location permission denied.' : 'Could not detect location.'), { enableHighAccuracy: false, maximumAge: 120000, timeout: 12000 })
  }

  function selectPlace(place) {
    const point = { latitude: Number(place.latitude), longitude: Number(place.longitude) }
    setCoordinates(point); setPolygon([]); setPlaceQuery(place.label); setPlaceOpen(false); setPlaceResults([])
    if (place.country_code) setCountryCode(place.country_code.toUpperCase())
    setGeoStatus(`Location selected · ${place.label}`); analyze(null, point, [])
  }

  function checkCustomCrop(event) { analyze(event, coordinates) }

  function updateCoordinates(next) { setCoordinates(next); setPayload(null) }
  function updatePolygon(next) { setPolygon(next); setPayload(null) }

  async function installApp() {
    if (!installPrompt) { setInstallHelpOpen(true); return }
    await installPrompt.prompt()
    const choice = await installPrompt.userChoice
    if (choice?.outcome === 'accepted') setIsInstalled(true)
    setInstallPrompt(null)
  }

  const analyzeButton = <button onClick={analyze} disabled={loading} className="flex items-center gap-2 rounded-xl bg-field px-4 py-3 text-xs font-bold text-white shadow-sm transition hover:bg-[#1e4b34] disabled:cursor-wait disabled:opacity-60"><RotateCcw size={14} className={loading ? 'animate-spin' : ''}/>{loading ? 'Loading soil & crop data…' : payload ? 'Refresh soil report' : 'Analyze soil & crops'}</button>
  const sidebar = <aside className={`fixed inset-y-0 left-0 z-30 flex w-[248px] flex-col border-r border-[#e9ede4] bg-white px-5 py-6 transition-transform lg:translate-x-0 ${mobileNav ? 'translate-x-0' : '-translate-x-full'}`}>
    <div className="flex items-center justify-between"><div className="flex items-center gap-2.5"><div className="grid h-9 w-9 place-items-center rounded-xl bg-field text-lime"><Leaf size={19}/></div><span className="font-display text-[19px] font-extrabold tracking-tight">orbit<span className="text-field">_crop</span></span></div><button className="rounded-lg p-1 lg:hidden" onClick={() => setMobileNav(false)} aria-label="Close menu"><X size={18}/></button></div>
    {['FIELD', 'PLAN', 'INSIGHTS', 'SAFETY'].map(group => <div key={group} className="mt-9 first:mt-10"><div className="px-3 text-[10px] font-bold uppercase tracking-[.16em] text-[#a1aca0]">{group === 'FIELD' ? 'Workspace' : group === 'PLAN' ? 'Planning' : group === 'SAFETY' ? 'Safety' : 'Insights'}</div><nav className="mt-2 space-y-1">{NAV.filter(link => link.group === group).map(link => <button key={link.id} onClick={() => { setActive(link.id); setMobileNav(false) }} className={`flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left text-[12px] font-bold transition ${active === link.id ? 'bg-[#edf4e8] text-field' : 'text-[#849185] hover:bg-[#f7f9f5] hover:text-ink'}`}><span className="relative grid place-items-center"><link.icon size={17}/>{link.id === 'alerts' && activeDisasterCount > 0 && <span className="absolute -right-2 -top-2 grid h-4 min-w-4 place-items-center rounded-full bg-red-600 px-1 text-[8px] font-extrabold text-white shadow-sm" aria-label={`${activeDisasterCount} active hazards`}>{activeDisasterCount > 9 ? '9+' : activeDisasterCount}</span>}</span>{link.label}</button>)}</nav></div>)}
    <div className="mt-auto rounded-2xl bg-[#f3f6ef] p-4"><div className="flex items-center gap-2 text-[12px] font-bold"><CircleHelp size={15} className="text-field"/> Field note</div><p className="mb-0 mt-2 text-[10px] leading-relaxed text-[#748275]">Climate and crop scores are planning aids. Validate with local observations, soil tests, and extension advice.</p></div>
    <div className="relative mt-4 border-t border-[#edf0ea] pt-4"><button onClick={() => setAccountOpen(value => !value)} aria-expanded={accountOpen} className="flex w-full items-center gap-3 text-left"><div className="grid h-9 w-9 place-items-center rounded-full bg-[#dbe9d3] text-[11px] font-bold text-field">FM</div><div><div className="text-[11px] font-bold">Farm manager</div><div className="text-[10px] text-[#94a094]">My workspace</div></div><ChevronDown className="ml-auto text-[#94a094]" size={15}/></button>{accountOpen && <div className="absolute bottom-14 left-0 z-40 w-full rounded-xl border border-[#e5eae1] bg-white p-2 shadow-lg"><button onClick={() => { setHelpOpen(true); setAccountOpen(false) }} className="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-[#f5f7f1]">Data & privacy notes</button><button onClick={() => { setActive('overview'); setAccountOpen(false) }} className="w-full rounded-lg px-3 py-2 text-left text-xs hover:bg-[#f5f7f1]">Farm settings</button></div>}</div>
  </aside>

  return <div className="min-h-screen bg-mist text-ink">
    {sidebar}{mobileNav && <button className="fixed inset-0 z-20 bg-black/25 lg:hidden" onClick={() => setMobileNav(false)} aria-label="Close navigation overlay"/>}
    <main className="min-h-screen pb-[calc(5.25rem+env(safe-area-inset-bottom))] lg:pb-0 lg:ml-[248px]">
      <header className="sticky top-0 z-10 flex min-h-[68px] flex-wrap items-center justify-between gap-2 border-b border-[#e8ece3] bg-mist/95 px-3 py-2 backdrop-blur sm:px-8"><div className="min-w-0 flex items-center gap-2 sm:gap-3"><button onClick={() => setMobileNav(true)} className="rounded-lg p-1 lg:hidden" aria-label="Open navigation"><Menu size={20}/></button><div className="text-[10px] font-medium text-[#8c9a8d] sm:text-[11px]">Workspace <span className="px-1">/</span> {sections[active]}</div></div><div className="relative order-3 min-w-0 w-full max-w-[440px] sm:order-none sm:flex-1 sm:px-4"><div className="relative"><Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[#879387]"/><ClearableInput value={placeQuery} onFocus={() => setPlaceOpen(true)} onChange={event => setPlaceQuery(event.target.value)} onClear={() => { setPlaceQuery(''); setPlaceOpen(false); setPlaceResults([]) }} clearLabel="Clear place search" onKeyDown={event => { if (event.key === 'Enter' && placeResults[0]) { event.preventDefault(); selectPlace(placeResults[0]) } if (event.key === 'Escape') setPlaceOpen(false) }} placeholder="Search village, district, state, or country" aria-label="Search any global place" className="pl-9" role="combobox" aria-expanded={placeOpen && placeResults.length > 0} aria-controls="place-search-results"/></div>{placeOpen && placeResults.length > 0 && <div id="place-search-results" role="listbox" className="absolute left-0 right-0 top-full z-50 mt-1 max-h-64 overflow-auto rounded-xl border border-[#e5eae1] bg-white p-1 shadow-xl">{placeResults.map((place, index) => <button role="option" aria-selected="false" key={`${place.latitude}-${place.longitude}-${index}`} onClick={() => selectPlace(place)} className="flex w-full items-start gap-2 rounded-lg px-3 py-2 text-left text-xs hover:bg-[#f5f7f1]"><MapPin size={13} className="mt-0.5 shrink-0 text-field"/><span>{place.label}<span className="mt-0.5 block text-[9px] text-[#8d998e]">{place.latitude.toFixed(4)}, {place.longitude.toFixed(4)}</span></span></button>)}</div>}</div><div className="ml-auto flex shrink-0 items-center gap-1.5 sm:gap-2">{!isInstalled && <button onClick={installApp} className="flex items-center gap-1.5 rounded-xl bg-field px-2.5 py-2 text-[10px] font-bold text-white shadow-sm hover:bg-[#1e4b34] sm:px-3" aria-label="Install Orbit Crop"><Download size={14}/><span className="hidden sm:inline">Install app</span></button>}<button onClick={detectMyLocation} className="flex items-center gap-1.5 rounded-xl border border-[#e5eae1] bg-white px-2.5 py-2 text-[10px] font-bold text-field sm:px-3" title="Detect my field using device GPS"><LocateFixed size={14}/><span className="hidden sm:inline">Detect My Soil</span></button><span className="hidden max-w-[180px] truncate text-[9px] text-[#819082] xl:inline" title={geoStatus}>{geoStatus}</span><button onClick={() => setHelpOpen(true)} className="grid h-9 w-9 place-items-center rounded-full border border-[#e5eae1] bg-white text-[#748275]" aria-label="Help and data notes"><CircleHelp size={16}/></button></div></header>
      <div className="mx-auto max-w-[1420px] px-4 pb-10 pt-7 sm:px-8">
        {error && <div role="alert" className="mb-5 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-xs leading-relaxed text-red-800"><AlertTriangle className="mt-0.5 shrink-0" size={15}/><span>{error}</span><button onClick={() => setError('')} className="ml-auto" aria-label="Dismiss error"><X size={15}/></button></div>}

        {active === 'overview' && <>
          <SectionTitle eyebrow="Field intelligence" title="Field overview" detail="Map the field, inspect climate signals, and compare crop options." action={analyzeButton}/>
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.25fr)_minmax(340px,.8fr)]">
            <Card><CardTitle sub="Enter the pin location or draw the field boundary on the map.">Field location & boundary</CardTitle><form onSubmit={analyze} className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className="text-[10px] font-bold text-[#657467]">Latitude<input type="number" step="0.000001" min="-90" max="90" required value={coordinates.latitude} onChange={e => { const val = parseFloat(e.target.value); updateCoordinates({ ...coordinates, latitude: Number.isFinite(val) ? val : e.target.value }) }} className="form-input mt-1.5"/></label>
              <label className="text-[10px] font-bold text-[#657467]">Longitude<input type="number" step="0.000001" min="-180" max="180" required value={coordinates.longitude} onChange={e => { const val = parseFloat(e.target.value); updateCoordinates({ ...coordinates, longitude: Number.isFinite(val) ? val : e.target.value }) }} className="form-input mt-1.5"/></label>
              <label className="text-[10px] font-bold text-[#657467]">Soil type<select value={soilType} onChange={e => { setSoilType(e.target.value); setPayload(null) }} className="form-input mt-1.5"><option value="">Auto-detect soil</option><option>Loamy</option><option>Clay</option><option>Sandy</option><option>Laterite</option></select></label>
              <label className="text-[10px] font-bold text-[#657467]">Previous crop<select value={previousCrop} onChange={e => { setPreviousCrop(e.target.value); setPayload(null) }} className="form-input mt-1.5">{['Rice', 'Maize', 'Wheat', 'Sugarcane', 'Pulses', 'Groundnut', 'Soybean', 'Millets', 'Cotton', 'Other'].map(crop => <option key={crop}>{crop}</option>)}</select></label>
              <div className="flex flex-wrap items-center gap-3 sm:col-span-2 lg:col-span-4"><button type="submit" disabled={loading} className="rounded-xl bg-[#eaf2e4] px-4 py-2.5 text-[11px] font-bold text-field hover:bg-[#dcebd1] disabled:opacity-60">{loading ? 'Analyzing…' : 'Analyze field'}</button><label className="flex items-center gap-2 text-[10px] font-semibold text-[#7d8a7e]">History<select value={years} onChange={e => { setYears(Number(e.target.value)); setPayload(null) }} className="rounded-lg border border-[#e7ebe4] bg-white px-2 py-1.5 text-[10px] font-bold"><option value={1}>1 year</option><option value={2}>2 years</option><option value={3}>3 years</option><option value={4}>4 years</option><option value={5}>5 years</option></select></label><span className="text-[10px] text-[#a0aa9f]">{polygon.length >= 3 ? `${polygon.length} boundary points ready` : 'Optional polygon supports multi-point perimeter estimates'}</span></div>
            </form>{payload?.soil_detection && <div role="status" className="mb-3 rounded-xl border border-[#e8ece3] bg-[#f8faf6] px-3 py-2 text-[10px] leading-relaxed text-[#657467]"><b>{payload.soil_detection.status === 'detected' ? 'Auto-detected soil' : payload.soil_detection.status === 'manual' ? 'Selected soil type' : 'Soil type not resolved'}:</b> {payload.soil_detection.texture_class || payload.soil_detection.soil_type || 'Choose a soil type or retry detection.'} <span className="text-[#899589]">{payload.soil_detection.source ? `· ${payload.soil_detection.source}` : ''} {payload.soil_detection.status === 'unavailable' ? '· The analysis does not assume loam.' : ''}</span></div>}<div className="mt-4"><Suspense fallback={<div className="grid min-h-[330px] place-items-center rounded-2xl bg-[#f7f9f5] text-xs text-[#829084]">Loading Leaflet map…</div>}><FarmMap latitude={coordinates.latitude} longitude={coordinates.longitude} polygon={polygon} setPolygon={updatePolygon} onLocationChange={updateCoordinates} areaHectares={payload?.field?.area_hectares}/></Suspense></div></Card>
            <div className="space-y-5"><div className="relative overflow-hidden rounded-[20px] bg-field p-5 text-white sm:p-6"><div className="absolute -right-8 -top-10 h-40 w-40 rounded-full border border-white/10"/><div className="relative"><div className="flex items-center gap-2 text-[10px] font-bold uppercase tracking-widest text-white/65"><Sun size={14} className="text-lime"/> Seasonal outlook</div><h2 className="mt-6 font-display text-[25px] font-extrabold">{payload?.analysis?.climate_classification || 'Ready for your field'}</h2><p className="mt-1 text-xs text-white/70">{payload ? `${payload.analysis.water_availability} water availability` : 'Run an analysis to load historical climate conditions'}</p><div className="my-5 h-px bg-white/15"/><div className="grid grid-cols-2 gap-4"><div><div className="text-[10px] text-white/55">Annual rainfall estimate</div><div className="mt-1 font-display text-xl font-bold">{payload?.analysis?.summary?.mean_rainfall_mm_day != null ? Math.round(payload.analysis.summary.mean_rainfall_mm_day * 365) : '—'}<span className="ml-1 text-[10px] font-medium text-white/60">mm*</span></div></div><div><div className="text-[10px] text-white/55">Mean temperature</div><div className="mt-1 font-display text-xl font-bold">{payload?.analysis?.summary?.mean_temperature_c ?? '—'}<span className="ml-1 text-[10px] font-medium text-white/60">°C</span></div></div></div>{payload?.analysis?.summary?.wettest_month && <div className="mt-5 rounded-xl bg-white/10 px-3 py-2.5 text-[10px] text-white/75">Wettest: {payload.analysis.summary.wettest_month} · Driest: {payload.analysis.summary.driest_month}</div>}<div className="mt-2 text-[9px] text-white/45">*Mean daily precipitation rate × 365.</div></div></div>
              <div className="grid grid-cols-2 gap-3"><Metric icon={Droplets} label="Root-zone wetness" value={latestWithWetness?.GWETROOT?.toFixed(3) ?? latest?.GWETROOT?.toFixed(3) ?? '—'} unit="fraction" note="NASA POWER GWETROOT · latest record"/><Metric icon={Activity} label="Field area" value={payload?.field?.area_hectares ?? '—'} unit="ha" note="Geodesic polygon estimate" tone="amber"/></div></div>
          </div>
          <div className="mt-5 grid gap-5 xl:grid-cols-[1.15fr_.85fr]"><Card><CardTitle sub="All available crop candidates with comparative climate suitability." action={<span className="rounded-full bg-[#f2f6ed] px-2.5 py-1 text-[10px] font-bold text-field">{recommendations.length} options</span>}>Crop matches</CardTitle><Suspense fallback={<div className="p-4 text-xs">Loading crop library…</div>}><CropSuitabilityPanel crops={recommendations} customResult={payload?.crop_suitability?.custom_crop_check} customName={customName} setCustomName={setCustomName} customCategory={customCategory} setCustomCategory={setCustomCategory} onCheckCustom={checkCustomCrop} onSelect={pickCrop}/></Suspense><button onClick={() => setActive('rotation')} className="mt-4 w-full rounded-xl border border-[#e7ece3] py-2.5 text-[10px] font-bold text-[#68776b] hover:bg-[#f8faf6]">Open rotation planner</button></Card><Card><CardTitle sub="Monthly climate normals calculated from the selected history period.">Weather at a glance</CardTitle>{monthly.length ? <WeatherChart data={monthly}/> : <EmptyPanel icon={CloudRain} title="No field history loaded">Analyze your field to retrieve temperature, rainfall, wetness, and solar radiation from NASA POWER.</EmptyPanel>}</Card></div>
        </>}

        {active === 'calendar' && <><SectionTitle eyebrow="Season planning" title="Crop calendar" detail="Growth-stage windows for the selected crop and local planting season." action={analyzeButton}/><Card><div className="grid gap-4 sm:grid-cols-3"><label className="text-[11px] font-bold text-[#657467]">Crop<select value={rotation[0]} onChange={e => setRotation([e.target.value, ...rotation.slice(1)])} className="form-input mt-2">{allCrops.map(crop => <option key={crop.crop}>{crop.crop}</option>)}</select></label><label className="text-[11px] font-bold text-[#657467]">Planting month<select value={calendarStart} onChange={e => setCalendarStart(e.target.value)} className="form-input mt-2"><option value="recommended">Use crop's recommended window</option>{MONTHS.map((m, i) => <option key={m} value={i}>{m}</option>)}</select></label><label className="text-[11px] font-bold text-[#657467]">Growing season<select value={calendarSeason} onChange={e => setCalendarSeason(e.target.value)} className="form-input mt-2"><option value="current">Next local season</option><option value="kharif">Kharif</option><option value="rabi">Rabi</option><option value="zaid">Zaid</option></select></label></div></Card><GrowthCalendar crop={allCrops.find(crop => crop.crop === rotation[0])} startMonth={resolveStartMonth(calendarStart, calendarSeason, allCrops.find(crop => crop.crop === rotation[0]))}/><p className="mt-4 text-[10px] leading-relaxed text-[#909b8f]">Stage spans are estimated from typical crop duration and your selected sowing month, not a phenology model. Tune dates to the locally recommended variety and observed sowing date.</p></>}

        {active === 'rotation' && <><SectionTitle eyebrow="Crop sequence" title="Rotation planner" detail="Build, edit, and validate crop sequences for multiple seasons." action={analyzeButton}/><Card className="mb-4"><div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="font-display text-sm font-extrabold">Adapt to Country Requirements</h2><p className="mb-0 mt-1 text-[11px] text-[#879387]">Apply a staple-crop ranking signal. This is not a legal or fertilizer compliance check.</p></div><label className="flex items-center gap-2 text-xs font-bold"><input type="checkbox" checked={adaptCountry} onChange={event => { setAdaptCountry(event.target.checked); setPayload(null) }}/> Enabled</label><select aria-label="Country" value={countryCode} onChange={event => { setCountryCode(event.target.value); setPayload(null) }} className="form-input max-w-[220px]" disabled={!adaptCountry}><option value="">Choose country</option>{countryOptions.map(country => <option key={country.code} value={country.code}>{country.country}</option>)}</select></div>{adaptCountry && <p className="mb-0 mt-3 text-[10px] leading-relaxed text-[#7b887c]">{countryOptions.find(country => country.code === countryCode)?.note || 'No country profile is configured. Climate recommendations will remain unchanged.'} {countryOptions.find(country => country.code === countryCode)?.source_url && <a className="underline" href={countryOptions.find(country => country.code === countryCode).source_url} target="_blank" rel="noreferrer">Profile source</a>}</p>}</Card>{!payload && <div className="mb-4 rounded-xl bg-amber-50 p-3 text-xs text-amber-900">Preview sequence is illustrative. Analyze your field for climate-based rankings.</div>}<Card><CardTitle sub="Choose a crop for each season; open any crop for full requirements and feasibility." action={<span className="rounded-full bg-[#f0f5eb] px-2.5 py-1.5 text-[10px] font-bold text-field"><Check className="mr-1 inline" size={12}/> Family rotation</span>}>Custom sequence</CardTitle><form onSubmit={addCustomCrop} className="mb-4 grid gap-2 rounded-xl border border-[#edf0ea] p-3 sm:grid-cols-[1fr_1fr_auto]"><ClearableInput value={customName} onChange={event => setCustomName(event.target.value)} onClear={() => setCustomName('')} maxLength={80} placeholder="Any crop name" aria-label="Custom crop name" clearLabel="Clear crop name" required/><ClearableInput value={customFamily} onChange={event => setCustomFamily(event.target.value)} onClear={() => setCustomFamily('')} maxLength={80} placeholder="Botanical family (optional)" aria-label="Botanical family" clearLabel="Clear botanical family"/><button className="rounded-xl bg-field px-4 py-2 text-xs font-bold text-white">Add custom crop</button></form><div className="grid gap-4 md:grid-cols-3">{rotation.map((crop, index) => <div key={`${index}-${crop}`} className="rounded-2xl bg-[#f8faf6] p-4"><div className="flex items-center justify-between"><span className="rounded-full bg-white px-2.5 py-1 text-[9px] font-bold text-[#788779]">SEASON {String(index + 1).padStart(2, '0')}</span><button onClick={() => pickCrop(crop)} className="text-[10px] font-bold text-field">Crop details</button></div><select value={crop} onChange={e => setRotation(current => current.map((value, slot) => slot === index ? e.target.value : value))} className="form-input mt-3">{allCrops.map(item => <option key={item.crop}>{item.crop}</option>)}</select><div className="mt-3 space-y-2 text-[10px] text-[#788579]"><p><b className="text-[#5d6c60]">Sowing:</b> {allCrops.find(item => item.crop === crop)?.sow || 'Use locally recommended planting window'}</p><p><b className="text-[#5d6c60]">Harvest:</b> {allCrops.find(item => item.crop === crop)?.harvest || 'Variety dependent'}</p><p>{allCrops.find(item => item.crop === crop)?.irrigation}</p></div><div className="mt-3 flex items-center justify-between"><button onClick={() => pickCrop(crop)} className="rounded-lg bg-white px-3 py-2 text-[10px] font-bold text-field">Evaluate crop</button><button onClick={() => setRotation(current => current.filter((_, slot) => slot !== index))} className="rounded-lg px-2 py-2 text-[10px] font-bold text-red-700" aria-label={`Remove season ${index + 1}`}>Remove</button></div></div>)}</div><div className="mt-4 flex flex-wrap gap-2"><button onClick={() => setRotation(current => [...current, allCrops[0]?.crop || 'Pulses'])} className="rounded-xl border border-[#e7ece3] px-3 py-2 text-xs font-bold text-field">+ Add season</button><button onClick={() => setRotation(['Pulses', 'Groundnut', 'Millets'])} className="rounded-xl border border-[#e7ece3] px-3 py-2 text-xs font-bold text-[#68776b]">Reset sequence</button></div>{rotationWarnings.length > 0 && <div role="status" className="mt-4 space-y-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-xs text-amber-950">{rotationWarnings.map((warning, i) => <p key={i} className="mb-0">Season {warning.season}: {warning.message}</p>)}</div>}<div className="mt-5 rounded-xl border border-[#edf0ea] p-4 text-xs leading-relaxed text-[#69786c]">{previousCrop} was the crop before season 1. Legumes can add biological nitrogen when inoculation and growing conditions are suitable. Confirm family, disease, nutrient, and local market requirements with extension services.</div></Card><Card className="mt-5"><CardTitle sub="Alternatives include lower-scoring options for more choice.">Crop alternatives</CardTitle><CropList crops={recommendations} onSelect={pickCrop}/></Card></>}

        {active === 'soil' && <><SectionTitle eyebrow="Soil profile · Open-Meteo / SoilGrids" title="Soil health" detail="Multi-depth water, texture, rocks, pH, and structure from global model grids." action={analyzeButton}/>{payload ? <Suspense fallback={<div className="rounded-xl bg-white p-5 text-xs">Loading soil profile…</div>}><SoilProfilePanel report={payload} onRefresh={analyze} loading={loading}/></Suspense> : <Card><EmptyPanel icon={Droplets} title="Detect a location to load soil layers">Use device GPS, search for a place, or enter coordinates and analyze the field.</EmptyPanel></Card>}</>}        {active === 'alerts' && <><SectionTitle eyebrow="Weather & emergency awareness" title="Disaster Alerts" detail="Global farm hazard outlook, source-issued alerts, and crop-saving steps."/><Suspense fallback={<Card><div className="text-xs text-[#829084]">Loading safety center…</div></Card>}><DisasterAlerts report={disasterReport} loading={disasterLoading} offline={disasterOffline} error={disasterError} onRefresh={() => { setDisasterError(''); setDisasterLoading(true); const query = new URLSearchParams({ lat: String(coordinates.latitude), lon: String(coordinates.longitude), country: countryCode || '', crop: rotation[0] || '' }); fetch(`${API}/api/disaster-alerts?${query}`).then(response => response.ok ? response.json() : Promise.reject(new Error('Disaster outlook could not be refreshed.'))).then(result => { setDisasterReport(result); setDisasterOffline(false); window.localStorage.setItem('orbit:last-disaster-report:v1', JSON.stringify(result)); window.localStorage.setItem(`orbit:disaster:v1:${coordinates.latitude.toFixed(3)}:${coordinates.longitude.toFixed(3)}:${countryCode}`, JSON.stringify(result)) }).catch(exception => setDisasterError(exception.message)).finally(() => setDisasterLoading(false)) }} countryCode={countryCode} coordinates={coordinates}/></Suspense></>}
        {active === 'weather' && <><SectionTitle eyebrow="NASA POWER · Agroclimatology" title="Weather history" detail={`Daily point or field-perimeter estimate · ${previousDates}`} action={analyzeButton}/>{monthly.length ? <><div className="grid gap-4 sm:grid-cols-3"><Metric icon={CloudRain} label="Mean daily precipitation" value={payload.analysis.summary.mean_rainfall_mm_day} unit="mm/day" tone="blue"/><Metric icon={Thermometer} label="Mean temperature" value={payload.analysis.summary.mean_temperature_c} unit="°C" tone="amber"/><Metric icon={Sun} label="Mean solar shortwave" value={(monthly.reduce((sum, item) => sum + (item.solar_kwh_m2_day || 0), 0) / Math.max(1, monthly.filter(item => item.solar_kwh_m2_day != null).length)).toFixed(2)} unit="kWh/m²/day"/></div><Card className="mt-5"><CardTitle sub={`Precipitation and temperature normals · ${payload.data_source.time_standard} · NASA units ${payload.data_source.solar_unit}`}>12-month climate profile</CardTitle><WeatherChart data={monthly} tall/></Card><Card className="mt-5"><CardTitle sub="Most recent daily observations in the selected history period.">Daily records</CardTitle><div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left text-xs"><thead className="border-b border-[#edf0ea] text-[10px] uppercase tracking-wide text-[#91a092]"><tr>{['Date', 'Rainfall (mm/day)', 'Temperature (°C)', 'Solar (kWh/m²/day)', 'Root wetness'].map(h => <th key={h} className="px-3 py-3">{h}</th>)}</tr></thead><tbody>{daily.slice(-14).reverse().map(day => <tr key={day.date} className="border-b border-[#f1f3ef]"><td className="px-3 py-3 font-semibold">{day.date}</td><td className="px-3 py-3">{day.PRECTOTCORR?.toFixed(2) ?? '—'}</td><td className="px-3 py-3">{day.T2M?.toFixed(1) ?? '—'}</td><td className="px-3 py-3">{day.ALLSKY_SFC_SW_DWN?.toFixed(2) ?? '—'}</td><td className="px-3 py-3">{day.GWETROOT?.toFixed(3) ?? '—'}</td></tr>)}</tbody></table></div></Card></> : <Card><EmptyPanel icon={CloudRain} title="Load field weather history">Enter the coordinate or boundary and analyze to fetch daily NASA POWER records and monthly summaries.</EmptyPanel></Card>}<p className="mt-4 text-[10px] text-[#929d91]">NASA POWER daily values are gridded model / observation products. Point coordinates are queried exactly; a small field may overlap one source grid cell.</p></>}

{payload && <footer className="mt-6 flex flex-wrap items-center justify-between gap-2 px-1 text-[9px] text-[#a0aaa0]"><span>Climate source: <a href={payload.data_source?.url || 'https://power.larc.nasa.gov/'} target="_blank" rel="noreferrer" className="underline">NASA POWER <ExternalLink className="inline" size={10}/></a></span><span>Records {payload.data_source?.start || '—'} – {payload.data_source?.end || '—'} · {payload.data_source?.time_standard || 'UTC'}</span><span>{payload.field?.sampling?.method || 'Point coordinate sampling'}</span></footer>}
      </div>
      <footer className="mx-auto max-w-[1420px] px-4 pb-3 text-center text-[9px] leading-relaxed text-[#929d91] sm:px-8">Code and derived crop or hazard estimates are SI-assisted; external observations retain their providers' attribution. <a className="font-semibold underline underline-offset-2" href={`${API}/api/metadata`} target="_blank" rel="noreferrer">View provenance metadata</a>.</footer>
    </main>
    <nav aria-label="Mobile app navigation" className="mobile-app-nav fixed inset-x-0 bottom-0 z-40 grid grid-cols-6 border-t border-[#e4e9df] bg-white/95 px-1 pt-2 shadow-[0_-8px_28px_rgba(31,50,35,.08)] backdrop-blur lg:hidden">
      {NAV.map(link => <button key={link.id} onClick={() => { setActive(link.id); setMobileNav(false) }} aria-current={active === link.id ? 'page' : undefined} className={`relative flex min-w-0 flex-col items-center justify-center gap-1 rounded-xl px-0.5 pb-[calc(.35rem+env(safe-area-inset-bottom))] pt-1 text-center transition ${active === link.id ? 'text-field' : 'text-[#879387]'}`}>
        <span className={`relative grid h-7 w-9 place-items-center rounded-xl ${active === link.id ? 'bg-[#edf4e8]' : ''}`}><link.icon size={18}/>{link.id === 'alerts' && activeDisasterCount > 0 && <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-red-600 px-1 text-[8px] font-extrabold text-white" aria-label={`${activeDisasterCount} active hazards`}>{activeDisasterCount > 9 ? '9+' : activeDisasterCount}</span>}</span>
        <span className="max-w-full truncate text-[8px] font-bold leading-none">{{ overview: 'Field', calendar: 'Calendar', rotation: 'Rotation', weather: 'Weather', soil: 'Soil', alerts: 'Alerts' }[link.id]}</span>
      </button>)}
    </nav>
    {selectedCrop && <Suspense fallback={null}><CropDetail crop={selectedCrop} soilType={payload?.selected_soil_type || soilType || null} onClose={() => setSelectedCrop(null)}/></Suspense>}
    {helpOpen && <div className="fixed inset-0 z-50 grid place-items-center bg-[#142017]/35 p-4" onMouseDown={event => event.target === event.currentTarget && setHelpOpen(false)}><section role="dialog" aria-modal="true" className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl"><div className="flex items-center justify-between"><h2 className="font-display text-lg font-extrabold">Data & setup notes</h2><button aria-label="Close help" onClick={() => setHelpOpen(false)}><X size={18}/></button></div><p className="mt-3 text-xs leading-relaxed text-[#69786c]">Field maps use OpenStreetMap. NASA POWER / SMAP products are gridded model products. Texture and field-averaged NDVI scores require separate sources. Crop risk, yields, prices, and local regulations vary by location and season.</p><button onClick={() => { setHelpOpen(false); setActive('soil') }} className="mt-3 rounded-lg bg-[#edf4e8] px-3 py-2 text-xs font-bold text-field">View soil data availability</button></section></div>}
    {installHelpOpen && <div className="fixed inset-0 z-50 grid place-items-center bg-[#142017]/40 p-4" onMouseDown={event => event.target === event.currentTarget && setInstallHelpOpen(false)}><section role="dialog" aria-modal="true" aria-labelledby="install-title" className="w-full max-w-md rounded-2xl bg-white p-6 shadow-2xl"><div className="flex items-center justify-between gap-3"><h2 id="install-title" className="font-display text-lg font-extrabold">Install Orbit Crop</h2><button onClick={() => setInstallHelpOpen(false)} aria-label="Close install instructions" className="rounded-lg p-2 hover:bg-[#f3f6ef]"><X size={18}/></button></div><p className="mt-2 text-xs leading-relaxed text-[#69786c]">Add this app to your home screen or desktop for a focused, app-like experience. Installation requires a secure site (HTTPS) or localhost.</p><ol className="mt-4 list-decimal space-y-2 pl-5 text-xs leading-relaxed text-[#526455]"><li><b>Android / Chrome:</b> open the browser menu and choose <i>Install app</i> or <i>Add to Home screen</i>.</li><li><b>iPhone / iPad:</b> in Safari, tap Share, then <i>Add to Home Screen</i>.</li><li><b>Windows / Mac:</b> in Chrome or Edge, use the install icon in the address bar or the browser menu.</li></ol><p className="mb-0 mt-4 rounded-xl bg-[#f3f6ef] p-3 text-[10px] leading-relaxed text-[#68776b]">The app shell and saved disaster alerts remain available offline. Fresh weather and soil analyses need an internet connection.</p></section></div>}
  </div>
}

function CropList({ crops, onSelect }) { return <div className="space-y-2">{crops.map((crop, index) => <button key={crop.crop} onClick={() => onSelect(crop.crop)} className="w-full rounded-[14px] border border-[#edf0ea] p-3 text-left transition hover:border-[#c9d9bf] hover:bg-[#fbfcfa]"><div className="flex items-center gap-3"><div className={`grid h-9 w-9 shrink-0 place-items-center rounded-xl ${index === 0 ? 'bg-[#edf5e7] text-field' : 'bg-[#f5f6f1] text-[#839082]'}`}><Sprout size={17}/></div><div className="min-w-0 flex-1"><div className="flex items-center gap-2"><span className="text-xs font-bold">{crop.crop}</span>{index === 0 && <span className="rounded-full bg-[#eef5e7] px-1.5 py-0.5 text-[8px] font-bold uppercase text-field">Top fit</span>}</div><div className="mt-0.5 text-[10px] text-[#8c998d]">{crop.season} · {crop.family} · {crop.risk_profile || crop.risk}</div></div><div className="text-right"><div className="text-sm font-extrabold text-field">{crop.score ?? '—'}<span className="text-[9px]">%</span></div><div className="text-[8px] text-[#a0aaa0]">match</div></div></div><div className="mt-2 h-1 overflow-hidden rounded-full bg-[#f0f2ed]"><div className="h-full rounded-full bg-[#8ab584]" style={{ width: `${crop.score || 0}%` }}/></div></button>)}</div> }
function WeatherChart({ data, tall = false }) { return <div className={`${tall ? 'h-[340px]' : 'h-[230px]'} w-full`}><ResponsiveContainer width="100%" height="100%"><AreaChart data={data} margin={{ top: 8, right: 5, left: -18, bottom: 0 }}><defs><linearGradient id="rainFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8ab584" stopOpacity={0.22}/><stop offset="95%" stopColor="#8ab584" stopOpacity={0.01}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#edf0ea" strokeDasharray="3 5"/><XAxis dataKey="month_name" tickLine={false} axisLine={false} tick={{ fill: '#929e92', fontSize: 10 }} dy={9}/><YAxis yAxisId="rain" tickLine={false} axisLine={false} tick={{ fill: '#a0aaa0', fontSize: 9 }} width={30}/><YAxis yAxisId="temp" orientation="right" tickLine={false} axisLine={false} tick={{ fill: '#a0aaa0', fontSize: 9 }} width={35}/><Tooltip contentStyle={{ border: '1px solid #e8ece3', borderRadius: 12, fontSize: 11 }} formatter={(value, name) => [`${value}${name === 'Temperature' ? ' °C' : ' mm/day'}`, name]}/><Area yAxisId="rain" type="monotone" dataKey="rainfall_mm_day" name="Rainfall" stroke="#78a773" strokeWidth={2.3} fill="url(#rainFill)"/><Line yAxisId="temp" type="monotone" dataKey="temperature_c" name="Temperature" stroke="#d9a747" strokeWidth={2} dot={false}/></AreaChart></ResponsiveContainer></div> }
function validateRotation(rotation, crops, previousCrop) {
  const warnings = []
  if (!rotation.length) return warnings
  const first = crops.find(item => item.crop === rotation[0])
  if (['rice', 'maize', 'wheat', 'sugarcane'].includes(previousCrop?.toLowerCase()) && first && first.family !== 'legume' && !first.botanical_family?.toLowerCase().includes('fabaceae')) warnings.push({ season: 1, message: `After ${previousCrop}, consider a legume or cover crop before another non-legume.` })
  const prevFamily = previousCrop?.toLowerCase() === 'sugarcane' ? 'poaceae' : crops.find(item => item.crop?.toLowerCase() === previousCrop?.toLowerCase())?.botanical_family?.toLowerCase()
  if (prevFamily && first?.botanical_family?.toLowerCase() === prevFamily) warnings.push({ season: 1, message: `${first.crop} shares ${first.botanical_family} with the previous crop; consider a family break to reduce shared pest and disease pressure.` })
  rotation.forEach((name, index) => {
    if (!index) return
    const before = crops.find(item => item.crop === rotation[index - 1])
    const current = crops.find(item => item.crop === name)
    const family = current?.botanical_family?.toLowerCase()
    if (before?.botanical_family && family && family !== 'unknown' && !family.includes('species dependent') && before.botanical_family.toLowerCase() === family) warnings.push({ season: index + 1, message: `${name} follows the same botanical family; consider a family break to reduce shared pest and disease pressure.` })
    if (['rice', 'maize', 'wheat', 'sugarcane'].includes(before?.crop?.toLowerCase()) && current && current.family !== 'legume' && !family?.includes('fabaceae')) warnings.push({ season: index + 1, message: `After ${before.crop}, consider a legume or cover crop before another non-legume.` })
  })
  return warnings
}
function resolveStartMonth(selectedMonth, season, crop) {
  if (selectedMonth !== 'recommended') return Number(selectedMonth)
  if (season === 'kharif') return 5
  if (season === 'rabi') return 9
  if (season === 'zaid') return 2
  const firstMonth = crop?.sow?.match(/January|February|March|April|May|June|July|August|September|October|November|December/i)?.[0]
  return Math.max(0, MONTHS.findIndex(month => month.toLowerCase() === (firstMonth || 'June').slice(0, 3).toLowerCase()))
}
function GrowthCalendar({ crop, startMonth }) {
  const stages = [
    { title: 'Land preparation', share: 12, icon: Wheat, note: 'Soil test, land preparation, and drainage planning' },
    { title: 'Sowing & establishment', share: 13, icon: Sprout, note: crop?.sow || 'Use the locally recommended sowing window' },
    { title: 'Vegetative growth', share: 30, icon: Leaf, note: 'Weed control, nutrition, and stand monitoring' },
    { title: 'Flowering / reproductive', share: 25, icon: Sun, note: 'Protect from water stress and scout for pests' },
    { title: 'Maturity & harvest', share: 20, icon: Check, note: crop?.harvest || 'Harvest timing depends on cultivar and conditions' },
  ]
  const durationMatch = crop?.harvest?.match(/(\d+)[–-](\d+)\s*months/i)
  const duration = durationMatch ? (Number(durationMatch[1]) + Number(durationMatch[2])) / 2 : 4
  let accumulated = 0
  const windows = stages.map(stage => { const phaseStart = accumulated; accumulated += stage.share; return { ...stage, phaseStart } })
  return <Card className="mt-5"><CardTitle sub={`${crop?.crop || 'Selected crop'} · typical cycle: ${crop?.harvest || 'variety dependent'} · sowing month: ${MONTHS[startMonth]}`}>Season stages</CardTitle>
    <div className="mb-3 hidden grid-cols-12 gap-1 pl-[160px] text-[9px] font-bold text-[#929e92] md:grid">{MONTHS.map(month => <span key={month} className="text-center">{month}</span>)}</div>
    {windows.map((stage, index) => {
      const stageStart = (startMonth + (duration * stage.phaseStart / 100)) % 12
      const width = Math.max(0.7, duration * stage.share / 100)
      const left = stageStart / 12 * 100
      const widthPercent = width / 12 * 100
      const firstWidth = Math.min(widthPercent, 100 - left)
      const wrappedWidth = widthPercent - firstWidth
      return <div key={stage.title} className="mb-4 grid gap-2 md:grid-cols-[150px_1fr]"><div className="flex items-center gap-2 text-xs font-bold"><stage.icon size={15} className="shrink-0 text-field"/><span>{stage.title}</span></div><div><div className="relative h-7 overflow-hidden rounded-lg bg-[#f3f5f1]"><div className="absolute top-1 h-5 rounded-md" title={stage.note} style={{ left: `${left}%`, width: `${firstWidth}%`, background: ['#dcebd1', '#cfe3c0', '#b8d4a8', '#a5c791', '#dfd5aa'][index] }}/>{wrappedWidth > 0 && <div className="absolute top-1 h-5 rounded-md" title={stage.note} style={{ left: 0, width: `${wrappedWidth}%`, background: ['#dcebd1', '#cfe3c0', '#b8d4a8', '#a5c791', '#dfd5aa'][index] }}/>}</div><p className="mb-0 mt-1 text-[9px] text-[#869287]">{stage.note}</p></div></div>
    })}
    <div className="mt-4 rounded-xl border border-[#edf0ea] p-3 text-[10px] leading-relaxed text-[#778579]">{crop?.irrigation || 'Set irrigation from soil moisture observations and local recommendations.'}</div>
  </Card>
}
