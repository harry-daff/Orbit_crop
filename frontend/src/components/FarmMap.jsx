import { useCallback, useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Marker, Polygon, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { Check, Layers3, MapPin, Minus, Plus, Undo2 } from 'lucide-react'

const markerIcon = L.divIcon({ className: '', html: '<span class="map-pin-dot"></span>', iconSize: [22, 22], iconAnchor: [11, 11] })
const ndviTime = new Date(Date.now() - 2 * 86400000).toISOString().slice(0, 10)

function MapEvents({ drawing, onVertex, onLocation }) {
  useMapEvents({ click(event) {
    const latitude = Number(event.latlng.lat.toFixed(6)); const longitude = Number(event.latlng.lng.toFixed(6))
    if (drawing) onVertex([longitude, latitude])
    else onLocation({ latitude, longitude })
  } })
  return null
}

function Recenter({ latitude, longitude }) {
  const map = useMap()
  useEffect(() => { map.flyTo([latitude, longitude], map.getZoom(), { duration: 0.6 }) }, [map, latitude, longitude])
  return null
}

export default function FarmMap({ latitude, longitude, polygon, setPolygon, onLocationChange, areaHectares }) {
  const [drawing, setDrawing] = useState(false)
  const [showNdvi, setShowNdvi] = useState(false)
  const [tileError, setTileError] = useState(false)
  const center = useMemo(() => [latitude, longitude], [latitude, longitude])
  const onVertex = useCallback(point => setPolygon(current => [...current, point]), [setPolygon])
  const closedRing = polygon.length >= 3 ? [...polygon, polygon[0]] : polygon
  const positions = closedRing.map(([lng, lat]) => [lat, lng])
  const handleDrag = useCallback(event => {
    const point = event.target.getLatLng()
    onLocationChange({ latitude: Number(point.lat.toFixed(6)), longitude: Number(point.lng.toFixed(6)) })
  }, [onLocationChange])

  return <div className="space-y-2">
    <div className="relative h-[370px] overflow-hidden rounded-2xl border border-[#dce3d9]">
      <MapContainer center={center} zoom={5} scrollWheelZoom className="farm-map">
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} eventHandlers={{ tileerror: () => setTileError(true), tileload: () => setTileError(false) }} />
        {showNdvi && <TileLayer attribution='Imagery &copy; <a href="https://earthdata.nasa.gov/">NASA GIBS</a>' url={`https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_NDVI_8Day/default/${ndviTime}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.png`} opacity={0.65} eventHandlers={{ tileerror: () => setTileError(true) }} />}
        <MapEvents drawing={drawing} onVertex={onVertex} onLocation={onLocationChange}/><Recenter latitude={latitude} longitude={longitude}/>
        <Marker position={center} icon={markerIcon} draggable eventHandlers={{ dragend: handleDrag }}><Tooltip>Field reference point</Tooltip></Marker>
        {positions.length >= 3 && <Polygon positions={positions} pathOptions={{ color: '#e4f3a3', weight: 3, fillColor: '#8aba72', fillOpacity: 0.22 }} />}
        {polygon.map(([lng, lat], i) => <CircleMarker key={`${lng}-${lat}-${i}`} center={[lat, lng]} radius={6} pathOptions={{ color: 'white', weight: 2, fillColor: '#315e41', fillOpacity: 1 }}><Tooltip>Boundary point {i + 1}</Tooltip></CircleMarker>)}
      </MapContainer>
      <div className="absolute right-3 top-3 z-[1000] flex flex-wrap justify-end gap-2">
        <button type="button" onClick={() => setShowNdvi(value => !value)} className={`flex items-center gap-1.5 rounded-xl px-3 py-2 text-xs font-bold shadow ${showNdvi ? 'bg-[#315e41] text-white' : 'bg-white text-ink'}`}><Layers3 size={14}/>{showNdvi ? 'Hide NASA NDVI' : 'NASA NDVI layer'}</button>
        <button type="button" onClick={() => setDrawing(value => !value)} className={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-bold shadow ${drawing ? 'bg-field text-white' : 'bg-white text-ink'}`}>{drawing ? <Check size={14}/> : <Plus size={14}/>} {drawing ? 'Finish boundary' : 'Draw boundary'}</button>
        {drawing && polygon.length > 0 && <button type="button" onClick={() => setPolygon(current => current.slice(0, -1))} className="rounded-xl bg-white px-3 py-2 text-xs font-bold text-ink shadow"><Undo2 size={14} className="inline"/> Undo</button>}
        {polygon.length > 0 && <button type="button" onClick={() => setPolygon([])} className="rounded-xl bg-white px-3 py-2 text-xs font-bold text-red-700 shadow"><Minus size={14} className="inline"/> Clear</button>}
      </div>
      {areaHectares != null && <div className="absolute bottom-3 left-3 z-[1000] rounded-lg bg-white/95 px-3 py-2 text-xs font-bold text-ink shadow">{areaHectares.toFixed(2)} ha</div>}
      {tileError && <div role="status" className="absolute bottom-3 right-3 z-[1000] max-w-[250px] rounded-lg bg-amber-50 px-3 py-2 text-[10px] leading-relaxed text-amber-950 shadow">Some map tiles failed to load. The public tile service may be temporarily unavailable or rate limited; retry shortly.</div>}
    </div>
    <p className="px-1 text-[11px] text-[#829084]">{drawing ? `Click the map to add boundary vertices (${polygon.length} points). Add at least 3, then finish.` : 'Click or drag the pin to set the exact reference coordinate. Map tiles © OpenStreetMap contributors.'} {showNdvi && 'NASA NDVI is a visual satellite layer, not a field-averaged numeric reading.'}</p>
  </div>
}
