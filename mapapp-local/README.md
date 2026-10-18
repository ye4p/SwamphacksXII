# Swamp Search — local copy

This folder is a standalone local copy of the Mapapp map UI. It uses bundled
sample events and does not start the DeepSpace CLI, contact DeepSpace, or
require a DeepSpace account.

## Run locally

From this folder, install dependencies once and start Vite:

```powershell
npm install
npm run dev
```

Open the localhost URL printed by Vite. Stop the server with `Ctrl+C`.

The map's base tiles are served by CARTO, so displaying the map background
still requires an internet connection. The event pins and search/filter
behavior use the sample data in `src/data/events.ts`.

Submitting a search opens the results page. Use the Events and Organizations
tabs to switch between event results and advanced organization search. Local
organization profiles and their upcoming events are in
`src/data/organizations.ts`.
