// chartUtils.js
// Utilities for preparing chart data and configuration for Chart.js

/**
 * Prepares chart data for Chart.js from processed metrics.
 */
function prepareChartData(processedMetrics, selectedMetrics, metricsConfig) {
    if (!processedMetrics) return { datasets: [], commonLabels: [] };
    selectedMetrics = selectedMetrics || [];
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

    for (const metricId of selectedMetrics) {
        const metricConfig = metricsConfig.find(m => m.id === metricId);
        const data = processedMetrics[metricId];
        if (!metricConfig || !data) {
            continue;
        }

        let dataMap;
        if (Array.isArray(data)) {
            // Convert array data to a Map for efficient lookup
            dataMap = new Map(data.map(item => [item.date, item.value]));
        } else {
            // Handle object-based data (like 'price')
            dataMap = new Map(Object.entries(data));
        }

        const alignedData = commonLabels.map(label => dataMap.get(label) ?? null);

        datasetsForChart.push({
            label: metricConfig.label,
            data: alignedData,
            borderColor: metricConfig.color,
            backgroundColor: metricConfig.color,
            yAxisID: metricConfig.axis,
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
        track.style.background = `linear-gradient(to right, #475569 ${pct1}%, #3b82f6 ${pct1}%, #3b82f6 ${pct2}%, #475569 ${pct2}%)`;
        
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
function initFinancialChart({ ticker, dataUrl, metricsConfig, initialStartDate, initialEndDate }) {
    let chartInstance = null;
    let commonLabelsGlobal = [];
    let processedMetrics = {};
    let sliderController = null;

    function getSelectedMetrics() {
        const selected = [];
        if (document.getElementById('metric-price').checked) selected.push('price');
        if (document.getElementById('metric-pe_ratio').checked) selected.push('pe_ratio');
        if (document.getElementById('metric-eps').checked) selected.push('eps');
        if (document.getElementById('metric-revenue').checked) selected.push('revenue');
        if (document.getElementById('metric-free_cash_flow').checked) selected.push('free_cash_flow');
        if (document.getElementById('metric-shares_outstanding').checked) selected.push('shares_outstanding');
        if (document.getElementById('metric-ps_ratio').checked) selected.push('ps_ratio');
        return selected;
    }

    function formatNumber(value) {
        if (value === null || value === undefined) return '';
        const absVal = Math.abs(value);
        if (absVal >= 1e9) return (value / 1e9).toFixed(1) + "B";
        if (absVal >= 1e6) return (value / 1e6).toFixed(1) + "M";
        if (absVal >= 1e3) return (value / 1e3).toFixed(1) + "K";
        return value.toFixed(1);
    }

    function formatTooltipVal(val, label) {
        if (val === null || val === undefined) return '';
        const labelLower = label.toLowerCase();
        const isCurrency = label.includes("$") || labelLower.includes("revenue") || labelLower.includes("cash flow") || labelLower.includes("price") || labelLower.includes("fcf");
        const prefix = isCurrency ? "$" : "";
        const absVal = Math.abs(val);
        if (absVal >= 1e9) return prefix + (val / 1e9).toFixed(2) + "B";
        if (absVal >= 1e6) return prefix + (val / 1e6).toFixed(2) + "M";
        if (absVal >= 1e3) return prefix + (val / 1e3).toFixed(2) + "K";
        return prefix + val.toFixed(2);
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
        const { datasets, commonLabels } = prepareChartData(processedMetrics, selectedMetrics, metricsConfig);
        
        if (!commonLabelsGlobal.length || commonLabelsGlobal.length !== commonLabels.length) {
            commonLabelsGlobal = commonLabels;
        }

        const startSlider = document.getElementById('leftSlider');
        const endSlider = document.getElementById('rightSlider');
        const startIdx = startSlider ? (isNaN(parseInt(startSlider.value)) ? 0 : parseInt(startSlider.value)) : 0;
        const endIdx = endSlider ? (isNaN(parseInt(endSlider.value)) ? (commonLabels.length - 1) : parseInt(endSlider.value)) : (commonLabels.length - 1);
        
        let filteredLabels = commonLabels.slice(startIdx, endIdx + 1);
        let filteredDatasets = datasets.map(ds => ({ 
            ...ds, 
            data: ds.data.slice(startIdx, endIdx + 1) 
        }));
        
        if (chartInstance) {
            chartInstance.data.labels = filteredLabels;
            chartInstance.data.datasets = filteredDatasets;
            chartInstance.update();
        } else {
            const ctx = document.getElementById("financialChart").getContext("2d");
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
                            ticks: { color: "#94a3b8", callback: v => "$" + formatNumber(v) },
                            grid: { color: "rgba(148, 163, 184, 0.1)" }
                        },
                        y1: { 
                            type: "linear", position: "right",
                            ticks: { color: "#94a3b8", callback: v => formatNumber(v) },
                            grid: { drawOnChartArea: false }
                        },
                        x: { ticks: { color: "#94a3b8" }, grid: { color: "rgba(148, 163, 184, 0.1)" } }
                    },
                    plugins: {
                        legend: { labels: { color: "#f8fafc" } },
                        tooltip: {
                            callbacks: {
                                label: ctx => ctx.dataset.label + ': ' + formatTooltipVal(ctx.parsed.y, ctx.dataset.label)
                            }
                        }
                    }
                }
            });
        }
    }

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
        
        document.querySelectorAll('.btn-group .btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.getAttribute('onclick').includes(timeline)) {
                btn.classList.add('active');
            }
        });
        updateChart();
    }

    // Expose setTimeline globally so standard onclick markup attributes resolve correctly
    window.setTimeline = setTimeline;

    // Attach event listeners to checkboxes
    document.querySelectorAll('.checkbox-group input').forEach(input => {
        input.addEventListener('change', updateChart);
    });

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
                document.querySelectorAll('.btn-group .btn').forEach(btn => btn.classList.remove('active'));
                updateChart();
            }
        );
        
        updateChart();

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
            updateChart();
        } else {
            setTimeline('all');
        }
      });
}

// Expose functions globally to window
window.prepareChartData = prepareChartData;
window.setupDualSlider = setupDualSlider;
window.initFinancialChart = initFinancialChart;
