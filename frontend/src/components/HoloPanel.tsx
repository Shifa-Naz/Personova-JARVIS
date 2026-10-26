import type { ReactNode } from "react";

interface PanelProps {
  children: ReactNode;
  title?: string;
  /** Optional element shown at the right of the title row (a count, a button). */
  aside?: ReactNode;
  className?: string;
  as?: "section" | "div";
}

/** Flat instrument panel. The name is kept from the original codebase; it no longer glows. */
const HoloPanel = ({ children, title, aside, className = "", as: Tag = "section" }: PanelProps) => (
  <Tag className={`panel p-5 ${className}`}>
    {(title || aside) && (
      <header className="mb-4 flex items-baseline justify-between gap-3">
        {title && <h2 className="text-base font-semibold text-foreground">{title}</h2>}
        {aside && <div className="text-sm text-muted-foreground">{aside}</div>}
      </header>
    )}
    {children}
  </Tag>
);

export default HoloPanel;
