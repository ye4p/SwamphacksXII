import { useEffect, useRef } from "react";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { config } from "../../config";
import type { Event } from "../../types";
import EventPopup from "../EventPopup";
const icon = (name: string, color: string) => L.divIcon({ className: "", html: `<div class="${name}" style="background:${color}"></div>`, iconSize: [29, 29], iconAnchor: [14.5, 29], popupAnchor: [0, -29] });
const eventIcon = icon("custom-marker", config.marker.eventColor);
const userIcon = icon("user-marker", config.marker.userColor);
function MapPosition({ position }: { position: [number, number] | null }) {
  const map = useMap();
  useEffect(() => { const observer = new ResizeObserver(() => map.invalidateSize()); observer.observe(map.getContainer()); return () => observer.disconnect(); }, [map]);
  return null;
}
function EventMarker({ event, selection }: { event: Event; selection: Event | null }) {
  const marker = useRef<L.Marker>(null);
  const map = useMap();
  useEffect(() => { if (selection?.id === event.id) { map.setView([event.latitude, event.longitude], Math.max(map.getZoom(), config.map.defaultZoom)); marker.current?.openPopup(); } }, [event, selection, map]);
  return <Marker ref={marker} position={[event.latitude, event.longitude]} icon={eventIcon}><Popup><EventPopup event={event} /></Popup></Marker>;
}
export default function EventMap({ events, userPosition, selectedEvent }: { events: Event[]; userPosition: [number, number] | null; selectedEvent: Event | null }) {
  const apiKey = import.meta.env.VITE_CARTO_API;
  return <MapContainer center={config.map.defaultCenter} zoom={config.map.defaultZoom} className="event-map">
    <TileLayer attribution={config.tileLayer.attribution} url={apiKey ? `${config.tileLayer.baseUrl}?key=${apiKey}` : config.tileLayer.baseUrl} subdomains={config.tileLayer.subdomains} />
    <MapPosition position={userPosition} />
    {userPosition && <Marker position={userPosition} icon={userIcon}><Popup><div className="event-popup"><h3>You are here</h3></div></Popup></Marker>}
    {events.map((event) => <EventMarker key={event.id} event={event} selection={selectedEvent} />)}
  </MapContainer>;
}
