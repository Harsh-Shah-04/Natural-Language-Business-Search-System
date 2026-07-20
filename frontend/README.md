# Business Search — Frontend (M5.1)

A clean React + TypeScript interface for the Natural Language Business Search
backend. It consumes the existing FastAPI endpoints — no backend logic lives
here.

## What it does

- **Search**: natural-language query box; Enter or the button runs the search.
- **Filters**: five dropdowns (Industry, City, State, Nature, Sub Category)
  populated from `GET /api/filters/values`. Changing a filter re-runs the
  current query narrowed by it.
- **Results**: responsive cards showing business name, industry, sub category,
  location, description, products/services, relevance score, and how the result
  matched (Semantic / Keyword / Both).
- **States**: loading spinner, empty ("no results"), and error messages.

## Stack

React 19, TypeScript, Vite. No UI kit, no state library, no HTTP client —
`fetch` and plain CSS keep the dependency surface minimal.

## Structure

```
src/
  api/         HTTP client + typed endpoint functions (service layer)
  types/       API contract types, mirroring backend/app/schemas.py
  hooks/       useSearch (request lifecycle), useFilterOptions (dropdown data)
  components/  SearchBar, FilterPanel, FilterSelect, ResultsList,
               ResultCard, StatusMessage
  App.tsx      composition + state wiring
```

## Running

The backend must be running first (see `../backend/README.md`) with CORS
allowing this origin — the default backend config already allows the Vite dev
server on `http://localhost:5173`.

```bash
npm install
npm run dev        # http://localhost:5173
```

Point at a non-default backend by copying `.env.example` to `.env.local` and
setting `VITE_API_BASE_URL`.

```bash
npm run build      # type-check (tsc -b) + production build to dist/
npm run preview    # serve the production build locally
```
