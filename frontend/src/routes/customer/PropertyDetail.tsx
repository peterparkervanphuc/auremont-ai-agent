import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { InventoryUnitResponse } from "../../types";
import { ChatbotWidget } from "./ChatbotWidget";

// CLAUDE.md §6.3.a step 3 — mặt bằng, tiện ích, giá công khai, hình ảnh.
export function PropertyDetail() {
  const { propertyId } = useParams<{ propertyId: string }>();
  const [unit, setUnit] = useState<InventoryUnitResponse | null>(null);
  const [imageUrls, setImageUrls] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!propertyId) return;
    api
      .get<InventoryUnitResponse>(`/inventory/${propertyId}`)
      .then(setUnit)
      .catch((err) => setError(err.message));
  }, [propertyId]);

  useEffect(() => {
    if (!unit || unit.images.length === 0) return;
    Promise.all(unit.images.map((img) => api.get<{ url: string }>(`/inventory/images/${img.id}/url`))).then((results) =>
      setImageUrls(results.map((r) => r.url)),
    );
  }, [unit]);

  if (error) return <p>Không tìm thấy BĐS: {error}</p>;
  if (!unit) return <p>Đang tải...</p>;

  return (
    <div>
      <h2>{unit.unit_type ?? "Căn hộ"} — {unit.unit_code}</h2>
      <p>Diện tích: {unit.area_sqm ?? "—"} m²</p>
      <p>Giá: {unit.price ?? "Liên hệ"}</p>
      <p>Cập nhật lần cuối: {new Date(unit.updated_at).toLocaleDateString("vi-VN")}</p>
      {!unit.has_images && <p>Chưa có hình ảnh</p>}
      {imageUrls.map((url) => (
        <img key={url} src={url} alt="Mặt bằng" />
      ))}

      <ChatbotWidget />
    </div>
  );
}
