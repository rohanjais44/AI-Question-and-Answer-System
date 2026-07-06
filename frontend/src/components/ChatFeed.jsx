export default function ChatFeed({ turns }) {
  if (turns.length === 0) {
    return (
      <div className="empty-state">
        <span className="glyph">§</span>
        <h2>Ask something about your documents</h2>
        <p>
          Upload a PDF or text file in the sidebar, then ask a question here.
          Answers are grounded in passages retrieved from what you've
          uploaded.
        </p>
      </div>
    );
  }

  return (
    <>
      {turns.map((turn) => (
        <div className="qa-block" key={turn.id}>
          <div className="question-row">
            <span className="avatar">?</span>
            <h3>{turn.question}</h3>
          </div>

          {turn.status === "loading" && (
            <div className="answer-card loading">Retrieving passages…</div>
          )}

          {turn.status === "error" && (
            <div className="answer-card error">{turn.error}</div>
          )}

          {(turn.status === "streaming" || turn.status === "done") && (
            <div className="answer-card">
              <div className="answer-text">
                {turn.answer}
                {turn.status === "streaming" && <span className="cursor-blink" />}
              </div>

              {turn.sources?.length > 0 && (
                <details className="sources-toggle">
                  <summary>{turn.sources.length} source passage{turn.sources.length > 1 ? "s" : ""}</summary>
                  {turn.sources.map((s, idx) => (
                    <div className="excerpt-strip" key={idx}>
                      <div className="excerpt-meta">
                        <span>{s.source}</span>
                        <span className="score">{(s.score * 100).toFixed(0)}% match</span>
                      </div>
                      {s.excerpt}…
                    </div>
                  ))}
                </details>
              )}
            </div>
          )}
        </div>
      ))}
    </>
  );
}
