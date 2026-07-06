export default function ViewSwitch({ view, setView }) {
  return (
    <div className="flex rounded-lg border border-ink-600 overflow-hidden text-sm">
      {[
        ["command", "Command"],
        ["citizen", "Citizen"],
      ].map(([id, label]) => (
        <button
          key={id}
          onClick={() => setView(id)}
          className={`px-3 py-1 transition ${
            view === id ? "bg-accent text-ink-900 font-semibold"
                        : "text-slate-400 hover:text-slate-200"}`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
