import { useEffect, useState, type ReactNode } from "react";
import { EventTagsContext } from "../../hooks/useEventTags";
import { loadTags } from "../../lib/tags";
import { apiErrorMessage } from "../../lib/api";

export default function EventTagsProvider({ children }: { children: ReactNode }) {
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<{ tags: string[]; loading: boolean; error: string | null }>({ tags: [], loading: true, error: null });
  useEffect(() => {
    let active = true;
    loadTags().then((tags) => {
      if (active) setState({ tags, loading: false, error: null });
    }).catch((cause: unknown) => {
      if (active) setState({ tags: [], loading: false, error: apiErrorMessage(cause, "Unable to load tags.") });
    });
    return () => { active = false; };
  }, [attempt]);
  const retry = () => {
    setState({ tags: [], loading: true, error: null });
    setAttempt((value) => value + 1);
  };
  return <EventTagsContext.Provider value={{ ...state, retry }}>{children}</EventTagsContext.Provider>;
}
