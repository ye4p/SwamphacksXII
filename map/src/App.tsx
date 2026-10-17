import { useEffect, useState } from "react";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./index.css";
import hardcodedEvents from "./data/events";
import type { Event } from "./types";
import { config } from "./config";
import EventPopup from "./components/EventPopup";
import { useEvents } from "./hooks/useEvents";
import { useEventDistances } from "./hooks/useEventDistances";

const makeMarkerIcon = (html: string, size: number = config.marker.size) =>
  L.divIcon({
    className: "",
    html,
    iconSize: [size, size],
    iconAnchor: [size / 2, size],
    popupAnchor: [0, -size],
  });

const eventMarkerIcon = makeMarkerIcon(
  `<div class="custom-marker" style="background:${config.marker.eventColor}"></div>`,
  config.marker.size
);

const userMarkerIcon = makeMarkerIcon(
  `<div class="user-marker" style="background:${config.marker.userColor}"></div>`,
  config.marker.size
);

export default function App() {
  const apiKey = import.meta.env.VITE_CARTO_API;
  const tileUrl = apiKey
    ? `${config.tileLayer.baseUrl}?key=${apiKey}`
    : config.tileLayer.baseUrl;

  const [center, setCenter] = useState<[number, number]>(
    config.map.defaultCenter
  );
  const [userPosition, setUserPosition] = useState<[number, number] | null>(null);

  const { events: storedEvents, setEvents } = useEvents();
  const { distances: distances } = useEventDistances(storedEvents, userPosition);

  useEffect(() => {
    distances.forEach((d) => {
      console.log("event id: ", d.eventId, " distance: ", d.distance);
    })
  }, [distances]);

  useEffect(() => {
    if (!navigator.geolocation) return;
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude;
        const lng = pos.coords.longitude;
        setUserPosition([lat, lng]);
        setCenter([lat, lng]);
      },
      () => {}
    );
  }, []);

  useEffect(() => {
    setEvents(hardcodedEvents);
  }, [setEvents]);

  return (
    <MapContainer
      center={center}
      zoom={config.map.defaultZoom}
      style={{ height: "100vh", width: "100%" }}
    >
      <TileLayer
        attribution={config.tileLayer.attribution}
        url={tileUrl}
        subdomains={config.tileLayer.subdomains}
      />
      {userPosition && (
        <Marker position={userPosition} icon={userMarkerIcon}>
          <Popup>
            <div className="event-popup">
              <h3>You are here</h3>
            </div>
          </Popup>
        </Marker>
      )}
      {storedEvents.map((e: Event) => (
        <Marker key={e.id} position={[e.lat, e.lng]} icon={eventMarkerIcon}>
          <Popup>
            <EventPopup event={e} />
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
