import { useEffect, useState } from "react";

export const API_BASE = "/api";

export interface AppConfig {
  demo_mode: boolean;
  max_upload_mb: number;
  max_pdf_pages: number;
  max_questions: number;
  allowed_models: string[] | null; // null until loaded: show every model
}

const DEFAULT_CONFIG: AppConfig = {
  demo_mode: false,
  max_upload_mb: 0,
  max_pdf_pages: 0,
  max_questions: 0,
  allowed_models: null,
};

// Server settings for the UI (demo mode, limits, allowed models). Defaults until loaded or if the call
// fails; the backend enforces the limits either way.
export function useAppConfig(): AppConfig {
  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG);
  useEffect(() => {
    fetch(`${API_BASE}/config`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setConfig({ ...DEFAULT_CONFIG, ...data });
      })
      .catch(() => {});
  }, []);
  return config;
}

export const AI_MODELS = [
  { id: "gpt-4o-mini", name: "GPT-4o Mini", cost: "Low", speed: "Fast" },
  { id: "gpt-5-mini", name: "GPT-5 Mini", cost: "Medium", speed: "Fast" },
  { id: "gpt-6-luna", name: "GPT-6 Luna", cost: "Low", speed: "Medium" },
];

// The dropdown's models: the backend's allowed models (all of them until the config is loaded).
export function visibleModels(config: AppConfig) {
  const allowed = config.allowed_models;
  return allowed ? AI_MODELS.filter((m) => allowed.includes(m.id)) : AI_MODELS;
}

// Keeps the selected model valid: switches to the first visible model when the current one is not offered.
export function useValidModel(
  config: AppConfig,
  selected: string,
  setSelected: (model: string) => void,
) {
  const models = visibleModels(config);
  useEffect(() => {
    if (models.length > 0 && !models.some((m) => m.id === selected)) setSelected(models[0].id);
  }, [models, selected, setSelected]);
  return models;
}

export function demoLimitsHint(config: AppConfig, withPdf = true): string {
  const parts = [`up to ${config.max_questions} questions`, `${config.max_upload_mb} MB`];
  if (withPdf) parts.push(`${config.max_pdf_pages} PDF pages`);
  return `Public demo: ${parts.join(", ")}`;
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
