# Google Maps setup (place search and the map picker)

Without any keys the app uses the free OpenStreetMap search (Photon) and has no map picker. With the two keys below it uses **Google Places API (New)** for suggestions and a **Google map with a fixed pin** for picking an exact spot, like a delivery app.

## What you get

- **Suggestions** while typing (Places API (New) Autocomplete, India only, biased to the depot). Picking one fetches its exact position (Place Details) in the same session, which is how Google bills a search-and-pick as one session.
- **Pick on map** button in every place field: search, "use my current location", or move the map under the fixed pin; the address of the spot under the pin updates (Geocoding API); Confirm saves the pin's exact latitude and longitude with the trip or request.
- The driver's **Navigate** button goes to that exact saved point.

## One-time setup (about 15 minutes, needs a card for billing)

1. Open the [Google Cloud console](https://console.cloud.google.com), create a project, and **turn on billing** for it.
2. **APIs and services, Library:** enable all three: **Places API (New)**, **Geocoding API**, **Maps JavaScript API**.
3. **Credentials, Create credentials, API key**, twice:
   - **Server key.** Restrict it to the APIs **Places API (New)** and **Geocoding API**. For "application restriction" choose IP addresses and add the public address of the machine that runs the API (leave it unrestricted only while testing on your own PC). This key never leaves the server.
   - **Browser key.** Restrict it to the API **Maps JavaScript API**, and under "application restriction" choose **Websites** (HTTP referrers) and list where the app runs, for example `http://localhost:5173/*`, `http://localhost:4173/*`, `https://*.trycloudflare.com/*` while demoing, and your real site later. Google expects this key to be visible in the browser; the referrer list is what protects it.
4. In `.env` (repo root, never commit it):
   ```
   GOOGLE_MAPS_SERVER_KEY=<the server key>
   GOOGLE_MAPS_BROWSER_KEY=<the browser key>
   PLACES_PROVIDER=auto
   ```
   After saving `.env`, run `docker compose up -d api` (with `pnpm dev:all` instead, saving restarts the API by itself). Check `http://localhost:8000/places/config`: it should say `"provider": "google"` and show the browser key (never the server key).
5. **Set a budget alert and a daily quota cap** in the console (Billing, Budgets; APIs, Quotas) so a mistake or abuse cannot run up a bill. Prices and the free allowance change: read Google's current pricing page before launch.

`PLACES_PROVIDER=photon` switches Google off again without removing the keys.

## If something does not work

| What you see | Likely cause |
|---|---|
| Suggestions say "not available right now. Type the place." | Server key wrong, Places API (New) not enabled, billing off, or the IP restriction does not match this machine. The API log shows only the HTTP code (never the key), for example `google http 403`. |
| "The map could not load..." in the picker | Browser key wrong, **Maps JavaScript API** not enabled, or the site address is not in the key's referrer list (a new tunnel address needs adding). |
| The address under the pin shows coordinates | **Geocoding API** not enabled for the server key (`REQUEST_DENIED`). The pin still confirms with its exact position. |

## Terms to be aware of (decision 81)

- Google's terms do not allow caching its search results, so Google answers are never cached here (the OpenStreetMap fallback is).
- Google's suggestions must be credited ("Powered by Google" is shown under the list), and its place data is meant to be shown on a Google map: the picker uses a Google map for that reason.
- **Open question for the owner:** Google lets you store a place id indefinitely but limits storing other place data, coordinates included, to temporary caching (30 days at the time of writing). CargoOne saves the latitude and longitude of the pin the person confirmed on the map (their own chosen spot) next to each trip. For a small internal tool this is common practice, but if you expand, or want to be strict, confirm with Google's current terms or a lawyer; the alternative is to store the place id and look the position up again.
