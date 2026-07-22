import { useCallback, useState } from 'react';

import { RegisterPage } from './pages/RegisterPage';
import { SearchPage } from './pages/SearchPage';

type View = 'search' | 'register';

export default function App() {
  const [view, setView] = useState<View>('search');
  // Handoff from registration to search: bumping the nonce re-triggers the
  // search even if the same business name is searched twice.
  const [searchTrigger, setSearchTrigger] = useState<{
    query: string;
    nonce: number;
  } | null>(null);
  // Bumped on each successful registration so SearchPage reloads filter
  // dropdown options (new city / industry / etc.) while it stays mounted.
  const [filtersRefreshNonce, setFiltersRefreshNonce] = useState(0);

  const handleRegistered = useCallback(() => {
    setFiltersRefreshNonce((n) => n + 1);
  }, []);

  const handleSearchBusiness = (businessName: string) => {
    setSearchTrigger({ query: businessName, nonce: Date.now() });
    setView('search');
  };

  return (
    <div className="app">
      <header className="app__header">
        <div>
          <h1 className="app__title">Business Search</h1>
          <p className="app__subtitle">
            Natural-language search across the business directory.
          </p>
        </div>
        <nav className="app__nav" aria-label="Primary">
          <button
            type="button"
            className={`app__nav-item${view === 'search' ? ' app__nav-item--active' : ''}`}
            aria-current={view === 'search' ? 'page' : undefined}
            onClick={() => setView('search')}
          >
            Search
          </button>
          <button
            type="button"
            className={`app__nav-item${view === 'register' ? ' app__nav-item--active' : ''}`}
            aria-current={view === 'register' ? 'page' : undefined}
            onClick={() => setView('register')}
          >
            Register
          </button>
        </nav>
      </header>

      {/* Both pages stay mounted; only the active one is shown. This preserves
          each page's state across tab switches and ensures the search handoff
          fires only when a genuinely new trigger arrives (not on a plain tab
          switch back to Search). */}
      <main>
        <div hidden={view !== 'search'}>
          <SearchPage
            trigger={searchTrigger}
            filtersRefreshNonce={filtersRefreshNonce}
          />
        </div>
        <div hidden={view !== 'register'}>
          <RegisterPage
            onSearchBusiness={handleSearchBusiness}
            onRegistered={handleRegistered}
          />
        </div>
      </main>
    </div>
  );
}
