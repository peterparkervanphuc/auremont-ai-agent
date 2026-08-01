import { useState } from "react";
import { Layout } from "../../components/Layout";
import { ConflictsTab } from "./ConflictsTab";
import { DocumentsTab } from "./DocumentsTab";
import { EvalTab } from "./EvalTab";
import { SettingsTab } from "./SettingsTab";

type Tab = "documents" | "eval" | "conflicts" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "documents", label: "Tab 1: Kho tài liệu" },
  { id: "eval", label: "Tab 2: Đánh giá AI" },
  { id: "conflicts", label: "Tab 3: Cảnh báo mâu thuẫn" },
  { id: "settings", label: "Cài đặt chung" },
];

// CLAUDE.md §5.3 — "SalesMate Admin" với sidebar 4 mục.
export function AdminPage() {
  const [activeTab, setActiveTab] = useState<Tab>("documents");

  return (
    <Layout title="SalesMate Admin">
      <nav>
        {TABS.map((tab) => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)}>
            {tab.label}
          </button>
        ))}
      </nav>
      {activeTab === "documents" && <DocumentsTab />}
      {activeTab === "eval" && <EvalTab />}
      {activeTab === "conflicts" && <ConflictsTab />}
      {activeTab === "settings" && <SettingsTab />}
    </Layout>
  );
}
