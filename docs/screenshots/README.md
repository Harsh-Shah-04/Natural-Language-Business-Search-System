# Screenshots

Placeholder directory. The images referenced from the root `README.md` live
here; none have been captured yet.

## Required set

| Filename | What it should show |
|---|---|
| `search-page.png` | Search page in its idle state, before any query. |
| `search-results.png` | Results for a real query, with keyword highlighting visible in the cards. |
| `filters.png` | Results narrowed by at least one filter, with the Clear filters button visible. |
| `registration.png` | Registration form showing the three grouped sections and required-field markers. |
| `responsive-mobile.png` | Mobile layout (~390px): single-column cards, full-width nav. |

## How to capture

1. Start the backend and frontend:
   ```bash
   cd backend  && uv run uvicorn app.main:app --reload
   cd frontend && npm run dev
   ```
   Open <http://localhost:5173>.
2. **search-page** — capture before searching.
3. **search-results** — search `eco friendly packaging for restaurants`. The
   matched terms render highlighted inside the result cards.
4. **filters** — with results on screen, set *State* to a real value (for example
   `Maharashtra`) and capture the narrowed set.
5. **registration** — switch to the Register tab and capture the grouped form.
6. **responsive-mobile** — DevTools device toolbar at ~390px width.

Save each as PNG with the exact filename above. The links in the root README
resolve once the files exist.
