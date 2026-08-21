import type { ReactNode } from "react";

interface AdminMetricCardProps {
  label: string;
  value: string | number;
  hint: string;
  icon: ReactNode;
  tone?: "default" | "success" | "warning" | "danger";
}

export function AdminMetricCard({ label, value, hint, icon, tone = "default" }: AdminMetricCardProps) {
  return (
    <article className={`admin-metric admin-metric--${tone}`}>
      <div className="admin-metric-icon">{icon}</div>
      <div>
        <span className="admin-metric-label">{label}</span>
        <strong className="admin-metric-value">{value}</strong>
        <span className="admin-metric-hint">{hint}</span>
      </div>
    </article>
  );
}
