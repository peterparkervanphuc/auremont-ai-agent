import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { useAuth } from "../../hooks/useAuth";
import type { DocumentResponse } from "../../types";
import { Sparkline } from "../../components/Sparkline";
import {
  AlertIcon,
  ArrowRightIcon,
  ChartIcon,
  DocumentIcon,
  SettingsIcon,
  ShieldCheckIcon,
} from "../../components/Icons";

interface ConflictFlagResponse {
  id: number;
  document_id_a: number;
  document_id_b: number;
  description: string | null;
  status: "open" | "resolved";
  created_at: string;
}

interface EvalScores {
  faithfulness_avg: number | null;
  answer_relevancy_avg: number | null;
  top_failed_questions: { message_id: number; question: string; feedback_count: number }[];
}

interface AdminTrends {
  documents: number[];
  open_conflicts: number[];
}

const QUICK_LINKS = [
  { to: "/documents", icon: <DocumentIcon size={22} />, title: "Kho tài liệu", desc: "Tải lên và quản lý tài liệu dự án" },
  { to: "/eval", icon: <ChartIcon size={22} />, title: "Chất lượng trả lời", desc: "Theo dõi các câu trả lời cần cải thiện" },
  { to: "/conflicts", icon: <AlertIcon size={22} />, title: "Cảnh báo mâu thuẫn", desc: "Xử lý tài liệu chồng chéo thông tin" },
  { to: "/settings", icon: <SettingsIcon size={22} />, title: "Cài đặt chung", desc: "Cấu hình hệ thống" },
];

function pct(value: number | null | undefined) {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

export function AdminHome() {
  const { username } = useAuth();
  const [documents, setDocuments] = useState<DocumentResponse[] | null>(null);
  const [conflicts, setConflicts] = useState<ConflictFlagResponse[] | null>(null);
  const [scores, setScores] = useState<EvalScores | null>(null);
  const [trends, setTrends] = useState<AdminTrends | null>(null);

  useEffect(() => {
    api.get<DocumentResponse[]>("/documents").then(setDocuments).catch(() => setDocuments([]));
    api.get<ConflictFlagResponse[]>("/admin/conflicts").then(setConflicts).catch(() => setConflicts([]));
    api.get<EvalScores>("/admin/eval/scores").then(setScores).catch(() => {});
    api.get<AdminTrends>("/admin/stats/trends").then(setTrends).catch(() => setTrends(null));
  }, []);

  const openConflicts = (conflicts ?? []).filter((c) => c.status === "open");
  const recentOpenConflicts = openConflicts.slice(0, 3);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">Bảng điều khiển quản trị</h2>
          <p className="page-sub">
            Chào {username ?? "bạn"}, đây là tổng quan kho tri thức, chất lượng trả lời AI và các cảnh báo cần xử lý.
          </p>
        </div>
      </div>

      <div className="stat-grid">
        <div className="stat-card">
          <div className="stat-label">Tài liệu trong kho</div>
          <div className="stat-card-foot">
            <div className="stat-value">{documents == null ? "—" : documents.length}</div>
            {trends && <Sparkline values={trends.documents} />}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Cảnh báo đang mở</div>
          <div className="stat-card-foot">
            <div className="stat-value">{conflicts == null ? "—" : openConflicts.length}</div>
            {trends && <Sparkline values={trends.open_conflicts} />}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Bám sát nguồn</div>
          <div className="stat-value">{pct(scores?.faithfulness_avg)}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Độ liên quan</div>
          <div className="stat-value">{pct(scores?.answer_relevancy_avg)}</div>
        </div>
      </div>

      <section className="section-block">
        <h3 className="section-title">Truy cập nhanh</h3>
        <div className="hero-nav-cards home-action-grid">
          {QUICK_LINKS.map((l, i) => (
            <Link key={l.to} to={l.to} className={`hero-nav-card ${i === 0 ? "hero-nav-card--primary" : ""}`}>
              <div className="hero-nav-card-icon">{l.icon}</div>
              <div>
                <p className="hero-nav-card-title">{l.title}</p>
                <p className="hero-nav-card-desc">{l.desc}</p>
              </div>
              <ArrowRightIcon size={16} className="hero-nav-card-arrow" />
            </Link>
          ))}
        </div>
      </section>

      <section>
        <h3 className="section-title">Cảnh báo mâu thuẫn gần đây</h3>
        {recentOpenConflicts.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <ShieldCheckIcon size={26} />
            </div>
            <p className="empty-state-title">Không có cảnh báo nào đang mở</p>
            <p className="empty-state-text">Kho tài liệu hiện không có xung đột thông tin cần xử lý.</p>
          </div>
        ) : (
          <div className="data-list">
            {recentOpenConflicts.map((c) => (
              <Link key={c.id} to="/conflicts" className="data-row">
                <div className="data-row-icon">
                  <AlertIcon size={16} />
                </div>
                <div className="data-row-main">
                  <div className="data-row-title">{c.description ?? `Tài liệu #${c.document_id_a} và #${c.document_id_b}`}</div>
                  <div className="data-row-meta">
                    <span>Tài liệu #{c.document_id_a} ↔ #{c.document_id_b}</span>
                  </div>
                </div>
                <ArrowRightIcon size={16} />
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
