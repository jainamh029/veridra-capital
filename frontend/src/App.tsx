import { BrowserRouter, Routes, Route, useLocation } from "react-router-dom";
import { useEffect } from "react";
import Home from "@/pages/Home";
import Overview from "@/pages/console/Overview";
import Verification from "@/pages/console/Verification";
import Approvals from "@/pages/console/Approvals";
import CashPlanning from "@/pages/console/CashPlanning";
import Forecasting from "@/pages/console/Forecasting";
import K1Routing from "@/pages/console/K1Routing";

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [pathname]);
  return null;
}

export default function App() {
  return (
    <BrowserRouter>
      <ScrollToTop />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/console" element={<Overview />} />
        <Route path="/console/verification" element={<Verification />} />
        <Route path="/console/approvals" element={<Approvals />} />
        <Route path="/console/cash-planning" element={<CashPlanning />} />
        <Route path="/console/forecasting" element={<Forecasting />} />
        <Route path="/console/k1-routing" element={<K1Routing />} />
      </Routes>
    </BrowserRouter>
  );
}
