// chartUtils.js
// Utilities for preparing chart data and configuration for Chart.js

const SEGMENT_COLORS = [
    '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
    '#ec4899', '#06b6d4', '#f97316', '#14b8a6', '#6366f1',
    '#d946ef', '#0ea5e9', '#eab308', '#a855f7', '#64748b'
];

/**
 * Prepares chart data for Chart.js from processed metrics.
 */
function prepareChartData(processedMetrics, selectedMetrics, metricsConfig, options) {
    if (!processedMetrics) return { datasets: [], commonLabels: [] };
    selectedMetrics = selectedMetrics || [];
    options = options || {};
    const perShareMetrics = options.perShareMetrics || [];
    const axisMappings = options.axisMappings || new Map();
    const normalize = !!options.normalize;
    const datasetsForChart = [];
    
    // Find the longest array/object of date keys across all metrics
    let commonLabels = [];
    for (const key in processedMetrics) {
        if (processedMetrics[key]) {
            const keys = Array.isArray(processedMetrics[key]) 
                ? processedMetrics[key].map(item => item.date) 
                : Object.keys(processedMetrics[key]);
            if (keys.length > commonLabels.length) {
                commonLabels = keys.sort();
            }
        }
    }

    const sharesMap = new Map(Object.entries(processedMetrics['shares_outstanding'] || {}));

    for (const metricId of selectedMetrics) {
        const metricConfig = metricsConfig.find(m => m.id === metricId);
        const data = processedMetrics[metricId];
        if (!metricConfig || !data) {
            continue;
        }

        // Check if this is a segment metric (dict of dicts)
        const isSegmentMetric = metricConfig.chartType === 'stackedBar';
        if (isSegmentMetric) {
            // data is {date: {segmentName: value, ...}, ...}
            // Collect all unique segment names across all dates
            const segmentNames = new Set();
            for (const dateKey of Object.keys(data)) {
                if (typeof data[dateKey] === 'object' && data[dateKey] !== null) {
                    Object.keys(data[dateKey]).forEach(name => segmentNames.add(name));
                }
            }
            
            // Create one bar dataset per segment
            let colorIdx = 0;
            for (const segName of segmentNames) {
                const alignedData = commonLabels.map(label => {
                    const dateData = data[label];
                    if (dateData && typeof dateData === 'object') {
                        return dateData[segName] ?? null;
                    }
                    return null;
                });
                
                const color = SEGMENT_COLORS[colorIdx % SEGMENT_COLORS.length];
                datasetsForChart.push({
                    label: segName,
                    data: alignedData,
                    backgroundColor: color + 'CC',  // Slightly transparent
                    borderColor: color,
                    borderWidth: 1,
                    yAxisID: 'y',
                    type: 'bar',
                    stack: metricId,  // Stack bars by segment type
                    order: 2  // Bars render behind lines
                });
                colorIdx++;
            }
            continue;  // Skip the normal line dataset creation
        }

        let dataMap;
        if (Array.isArray(data)) {
            dataMap = new Map(data.map(item => [item.date, item.value]));
        } else {
            dataMap = new Map(Object.entries(data));
        }

        const alignedData = commonLabels.map(label => {
            let val = dataMap.get(label) ?? null;
            if (val !== null && perShareMetrics.includes(metricId) && metricConfig.isAggregate) {
                const shares = sharesMap.get(label);
                if (shares && shares > 0) {
                    val = val / shares;
                } else {
                    val = null; // Division by zero/missing shares safeguard
                }
            }
            return val;
        });

        // Determine Axis ID
        let yAxisID = metricConfig.axis || metricConfig.defaultAxis || 'y';
        if (axisMappings.has(metricId)) {
            yAxisID = axisMappings.get(metricId);
        }

        // Suffix label with axis indicator only if not normalizing (since normalization is single-axis)
        let axisSuffix = "";
        if (!normalize) {
            axisSuffix = yAxisID === 'y' ? " (L)" : " (R)";
        }

        datasetsForChart.push({
            label: metricConfig.label + (perShareMetrics.includes(metricId) && metricConfig.isAggregate ? " ($/sh)" : "") + axisSuffix,
            data: alignedData,
            borderColor: metricConfig.color,
            backgroundColor: metricConfig.color,
            yAxisID: yAxisID,
            tension: 0.1,
            fill: false,
            spanGaps: true
        });
    }
    return { datasets: datasetsForChart, commonLabels };
}

/**
 * Setup and manage the double-ended timeline range slider.
 */
function setupDualSlider(startSliderId, endSliderId, trackClass, startLabelId, endLabelId, labels, onUpdate) {
    const startSlider = document.getElementById(startSliderId);
    const endSlider = document.getElementById(endSliderId);
    const track = document.querySelector('.' + trackClass);
    const startLabel = document.getElementById(startLabelId);
    const endLabel = document.getElementById(endLabelId);
    
    if (!startSlider || !endSlider || !track) return null;
    
    const max = Math.max(0, labels.length - 1);
    startSlider.min = 0;
    startSlider.max = max;
    startSlider.value = 0;
    endSlider.min = 0;
    endSlider.max = max;
    endSlider.value = max;
    
    function updateUI() {
        let val1 = isNaN(parseInt(startSlider.value)) ? 0 : parseInt(startSlider.value);
        let val2 = isNaN(parseInt(endSlider.value)) ? max : parseInt(endSlider.value);
        
        if (val1 > val2) {
            [val1, val2] = [val2, val1];
            startSlider.value = val1;
            endSlider.value = val2;
        }
        
        const pct1 = (val1 / max) * 100;
        const pct2 = (val2 / max) * 100;
        track.style.background = `linear-gradient(to right, #cbd5e1 ${pct1}%, #3b82f6 ${pct1}%, #3b82f6 ${pct2}%, #cbd5e1 ${pct2}%)`;
        
        if (labels.length > 0) {
            if (startLabel) startLabel.innerText = labels[val1];
            if (endLabel) endLabel.innerText = labels[val2];
        }
    }
    
    startSlider.addEventListener('input', () => {
        let val1 = isNaN(parseInt(startSlider.value)) ? 0 : parseInt(startSlider.value);
        let val2 = isNaN(parseInt(endSlider.value)) ? max : parseInt(endSlider.value);
        if (val1 > val2) {
            startSlider.value = val2;
        }
        updateUI();
        onUpdate(isNaN(parseInt(startSlider.value)) ? 0 : parseInt(startSlider.value), isNaN(parseInt(endSlider.value)) ? max : parseInt(endSlider.value));
    });
    
    endSlider.addEventListener('input', () => {
        let val1 = isNaN(parseInt(startSlider.value)) ? 0 : parseInt(startSlider.value);
        let val2 = isNaN(parseInt(endSlider.value)) ? max : parseInt(endSlider.value);
        if (val2 < val1) {
            endSlider.value = val1;
        }
        updateUI();
        onUpdate(isNaN(parseInt(startSlider.value)) ? 0 : parseInt(startSlider.value), isNaN(parseInt(endSlider.value)) ? max : parseInt(endSlider.value));
    });
    
    updateUI();
    return {
        updateRange: (sVal, eVal) => {
            startSlider.value = sVal;
            endSlider.value = eVal;
            updateUI();
        }
    };
}

/**
 * Initializes the entire financial chart dashboard with config and events.
 */
function initFinancialChart({ 
    ticker, 
    dataUrl, 
    metricsConfig, 
    initialMetrics, 
    initialStartDate, 
    initialEndDate,
    initialNormalize,
    initialPerShareMetrics,
    initialLeftAxisMetrics,
    initialRightAxisMetrics
}) {
    let chartInstance = null;
    let commonLabelsGlobal = [];
    let processedMetrics = {};
    let sliderController = null;

    function getSelectedMetrics() {
        const selected = [];
        metricsConfig.forEach(m => {
            const el = document.getElementById(`metric-${m.id}`);
            if (el && el.checked) {
                selected.push(m.id);
            }
        });
        return selected;
    }

    function getPerShareMetrics() {
        const perShare = [];
        metricsConfig.forEach(m => {
            const btn = document.getElementById(`sh-${m.id}`);
            if (btn && btn.classList.contains('active')) {
                perShare.push(m.id);
            }
        });
        return perShare;
    }

    function getAxisMappings() {
        const mappings = new Map();
        metricsConfig.forEach(m => {
            const container = document.getElementById(`axis-selector-${m.id}`);
            if (container) {
                const activeBtn = container.querySelector('.btn-axis.active');
                if (activeBtn) {
                    mappings.set(m.id, activeBtn.innerText === 'L' ? 'y' : 'y1');
                }
            }
        });
        return mappings;
    }

    function isNormalizeChecked() {
        const el = document.getElementById('global-normalize');
        return el ? el.checked : false;
    }

    function formatNumber(value) {
        if (value === null || value === undefined) return '';
        const absVal = Math.abs(value);
        if (absVal >= 1e9) return (value / 1e9).toFixed(1) + "B";
        if (absVal >= 1e6) return (value / 1e6).toFixed(1) + "M";
        if (absVal >= 1e3) return (value / 1e3).toFixed(1) + "K";
        return value.toFixed(1);
    }

    function formatTooltipVal(val, label, normalize) {
        if (val === null || val === undefined) return '';
        if (normalize) {
            return val.toFixed(2) + "%";
        }
        const labelLower = label.toLowerCase();
        const isCurrency = label.includes("$") || labelLower.includes("revenue") || labelLower.includes("cash flow") || labelLower.includes("price") || labelLower.includes("fcf") || labelLower.includes("cogs") || labelLower.includes("expenses") || labelLower.includes("repurchases") || labelLower.includes("equivalents") || labelLower.includes("debt") || labelLower.includes("cap") || labelLower.includes("value");
        const prefix = isCurrency ? "$" : "";
        const suffix = labelLower.includes("margin") || labelLower.includes("yield") || labelLower.includes("ratio (fcf") || labelLower.includes("ratio (ocf") ? "%" : "";
        
        const absVal = Math.abs(val);
        if (absVal >= 1e9) return prefix + (val / 1e9).toFixed(2) + "B" + suffix;
        if (absVal >= 1e6) return prefix + (val / 1e6).toFixed(2) + "M" + suffix;
        if (absVal >= 1e3) return prefix + (val / 1e3).toFixed(2) + "K" + suffix;
        return prefix + val.toFixed(2) + suffix;
    }

    function findClosestDateIndex(labels, targetDateStr) {
        const targetDate = new Date(targetDateStr);
        if (isNaN(targetDate)) return -1;
        
        let closestIdx = -1;
        let minDiff = Infinity;
        for (let i = 0; i < labels.length; i++) {
            const d = new Date(labels[i]);
            const diff = Math.abs(d - targetDate);
            if (diff < minDiff) {
                minDiff = diff;
                closestIdx = i;
            }
        }
        return closestIdx;
    }

    function updateChart() {
        const selectedMetrics = getSelectedMetrics();
        const perShare = getPerShareMetrics();
        const axisMappings = getAxisMappings();
        const normalize = isNormalizeChecked();

        const { datasets, commonLabels } = prepareChartData(processedMetrics, selectedMetrics, metricsConfig, {
            perShareMetrics: perShare,
            axisMappings: axisMappings,
            normalize: normalize
        });
        
        if (!commonLabelsGlobal.length || commonLabelsGlobal.length !== commonLabels.length) {
            commonLabelsGlobal = commonLabels;
        }

        const startSlider = document.getElementById('leftSlider');
        const endSlider = document.getElementById('rightSlider');
        const startIdx = startSlider ? (isNaN(parseInt(startSlider.value)) ? 0 : parseInt(startSlider.value)) : 0;
        const endIdx = endSlider ? (isNaN(parseInt(endSlider.value)) ? (commonLabels.length - 1) : parseInt(endSlider.value)) : (commonLabels.length - 1);
        
        let filteredLabels = commonLabels.slice(startIdx, endIdx + 1);
        let filteredDatasets = datasets.map(ds => {
            let slicedData = ds.data.slice(startIdx, endIdx + 1);
            
            // Apply Normalization over the visible range if active
            if (normalize) {
                // Find first non-null, non-zero baseline value in this sliced window
                let baseline = null;
                for (let val of slicedData) {
                    if (val !== null && val !== undefined && val !== 0) {
                        baseline = val;
                        break;
                    }
                }
                
                if (baseline !== null) {
                    slicedData = slicedData.map(v => v !== null && v !== undefined ? ((v / baseline) * 100) : null);
                } else {
                    slicedData = slicedData.map(() => null);
                }
            }

            return { 
                ...ds, 
                data: slicedData,
                yAxisID: normalize ? 'y' : ds.yAxisID // Standardize to left axis if normalized
            };
        });
        
        // Determine if we have bar datasets (segments) — affects stacking and chart lifecycle
        const hasBarDatasets = filteredDatasets.some(ds => ds.type === 'bar');

        // Always destroy existing chart before recreating.
        // Mixed charts (line + bar) require full recreation when dataset types change;
        // in-place update causes "Canvas already in use" and data parsing errors.
        if (chartInstance) {
            chartInstance.destroy();
            chartInstance = null;
        }

        if (filteredDatasets.length === 0) return;

        const ctx = document.getElementById("financialChart").getContext("2d");
        const hasRightAxis = filteredDatasets.some(ds => ds.yAxisID === 'y1');
        chartInstance = new Chart(ctx, {
            type: "line",
            data: {
                labels: filteredLabels,
                datasets: filteredDatasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                scales: {
                    y: { 
                        type: "linear", position: "left",
                        ticks: { color: "#334155", callback: v => normalize ? v.toFixed(0) + "%" : formatNumber(v) },
                        grid: { color: "rgba(0, 0, 0, 0.05)" },
                        stacked: hasBarDatasets  // Enable stacking only when bar datasets (segments) exist
                    },
                    y1: { 
                        type: "linear", position: "right",
                        ticks: { color: "#334155", callback: v => formatNumber(v) },
                        grid: { drawOnChartArea: false },
                        display: !normalize && hasRightAxis
                    },
                    x: { 
                        ticks: { color: "#334155" }, 
                        grid: { color: "rgba(0, 0, 0, 0.05)" },
                        stacked: true
                    }
                },
                plugins: {
                    legend: { labels: { color: "#0f172a", font: { weight: '600', size: 11 } } },
                    tooltip: {
                        callbacks: {
                            label: ctx => ctx.dataset.label + ': ' + formatTooltipVal(ctx.parsed.y, ctx.dataset.label, isNormalizeChecked())
                        }
                    }
                }
            }
        });
    }

    // Set timeline bounds
    function setTimeline(timeline) {
        if (!commonLabelsGlobal.length) return;
        const total = commonLabelsGlobal.length;
        let sIdx = 0;
        let eIdx = total - 1;
        
        if (timeline !== 'all') {
            const years = parseInt(timeline);
            const latestDate = new Date(commonLabelsGlobal[total - 1]);
            const cutoffDate = new Date(latestDate);
            cutoffDate.setFullYear(latestDate.getFullYear() - years);
            
            sIdx = commonLabelsGlobal.findIndex(d => new Date(d) >= cutoffDate);
            if (sIdx === -1) sIdx = 0;
        }
        
        if (sliderController) {
            sliderController.updateRange(sIdx, eIdx);
        }
        updateChart();
    }

    // Expose control handlers globally
    window.onMetricCheckedChange = function(metricId) {
        updateChart();
    };
    
    window.setMetricAxis = function(metricId, axis) {
        const container = document.getElementById(`axis-selector-${metricId}`);
        if (container) {
            container.querySelectorAll('.btn-axis').forEach(btn => {
                btn.classList.remove('active');
                if ((axis === 'y' && btn.innerText === 'L' || axis === 'y1' && btn.innerText === 'R')) {
                    btn.classList.add('active');
                }
            });
        }
        updateChart();
    };
    
    window.togglePerShare = function(metricId) {
        const btn = document.getElementById(`sh-${metricId}`);
        if (btn) {
            btn.classList.toggle('active');
        }
        updateChart();
    };
    
    window.onNormalizeChanged = function() {
        updateChart();
    };

    window.updateChartParameters = function({ metrics, startDate, endDate, normalize, perShareMetrics, leftAxisMetrics, rightAxisMetrics }) {
        metricsConfig.forEach(m => {
            const el = document.getElementById(`metric-${m.id}`);
            if (el) el.checked = metrics.includes(m.id);
            
            const shBtn = document.getElementById(`sh-${m.id}`);
            if (shBtn) {
                if (perShareMetrics && perShareMetrics.includes(m.id)) {
                    shBtn.classList.add('active');
                } else {
                    shBtn.classList.remove('active');
                }
            }
            
            const axisContainer = document.getElementById(`axis-selector-${m.id}`);
            if (axisContainer) {
                axisContainer.querySelectorAll('.btn-axis').forEach(btn => {
                    btn.classList.remove('active');
                    const isL = btn.innerText === 'L';
                    const targetL = (leftAxisMetrics && leftAxisMetrics.includes(m.id)) || 
                                    (!rightAxisMetrics || !rightAxisMetrics.includes(m.id)) && m.defaultAxis === 'y';
                    if ((isL && targetL) || (!isL && !targetL)) {
                        btn.classList.add('active');
                    }
                });
            }
        });
        
        const normEl = document.getElementById('global-normalize');
        if (normEl) normEl.checked = !!normalize;
        
        if (startDate || endDate) {
            let sIdx = 0;
            let eIdx = commonLabelsGlobal.length - 1;
            if (startDate) {
                const idx = findClosestDateIndex(commonLabelsGlobal, startDate);
                if (idx !== -1) sIdx = idx;
            }
            if (endDate) {
                const idx = findClosestDateIndex(commonLabelsGlobal, endDate);
                if (idx !== -1) eIdx = idx;
            }
            if (sliderController) sliderController.updateRange(sIdx, eIdx);
        }
        updateChart();
    };

    // Load data dynamically
    fetch(dataUrl)
      .then(response => response.json())
      .then(data => {
        processedMetrics = data;
        
        for (const key in processedMetrics) {
            const keys = Object.keys(processedMetrics[key]);
            if (keys.length > commonLabelsGlobal.length) {
                commonLabelsGlobal = keys.sort();
            }
        }
        
        sliderController = setupDualSlider(
            'leftSlider',
            'rightSlider',
            'slider-track',
            'slider-start-label',
            'slider-end-label',
            commonLabelsGlobal,
            (sIdx, eIdx) => {
                updateChart();
            }
        );
        
        // Initial setup from window variables
        if (initialMetrics) {
            metricsConfig.forEach(m => {
                const el = document.getElementById(`metric-${m.id}`);
                if (el) el.checked = initialMetrics.includes(m.id);
            });
        }
        if (initialPerShareMetrics) {
            initialPerShareMetrics.forEach(mId => {
                const btn = document.getElementById(`sh-${mId}`);
                if (btn) btn.classList.add('active');
            });
        }
        if (initialLeftAxisMetrics) {
            initialLeftAxisMetrics.forEach(mId => {
                window.setMetricAxis(mId, 'y');
            });
        }
        if (initialRightAxisMetrics) {
            initialRightAxisMetrics.forEach(mId => {
                window.setMetricAxis(mId, 'y1');
            });
        }
        
        if (initialStartDate || initialEndDate) {
            let sIdx = 0;
            let eIdx = commonLabelsGlobal.length - 1;
            if (initialStartDate) {
                const idx = findClosestDateIndex(commonLabelsGlobal, initialStartDate);
                if (idx !== -1) sIdx = idx;
            }
            if (initialEndDate) {
                const idx = findClosestDateIndex(commonLabelsGlobal, initialEndDate);
                if (idx !== -1) eIdx = idx;
            }
            if (sliderController) sliderController.updateRange(sIdx, eIdx);
        }
        
        updateChart();
        
        // Check if there is any pending update queued by a duplicate frame
        if (window.pendingUpdate) {
            window.updateChartParameters(window.pendingUpdate);
            delete window.pendingUpdate;
        }
      });
}

// Expose functions globally to window
window.prepareChartData = prepareChartData;
window.setupDualSlider = setupDualSlider;
window.initFinancialChart = initFinancialChart;
