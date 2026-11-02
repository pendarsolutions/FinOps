/**
 * Plain-language wording for what the engine reports: spec names, values, price lines and its English notes.
 * Text with no translation here is shown as the engine wrote it, so nothing is ever hidden.
 */
import type { ComponentLine, ConstraintResult, Recommendation } from "../api/types";
import { useProviderName } from "./hooks";
import { useI18n, type Lang } from "./i18n";
import { formatDecimal, localizeDigits } from "./money";

type Pair = [fa: string, en: string];

const DIMENSIONS: Record<string, Pair> = {
  cpu_cores: ["پردازنده", "CPU"],
  cpu_class: ["نوع پردازنده", "CPU type"],
  ram_gb: ["حافظه", "Memory"],
  storage_gb: ["دیسک", "Disk"],
  storage_type: ["نوع دیسک", "Disk type"],
  included_traffic_gb: ["ترافیک همراه پلن", "Traffic in the plan"],
  traffic_cost_toman: ["هزینه ترافیک", "Traffic cost"],
  ipv4_cost_toman: ["هزینه IP عمومی", "Public IP cost"],
  datacenter: ["دیتاسنتر", "Datacenter"],
  billing_cadence: ["شیوه پرداخت", "Billing"],
  unknown_features: ["موارد نامشخص", "Not stated"],
};

const VALUES: Record<string, Pair> = {
  shared: ["اشتراکی", "shared"],
  "dedicated/optimized": ["اختصاصی", "dedicated"],
  unknown: ["نامشخص", "not stated"],
  monthly: ["ماهانه", "monthly"],
  hourly: ["ساعتی", "hourly"],
  "hourly+monthly": ["ساعتی یا ماهانه", "hourly or monthly"],
};

const UNITS: Record<string, Pair> = {
  day: ["روز", "days"],
  gb: ["گیگابایت", "GB"],
  gb_month: ["گیگابایت", "GB"],
  gb_ram_month: ["گیگابایت", "GB"],
  vcore_month: ["هسته", "cores"],
  plan_month: ["ماه", "month"],
  plan_hour: ["ساعت", "hours"],
  ip_month: ["IP", "IP"],
  ip_hour: ["ساعت", "hours"],
  gpu_month: ["GPU", "GPU"],
  toman: ["تومان", "Toman"],
};

const LEVELS: Record<string, Pair> = {
  none: ["ندارد", "none"],
  low: ["کم", "low"],
  medium: ["متوسط", "medium"],
  high: ["زیاد", "high"],
  unverified: ["تأییدنشده", "unverified"],
  needs_human_review: ["نیاز به بررسی شما", "needs your review"],
  not_equivalent: ["معادل نیست", "not equivalent"],
};

const CHECKS: Record<string, Pair> = {
  "HC-CPU": ["پردازنده کمتر از سرور فعلی نیست", "At least as much CPU as now"],
  "HC-RAM": ["حافظه کمتر از سرور فعلی نیست", "At least as much memory as now"],
  "HC-DISK": ["دیسک کمتر از سرور فعلی نیست", "At least as much disk as now"],
  "HC-AVAIL": ["این پلن الان برای خرید موجود است", "The plan is available to buy now"],
  "HC-EXACT": ["قیمت این پلن دقیق است، نه «شروع از»", "The plan has an exact price, not a \"starting from\" price"],
  "HC-REGION": ["سرور در ایران است", "The server is in Iran"],
  "HC-DEDICATED": ["پردازنده اختصاصی به اشتراکی تبدیل نمی‌شود", "A dedicated CPU doesn't become a shared one"],
  "HC-PRICEABLE": ["هزینه ماهانه برای مصرف شما قابل محاسبه است", "The monthly cost can be worked out for your usage"],
};

const FA_LINES: [RegExp, string][] = [
  [/^CPU (\S+)$/, "پردازنده $1 هسته"],
  [/^RAM GB (\S+)$/, "حافظه $1 گیگابایت"],
  [/^Disk GB (\S+)$/, "دیسک $1 گیگابایت"],
  [/^vCPU \((.+)\)$/, "پردازنده ($1)"],
  [/^RAM GB \((.+)\)$/, "حافظه ($1)"],
  [/^Block storage \((.+)\)$/, "دیسک ($1)"],
  [/^First IPv4$/, "نخستین IP عمومی"],
  [/^Additional IPv4$/, "IP عمومی اضافه"],
  [/^Public IPv4$/, "IP عمومی"],
  [/^IPv4 monthly$/, "IP عمومی، ماهانه"],
  [/^Traffic$/, "ترافیک"],
  [/^Traffic within included (.+) GB$/, "ترافیک، تا $1 گیگابایت همراه پلن"],
  [/^Traffic: unlimited per catalog$/, "ترافیک نامحدود"],
  [/^Traffic: unlimited at rate limit$/, "ترافیک نامحدود با سرعت محدود"],
  [/^Traffic within fair use \((.+) GB\/day\)$/, "ترافیک، تا $1 گیگابایت در روز"],
  [/^Traffic download$/, "ترافیک دانلود"],
  [/^Traffic upload$/, "ترافیک آپلود"],
  [/^(.+) monthly$/, "$1، ماهانه"],
];

/** `{p}` is the provider's display name. */
const FA_NOTES: [RegExp, string][] = [
  [/^(\w+): the official calculator doesn't price traffic.*$/, "{p}: ماشین‌حساب رسمی ترافیک را قیمت‌گذاری نمی‌کند، پس اینجا حساب نشده است. ممکن است ترافیک جدا محاسبه شود."],
  [/^(\w+): the official calculator doesn't price IPv4.*$/, "{p}: ماشین‌حساب رسمی IP عمومی را قیمت‌گذاری نمی‌کند، پس فرض شده یک IP همراه سرور است."],
  [/^(\w+): the price list mentions a setup fee equal to 7 days.*$/, "{p}: در فهرست قیمت، هزینه راه‌اندازی برابر ۷ روز آمده است. این هزینه یک‌باره در رقم ماهانه نیست."],
  [/^(\w+): CPU (\S+) priced at the next size sold, (\S+)\.$/, "{p}: پردازنده شما $2 هسته است و با نزدیک‌ترین اندازه فروشی، $3 هسته، حساب شده است."],
  [/^(\w+): RAM GB (\S+) priced at the next size sold, (\S+)\.$/, "{p}: حافظه شما $2 گیگابایت است و با نزدیک‌ترین اندازه فروشی، $3 گیگابایت، حساب شده است."],
  [/^(\w+): Disk GB (\S+) priced at the next size sold, (\S+)\.$/, "{p}: دیسک شما $2 گیگابایت است و با نزدیک‌ترین اندازه فروشی، $3 گیگابایت، حساب شده است."],
  [/^(\w+): one public IPv4 assumed included.*$/, "{p}: فهرست قیمت درباره IP عمومی چیزی نگفته است، پس فرض شده یک IP همراه سرور است."],
  [/^(\w+): catalog does not state which direction.*$/, "{p}: مشخص نیست سهمیه ترافیک برای دانلود است یا آپلود، پس برای احتیاط مجموع هر دو با سهمیه مقایسه شده است."],
  [/^(\w+): 30-day plan price used as the monthly price.*$/, "{p}: قیمت پلن ۳۰ روزه به‌عنوان قیمت ماهانه در نظر گرفته شده است."],
  [/^(\w+) (\S+): no hourly rate in the seed.*$/, "{p} $2: نرخ ساعتی در دسترس نیست و با قیمت ماهانه حساب شده است."],
  [/^(\w+) (\S+): download is unlimited but rate-limited to (\S+) Mbps\.$/, "{p} $2: دانلود نامحدود است، اما سرعت آن به $3 مگابیت بر ثانیه محدود است."],
  [/^Prices exclude tax\. Provider rule \S+ adds (\S+)% VAT.*$/, "قیمت‌ها بدون مالیات است. این ارائه‌دهنده $1٪ مالیات بر ارزش افزوده به فاکتور اضافه می‌کند."],
  [/^ArvanCloud: Seed only contains monthly component rates.*$/, "آروان‌کلود: نرخ ساعتی در دسترس نیست، پس سرور زمان‌بندی‌شده با قیمت یک ماه کامل حساب شده است."],
  [/^ArvanCloud: IR-IPV4-FIRST is applied.*$/, "آروان‌کلود: نخستین IP و IPهای اضافه هر سرور با نرخ جداگانه حساب شده‌اند."],
  [/^ArvanCloud: Resource 'download'.*$/, "آروان‌کلود: دانلود به‌عنوان ترافیک خروجی و آپلود به‌عنوان ترافیک ورودی حساب شده است. این نگاشت در صفحه آروان تأیید نشده است."],
  [/^ArvanCloud: Each tier price applies only.*$/, "آروان‌کلود: قیمت هر پله فقط برای همان بخش از حجم مصرفی اعمال شده است."],
  [/^Liara: If the resource's billing_mode.*$/, "لیارا: چون زمان کار سرور محدود است، با نرخ ساعتی حساب شده است."],
  [/^CPU class semantics.*$/, "این ارائه‌دهنده نوع پردازنده را اعلام نکرده است."],
  [/^candidate traffic policy: included_quota$/, "حجم مشخصی ترافیک همراه پلن است."],
  [/^candidate traffic policy: unlimited$/, "ترافیک نامحدود است."],
  [/^candidate traffic policy: .*$/, "شرایط ترافیک این پلن با پلن فعلی فرق دارد."],
  [/^public IPv4 inclusion not stated in catalog$/, "مشخص نیست IP عمومی همراه پلن است یا نه."],
  [/^(\S+) GB\/month exceeds the (\S+) GB included in (\S+); .*$/, "مصرف $1 گیگابایت در ماه از سهمیه $2 گیگابایتی $3 بیشتر است و قیمت ترافیک اضافه اعلام نشده است."],
  [/^Discovery context only.*$/, "فقط برای آشنایی است و در جمع هزینه یا صرفه‌جویی حساب نمی‌شود."],
  [/^Separate invoice line; not part of base price\.$/, "در فاکتور جدا می‌آید و جزو قیمت پایه نیست."],
];

/** Numbers come back from the engine padded ("1024.0000"). */
const trimZeros = (s: string) => s.replace(/(\d+)\.0+(?!\d)/g, "$1");

export function usePlain() {
  const { lang, fieldLabel } = useI18n();
  const pname = useProviderName();
  const tr = (p: Pair | undefined, fallback: string) => (p ? p[lang === "fa" ? 0 : 1] : fallback);

  const note = (raw: string): string => {
    const text = trimZeros(raw).replace(/the seed catalog/g, "the price list").replace(/in the seed/g, "in the price list");
    if (lang !== "fa") return text;
    const unknownField = /^'(\w+)' is not known/.exec(text);
    if (unknownField) return `${fieldLabel(unknownField[1])} مشخص نیست. آن را وارد کنید.`;
    for (const [re, fa] of FA_NOTES) {
      const m = re.exec(text);
      if (m) return localizeDigits(text.replace(re, fa).replace("{p}", pname(m[1], lang)), lang);
    }
    return text;
  };

  return {
    dimension: (d: string) => tr(DIMENSIONS[d], d),
    /** A spec value with its unit: "24 cores", "48 GB". */
    value: (dim: string, v: unknown): string => {
      if (v === null || v === undefined || v === "") return tr(VALUES.unknown, "—");
      if (Array.isArray(v)) return v.map((x) => note(String(x))).join(" ");
      if (typeof v === "object") return tr(VALUES.unknown, "—");
      const s = String(v);
      if (VALUES[s]) return tr(VALUES[s], s);
      const n = formatDecimal(s, lang, { maxFraction: 2 });
      if (dim === "cpu_cores") return `${n} ${tr(UNITS.vcore_month, "")}`;
      if (dim.endsWith("_gb")) return `${n} ${tr(UNITS.gb, "")}`;
      if (dim.endsWith("_toman")) return `${n} ${tr(UNITS.toman, "")}`;
      return n;
    },
    unit: (u: string | null) => (u ? tr(UNITS[u], u) : ""),
    level: (v: string | null | undefined) => {
      const k = (v ?? "").toLowerCase();
      return k === "" || k === "n/a" ? "—" : tr(LEVELS[k], v ?? "—");
    },
    check: (c: ConstraintResult) => tr(CHECKS[c.constraint_id], c.constraint_id),
    lineLabel: (l: ComponentLine): string => {
      const text = trimZeros(l.description);
      if (l.status === "unavailable") return note(l.description);
      if (lang !== "fa") return text.replace(/^CPU (\S+)$/, "$1 CPU cores").replace(/^RAM GB (\S+)$/, "$1 GB memory").replace(/^Disk GB (\S+)$/, "$1 GB disk");
      for (const [re, fa] of FA_LINES) if (re.test(text)) return localizeDigits(text.replace(re, fa), lang);
      return text;
    },
    note,
  };
}

/** What a suggestion asks you to do. A move names the plan it moves to. */
export function recTitle(r: Recommendation, lang: Lang): string {
  const target = r.evidence?.candidate_label;
  if (r.rule_id === "REC-003" && target) return lang === "fa" ? `انتقال به ${target}` : `Move to ${target}`;
  return lang === "fa" ? r.title_fa || r.title_en : r.title_en || r.title_fa;
}
