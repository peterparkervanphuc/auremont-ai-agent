import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { InventoryBulkUploadPreview, InventoryUnitResponse } from "../../types";

// CLAUDE.md §6.6 — Kênh 1: upload Excel hàng loạt + .zip ảnh; Kênh 2: Form thêm/sửa 1 căn lẻ.
export function InventoryTab() {
  const [units, setUnits] = useState<InventoryUnitResponse[]>([]);
  const [unitCode, setUnitCode] = useState("");
  const [projectId, setProjectId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const [excelFile, setExcelFile] = useState<File | null>(null);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<InventoryBulkUploadPreview | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);

  const loadUnits = () => api.get<InventoryUnitResponse[]>("/admin/inventory").then(setUnits);

  useEffect(() => {
    loadUnits();
  }, []);

  const createUnit = async () => {
    setFormError(null);
    try {
      await api.post("/admin/inventory", { unit_code: unitCode, project_id: projectId });
      setUnitCode("");
      setProjectId("");
      loadUnits();
    } catch (err) {
      // Mã căn trùng -> 409, CLAUDE.md §6.6.b bước 5.
      setFormError((err as Error).message);
    }
  };

  const removeUnit = async (unitId: number) => {
    await api.delete(`/admin/inventory/${unitId}`);
    loadUnits();
  };

  const runPreview = async () => {
    if (!excelFile) return;
    setBulkError(null);
    const body = new FormData();
    body.append("excel_file", excelFile);
    if (zipFile) body.append("images_zip", zipFile);
    try {
      const result = await api.postForm<InventoryBulkUploadPreview>("/admin/inventory/bulk-upload/preview", body);
      setPreview(result);
    } catch (err) {
      // Thiếu cột bắt buộc -> 422, CLAUDE.md §6.6.a bước 2.
      setBulkError((err as Error).message);
    }
  };

  const confirmBulkUpload = async () => {
    if (!excelFile) return;
    const body = new FormData();
    body.append("excel_file", excelFile);
    if (zipFile) body.append("images_zip", zipFile);
    await api.postForm("/admin/inventory/bulk-upload/confirm", body);
    setPreview(null);
    setExcelFile(null);
    setZipFile(null);
    loadUnits();
  };

  return (
    <div>
      <h3>Quản lý Tồn kho</h3>

      <section>
        <h4>Kênh 1 — Upload Excel hàng loạt</h4>
        <input type="file" accept=".xlsx" onChange={(e) => setExcelFile(e.target.files?.[0] ?? null)} />
        <input type="file" accept=".zip" onChange={(e) => setZipFile(e.target.files?.[0] ?? null)} />
        <button onClick={runPreview} disabled={!excelFile}>
          Xem trước
        </button>
        {bulkError && <p>Lỗi: {bulkError}</p>}
        {preview && (
          <div>
            <p>
              Tổng {preview.total} căn — {preview.missing_images} căn chưa có hình ảnh.
            </p>
            <table>
              <thead>
                <tr>
                  <th>Mã căn</th>
                  <th>Ảnh</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((row) => (
                  <tr key={row.unit_code}>
                    <td>{row.unit_code}</td>
                    <td>{row.has_image ? "Đã có ảnh" : "Chưa có hình ảnh"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <button onClick={confirmBulkUpload}>Xác nhận lưu</button>
          </div>
        )}
      </section>

      <section>
        <h4>Kênh 2 — Thêm căn lẻ</h4>
        <input placeholder="Mã căn" value={unitCode} onChange={(e) => setUnitCode(e.target.value)} />
        <input placeholder="Dự án (ID)" value={projectId} onChange={(e) => setProjectId(e.target.value)} />
        <button onClick={createUnit} disabled={!unitCode || !projectId}>
          Lưu
        </button>
        {formError && <p>Lỗi: {formError}</p>}
      </section>

      <section>
        <h4>Danh sách căn</h4>
        <table>
          <thead>
            <tr>
              <th>Mã căn</th>
              <th>Dự án</th>
              <th>Trạng thái</th>
              <th>Cập nhật</th>
              <th>Xoá</th>
            </tr>
          </thead>
          <tbody>
            {units.map((u) => (
              <tr key={u.id}>
                <td>{u.unit_code}</td>
                <td>{u.project_id}</td>
                <td>{u.status}</td>
                <td>{new Date(u.updated_at).toLocaleDateString("vi-VN")}</td>
                <td>
                  <button onClick={() => removeUnit(u.id)}>Xoá</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
