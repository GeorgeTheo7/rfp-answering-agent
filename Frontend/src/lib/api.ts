import { useEffect, useState } from "react";

export const API_BASE = "/api";

export interface AppConfig {
  demo_mode: boolean;
}

const DEFAULT_CONFIG: AppConfig = { demo_mode: false };

// Server settings for the UI (e.g. demo mode). Defaults until loaded or if the call fails;
// the backend enforces the limits either way.
export function useAppConfig(): AppConfig {
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  useEffect(() => {
    fetch(`${API_BASE}/config`)
      .then((res) => (res.ok ? res.json() : DEFAULT_CONFIG))
      .then((data) => setConfig({ demo_mode: Boolean(data?.demo_mode) }))
      .catch(() => {});
  }, []);
  return config;
}

// The backend's `detail` message, or a fallback with the status when the body is not JSON
// (e.g. an nginx or ingress error page).
export async function errorMessage(
  res: Response,
  fallback = "The server returned an error.",
): Promise<string> {
  try {
    const data = await res.json();
    if (typeof data?.detail === "string" && data.detail) return data.detail;
  } catch {
    // not JSON
  }
  return `${fallback} (${res.status}${res.statusText ? ` ${res.statusText}` : ""})`;
}
