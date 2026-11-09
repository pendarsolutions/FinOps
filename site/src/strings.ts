import { useLang, type Lang } from "./lang";

/** [fa, en]. Technical terms (FinOps, SKU, Docker...) stay in English inside Persian text. */
const S = {
  appName: ["FinOps agent", "FinOps agent"],
  poweredBy: ["قدرت‌گرفته از پندار", "Powered by Pendar"],
  providerDist: ["توزیع بر اساس ارائه‌دهنده", "By provider"],
  copy: ["کپی", "Copy"],
  copied: ["کپی شد", "Copied"],
  // ---- landing (moved from the app's dictionary, apps/web/src/lib/i18n.tsx)
  lpNavFeatures: ["امکانات", "Features"],
  lpNavHow: ["چطور کار می‌کند", "How it works"],
  lpNavTrust: ["اصول ما", "Principles"],
  lpBadge: ["FinOps متن‌باز برای تیم‌های ایرانی", "Open-source FinOps for Iranian teams"],
  lpHeroA: ["هزینه زیرساخت ابری‌تان را", "Know exactly what your"],
  lpHeroB: ["دقیق بشناسید", "Iranian cloud costs"],
  lpHeroSub: [
    "قیمت دقیق از کاتالوگ رسمی آروان، لیارا، سرور.آی‌آر و ایران‌سرور. مقایسه منصفانه پلن‌های معادل و پیشنهاد صرفه‌جویی با شواهد — بدون حدس هوش مصنوعی.",
    "Exact prices from the official catalogs of ArvanCloud, Liara, Server.ir and IranServer. Fair like-for-like comparisons and evidence-backed savings — no AI guesswork.",
  ],
  lpCtaHow: ["ببینید چطور کار می‌کند", "See how it works"],
  lpPreviewLabel: ["محاسبه‌شده روی یک زیرساخت نمونه", "Computed on a sample setup"],
  lpPreviewSpend: ["هزینه ماهانه", "Monthly spend"],
  lpPreviewAvoidable: ["قابل اجتناب", "Avoidable"],
  lpProvidersTitle: ["کاتالوگ قیمت نسخه‌دار از ارائه‌دهندگان ایرانی", "Versioned price catalog of Iranian providers"],
  lpHowTitle: ["از توضیح ساده تا صرفه‌جویی واقعی", "From a plain description to real savings"],
  lpStep1T: ["وارد کنید", "Add"],
  lpStep1B: ["سرورها را متصل کنید، یا از فرم، چت فارسی یا فاکتور PDF/CSV استفاده کنید.", "Connect your servers, or use the builder, Persian chat or a PDF/CSV invoice."],
  lpStep2T: ["تأیید کنید", "Confirm"],
  lpStep2B: ["هر ردیف را بازبینی می‌کنید؛ قبل از تأیید هیچ قیمتی محاسبه نمی‌شود.", "You review every row; nothing is priced before you confirm."],
  lpStep3T: ["قیمت دقیق", "Exact price"],
  lpStep3B: ["موتور قطعی با Decimal و منبع و تاریخ برای هر قیمت.", "A deterministic Decimal engine, with source and date on every price."],
  lpStep4T: ["مقایسه معادل", "Compare"],
  lpStep4B: ["فقط پلن‌هایی که واقعاً معادل‌اند، با فهرست کامل تفاوت‌ها.", "Only truly equivalent plans, with every difference listed."],
  lpStep5T: ["صرفه‌جویی", "Save"],
  lpStep5B: ["پیشنهادهای قابل اجرا با ریسک، تلاش و دوره بازگشت سرمایه.", "Actionable recommendations with risk, effort and payback."],
  lpFeatTitle: ["ساخته‌شده برای اعتماد، نه برای جلوه", "Built for trust, not for show"],
  lpF1T: ["قیمت دقیق، نه تخمین", "Exact prices, not estimates"],
  lpF1B: ["اگر قیمتی منتشر نشده باشد، به‌جای حدس زدن صریحاً PRICE_UNAVAILABLE نشان می‌دهیم.", "When a price isn't published we say PRICE_UNAVAILABLE instead of guessing."],
  lpF2T: ["ارزان‌تر ≠ معادل", "Cheaper ≠ equivalent"],
  lpF2B: ["محدودیت‌های سخت، امتیاز تطابق و تفاوت‌های CPU، دیسک، ترافیک و دیتاسنتر.", "Hard constraints, fit score, and the CPU, disk, traffic and datacenter differences."],
  lpF3T: ["شواهد برای هر عدد", "Evidence for every number"],
  lpF3B: ["هر پیشنهاد به ردیف کاتالوگ، نسخه قیمت و تاریخ منبع ارجاع می‌دهد.", "Every recommendation cites its catalog rows, price version and source date."],
  lpF4T: ["تاریخچه قیمت", "Price history"],
  lpF4B: ["قیمت‌ها هرگز بازنویسی نمی‌شوند؛ هر تغییر نسخه جدیدی می‌سازد.", "Prices are never overwritten; every change creates a new version."],
  lpF5T: ["مشاوری که عدد نمی‌سازد", "An advisor that can't invent numbers"],
  lpF5B: ["مشاور فقط اعداد ابزارهای قطعی را توضیح می‌دهد؛ هر عدد ساختگی رد می‌شود.", "The advisor only explains tool numbers; any invented figure is rejected."],
  lpF6T: ["فارسی، از روز اول", "Persian from day one"],
  lpF6B: ["رابط راست‌به‌چپ، اعداد فارسی، تومان و ریال با تأیید صریح.", "RTL interface, Persian digits, Toman and Rial with explicit confirmation."],
  lpTrustTitle: ["کارهایی که هرگز انجام نمی‌دهیم", "Things we never do"],
  lpT1: ["قیمت یا صرفه‌جویی را با هوش مصنوعی محاسبه نمی‌کنیم", "Let AI calculate a price or a saving"],
  lpT2: ["ریال را بی‌صدا تومان فرض نمی‌کنیم", "Silently assume Rial is Toman"],
  lpT3: ["بدون داده مصرف، کوچک‌سازی پیشنهاد نمی‌دهیم", "Recommend downsizing without usage data"],
  lpT4: ["تفاوت‌ها را برای ارزان‌تر نشان دادن پنهان نمی‌کنیم", "Hide differences to make a cheaper plan look better"],
  lpFinalTitle: ["اولین تحلیل را در چند دقیقه ببینید", "See your first analysis in minutes"],
  lpFinalBody: ["نصبش کنید، سرورهایتان را اضافه کنید و ببینید هر کدام واقعاً چقدر هزینه دارد.", "Install it, add your servers, and see what each one really costs."],
  lpFooter: ["FinOps agent — شفافیت هزینه زیرساخت در ایران", "FinOps agent — infrastructure cost transparency for Iran"],
  // ---- the site's own
  lpNavInstall: ["نصب", "Install"],
  lpCtaInstall: ["روی سرور خودتان نصب کنید", "Install on your server"],
  lpCtaGithub: ["کد در GitHub", "Code on GitHub"],
  lpInstallTitle: ["با یک دستور، روی سرور خودتان", "One command, on your own server"],
  lpInstallBody: [
    "روی یک سرور لینوکس با دست‌کم ۲ گیگابایت حافظه اجرا کنید. اگر Docker نباشد نصبش می‌کند، چند سؤال می‌پرسد و نشانی داشبورد را نشان می‌دهد. داده‌هایتان روی سرور خودتان می‌ماند.",
    "Run it on a Linux server with at least 2 GB of memory. It installs Docker if it's missing, asks a few questions and prints the address of your dashboard. Your data stays on your server.",
  ],
  lpInstallCommandLabel: ["دستور نصب", "Install command"],
  lpManageTitle: ["بعد از نصب، همه‌چیز از خط فرمان", "After that, everything from the command line"],
  lpManage1: ["وضعیت، نشانی و نسخه", "Status, address and version"],
  lpManage2: ["ایمیل برای هشدارها و بازیابی رمز", "Email for alerts and password resets"],
  lpManage3: ["پشتیبان‌گیری پیش از ارتقا، بعد ارتقا", "Back up, then upgrade"],
  lpManage4: ["بررسی همه‌چیز، با راه‌حل", "Check everything, with fixes"],
  lpInstallBlocked: [
    "Docker Hub در دسترس نیست؟ از --registry-mirror یا بسته آفلاین هر نسخه استفاده کنید.",
    "Docker Hub blocked? Use --registry-mirror, or the offline bundle attached to every release.",
  ],
  lpLinkGuide: ["راهنمای نصب", "Installation guide"],
  lpLinkReleases: ["نسخه‌ها و بسته آفلاین", "Releases and offline bundles"],
  lpLinkSource: ["کد منبع", "Source code"],
  lpLicense: ["مجوز Apache 2.0", "Apache 2.0 license"],
} as const satisfies Record<string, readonly [string, string]>;

export type Key = keyof typeof S;

export function useT(): { t: (k: Key) => string; lang: Lang; setLang: (l: Lang) => void } {
  const { lang, setLang } = useLang();
  return { t: (k) => S[k][lang === "fa" ? 0 : 1], lang, setLang };
}
