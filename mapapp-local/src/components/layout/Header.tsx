import { useEffect, useState } from "react";
import { UserRound } from "lucide-react";
import { loadLocalProfile, PROFILE_STORAGE_KEY, PROFILE_UPDATED_EVENT } from "../../data/localProfile";

interface HeaderProps {
  query: string;
  onAdvancedSearch: (query: string) => void;
  onProfileClick: () => void;
}
export default function Header({ query, onAdvancedSearch, onProfileClick }: HeaderProps) {
  const [draft, setDraft] = useState(query);
  const [profileName, setProfileName] = useState(() => loadLocalProfile().name);
  useEffect(() => setDraft(query), [query]);
  useEffect(() => {
    const updateProfileName = () => setProfileName(loadLocalProfile().name);
    window.addEventListener(PROFILE_UPDATED_EVENT, updateProfileName);
    window.addEventListener("storage", updateProfileName);
    return () => {
      window.removeEventListener(PROFILE_UPDATED_EVENT, updateProfileName);
      window.removeEventListener("storage", updateProfileName);
    };
  }, []);
  return (
    <header className="app-header">
      <a className="brand" href="/" aria-label="swampsearch home">
        <img className="brand-logo" src="/gator.svg" alt="" width="100" height="100" />
        <span className="brand-wordmark">swamp<span>search</span></span>
      </a>
      <form className="header-search" role="search" onSubmit={(event) => { event.preventDefault(); onAdvancedSearch(draft); }}>
        <label className="sr-only" htmlFor="global-search">Search events</label>
        <input id="global-search" type="search" value={draft} onChange={(event) => setDraft(event.target.value)} />
        <button className="advanced-search-button" type="submit">Advanced Search</button>
      </form>
      <div className="account-controls">
        <div className="header-profile">
          <span className="header-profile-avatar" aria-hidden="true"><UserRound size={22} /></span>
          <span className="header-profile-name" title={profileName}>{profileName || "Your profile"}</span>
          <button className="profile-button" type="button" onClick={onProfileClick}>Profile</button>
        </div>
      </div>
    </header>
  );
}
