import type { Meta, StoryObj } from "@storybook/react-vite";
import { Copy, Search } from "lucide-react";

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

const meta = {
  title: "UI/Firecrawl Study",
  parameters: {
    docs: {
      description: {
        component:
          "A focused component set for the Firecrawl-inspired Sunstead landing page: heat accent, pale canvas, thin borders, compact controls, and code-forward panels.",
      },
    },
  },
} satisfies Meta;

export default meta;

type Story = StoryObj<typeof meta>;

export const ComponentSet: Story = {
  render: () => (
    <main className="story-page">
      <section className="story-grid">
        <div className="story-row">
          <LogoMark />
          <Button href="#">Sign up</Button>
          <Button href="#" variant="primary">
            Start for free
          </Button>
          <Button href="#" icon={<Copy aria-hidden size={16} />} size="lg">
            Setup for agents
          </Button>
        </div>

        <SectionHeader title={<span>Start scraping today</span>} eyebrow="Developer first">
          Reusable pieces for the landing-page rhythm.
        </SectionHeader>

        <div className="product-grid">
          <FeatureCard title="Search">
            <Search aria-hidden size={18} />
            Find high-signal sources and return the context behind each result.
          </FeatureCard>
          <FeatureCard title="Scrape">
            Return markdown, JSON, screenshots, links, and metadata.
          </FeatureCard>
          <FeatureCard title="Interact">
            Click, wait, navigate, and extract from dynamic pages.
          </FeatureCard>
        </div>

        <BrowserFrame>
          <CodePanel
            lines={[
              "[",
              "  {",
              '    "url": "https://source.example",',
              '    "markdown": "# Clean context"',
              "  }",
              "]",
            ]}
          />
        </BrowserFrame>

        <div className="metrics-panel">
          <MiniMetric label="Requests served" value="2.8B" />
          <MiniMetric label="Median parse time" value="1.2s" />
          <MiniMetric label="Schema accuracy" value="99.2%" />
        </div>

        <div className="faq-list">
          <FAQItem
            question="Can this become a full library?"
            answer="Yes. The page is built from focused primitives that can be expanded with more states and variants."
          />
        </div>
      </section>
    </main>
  ),
};
