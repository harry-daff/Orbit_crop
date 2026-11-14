# Orbit_crop

Orbit_crop is a responsive crop planning dashboard with keyless Leaflet/OpenStreetMap field mapping, NASA POWER weather and solar history, SMAP moisture indicators, optional SoilGrids texture estimates, crop feasibility guidance, and an editable rotation planner.

## Project structure

```text
Orbit_crop/
├── backend/
│   ├── main.py                  # FastAPI endpoints and GeoJSON validation
│   ├── nasa_service.py          # NASA POWER weather, wetness, and SMAP data
│   ├── soil_profile_service.py  # optional ISRIC SoilGrids point adapter
│   ├── country_profiles.py      # transparent staple-priority hints
│   └── rotation_engine.py       # crop catalog, scores, custom profiles, rotation rules
├── frontend/
│   ├── .env.example             # API URL configuration
│   └── src/
│       ├── App.jsx              # dashboard, navigation, planners, API integration
│       └── components/
│           ├── FarmMap.jsx      # Leaflet/OSM boundary drawing and NASA GIBS overlay
│           └── CropDetail.jsx   # feasibility requirements and action plan dialog
├── requirements.txt
└── requirements-dev.txt
```

## Local setup

Requires Python 3.10+ and Node.js 18+.

The map uses public OpenStreetMap raster tiles and NASA GIBS imagery; no map API key is needed. The public OSM tile service is community-operated and has a usage policy, so high-traffic production deployments should select a tile provider or self-hosted tile cache that matches expected usage. Copy `frontend/.env.example` to `frontend/.env.local` only if you need to change `VITE_API_URL`.

### Start the backend

From the project root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000
```

API docs: `http://127.0.0.1:8000/docs`.

### Start the frontend

In another terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

### Tests and production build

```powershell
pip install -r requirements-dev.txt
python -m pytest
cd frontend
npm run build
```

## Data notes and limitations

- NASA POWER daily time series are requested at the entered coordinate. For a drawn polygon, the app samples up to eight points on its perimeter and averages coincident daily records. NASA data are gridded, so small parcels can share a source grid cell and the result is not a field sensor reading. Requests explicitly use UTC for date alignment.
- POWER weather, radiation, and GEOS wetness are requested with best-effort fallbacks. SMAP `RZMC` and `SFMC`, when available through POWER, are volumetric root-zone (0–100 cm) and surface (0–5 cm) moisture. `GWETROOT` and `GWETTOP` are model wetness fractions. `ALLSKY_SFC_SW_DWN` is normalized to kWh/m²/day.
- NASA POWER and SMAP do not return sand/silt/clay fractions. The optional SoilGrids point adapter queries a modeled topsoil estimate; ISRIC documents possible REST API outages, so errors produce an explicit unavailable result. A raster prediction is not a substitute for a field soil test.
- Field overview can display NASA GIBS MODIS Terra NDVI imagery. It is a visual raster only; this app does not claim a numeric field-average NDVI because that requires pixel decoding, cloud masking, and polygon aggregation. Tile load failures are surfaced in the map. Public tile providers may rate-limit requests.
- Country adaptation currently adds a staple-priority ranking signal for India, Kenya, Philippines, Brazil, and the United States. It is not a complete national, state, or county fertilizer-law database and must not be treated as a regulatory compliance determination.
- Crop match scores are broad screening rules. Custom crop profiles do not invent crop-specific requirements. Yield ranges, prices, pH correction, fertilizer rates, and pest actions depend on crop variety and local conditions; confirm with soil tests, extension services, and buyers.

## API overview

- `GET /api/health` — service status.
- `GET /api/crops` — crop profiles and action steps.
- `GET /api/countries` — country staple-priority profiles.
- `POST /api/plan` — point or GeoJSON field analysis, climate history, and crop matches.
- `POST /api/soil` — NASA POWER surface/root-zone wetness history.
- `POST /api/soil/profile` — best-effort SoilGrids texture lookup.
- `POST /api/crops/custom` — user-defined crop guide scaffold.
- `POST /api/rotation/validate` — botanical-family and nitrogen rotation warnings.

Set `CORS_ORIGINS` to a comma-separated list when serving the frontend from a non-default origin.
