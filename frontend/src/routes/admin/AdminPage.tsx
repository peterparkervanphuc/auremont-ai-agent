import { useState } from "react";
import { Layout } from "../../components/Layout";
import { AdminChatTab } from "./AdminChatTab";
import { ApiTestTab } from "./ApiTestTab";
import { ConflictsTab } from "./ConflictsTab";
import { DocumentsTab } from "./DocumentsTab";
import { EvalTab } from "./EvalTab";
import { SettingsTab } from "./SettingsTab";
import { AlertIcon, ApiIcon, ChartIcon, ChatIcon, DocumentIcon, SettingsIcon } from "../../components/Icons";

type Tab = "chat" | "documents" | "eval" | "conflicts" | "api-test" | "settings";

// sidebar Admin: Kho tài liệu, Đánh giá AI, Cảnh báo mâu thuẫn, Cài đặt chung.
const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "chat", label: "Chat", icon: <ChatIcon /> },
  { id: "documents", label: "Kho tài liệu", icon: <DocumentIcon /> },
  { id: "eval", label: "Đánh giá AI", icon: <ChartIcon /> },
  { id: "conflicts", label: "Cảnh báo mâu thuẫn", icon: <AlertIcon /> },
  { id: "api-test", label: "Kiểm tra API", icon: <ApiIcon /> },
  { id: "settings", label: "Cài đặt chung", icon: <SettingsIcon /> },
];

export function AdminPage() {
  const [activeTab, setActiveTab] = useState<Tab>("chat");

  return (
    <Layout title="SalesMate Admin" navItems={TABS} activeTab={activeTab} onTabChange={(id) => setActiveTab(id as Tab)}>
      {activeTab === "chat" && <AdminChatTab />}
      {activeTab === "documents" && <DocumentsTab />}
      {activeTab === "eval" && <EvalTab />}
      {activeTab === "conflicts" && <ConflictsTab />}
      {activeTab === "api-test" && <ApiTestTab />}
      {activeTab === "settings" && <SettingsTab />}
    </Layout>
  );
}
