import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { CheckIcon, LoaderIcon } from "../../components/Icons";

interface SettingsResponse {
  verifier_threshold_sale: number;
}

// General settings — minimum confidence threshold for the Verifier Agent.
export function SettingsTab() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.get<SettingsResponse>("/admin/settings").then(setSettings).catch(() => {});
  }, []);

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    setSaved(false);
    try {
      const updated = await api.put<SettingsResponse>("/admin/settings", settings);
      setSettings(updated);
      setSaved(true);
    } finally {
      setSaving(false);
    }
  };

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
          <input
            type="number"
            step="0.01"
            min="0"
            max="1"
            value={settings.verifier_threshold_sale}
            onChange={(e) => setSettings({ ...settings, verifier_threshold_sale: Number(e.target.value) })}
          />
          <span className="field-hint">Giá trị từ 0 đến 1 — dưới ngưỡng này AI sẽ từ chối trả lời.</span>
        </label>

        <div style={{ height: 18 }} />

        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <button onClick={save} disabled={saving} className="btn btn-primary">
            {saving && <LoaderIcon size={16} className="icon-spin" />}
            Lưu thay đổi
          </button>
          {saved && (
            <span className="hitl-confirmed">
              <CheckIcon size={16} />
              Đã lưu
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
