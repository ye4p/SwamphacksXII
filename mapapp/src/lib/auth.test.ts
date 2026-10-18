import { afterEach, describe, expect, it, vi } from "vitest";
import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";
import { api, apiErrorMessage, apiUrl, API_BASE } from "./api";
import { endSession, getCurrentUser } from "./auth";

function httpError(status: number, detail: unknown = "Request failed") {
  return new AxiosError("Request failed", undefined, undefined, undefined, {
    status, data: { detail }, statusText: "Error", headers: {}, config: { headers: new AxiosHeaders() },
  } as AxiosResponse);
}

afterEach(() => vi.restoreAllMocks());

describe("backend session contract", () => {
  it("uses credentialed requests and the backend user shape", async () => {
    const user = { id: 42, email: "user@example.com", auth0_id: "auth0|42", system_role: "user" };
    const get = vi.spyOn(api, "get").mockResolvedValue({ data: user });
    expect(await getCurrentUser()).toEqual(user);
    expect(get).toHaveBeenCalledWith("/auth/me");
    expect(api.defaults.withCredentials).toBe(true);
  });

  it("treats an expired or absent session as anonymous", async () => {
    vi.spyOn(api, "get").mockRejectedValue(httpError(401));
    expect(await getCurrentUser()).toBeNull();
  });

  it.each([403, 500])("does not hide HTTP %s failures as anonymous sessions", async (status) => {
    vi.spyOn(api, "get").mockRejectedValue(httpError(status));
    await expect(getCurrentUser()).rejects.toBeInstanceOf(AxiosError);
  });

  it("rejects a misrouted HTML response instead of displaying a signed-in account", async () => {
    vi.spyOn(api, "get").mockResolvedValue({ data: "<!doctype html>" });
    await expect(getCurrentUser()).rejects.toThrow("invalid account response");
  });

  it("clears the session via POST and propagates logout failures", async () => {
    const post = vi.spyOn(api, "post").mockResolvedValue({ data: { message: "Logged out" } });
    await endSession();
    expect(post).toHaveBeenCalledWith("/auth/logout");
    post.mockRejectedValue(httpError(500));
    await expect(endSession()).rejects.toBeInstanceOf(AxiosError);
  });

  it("builds navigation URLs from the same base as API requests", () => {
    expect(apiUrl("/auth/auth0/login")).toBe(`${API_BASE}/auth/auth0/login`);
    expect(apiUrl("auth/auth0/logout")).toBe(`${API_BASE}/auth/auth0/logout`);
  });

  it("only presents string backend errors", () => {
    expect(apiErrorMessage(httpError(500, "Unavailable"), "Retry")).toBe("Unavailable");
    expect(apiErrorMessage(httpError(422, [{ msg: "invalid" }]), "Retry")).toBe("Retry");
    expect(apiErrorMessage(new Error("network"), "Retry")).toBe("Retry");
  });
});
