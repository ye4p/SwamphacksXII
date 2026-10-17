import { useEffect, useState } from "react";
import AccountControls from "../auth/AccountControls";

interface HeaderProps {
  query: string;
  onSearch: (query: string) => void;
}
export default function Header({ query, onSearch }: HeaderProps) {
  const [draft, setDraft] = useState(query);
  useEffect(() => setDraft(query), [query]);
  return (
    <header className="app-header">
      <a className="brand" href="/" aria-label="swampsearch home">
        <img className="brand-logo" src="/Alligator_peering_through_a_lens.svg" alt="" width="100" height="100" />
        <span><span className="brand-wordmark">swamp<span>search</span></span><small>Discover what's happening</small></span>
      </a>
      <form className="header-search" role="search" onSubmit={(event) => { event.preventDefault(); onSearch(draft); }}>
        <label className="sr-only" htmlFor="global-search">Search events</label>
        <input id="global-search" type="search" placeholder="Find your next event…" value={draft} onChange={(event) => setDraft(event.target.value)} />
        <button className="primary-button" type="submit">Search</button>
      </form>
      <AccountControls />
    </header>
  );
}
