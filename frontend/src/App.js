import { useState } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import EnergyAudit from "@/components/EnergyAudit";

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<EnergyAudit />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
