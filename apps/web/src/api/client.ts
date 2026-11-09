import type {
  AdvisorAnswer,
  AuditEntry,
  CatalogItem,
  CompareResponse,
  Integrations,
  InventorySummary,
  InventoryView,
  Member,
  OrgSettings,
  Overview,
  ProviderInfo,
  QuoteSummary,
  QuoteView,
  Recommendation,
  RecsResponse,
  ResourceDraft,
  ServerDetail,
  ServersResponse,
  ServerView,
  Session,
  SyncRun,
} from "./types";

const TOKEN_KEY = "finops.session";

export function loadSession(): Session | null {
  try {
    const raw = sessionStorage.getItem(TOKEN_KEY);
    return raw ? (JSON.parse(raw) as Session) : null;
  } catch {
    return null;
  }
}

export function saveSession(s: Session | null): void {
  try {
    if (s) sessionStorage.setItem(TOKEN_KEY, JSON.stringify(s));
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable: session lives in memory only */
  }
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : `HTTP ${status}`);
  }
}

export const UNAUTHORIZED_EVENT = "finops:unauthorized";

async function request<T>(method: string, path: string, body?: unknown, raw = false): Promise<T> {
  const headers: Record<string, string> = { Accept: raw ? "*/*" : "application/json" };
  const s = loadSession();
  if (s) headers.Authorization = `Bearer ${s.access_token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(path, { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "network");
  }
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const j = await res.json();
      detail = j?.detail ?? j;
    } catch {
      /* non-JSON error body */
    }
    if (res.status === 401 && !path.includes("/auth/")) {
      saveSession(null);
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
    }
    throw new ApiError(res.status, detail);
  }
  if (raw) return (await res.blob()) as T;
  return (await res.json()) as T;
}

const get = <T>(p: string) => request<T>("GET", p);
const post = <T>(p: string, b: unknown = {}) => request<T>("POST", p, b);
const V = "/api/v1";

export const api = {
  authStatus: () => get<{ registration_open: boolean; setup_needed: boolean; demo_user: boolean; password_reset_email: boolean }>(`${V}/auth/status`),
  forgotPassword: (email: string) => post<{ status: string }>(`${V}/auth/forgot-password`, { email }),
  resetPassword: (token: string, password: string) => post<{ status: string }>(`${V}/auth/reset-password`, { token, password }),
  changePassword: (current_password: string, new_password: string) =>
    post<Session>(`${V}/auth/change-password`, { current_password, new_password }),
  login: (email: string, password: string) => post<Session>(`${V}/auth/login`, { email, password }),
  register: (b: { email: string; password: string; name: string; organization_name: string }) =>
    post<Session>(`${V}/auth/register`, b),

  inventories: () => get<InventorySummary[]>(`${V}/inventories`),
  inventory: (id: string) => get<InventoryView>(`${V}/inventories/${id}`),
  createInventory: (name: string, resources: Partial<ResourceDraft>[]) =>
    post<InventoryView>(`${V}/inventories`, { name, resources }),
  createDemo: () => post<InventoryView>(`${V}/inventories/demo`),
  fromChat: (text: string, name: string) => post<InventoryView>(`${V}/inventories/from-chat`, { text, name }),
  fromInvoice: (file: File, name: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("name", name);
    return post<InventoryView>(`${V}/inventories/from-invoice`, fd);
  },
  setCurrency: (id: string, currency: "TOMAN" | "RIAL") =>
    post<InventoryView>(`${V}/inventories/${id}/currency`, { currency }),
  patchResource: (id: string, rid: string, body: { fields?: Record<string, unknown>; user_confirmed?: boolean }) =>
    request<InventoryView>("PATCH", `${V}/inventories/${id}/resources/${rid}`, body),
  addResource: (id: string, draft: Partial<ResourceDraft>) =>
    post<InventoryView>(`${V}/inventories/${id}/resources`, draft),
  deleteResource: (id: string, rid: string) =>
    request<InventoryView>("DELETE", `${V}/inventories/${id}/resources/${rid}`),
  confirm: (id: string, confirm_all_rows = false) =>
    post<InventoryView>(`${V}/inventories/${id}/confirm`, { confirm_all_rows }),
  archive: (id: string) => post<{ id: string; status: string }>(`${V}/inventories/${id}/archive`),

  overview: (id: string) => get<Overview>(`${V}/inventories/${id}/overview`),
  quote: (id: string, include_tax: boolean) => post<QuoteView>(`${V}/inventories/${id}/quote`, { include_tax }),
  quotes: (id: string) => get<QuoteSummary[]>(`${V}/inventories/${id}/quotes`),
  getQuote: (qid: string) => get<QuoteView>(`${V}/quotes/${qid}`),
  compare: (id: string, allow_outside_iran: boolean, resource_ids?: string[]) =>
    post<CompareResponse>(`${V}/inventories/${id}/compare`, { allow_outside_iran, resource_ids: resource_ids ?? null }),
  runRecs: (id: string) => post<RecsResponse>(`${V}/inventories/${id}/recommendations`),
  recs: (id: string) => get<RecsResponse>(`${V}/inventories/${id}/recommendations`),
  rec: (rid: string) => get<Recommendation>(`${V}/recommendations/${rid}`),
  report: (id: string, lang: "fa" | "en") => request<Blob>("GET", `${V}/inventories/${id}/report?lang=${lang}`, undefined, true),

  advisor: (inventory_id: string, question: string, lang: "fa" | "en") =>
    post<AdvisorAnswer>(`${V}/advisor/chat`, { inventory_id, question, lang }),

  providers: () => get<ProviderInfo[]>(`${V}/providers`),
  catalog: (f: { provider_id?: string; service_type?: string; q?: string }) => {
    const qs = new URLSearchParams();
    Object.entries(f).forEach(([k, v]) => v && qs.set(k, v));
    const s = qs.toString();
    return get<CatalogItem[]>(`${V}/catalog${s ? `?${s}` : ""}`);
  },
  catalogHistory: (itemId: string) => get<CatalogItem[]>(`${V}/catalog/${itemId}/history`),

  servers: () => get<ServersResponse>(`${V}/servers`),
  server: (id: string) => get<ServerDetail>(`${V}/servers/${id}`),
  enrollCommand: () => get<{ command: string; removal_command: string }>(`${V}/servers/enroll-command`),
  addServer: (b: { name: string; host: string; port: number }) => post<ServerView>(`${V}/servers`, b),
  patchServer: (id: string, b: Record<string, unknown>) => request<ServerView>("PATCH", `${V}/servers/${id}`, b),
  checkServer: (id: string) => post<ServerView>(`${V}/servers/${id}/check`),
  trustServer: (id: string) => post<ServerView>(`${V}/servers/${id}/trust-new-identity`),
  deleteServer: (id: string) => request<{ removal_command: string }>("DELETE", `${V}/servers/${id}`),
  serversToInventory: () => post<{ id: string }>(`${V}/servers/inventory`),

  integrations: () => get<Integrations>(`${V}/integrations`),
  syncRuns: () => get<SyncRun[]>(`${V}/admin/sync-runs`),
  syncProvider: (pid: string) => post<SyncRun | { queued: boolean; task_id: string }>(`${V}/admin/providers/${pid}/sync`),
  approveRun: (runId: string) => post<SyncRun>(`${V}/admin/sync-runs/${runId}/approve`),

  members: () => get<Member[]>(`${V}/members`),
  addMember: (b: { email: string; password: string; name: string; role: string }) => post<Member>(`${V}/members`, b),
  setMemberRole: (id: string, role: string) => request<Member>("PATCH", `${V}/members/${id}`, { role }),
  removeMember: (id: string) => request<{ status: string }>("DELETE", `${V}/members/${id}`),
  setMemberPassword: (id: string, password: string) => post<{ status: string }>(`${V}/members/${id}/password`, { password }),

  settings: () => get<OrgSettings>(`${V}/settings`),
  putSettings: (b: { engineer_day_rate_toman?: string | null; default_language?: string | null }) =>
    request<{ settings: OrgSettings["settings"] }>("PUT", `${V}/settings`, b),
  auditLogs: (limit = 100) => get<AuditEntry[]>(`${V}/audit-logs?limit=${limit}`),
};
