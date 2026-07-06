import { useState } from "react";

export default function Composer({ onSend, disabled, onClear }) {
  const [value, setValue] = useState("");

  const submit = () => {
    const q = value.trim();
    if (!q || disabled) return;
    onSend(q);
    setValue("");
  };

  return (
    <div className="composer">
      <div className="composer-inner">
        <textarea
          rows={1}
          placeholder="e.g., What are the key points of Unit 1?"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button className="send-btn" onClick={submit} disabled={disabled || !value.trim()}>
          Ask
        </button>
      </div>
      <div className="composer-hint">
        <span>Enter to send · Shift+Enter for a new line</span>
        {onClear ? (
          <button className="clear-link" onClick={onClear} type="button">
            Clear conversation
          </button>
        ) : (
          <span>Powered by Groq</span>
        )}
      </div>
    </div>
  );
}
