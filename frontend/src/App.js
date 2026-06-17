import React, { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

function IPIntelligencePanel({ ipResult, loading }) {
  if (loading) {
    return (
      <div style={ipStyles.panel}>
        <div style={ipStyles.header}>🔍 IP Intelligence</div>
        <div style={ipStyles.loading}>Analyzing IP address...</div>
      </div>
    );
  }

  if (!ipResult) return null;

  const { ipIntelligence, riskAssessment } = ipResult;
  if (!ipIntelligence) return null;

  const riskColor = getRiskColor(riskAssessment?.decision);
  const scoreColor = getScoreColor(ipIntelligence.ipReputationScore);

  return (
    <div style={ipStyles.panel}>
      <div style={ipStyles.header}>🛡️ IP Intelligence Report</div>

      <div style={ipStyles.grid}>
        <div style={ipStyles.card}>
          <div style={ipStyles.cardTitle}>IP Address</div>
          <div style={ipStyles.cardValue}>{ipIntelligence.ipAddress}</div>
        </div>

        <div style={ipStyles.card}>
          <div style={ipStyles.cardTitle}>Location</div>
          <div style={ipStyles.cardValue}>
            {ipIntelligence.city}, {ipIntelligence.region}, {ipIntelligence.country}
          </div>
        </div>

        <div style={{...ipStyles.card, borderLeft: `4px solid ${scoreColor}`}}>
          <div style={ipStyles.cardTitle}>Reputation Score</div>
          <div style={{...ipStyles.cardValue, color: scoreColor, fontSize: '1.5rem'}}>
            {ipIntelligence.ipReputationScore}/100
          </div>
        </div>

        <div style={{...ipStyles.card, borderLeft: `4px solid ${riskColor}`}}>
          <div style={ipStyles.cardTitle}>Decision</div>
          <div style={{...ipStyles.cardValue, color: riskColor, fontWeight: 'bold'}}>
            {riskAssessment?.decision || 'N/A'}
          </div>
        </div>
      </div>

      <div style={ipStyles.flagsSection}>
        <div style={ipStyles.flagsTitle}>Detection Flags</div>
        <div style={ipStyles.flags}>
          <FlagBadge label="VPN" active={ipIntelligence.isVpn} />
          <FlagBadge label="Proxy" active={ipIntelligence.isProxy} />
          <FlagBadge label="TOR" active={ipIntelligence.isTor} />
          <FlagBadge label="High-Risk Geo" active={ipIntelligence.isHighRiskGeo} />
          <FlagBadge label="Velocity Alert" active={ipIntelligence.velocityFlag} />
          <FlagBadge label="New IP" active={ipIntelligence.isNewIp} />
        </div>
      </div>

      {riskAssessment?.riskFactors?.length > 0 && (
        <div style={ipStyles.factorsSection}>
          <div style={ipStyles.flagsTitle}>Risk Factors</div>
          <div style={ipStyles.factors}>
            {riskAssessment.riskFactors.map((factor, i) => (
              <span key={i} style={ipStyles.factorBadge}>{factor}</span>
            ))}
          </div>
        </div>
      )}

      {riskAssessment?.actions?.length > 0 && (
        <div style={ipStyles.actionsSection}>
          <div style={ipStyles.flagsTitle}>Recommended Actions</div>
          <ul style={ipStyles.actionsList}>
            {riskAssessment.actions.map((action, i) => (
              <li key={i}>{formatAction(action)}</li>
            ))}
          </ul>
        </div>
      )}

      <div style={ipStyles.timestamp}>
        Last checked: {ipIntelligence.lastSeenTimestamp}
      </div>
    </div>
  );
}

function FlagBadge({ label, active }) {
  return (
    <span style={{
      ...ipStyles.badge,
      background: active ? '#fee2e2' : '#f0fdf4',
      color: active ? '#dc2626' : '#16a34a',
      border: `1px solid ${active ? '#fca5a5' : '#86efac'}`,
    }}>
      {active ? '⚠️' : '✓'} {label}
    </span>
  );
}

function getRiskColor(decision) {
  switch (decision) {
    case 'BLOCK': return '#dc2626';
    case 'STEP_UP_AUTH': return '#ea580c';
    case 'HIGH_RISK': return '#dc2626';
    case 'MEDIUM_RISK': return '#d97706';
    case 'LOW_RISK': return '#16a34a';
    default: return '#6b7280';
  }
}

function getScoreColor(score) {
  if (score >= 70) return '#dc2626';
  if (score >= 40) return '#d97706';
  return '#16a34a';
}

function formatAction(action) {
  const actions = {
    'STEP_UP_AUTHENTICATION': '🔐 Require step-up authentication',
    'BLOCK_OR_MANUAL_REVIEW': '🚫 Block transaction / Send for manual review',
    'DELAY_AND_WARNING': '⏳ Delay processing + display warning',
    'TEMPORARY_THROTTLE': '🔄 Apply temporary rate throttle',
  };
  return actions[action] || action;
}

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [activeTab, setActiveTab] = useState('chat');
  const [ipInput, setIpInput] = useState('');
  const [ipResult, setIpResult] = useState(null);
  const [ipLoading, setIpLoading] = useState(false);
  const [transactionAmount, setTransactionAmount] = useState('');
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

  const checkIp = async () => {
    const ip = ipInput.trim();
    if (!ip) return;

    setIpLoading(true);
    setIpResult(null);

    try {
      const body = { ipAddress: ip };
      if (transactionAmount) {
        body.transactionAmount = parseFloat(transactionAmount);
      }

      const res = await fetch(`${API_URL}/api/ip-intelligence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      setIpResult(data);
    } catch (err) {
      setIpResult({ error: err.message });
    }
    setIpLoading(false);
  };

  const newSession = () => {
    setSessionId(null);
    setMessages([]);
  };

  return (
    <div style={styles.container}>
      <div style={styles.banner}>
        <h1 style={styles.title}>✈️ AnyCompany AI Travel Assistant</h1>
        <p style={styles.subtitle}>Flight Search & Booking | IP Intelligence Fraud Detection</p>
      </div>

      <div style={styles.tabs}>
        <button
          onClick={() => setActiveTab('chat')}
          style={activeTab === 'chat' ? styles.activeTab : styles.tab}
        >
          💬 Chat
        </button>
        <button
          onClick={() => setActiveTab('ipIntel')}
          style={activeTab === 'ipIntel' ? styles.activeTab : styles.tab}
        >
          🛡️ IP Intelligence
        </button>
      </div>

      {activeTab === 'chat' && (
        <>
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
        </>
      )}

      {activeTab === 'ipIntel' && (
        <div style={ipStyles.container}>
          <div style={ipStyles.inputSection}>
            <h2 style={ipStyles.sectionTitle}>Device IP Address Intelligence</h2>
            <p style={ipStyles.description}>
              Evaluate IP address risk profile for fraud detection. Checks VPN/Proxy/TOR usage,
              geo-location risk, velocity anomalies, and reputation scoring.
            </p>

            <div style={ipStyles.inputRow}>
              <input
                style={ipStyles.ipInput}
                value={ipInput}
                onChange={e => setIpInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && checkIp()}
                placeholder="Enter IP address (e.g., 185.220.100.240)"
              />
              <input
                style={ipStyles.amountInput}
                value={transactionAmount}
                onChange={e => setTransactionAmount(e.target.value)}
                placeholder="Amount ($)"
                type="number"
              />
              <button onClick={checkIp} style={ipStyles.checkBtn} disabled={ipLoading}>
                {ipLoading ? '⏳ Analyzing...' : '🔍 Analyze IP'}
              </button>
            </div>

            <div style={ipStyles.sampleIps}>
              <span style={ipStyles.sampleLabel}>Sample IPs to test:</span>
              <button style={ipStyles.sampleBtn} onClick={() => setIpInput('185.220.100.240')}>
                TOR Exit Node
              </button>
              <button style={ipStyles.sampleBtn} onClick={() => setIpInput('10.8.0.1')}>
                VPN
              </button>
              <button style={ipStyles.sampleBtn} onClick={() => setIpInput('203.0.113.50')}>
                Proxy + High-Risk Geo
              </button>
              <button style={ipStyles.sampleBtn} onClick={() => setIpInput('192.168.1.100')}>
                Clean IP
              </button>
            </div>
          </div>

          <IPIntelligencePanel ipResult={ipResult} loading={ipLoading} />

          {ipResult?.fullRiskAssessment && (
            <div style={ipStyles.fullAssessment}>
              <div style={ipStyles.header}>📊 Full Risk Assessment</div>
              <div style={ipStyles.grid}>
                <div style={ipStyles.card}>
                  <div style={ipStyles.cardTitle}>Total Risk Score</div>
                  <div style={{
                    ...ipStyles.cardValue,
                    fontSize: '2rem',
                    color: getScoreColor(ipResult.fullRiskAssessment.totalRiskScore)
                  }}>
                    {ipResult.fullRiskAssessment.totalRiskScore}/100
                  </div>
                </div>
                <div style={ipStyles.card}>
                  <div style={ipStyles.cardTitle}>Risk Level</div>
                  <div style={ipStyles.cardValue}>{ipResult.fullRiskAssessment.riskLevel}</div>
                </div>
                <div style={ipStyles.card}>
                  <div style={ipStyles.cardTitle}>Decision</div>
                  <div style={ipStyles.cardValue}>{ipResult.fullRiskAssessment.decision}</div>
                </div>
                <div style={ipStyles.card}>
                  <div style={ipStyles.cardTitle}>Processing Time</div>
                  <div style={ipStyles.cardValue}>
                    {ipResult.fullRiskAssessment.processingTimeMs}ms
                    {ipResult.fullRiskAssessment.withinSla ? ' ✅ Within SLA' : ' ⚠️ SLA Exceeded'}
                  </div>
                </div>
              </div>

              <div style={ipStyles.breakdown}>
                <div style={ipStyles.flagsTitle}>Score Breakdown</div>
                <div style={ipStyles.breakdownGrid}>
                  {Object.entries(ipResult.fullRiskAssessment.scoreBreakdown).map(([key, val]) => (
                    <div key={key} style={ipStyles.breakdownItem}>
                      <span style={ipStyles.breakdownLabel}>{key.replace('Score', '')}</span>
                      <span style={ipStyles.breakdownValue}>{val}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
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
  tabs: {
    display: 'flex', background: '#fff', borderBottom: '1px solid #e0e0e0',
    padding: '0 24px',
  },
  tab: {
    padding: '12px 24px', border: 'none', background: 'transparent',
    fontSize: '0.95rem', cursor: 'pointer', color: '#666',
    borderBottom: '3px solid transparent',
  },
  activeTab: {
    padding: '12px 24px', border: 'none', background: 'transparent',
    fontSize: '0.95rem', cursor: 'pointer', color: '#1a237e',
    borderBottom: '3px solid #1a237e', fontWeight: '600',
  },
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

const ipStyles = {
  container: {
    flex: 1, overflowY: 'auto', padding: '24px',
  },
  inputSection: {
    background: '#fff', borderRadius: '12px', padding: '24px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '20px',
  },
  sectionTitle: {
    margin: '0 0 8px', fontSize: '1.3rem', color: '#1a237e',
  },
  description: {
    margin: '0 0 16px', color: '#666', fontSize: '0.9rem',
  },
  inputRow: {
    display: 'flex', gap: '8px', marginBottom: '12px',
  },
  ipInput: {
    flex: 2, padding: '12px 16px', fontSize: '1rem',
    border: '1px solid #ccc', borderRadius: '8px', outline: 'none',
  },
  amountInput: {
    flex: 1, padding: '12px 16px', fontSize: '1rem',
    border: '1px solid #ccc', borderRadius: '8px', outline: 'none',
  },
  checkBtn: {
    padding: '12px 24px', fontSize: '0.95rem', border: 'none',
    background: '#1a237e', color: '#fff', borderRadius: '8px', cursor: 'pointer',
    whiteSpace: 'nowrap',
  },
  sampleIps: {
    display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap',
  },
  sampleLabel: {
    fontSize: '0.85rem', color: '#666',
  },
  sampleBtn: {
    padding: '6px 12px', fontSize: '0.8rem', border: '1px solid #ddd',
    background: '#f8f9fa', borderRadius: '16px', cursor: 'pointer',
  },
  panel: {
    background: '#fff', borderRadius: '12px', padding: '24px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '20px',
  },
  header: {
    fontSize: '1.1rem', fontWeight: '600', color: '#1a237e',
    marginBottom: '16px', paddingBottom: '8px', borderBottom: '1px solid #e5e7eb',
  },
  loading: {
    textAlign: 'center', padding: '20px', color: '#666',
  },
  grid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '12px', marginBottom: '16px',
  },
  card: {
    background: '#f8f9fa', borderRadius: '8px', padding: '12px 16px',
  },
  cardTitle: {
    fontSize: '0.75rem', color: '#666', textTransform: 'uppercase',
    letterSpacing: '0.05em', marginBottom: '4px',
  },
  cardValue: {
    fontSize: '1rem', color: '#1f2937', fontWeight: '500',
  },
  flagsSection: {
    marginBottom: '16px',
  },
  flagsTitle: {
    fontSize: '0.85rem', fontWeight: '600', color: '#374151',
    marginBottom: '8px',
  },
  flags: {
    display: 'flex', gap: '8px', flexWrap: 'wrap',
  },
  badge: {
    padding: '4px 10px', borderRadius: '12px', fontSize: '0.8rem',
    fontWeight: '500',
  },
  factorsSection: {
    marginBottom: '16px',
  },
  factors: {
    display: 'flex', gap: '8px', flexWrap: 'wrap',
  },
  factorBadge: {
    padding: '4px 10px', borderRadius: '4px', fontSize: '0.75rem',
    background: '#fef3c7', color: '#92400e', border: '1px solid #fcd34d',
    fontFamily: 'monospace',
  },
  actionsSection: {
    marginBottom: '16px',
  },
  actionsList: {
    margin: '4px 0', paddingLeft: '20px', fontSize: '0.9rem', color: '#374151',
  },
  timestamp: {
    fontSize: '0.75rem', color: '#9ca3af', textAlign: 'right',
  },
  fullAssessment: {
    background: '#fff', borderRadius: '12px', padding: '24px',
    boxShadow: '0 1px 3px rgba(0,0,0,0.1)', marginBottom: '20px',
  },
  breakdown: {
    marginTop: '16px',
  },
  breakdownGrid: {
    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
    gap: '8px',
  },
  breakdownItem: {
    display: 'flex', justifyContent: 'space-between', padding: '8px 12px',
    background: '#f8f9fa', borderRadius: '6px',
  },
  breakdownLabel: {
    fontSize: '0.8rem', color: '#666', textTransform: 'capitalize',
  },
  breakdownValue: {
    fontSize: '0.9rem', fontWeight: '600', color: '#1f2937',
  },
};

export default App;
