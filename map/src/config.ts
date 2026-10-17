export const config = {
  marker: {
    size: 29,
    eventColor: "#ef4444",
    userColor: "#3b82f6",
  },
  map: {
    defaultCenter: [29.6436, -82.3549] as [number, number],
    defaultZoom: 15,
  },
  tileLayer: {
    baseUrl:
      "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
    attribution:
      "&copy; OpenStreetMap contributors &copy; CARTO",
    subdomains: "abcd",
  },
} as const;
