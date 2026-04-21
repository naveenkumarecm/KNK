import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = async () => {
    const prompt = input.trim();
    if (!prompt || loading) return;

    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: prompt }]);
    setLoading(true);

    // Add empty assistant message for streaming
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    try {
      const res = await fetch(`${API_URL}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt, session_id: sessionId }),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const event = JSON.parse(line.slice(6));
            if (event.type === 'session') {
              setSessionId(event.session_id);
            } else if (event.type === 'text') {
              setMessages(prev => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === 'assistant') {
                  updated[updated.length - 1] = { ...last, content: last.content + event.content };
                }
                return updated;
              });
            }
          } catch {}
        }
      }
    } catch (err) {
      setMessages(prev => {
        const updated = [...prev];
        updated[updated.length - 1] = { role: 'assistant', content: `Error: ${err.message}` };
        return updated;
      });
    }
    setLoading(false);
  };

  const newSession = () => {
    setSessionId(null);
    setMessages([]);
  };

  return (
    <div style={styles.container}>
      <div style={styles.banner}>
        <h1 style={styles.title}>✈️ AnyCompany AI Travel Assistant</h1>
        <p style={styles.subtitle}>Only Flight functionality for now</p>
      </div>

      <div style={styles.chatArea}>
        {messages.length === 0 && (
          <div style={styles.empty}>Ask me to search for flights!</div>
        )}
        {messages.map((msg, i) => (
          <div key={i} style={msg.role === 'user' ? styles.userRow : styles.assistantRow}>
            <div style={msg.role === 'user' ? styles.userBubble : styles.assistantBubble}>
              {msg.role === 'user' ? (
                msg.content
              ) : (
                <ReactMarkdown>{msg.content || '...'}</ReactMarkdown>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div style={styles.inputArea}>
        <button onClick={newSession} style={styles.newBtn} title="New session">🔄</button>
        <input
          style={styles.input}
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && sendMessage()}
          placeholder="e.g. Find flights from London to New York on April 1st"
          disabled={loading}
        />
        <button onClick={sendMessage} style={styles.sendBtn} disabled={loading}>
          {loading ? '⏳' : '➤'}
        </button>
      </div>
    </div>
  );
}

const styles = {
  container: {
    display: 'flex', flexDirection: 'column', height: '100vh',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    background: '#f5f5f5',
  },
  banner: {
    background: 'linear-gradient(135deg, #1a237e, #0d47a1)',
    color: '#fff', padding: '16px 24px', textAlign: 'center',
  },
  title: { margin: 0, fontSize: '1.5rem' },
  subtitle: { margin: '4px 0 0', fontSize: '0.85rem', opacity: 0.8 },
  chatArea: {
    flex: 1, overflowY: 'auto', padding: '16px 24px',
    display: 'flex', flexDirection: 'column', gap: '12px',
  },
  empty: { textAlign: 'center', color: '#999', marginTop: '40px', fontSize: '1.1rem' },
  userRow: { display: 'flex', justifyContent: 'flex-end' },
  assistantRow: { display: 'flex', justifyContent: 'flex-start' },
  userBubble: {
    background: '#1a237e', color: '#fff', padding: '10px 16px',
    borderRadius: '16px 16px 4px 16px', maxWidth: '70%', whiteSpace: 'pre-wrap',
  },
  assistantBubble: {
    background: '#fff', color: '#222', padding: '10px 16px',
    borderRadius: '16px 16px 16px 4px', maxWidth: '80%',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)', lineHeight: 1.5,
  },
  inputArea: {
    display: 'flex', gap: '8px', padding: '12px 24px',
    background: '#fff', borderTop: '1px solid #e0e0e0',
  },
  input: {
    flex: 1, padding: '12px 16px', fontSize: '1rem',
    border: '1px solid #ccc', borderRadius: '24px', outline: 'none',
  },
  sendBtn: {
    padding: '12px 20px', fontSize: '1.2rem', border: 'none',
    background: '#1a237e', color: '#fff', borderRadius: '24px', cursor: 'pointer',
  },
  newBtn: {
    padding: '12px 16px', fontSize: '1.1rem', border: '1px solid #ccc',
    background: '#fff', borderRadius: '24px', cursor: 'pointer',
  },
};

export default App;
