// Mejoras progresivas: la app funciona sin JavaScript; esto solo agrega comodidad.
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

// Evita doble clic en botones de envío (reservas duplicadas).
document.addEventListener("submit", (e) => {
  const f = e.target;
  if (f.dataset.sent) { e.preventDefault(); return; }
  f.dataset.sent = "1";
  f.querySelectorAll("button[type=submit]").forEach((b) => { b.style.opacity = ".7"; });
  setTimeout(() => { delete f.dataset.sent; }, 4000);
});

// Tamaño de letra (A+): pequeño -> normal -> grande. Se recuerda en este dispositivo.
(() => {
  const btn = document.getElementById("tsz");
  if (!btn) return;
  const order = ["", "lg", "sm"]; // "" = normal
  btn.addEventListener("click", () => {
    const cur = document.documentElement.dataset.size || "";
    const next = order[(order.indexOf(cur) + 1) % order.length];
    if (next) document.documentElement.dataset.size = next; else delete document.documentElement.dataset.size;
    try { localStorage.setItem("miyjo-size", next); } catch (e) {}
  });
})();

// Intereses: máximo 3, y "No sé, muéstrame variedad" excluye al resto.
document.querySelectorAll("[data-max]").forEach((group) => {
  const max = +group.dataset.max, anyVal = group.dataset.any;
  const boxes = [...group.querySelectorAll("input[type=checkbox]")];
  const anyBox = boxes.find((b) => b.value === anyVal), real = boxes.filter((b) => b !== anyBox);
  const sync = () => {
    const n = real.filter((b) => b.checked).length;
    real.forEach((b) => { b.disabled = !b.checked && (n >= max || (anyBox && anyBox.checked)); });
  };
  boxes.forEach((b) => b.addEventListener("change", () => {
    if (b === anyBox && b.checked) real.forEach((x) => { x.checked = false; });
    if (b !== anyBox && b.checked && anyBox) anyBox.checked = false;
    sync();
  }));
  sync();
});

// Calculadora del modelo de negocio (panel de métricas).
const calc = document.getElementById("calc");
if (calc) {
  const v = (id) => parseFloat(calc.querySelector("#" + id).value) || 0;
  const money = (n) => "S/ " + Math.round(n).toLocaleString("es-PE");
  const run = () => {
    const fam = v("c-fam"), ticket = v("c-ticket"), com = v("c-com") / 100, churn = v("c-churn") / 100;
    const cac = v("c-cac"), prov = v("c-prov"), sub = v("c-sub"), fixed = v("c-fixed");
    const mrr = fam * ticket * com + prov * sub;
    const ltv = churn > 0 ? (ticket * com) / churn : 0;
    const out = {
      "o-mrr": money(mrr), "o-arr": money(mrr * 12), "o-ltv": money(ltv),
      "o-ratio": cac > 0 ? (ltv / cac).toFixed(1) + "x" : "—",
      "o-pay": ticket * com > 0 ? Math.ceil(cac / (ticket * com)) + " meses" : "—",
      "o-be": ticket * com > 0 ? Math.ceil((fixed - prov * sub) / (ticket * com)) + " familias" : "—",
      "o-life": churn > 0 ? (1 / churn).toFixed(1) + " meses" : "—",
    };
    for (const k in out) calc.querySelector("#" + k).textContent = out[k];
  };
  calc.addEventListener("input", run);
  run();
}
