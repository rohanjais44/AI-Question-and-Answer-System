export default function SettingsPanel({ models, model, setModel, topK, setTopK }) {
  return (
    <>
      <div className="field">
        <label>Model</label>
        <select value={model} onChange={(e) => setModel(e.target.value)}>
          {models.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label>
          Passages retrieved <span className="value">{topK}</span>
        </label>
        <input
          type="range"
          min="1"
          max="8"
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
        />
      </div>
    </>
  );
}
