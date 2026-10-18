import { createContext, useContext } from "react";

export interface EventTagsState {
  tags: string[];
  loading: boolean;
  error: string | null;
  retry: () => void;
}
export const EventTagsContext = createContext<EventTagsState | null>(null);
export function useEventTags(): EventTagsState {
  const state = useContext(EventTagsContext);
  if (!state) throw new Error("useEventTags must be used inside EventTagsProvider.");
  return state;
}
