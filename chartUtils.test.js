import { prepareChartData } from './chartUtils.js';
// Add tests for prepareChartData here, moved from script.test.js if any exist.
// (No prepareChartData-specific tests were present in the provided script.test.js, but this is the correct structure for future tests.) 

describe('prepareChartData', () => {
    const metricsConfig = [
        { id: 'price', label: 'Price', color: 'blue', axis: 'y' },
        { id: 'revenue', label: 'Revenue', color: 'green', axis: 'y1' },
    ];

    test('returns empty datasets and labels if processedMetrics is null', () => {
        const result = prepareChartData(null, ['price'], metricsConfig);
        expect(result).toEqual({ datasets: [], commonLabels: [] });
    });

    test('returns empty datasets if selectedMetrics is empty', () => {
        const processedMetrics = { price: { '2023-01-31': 100 } };
        const result = prepareChartData(processedMetrics, [], metricsConfig);
        expect(result.datasets).toEqual([]);
        expect(result.commonLabels).toEqual(['2023-01-31']);
    });

    test('returns correct dataset for single metric (object data)', () => {
        const processedMetrics = { price: { '2023-01-31': 100, '2023-02-28': 110 } };
        const result = prepareChartData(processedMetrics, ['price'], metricsConfig);
        expect(result.commonLabels).toEqual(['2023-01-31', '2023-02-28']);
        expect(result.datasets.length).toBe(1);
        expect(result.datasets[0].label).toBe('Price');
        expect(result.datasets[0].data).toEqual([100, 110]);
    });

    test('returns correct datasets for multiple metrics (object and array data)', () => {
        const processedMetrics = {
            price: { '2023-01-31': 100, '2023-02-28': 110 },
            revenue: [
                { date: '2023-01-31', value: 200 },
                { date: '2023-02-28', value: 220 }
            ]
        };
        const result = prepareChartData(processedMetrics, ['price', 'revenue'], metricsConfig);
        expect(result.commonLabels).toEqual(['2023-01-31', '2023-02-28']);
        expect(result.datasets.length).toBe(2);
        expect(result.datasets[0].label).toBe('Price');
        expect(result.datasets[0].data).toEqual([100, 110]);
        expect(result.datasets[1].label).toBe('Revenue');
        expect(result.datasets[1].data).toEqual([200, 220]);
    });

    test('fills missing data with nulls', () => {
        const processedMetrics = {
            price: { '2023-01-31': 100, '2023-02-28': 110 },
            revenue: [
                { date: '2023-01-31', value: 200 }
            ]
        };
        const result = prepareChartData(processedMetrics, ['price', 'revenue'], metricsConfig);
        expect(result.commonLabels).toEqual(['2023-01-31', '2023-02-28']);
        expect(result.datasets[1].data).toEqual([200, null]);
    });
}); 