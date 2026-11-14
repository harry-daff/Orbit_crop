# Orbit_crop

Orbit_crop is a farmer-facing crop planning dashboard. Its FastAPI service fetches daily NASA POWER Agroclimatology data for a selected point and aggregates a calendar-month climatology. A transparent rule-based engine ranks three crops and lays out a three-season rotation. The React dashboard includes a clickable map, historical climate chart, field inputs, crop matches, and rotation timeline.

## Project structure

```text
Orbit_crop/
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── nasa_service.py
│   ├── rotation_engine.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── postcss.config.js
│   ├── tailwind.config.js
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx
│       ├── index.css
│       └── main.jsx
├── requirements.txt
└── README.md
```

## Run locally

Use Python 3.10+ and Node.js 18+.

1. From the project root, create and activate a virtual environment, then install the Python dependencies:

   ```bash
   python -m venv .venv
   # macOS/Linux: source .venv/bin/activate
   # Windows PowerShell: .venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

2. Start the API from the project root:

   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

3. In another terminal, start the dashboard:

   ```bash
   cd frontend
   npm install
   npm run dev
   ```

Open the Vite URL (usually `http://localhost:5173`). Click on the map or enter coordinates, select soil and the previous crop, set the history length (1–5 years), then choose **Analyze field**. API docs are available at `http://localhost:8000/docs`.

NASA data is retrieved from the public [NASA POWER daily point API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/). Precipitation is treated as a daily rate and monthly values are climatological average daily rates. NASA POWER grid values are regional estimates; use local observations and agronomist guidance before committing inputs. The deeper-soil endpoint is intentionally a placeholder for a future SMAP or OpenLandMap adapter and does not return invented metrics.
