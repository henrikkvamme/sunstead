import { type VariantProps, cva } from "class-variance-authority";
import type { ComponentPropsWithoutRef, ReactNode } from "react";

import { cn } from "#/lib/cn";

export function LogoMark() {
  return (
    <a aria-label="Sunstead home" className="brand-mark" href="/">
      <span className="brand-flame" aria-hidden />
      <span>Sunstead</span>
    </a>
  );
}

const buttonStyles = cva("ui-button", {
  variants: {
    variant: {
      primary: "ui-button-primary",
      secondary: "ui-button-secondary",
      ghost: "ui-button-ghost",
    },
    size: {
      sm: "ui-button-sm",
      md: "ui-button-md",
      lg: "ui-button-lg",
    },
  },
  defaultVariants: {
    size: "md",
    variant: "secondary",
  },
});

export type ButtonProps = ComponentPropsWithoutRef<"a"> &
  VariantProps<typeof buttonStyles> & {
    icon?: ReactNode;
  };

export function Button({ children, className, icon, size, variant, ...props }: ButtonProps) {
  return (
    <a className={cn(buttonStyles({ size, variant }), className)} {...props}>
      <span>{children}</span>
      {icon}
    </a>
  );
}

export function SectionMarker({ children = "Developer first" }: { children?: ReactNode }) {
  return (
    <div className="section-marker">
      <span aria-hidden>//</span>
      {children}
      <span aria-hidden>//</span>
    </div>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  children,
}: {
  eyebrow?: string;
  title: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="section-head">
      {eyebrow ? <SectionMarker>{eyebrow}</SectionMarker> : null}
      <h2>{title}</h2>
      {children ? <p>{children}</p> : null}
    </div>
  );
}

export function BrowserFrame({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn("browser-frame", className)}>
      <div className="browser-top">
        <div className="browser-lights" aria-hidden>
          <span />
          <span />
          <span />
        </div>
        <div className="browser-tab" aria-hidden />
        <div className="browser-address" />
        <div className="browser-pill" />
      </div>
      <div className="browser-content">{children}</div>
    </div>
  );
}

export function CodePanel({ lines }: { lines: Array<string> }) {
  return (
    <pre className="code-panel" aria-label="Example structured output">
      {lines.map((line, index) => (
        <span className="code-line" key={`${line}-${index}`}>
          <span className="code-number">{index + 1}</span>
          <code>{line}</code>
        </span>
      ))}
    </pre>
  );
}

export function FeatureCard({
  children,
  className,
  title,
}: {
  children: ReactNode;
  className?: string;
  title: string;
}) {
  return (
    <article className={cn("feature-card", className)}>
      <h3>{title}</h3>
      <p>{children}</p>
    </article>
  );
}

export function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="mini-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export function FAQItem({ answer, question }: { answer: string; question: string }) {
  return (
    <details className="faq-item">
      <summary>{question}</summary>
      <p>{answer}</p>
    </details>
  );
}
