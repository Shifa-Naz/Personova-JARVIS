import type { ReactNode } from "react";

interface Props {
  title: string;
  /** One plain sentence: what's here, or how to use it by voice. */
  lead?: ReactNode;
  offline?: boolean;
  error?: string | null;
  children?: ReactNode;
}

/** Shared header for the productivity pages, with honest offline/error states. */
const PageHeader = ({ title, lead, offline, error, children }: Props) => (
  <header className="mb-8 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
    <div>
      <h1 className="font-display text-4xl font-semibold text-foreground">{title}</h1>
      {lead && <p className="mt-2 max-w-2xl text-muted-foreground">{lead}</p>}
      {offline && (
        <p className="mt-2 text-sm text-jarvis-ember">
          The backend is offline, so you're seeing the last saved copy. Changes need the backend running.
        </p>
      )}
      {error && <p className="mt-2 text-sm text-jarvis-red">{error}</p>}
    </div>
    {children}
  </header>
);

export default PageHeader;
