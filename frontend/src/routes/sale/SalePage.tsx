import { Route, Routes } from "react-router-dom";
import { Layout } from "../../components/Layout";
import { ChatWindow } from "./ChatWindow";
import { SessionList } from "./SessionList";

export function SalePage() {
  return (
    <Layout title="SalesMate — Sale">
      <div style={{ display: "flex" }}>
        <SessionList />
        <Routes>
          <Route path="sessions/:sessionId" element={<ChatWindow />} />
          <Route path="*" element={<p>Chọn hoặc tạo một Session để bắt đầu.</p>} />
        </Routes>
      </div>
    </Layout>
  );
}
