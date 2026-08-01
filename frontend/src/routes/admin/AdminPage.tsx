import { useState } from "react";
import { Layout } from "../../components/Layout";
import { ConflictsTab } from "./ConflictsTab";
import { DocumentsTab } from "./DocumentsTab";
import { EvalTab } from "./EvalTab";
import { InventoryTab } from "./InventoryTab";
import { SettingsTab } from "./SettingsTab";

type Tab = "documents" | "inventory" | "eval" | "conflicts" | "settings";

const TABS: { id: Tab; label: string }[] = [
  { id: "documents", label: "Tab 1: Kho tài liệu" },
  { id: "inventory", label: "Tab 2: Quản lý Tồn kho" },
  { id: "eval", label: "Tab 3: Đánh giá AI" },
  { id: "conflicts", label: "Tab 4: Cảnh báo mâu thuẫn" },
  { id: "settings", label: "Cài đặt chung" },
];

// CLAUDE.md §6.5 — "SalesMate Admin" với sidebar 4 mục.
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
      {activeTab === "inventory" && <InventoryTab />}
      {activeTab === "eval" && <EvalTab />}
      {activeTab === "conflicts" && <ConflictsTab />}
      {activeTab === "settings" && <SettingsTab />}
    </Layout>
  );
}
