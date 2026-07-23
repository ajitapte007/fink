// chartUtils.js
// Utilities for preparing chart data and configuration for Chart.js

/**
 * Prepares chart data for Chart.js from processed metrics.
 */
export function prepareChartData(processedMetrics, selectedMetrics, metricsConfig) {
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

// Deleted Sankey/QuickChart utilities. Only multi-graph line charting utilities are retained.


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