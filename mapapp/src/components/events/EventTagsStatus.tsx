import { useEventTags } from "../../hooks/useEventTags";

export default function EventTagsStatus() {
  const { tags, loading, error, retry } = useEventTags();
  if (loading) return <p role="status">Loading tags…</p>;
  if (error) return <p role="alert">{error} <button type="button" className="text-button" onClick={retry}>Retry</button></p>;
  if (!tags.length) return <p>No tags available.</p>;
  return null;
}
