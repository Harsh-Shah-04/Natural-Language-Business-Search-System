# Business Search — Frontend (M5.1 + M5.2)

A clean React + TypeScript interface for the Natural Language Business Search
backend. It consumes the existing FastAPI endpoints — no backend logic lives
here. Two views, toggled by the header nav (no router — a dependency-free view
switch): **Search** and **Register**.

## What it does

- **Search**: natural-language query box; Enter or the button runs the search.
- **Filters**: five dropdowns (Industry, City, State, Nature, Sub Category)
  populated from `GET /api/filters/values`. Changing a filter re-runs the
  current query narrowed by it.
- **Results**: responsive cards showing business name, industry, sub category,
  location, description, products/services, relevance score, and how the result
  matched (Semantic / Keyword / Both).
- **Register (M5.2)**: a validated form (`POST /api/businesses`) to add a new
  business. Required fields plus optional contact details; client-side checks
  for required fields, email, and website URL mirror the backend. On success it
  clears the form and offers a one-click "Search this business" that jumps to
  the Search view and runs the query — the new business is searchable
  immediately.
- **States**: loading spinner, empty ("no results"), error messages, and
  per-field + submit-level validation errors on the form.

## Stack

React 19, TypeScript, Vite. No UI kit, no state library, no HTTP client —
`fetch` and plain CSS keep the dependency surface minimal.

## Structure

```
src/
  api/         HTTP client + typed endpoint functions (search, businesses)
  types/       API contract types, mirroring backend/app/schemas.py
  hooks/       useSearch, useFilterOptions, useRegistrationForm
  components/  SearchBar, FilterPanel, FilterSelect, ResultsList,
               ResultCard, StatusMessage, FormField
  pages/       SearchPage, RegisterPage
  App.tsx      shell: header nav + view switch + search handoff
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
