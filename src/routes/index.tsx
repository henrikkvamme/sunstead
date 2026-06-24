import { createFileRoute } from "@tanstack/react-router";
import {
  ArrowRight,
  Braces,
  Check,
  ChevronDown,
  Copy,
  FileJson,
  Github,
  MousePointer2,
  Search,
  Sparkles,
  Zap,
} from "lucide-react";

import {
  BrowserFrame,
  Button,
  CodePanel,
  FAQItem,
  FeatureCard,
  LogoMark,
  MiniMetric,
  SectionHeader,
} from "#/ui";

export const Route = createFileRoute("/")({
  component: Home,
});

const navItems = ["Products", "Resources", "Pricing", "Docs", "Blog", "Playground"];

const codeLines = [
  "[",
  "  {",
  '    "url": "https://source.example/report",',
  '    "markdown": "# Market signal\\nClean content...",',
  '    "json": { "title": "Agent-ready context" },',
  '    "screenshot": "capture-2026.png"',
  "  }",
  "]",
];

const products = [
  {
    icon: Search,
    title: "Search",
    text: "Find high-signal sources and return the full context behind every result.",
  },
  {
    icon: FileJson,
    title: "Scrape",
    text: "Turn any page into clean markdown, JSON, links, screenshots, and metadata.",
  },
  {
    icon: MousePointer2,
    title: "Interact",
    text: "Let agents click, wait, navigate, and extract from dynamic web apps.",
  },
];

const agentSteps = [
  "Connect the SDK",
  "Choose a source",
  "Return structured context",
  "Ship the workflow",
];

const hardStuff = [
  "JavaScript rendering",
  "Proxy rotation",
  "Rate limits",
  "Schema extraction",
  "Change detection",
  "Queued batches",
];

const solutions = [
  ["Sales intelligence", "Find accounts", "Enrich profiles", "Monitor signals"],
  ["Research agents", "Collect papers", "Compare sources", "Summarize evidence"],
  ["Operations", "Track vendors", "Read portals", "Trigger workflows"],
  ["Knowledge bases", "Crawl docs", "Normalize markdown", "Sync updates"],
];

const faqs = [
  {
    question: "What can I build with this interface?",
    answer:
      "Agent research tools, live web monitors, knowledge-base ingestion, competitive intelligence, and structured extraction flows.",
  },
  {
    question: "Does the layout work on mobile?",
    answer:
      "Yes. The desktop grids collapse to focused single-column sections while preserving the same controls, spacing rhythm, and visual language.",
  },
  {
    question: "Is this an exact Firecrawl copy?",
    answer:
      "It is a close visual study of the layout system, spacing, component shapes, and orange-accent identity, with original naming and copy.",
  },
  {
    question: "Can this become a full component library?",
    answer:
      "Yes. The page is built from reusable primitives so we can keep adding Storybook stories and interaction states without rewriting the page.",
  },
];

function Home() {
  return (
    <main className="site-shell">
      <div className="announcement">
        <span>Introducing Sunstead Research Index, specialized context for agent workflows.</span>
        <a href="#solutions">Try it now -&gt;</a>
      </div>

      <header className="site-header">
        <nav className="nav-container" aria-label="Primary navigation">
          <LogoMark />
          <div className="nav-links">
            {navItems.map((item) => (
              <a href={`#${item.toLowerCase()}`} key={item}>
                {item}
                {item === "Products" || item === "Resources" ? (
                  <ChevronDown aria-hidden size={13} />
                ) : null}
              </a>
            ))}
          </div>
          <div className="nav-actions">
            <a className="github-stat" href="https://github.com" aria-label="GitHub stars">
              <Github aria-hidden size={17} />
              138.5K
            </a>
            <Button href="#signup" size="sm">
              Sign up
            </Button>
          </div>
        </nav>
      </header>

      <section className="hero-section">
        <div className="grid-backdrop" aria-hidden>
          <span className="grid-label grid-label-left">[ 200 OK ]</span>
          <span className="grid-label grid-label-right">[ SCRAPE ]</span>
          <span className="grid-label grid-label-bottom-left">[ .JSON ]</span>
          <span className="grid-label grid-label-bottom-right">[ .MD ]</span>
          <span className="spark spark-one" />
          <span className="spark spark-two" />
        </div>

        <div className="hero-copy">
          <a className="promo-pill" href="#pricing">
            2 Months Free - Annually
            <span>
              <ArrowRight aria-hidden size={14} />
            </span>
          </a>
          <h1>
            Power every agent with
            <br />
            <span>clean web context</span>
          </h1>
          <p>
            The complete toolkit to search, scrape, and interact with the web at scale.{" "}
            <a href="#open-source">It is also open source.</a>
          </p>
          <div className="hero-actions">
            <Button href="#signup" size="lg" variant="primary">
              Start for free
            </Button>
            <Button href="#agents" icon={<Copy aria-hidden size={17} />} size="lg">
              Setup for agents
            </Button>
          </div>
        </div>

        <BrowserFrame className="hero-browser">
          <div className="scrape-demo">
            <div className="scrape-form">
              <div className="fake-row">
                <div className="fake-avatar" />
                <span className="fake-input fake-input-short" />
                <span className="fake-tag">A--0</span>
              </div>
              <div className="fake-row fake-row-wrap">
                <span className="fake-input" />
                <span className="fake-input fake-input-medium" />
              </div>
              <span className="fake-input fake-input-wide" />
              <div className="fake-toolbar-row">
                <span />
                <span />
                <span />
                <span />
              </div>
              <span className="fake-line" />
              <span className="fake-line fake-line-short" />
              <span className="fake-button" />
            </div>
            <div className="result-pane">
              <div className="result-toolbar">
                <span />
                <span />
                <span />
                <strong>[ .JSON ]</strong>
              </div>
              <CodePanel lines={codeLines} />
              <div className="scraping-pill">
                <Sparkles aria-hidden size={14} />
                Scraping ...
              </div>
            </div>
          </div>
        </BrowserFrame>
      </section>

      <section className="logo-strip" aria-label="Customer logos">
        {["Mercury", "Raycast", "Cal.com", "Cursor", "Zapier"].map((name) => (
          <span key={name}>{name}</span>
        ))}
      </section>

      <section className="section-block" id="products">
        <SectionHeader
          eyebrow="Developer first"
          title={<TitleAccent before="Start" accent="scraping" after="today" />}
        >
          Infrastructure that helps AI find, read, and act on the live web.
        </SectionHeader>

        <div className="product-grid">
          {products.map((product) => {
            const Icon = product.icon;

            return (
              <FeatureCard key={product.title} title={product.title}>
                <Icon aria-hidden size={18} />
                {product.text}
              </FeatureCard>
            );
          })}
        </div>

        <div className="code-workbench">
          <div className="workbench-tabs">
            <button type="button">Search</button>
            <button className="active" type="button">
              Scrape
            </button>
            <button type="button">Interact</button>
          </div>
          <CodePanel
            lines={[
              "import { Sunstead } from '@sunstead/sdk';",
              "const app = new Sunstead({ apiKey });",
              "",
              "const page = await app.scrape('https://example.com');",
              "return page.markdown;",
            ]}
          />
          <div className="output-card">
            <strong>Output</strong>
            <p>Clean markdown, screenshots, links, and typed fields in one response.</p>
          </div>
        </div>
      </section>

      <section className="section-block" id="agents">
        <SectionHeader
          eyebrow="Agents"
          title={<TitleAccent before="Easily connect with your" accent="AI agents" />}
        >
          Feed browser-grade context into the tools your agents already use.
        </SectionHeader>
        <div className="agent-grid">
          {agentSteps.map((step, index) => (
            <article className="agent-card" key={step}>
              <span>{String(index + 1).padStart(2, "0")}</span>
              <h3>{step}</h3>
              <p>
                {index === 0
                  ? "Install the SDK or call the API directly."
                  : "Keep the workflow deterministic, inspectable, and easy to retry."}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section className="section-block" id="open-source">
        <SectionHeader
          eyebrow="Open source"
          title={
            <TitleAccent
              before="Fast, reliable, and token-efficient. And it is"
              accent="open source"
            />
          }
        >
          Designed for teams that need web context without brittle scraping pipelines.
        </SectionHeader>
        <div className="opensource-grid">
          <FeatureCard title="Built for production">
            <Zap aria-hidden size={18} />
            Queues, retries, observability, and clean outputs are treated as core product surfaces.
          </FeatureCard>
          <div className="metrics-panel">
            <MiniMetric label="Requests served" value="2.8B" />
            <MiniMetric label="Median parse time" value="1.2s" />
            <MiniMetric label="Schema accuracy" value="99.2%" />
          </div>
          <FeatureCard title="Agent-native outputs">
            <Braces aria-hidden size={18} />
            Return markdown, JSON, screenshots, links, actions, and citations in the same flow.
          </FeatureCard>
        </div>
      </section>

      <section className="section-block">
        <SectionHeader
          eyebrow="Scale"
          title={<TitleAccent before="We handle the" accent="hard stuff" />}
        >
          Browser automation and extraction details disappear behind one clean interface.
        </SectionHeader>
        <div className="hard-grid">
          {hardStuff.map((item) => (
            <div className="hard-card" key={item}>
              <Check aria-hidden size={16} />
              <span>{item}</span>
            </div>
          ))}
        </div>
        <div className="flow-diagram" aria-label="Processing pipeline">
          <span>URL</span>
          <ArrowRight aria-hidden />
          <span className="hot">Sunstead</span>
          <ArrowRight aria-hidden />
          <span>Markdown</span>
          <ArrowRight aria-hidden />
          <span>Agent</span>
        </div>
      </section>

      <section className="section-block" id="solutions">
        <SectionHeader
          eyebrow="Solutions"
          title={<TitleAccent before="Transform web data into" accent="AI-powered solutions" />}
        >
          A simple product surface for the workflows teams keep rebuilding.
        </SectionHeader>
        <div className="solutions-layout">
          <aside>
            {solutions.map(([name], index) => (
              <button className={index === 0 ? "active" : ""} key={name} type="button">
                {name}
              </button>
            ))}
          </aside>
          <div className="solution-table">
            {solutions.map((row) => (
              <div className="solution-row" key={row[0]}>
                {row.map((cell, index) => (
                  <span key={cell} className={index === 0 ? "solution-name" : ""}>
                    {cell}
                  </span>
                ))}
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section-block testimonials">
        <SectionHeader
          eyebrow="Wall of love"
          title={<TitleAccent before="People love building with" accent="Sunstead" />}
        >
          Small primitives, sturdy outputs, and fewer fragile scraping scripts.
        </SectionHeader>
        <div className="testimonial-grid">
          {[
            "The first API we reach for when an agent needs reliable live context.",
            "It turned a week of extraction work into a single afternoon.",
            "The output is clean enough to feed directly into evals and research flows.",
          ].map((quote, index) => (
            <blockquote key={quote}>
              <p>{quote}</p>
              <footer>Builder {index + 1}</footer>
            </blockquote>
          ))}
        </div>
      </section>

      <section className="section-block faq-section" id="resources">
        <SectionHeader
          eyebrow="FAQ"
          title={<TitleAccent before="Frequently asked" accent="questions" />}
        />
        <div className="faq-list">
          {faqs.map((item) => (
            <FAQItem answer={item.answer} key={item.question} question={item.question} />
          ))}
        </div>
      </section>

      <footer className="site-footer">
        <div>
          <LogoMark />
          <p>Clean context for AI agents and product teams.</p>
        </div>
        <div className="footer-columns">
          {["Products", "Resources", "Company", "Legal"].map((heading) => (
            <div key={heading}>
              <h3>{heading}</h3>
              <a href="/">Overview</a>
              <a href="/">Docs</a>
              <a href="/">Changelog</a>
              <a href="/">Contact</a>
            </div>
          ))}
        </div>
      </footer>
    </main>
  );
}

function TitleAccent({
  accent,
  after,
  before,
}: {
  accent: string;
  after?: string;
  before: string;
}) {
  return (
    <>
      {before} <span>{accent}</span>
      {after ? ` ${after}` : null}
    </>
  );
}
