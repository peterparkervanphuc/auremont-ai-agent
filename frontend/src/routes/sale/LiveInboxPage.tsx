import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { saleLiveApi } from "../../api/saleLive";
import type { LiveInboxEntry } from "../../types";
import { parseServerDate } from "../../utils/datetime";
import { ArrowRightIcon, ChatIcon, ClockIcon, UsersIcon } from "../../components/Icons";

const POLL_INTERVAL_MS = 5000;

function formatWaitTime(iso: string | null): string {
  if (!iso) return "";
  const started = parseServerDate(iso).getTime();
  if (Number.isNaN(started)) return "";
  const minutes = Math.max(0, Math.round((Date.now() - started) / 60000));
  if (minutes < 1) return "vừa mới xong";
  return `${minutes} phút trước`;
}

// "Khách đang chờ" — the Sale/Admin queue of customers the AI has handed off to a live
// person (see the SessionStatus state machine in backend/core/enums.py), plus this Sale's
// own already-claimed conversations. Both lists matter: claiming a session removes it from
// the waiting queue, so without the second list a Sale who navigates away (or logs back in
// later) would have no way back to a customer they're already chatting with. Polled rather
// than pushed — see the plan's real-time decision (polling first, WebSocket is a later
// upgrade).
export function LiveInboxPage() {
  const [waiting, setWaiting] = useState<LiveInboxEntry[]>([]);
  const [mine, setMine] = useState<LiveInboxEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [claimingId, setClaimingId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const reload = useCallback(() => {
    Promise.all([saleLiveApi.listWaiting(), saleLiveApi.listMine()])
      .then(([waitingRows, mineRows]) => {
        setWaiting(waitingRows);
        setMine(mineRows);
      })
      .catch(() => {
        setWaiting([]);
        setMine([]);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    reload();
    const interval = setInterval(reload, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [reload]);

  const claim = async (sessionId: number) => {
    if (claimingId) return;
    setClaimingId(sessionId);
    setError(null);
    try {
      await saleLiveApi.claim(sessionId);
      navigate(`/live-inbox/${sessionId}`);
    } catch {
      setError("Khách này vừa được chuyên viên khác tiếp nhận — danh sách đã được làm mới.");
      reload();
    } finally {
      setClaimingId(null);
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">Khách đang chờ</h2>
      <p className="page-sub">
        Khách đã được AI kết nối tới chuyên viên — bấm Tiếp nhận để đọc lại lịch sử và trả lời trực tiếp.
      </p>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: 16 }}>
          {error}
        </div>
      )}

      {!loading && mine.length > 0 && (
        <div style={{ marginBottom: 28 }}>
          <h3 className="live-inbox-section-title">Chat với khách hàng</h3>
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            {mine.map((e) => (
              <button
                key={e.session_id}
                type="button"
                className="live-inbox-row live-inbox-row--clickable"
                onClick={() => navigate(`/live-inbox/${e.session_id}`)}
              >
                <div className="live-inbox-row-info">
                  <span className="live-inbox-row-name">{e.customer_label}</span>
                  <span className="live-inbox-row-preview">{e.last_message_preview}</span>
                </div>
                <span className="btn btn-outline btn-sm">
                  <ChatIcon size={14} />
                  Tiếp tục chat
                </span>
              </button>
            ))}
          </div>
        </div>
      )}

      <h3 className="live-inbox-section-title">Đang chờ tiếp nhận</h3>
      {loading ? (
        <div className="empty-state">
          <p>Đang tải...</p>
        </div>
      ) : waiting.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <UsersIcon size={26} />
          </div>
          <p>Chưa có khách nào đang chờ.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {waiting.map((e) => (
            <div key={e.session_id} className="live-inbox-row">
              <div className="live-inbox-row-info">
                <span className="live-inbox-row-name">{e.customer_label}</span>
                <span className="live-inbox-row-preview">{e.last_message_preview}</span>
                <span className="live-inbox-row-wait">
                  <ClockIcon size={12} />
                  {formatWaitTime(e.waiting_since)}
                </span>
              </div>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => claim(e.session_id)}
                disabled={claimingId !== null}
              >
                Tiếp nhận
                <ArrowRightIcon size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
