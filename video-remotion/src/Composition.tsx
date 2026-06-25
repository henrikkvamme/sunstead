import { Video } from "@remotion/media";
import type React from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
} from "remotion";

export const FPS = 30;
export const DEMO_DURATION_IN_FRAMES = 540;

const INTRO_FRAMES = 72;
const RECORDING_FRAMES = 364;
const OUTRO_START = INTRO_FRAMES + RECORDING_FRAMES;
const VIDEO_SRC = staticFile("recording/test.mp4");

const easeOut = Easing.bezier(0.16, 1, 0.3, 1);

const clamp = {
  extrapolateLeft: "clamp" as const,
  extrapolateRight: "clamp" as const,
};

type Beat = {
  start: number;
  end: number;
  eyebrow: string;
  title: string;
  detail: string;
  metric: string;
};

const beats: Beat[] = [
  {
    start: INTRO_FRAMES + 8,
    end: INTRO_FRAMES + 126,
    eyebrow: "shortage signal",
    title: "Carboplatin risk is no longer hidden in a table",
    detail: "The medicine becomes the entry point into suppliers, evidence, and weak links.",
    metric: "Risk 87",
  },
  {
    start: INTRO_FRAMES + 126,
    end: INTRO_FRAMES + 250,
    eyebrow: "supply path",
    title: "The investigation follows the chain, not a static dashboard",
    detail: "Supplier, geography, quality, demand, and logistics context stay connected.",
    metric: "Graph view",
  },
  {
    start: INTRO_FRAMES + 250,
    end: OUTRO_START + 12,
    eyebrow: "operator action",
    title: "The risk resolves into an action queue",
    detail: "Teams see why the recommendation matters before oncology stock falls below safety threshold.",
    metric: "Alternate supplier",
  },
];

export const MyComposition: React.FC = () => {
  const frame = useCurrentFrame();

  return (
    <AbsoluteFill style={styles.stage}>
      <AmbientBackdrop />

      <OpeningTitle />

      <Sequence from={INTRO_FRAMES} durationInFrames={RECORDING_FRAMES}>
        <HeroRecording />
      </Sequence>

      <Timeline frame={frame} />
      <BeatCaption frame={frame} />

      <Sequence from={OUTRO_START} durationInFrames={DEMO_DURATION_IN_FRAMES - OUTRO_START}>
        <ClosingCard />
      </Sequence>
    </AbsoluteFill>
  );
};

const AmbientBackdrop: React.FC = () => {
  const frame = useCurrentFrame();
  const scale = interpolate(frame, [0, DEMO_DURATION_IN_FRAMES], [1.08, 1.16], clamp);
  const opacity = interpolate(frame, [0, 54, OUTRO_START, DEMO_DURATION_IN_FRAMES], [0.26, 0.54, 0.5, 0.18], clamp);

  return (
    <AbsoluteFill style={styles.backdropWrap}>
      <Video
        src={VIDEO_SRC}
        muted
        objectFit="cover"
        style={{
          ...styles.backdropVideo,
          opacity,
          transform: `scale(${scale})`,
        }}
      />
      <AbsoluteFill style={styles.redWash} />
      <AbsoluteFill style={styles.tealWash} />
      <AbsoluteFill style={styles.vignette} />
      <AbsoluteFill style={styles.scanlines} />
    </AbsoluteFill>
  );
};

const OpeningTitle: React.FC = () => {
  const frame = useCurrentFrame();
  const titleOpacity = interpolate(frame, [8, 28, 64, 82], [0, 1, 1, 0], clamp);
  const titleY = interpolate(frame, [8, 34], [34, 0], { ...clamp, easing: easeOut });
  const ruleWidth = interpolate(frame, [24, 54], [0, 420], { ...clamp, easing: easeOut });
  const previewOpacity = interpolate(frame, [20, 58], [0, 0.24], clamp);

  return (
    <AbsoluteFill style={styles.intro}>
      <div
        style={{
          ...styles.previewGlass,
          opacity: previewOpacity,
          transform: `translateY(${interpolate(frame, [20, 72], [28, 0], clamp)}px) scale(0.88)`,
        }}
      >
        <Video src={VIDEO_SRC} muted objectFit="cover" style={styles.previewVideo} />
      </div>

      <div
        style={{
          ...styles.titleBlock,
          opacity: titleOpacity,
          transform: `translateY(${titleY}px)`,
        }}
      >
        <div style={styles.kicker}>SANITAS DEMO</div>
        <h1 style={styles.h1}>Medicine supply risk chain</h1>
        <div style={styles.ruleTrack}>
          <div style={{ ...styles.ruleFill, width: ruleWidth }} />
        </div>
        <p style={styles.lede}>
          From shortage signal to supplier path to recommended action.
        </p>
      </div>
    </AbsoluteFill>
  );
};

const HeroRecording: React.FC = () => {
  const frame = useCurrentFrame();
  const entrance = interpolate(frame, [0, 48], [0, 1], { ...clamp, easing: easeOut });
  const exit = interpolate(frame, [RECORDING_FRAMES - 40, RECORDING_FRAMES], [1, 0.82], clamp);
  const opacity = entrance * exit;
  const scale = interpolate(frame, [0, RECORDING_FRAMES], [0.985, 1.02], clamp);
  const y = interpolate(frame, [0, 54], [30, 0], { ...clamp, easing: easeOut });

  return (
    <AbsoluteFill style={{ ...styles.heroLayer, opacity }}>
      <div
        style={{
          ...styles.deviceGlow,
          opacity: 0.55 * opacity,
          scale,
          translate: `0px ${y}px`,
        }}
      />
      <div
        style={{
          ...styles.monitorFrame,
          scale,
          translate: `0px ${y}px`,
        }}
      >
        <Video src={VIDEO_SRC} volume={1} objectFit="contain" style={styles.mainVideo} />
      </div>
      <div
        style={{
          ...styles.deviceBase,
          opacity,
          scale,
          translate: `0px ${y}px`,
        }}
      />
    </AbsoluteFill>
  );
};

const BeatCaption: React.FC<{ frame: number }> = ({ frame }) => {
  const beat = beats.find((item) => frame >= item.start && frame < item.end);

  if (!beat) {
    return null;
  }

  const inFrame = frame - beat.start;
  const outFrame = beat.end - frame;
  const opacity = Math.min(
    interpolate(inFrame, [0, 18], [0, 1], { ...clamp, easing: easeOut }),
    interpolate(outFrame, [0, 18], [0, 1], clamp),
  );
  const x = interpolate(inFrame, [0, 28], [-34, 0], { ...clamp, easing: easeOut });

  return (
    <div
      style={{
        ...styles.caption,
        opacity,
        transform: `translateX(${x}px)`,
      }}
    >
      <div style={styles.captionMeta}>
        <span style={styles.captionEyebrow}>{beat.eyebrow}</span>
        <span style={styles.captionMetric}>{beat.metric}</span>
      </div>
      <div style={styles.captionTitle}>{beat.title}</div>
      <div style={styles.captionDetail}>{beat.detail}</div>
    </div>
  );
};

const Timeline: React.FC<{ frame: number }> = ({ frame }) => {
  const progress = interpolate(frame, [INTRO_FRAMES, OUTRO_START], [0, 1], clamp);
  const visible = interpolate(frame, [INTRO_FRAMES - 18, INTRO_FRAMES + 8, OUTRO_START, OUTRO_START + 20], [0, 1, 1, 0], clamp);

  return (
    <div style={{ ...styles.timeline, opacity: visible }}>
      <div style={styles.timelineLabel}>LIVE DEMO CAPTURE</div>
      <div style={styles.timelineTrack}>
        <div style={{ ...styles.timelineFill, width: `${progress * 100}%` }} />
        {beats.map((beat) => {
          const left = interpolate(beat.start, [INTRO_FRAMES, OUTRO_START], [0, 100], clamp);
          const active = frame >= beat.start && frame < beat.end;
          return (
            <div
              key={beat.eyebrow}
              style={{
                ...styles.timelineDot,
                left: `${left}%`,
                borderColor: active ? "#ff5a0a" : "#282828",
                background: active ? "#ff5a0a" : "#151515",
                boxShadow: active ? "0 0 24px rgba(255, 90, 10, 0.58)" : "none",
              }}
            />
          );
        })}
      </div>
      <div style={styles.timelineTime}>
        {String(Math.max(0, Math.floor((frame - INTRO_FRAMES) / FPS))).padStart(2, "0")}s
      </div>
    </div>
  );
};

const ClosingCard: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 28], [0, 1], { ...clamp, easing: easeOut });
  const y = interpolate(frame, [0, 36], [26, 0], { ...clamp, easing: easeOut });
  const items = [
    "Shortage evidence stays connected",
    "Supplier paths become explainable",
    "Clinical teams get a recommended action",
  ];

  return (
    <AbsoluteFill style={{ ...styles.closing, opacity }}>
      <div style={{ ...styles.closingPanel, transform: `translateY(${y}px)` }}>
        <div style={styles.kicker}>FROM SIGNAL TO DECISION</div>
        <h2 style={styles.h2}>A cinematic view of supply risk before it becomes care disruption.</h2>
        <div style={styles.closingGrid}>
          {items.map((item, index) => {
            const itemOpacity = interpolate(frame, [24 + index * 12, 46 + index * 12], [0, 1], clamp);
            return (
              <div key={item} style={{ ...styles.closingItem, opacity: itemOpacity }}>
                <span style={styles.closingIndex}>0{index + 1}</span>
                <span>{item}</span>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const styles: Record<string, React.CSSProperties> = {
  stage: {
    background: "#050505",
    color: "#f5f5f5",
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    overflow: "hidden",
  },
  backdropWrap: {
    overflow: "hidden",
    background:
      "linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px), #050505",
    backgroundSize: "64px 64px, 64px 64px, auto",
  },
  backdropVideo: {
    width: "100%",
    height: "100%",
    filter: "blur(18px) saturate(0.88) contrast(1.05)",
  },
  redWash: {
    background:
      "radial-gradient(circle at 17% 44%, rgba(255, 90, 10, 0.18) 0%, rgba(255, 90, 10, 0.05) 32%, transparent 62%)",
    mixBlendMode: "screen",
  },
  tealWash: {
    background:
      "linear-gradient(90deg, rgba(10, 10, 10, 0.12), rgba(21, 21, 21, 0.44), rgba(255, 90, 10, 0.06))",
    mixBlendMode: "screen",
  },
  vignette: {
    background:
      "radial-gradient(circle at 50% 50%, transparent 0%, rgba(5, 5, 5, 0.1) 48%, rgba(5, 5, 5, 0.72) 100%)",
  },
  scanlines: {
    background:
      "linear-gradient(rgba(255,255,255,0.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.018) 1px, transparent 1px)",
    backgroundSize: "100% 42px, 52px 100%",
    opacity: 0.22,
  },
  intro: {
    alignItems: "center",
    justifyContent: "center",
  },
  previewGlass: {
    position: "absolute",
    width: 1280,
    height: 804,
    border: "1px solid #282828",
    borderRadius: 12,
    overflow: "hidden",
    boxShadow: "0 34px 140px rgba(0, 0, 0, 0.78)",
  },
  previewVideo: {
    width: "100%",
    height: "100%",
    filter: "blur(8px) saturate(1.05)",
  },
  titleBlock: {
    position: "absolute",
    left: 170,
    bottom: 210,
    width: 980,
  },
  kicker: {
    color: "#ff5a0a",
    fontSize: 23,
    fontWeight: 750,
    lineHeight: 1.1,
    textTransform: "uppercase",
  },
  h1: {
    margin: "20px 0 24px",
    fontSize: 92,
    lineHeight: 0.97,
    fontWeight: 820,
    maxWidth: 1020,
  },
  ruleTrack: {
    width: 420,
    height: 3,
    background: "rgba(214, 255, 247, 0.14)",
    marginBottom: 24,
  },
  ruleFill: {
    height: "100%",
    background: "#ff5a0a",
  },
  lede: {
    margin: 0,
    color: "#a7a7a7",
    fontSize: 32,
    lineHeight: 1.28,
    maxWidth: 820,
  },
  heroLayer: {
    alignItems: "center",
    justifyContent: "center",
  },
  deviceGlow: {
    position: "absolute",
    width: 1640,
    height: 1030,
    borderRadius: 12,
    background:
      "linear-gradient(135deg, rgba(255, 90, 10, 0.32), rgba(21, 21, 21, 0.64), rgba(5,5,5,0))",
    filter: "blur(24px)",
  },
  monitorFrame: {
    position: "absolute",
    width: 1592,
    height: 1000,
    borderRadius: 12,
    overflow: "hidden",
    background: "#0a0a0a",
    border: "1px solid #282828",
    boxShadow:
      "0 0 0 1px rgba(255,255,255,0.04) inset, 0 44px 150px rgba(0,0,0,0.72), 0 0 70px rgba(255,90,10,0.12)",
  },
  mainVideo: {
    width: "100%",
    height: "100%",
    background: "#0a0a0a",
  },
  deviceBase: {
    position: "absolute",
    left: 195,
    bottom: 16,
    width: 1530,
    height: 48,
    borderRadius: "0 0 16px 16px",
    background: "linear-gradient(180deg, #282828, #0a0a0a)",
    border: "1px solid #282828",
    pointerEvents: "none",
  },
  caption: {
    position: "absolute",
    left: 72,
    bottom: 72,
    width: 560,
    padding: "22px 26px",
    borderRadius: 10,
    background: "rgba(10, 10, 10, 0.9)",
    border: "1px solid #282828",
    boxShadow: "0 24px 100px rgba(0, 0, 0, 0.62)",
    backdropFilter: "blur(18px)",
  },
  captionMeta: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 24,
    marginBottom: 12,
  },
  captionEyebrow: {
    color: "#ff5a0a",
    fontSize: 15,
    lineHeight: 1,
    fontWeight: 800,
    textTransform: "uppercase",
  },
  captionMetric: {
    color: "#ff5a0a",
    fontSize: 16,
    lineHeight: 1,
    fontWeight: 850,
  },
  captionTitle: {
    color: "#f5f5f5",
    fontSize: 27,
    lineHeight: 1.12,
    fontWeight: 820,
    marginBottom: 10,
  },
  captionDetail: {
    color: "#a7a7a7",
    fontSize: 18,
    lineHeight: 1.36,
  },
  timeline: {
    position: "absolute",
    right: 72,
    bottom: 80,
    width: 500,
    display: "grid",
    gridTemplateColumns: "auto 1fr auto",
    alignItems: "center",
    gap: 20,
    padding: "18px 22px",
    borderRadius: 999,
    background: "rgba(10, 10, 10, 0.9)",
    border: "1px solid #282828",
    boxShadow: "0 18px 70px rgba(0, 0, 0, 0.5)",
    backdropFilter: "blur(16px)",
  },
  timelineLabel: {
    color: "#9d9d9d",
    fontSize: 16,
    fontWeight: 800,
    textTransform: "uppercase",
  },
  timelineTrack: {
    position: "relative",
    height: 4,
    background: "#282828",
    borderRadius: 999,
  },
  timelineFill: {
    position: "absolute",
    left: 0,
    top: 0,
    height: 4,
    borderRadius: 999,
    background: "#ff5a0a",
  },
  timelineDot: {
    position: "absolute",
    top: -7,
    width: 18,
    height: 18,
    marginLeft: -9,
    borderRadius: 999,
    border: "2px solid #282828",
  },
  timelineTime: {
    color: "#f5f5f5",
    fontSize: 18,
    fontWeight: 850,
    fontVariantNumeric: "tabular-nums",
  },
  closing: {
    alignItems: "center",
    justifyContent: "center",
    background:
      "linear-gradient(90deg, rgba(5,5,5,0.94), rgba(10,10,10,0.82)), radial-gradient(circle at 32% 42%, rgba(255,90,10,0.16), transparent 42%)",
  },
  closingPanel: {
    width: 1180,
  },
  h2: {
    margin: "22px 0 38px",
    fontSize: 66,
    lineHeight: 1.02,
    fontWeight: 830,
    maxWidth: 1120,
  },
  closingGrid: {
    display: "grid",
    gridTemplateColumns: "1fr 1fr 1fr",
    gap: 18,
  },
  closingItem: {
    minHeight: 142,
    borderRadius: 16,
    padding: "26px 28px",
    background: "#151515",
    border: "1px solid #282828",
    color: "#f3f3f3",
    fontSize: 25,
    lineHeight: 1.26,
    fontWeight: 720,
  },
  closingIndex: {
    display: "block",
    color: "#ff5a0a",
    fontSize: 19,
    fontWeight: 850,
    marginBottom: 16,
  },
};
