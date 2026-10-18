import { useEffect, useState } from "react";
import { getOrganizations, type Organization } from "../lib/organizations";
import { apiErrorMessage } from "../lib/api";
export function useOrganizations() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getOrganizations(controller.signal).then((items) => {
      if (!controller.signal.aborted) setOrganizations(items);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) setError(apiErrorMessage(cause, "Unable to load organizations."));
    }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, []);
  return { organizations, loading, error };
}
