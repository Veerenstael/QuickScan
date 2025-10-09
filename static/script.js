// ===== Backend-basis: detectie + fallback =====
function resolveBackendBase() {
  const raw = (typeof window !== "undefined" && window.QUICKSCAN_BACKEND != null)
    ? String(window.QUICKSCAN_BACKEND).trim()
    : "";

  let base = raw;
  if (!base) {
    if (location.hostname === "localhost" || location.hostname === "127.0.0.1") {
      base = "http://127.0.0.1:5000";
    } else {
      base = "https://veerenstael-quickscan-backend.onrender.com";
    }
  }
  base = base.replace(/\/+$/, "");
  try {
    const u = new URL(base);
    if (!u.protocol.startsWith("http")) throw new Error("Ongeldig protocol");
  } catch (e) {
    throw new Error(`Ongeldige QUICKSCAN_BACKEND basis-URL: "${base}".`);
  }
  return base;
}

let BACKEND_BASE;
try {
  BACKEND_BASE = resolveBackendBase();
} catch (e) {
  console.error(e);
  const res = document.getElementById("result");
  if (res) {
    res.removeAttribute("hidden");
    res.className = "result-block";
    res.innerHTML = `
      <h2>Er ging iets mis</h2>
      <p><strong>Configuratiefout</strong><br/>${e.message}</p>
    `;
  }
  BACKEND_BASE = "https://veerenstael-quickscan-backend.onrender.com";
}

// ===== Vragen =====
const QUESTIONS = {
  "Asset Management Strategie": [
    "Zijn rollen, verantwoordelijkheden en bevoegdheden binnen onderhoudsprocessen helder belegd (bijv. tussen opdrachtgever, werkvoorbereider, coördinator en monteurs)?",
    "Is het binnen de organisatie duidelijk welke technische doelen worden nagestreefd (denk aan SAMP, line-of-sight)?"
  ],
  "Werkvoorbereiding": [
    "Is er een actuele korte én lange termijn planning (tot 5 jaar) waarop onderhoudswerkzaamheden worden afgestemd?",
    "Zijn alle benodigde resources (mensen, materiaal, onderaannemers) tijdig inzichtelijk en beschikbaar voor de uitvoering?"
  ],
  "Uitvoering onderhoud": [
    "Zijn er duidelijke werkinstructies beschikbaar waarin kwaliteit geborgd is?",
    "Worden storingen en inspectieresultaten systematisch geregistreerd?"
  ],
  "Werk afhandelen en controleren": [
    "Wordt de kwaliteit van uitgevoerd werk (en dat van onderaannemers) structureel gecontroleerd en vastgelegd?",
    "Vindt er standaard evaluatie plaats om afwijkingen of restpunten op te volgen?"
  ],
  "Analyse gegevens": [
    "Worden prestaties van assets en onderhoud zichtbaar gemaakt met dashboards of rapportages?",
    "Worden terugkerende storingen en trendanalyses gebruikt om te verbeteren?"
  ],
  "Maintenance & Reliability Engineering": [
    "Is er een proces om technische risico’s en faalkosten in kaart te brengen en te beheersen (bijv. met RCM of LCC)?",
    "Worden onderhoudsplannen en sparepartsbeleid periodiek herzien?"
  ],
  "Inregelen onderhoudsplan": [
    "Zijn onderhoudsplannen geborgd in systemen (OMS/EAM) en worden deze periodiek herzien?",
    "Wordt er gewerkt met een continu verbeterproces (bijv. met PDCA) om plannen, SLA’s en KPI's bij te sturen?"
  ]
};

// ===== Helpers =====
function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.substring(2), v);
    else if (k === "html") node.innerHTML = v;
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child == null) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

// “Uw cijfer” met 5 klikbare bolletjes (1..5) met cijfers erin
function scoreDots(name, initial) {
  const wrap = el("div", { class: "score-dots" });
  const label = el("span", { class: "label" }, "Uw cijfer:");
  const dots = el("div", { class: "dots" });

  for (let i = 1; i <= 5; i++) {
    const id = `${name}_${i}`;
    const input = el("input", {
      type: "radio",
      id,
      name,
      value: String(i),
      ...(String(initial) === String(i) ? { checked: "checked" } : {})
    });
    const dot = el("label", { class: "dot", for: id, title: `Score ${i}`, "aria-label": `Score ${i}` }, String(i));
    dots.appendChild(input);
    dots.appendChild(dot);
  }

  wrap.appendChild(label);
  wrap.appendChild(dots);
  return wrap;
}

// Maak één vraagblok
function makeQuestion(section, qText, index) {
  const baseName = `${section}_${index}`;

  const label = document.createElement("label");
  label.innerText = qText;

  const textarea = document.createElement("textarea");
  textarea.name = `${baseName}_answer`;
  textarea.rows = 3;
  textarea.style.width = "100%";

  const hiddenLabel = document.createElement("input");
  hiddenLabel.type = "hidden";
  hiddenLabel.name = `${baseName}_label`;
  hiddenLabel.value = qText;

  const scoreName = `${baseName}_customer_score`;
  const dots = scoreDots(scoreName, "");

  return [label, textarea, hiddenLabel, dots];
}

// Dynamisch de vragen inladen
const qContainer = document.getElementById("questions");
Object.entries(QUESTIONS).forEach(([section, qs]) => {
  const h3 = document.createElement("h3");
  h3.innerText = section;
  qContainer.appendChild(h3);

  qs.forEach((q, i) => {
    const parts = makeQuestion(section, q, i);
    parts.forEach(elm => qContainer.appendChild(elm));
  });
});

// UI error helper
function showError(where, msg) {
  const res = document.getElementById("result");
  if (!res) return;
  res.removeAttribute("hidden");
  res.className = "result-block";
  res.innerHTML = `
    <h2>Er ging iets mis</h2>
    <p>${where ? `<strong>${where}</strong><br/>` : ""}${msg}</p>
  `;
}

document.getElementById("quickscan-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const formData = new FormData(e.target);
  const data = Object.fromEntries(formData.entries());

  const submitUrl = `${BACKEND_BASE}/submit`;

  try {
    const res = await fetch(submitUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });

    let payload = {};
    try { payload = await res.json(); } catch {}

    if (!res.ok) {
      const msg = payload && payload.error ? payload.error : `HTTP ${res.status}`;
      showError("Backend-response", msg);
      return;
    }

    const box = document.getElementById("result");
    if (box) {
      box.removeAttribute("hidden");
      box.className = "result-block";
      box.innerHTML = `
        <h2>Dank je wel!</h2>
        <p>De QuickScan is ontvangen.${payload.email_sent
          ? " Het PDF-rapport is per e-mail verzonden."
          : " E-mail verzenden is overgeslagen (geen e-mailconfig gevonden). Het rapport is lokaal op de server opgeslagen als quickscan.pdf."}
        </p>
      `;
    }
  } catch (err) {
    showError("Netwerkfout", String(err));
    console.error(err);
  }
});
