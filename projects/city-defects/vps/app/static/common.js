// Спільні помічники для сторінки мешканця і диспетчерської.
const STATUS = { new: "Нова", assigned: "Призначена", in_progress: "В роботі", resolved: "Виконана", rejected: "Відхилена" };
const SLA_H = { 5: 4, 4: 24, 3: 72, 2: 168, 1: 336 };
const SEV_TXT = { 1: "косметична", 2: "незначна", 3: "помірна", 4: "серйозна", 5: "небезпека для життя" };
const SEV_COLOR = { 1: "#5E8F6A", 2: "#8A9E3C", 3: "#C9940F", 4: "#DB6418", 5: "#C42F28" };
const DEFAULT_CENTER = [50.4501, 30.5234]; // Київ; змініть на своє місто
const OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

const $ = (id) => document.getElementById(id);
function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null && k !== false) n.append(k instanceof Node ? k : String(k));
  return n;
}
const fmt = (ms) => new Date(ms).toLocaleString("uk-UA", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
const sevChip = (s) => el("span", { class: "sev", "data-s": s }, el("i"), `${s}/5 · ${SEV_TXT[s] || ""}`);
const statusChip = (s) => el("span", { class: "chip st-" + s }, STATUS[s] || s);
const isOpen = (r) => !["resolved", "rejected"].includes(r.status);
const slaLeft = (r) => r.created_at + (SLA_H[r.severity] || 72) * 3600e3 - Date.now();
function slaText(ms) {
  const h = Math.round(Math.abs(ms) / 3600e3);
  const t = h >= 48 ? `${Math.round(h / 24)} дн` : `${h} год`;
  return ms < 0 ? `прострочено на ${t}` : `залишилось ${t}`;
}
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
};
async function api(url, opts) {
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `Помилка ${r.status}`);
  return data;
}

function reportCard(r, { actions = null, contact = false } = {}) {
  const mapLink = r.lat != null ? el("a", { href: `https://www.google.com/maps?q=${r.lat},${r.lng}`, target: "_blank", rel: "noopener" }, "Google Maps") : null;
  const left = slaLeft(r);
  return el("article", { class: "card", "data-s": r.severity, id: "r-" + r.id },
    r.photo_url ? el("img", { class: "thumb", src: r.photo_url, alt: "", loading: "lazy" }) : el("div", { class: "thumb" }),
    el("div", { class: "card-main" },
      el("div", { class: "card-top" }, el("span", { class: "mono" }, r.id), statusChip(r.status), sevChip(r.severity),
        r.emergency ? el("span", { class: "chip emer" }, "Аварійна") : null,
        r.confirmations > 1 ? el("span", { class: "chip" }, `скарг: ${r.confirmations}`) : null),
      el("h3", {}, r.title),
      el("div", { class: "meta" }, r.department),
      el("div", { class: "meta" }, r.address || "адреса не вказана", mapLink ? " · " : "", mapLink, " · ", fmt(r.created_at)),
      isOpen(r) ? el("div", { class: "meta " + (left < 0 ? "overdue" : "") }, `Термін реакції ${SLA_H[r.severity]} год: ${slaText(left)}`) : null,
      actions,
      el("details", { class: "more" }, el("summary", {}, "Деталі та історія"),
        r.photo_url ? el("img", { class: "big-photo", src: r.photo_url, alt: "Фото заявки", loading: "lazy" }) : null,
        r.description ? el("div", {}, r.description) : null,
        r.comment ? el("div", { class: "meta" }, "Коментар мешканця: " + r.comment) : null,
        r.ai?.action ? el("div", { class: "meta" }, "Рекомендація AI: " + r.ai.action) : null,
        r.ai?.hazards?.length ? el("div", { class: "meta" }, "Ризики: " + r.ai.hazards.join("; ")) : null,
        contact && r.contact ? el("div", { class: "meta" }, "Контакт: " + r.contact) : null,
        el("ul", { class: "hist" }, (r.history || []).map((h) =>
          el("li", {}, el("span", { class: "mono" }, fmt(h.at)), el("span", {}, `${STATUS[h.status] || h.status}. ${h.note || ""}`)))),
      )));
}
