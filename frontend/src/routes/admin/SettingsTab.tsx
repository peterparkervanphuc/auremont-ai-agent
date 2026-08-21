import { useEffect, useState } from "react";
import { api } from "../../api/client";

interface SettingsResponse {
  verifier_threshold_sale: number;
}

// General settings — minimum confidence threshold for the Verifier Agent.
//
// Read-only on purpose. The field used to be editable with a "Lưu thay đổi" button that
// reported "Đã lưu" while the backend stored nothing, so an Admin could believe they had
// moved the threshold that decides when the AI refuses to answer. Showing the real value
// and where it comes from is more useful than an input that cannot take effect.
export function SettingsTab() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [failedToLoad, setFailedToLoad] = useState(false);

  useEffect(() => {
    api
      .get<SettingsResponse>("/admin/settings")
      .then((result) => {
        setSettings(result);
        setFailedToLoad(false);
      })
      .catch(() => setFailedToLoad(true));
  }, []);

  if (failedToLoad) {
    return (
      <div className="page">
        <h2 className="page-title">Cài đặt chung</h2>
        <div className="alert alert-danger">Không tải được cài đặt.</div>
      </div>
    );
  }

  if (!settings) {
    return (
      <div className="page">
        <div className="skeleton" style={{ height: 120 }} />
      </div>
    );
  }

  return (
    <div className="page" style={{ maxWidth: 620 }}>
      <h2 className="page-title">Cài đặt chung</h2>
      <p className="page-sub">Ngưỡng điểm Verifier tối thiểu — dưới ngưỡng, hệ thống báo "Không đủ thông tin".</p>

      <div className="card">
        <label className="field" style={{ marginBottom: 0 }}>
          Ngưỡng tin cậy — Sale
          <input type="number" value={settings.verifier_threshold_sale} readOnly disabled />
          <span className="field-hint">
            Giá trị từ 0 đến 1 — dưới ngưỡng này AI sẽ từ chối trả lời. Cấu hình qua biến môi trường{" "}
            <code>VERIFIER_THRESHOLD_SALE</code>, có hiệu lực sau khi khởi động lại dịch vụ.
          </span>
        </label>
      </div>
    </div>
  );
}
