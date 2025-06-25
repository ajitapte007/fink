import { roundDateToEndOfMonth, getNestedValue, calculateTTM, interpolateData, processFinancialData, prepareChartData } from './script.js';

describe('roundDateToEndOfMonth', () => {
    test('should round a mid-month date to the end of that month', () => {
        const inputDate = '2023-05-15';
        const expectedDate = '2023-05-31';
        expect(roundDateToEndOfMonth(inputDate)).toBe(expectedDate);
    });

    test('should handle the end of a month correctly', () => {
        const inputDate = '2023-02-28';
        const expectedDate = '2023-02-28';
        expect(roundDateToEndOfMonth(inputDate)).toBe(expectedDate);
    });

    test('should handle the beginning of a month correctly', () => {
        const inputDate = '2023-09-01';
        const expectedDate = '2023-09-30';
        expect(roundDateToEndOfMonth(inputDate)).toBe(expectedDate);
    });

    test('should handle a leap year correctly', () => {
        const inputDate = '2024-02-10';
        const expectedDate = '2024-02-29';
        expect(roundDateToEndOfMonth(inputDate)).toBe(expectedDate);
    });

    test('should return null for an invalid date string', () => {
        const inputDate = 'not a real date';
        expect(roundDateToEndOfMonth(inputDate)).toBeNull();
    });
});

describe('getNestedValue', () => {
    const testObj = {
        a: {
            b: {
                c: 123
            },
            d: [
                { e: 456 },
                { f: 789 }
            ]
        }
    };

    test('should retrieve a deeply nested value', () => {
        expect(getNestedValue(testObj, ['a', 'b', 'c'])).toBe(123);
    });

    test('should retrieve a value from an array within the object', () => {
        expect(getNestedValue(testObj, ['a', 'd', '0', 'e'])).toBe(456);
    });

    test('should return undefined for a path that does not exist', () => {
        expect(getNestedValue(testObj, ['a', 'x', 'y'])).toBeUndefined();
    });

    test('should return undefined for an incomplete path', () => {
        expect(getNestedValue(testObj, ['a', 'b'])).toEqual({ c: 123 });
    });

    test('should return undefined when the starting object is null or undefined', () => {
        expect(getNestedValue(null, ['a', 'b'])).toBeUndefined();
        expect(getNestedValue(undefined, ['a', 'b'])).toBeUndefined();
    });
});

describe('calculateTTM', () => {
    const quarterlyEPS = [
        { date: '2023-03-31', value: 1.0 },
        { date: '2023-06-30', value: 1.1 },
        { date: '2023-09-30', value: 1.2 },
        { date: '2023-12-31', value: 1.3 },
        { date: '2024-03-31', value: 1.4 }
    ];

    const quarterlyDividends = [
        { date: '2023-02-15', value: 0.5 },
        { date: '2023-05-15', value: 0.5 },
        { date: '2023-08-15', value: 0.6 },
        { date: '2023-11-15', value: 0.6 },
        { date: '2024-02-15', value: 0.7 }
    ];

    test('should calculate TTM EPS correctly', () => {
        const ttmEps = calculateTTM(quarterlyEPS);
        expect(ttmEps).toHaveLength(2);
        expect(ttmEps[0].value).toBeCloseTo(1.0 + 1.1 + 1.2 + 1.3);
        expect(ttmEps[1].value).toBeCloseTo(1.1 + 1.2 + 1.3 + 1.4);
        expect(ttmEps[1].date).toBe('2024-03-31');
    });

    test('should calculate TTM Dividends correctly by summing', () => {
        const ttmDividends = calculateTTM(quarterlyDividends);
        expect(ttmDividends).toHaveLength(2);
        expect(ttmDividends[0].value).toBeCloseTo(0.5 + 0.5 + 0.6 + 0.6);
        expect(ttmDividends[1].value).toBeCloseTo(0.5 + 0.6 + 0.6 + 0.7);
        expect(ttmDividends[1].date).toBe('2024-02-15');
    });

    test('should return an empty array if there are fewer than 4 data points', () => {
        expect(calculateTTM(quarterlyEPS.slice(0, 3))).toEqual([]);
    });

    test('should return an empty array for null or empty input', () => {
        expect(calculateTTM(null)).toEqual([]);
        expect(calculateTTM([])).toEqual([]);
    });
});

describe('interpolateData', () => {
    const annualData = [
        { date: '2022-12-31', value: 100 },
        { date: '2023-12-31', value: 200 }
    ];
    const targetDates = ['2022-11-30', '2022-12-31', '2023-01-31', '2023-12-31', '2024-01-31'];

    test('should forward-fill data correctly', () => {
        const interpolated = interpolateData(annualData, targetDates);
        expect(interpolated).toHaveLength(targetDates.length);
        expect(interpolated[0].value).toBeNull(); // Before first data point
        expect(interpolated[1].value).toBe(100);  // Exact match
        expect(interpolated[2].value).toBe(100);  // Forward-filled
        expect(interpolated[3].value).toBe(200);  // Exact match
        expect(interpolated[4].value).toBe(200);  // Forward-filled
    });

    test('should handle empty source data', () => {
        const interpolated = interpolateData([], targetDates);
        expect(interpolated).toEqual(targetDates.map(date => ({ date, value: null })));
    });

    test('should handle empty target dates', () => {
        expect(interpolateData(annualData, [])).toEqual([]);
    });

    test('should return null values for all dates if target dates are all before the first data point', () => {
        const earlyTargetDates = ['2021-01-31', '2021-02-28'];
        const interpolated = interpolateData(annualData, earlyTargetDates);
        expect(interpolated).toEqual(earlyTargetDates.map(date => ({ date, value: null })));
    });
});

describe('processFinancialData', () => {
    const metricsConfig = [
        {
            id: 'price',
            label: 'Adjusted Close Price',
            type: 'raw_time_series',
            source_function: 'TIME_SERIES_MONTHLY_ADJUSTED',
            source_path: ['Monthly Adjusted Time Series', '5. adjusted close'],
            isTimeSeries: true,
            is_plottable: true,
            fx_adjust: false
        },
        {
            id: 'annualRevenue',
            label: 'Total Revenue (Annual)',
            type: 'raw_fundamental',
            source_function: 'INCOME_STATEMENT',
            source_path: ['annualReports', 'totalRevenue'],
            date_keys: 'fiscalDateEnding',
            isTimeSeries: false,
            is_plottable: true,
            fx_adjust: true
        },
        {
            id: 'commonSharesOutstanding',
            label: 'Shares Outstanding',
            type: 'raw_fundamental',
            source_function: 'BALANCE_SHEET',
            source_path: ['annualReports', 'commonStockSharesOutstanding'],
            date_keys: 'fiscalDateEnding',
            isTimeSeries: false,
            is_plottable: false,
            fx_adjust: false
        }
    ];

    it('should apply FX rates to non-price metrics and not to price', () => {
        const rawData = {
            'TIME_SERIES_MONTHLY_ADJUSTED': {
                'Monthly Adjusted Time Series': {
                    '2023-01-31': { '5. adjusted close': '100' },
                    '2023-02-28': { '5. adjusted close': '110' },
                    '2023-03-31': { '5. adjusted close': '120' }
                }
            },
            'INCOME_STATEMENT': {
                annualReports: [
                    { fiscalDateEnding: '2023-01-31', totalRevenue: '200', reportedCurrency: 'EUR' },
                    { fiscalDateEnding: '2023-02-28', totalRevenue: '220', reportedCurrency: 'EUR' },
                    { fiscalDateEnding: '2023-03-31', totalRevenue: '240', reportedCurrency: 'EUR' }
                ]
            }
        };
        const fxRateUsed = 1.2;
        const startDate = new Date('2023-01-31');
        const endDate = new Date('2023-03-31');
        const processedMetrics = processFinancialData(rawData, fxRateUsed, startDate, endDate, metricsConfig);
        const chartData = prepareChartData(processedMetrics, ['price', 'annualRevenue'], metricsConfig);
        // Find the dataset for annualRevenue
        const annualRevenueDs = chartData.datasets.find(d => d.label === 'Total Revenue (Annual)');
        expect(annualRevenueDs).toBeDefined();
        // Check all values
        expect(annualRevenueDs.data[0]).toBeCloseTo(200 * 1.2);
        expect(annualRevenueDs.data[1]).toBeCloseTo(220 * 1.2);
        expect(annualRevenueDs.data[2]).toBeCloseTo(240 * 1.2);
    });

    it('should not apply FX if fxRates is empty (USD passthrough)', () => {
        const rawData = {
            'TIME_SERIES_MONTHLY_ADJUSTED': {
                'Monthly Adjusted Time Series': {
                    '2023-01-31': { '5. adjusted close': '100' },
                    '2023-02-28': { '5. adjusted close': '110' },
                    '2023-03-31': { '5. adjusted close': '120' }
                }
            },
            'INCOME_STATEMENT': {
                annualReports: [
                    { fiscalDateEnding: '2023-01-31', totalRevenue: '200', reportedCurrency: 'USD' },
                    { fiscalDateEnding: '2023-02-28', totalRevenue: '220', reportedCurrency: 'USD' },
                    { fiscalDateEnding: '2023-03-31', totalRevenue: '240', reportedCurrency: 'USD' }
                ]
            }
        };
        const fxRateUsed = 1.0; // USD passthrough
        const startDate = new Date('2023-01-31');
        const endDate = new Date('2023-03-31');
        const processedMetrics = processFinancialData(rawData, fxRateUsed, startDate, endDate, metricsConfig);
        const chartData = prepareChartData(processedMetrics, ['price', 'annualRevenue'], metricsConfig);
        // Find the dataset for annualRevenue
        const annualRevenueDs = chartData.datasets.find(d => d.label === 'Total Revenue (Annual)');
        expect(annualRevenueDs).toBeDefined();
        expect(annualRevenueDs.data[0]).toBeCloseTo(200);
        expect(annualRevenueDs.data[1]).toBeCloseTo(220);
        expect(annualRevenueDs.data[2]).toBeCloseTo(240);
    });
}); 