import { AbsoluteFill, Easing, interpolate, Sequence, useCurrentFrame } from "remotion";

const fps = 30;
const duration = 35 * fps;
const critical = "#ff4d5f";
const elevated = "#ffb020";
const stable = "#30d7a3";
const ink = "#f7fbff";
const muted = "rgba(223, 235, 255, 0.72)";
const panel = "rgba(10, 18, 31, 0.68)";
const border = "rgba(162, 188, 255, 0.22)";
const easeOut = Easing.bezier(0.16, 1, 0.3, 1);
const easeInOut = Easing.bezier(0.45, 0, 0.55, 1);

type Risk = "critical" | "elevated" | "stable" | "watch";

type ChainNode = {
  label: string;
  risk: Risk;
  x: number;
  y: number;
};

const chainNodes: ChainNode[] = [
  { label: "Carboplatin\nInjection", risk: "critical", x: 8, y: 50 },
  { label: "Platinum\nAPI", risk: "critical", x: 25, y: 33 },
  { label: "Accord /\nIntas", risk: "critical", x: 43, y: 43 },
  { label: "Gujarat\nsite", risk: "critical", x: 60, y: 35 },
  { label: "GMP\nconstraint", risk: "critical", x: 74, y: 52 },
  { label: "FDA + ASHP\nshortage", risk: "critical", x: 91, y: 42 },
  { label: "Hospital\npharmacy", risk: "watch", x: 86, y: 74 },
];

const branchNodes: ChainNode[] = [
  { label: "Demand\nincrease", risk: "elevated", x: 45, y: 75 },
  { label: "Shipping\ndelay", risk: "elevated", x: 63, y: 78 },
  { label: "Discontinued\npresentations", risk: "watch", x: 24, y: 72 },
  { label: "Platinum raw\nmaterial", risk: "elevated", x: 18, y: 16 },
];

const sourceCards = [
  {
    label: "FDA",
    title: "Current shortage",
    detail: "Supplier rows cite GMP compliance, demand, delays, and discontinued presentations.",
    risk: "critical" as Risk,
  },
  {
    label: "ASHP",
    title: "Clinical shortage detail",
    detail: "Hospital pharmacy context: usual ordering cannot be assumed available.",
    risk: "critical" as Risk,
  },
  {
    label: "2026 API signal",
    title: "New upstream signal",
    detail: "API pressure strengthens the explanation without overstating direct causality.",
    risk: "elevated" as Risk,
  },
];

const actionCards = [
  "Verify alternate presentations",
  "Prioritize high-risk orders",
  "Monitor supplier evidence",
  "Escalate before stockout",
];

function riskColor(risk: Risk) {
  if (risk === "critical") {
    return critical;
  }

  if (risk === "elevated") {
    return elevated;
  }

  if (risk === "stable") {
    return stable;
  }

  return "#8fb7ff";
}

function appear(frame: number, start: number, length = 24) {
  return interpolate(frame, [start, start + length], [0, 1], {
    easing: easeOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

function fadeOut(frame: number, start: number, length = 18) {
  return interpolate(frame, [start, start + length], [1, 0], {
    easing: Easing.in((value) => Easing.cubic(value)),
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
}

function sceneOpacity(frame: number, sceneDuration: number) {
  return appear(frame, 0, 22) * fadeOut(frame, sceneDuration - 18, 18);
}

function Background({ accent = "#2f83ff" }: { accent?: string }) {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill
      style={{
        backgroundColor: "#050813",
        backgroundImage: [
          `radial-gradient(circle at ${18 + frame * 0.018}% ${22 + frame * 0.01}%, ${accent}55 0, transparent 28%)`,
          `radial-gradient(circle at ${84 - frame * 0.012}% 74%, ${critical}33 0, transparent 26%)`,
          "linear-gradient(135deg, #081323 0%, #050813 42%, #0a1020 100%)",
        ].join(", "),
        overflow: "hidden",
      }}
    >
      <AbsoluteFill
        style={{
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.035) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.035) 1px, transparent 1px)",
          backgroundSize: "72px 72px",
          opacity: 0.32,
          translate: `${interpolate(frame, [0, duration], [-30, 10])}px ${interpolate(frame, [0, duration], [-10, 30])}px`,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(90deg, rgba(5,8,19,0.92), transparent 36%, transparent 64%, rgba(5,8,19,0.82))",
        }}
      />
    </AbsoluteFill>
  );
}

function SafeFrame({ children }: { children: React.ReactNode }) {
  return (
    <AbsoluteFill
      style={{
        padding: "100px 120px",
      }}
    >
      {children}
    </AbsoluteFill>
  );
}

function Kicker({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        color: muted,
        fontSize: 34,
        fontWeight: 700,
        letterSpacing: 0,
        textTransform: "uppercase",
      }}
    >
      {children}
    </div>
  );
}

function Headline({ children, size = 102 }: { children: React.ReactNode; size?: number }) {
  return (
    <div
      style={{
        color: ink,
        fontSize: size,
        fontWeight: 820,
        letterSpacing: 0,
        lineHeight: 0.94,
        maxWidth: 1180,
      }}
    >
      {children}
    </div>
  );
}

function Copy({ children, maxWidth = 780 }: { children: React.ReactNode; maxWidth?: number }) {
  return (
    <div
      style={{
        color: muted,
        fontSize: 43,
        fontWeight: 520,
        lineHeight: 1.2,
        maxWidth,
      }}
    >
      {children}
    </div>
  );
}

function RiskPill({ risk, label }: { label: string; risk: Risk }) {
  return (
    <div
      style={{
        alignItems: "center",
        background: `${riskColor(risk)}1f`,
        border: `1px solid ${riskColor(risk)}99`,
        borderRadius: 999,
        color: ink,
        display: "flex",
        fontSize: 30,
        fontWeight: 800,
        gap: 14,
        padding: "14px 22px",
        width: "fit-content",
      }}
    >
      <span
        style={{
          background: riskColor(risk),
          borderRadius: 99,
          boxShadow: `0 0 30px ${riskColor(risk)}99`,
          height: 16,
          width: 16,
        }}
      />
      {label}
    </div>
  );
}

function ChainGraph({ focus = 1 }: { focus?: number }) {
  const frame = useCurrentFrame();
  const nodeAppearOffset = 10;
  const allNodes = [...chainNodes, ...branchNodes];

  return (
    <div
      style={{
        border: `1px solid ${border}`,
        borderRadius: 8,
        boxShadow: "0 32px 80px rgba(0, 0, 0, 0.42)",
        flex: 1,
        minHeight: 610,
        overflow: "hidden",
        position: "relative",
      }}
    >
      <div
        style={{
          background: "linear-gradient(180deg, rgba(14,26,46,0.82), rgba(5,8,19,0.78))",
          inset: 0,
          position: "absolute",
        }}
      />
      <svg
        height="100%"
        style={{
          inset: 0,
          position: "absolute",
        }}
        viewBox="0 0 100 100"
        width="100%"
      >
        {[
          ...chainNodes.slice(0, -1).map((node, index) => [node, chainNodes[index + 1]] as const),
          [chainNodes[1], branchNodes[3]] as const,
          [chainNodes[2], branchNodes[0]] as const,
          [chainNodes[3], branchNodes[1]] as const,
          [chainNodes[1], branchNodes[2]] as const,
          [chainNodes[5], chainNodes[6]] as const,
        ].map(([from, to], index) => {
          const progress = appear(frame, 16 + index * 10, 24) * focus;
          const color = riskColor(from.risk === "watch" ? to.risk : from.risk);

          return (
            <g key={`${from.label}-${to.label}`}>
              <line
                stroke="rgba(175, 205, 255, 0.16)"
                strokeWidth="0.48"
                x1={from.x}
                x2={to.x}
                y1={from.y}
                y2={to.y}
              />
              <line
                pathLength={1}
                stroke={color}
                strokeDasharray={`${progress} ${1 - progress}`}
                strokeLinecap="round"
                strokeWidth="0.62"
                x1={from.x}
                x2={to.x}
                y1={from.y}
                y2={to.y}
              />
            </g>
          );
        })}
      </svg>
      {allNodes.map((node, index) => {
        const show = appear(frame, nodeAppearOffset + index * 6, 18);
        const pulse = 0.5 + Math.sin((frame + index * 9) / 12) * 0.5;

        return (
          <div
            key={node.label}
            style={{
              left: `${node.x}%`,
              opacity: show,
              position: "absolute",
              top: `${node.y}%`,
              translate: "-50% -50%",
              scale: interpolate(show, [0, 1], [0.82, 1]),
            }}
          >
            <div
              style={{
                alignItems: "center",
                background: `linear-gradient(180deg, ${riskColor(node.risk)}2d, rgba(5, 8, 19, 0.88))`,
                border: `1px solid ${riskColor(node.risk)}99`,
                borderRadius: 8,
                boxShadow: `0 0 ${24 + pulse * 24}px ${riskColor(node.risk)}55`,
                color: ink,
                display: "flex",
                fontSize: 23,
                fontWeight: 820,
                justifyContent: "center",
                lineHeight: 1.02,
                minHeight: 82,
                padding: "12px 14px",
                textAlign: "center",
                whiteSpace: "pre-line",
                width: 152,
              }}
            >
              {node.label}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function IntroScene({ sceneDuration }: { sceneDuration: number }) {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, sceneDuration) }}>
      <SafeFrame>
        <div
          style={{
            alignItems: "center",
            display: "flex",
            flexDirection: "column",
            gap: 34,
            height: "100%",
            justifyContent: "center",
            textAlign: "center",
          }}
        >
          <div
            style={{
              opacity: appear(frame, 0, 22),
              translate: `0 ${interpolate(appear(frame, 0, 22), [0, 1], [28, 0])}px`,
            }}
          >
            <Kicker>Sanitas supply-risk graph</Kicker>
          </div>
          <div
            style={{
              opacity: appear(frame, 14, 28),
              scale: interpolate(appear(frame, 14, 28), [0, 1], [0.94, 1]),
            }}
          >
            <Headline size={118}>
              Why carboplatin can disappear before the shelf looks empty
            </Headline>
          </div>
          <div style={{ opacity: appear(frame, 52, 24) }}>
            <Copy maxWidth={1040}>
              One medicine depends on active ingredients, supplier quality, manufacturing sites,
              logistics, and evidence that changes faster than procurement cycles.
            </Copy>
          </div>
          <div style={{ opacity: appear(frame, 86, 18) }}>
            <RiskPill label="Risk score 87 · critical" risk="critical" />
          </div>
        </div>
      </SafeFrame>
    </AbsoluteFill>
  );
}

function ChainScene({ sceneDuration }: { sceneDuration: number }) {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, sceneDuration) }}>
      <SafeFrame>
        <div
          style={{
            alignItems: "center",
            display: "flex",
            gap: 70,
            height: "100%",
          }}
        >
          <div
            style={{
              display: "flex",
              flex: "0 0 610px",
              flexDirection: "column",
              gap: 34,
            }}
          >
            <div style={{ opacity: appear(frame, 2, 20) }}>
              <Kicker>The strongest current path</Kicker>
            </div>
            <div style={{ opacity: appear(frame, 16, 24) }}>
              <Headline size={78}>Risk travels through the chain, not just the label.</Headline>
            </div>
            <div style={{ opacity: appear(frame, 50, 22) }}>
              <Copy maxWidth={610}>
                Carboplatin links to a platinum API, a named supplier path, a manufacturing site,
                and primary shortage evidence.
              </Copy>
            </div>
          </div>
          <div
            style={{
              opacity: appear(frame, 24, 24),
              translate: `${interpolate(appear(frame, 24, 24), [0, 1], [34, 0])}px 0`,
              width: 960,
            }}
          >
            <ChainGraph />
          </div>
        </div>
      </SafeFrame>
    </AbsoluteFill>
  );
}

function FailureScene({ sceneDuration }: { sceneDuration: number }) {
  const frame = useCurrentFrame();
  const risks = [
    {
      title: "GMP compliance",
      body: "Quality constraints can remove supplier capacity even when demand is unchanged.",
      risk: "critical" as Risk,
    },
    {
      title: "Demand increase",
      body: "Backup suppliers may already be absorbing redirected orders.",
      risk: "elevated" as Risk,
    },
    {
      title: "Shipping delay",
      body: "Nominal supply becomes uncertain delivery timing for buyers.",
      risk: "elevated" as Risk,
    },
  ];

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, sceneDuration) }}>
      <SafeFrame>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 52,
            height: "100%",
            justifyContent: "center",
          }}
        >
          <div style={{ maxWidth: 1260 }}>
            <div style={{ opacity: appear(frame, 0, 18) }}>
              <Kicker>Where the chain breaks</Kicker>
            </div>
            <div style={{ marginTop: 24, opacity: appear(frame, 12, 24) }}>
              <Headline size={86}>The supplier list is not the same as usable supply.</Headline>
            </div>
          </div>
          <div
            style={{
              display: "grid",
              gap: 28,
              gridTemplateColumns: "repeat(3, 1fr)",
            }}
          >
            {risks.map((risk, index) => {
              const show = appear(frame, 42 + index * 16, 22);

              return (
                <div
                  key={risk.title}
                  style={{
                    background: panel,
                    border: `1px solid ${riskColor(risk.risk)}77`,
                    borderRadius: 8,
                    boxShadow: `0 26px 70px ${riskColor(risk.risk)}20`,
                    minHeight: 330,
                    opacity: show,
                    padding: 38,
                    scale: interpolate(show, [0, 1], [0.94, 1]),
                    translate: `0 ${interpolate(show, [0, 1], [28, 0])}px`,
                  }}
                >
                  <RiskPill label={risk.risk} risk={risk.risk} />
                  <div
                    style={{
                      color: ink,
                      fontSize: 52,
                      fontWeight: 820,
                      lineHeight: 1,
                      marginTop: 30,
                    }}
                  >
                    {risk.title}
                  </div>
                  <div
                    style={{
                      color: muted,
                      fontSize: 33,
                      fontWeight: 520,
                      lineHeight: 1.2,
                      marginTop: 22,
                    }}
                  >
                    {risk.body}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </SafeFrame>
    </AbsoluteFill>
  );
}

function EvidenceScene({ sceneDuration }: { sceneDuration: number }) {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, sceneDuration) }}>
      <SafeFrame>
        <div
          style={{
            alignItems: "center",
            display: "grid",
            gap: 72,
            gridTemplateColumns: "0.82fr 1.18fr",
            height: "100%",
          }}
        >
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 32,
            }}
          >
            <div style={{ opacity: appear(frame, 0, 18) }}>
              <Kicker>Evidence, not guesses</Kicker>
            </div>
            <div style={{ opacity: appear(frame, 14, 22) }}>
              <Headline size={80}>Sanitas separates proof from risk signals.</Headline>
            </div>
            <div style={{ opacity: appear(frame, 46, 20) }}>
              <Copy maxWidth={690}>
                Primary shortage records anchor the graph. News and market signals expand the
                investigation without pretending every link is proven.
              </Copy>
            </div>
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 22,
            }}
          >
            {sourceCards.map((source, index) => {
              const show = appear(frame, 22 + index * 18, 20);

              return (
                <div
                  key={source.label}
                  style={{
                    alignItems: "center",
                    background: `linear-gradient(90deg, ${riskColor(source.risk)}22, rgba(10, 18, 31, 0.78))`,
                    border: `1px solid ${riskColor(source.risk)}66`,
                    borderRadius: 8,
                    display: "grid",
                    gap: 28,
                    gridTemplateColumns: "215px 1fr",
                    minHeight: 172,
                    opacity: show,
                    padding: "26px 30px",
                    translate: `${interpolate(show, [0, 1], [36, 0])}px 0`,
                  }}
                >
                  <div
                    style={{
                      alignItems: "center",
                      background: `${riskColor(source.risk)}22`,
                      border: `1px solid ${riskColor(source.risk)}88`,
                      borderRadius: 8,
                      color: ink,
                      display: "flex",
                      fontSize: 34,
                      fontWeight: 900,
                      height: 124,
                      justifyContent: "center",
                      lineHeight: 1.08,
                      textAlign: "center",
                    }}
                  >
                    {source.label}
                  </div>
                  <div>
                    <div
                      style={{
                        color: ink,
                        fontSize: 42,
                        fontWeight: 820,
                        lineHeight: 1,
                      }}
                    >
                      {source.title}
                    </div>
                    <div
                      style={{
                        color: muted,
                        fontSize: 29,
                        fontWeight: 520,
                        lineHeight: 1.22,
                        marginTop: 14,
                      }}
                    >
                      {source.detail}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </SafeFrame>
    </AbsoluteFill>
  );
}

function AgentScene({ sceneDuration }: { sceneDuration: number }) {
  const frame = useCurrentFrame();
  const scan = interpolate(frame, [24, 128], [0, 1], {
    easing: easeInOut,
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, sceneDuration) }}>
      <SafeFrame>
        <div
          style={{
            alignItems: "center",
            display: "grid",
            gap: 70,
            gridTemplateColumns: "1fr 1fr",
            height: "100%",
          }}
        >
          <div
            style={{
              border: `1px solid ${border}`,
              borderRadius: 8,
              minHeight: 690,
              overflow: "hidden",
              position: "relative",
            }}
          >
            <ChainGraph focus={0.8} />
            <div
              style={{
                background: `linear-gradient(90deg, transparent, ${stable}66, transparent)`,
                height: "100%",
                left: `${interpolate(scan, [0, 1], [-15, 100])}%`,
                opacity: 0.8,
                position: "absolute",
                top: 0,
                width: 90,
              }}
            />
          </div>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 32,
            }}
          >
            <div style={{ opacity: appear(frame, 2, 18) }}>
              <Kicker>Agent-assisted investigation</Kicker>
            </div>
            <div style={{ opacity: appear(frame, 14, 24) }}>
              <Headline size={78}>The agent turns the graph into an action queue.</Headline>
            </div>
            <div style={{ opacity: appear(frame, 46, 22) }}>
              <Copy maxWidth={760}>
                It surfaces the highest-risk path first, cites the supporting source, and flags what
                is evidence versus inference.
              </Copy>
            </div>
            <div
              style={{
                display: "flex",
                flexWrap: "wrap",
                gap: 18,
                opacity: appear(frame, 82, 20),
              }}
            >
              <RiskPill label="Evidence: FDA + ASHP" risk="critical" />
              <RiskPill label="Inference: upstream raw material" risk="elevated" />
            </div>
          </div>
        </div>
      </SafeFrame>
    </AbsoluteFill>
  );
}

function ActionScene({ sceneDuration }: { sceneDuration: number }) {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={{ opacity: sceneOpacity(frame, sceneDuration) }}>
      <SafeFrame>
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: 46,
            height: "100%",
            justifyContent: "center",
          }}
        >
          <div style={{ opacity: appear(frame, 0, 18) }}>
            <Kicker>Before the shortage reaches the patient</Kicker>
          </div>
          <div style={{ opacity: appear(frame, 14, 24) }}>
            <Headline size={90}>See the weak link early. Move before care is delayed.</Headline>
          </div>
          <div
            style={{
              display: "grid",
              gap: 22,
              gridTemplateColumns: "repeat(4, 1fr)",
              marginTop: 22,
            }}
          >
            {actionCards.map((action, index) => {
              const show = appear(frame, 54 + index * 12, 20);

              return (
                <div
                  key={action}
                  style={{
                    alignItems: "center",
                    background: panel,
                    border: `1px solid ${index === 3 ? critical : border}`,
                    borderRadius: 8,
                    color: ink,
                    display: "flex",
                    fontSize: 38,
                    fontWeight: 820,
                    justifyContent: "center",
                    lineHeight: 1.04,
                    minHeight: 190,
                    opacity: show,
                    padding: 30,
                    scale: interpolate(show, [0, 1], [0.92, 1]),
                    textAlign: "center",
                  }}
                >
                  {action}
                </div>
              );
            })}
          </div>
          <div
            style={{
              alignItems: "center",
              display: "flex",
              gap: 26,
              marginTop: 18,
              opacity: appear(frame, 112, 24),
            }}
          >
            <div
              style={{
                background: critical,
                borderRadius: 99,
                boxShadow: `0 0 42px ${critical}`,
                height: 22,
                width: 22,
              }}
            />
            <div
              style={{
                color: muted,
                fontSize: 42,
                fontWeight: 640,
              }}
            >
              Sanitas makes medicine supply risk visible while there is still time to act.
            </div>
          </div>
        </div>
      </SafeFrame>
    </AbsoluteFill>
  );
}

export const MyComposition = () => {
  return (
    <AbsoluteFill>
      <Background accent="#327bff" />
      <Sequence durationInFrames={150} premountFor={fps}>
        <IntroScene sceneDuration={150} />
      </Sequence>
      <Sequence from={132} durationInFrames={210} premountFor={fps}>
        <ChainScene sceneDuration={210} />
      </Sequence>
      <Sequence from={324} durationInFrames={180} premountFor={fps}>
        <FailureScene sceneDuration={180} />
      </Sequence>
      <Sequence from={486} durationInFrames={180} premountFor={fps}>
        <EvidenceScene sceneDuration={180} />
      </Sequence>
      <Sequence from={648} durationInFrames={210} premountFor={fps}>
        <AgentScene sceneDuration={210} />
      </Sequence>
      <Sequence from={840} durationInFrames={210} premountFor={fps}>
        <ActionScene sceneDuration={210} />
      </Sequence>
    </AbsoluteFill>
  );
};
