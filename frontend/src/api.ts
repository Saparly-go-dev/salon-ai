const TOKEN_KEY = "salon.token";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    // Без хранилища сессия закончится при перезагрузке страницы
  }
}

export class ApiError extends Error {
  constructor(public code: string, public status: number) {
    super(code);
  }
}

type Options = { method?: string; body?: unknown; form?: FormData };

export async function api<T>(path: string, options: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(path, {
      method: options.method ?? (options.body !== undefined || options.form ? "POST" : "GET"),
      headers,
      body: options.form ?? (options.body !== undefined ? JSON.stringify(options.body) : undefined),
    });
  } catch {
    throw new ApiError("network", 0);
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    const detail = data?.detail;
    const code = typeof detail?.code === "string" ? detail.code : response.status === 422 ? "validation" : "generic";
    throw new ApiError(code, response.status);
  }
  return response.json();
}

export function errorCode(error: unknown): string {
  return error instanceof ApiError ? error.code : "generic";
}

export type Localized = Record<string, string>;
export type Role = "client" | "master" | "admin";
export type User = { id: number; email: string; full_name: string; phone: string | null; role: Role };
export type Meta = { timezone: string; currency: string; ai_enabled: boolean };
export type Service = { id: number; category: string; name: Localized; description: Localized; duration_minutes: number; price: number; is_active: boolean };
export type Hours = { weekday: number; start_time: string; end_time: string };
export type Master = { id: number; full_name: string; title: Localized; is_active: boolean; service_ids: number[]; hours: Hours[] };
export type Slot = { master_id: number; master_name: string; starts_at: string };
export type Status = "booked" | "completed" | "cancelled" | "no_show";
export type Appointment = {
  id: number; client_id: number; client_name: string; client_phone: string | null;
  master_id: number; master_name: string; service_id: number; service_name: Localized;
  starts_at: string; ends_at: string; price: number; status: Status; source: "web" | "chat" | "admin"; notes: string | null;
};
export type Client = { id: number; full_name: string; email: string; phone: string | null; visits: number; total_spent: number; last_visit: string | null };
export type ChatTurn = { role: "user" | "assistant"; text: string };
export type ChatResponse = { conversation_id: number | null; messages: ChatTurn[]; booked: boolean };
export type NailResult = {
  is_nail_photo: boolean; photo_kind: "own_nails" | "design_reference" | "other"; summary: string; shape: string; length: string;
  colors: string[]; finish: string; design_details: string[]; care_observations: string[]; see_doctor_note: string | null;
  recommendations: { service_id: number; name: Localized; price: number; duration_minutes: number; reason: string }[];
};
export type Kpis = { revenue: number; completed: number; avg_ticket: number; cancel_rate: number; no_show_rate: number; new_clients: number };
export type Overview = {
  days: number; kpis: Kpis; previous_kpis: Kpis;
  daily: { date: string; appointments: number; revenue: number }[];
  top_services: { id: number; name: Localized; count: number; revenue: number }[];
  masters: { id: number; name: string; appointments: number; revenue: number; utilization: number }[];
  heatmap: { weekday: number; hour: number; count: number }[];
};
export type ForecastPoint = { date: string; appointments: number; low: number; high: number; revenue: number; booked: number; load: number; level: "high" | "normal" | "low" };
export type Forecast =
  | { available: false; min_history_days: number }
  | {
      available: true;
      history: { date: string; appointments: number }[];
      forecast: ForecastPoint[];
      metrics: { holdout_days: number; model: { mae: number; rmse: number; wmape: number }; baseline: { mae: number; rmse: number; wmape: number } };
    };
