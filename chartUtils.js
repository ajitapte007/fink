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
            tension: 0.1
        });
    }
    return { datasets: datasetsForChart, commonLabels };
} 