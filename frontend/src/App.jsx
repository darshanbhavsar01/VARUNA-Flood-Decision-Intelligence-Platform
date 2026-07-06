import { useState } from "react";
import CommandView from "./views/CommandView.jsx";
import CitizenView from "./views/CitizenView.jsx";

export default function App() {
  const [view, setView] = useState("command");
  return (
    <div className="h-full flex flex-col">
      {view === "command" ? (
        <CommandView view={view} setView={setView} />
      ) : (
        <CitizenView view={view} setView={setView} />
      )}
    </div>
  );
}
