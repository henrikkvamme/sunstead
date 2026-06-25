---
theme: default
title: Sanitas
info: Hackathon pitch deck for Sanitas medicine supply risk.
class: sanitas-deck
transition: fade
drawings:
  enabled: false
mdc: true
canvasWidth: 1280
aspectRatio: 16/9
fonts:
  sans: Inter
  mono: Roboto Mono
---

<style>
:root {
  color: #f4f4f4;
  background: #050505;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  letter-spacing: 0;
}

.slidev-layout {
  width: 100%;
  height: 100%;
  padding: 0;
  background:
    radial-gradient(circle at 18% 18%, rgb(255 90 10 / 12%), transparent 18rem),
    radial-gradient(circle at 84% 28%, rgb(92 213 255 / 10%), transparent 17rem),
    #050505;
  color: #f4f4f4;
}

.slide {
  display: grid;
  width: 100%;
  height: 100%;
  grid-template-rows: 64px minmax(0, 1fr) 48px;
  gap: 18px;
  padding: 34px 42px 28px;
}

.topbar,
.footer {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  color: #9d9d9d;
  font-family: "Roboto Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  text-transform: uppercase;
}

.brand {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
  color: #f4f4f4;
}

.brand img {
  width: 34px;
  height: 34px;
  object-fit: contain;
}

.content {
  display: grid;
  min-height: 0;
  align-content: center;
  gap: 28px;
}

.split {
  display: grid;
  min-height: 0;
  grid-template-columns: minmax(0, 0.95fr) minmax(420px, 1.05fr);
  gap: 28px;
  align-items: center;
}

.hero-title,
.title {
  max-width: 840px;
  margin: 0;
  color: #f4f4f4;
  font-size: 72px;
  font-weight: 520;
  letter-spacing: 0;
  line-height: 0.96;
}

.hero-title {
  max-width: 760px;
  font-size: 82px;
}

.lead {
  max-width: 760px;
  margin: 0;
  color: #b8b8b8;
  font-size: 28px;
  line-height: 1.22;
}

.tag {
  display: inline-flex;
  width: fit-content;
  align-items: center;
  border: 1px solid rgb(255 90 10 / 64%);
  border-radius: 999px;
  background: rgb(255 90 10 / 10%);
  padding: 8px 12px;
  color: #ff8a3d;
  font-family: "Roboto Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  font-weight: 650;
  text-transform: uppercase;
}

.panel {
  border: 1px solid #282828;
  border-radius: 14px;
  background:
    linear-gradient(180deg, rgb(255 255 255 / 4%), transparent 10rem),
    rgb(13 13 13 / 92%);
  box-shadow: 0 24px 80px rgb(0 0 0 / 34%);
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  overflow: hidden;
  border: 1px solid #282828;
  border-radius: 14px;
  background: #282828;
}

.metric {
  display: grid;
  min-height: 150px;
  align-content: space-between;
  gap: 18px;
  background: rgb(8 8 8 / 96%);
  padding: 20px;
}

.metric strong {
  color: #f4f4f4;
  font-size: 42px;
  font-weight: 480;
  line-height: 1;
}

.metric span,
.metric p {
  margin: 0;
  color: #9d9d9d;
  font-size: 15px;
  line-height: 1.34;
}

.graph-shell {
  display: grid;
  min-height: 510px;
  grid-template-rows: 82px minmax(0, 1fr);
  overflow: hidden;
}

.graph-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 18px;
  border-bottom: 1px solid #282828;
  padding: 18px 20px;
}

.graph-head h2 {
  margin: 4px 0 0;
  color: #f4f4f4;
  font-size: 21px;
  font-weight: 480;
}

.graph-head p,
.mini-label {
  margin: 0;
  color: #ff5a0a;
  font-family: "Roboto Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 12px;
  text-transform: uppercase;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.filters span {
  border: 1px solid #2f2f2f;
  border-radius: 999px;
  background: #101010;
  padding: 6px 9px;
  color: #b8b8b8;
  font-size: 12px;
}

.graph-canvas {
  position: relative;
  min-height: 0;
  background:
    radial-gradient(circle at 18% 45%, rgb(255 90 10 / 13%), transparent 14rem),
    radial-gradient(circle at 78% 22%, rgb(92 213 255 / 10%), transparent 12rem),
    linear-gradient(rgb(255 255 255 / 3%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(255 255 255 / 3%) 1px, transparent 1px),
    #080808;
  background-size: auto, auto, 56px 56px, 56px 56px, auto;
}

.graph-canvas svg {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}

.edge {
  fill: none;
  stroke: #56666a;
  stroke-linecap: round;
  stroke-width: 3;
  opacity: 0.46;
}

.edge.hot {
  filter: drop-shadow(0 0 8px rgb(255 90 10 / 76%));
  stroke: #ff5a0a;
  stroke-width: 6;
  opacity: 0.95;
}

.edge.context {
  stroke: #ff8a3d;
  opacity: 0.58;
}

.node {
  position: absolute;
  display: grid;
  width: 178px;
  min-height: 72px;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 6px 9px;
  align-items: center;
  border: 1px solid #3a3a3a;
  border-radius: 10px;
  background: rgb(13 13 13 / 96%);
  padding: 10px;
  box-shadow: 0 18px 50px rgb(0 0 0 / 38%);
}

.node .icon {
  display: grid;
  width: 30px;
  height: 30px;
  grid-row: span 2;
  place-items: center;
  border-radius: 8px;
  background: #171717;
  color: #9f9f9f;
  font-size: 14px;
}

.node strong {
  min-width: 0;
  overflow-wrap: anywhere;
  color: #f4f4f4;
  font-size: 15px;
  font-weight: 520;
  line-height: 1.08;
}

.node small {
  min-width: 0;
  color: #999;
  font-size: 11px;
  line-height: 1.18;
}

.node.hot {
  border-color: rgb(255 90 10 / 78%);
  background: linear-gradient(180deg, rgb(255 90 10 / 16%), transparent), #0f0f0f;
  box-shadow:
    0 0 0 1px rgb(255 90 10 / 18%),
    0 18px 55px rgb(255 90 10 / 13%);
}

.node.hot .icon {
  color: #ff5a0a;
}

.n-med { left: 38px; top: 154px; }
.n-fda { left: 294px; top: 104px; }
.n-supplier { left: 540px; top: 154px; }
.n-gmp { left: 790px; top: 104px; }
.n-api { left: 302px; top: 292px; }
.n-source { left: 788px; top: 294px; }

.side-panel {
  display: grid;
  gap: 12px;
  padding: 16px;
}

.side-panel h3 {
  margin: 0;
  color: #f4f4f4;
  font-size: 24px;
  font-weight: 500;
}

.risk-score {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 16px;
  align-items: center;
  border: 1px solid rgb(255 90 10 / 38%);
  border-radius: 10px;
  background: rgb(255 90 10 / 9%);
  padding: 14px;
}

.risk-score strong {
  color: #ff5a0a;
  font-size: 42px;
  font-weight: 520;
  line-height: 1;
}

.risk-score span,
.side-panel p {
  margin: 0;
  color: #b8b8b8;
  font-size: 16px;
  line-height: 1.36;
}

.chips {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.chip {
  display: grid;
  min-height: 72px;
  align-content: center;
  gap: 5px;
  border: 1px solid #2d2d2d;
  border-radius: 9px;
  background: #101010;
  padding: 10px;
}

.chip span {
  color: #ff8a3d;
  font-family: "Roboto Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 10px;
  text-transform: uppercase;
}

.chip strong {
  color: #f4f4f4;
  font-size: 13px;
  font-weight: 520;
  line-height: 1.16;
}

.flow {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.flow-card {
  display: grid;
  min-height: 168px;
  align-content: space-between;
  border: 1px solid #282828;
  border-radius: 12px;
  background: rgb(13 13 13 / 92%);
  padding: 16px;
}

.flow-card span {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 999px;
  background: rgb(255 90 10 / 13%);
  color: #ff8a3d;
  font-family: "Roboto Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
}

.flow-card strong {
  color: #f4f4f4;
  font-size: 21px;
  font-weight: 520;
  line-height: 1.12;
}

.flow-card p {
  margin: 0;
  color: #9d9d9d;
  font-size: 14px;
  line-height: 1.28;
}

.report-card {
  display: grid;
  max-width: 760px;
  gap: 14px;
  border: 1px solid rgb(92 213 255 / 34%);
  border-radius: 14px;
  background:
    radial-gradient(circle at 14% 20%, rgb(255 90 10 / 14%), transparent 8rem),
    #101010;
  padding: 24px;
}

.report-card strong {
  color: #ff8a3d;
  font-family: "Roboto Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  text-transform: uppercase;
}

.report-card p {
  margin: 0;
  color: #f4f4f4;
  font-size: 28px;
  line-height: 1.2;
}

.stack {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.stack span {
  border: 1px solid #2f2f2f;
  border-radius: 999px;
  background: #101010;
  padding: 9px 12px;
  color: #d6d6d6;
  font-family: "Roboto Mono", ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
}
</style>

<section class="slide">
  <header class="topbar">
    <div class="brand">
      <img src="../logo-candidates/sanitas-logo-4-compact-orbit-transparent.png" alt="">
      <span>Sanitas</span>
    </div>
    <span>Hackathon pitch</span>
  </header>
  <main class="content">
    <span class="tag">Medicine supply risk</span>
    <h1 class="hero-title">Find the shortage before the patient feels it.</h1>
    <p class="lead">A hospital dashboard that maps medicine supply risk, evidence, and the next action.</p>
  </main>
  <footer class="footer">
    <span>Cisplatin demo</span>
    <span>Built for hospital pharmacy teams</span>
  </footer>
</section>

---

<section class="slide">
  <header class="topbar">
    <div class="brand">
      <img src="../logo-candidates/sanitas-logo-4-compact-orbit-transparent.png" alt="">
      <span>Sanitas</span>
    </div>
    <span>The pain</span>
  </header>
  <main class="split">
    <div class="content">
      <span class="tag">Problem</span>
      <h2 class="title">Hospitals see shortages too late.</h2>
      <p class="lead">The ordering screen fails after the risk has already moved through suppliers, ingredients, and manufacturing events.</p>
    </div>
    <div class="metric-grid">
      <article class="metric">
        <span>Patient story</span>
        <strong>1 drug</strong>
        <p>Cisplatin Injection, needed for cancer treatment.</p>
      </article>
      <article class="metric">
        <span>Signal</span>
        <strong>FDA</strong>
        <p>Current shortage evidence anchors the graph.</p>
      </article>
      <article class="metric">
        <span>Goal</span>
        <strong>Early</strong>
        <p>Spot the supply path before treatment is delayed.</p>
      </article>
    </div>
  </main>
  <footer class="footer">
    <span>The patient is narration</span>
    <span>The graph models supply risk</span>
  </footer>
</section>

---

<section class="slide">
  <header class="topbar">
    <div class="brand">
      <img src="../logo-candidates/sanitas-logo-4-compact-orbit-transparent.png" alt="">
      <span>Sanitas</span>
    </div>
    <span>Product view</span>
  </header>
  <main class="content">
    <span class="tag">Dashboard</span>
    <h2 class="title">A digital twin of medicine supply chains.</h2>
    <div class="flow">
      <article class="flow-card">
        <span>01</span>
        <strong>Medicines</strong>
        <p>Start from the hospital portfolio.</p>
      </article>
      <article class="flow-card">
        <span>02</span>
        <strong>Suppliers</strong>
        <p>Map manufacturers and source evidence.</p>
      </article>
      <article class="flow-card">
        <span>03</span>
        <strong>Events</strong>
        <p>Connect shortages, quality constraints, and delays.</p>
      </article>
      <article class="flow-card">
        <span>04</span>
        <strong>Action</strong>
        <p>Open the path that needs attention.</p>
      </article>
    </div>
  </main>
  <footer class="footer">
    <span>Fast to scan</span>
    <span>Evidence-backed</span>
  </footer>
</section>

---

<section class="slide">
  <header class="topbar">
    <div class="brand">
      <img src="../logo-candidates/sanitas-logo-4-compact-orbit-transparent.png" alt="">
      <span>Sanitas</span>
    </div>
    <span>Demo graph</span>
  </header>
  <main class="split">
    <div class="graph-shell panel">
      <div class="graph-head">
        <div>
          <p>Supply graph</p>
          <h2>Cisplatin Injection</h2>
        </div>
        <div class="filters">
          <span>Critical</span>
          <span>Evidence</span>
          <span>Suppliers</span>
        </div>
      </div>
      <div class="graph-canvas">
        <svg viewBox="0 0 1000 390" aria-hidden="true">
          <path class="edge hot" d="M175 188 C235 142 285 126 370 132" />
          <path class="edge hot" d="M468 142 C525 158 560 188 620 192" />
          <path class="edge hot" d="M718 188 C774 148 805 126 876 132" />
          <path class="edge context" d="M175 222 C250 300 340 332 430 320" />
          <path class="edge" d="M718 226 C780 292 830 322 876 322" />
        </svg>
        <div class="node hot n-med">
          <span class="icon">Rx</span>
          <strong>Cisplatin Injection</strong>
          <small>Medicine, risk 87</small>
        </div>
        <div class="node hot n-fda">
          <span class="icon">!</span>
          <strong>FDA current shortage</strong>
          <small>Primary signal</small>
        </div>
        <div class="node hot n-supplier">
          <span class="icon">M</span>
          <strong>Accord / Intas</strong>
          <small>Supplier path</small>
        </div>
        <div class="node hot n-gmp">
          <span class="icon">Q</span>
          <strong>GMP compliance</strong>
          <small>Quality constraint</small>
        </div>
        <div class="node n-api">
          <span class="icon">API</span>
          <strong>Platinum API</strong>
          <small>Context risk</small>
        </div>
        <div class="node n-source">
          <span class="icon">S</span>
          <strong>Times of India</strong>
          <small>New evidence</small>
        </div>
      </div>
    </div>
    <aside class="side-panel panel">
      <p class="mini-label">Selected node</p>
      <h3>FDA current shortage</h3>
      <div class="risk-score">
        <strong>90</strong>
        <span>Primary evidence confirms the active shortage signal.</span>
      </div>
      <div class="chips">
        <div class="chip">
          <span>Primary</span>
          <strong>FDA shortage page</strong>
        </div>
        <div class="chip">
          <span>Clinical</span>
          <strong>ASHP shortage detail</strong>
        </div>
        <div class="chip">
          <span>Supplier</span>
          <strong>Accord / Intas</strong>
        </div>
        <div class="chip">
          <span>Context</span>
          <strong>API report</strong>
        </div>
      </div>
    </aside>
  </main>
  <footer class="footer">
    <span>One red path</span>
    <span>All nodes remain explainable</span>
  </footer>
</section>

---

<section class="slide">
  <header class="topbar">
    <div class="brand">
      <img src="../logo-candidates/sanitas-logo-4-compact-orbit-transparent.png" alt="">
      <span>Sanitas</span>
    </div>
    <span>Agent</span>
  </header>
  <main class="content">
    <span class="tag">Click investigate</span>
    <h2 class="title">The agent turns the graph into a hospital handoff.</h2>
    <div class="flow">
      <article class="flow-card">
        <span>01</span>
        <strong>Inspect FDA evidence</strong>
        <p>Start from the mapped shortage node.</p>
      </article>
      <article class="flow-card">
        <span>02</span>
        <strong>Check supplier constraint</strong>
        <p>Read the Accord / Intas path.</p>
      </article>
      <article class="flow-card">
        <span>03</span>
        <strong>Add one source</strong>
        <p>Attach the 2026 API context calmly.</p>
      </article>
      <article class="flow-card">
        <span>04</span>
        <strong>Prepare report</strong>
        <p>Evidence, risk path, and next checks.</p>
      </article>
    </div>
  </main>
  <footer class="footer">
    <span>Visible tool calls</span>
    <span>No treatment advice</span>
  </footer>
</section>

---

<section class="slide">
  <header class="topbar">
    <div class="brand">
      <img src="../logo-candidates/sanitas-logo-4-compact-orbit-transparent.png" alt="">
      <span>Sanitas</span>
    </div>
    <span>Output</span>
  </header>
  <main class="split">
    <div class="content">
      <span class="tag">Report ready</span>
      <h2 class="title">Short enough to use in a real supply meeting.</h2>
      <p class="lead">What changed, why it matters, which sources back it, and what the team should check next.</p>
    </div>
    <div class="report-card">
      <strong>Action needed</strong>
      <p>Prepare alternate supplier order. Verify approved supplier availability before stock drops below the safety threshold.</p>
    </div>
  </main>
  <footer class="footer">
    <span>Human decision stays with the hospital</span>
    <span>Sanitas prepares the context</span>
  </footer>
</section>

---

<section class="slide">
  <header class="topbar">
    <div class="brand">
      <img src="../logo-candidates/sanitas-logo-4-compact-orbit-transparent.png" alt="">
      <span>Sanitas</span>
    </div>
    <span>Why now</span>
  </header>
  <main class="content">
    <span class="tag">Build path</span>
    <h2 class="title">Six months gets this into pilot shape.</h2>
    <p class="lead">Connect live data, expand the graph, and test the workflow with hospital supply teams.</p>
    <div class="stack">
      <span>Kafka</span>
      <span>Neo4j</span>
      <span>Aiven</span>
      <span>Claude managed agents</span>
      <span>Research-backed graph scoring</span>
    </div>
  </main>
  <footer class="footer">
    <span>We can ship this</span>
    <span>Sanitas</span>
  </footer>
</section>
