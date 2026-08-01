import type { ReactNode } from "react";

interface LayoutProps {
  title: string;
  children: ReactNode;
}

/** Minimal shared shell — Sale/Admin nav chrome to be filled in once each area's UI is built. */
export function Layout({ title, children }: LayoutProps) {
  return (
    <div>
      <header>
        <h1>{title}</h1>
      </header>
      <main>{children}</main>
    </div>
  );
}
