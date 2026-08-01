import { useEffect, useState } from "react";
import { api } from "../../api/client";

interface SettingsResponse {
  verifier_threshold_sale: number;
  verifier_threshold_public: number;
}

// CLAUDE.md §6.5 Cài đặt chung — ngưỡng tin cậy tối thiểu cho Chatbot công khai.
export function SettingsTab() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);

  useEffect(() => {
    api.get<SettingsResponse>("/admin/settings").then(setSettings);
  }, []);

  const save = async () => {
    if (!settings) return;
    const updated = await api.put<SettingsResponse>("/admin/settings", settings);
    setSettings(updated);
  };

  if (!settings) return <p>Đang tải...</p>;

  return (
    <div>
      <h3>Cài đặt chung</h3>
      <label>
        Ngưỡng tin cậy — Sale
        <input
          type="number"
          step="0.01"
          value={settings.verifier_threshold_sale}
          onChange={(e) => setSettings({ ...settings, verifier_threshold_sale: Number(e.target.value) })}
        />
      </label>
      <label>
        Ngưỡng tin cậy — Chatbot công khai
        <input
          type="number"
          step="0.01"
          value={settings.verifier_threshold_public}
          onChange={(e) => setSettings({ ...settings, verifier_threshold_public: Number(e.target.value) })}
        />
      </label>
      <button onClick={save}>Lưu</button>
    </div>
  );
}
