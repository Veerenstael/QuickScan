// ===== Backend-basis: robuuste detectie + fallback =====
// Volgorde:
// 1) window.QUICKSCAN_BACKEND (zonder trailing slash)
// 2) localhost fallback (voor lokale ontwikkeling)
// 3) Productie fallback: jouw Render-URL
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

  // verwijder trailing slashes
  base = base.replace(/\/+$/, "");

  // valideer URL
  try {
    // Als dit faalt zat er iets als "https://" of "veerenstael..." zonder schema
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
  // Toon nette melding in de UI; formulier blijft zichtbaar
  const res = document.getElementById("result");
  if (res) {
    res.innerHTML = `
      <div class="result-block">
        <h2>Er ging iets mis</h2>
        <p><strong>Configuratiefout</strong><br/>${e.message}</p>
      </div>
    `;
  }
  // Laat een veilige default staan zodat de rest van het script blijft werken
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

// Helpers
function createOption(v) {
  const o = document.createElement("option");
  o.value = String(v);
  o.textContent = String(v);
  return o;
}

// Dynamisch de vragen inladen (textarea + score 1–5 + hidden label)
const qContainer = document.getElementById("questions");
Object.entries(QUESTIONS).forEach(([section, qs]) => {
  const h3 = document.createElement("h3");
  h3.innerText = section;
  qContainer.appendChild(h3);

  qs.forEach((q, i) => {
    const label = document.createElement("label");
    label.innerText = q;

    const textarea = document.createElement("textarea");
    const baseName = `${section}_${i}`;
    textarea.name = `${baseName}_answer`;
    textarea.rows = 3;
    textarea.style.width = "100%";

    const hiddenLabel = document.createElement("input");
    hiddenLabel.type = "hidden";
    hiddenLabel.name = `${baseName}_label`;
    hiddenLabel.value = q;

    const scoreLabel = document.createElement("div");
    scoreLabel.className = "score-row";
    const scoreText = document.createElement("span");
    scoreText.textContent = "Uw cijfer (1–5):";
    const select = document.createElement("select");
    select.name = `${baseName}_customer_score`;
    select.appendChild(new Option("-", ""));
    [1,2,3,4,5].forEach(v => select.appendChild(createOption(v)));
    scoreLabel.appendChild(scoreText);
    scoreLabel.appendChild(select);

    qContainer.appendChild(label);
    qContainer.appendChild(textarea);
    qContainer.appendChild(hiddenLabel);
    qContainer.appendChild(scoreLabel);
  });
});

// Intro-tekst ook meesturen zodat deze in de PDF komt
const introEl = document.getElementById("intro");

// UI error helper
function showError(where, msg) {
  document.getElementById("result").innerHTML = `
    <div class="result-block">
      <h2>Er ging iets mis</h2>
      <p>${where ? `<strong>${where}</strong><br/>` : ""}${msg}</p>
    </div>
  `;
}

document.getElementById("quickscan-form").addEventListener("submit", async (e) => {
  e.preventDefault();

  const formData = new FormData(e.target);
  const data = Object.fromEntries(formData.entries());

  if (introEl) {
    const p = introEl.querySelector("p");
    data.introText = p ? p.innerText : "";
  }

  const submitUrl = `${BACKEND_BASE}/submit`;

  try {
    const res = await fetch(submitUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });

    let payload;
    try {
      payload = await res.json();
    } catch {
      payload = {};
    }

    if (!res.ok) {
      const msg = payload && payload.error ? payload.error : `HTTP ${res.status}`;
      showError("Backend-response", msg);
      return;
    }

    document.getElementById("result").innerHTML = `
      <div class="result-block">
        <h2>Resultaten QuickScan</h2>
        <p><strong>Gemiddeld cijfer AI:</strong> ${payload.total_score_ai ?? "-"}</p>
        <p><strong>Gemiddeld cijfer klant:</strong> ${payload.total_score_customer || "-"}</p>
        <p><strong>Samenvatting:</strong><br/>${payload.summary || "-"}</p>
        <p>${payload.email_sent ? "Het PDF-rapport is per e-mail verzonden." : "E-mail verzenden is overgeslagen (geen e-mailconfig gevonden). Het rapport is lokaal op de server opgeslagen als quickscan.pdf."}</p>
      </div>
    `;
  } catch (err) {
    showError("Netwerkfout", String(err));
    console.error(err);
  }
});
