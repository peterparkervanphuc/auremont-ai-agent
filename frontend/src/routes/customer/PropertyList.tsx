import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { InventoryUnitResponse } from "../../types";

// CLAUDE.md §6.3.a — public listing, no login required.
export function PropertyList() {
  const [units, setUnits] = useState<InventoryUnitResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<InventoryUnitResponse[]>("/inventory")
      .then(setUnits)
      .catch((err) => setError(err.message));
  }, []);

  // TODO: add filter controls (project, unit type, khu vực, khoảng giá) per CLAUDE.md §6.3.a step 2.

  if (error) return <p>Không tải được danh sách BĐS: {error}</p>;

  return (
    <div>
      <h2>Danh sách BĐS đang giao bán</h2>
      {units.length === 0 && <p>Chưa có BĐS nào được công bố.</p>}
      <ul>
        {units.map((u) => (
          <li key={u.id}>
            <Link to={`/properties/${u.id}`}>
              {u.unit_type ?? "Căn hộ"} — {u.price ?? "Liên hệ"}
            </Link>
            <small> · Cập nhật: {new Date(u.updated_at).toLocaleDateString("vi-VN")}</small>
          </li>
        ))}
      </ul>
    </div>
  );
}
