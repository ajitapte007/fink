import React, { useState, useRef, useEffect } from 'react';
import {
  Radar, RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, Legend, CartesianGrid
} from 'recharts';
import './App.css';

export default function App() {
  const [ticker, setTicker] = useState('');
  const [topTickerInput, setTopTickerInput] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const [agentData, setAgentData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' or 'historical'

  // Historical chart states
  const [selectedMetrics, setSelectedMetrics] = useState([]); // e.g. ['Revenue', 'Net Income']
  const [sliderStart, setSliderStart] = useState(0);
  const [sliderEnd, setSliderEnd] = useState(0);

  const chatEndRef = useRef(null);

  // Auto-scroll chat
  useEffect(() => {
    if (chatEndRef.current) {
      chatEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatHistory]);

  const triggerAnalysis = async (targetTicker, customMessage = "", isSilent = false) => {
    const messageToSend = customMessage.trim() || `Analyze ${targetTicker}`;

    if (!isSilent) {
      setChatHistory(prev => [...prev, { role: 'user', content: messageToSend, pathway: ["Coordinator Agent (Planning...)"] }]);
    }
    setLoading(true);

    try {
      const payload = JSON.stringify({ ticker: targetTicker, message: messageToSend });
      
      // Stage 1: Plan
      const planRes = await fetch('http://localhost:8000/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload
      }).then(r => r.json());
      
      setAgentData(prev => ({ ...(prev || {}), corporate_identity: planRes.corporate_identity }));
      setTicker(planRes.corporate_identity.ticker);
      setTopTickerInput(planRes.corporate_identity.ticker);

      const isHistorical = planRes.ui_state.active_tab === 'historical';
      setActiveTab(planRes.ui_state.active_tab);

      const recommendedMetrics = planRes.ui_state.selected_historical_metrics || [];
      setSelectedMetrics(recommendedMetrics.length > 0 ? [recommendedMetrics[0]] : []);

      if (!isSilent) {
        setChatHistory(prev => {
          const updated = [...prev];
          for (let i = updated.length - 1; i >= 0; i--) {
            if (updated[i].role === 'user') {
              updated[i] = { ...updated[i], pathway: ["Coordinator Agent (Done)", isHistorical ? "Historical Data Specialist (Retrieving...)" : "Sector/Stage Agents (Analyzing...)"] };
              break;
            }
          }
          return updated;
        });
      }

      // Always fetch historical data because it's purely programmatic and fast.
      // This ensures the Historical Tab works perfectly if the user clicks it manually later.
      const histPromise = fetch('http://localhost:8000/api/data/historical', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload
      }).then(r => r.json());

      // Stage 2: Branch Execution
      if (!isHistorical) {
        // Overview Flow
        const overviewPromise = fetch('http://localhost:8000/api/data/overview', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: payload
        }).then(r => r.json());

        const [overviewRes, histRes] = await Promise.all([overviewPromise, histPromise]);

        setAgentData(prev => ({
          ...prev,
          iron_triangle_scores: overviewRes.iron_triangle_scores,
          drilldown_matrix: overviewRes.drilldown_matrix,
          synthesis_summary: overviewRes.synthesis_summary,
          historical_chart_data: histRes.historical_chart_data
        }));

        if (!isSilent) {
          setChatHistory(prev => {
            const updated = [...prev];
            for (let i = updated.length - 1; i >= 0; i--) {
              if (updated[i].role === 'user') {
                updated[i] = { ...updated[i], pathway: planRes.agent_pathway };
                break;
              }
            }
            return [
              ...updated,
              { role: 'agent', content: "Overview ready." }
            ];
          });
        }
      } else {
        // Historical Flow
        const synthPayload = JSON.stringify({ ticker: targetTicker, message: messageToSend, active_tab: "historical" });
        const synthPromise = fetch('http://localhost:8000/api/chat/reply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: synthPayload
        }).then(r => r.json());

        histPromise.then(histRes => {
          setAgentData(prev => ({
            ...prev,
            historical_chart_data: histRes.historical_chart_data
          }));

          const hData = histRes.historical_chart_data || [];
          if (hData.length > 0) {
            let startIdx = 0;
            let endIdx = hData.length - 1;

            if (planRes.ui_state.start_date) {
              const idx = hData.findIndex(pt => pt.date >= planRes.ui_state.start_date);
              if (idx !== -1) startIdx = idx;
            }
            if (planRes.ui_state.end_date) {
              let lastIdx = hData.length - 1;
              for (let i = hData.length - 1; i >= 0; i--) {
                if (hData[i].date <= planRes.ui_state.end_date) {
                  lastIdx = i;
                  break;
                }
              }
              endIdx = lastIdx;
            }
            setSliderStart(startIdx);
            setSliderEnd(endIdx);
          }

          if (!isSilent) {
            setChatHistory(prev => {
              const updated = [...prev];
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].role === 'user') {
                  updated[i] = { ...updated[i], pathway: ["Coordinator Agent (Done)", "Historical Data Specialist (Done)", "Synthesis Specialist (Drafting...)"] };
                  break;
                }
              }
              return updated;
            });
          }
        });

        synthPromise.then(synthRes => {
          if (!isSilent) {
            setChatHistory(prev => {
              const updated = [...prev];
              for (let i = updated.length - 1; i >= 0; i--) {
                if (updated[i].role === 'user') {
                  updated[i] = { ...updated[i], pathway: planRes.agent_pathway };
                  break;
                }
              }
              return [
                ...updated,
                { role: 'agent', content: synthRes.synthesis_summary }
              ];
            });
          }
        });

        await Promise.all([histPromise, synthPromise]);
      }

    } catch (err) {
      console.error(err);
      if (!isSilent) {
        setChatHistory(prev => [
          ...prev,
          { role: 'agent', content: "[SYSTEM_ERROR] Failed to establish orchestration loop with Backend. Ensure FastAPI is running." }
        ]);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleTopInputKeyDown = (e) => {
    if (e.key === 'Enter' && topTickerInput.trim()) {
      triggerAnalysis(topTickerInput.trim().toUpperCase());
    }
  };

  const isPercentMetric = (metricName) => {
    if (!metricName) return false;
    const lower = metricName.toLowerCase();
    return lower.includes('yield') || lower.includes('ratio') || lower.includes('roic');
  };

  const formatNumberValue = (value, isPercent = false) => {
    const numValue = Number(value);
    if (value === null || value === undefined || isNaN(numValue)) return '';
    const absVal = Math.abs(numValue);
    
    let formatted = '';
    if (absVal >= 1.0e12) {
      formatted = (numValue / 1.0e12).toFixed(2) + 'T';
    } else if (absVal >= 1.0e9) {
      formatted = (numValue / 1.0e9).toFixed(2) + 'B';
    } else if (absVal >= 1.0e6) {
      formatted = (numValue / 1.0e6).toFixed(2) + 'M';
    } else if (absVal >= 1.0e3) {
      formatted = (numValue / 1.0e3).toFixed(2) + 'k';
    } else if (absVal < 10) {
      formatted = numValue.toFixed(2);
    } else {
      formatted = numValue.toFixed(1);
    }
    
    return isPercent ? `${formatted}%` : formatted;
  };

  const formatRightAxisTick = (value) => {
    const metricName = selectedMetrics[0] || '';
    const isPercent = isPercentMetric(metricName);
    return formatNumberValue(value, isPercent);
  };

  const tooltipFormatter = (value, name) => {
    const numValue = Number(value);
    if (value === null || value === undefined || isNaN(numValue)) {
      return ['', name];
    }
    if (name === 'Stock Price') {
      return [`$${numValue.toFixed(2)}`, name];
    }
    const isPercent = isPercentMetric(name);
    return [formatNumberValue(numValue, isPercent), name];
  };

  const handleChatSend = () => {
    if (!chatInput.trim()) return;
    triggerAnalysis(ticker, chatInput);
    setChatInput('');
  };

  // Convert Dict scores to Radar format
  const getRadarData = () => {
    if (!agentData || !agentData.iron_triangle_scores) return [];
    const { iron_triangle_scores } = agentData;
    return [
      { subject: 'Fundamentals', value: iron_triangle_scores.Fundamentals || 0 },
      { subject: 'Valuation', value: iron_triangle_scores.Valuation || 0 },
      { subject: 'Sentiment', value: iron_triangle_scores.SentimentMomentum || 0 }
    ];
  };

  const handleCheckboxToggle = (metric) => {
    setSelectedMetrics(prev => {
      if (prev.includes(metric)) {
        return [];
      } else {
        return [metric];
      }
    });
  };

  // Timeline filtering
  const allHistoricalData = (agentData && agentData.historical_chart_data) || [];
  const visibleHistoricalData = allHistoricalData.slice(sliderStart, sliderEnd + 1);
  const startDateText = allHistoricalData[sliderStart]?.date || '';
  const endDateText = allHistoricalData[sliderEnd]?.date || '';

  // Synchronize start/end default boundaries on ticker loads
  useEffect(() => {
    if (allHistoricalData.length > 0 && activeTab === 'overview') {
      setSliderStart(0);
      setSliderEnd(allHistoricalData.length - 1);
    }
  }, [agentData]);

  return (
    <div className="workspace">
      {/* LEFT SIDEBAR: Nav Tabs */}
      <div className="left-sidebar">
        <button
          className={`sidebar-tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
          onClick={() => setActiveTab('overview')}
          title="Overview Dashboard"
        >
          📊
        </button>
        <button
          className={`sidebar-tab-btn ${activeTab === 'historical' ? 'active' : ''}`}
          onClick={() => setActiveTab('historical')}
          title="Historical Charts"
        >
          📈
        </button>
      </div>

      {/* CENTER CANVAS: Dynamic Visualization Stage */}
      <div className="center-canvas">
        {/* Tier 1: Identity Panel */}
        <div className="tier1-header">
          <div className="ticker-input-container">
            <input
              type="text"
              className="ticker-input"
              value={topTickerInput}
              onChange={(e) => setTopTickerInput(e.target.value)}
              onKeyDown={handleTopInputKeyDown}
              placeholder="Enter ticker symbol e.g. AAPL"
              disabled={loading}
            />
            <button
              className="ticker-trigger-btn"
              onClick={() => {
                if (topTickerInput.trim()) {
                  triggerAnalysis(topTickerInput.trim().toUpperCase());
                }
              }}
              disabled={loading}
            >
              Submit
            </button>
          </div>

          {agentData && agentData.corporate_identity && (
            <div className="corporate-details">
              <div className="corporate-detail-item">
                <span className="corporate-detail-label">Price:</span>
                <span className="corporate-detail-value">{agentData.corporate_identity.last_closing_price}</span>
              </div>
              <div className="corporate-detail-item">
                <span className="corporate-detail-label">Market Cap:</span>
                <span className="corporate-detail-value">{agentData.corporate_identity.market_cap}</span>
              </div>
              <div className="corporate-detail-item">
                <span className="corporate-detail-label">Sector:</span>
                <span className="corporate-detail-value">{agentData.corporate_identity.sector}</span>
              </div>
              <div className="corporate-detail-item">
                <span className="corporate-detail-label">Industry:</span>
                <span className="corporate-detail-value">{agentData.corporate_identity.industry}</span>
              </div>
            </div>
          )}
        </div>

        {!agentData ? (
          <div className="splash-screen">
            {loading ? (
              <div className="loading-container">
                <div className="loading-spinner"></div>
                <p>Analyzing <strong>{topTickerInput.toUpperCase()}</strong>...</p>
              </div>
            ) : (
              <div className="splash-content">
                <div className="splash-icon">📈</div>
                <h2>Welcome to Fink!</h2>
                <p>Enter ticker symbol in the box above to begin analysis.</p>
              </div>
            )}
          </div>
        ) : activeTab === 'overview' ? (
          <>
            {/* Tier 2: Anchor View */}
            <div className="tier2-anchor">
              <div className="radar-wrapper">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart cx="50%" cy="50%" outerRadius="75%" data={getRadarData()}>
                    <PolarGrid stroke="#D1D5DB" gridType="circle" />
                    <PolarAngleAxis dataKey="subject" tick={{ fill: '#374151', fontSize: 11, fontWeight: 600 }} />
                    <PolarRadiusAxis domain={[0, 10]} tickCount={6} tick={{ fontSize: 9, fill: '#6B7280' }} axisLine={false} />
                    <Radar
                      name={ticker}
                      dataKey="value"
                      stroke="#2563EB"
                      strokeWidth={2}
                      fill="#3B82F6"
                      fillOpacity={0.3}
                      dot={{ r: 4, fill: '#1F2937', stroke: '#2563EB', strokeWidth: 1 }}
                    />
                  </RadarChart>
                </ResponsiveContainer>
              </div>

              <div className="synthesis-text">
                {agentData.synthesis_summary}
              </div>
            </div>

            {/* Tier 3: Drilldown Matrix */}
            <div className="tier3-matrix">
              {[
                { key: 'Fundamentals', label: 'Fundamentals' },
                { key: 'Valuation', label: 'Valuation' },
                { key: 'SentimentMomentum', label: 'Sentiment / Momentum' }
              ].map(column => (
                <div key={column.key} className="matrix-column">
                  <h4>{column.label}</h4>
                  {agentData.drilldown_matrix && agentData.drilldown_matrix[column.key] ? (
                    agentData.drilldown_matrix[column.key].map((row, i) => (
                      <div className="matrix-row" key={i}>
                        <span className="label">• {row.label}</span>
                        <span className="value">{row.value}</span>
                      </div>
                    ))
                  ) : (
                    <div style={{ color: '#9CA3AF', fontSize: 11 }}>No baseline established.</div>
                  )}
                </div>
              ))}
            </div>
          </>
        ) : (
          /* Historical View Panel */
          <div className="historical-panel">
            <div className="historical-header">
              <h3>Historical Performance vs Price</h3>

              {/* Single track double-ended timeline slider */}
              {allHistoricalData.length > 0 && (
                <div className="timeframe-slider-container">
                  <div className="slider-labels">
                    <span>Timeline Filter: <strong>{startDateText}</strong> — <strong>{endDateText}</strong></span>
                  </div>
                  <div className="slider-track"></div>
                  <div
                    className="slider-highlight"
                    style={{
                      left: `${allHistoricalData.length > 1 ? (sliderStart / (allHistoricalData.length - 1)) * 100 : 0}%`,
                      width: `${allHistoricalData.length > 1 ? ((sliderEnd - sliderStart) / (allHistoricalData.length - 1)) * 100 : 100}%`
                    }}
                  ></div>
                  <input
                    type="range"
                    min="0"
                    max={allHistoricalData.length - 1}
                    value={sliderStart}
                    onChange={(e) => setSliderStart(Math.min(Number(e.target.value), sliderEnd - 1))}
                    className="timeframe-slider"
                  />
                  <input
                    type="range"
                    min="0"
                    max={allHistoricalData.length - 1}
                    value={sliderEnd}
                    onChange={(e) => setSliderEnd(Math.max(Number(e.target.value), sliderStart + 1))}
                    className="timeframe-slider"
                  />
                </div>
              )}
            </div>

            <div className="historical-chart-container">
              {allHistoricalData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={visibleHistoricalData} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.05)" />
                    <XAxis dataKey="date" tick={{ fill: '#374151', fontSize: 10 }} />
                    <YAxis
                      yAxisId="left"
                      tick={{ fill: '#2563EB', fontSize: 10 }}
                      domain={['auto', 'auto']}
                      label={{ value: 'Price ($)', angle: -90, position: 'insideLeft', style: { fill: '#2563EB', fontSize: 11, fontWeight: 600 } }}
                    />
                    {selectedMetrics.length > 0 && (
                      <YAxis
                        yAxisId="right"
                        orientation="right"
                        tick={{ fill: '#4B5563', fontSize: 10 }}
                        tickFormatter={formatRightAxisTick}
                        domain={['auto', 'auto']}
                        label={{ value: selectedMetrics[0], angle: 90, position: 'insideRight', offset: 10, style: { fill: '#4B5563', fontSize: 11, fontWeight: 600 } }}
                      />
                    )}
                    <Tooltip contentStyle={{ fontSize: 11, borderRadius: 8, borderColor: '#E5E7EB' }} formatter={tooltipFormatter} />
                    <Legend wrapperStyle={{ fontSize: 11 }} />

                    <Line yAxisId="left" type="monotone" dataKey="price" stroke="#2563EB" strokeWidth={2.5} name="Stock Price" dot={{ r: 2, fill: '#1E40AF' }} activeDot={{ r: 4 }} connectNulls={true} />

                    {selectedMetrics.includes('Revenue') && (
                      <Line yAxisId="right" type="monotone" dataKey="revenue" stroke="#10B981" strokeWidth={2} name="Revenue" dot={{ r: 2, fill: '#065F46' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Operating Income') && (
                      <Line yAxisId="right" type="monotone" dataKey="operating_income" stroke="#F59E0B" strokeWidth={2} name="Operating Income" dot={{ r: 2, fill: '#92400E' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Net Income') && (
                      <Line yAxisId="right" type="monotone" dataKey="net_income" stroke="#EF4444" strokeWidth={2} name="Net Income" dot={{ r: 2, fill: '#991B1B' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('EPS') && (
                      <Line yAxisId="right" type="monotone" dataKey="eps" stroke="#EC4899" strokeWidth={2} name="EPS" dot={{ r: 2, fill: '#9D174D' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Free Cash Flow') && (
                      <Line yAxisId="right" type="monotone" dataKey="free_cash_flow" stroke="#8B5CF6" strokeWidth={2} name="Free Cash Flow" dot={{ r: 2, fill: '#5B21B6' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Operating Cash Flow') && (
                      <Line yAxisId="right" type="monotone" dataKey="operating_cash_flow" stroke="#3B82F6" strokeWidth={2} name="Operating Cash Flow" dot={{ r: 2, fill: '#1D4ED8' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Capex') && (
                      <Line yAxisId="right" type="monotone" dataKey="capex" stroke="#6B7280" strokeWidth={2} name="Capex" dot={{ r: 2, fill: '#374151' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('P/E') && (
                      <Line yAxisId="right" type="monotone" dataKey="pe_ratio" stroke="#DC2626" strokeWidth={2} name="P/E Ratio" dot={{ r: 2, fill: '#991B1B' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('P/S') && (
                      <Line yAxisId="right" type="monotone" dataKey="ps_ratio" stroke="#059669" strokeWidth={2} name="P/S Ratio" dot={{ r: 2, fill: '#047857' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('P/FCF') && (
                      <Line yAxisId="right" type="monotone" dataKey="pfcf_ratio" stroke="#7C3AED" strokeWidth={2} name="P/FCF Ratio" dot={{ r: 2, fill: '#5B21B6' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('P/OCF') && (
                      <Line yAxisId="right" type="monotone" dataKey="pocf_ratio" stroke="#2563EB" strokeWidth={2} name="P/OCF Ratio" dot={{ r: 2, fill: '#1D4ED8' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Shares Outstanding') && (
                      <Line yAxisId="right" type="monotone" dataKey="shares_outstanding" stroke="#EA580C" strokeWidth={2} name="Shares Outstanding" dot={{ r: 2, fill: '#C2410C' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Dividends (TTM)') && (
                      <Line yAxisId="right" type="monotone" dataKey="dividends" stroke="#D97706" strokeWidth={2} name="Dividends Paid" dot={{ r: 2, fill: '#B45309' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Dividend Yield') && (
                      <Line yAxisId="right" type="monotone" dataKey="dividend_yield" stroke="#0D9488" strokeWidth={2} name="Dividend Yield (%)" dot={{ r: 2, fill: '#0F766E' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Payout Ratio (FCF)') && (
                      <Line yAxisId="right" type="monotone" dataKey="payout_ratio_fcf" stroke="#4F46E5" strokeWidth={2} name="Payout (FCF) %" dot={{ r: 2, fill: '#3730A3' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('Payout Ratio (OCF)') && (
                      <Line yAxisId="right" type="monotone" dataKey="payout_ratio_ocf" stroke="#9333EA" strokeWidth={2} name="Payout (OCF) %" dot={{ r: 2, fill: '#6B21A8' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                    {selectedMetrics.includes('ROIC') && (
                      <Line yAxisId="right" type="monotone" dataKey="roic" stroke="#EC4899" strokeWidth={2} name="ROIC (%)" dot={{ r: 2, fill: '#9D174D' }} activeDot={{ r: 4 }} connectNulls={true} />
                    )}
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="historical-no-data">
                  No historical chart data loaded.
                </div>
              )}
            </div>

            {/* Checkbox Bottom Panel */}
            <div className="checkbox-metrics-panel">
              <div className="checkbox-metric-group">
                <h5>Income Statement</h5>
                <div className="checkbox-row">
                  {['Revenue', 'Operating Income', 'Net Income', 'EPS'].map(m => (
                    <label className="checkbox-item" key={m}>
                      <input
                        type="checkbox"
                        checked={selectedMetrics.includes(m)}
                        onChange={() => handleCheckboxToggle(m)}
                      />
                      <span>{m}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="checkbox-metric-group">
                <h5>Cash Flow</h5>
                <div className="checkbox-row">
                  {['Free Cash Flow', 'Operating Cash Flow', 'Capex'].map(m => (
                    <label className="checkbox-item" key={m}>
                      <input
                        type="checkbox"
                        checked={selectedMetrics.includes(m)}
                        onChange={() => handleCheckboxToggle(m)}
                      />
                      <span>{m}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="checkbox-metric-group">
                <h5>Valuation</h5>
                <div className="checkbox-row">
                  {['P/E', 'P/S', 'P/FCF', 'P/OCF'].map(m => (
                    <label className="checkbox-item" key={m}>
                      <input
                        type="checkbox"
                        checked={selectedMetrics.includes(m)}
                        onChange={() => handleCheckboxToggle(m)}
                      />
                      <span>{m}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="checkbox-metric-group">
                <h5>Shareholders</h5>
                <div className="checkbox-row">
                  {['Shares Outstanding', 'Dividends (TTM)', 'Dividend Yield', 'Payout Ratio (FCF)', 'Payout Ratio (OCF)', 'ROIC'].map(m => (
                    <label className="checkbox-item" key={m}>
                      <input
                        type="checkbox"
                        checked={selectedMetrics.includes(m)}
                        onChange={() => handleCheckboxToggle(m)}
                      />
                      <span>{m}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* RIGHT SIDEBAR: Chat Panel */}
      <div className="right-sidebar">
        <div className="chat-header-banner">
          <span className="banner-title">Fink</span>
          <span className="banner-subtitle">Your Finance Due Diligence Agent</span>
        </div>
        <div className="chat-history">
          {chatHistory.map((msg, i) => (
            <React.Fragment key={i}>
              <div className={`chat-bubble ${msg.role}`}>
                {msg.content}
              </div>
              {msg.role === 'user' && msg.pathway && (
                <div className="chat-breadcrumbs-inline">
                  {msg.pathway.join(" ➔ ")}
                </div>
              )}
            </React.Fragment>
          ))}
          {loading && <div className="chat-bubble agent">Working...</div>}
          <div ref={chatEndRef} />
        </div>

        <div className="chat-input-area">
          <input
            type="text"
            className="chat-input"
            placeholder="Ask away..."
            value={chatInput}
            onChange={(e) => setChatInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleChatSend()}
            disabled={loading}
          />
        </div>
      </div>
    </div>
  );
}
