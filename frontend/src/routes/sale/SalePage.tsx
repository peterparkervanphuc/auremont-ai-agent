import { Route, Routes } from "react-router-dom";
import { ChatWindow } from "./ChatWindow";
import { SessionList } from "./SessionList";
import { SparkleIcon } from "../../components/Icons";

// shell kiểu ChatGPT: sidebar Session + khung chat chính.
export function SalePage() {
  return (
    <div className="chat-shell">
      <SessionList />
      <Routes>
        <Route path="sessions/:sessionId" element={<ChatWindow />} />
        <Route
          path="*"
          element={
            <div className="chat-page">
              <div className="chat-messages">
                <div className="chat-messages-inner">
                  <div className="chat-empty">
                    <div className="chat-empty-icon">
                      <SparkleIcon size={26} />
                    </div>
                    <h2 className="chat-empty-title">Chào mừng tới SalesMate</h2>
                    <p className="chat-empty-text">
                      Chọn một phiên tư vấn ở thanh bên, hoặc tạo phiên khách hàng mới để bắt đầu.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          }
        />
      </Routes>
    </div>
  );
}
