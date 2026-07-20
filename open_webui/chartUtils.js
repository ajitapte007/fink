// chartUtils.js
// Utilities for preparing chart data and configuration for Chart.js

/**
 * Prepares chart data for Chart.js from processed metrics.
 */
export function prepareChartData(processedMetrics, selectedMetrics, metricsConfig) {
    if (!processedMetrics) return { datasets: [], commonLabels: [] };
    selectedMetrics = selectedMetrics || [];
    const datasetsForChart = [];
    // Price is still an object, so this is our source of truth for labels
    const commonLabels = Object.keys(processedMetrics['price'] || {}).sort();

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
 * Generate a QuickChart Sankey chart URL for a cashflow overview.
 * @param {Object} params
 *   - input: string (e.g., 'totalRevenue')
 *   - outputs: array of { label: string, value: number }
 *   - inputLabel: string (optional, for display)
 *   - outputLabels: array of string (optional, for display)
 * @returns {string} QuickChart URL
 */
export function getCashflowSankeyChartUrl({ input, outputs, inputLabel }) {
    // Default label
    const fromLabel = inputLabel || input;
    // Build data array for QuickChart Sankey
    const data = outputs
        .filter(o => o.value !== null && o.value !== undefined && !isNaN(o.value))
        .map(o => ({ from: fromLabel, to: o.label, flow: Math.abs(o.value) }));
    const chartConfig = {
        type: 'sankey',
        data: {
            datasets: [
                {
                    data: data
                }
            ]
        },
        options: {
            title: {
                display: true,
                text: 'Cashflow Overview',
                font: { size: 20 }
            }
        }
    };
    const encoded = encodeURIComponent(JSON.stringify(chartConfig));
    return `https://quickchart.io/chart?c=${encoded}&version=3`;
}

/**
 * Render a QuickChart image in a container by id.
 * @param {string} containerId
 * @param {string} chartUrl
 */
export function renderQuickChartImage(containerId, chartUrl) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = '';
    const img = document.createElement('img');
    img.src = chartUrl;
    img.style.maxWidth = '100%';
    img.style.minHeight = '400px';
    container.appendChild(img);
}

/**
 * Render an interactive Sankey diagram using Plotly.js
 * @param {string} containerId - The id of the container div
 * @param {string} inputLabel - The label for the input/source node
 * @param {Array<{label: string, value: number}>} outputs - Array of output nodes
 */
export function renderPlotlySankeyChart(containerId, inputLabel, outputs) {
    const container = document.getElementById(containerId);
    if (!container) return;
    // Prepare nodes and links for Plotly Sankey
    const labels = [inputLabel, ...outputs.map(o => o.label)];
    const source = outputs.map(() => 0); // All from input node (index 0)
    const target = outputs.map((_, i) => i + 1); // To each output node
    const values = outputs.map(o => Math.abs(Number(o.value) || 0));
    const data = [{
        type: 'sankey',
        orientation: 'h',
        node: {
            pad: 15,
            thickness: 20,
            line: { color: 'black', width: 0.5 },
            label: labels,
            color: ['#3b82f6', ...outputs.map(() => '#f59e42')]
        },
        link: {
            source: source,
            target: target,
            value: values,
            color: outputs.map(() => 'rgba(59,130,246,0.3)')
        }
    }];
    const layout = {
        font: { size: 14 },
        autosize: true,
        margin: { l: 0, r: 0, t: 10, b: 0 },
        width: null,
        height: 100
    };
    Plotly.react(container, data, layout, {responsive: true});
}

/**
 * Render a multi-level Sankey diagram using Plotly.js
 * @param {string} containerId - The id of the container div
 * @param {Array<string>} nodes - Array of node labels
 * @param {Array<{source: number, target: number, value: number}>} links - Array of links
 */
export function renderPlotlySankeyChartMultiLevel(containerId, nodes, links) {
    const container = document.getElementById(containerId);
    if (!container) return;
    const data = [{
        type: 'sankey',
        orientation: 'h',
        node: {
            pad: 15,
            thickness: 20,
            line: { color: 'black', width: 0.5 },
            label: nodes,
            color: nodes.map((_, i) => i === 0 ? '#3b82f6' : (i === 1 ? '#f59e42' : '#a3e635'))
        },
        link: {
            source: links.map(l => l.source),
            target: links.map(l => l.target),
            value: links.map(l => Math.abs(Number(l.value) || 0)),
            color: links.map(() => 'rgba(59,130,246,0.3)')
        }
    }];
    const layout = {
        font: { size: 14 },
        autosize: true,
        margin: { l: 0, r: 0, t: 10, b: 0 },
        width: null,
        height: 400
    };
    Plotly.react(container, data, layout, {responsive: true});
}

/**
 * Dynamically inject timeframe slider CSS styles into the document head.
 */
export function injectSliderStyles() {
    if (document.getElementById('slider-styles-injected')) return;
    const style = document.createElement('style');
    style.id = 'slider-styles-injected';
    style.innerHTML = `
        .timeframe-slider-container {
          position: relative;
          height: 24px;
          width: 100%;
          display: flex;
          align-items: center;
          margin-top: 10px;
          margin-bottom: 5px;
        }
        .slider-track {
          position: absolute;
          left: 0;
          right: 0;
          height: 6px;
          background-color: #475569;
          border-radius: 3px;
          z-index: 1;
        }
        input[type="range"].timeframe-slider {
          position: absolute;
          left: 0;
          width: 100%;
          -webkit-appearance: none;
          appearance: none;
          background: transparent;
          pointer-events: none;
          margin: 0;
          border: none;
          z-index: 3;
        }
        input[type="range"].timeframe-slider::-webkit-slider-thumb {
          -webkit-appearance: none;
          appearance: none;
          pointer-events: all;
          width: 14px;
          height: 14px;
          background-color: #3b82f6;
          border-radius: 50%;
          cursor: pointer;
          border: 2px solid #1e293b;
          box-shadow: 0 0 4px rgba(0, 0, 0, 0.15);
          transition: transform 0.1s ease;
        }
        input[type="range"].timeframe-slider::-webkit-slider-thumb:hover {
          transform: scale(1.15);
        }
        input[type="range"].timeframe-slider::-moz-range-thumb {
          pointer-events: all;
          width: 14px;
          height: 14px;
          background-color: #3b82f6;
          border-radius: 50%;
          cursor: pointer;
          border: 2px solid #1e293b;
          box-shadow: 0 0 4px rgba(0, 0, 0, 0.15);
        }
    `;
    document.head.appendChild(style);
}

/**
 * Setup and manage the double-ended timeline range slider.
 */
export function setupDualSlider(startSliderId, endSliderId, trackClass, startLabelId, endLabelId, labels, onUpdate) {
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