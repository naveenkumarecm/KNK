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
      <div style={ipStyles.timestamp}>Last checked: {ipIntelligence.lastSeenTimestamp}</div>
    </div>
  );
}

function PurposeAnalysisPanel({ result, loading }) {
  if (loading) {
    return (
      <div style={ipStyles.panel}>
        <div style={ipStyles.header}>🔍 Purpose Analysis</div>
        <div style={ipStyles.loading}>Analyzing payment purpose...</div>
      </div>
    );
  }
  if (!result) return null;
  const { purposeAnalysis, riskAssessment } = result;
  if (!purposeAnalysis) return null;
  const riskColor = getRiskColor(riskAssessment?.decision);
  const scamColor = getScamColor(purposeAnalysis.scamIndicator);

  return (
    <div style={ipStyles.panel}>
      <div style={ipStyles.header}>📋 Purpose of Payment Report</div>
      <div style={ipStyles.grid}>
        <div style={ipStyles.card}>
          <div style={ipStyles.cardTitle}>Declared Purpose</div>
          <div style={ipStyles.cardValue}>{purposeAnalysis.declaredPurpose}</div>
        </div>
        <div style={ipStyles.card}>
          <div style={ipStyles.cardTitle}>Category</div>
          <div style={ipStyles.cardValue}>{purposeAnalysis.purposeCategory}</div>
        </div>
        <div style={{...ipStyles.card, borderLeft: `4px solid ${scamColor}`}}>
          <div style={ipStyles.cardTitle}>Scam Indicator</div>
          <div style={{...ipStyles.cardValue, color: scamColor, fontWeight: 'bold'}}>
            {purposeAnalysis.scamIndicator}
          </div>
        </div>
        <div style={{...ipStyles.card, borderLeft: `4px solid ${riskColor}`}}>
          <div style={ipStyles.cardTitle}>Decision</div>
          <div style={{...ipStyles.cardValue, color: riskColor, fontWeight: 'bold'}}>
            {riskAssessment?.decision || 'N/A'}
          </div>
        </div>
      </div>
      <div style={ipStyles.grid}>
        <div style={ipStyles.card}>
          <div style={ipStyles.cardTitle}>Confidence Score</div>
          <div style={ipStyles.cardValue}>{(purposeAnalysis.confidenceScore * 100).toFixed(0)}%</div>
        </div>
        <div style={ipStyles.card}>
          <div style={ipStyles.cardTitle}>Purpose Risk Score</div>
          <div style={{...ipStyles.cardValue, color: getScoreColor(riskAssessment?.purposeRiskScore || 0)}}>
            {riskAssessment?.purposeRiskScore || 0}/100
          </div>
        </div>
      </div>
      <div style={ipStyles.flagsSection}>
        <div style={ipStyles.flagsTitle}>Detection Flags</div>
        <div style={ipStyles.flags}>
          <FlagBadge label="Scam Pattern" active={purposeAnalysis.scamIndicator !== 'NONE'} />
          <FlagBadge label="Historical Deviation" active={purposeAnalysis.historicalDeviation} />
          <FlagBadge label="Urgency Detected" active={purposeAnalysis.urgencyDetected} />
          <FlagBadge label="High-Risk Category" active={['INVESTMENT','UNKNOWN'].includes(purposeAnalysis.purposeCategory)} />
        </div>
      </div>
      {purposeAnalysis.matchedPatterns?.length > 0 && (
        <div style={ipStyles.factorsSection}>
          <div style={ipStyles.flagsTitle}>Matched Patterns</div>
          <div style={ipStyles.factors}>
            {purposeAnalysis.matchedPatterns.map((p, i) => (
              <span key={i} style={ipStyles.factorBadge}>{p}</span>
            ))}
          </div>
        </div>
      )}
      {riskAssessment?.customerWarnings?.length > 0 && (
        <div style={purposeStyles.warningsSection}>
          <div style={ipStyles.flagsTitle}>⚠️ Customer Warnings</div>
          {riskAssessment.customerWarnings.map((warning, i) => (
            <div key={i} style={purposeStyles.warningBox}>{warning}</div>
          ))}
        </div>
      )}
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
      <div style={ipStyles.timestamp}>Analyzed: {purposeAnalysis.analysisTimestamp}</div>
    </div>
  );
}

function FlagBadge({ label, active }) {
  return (
    <span style={{
      ...ipStyles.badge,
      background: active ? '#fde8e8' : '#e8f8ed',
      color: active ? '#9b1c1c' : '#1e6f3e',
      border: `1px solid ${active ? '#e8a0a0' : '#8fd4a4'}`,
    }}>
      {active ? '⚠️' : '✓'} {label}
    </span>
  );
}

function getRiskColor(decision) {
  switch (decision) {
    case 'BLOCK': return '#c0392b';
    case 'STEP_UP_AUTH': return '#d35400';
    case 'HIGH_RISK': return '#c0392b';
    case 'MEDIUM_RISK': return '#d4a017';
    case 'DELAY': return '#d4a017';
    case 'CONFIRM': return '#2874a6';
    case 'LOW_RISK': return '#1e8449';
    case 'ALLOW': return '#1e8449';
    default: return '#6c5b7b';
  }
}

function getScoreColor(score) {
  if (score >= 70) return '#c0392b';
  if (score >= 40) return '#d4a017';
  return '#1e8449';
}

function getScamColor(indicator) {
  if (indicator === 'NONE') return '#1e8449';
  if (indicator === 'INVOICE_REDIRECTION') return '#c0392b';
  return '#d35400';
}

function formatAction(action) {
  const actions = {
    'STEP_UP_AUTHENTICATION': '🔐 Require step-up authentication',
    'BLOCK_OR_MANUAL_REVIEW': '🚫 Block transaction / Send for manual review',
    'DELAY_AND_WARNING': '⏳ Delay processing + display warning',
    'TEMPORARY_THROTTLE': '🔄 Apply temporary rate throttle',
    'WARNING_AND_STEP_UP': '🔐 Warning + step-up authentication',
    'DELAY_AND_REVIEW': '⏳ Delay and review',
    'CUSTOMER_CONFIRMATION': '✋ Require customer confirmation',
    'BLOCK': '🚫 Block transaction',
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
  const [purposeInput, setPurposeInput] = useState('');
  const [purposeAmount, setPurposeAmount] = useState('');
  const [purposeResult, setPurposeResult] = useState(null);
  const [purposeLoading, setPurposeLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (!loading && activeTab === 'chat') {
      inputRef.current?.focus();
    }
  }, [loading, activeTab]);

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
                  let text = event.content;
                  // Replace agent execution messages with friendly status
                  if (text.match(/\[Executing:.*?\]/)) {
                    text = text.replace(/\[Executing:.*?\]/g, '🔄 *Working on it... connecting with our travel services*\n\n');
                  }
                  updated[updated.length - 1] = { ...last, content: last.content + text };
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
      if (transactionAmount) body.transactionAmount = parseFloat(transactionAmount);
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

  const checkPurpose = async () => {
    const ref = purposeInput.trim();
    if (!ref) return;
    setPurposeLoading(true);
    setPurposeResult(null);
    try {
      const body = { paymentReference: ref };
      if (purposeAmount) body.transactionAmount = parseFloat(purposeAmount);
      const res = await fetch(`${API_URL}/api/purpose-analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      setPurposeResult(data);
    } catch (err) {
      setPurposeResult({ error: err.message });
    }
    setPurposeLoading(false);
  };

  const newSession = () => { setSessionId(null); setMessages([]); };

  return (
    <div style={styles.container}>
      <div style={styles.banner}>
        <div style={styles.bannerInner}>
          <h1 style={styles.title}>AnyCompany</h1>
          <p style={styles.subtitle}>Fraud Intelligence Platform</p>
          <div style={styles.bannerAccent}></div>
        </div>
      </div>

      <div style={styles.tabs}>
        <button onClick={() => setActiveTab('chat')} style={activeTab === 'chat' ? styles.activeTab : styles.tab}>
          💬 Travel Assistant
        </button>
        <button onClick={() => setActiveTab('ipIntel')} style={activeTab === 'ipIntel' ? styles.activeTab : styles.tab}>
          🛡️ IP Intelligence
        </button>
        <button onClick={() => setActiveTab('purpose')} style={activeTab === 'purpose' ? styles.activeTab : styles.tab}>
          📋 Purpose Analysis
        </button>
      </div>

      {activeTab === 'chat' && (
        <>
          <div style={styles.chatArea}>
            {messages.length === 0 && (
              <div style={styles.empty}>
                <div style={styles.emptyIcon}>✈️</div>
                <div style={styles.emptyText}>Ask me to search for flights</div>
                <div style={styles.emptyHint}>Try: "Find flights from London to New York"</div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} style={msg.role === 'user' ? styles.userRow : styles.assistantRow}>
                <div style={msg.role === 'user' ? styles.userBubble : styles.assistantBubble}>
                  {msg.role === 'user' ? msg.content : <ReactMarkdown>{msg.content || '...'}</ReactMarkdown>}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>
          <div style={styles.inputArea}>
            <button onClick={newSession} style={styles.newBtn} title="New session">🔄</button>
            <input ref={inputRef} style={styles.input} value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && sendMessage()}
              placeholder="e.g. Find flights from London to New York on April 1st" disabled={loading} />
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
              Real-time IP risk profiling. Detects VPN, Proxy, TOR networks, geo-anomalies, and velocity spikes.
            </p>
            <div style={ipStyles.inputRow}>
              <input style={ipStyles.ipInput} value={ipInput} onChange={e => setIpInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && checkIp()}
                placeholder="Enter IP address (e.g., 185.220.100.240)" />
              <input style={ipStyles.amountInput} value={transactionAmount}
                onChange={e => setTransactionAmount(e.target.value)} placeholder="Amount ($)" type="number" />
              <button onClick={checkIp} style={ipStyles.checkBtn} disabled={ipLoading}>
                {ipLoading ? '⏳' : '🔍 Analyze'}
              </button>
            </div>
            <div style={ipStyles.sampleIps}>
              <span style={ipStyles.sampleLabel}>Quick test:</span>
              <button style={ipStyles.sampleBtn} onClick={() => setIpInput('185.220.100.240')}>TOR Node</button>
              <button style={ipStyles.sampleBtn} onClick={() => setIpInput('10.8.0.1')}>VPN</button>
              <button style={ipStyles.sampleBtn} onClick={() => setIpInput('203.0.113.50')}>Proxy</button>
              <button style={ipStyles.sampleBtn} onClick={() => setIpInput('192.168.1.100')}>Clean</button>
            </div>
          </div>
          <IPIntelligencePanel ipResult={ipResult} loading={ipLoading} />
          {ipResult?.fullRiskAssessment && (
            <div style={ipStyles.fullAssessment}>
              <div style={ipStyles.header}>📊 Full Risk Assessment</div>
              <div style={ipStyles.grid}>
                <div style={ipStyles.card}>
                  <div style={ipStyles.cardTitle}>Total Risk Score</div>
                  <div style={{...ipStyles.cardValue, fontSize: '2rem', color: getScoreColor(ipResult.fullRiskAssessment.totalRiskScore)}}>
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
                  <div style={ipStyles.cardTitle}>Latency</div>
                  <div style={ipStyles.cardValue}>{ipResult.fullRiskAssessment.processingTimeMs}ms {ipResult.fullRiskAssessment.withinSla ? '✅' : '⚠️'}</div>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {activeTab === 'purpose' && (
        <div style={ipStyles.container}>
          <div style={ipStyles.inputSection}>
            <h2 style={ipStyles.sectionTitle}>Purpose of Payment Intelligence</h2>
            <p style={ipStyles.description}>
              Semantic analysis of payment references. Detects investment scams, romance fraud, impersonation, and invoice redirection.
            </p>
            <div style={ipStyles.inputRow}>
              <input style={{...ipStyles.ipInput, flex: 3}} value={purposeInput}
                onChange={e => setPurposeInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && checkPurpose()}
                placeholder="Enter payment reference or purpose..." />
              <input style={ipStyles.amountInput} value={purposeAmount}
                onChange={e => setPurposeAmount(e.target.value)} placeholder="Amount ($)" type="number" />
              <button onClick={checkPurpose} style={ipStyles.checkBtn} disabled={purposeLoading}>
                {purposeLoading ? '⏳' : '📋 Analyze'}
              </button>
            </div>
            <div style={ipStyles.sampleIps}>
              <span style={ipStyles.sampleLabel}>Quick test:</span>
              <button style={ipStyles.sampleBtn} onClick={() => setPurposeInput('Urgent investment in crypto trading platform - guaranteed returns')}>Investment Scam</button>
              <button style={ipStyles.sampleBtn} onClick={() => setPurposeInput('Help my partner stuck abroad - hospital bill urgent')}>Romance Scam</button>
              <button style={ipStyles.sampleBtn} onClick={() => setPurposeInput('HMRC tax refund - verify identity immediately')}>Impersonation</button>
              <button style={ipStyles.sampleBtn} onClick={() => setPurposeInput('Updated bank details for invoice #4521 - new account number')}>Invoice Redirect</button>
              <button style={ipStyles.sampleBtn} onClick={() => setPurposeInput('Monthly rent payment to landlord')}>Clean</button>
            </div>
          </div>
          <PurposeAnalysisPanel result={purposeResult} loading={purposeLoading} />
          {purposeResult?.fullRiskAssessment && (
            <div style={ipStyles.fullAssessment}>
              <div style={ipStyles.header}>📊 Full Risk Assessment</div>
              <div style={ipStyles.grid}>
                <div style={ipStyles.card}>
                  <div style={ipStyles.cardTitle}>Total Risk Score</div>
                  <div style={{...ipStyles.cardValue, fontSize: '2rem', color: getScoreColor(purposeResult.fullRiskAssessment.totalRiskScore)}}>
                    {purposeResult.fullRiskAssessment.totalRiskScore}/100
                  </div>
                </div>
                <div style={ipStyles.card}>
                  <div style={ipStyles.cardTitle}>Risk Level</div>
                  <div style={ipStyles.cardValue}>{purposeResult.fullRiskAssessment.riskLevel}</div>
                </div>
                <div style={ipStyles.card}>
                  <div style={ipStyles.cardTitle}>Decision</div>
                  <div style={ipStyles.cardValue}>{purposeResult.fullRiskAssessment.decision}</div>
                </div>
                <div style={ipStyles.card}>
                  <div style={ipStyles.cardTitle}>Latency</div>
                  <div style={ipStyles.cardValue}>{purposeResult.fullRiskAssessment.processingTimeMs}ms {purposeResult.fullRiskAssessment.withinSla ? '✅' : '⚠️'}</div>
                </div>
              </div>
              <div style={ipStyles.breakdown}>
                <div style={ipStyles.flagsTitle}>Score Breakdown</div>
                <div style={ipStyles.breakdownGrid}>
                  {Object.entries(purposeResult.fullRiskAssessment.scoreBreakdown).map(([key, val]) => (
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
  container: { display: 'flex', flexDirection: 'column', height: '100vh',
    fontFamily: '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    background: '#f8f4ef' },
  banner: {
    background: 'linear-gradient(135deg, #4a1942 0%, #2d1b4e 50%, #1b3a5c 100%)',
    padding: '28px 32px', borderBottom: '3px solid #c9a84c',
    position: 'relative', overflow: 'hidden',
  },
  bannerInner: { position: 'relative', zIndex: 1, textAlign: 'center' },
  title: { margin: 0, fontSize: '1.9rem', color: '#f5e6c8',
    fontWeight: '700', letterSpacing: '3px', textTransform: 'uppercase' },
  subtitle: { margin: '6px 0 0', fontSize: '0.9rem', color: '#d4b896', letterSpacing: '1px' },
  bannerAccent: {
    position: 'absolute', top: 0, right: 0, width: '200px', height: '100%',
    background: 'linear-gradient(135deg, transparent, rgba(201,168,76,0.08))',
  },
  tabs: { display: 'flex', background: '#2d1b4e', borderBottom: '1px solid #5c3d6e', padding: '0 24px' },
  tab: { padding: '14px 28px', border: 'none', background: 'transparent', fontSize: '0.9rem',
    cursor: 'pointer', color: '#b89cc9', borderBottom: '3px solid transparent',
    transition: 'all 0.2s ease', letterSpacing: '0.5px' },
  activeTab: { padding: '14px 28px', border: 'none', background: 'transparent', fontSize: '0.9rem',
    cursor: 'pointer', color: '#f5e6c8', borderBottom: '3px solid #c9a84c', fontWeight: '600',
    letterSpacing: '0.5px' },
  chatArea: { flex: 1, overflowY: 'auto', padding: '24px 32px', display: 'flex',
    flexDirection: 'column', gap: '16px', background: '#f8f4ef' },
  empty: { textAlign: 'center', marginTop: '60px' },
  emptyIcon: { fontSize: '3rem', marginBottom: '12px' },
  emptyText: { color: '#4a1942', fontSize: '1.2rem', fontWeight: '500' },
  emptyHint: { color: '#7c6488', fontSize: '0.9rem', marginTop: '8px' },
  userRow: { display: 'flex', justifyContent: 'flex-end' },
  assistantRow: { display: 'flex', justifyContent: 'flex-start' },
  userBubble: { background: 'linear-gradient(135deg, #4a1942, #6b2d5b)', color: '#fdf8f0',
    padding: '12px 18px', borderRadius: '18px 18px 4px 18px', maxWidth: '70%',
    whiteSpace: 'pre-wrap', border: '1px solid #c9a84c', boxShadow: '0 3px 12px rgba(74,25,66,0.2)' },
  assistantBubble: { background: '#ffffff', color: '#2d1b4e', padding: '12px 18px',
    borderRadius: '18px 18px 18px 4px', maxWidth: '80%', border: '1px solid #e8ddd0',
    boxShadow: '0 3px 12px rgba(74,25,66,0.08)', lineHeight: 1.6 },
  inputArea: { display: 'flex', gap: '10px', padding: '16px 32px',
    background: '#fff9f2', borderTop: '2px solid #e8ddd0' },
  input: { flex: 1, padding: '14px 20px', fontSize: '0.95rem', border: '1px solid #d4c4b0',
    borderRadius: '12px', outline: 'none', background: '#ffffff', color: '#2d1b4e',
    transition: 'border-color 0.2s' },
  sendBtn: { padding: '14px 22px', fontSize: '1.1rem', border: 'none',
    background: 'linear-gradient(135deg, #4a1942, #6b2d5b)', color: '#f5e6c8',
    borderRadius: '12px', cursor: 'pointer', fontWeight: '700' },
  newBtn: { padding: '14px 18px', fontSize: '1rem', border: '1px solid #d4c4b0',
    background: '#ffffff', color: '#4a1942', borderRadius: '12px', cursor: 'pointer' },
};

const ipStyles = {
  container: { flex: 1, overflowY: 'auto', padding: '28px 32px', background: '#f8f4ef' },
  inputSection: { background: '#ffffff', borderRadius: '16px', padding: '28px',
    border: '1px solid #e8ddd0', marginBottom: '24px', boxShadow: '0 4px 20px rgba(74,25,66,0.08)' },
  sectionTitle: { margin: '0 0 8px', fontSize: '1.4rem', color: '#4a1942', fontWeight: '600' },
  description: { margin: '0 0 20px', color: '#7c6488', fontSize: '0.9rem', lineHeight: 1.5 },
  inputRow: { display: 'flex', gap: '10px', marginBottom: '14px' },
  ipInput: { flex: 2, padding: '14px 18px', fontSize: '0.95rem', border: '1px solid #d4c4b0',
    borderRadius: '10px', outline: 'none', background: '#fdf8f0', color: '#2d1b4e' },
  amountInput: { flex: 1, padding: '14px 18px', fontSize: '0.95rem', border: '1px solid #d4c4b0',
    borderRadius: '10px', outline: 'none', background: '#fdf8f0', color: '#2d1b4e' },
  checkBtn: { padding: '14px 24px', fontSize: '0.9rem', border: 'none',
    background: 'linear-gradient(135deg, #4a1942, #6b2d5b)', color: '#f5e6c8',
    borderRadius: '10px', cursor: 'pointer', fontWeight: '700', whiteSpace: 'nowrap',
    letterSpacing: '0.5px' },
  sampleIps: { display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' },
  sampleLabel: { fontSize: '0.8rem', color: '#7c6488' },
  sampleBtn: { padding: '6px 14px', fontSize: '0.78rem', border: '1px solid #d4c4b0',
    background: '#fdf8f0', color: '#4a1942', borderRadius: '20px', cursor: 'pointer',
    transition: 'all 0.2s' },
  panel: { background: '#ffffff', borderRadius: '16px', padding: '28px',
    border: '1px solid #e8ddd0', marginBottom: '24px', boxShadow: '0 4px 20px rgba(74,25,66,0.08)' },
  header: { fontSize: '1.1rem', fontWeight: '600', color: '#4a1942',
    marginBottom: '20px', paddingBottom: '10px', borderBottom: '2px solid #e8ddd0' },
  loading: { textAlign: 'center', padding: '24px', color: '#7c6488' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
    gap: '14px', marginBottom: '20px' },
  card: { background: '#fdf8f0', borderRadius: '12px', padding: '16px 20px',
    border: '1px solid #e8ddd0' },
  cardTitle: { fontSize: '0.7rem', color: '#7c6488', textTransform: 'uppercase',
    letterSpacing: '0.08em', marginBottom: '6px', fontWeight: '600' },
  cardValue: { fontSize: '1rem', color: '#2d1b4e', fontWeight: '500' },
  flagsSection: { marginBottom: '20px' },
  flagsTitle: { fontSize: '0.8rem', fontWeight: '700', color: '#4a1942', marginBottom: '10px',
    textTransform: 'uppercase', letterSpacing: '0.05em' },
  flags: { display: 'flex', gap: '8px', flexWrap: 'wrap' },
  badge: { padding: '6px 12px', borderRadius: '8px', fontSize: '0.78rem', fontWeight: '600' },
  factorsSection: { marginBottom: '20px' },
  factors: { display: 'flex', gap: '8px', flexWrap: 'wrap' },
  factorBadge: { padding: '5px 12px', borderRadius: '6px', fontSize: '0.72rem',
    background: '#f5ecd7', color: '#8b6914', border: '1px solid #c9a84c',
    fontFamily: '"JetBrains Mono", monospace', fontWeight: '500' },
  actionsSection: { marginBottom: '20px' },
  actionsList: { margin: '4px 0', paddingLeft: '20px', fontSize: '0.88rem', color: '#2d1b4e', lineHeight: 1.8 },
  timestamp: { fontSize: '0.72rem', color: '#9b8a9e', textAlign: 'right', fontStyle: 'italic' },
  fullAssessment: { background: '#ffffff', borderRadius: '16px', padding: '28px',
    border: '1px solid #e8ddd0', marginBottom: '24px', boxShadow: '0 4px 20px rgba(74,25,66,0.08)' },
  breakdown: { marginTop: '20px' },
  breakdownGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '10px' },
  breakdownItem: { display: 'flex', justifyContent: 'space-between', padding: '10px 14px',
    background: '#fdf8f0', borderRadius: '8px', border: '1px solid #e8ddd0' },
  breakdownLabel: { fontSize: '0.78rem', color: '#7c6488', textTransform: 'capitalize' },
  breakdownValue: { fontSize: '0.9rem', fontWeight: '700', color: '#4a1942' },
};

const purposeStyles = {
  warningsSection: { marginBottom: '20px' },
  warningBox: { background: 'linear-gradient(135deg, #fff8e8, #fdf2d5)', border: '1px solid #c9a84c',
    borderRadius: '10px', padding: '14px 18px', marginBottom: '10px', fontSize: '0.88rem',
    color: '#6b4c11', lineHeight: 1.6, boxShadow: '0 2px 8px rgba(201,168,76,0.12)' },
};

export default App;
