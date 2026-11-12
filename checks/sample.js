// A random sample of price pages from every game and type: each must draw the full card page with the same price as
// its own HTML, one address tag, and no script errors.
//
//   node checks/sample.js <built site dir>      AFTER=http://127.0.0.1:8765      PER_GROUP=4      SEED=1112
const { chromium } = require("playwright"); const fs = require("fs"); const path = require("path");
const AFTER = process.env.AFTER || "http://127.0.0.1:8765", site = process.argv[2], per = +(process.env.PER_GROUP || 4);
let seed = +(process.env.SEED || 1112); const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
const by = {};
for (const f of fs.readdirSync(path.join(site, "data", "set")).sort()) {
  const d = JSON.parse(fs.readFileSync(path.join(site, "data", "set", f), "utf8"));
  for (const i of d.items) if (i.pg) (by[`${d.k}/${i.t}`] ||= []).push(i.pg);
}
const pick = [];
for (const k of Object.keys(by).sort()) { const a = by[k].slice(); for (let n = 0; n < per && a.length; n++) pick.push(a.splice(Math.floor(rnd() * a.length), 1)[0]); }
(async () => {
  const browser = await chromium.launch(); let bad = 0, n = 0;
  for (const [idx, slug] of pick.entries()) {
    const vp = idx % 2 ? { width: 375, height: 812 } : { width: 1280, height: 800 };
    const ctx = await browser.newContext({ viewport: vp }); await ctx.route((u) => !u.href.startsWith("http://127.0.0.1"), (r) => r.abort());
    const raw = await (await ctx.request.get(`${AFTER}/p/${slug}.html`)).text();
    const m = raw.match(/<div class="price-big">(?:<span[^>]*>)?([^<]*)</); const sp = m ? m[1] : null;
    const page = await ctx.newPage(); const errs = [];
    page.on("pageerror", (e) => errs.push(String(e.message).slice(0, 120)));
    page.on("console", (m) => { if (m.type() === "error" && !/Failed to load resource|net::ERR/.test(m.text())) errs.push(m.text().slice(0, 120)); });
    await page.goto(`${AFTER}/p/${slug}.html`, { waitUntil: "domcontentloaded" }); await page.waitForTimeout(1500);
    const st = await page.evaluate(() => ({ price: document.querySelector(".price-big")?.innerText.trim(), chart: !!document.querySelector("#chart"), add: !!document.querySelector("#addcol"), canon: [...document.querySelectorAll('link[rel="canonical"]')].map((l) => l.getAttribute("href")), left: !!document.querySelector("#pp-static"), over: document.documentElement.scrollWidth > innerWidth + 1, h1: document.querySelectorAll("h1").length }));
    const pass = errs.length === 0 && st.price === sp && st.chart && st.add && st.canon.length === 1 && st.canon[0].endsWith(`/p/${slug}.html`) && !st.left && !st.over && st.h1 === 1;
    n++; if (!pass) { bad++; console.log("FAIL", slug, JSON.stringify({ sp, ...st, errs })); }
    await ctx.close();
  }
  console.log(`random price pages (${Object.keys(by).length} game/type groups): ${n - bad} of ${n} draw the full card page with the same price as their HTML, one address tag, no errors`);
  await browser.close(); process.exit(bad ? 1 : 0);
})();
