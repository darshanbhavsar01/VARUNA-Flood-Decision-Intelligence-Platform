import { useState } from "react";
import HomeView from "./views/HomeView.jsx";
import CommandView from "./views/CommandView.jsx";
import CitizenView from "./views/CitizenView.jsx";

export default function App() {
  const [view, setView] = useState("home");
  return (
    <div className="h-full flex flex-col">
      {view === "home" && <HomeView view={view} setView={setView} />}
      {view === "command" && <CommandView view={view} setView={setView} />}
      {view === "citizen" && <CitizenView view={view} setView={setView} />}
    </div>
  );
}
