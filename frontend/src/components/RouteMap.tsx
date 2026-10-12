import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { useEffect } from 'react'
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import { fmtDateTime, fmtDuration, fmtMiles, STOP_META } from '../format'
import type { TripPlan } from '../types'

function pin(color: string, content: string) {
  return L.divIcon({
    className: '',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
    popupAnchor: [0, -14],
    html: `<div style="width:30px;height:30px;border-radius:50%;background:${color};color:#fff;
      border:2.5px solid #fff;box-shadow:0 2px 6px rgba(0,0,0,.4);display:flex;align-items:center;
      justify-content:center;font:700 13px/1 system-ui,sans-serif">${content}</div>`,
  })
}

function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [40, 40] })
  }, [map, points])
  return null
}

export default function RouteMap({ plan }: { plan: TripPlan }) {
  const { locations, route, stops } = plan
  const line = route.coordinates

  return (
    <MapContainer
      center={[39.5, -98.35]}
      zoom={4}
      scrollWheelZoom={false}
      className="h-[420px] w-full rounded-xl lg:h-full lg:min-h-[480px]"
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <FitBounds points={line} />

      <Polyline positions={line} pathOptions={{ color: '#fff', weight: 8, opacity: 0.9 }} />
      <Polyline positions={line} pathOptions={{ color: '#0369a1', weight: 5 }} />

      <Marker position={[locations.current.lat, locations.current.lon]} icon={pin('#16a34a', 'S')}>
        <Popup>
          <strong>Start</strong>
          <br />
          {locations.current.label}
          <br />
          {fmtDateTime(plan.summary.start)}
        </Popup>
      </Marker>

      {stops.map((stop, i) => {
        const meta = STOP_META[stop.kind]
        return (
          <Marker key={i} position={[stop.lat, stop.lon]} icon={pin(meta.color, meta.icon)}>
            <Popup>
              <strong>{meta.label}</strong>
              <br />
              {stop.location} · mile {fmtMiles(stop.mile)}
              <br />
              {fmtDateTime(stop.start)}
              <br />
              Duration: {fmtDuration(stop.duration_hours)}
            </Popup>
          </Marker>
        )
      })}
    </MapContainer>
  )
}
