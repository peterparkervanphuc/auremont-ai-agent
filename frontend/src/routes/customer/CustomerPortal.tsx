import { Route, Routes } from "react-router-dom";
import { PropertyDetail } from "./PropertyDetail";
import { PropertyList } from "./PropertyList";

// CLAUDE.md §3 — public root URL, no login required to browse.
export function CustomerPortal() {
  return (
    <Routes>
      <Route index element={<PropertyList />} />
      <Route path="properties/:propertyId" element={<PropertyDetail />} />
    </Routes>
  );
}
