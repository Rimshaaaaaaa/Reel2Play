/** Typed calls to the Reel2Play API. The base URL comes from VITE_API_BASE_URL. */

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8000";

export type VideoStatus = "uploaded" | "ready" | "failed";

export interface VideoOut {
  id: string;
  shop_id: string;
  kind: "video" | "photos";
  status: VideoStatus;
  error: string | null;
  duration_s: number | null;
  rights_confirmed: boolean;
  audio_removed: boolean;
  is_synthetic: boolean;
  ad_id: string | null;
  shop_key?: string | null;
}

export type AdStatus =
  | "queued"
  | "analyzing"
  | "cutting_out"
  | "building"
  | "testing"
  | "fixing"
  | "publishing"
  | "published"
  | "needs_person"
  | "blocked"
  | "failed"
  | "ready"
  | "replaced";

export interface ProgressLine {
  at: string;
  actor: string;
  action: string;
  message: string;
}

export interface GateOut {
  gate: string;
  label: string;
  passed: boolean;
  message: string;
  screenshot_url: string | null;
}

export interface ReportOut {
  passed: boolean;
  language: "ur" | "en";
  rounds: number;
  summary: string;
  next_step: string;
  gates: GateOut[];
  screenshots: Record<string, string>;
  /** Feature 31: claims the shop cannot prove, or a missing price. */
  warnings?: string[];
}

export interface Captions {
  instagram: string;
  facebook: string;
  whatsapp_status: string;
  hashtags: string[];
  language: "ur" | "en";
  written_by: "model" | "code";
}

export interface ShareOut {
  link: string;
  preview_url: string | null;
  reel_url: string | null;
  reel_seconds: number | null;
  lead_in_url: string | null;
  meta_html_url: string | null;
  meta_zip_url: string | null;
  captions: Captions | null;
  published_at: string | null;
  /** Feature 18: the same game as a square or landscape page, and Reels in those shapes. */
  square_link?: string | null;
  landscape_link?: string | null;
  square_reel_url?: string | null;
  wide_reel_url?: string | null;
  /** Feature 36: the A4 counter poster with the game's QR code, and a picture of it. */
  poster_url?: string | null;
  poster_preview_url?: string | null;
  /** Feature 37: snippets for the shop's own website. */
  embeds?: Embed[];
}

export interface Embed {
  shape: "tall" | "wide";
  src: string;
  code: string;
}

export interface AdOut {
  id: string;
  video_id: string;
  status: AdStatus;
  step: string | null;
  error: string | null;
  is_synthetic: boolean;
  brief: {
    product: string;
    category: string;
    palette: string[];
    language: "ur" | "en";
    price: string | null;
    offer_text: string | null;
    offer_source: string;
    /** Feature 10/22: the occasion the game is themed for, or "none". */
    occasion?: string;
    /** Feature 11: the shop's other products in the game. */
    more_products?: string[];
  } | null;
  sprites: {
    url: string;
    method: string;
    quality: string;
    product_index: number;
    strip_url: string | null;
    strip_frames: number;
  }[];
  template: string | null;
  build_url: string | null;
  report: ReportOut | null;
  share: ShareOut | null;
  progress: ProgressLine[];
  shop_id?: string | null;
  variant?: string;
  /** Feature 44: this is an easier version of another game, and where it stands. */
  easier_for?: string | null;
  suggestion?: string | null;
}

const FINISHED: AdStatus[] = ["published", "needs_person", "blocked", "failed", "ready", "replaced"];

/** True once the pipeline has nothing more to do for this ad. */
// --- A/B tests (feature 19) -----------------------------------------------------------------

export interface VersionOut {
  id: string;
  variant: string;
  status: AdStatus;
  template: string | null;
  link: string | null;
  stats: Partial<GameStats>;
}

export interface AbTestOut {
  link: string | null;
  versions: VersionOut[];
  leader: string | null;
  verdict: string;
}

export function getAbTest(adId: string): Promise<AbTestOut> {
  return request<AbTestOut>(`/api/ads/${encodeURIComponent(adId)}/variants`);
}

export function makeVersions(adId: string, shopKey: string): Promise<AbTestOut> {
  return request<AbTestOut>(`/api/ads/${encodeURIComponent(adId)}/variants`, {
    method: "POST",
    headers: { "X-Shop-Key": shopKey },
  });
}

export function isSettled(ad: AdOut): boolean {
  return (
    FINISHED.includes(ad.status) || ad.progress.at(-1)?.action === "pipeline.stopped"
  );
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(0, "Could not reach Reel2Play. Check your connection and try again.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body ? String(body.detail) : null;
    throw new ApiError(response.status, detail ?? `Request failed (${response.status}).`);
  }
  return body as T;
}

/** What the owner tells us about the offer, for an upload or an import. */
export interface BriefValues {
  shopName: string;
  whatsappNumber: string;
  shopUrl: string;
  price: string;
  offer: string;
  language: "auto" | "ur" | "en";
  rightsConfirmed: boolean;
  /** Feature 22: a seasonal theme, or "none". */
  occasion?: string;
}

export interface UploadFields extends BriefValues {
  files: File[];
  /** Feature 10: the owner saying the offer, the occasion and who it is for. */
  voiceNote: File | null;
  /** Feature 11: the photos show different products, not one product from several sides. */
  catalog?: boolean;
  /** Feature 24: an experimental game with a mechanic the director invents. */
  lab?: boolean;
}

// --- the shop's studio key, kept in this browser only ------------------------------------

export interface StoredShop {
  id: string;
  key: string;
  name: string;
}

const SHOP_STORAGE = "r2p.shop";

/** The shop this browser made, if any. Storage can be missing or blocked; that is fine. */
export function storedShop(): StoredShop | null {
  try {
    const raw = window.localStorage.getItem(SHOP_STORAGE);
    return raw ? (JSON.parse(raw) as StoredShop) : null;
  } catch {
    return null;
  }
}

export function rememberShop(shop: StoredShop | null): void {
  try {
    if (shop) window.localStorage.setItem(SHOP_STORAGE, JSON.stringify(shop));
    else window.localStorage.removeItem(SHOP_STORAGE);
  } catch {
    // Private windows may refuse storage; the studio then needs the next upload's key.
  }
}

/** Send into the shop this browser made; if that shop is gone, start a new one and keep its key. */
async function asStoredShop<T extends { shop_id: string; shop_key?: string | null }>(
  shopName: string,
  send: (shop: StoredShop | null) => Promise<T>,
): Promise<T> {
  let video: T;
  try {
    video = await send(storedShop());
  } catch (error) {
    if (!(error instanceof ApiError && error.status === 403)) throw error;
    rememberShop(null); // the stored shop is gone or its key changed
    video = await send(null);
  }
  if (video.shop_key) rememberShop({ id: video.shop_id, key: video.shop_key, name: shopName });
  return video;
}

export function uploadVideo(fields: UploadFields): Promise<VideoOut> {
  const brand = agencyBrand();
  if (brand) return sendUpload(fields, null, brand); // feature 47: for an agency's brand
  return asStoredShop(fields.shopName, (shop) => sendUpload(fields, shop));
}

function sendUpload(
  fields: UploadFields,
  shop: StoredShop | null,
  brand: AgencyBrand | null = null,
): Promise<VideoOut> {
  const form = new FormData();
  if (shop) form.set("shop_id", shop.id);
  if (brand) form.set("shop_id", brand.shopId);
  form.set("shop_name", fields.shopName);
  form.set("language", fields.language);
  form.set("rights_confirmed", String(fields.rightsConfirmed));
  if (fields.whatsappNumber) form.set("whatsapp_number", fields.whatsappNumber);
  if (fields.shopUrl) form.set("shop_url", fields.shopUrl);
  if (fields.price) form.set("price", fields.price);
  if (fields.offer) form.set("offer", fields.offer);
  for (const file of fields.files) form.append("files", file);
  if (fields.voiceNote) form.set("voice_note", fields.voiceNote);
  if (fields.catalog) form.set("catalog", "true");
  if (fields.lab) form.set("lab", "true");
  if (fields.occasion && fields.occasion !== "none") form.set("occasion", fields.occasion);
  const headers: Record<string, string> = brand
    ? { "X-Agency-Key": brand.agencyKey }
    : shop
      ? { "X-Shop-Key": shop.key }
      : {};
  return request<VideoOut>("/api/uploads", { method: "POST", body: form, headers });
}

// --- batch mode (feature 46) ----------------------------------------------------------------

export interface BatchProduct {
  file: File;
  name: string;
  price: string;
  offer: string;
}

export interface BatchItem {
  video_id: string;
  name: string | null;
  price: string | null;
  video_status: string;
  ad_id: string | null;
  status: AdStatus | null;
  template: string | null;
  link: string | null;
  preview_url: string | null;
}

export interface BatchOut {
  id: string;
  shop_id: string;
  created_at: string;
  items: BatchItem[];
  published: number;
  finished: number;
  shop_key: string | null;
}

export const MAX_BATCH = 12;

export function uploadBatch(fields: BriefValues, products: BatchProduct[]): Promise<BatchOut> {
  return asStoredShop(fields.shopName, (shop) => sendBatch(fields, products, shop));
}

function sendBatch(
  fields: BriefValues,
  products: BatchProduct[],
  shop: StoredShop | null,
): Promise<BatchOut> {
  const form = new FormData();
  if (shop) form.set("shop_id", shop.id);
  form.set("shop_name", fields.shopName);
  form.set("language", fields.language);
  form.set("rights_confirmed", String(fields.rightsConfirmed));
  if (fields.whatsappNumber) form.set("whatsapp_number", fields.whatsappNumber);
  if (fields.shopUrl) form.set("shop_url", fields.shopUrl);
  if (fields.offer) form.set("offer", fields.offer);
  if (fields.occasion && fields.occasion !== "none") form.set("occasion", fields.occasion);
  form.set(
    "items",
    JSON.stringify(
      products.map((p) => ({
        name: p.name.trim() || null,
        price: p.price.trim() || null,
        offer: p.offer.trim() || null,
      })),
    ),
  );
  for (const product of products) form.append("files", product.file);
  const headers: Record<string, string> = shop ? { "X-Shop-Key": shop.key } : {};
  return request<BatchOut>("/api/batches", { method: "POST", body: form, headers });
}

export function getBatch(batchId: string): Promise<BatchOut> {
  return request<BatchOut>(`/api/batches/${batchId}`);
}

// --- Instagram and Facebook import ---------------------------------------------------------

export interface ImportPost {
  id: string;
  source: "instagram" | "facebook";
  account: string;
  caption: string;
  thumbnail_url: string | null;
  created_at: string | null;
  downloadable: boolean;
}

/** Opening this address starts "Continue with Facebook" and comes back to /import. */
export const IMPORT_START_URL = `${API_BASE_URL}/api/import/meta/start`;

export function getImportStatus(): Promise<{ enabled: boolean }> {
  return request<{ enabled: boolean }>("/api/import/meta/status");
}

export function getImportPosts(session: string): Promise<ImportPost[]> {
  return request<ImportPost[]>("/api/import/meta/posts", {
    headers: { "X-Import-Session": session },
  });
}

export function importPost(session: string, postId: string, fields: BriefValues): Promise<VideoOut> {
  return asStoredShop(fields.shopName, (shop) => {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "X-Import-Session": session,
    };
    if (shop) headers["X-Shop-Key"] = shop.key;
    const body = {
      post_id: postId,
      shop_id: shop?.id ?? null,
      shop_name: fields.shopName,
      language: fields.language,
      whatsapp_number: fields.whatsappNumber || null,
      shop_url: fields.shopUrl || null,
      price: fields.price || null,
      offer: fields.offer || null,
      rights_confirmed: fields.rightsConfirmed,
      occasion: fields.occasion ?? "none",
    };
    return request<VideoOut>("/api/import/meta/use", {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });
  });
}

export function getVideo(id: string): Promise<VideoOut> {
  return request<VideoOut>(`/api/videos/${encodeURIComponent(id)}`);
}

export function getAd(id: string): Promise<AdOut> {
  return request<AdOut>(`/api/ads/${encodeURIComponent(id)}`);
}

/** Server-sent progress for one ad; null when the browser cannot stream (then poll). */
export function streamAd(id: string, onChange: () => void): (() => void) | null {
  if (typeof EventSource === "undefined") return null;
  const source = new EventSource(`${API_BASE_URL}/api/ads/${encodeURIComponent(id)}/stream`);
  source.addEventListener("progress", onChange);
  source.addEventListener("status", onChange);
  source.addEventListener("end", () => source.close());
  return () => source.close();
}

// --- why panel ------------------------------------------------------------------------------

export interface Decision {
  at: string;
  actor: string;
  action: string;
  message: string;
  details: Record<string, unknown>;
}

export interface WhyOut {
  trail_intact: boolean;
  entries_checked: number;
  decisions: Decision[];
  builds: { number: number; template: string; reason: string; size_bytes: number }[];
  fixes: { round: number; failed_gates: string[]; change: string }[];
  cost: CostOut;
  cost_by_role: Record<string, number>;
}

export function getWhy(id: string): Promise<WhyOut> {
  return request<WhyOut>(`/api/ads/${encodeURIComponent(id)}/why`);
}

// --- try-it ---------------------------------------------------------------------------------

export interface SampleOut {
  key: string;
  title: string;
  about: string;
  language: "ur" | "en";
  synthetic: boolean;
  source: string;
  video_url: string;
}

export function getSamples(): Promise<SampleOut[]> {
  return request<SampleOut[]>("/api/samples");
}

export function trySample(key: string): Promise<VideoOut> {
  return request<VideoOut>("/api/try", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ sample: key }),
  });
}

// --- studio ---------------------------------------------------------------------------------

export interface CostOut {
  calls: number;
  usd: number;
  pkr: number;
}

export interface GameStats {
  plays: number;
  finishes: number;
  wins: number;
  cta_taps: number;
  median_seconds: number | null;
  completion: number | null;
  cta_rate: number | null;
  /** Features 36 and 37: plays opened from the counter poster, and on the shop's website. */
  poster_plays?: number;
  website_plays?: number;
  /** Feature 42: players who challenged a friend, and plays those challenges brought. */
  shares?: number;
  challenge_plays?: number;
}

export interface AdSummary {
  id: string;
  status: AdStatus;
  template: string | null;
  product: string | null;
  created_at: string;
  published_at: string | null;
  link: string | null;
  preview_url: string | null;
  stats: GameStats;
  cost: CostOut;
}

export interface ShopOut {
  id: string;
  name: string;
  language: string;
  brand_kit: { palette: string[]; tone: string; logo_url: string | null } | null;
  ads: AdSummary[];
  totals: { ads: number; published: number; plays: number; cta_taps: number; pkr: number };
  /** Feature 53: what worked for this shop, one line per game type, the best first. */
  memory?: string[];
}

export function getShop(key: string): Promise<ShopOut> {
  return request<ShopOut>("/api/shop", { headers: { "X-Shop-Key": key } });
}

// --- unique win codes (feature 40) -------------------------------------------------------------

export interface CouponsOut {
  issued: number;
  redeemed: number;
  by_ad: { ad_id: string; issued: number; redeemed: number }[];
  recent: { code: string; ad_id: string; issued_at: string; redeemed_at: string | null }[];
}

export interface RedeemOut {
  result: "redeemed" | "already_used" | "shared_code" | "not_found";
  code: string;
  message: string;
  product: string | null;
  ad_id: string | null;
  issued_at: string | null;
  redeemed_at: string | null;
}

export function getCoupons(key: string): Promise<CouponsOut> {
  return request<CouponsOut>("/api/shop/coupons", { headers: { "X-Shop-Key": key } });
}

export function redeemCoupon(key: string, code: string): Promise<RedeemOut> {
  return request<RedeemOut>("/api/shop/coupons/redeem", {
    method: "POST",
    headers: { "X-Shop-Key": key, "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
}

// --- gallery and the blind preference page --------------------------------------------------

export interface GalleryAd {
  id: string;
  product: string;
  category: string;
  language: "ur" | "en";
  template: string | null;
  link: string;
  preview_url: string | null;
  published_at: string | null;
  stats: GameStats;
}

export function getGallery(): Promise<GalleryAd[]> {
  return request<GalleryAd[]>("/api/gallery");
}

export interface Comparison {
  ad_id: string;
  game_url: string;
  still: { image_url: string; product: string; offer: string | null; price: string | null; language: "ur" | "en" };
  game_side: "left" | "right";
}

export function getComparison(): Promise<Comparison> {
  return request<Comparison>("/api/compare");
}

export async function sendVote(comparison: Comparison, choice: "game" | "still"): Promise<void> {
  await request<null>("/api/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ad_id: comparison.ad_id, choice, game_side: comparison.game_side }),
  });
}

// --- easier versions (feature 44) --------------------------------------------------------------

export interface EasierOut {
  hard: boolean;
  reason: string | null;
  stats: Partial<GameStats>;
  version: {
    id: string;
    status: AdStatus;
    state: "making" | "ready" | "using" | "used" | "dismissed" | null;
    change: string | null;
    play_url: string | null;
  } | null;
}

export function getEasier(adId: string): Promise<EasierOut> {
  return request<EasierOut>(`/api/ads/${adId}/easier`);
}

export function decideEasier(adId: string, shopKey: string, choice: "use" | "dismiss"): Promise<EasierOut> {
  return request<EasierOut>(`/api/ads/${adId}/easier/${choice}`, {
    method: "POST",
    headers: { "X-Shop-Key": shopKey },
  });
}

// --- offers on WhatsApp (feature 43) ---------------------------------------------------------

export interface LeadsOut {
  available: boolean;
  enabled: boolean;
  code: string | null;
  join_link: string | null;
  agreed: number;
}

export function getLeads(shopKey: string): Promise<LeadsOut> {
  return request<LeadsOut>("/api/shop/leads", { headers: { "X-Shop-Key": shopKey } });
}

export function setLeads(shopKey: string, enabled: boolean): Promise<LeadsOut> {
  return request<LeadsOut>("/api/shop/leads", {
    method: "POST",
    headers: { "X-Shop-Key": shopKey, "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

/** The sign-ups as a CSV file; it needs the studio key, so it is fetched, not linked. */
export async function downloadLeads(shopKey: string): Promise<Blob> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/shop/leads.csv`, {
      headers: { "X-Shop-Key": shopKey },
    });
  } catch {
    throw new ApiError(0, "Could not reach Reel2Play. Check your connection and try again.");
  }
  if (!response.ok) throw new ApiError(response.status, "The list could not be downloaded.");
  return response.blob();
}

// --- agency workspace (feature 47) ------------------------------------------------------------

export type AgencyRole = "owner" | "editor" | "viewer";

export interface AgencyMember {
  id: string;
  name: string;
  role: AgencyRole;
  you: boolean;
}

export interface AgencyBrandOut {
  id: string;
  name: string;
  games: number;
  live: number;
  plays: number;
  cta_taps: number;
}

export interface AgencyOut {
  id: string;
  name: string;
  you: AgencyMember;
  members: AgencyMember[];
  brands: AgencyBrandOut[];
}

export interface StoredAgency {
  key: string;
  name: string;
}

/** A brand this browser is making a game for, chosen on the agency page. */
export interface AgencyBrand {
  shopId: string;
  name: string;
  agencyKey: string;
}

const AGENCY_STORAGE = "r2p.agency";
const BRAND_STORAGE = "r2p.brand";

function readJson<T>(storage: () => Storage, key: string): T | null {
  try {
    const raw = storage().getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function writeJson(storage: () => Storage, key: string, value: unknown): void {
  try {
    if (value) storage().setItem(key, JSON.stringify(value));
    else storage().removeItem(key);
  } catch {
    // Storage may be blocked; the agency page then asks again.
  }
}

export const storedAgency = () => readJson<StoredAgency>(() => window.localStorage, AGENCY_STORAGE);
export const rememberAgency = (agency: StoredAgency | null) =>
  writeJson(() => window.localStorage, AGENCY_STORAGE, agency);
export const agencyBrand = () => readJson<AgencyBrand>(() => window.sessionStorage, BRAND_STORAGE);
export const chooseBrand = (brand: AgencyBrand | null) =>
  writeJson(() => window.sessionStorage, BRAND_STORAGE, brand);

const asMember = (key: string, json = false): Record<string, string> =>
  json ? { "X-Agency-Key": key, "Content-Type": "application/json" } : { "X-Agency-Key": key };

export function startAgency(name: string, yourName: string): Promise<{ key: string; agency: AgencyOut }> {
  return request("/api/agencies", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, your_name: yourName }),
  });
}

export function joinAgency(code: string, yourName: string): Promise<{ key: string; agency: AgencyOut }> {
  return request("/api/agency/join", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code, your_name: yourName }),
  });
}

export function getAgency(key: string): Promise<AgencyOut> {
  return request<AgencyOut>("/api/agency", { headers: asMember(key) });
}

export function inviteMember(key: string, role: AgencyRole): Promise<{ code: string; role: AgencyRole; expires_at: string }> {
  return request("/api/agency/invites", {
    method: "POST",
    headers: asMember(key, true),
    body: JSON.stringify({ role }),
  });
}

export function addBrand(
  key: string,
  brand: { name: string; whatsapp_number?: string; shop_url?: string },
): Promise<AgencyOut> {
  return request<AgencyOut>("/api/agency/brands", {
    method: "POST",
    headers: asMember(key, true),
    body: JSON.stringify(brand),
  });
}

export function changeRole(key: string, memberId: string, role: AgencyRole): Promise<AgencyOut> {
  return request<AgencyOut>(`/api/agency/members/${memberId}`, {
    method: "POST",
    headers: asMember(key, true),
    body: JSON.stringify({ role }),
  });
}

export function removeMember(key: string, memberId: string): Promise<AgencyOut> {
  return request<AgencyOut>(`/api/agency/members/${memberId}/remove`, {
    method: "POST",
    headers: asMember(key),
  });
}

export function brandStudio(key: string, shopId: string): Promise<ShopOut> {
  return request<ShopOut>(`/api/agency/brands/${shopId}`, { headers: asMember(key) });
}

// --- template marketplace (feature 49) --------------------------------------------------------

export interface TemplateCard {
  id: string;
  name: string;
  description: string;
  control: string;
  good_for: string[];
  designer: string;
  demo_url: string;
}

export interface SubmissionOut {
  id: string;
  template_id: string | null;
  status: "checks_failed" | "waiting" | "approved" | "rejected";
  problems: string[];
  review_note: string | null;
  created_at: string;
  token: string | null;
}

export function getTemplates(): Promise<TemplateCard[]> {
  return request<TemplateCard[]>("/api/marketplace/templates");
}

export function submitTemplate(form: {
  designerName: string;
  designerContact: string;
  templateJson: File;
  gameTs: File;
}): Promise<SubmissionOut> {
  const body = new FormData();
  body.set("designer_name", form.designerName);
  body.set("designer_contact", form.designerContact);
  body.set("license_confirmed", "true");
  body.set("template_json", form.templateJson);
  body.set("game_ts", form.gameTs);
  return request<SubmissionOut>("/api/marketplace/submissions", { method: "POST", body });
}
