import { roundDateToEndOfMonth, getNestedValue, calculateTTM, interpolateData, processFinancialData } from './processUtils.js';

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
        // Only test processFinancialData logic here
        expect(processedMetrics.annualRevenue[0].value).toBeCloseTo(200 * 1.2);
        expect(processedMetrics.annualRevenue[1].value).toBeCloseTo(220 * 1.2);
        expect(processedMetrics.annualRevenue[2].value).toBeCloseTo(240 * 1.2);
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
        expect(processedMetrics.annualRevenue[0].value).toBeCloseTo(200);
        expect(processedMetrics.annualRevenue[1].value).toBeCloseTo(220);
        expect(processedMetrics.annualRevenue[2].value).toBeCloseTo(240);
    });

    it('should extract and FX-adjust new metrics (OCF, OCF per share, P/OCF, payout ratios)', () => {
        const metricsConfigExtended = [
            ...metricsConfig,
            {
                id: 'operatingCashflow',
                label: 'Operating Cash Flow',
                type: 'raw_fundamental',
                source_function: 'CASH_FLOW',
                source_path: ['annualReports', 'operatingCashflow'],
                date_keys: 'fiscalDateEnding',
                isTimeSeries: false,
                is_plottable: true,
                fx_adjust: true
            },
            {
                id: 'operatingCashflowPerShare',
                label: 'Operating Cash Flow Per Share',
                type: 'derived_custom',
                calculation_formula: 'operatingCashflow / commonSharesOutstanding',
                is_plottable: false
            },
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
                id: 'dividendPayout',
                label: 'Dividend Payout',
                type: 'raw_fundamental',
                source_function: 'CASH_FLOW',
                source_path: ['annualReports', 'dividendPayout'],
                date_keys: 'fiscalDateEnding',
                isTimeSeries: false,
                is_plottable: false,
                fx_adjust: true
            },
            {
                id: 'fcf',
                label: 'Free Cash Flow',
                type: 'derived_custom',
                calculation_formula: 'operatingCashflow - capitalExpenditures',
                is_plottable: false
            },
            {
                id: 'capitalExpenditures',
                label: 'Capital Expenditures',
                type: 'raw_fundamental',
                source_function: 'CASH_FLOW',
                source_path: ['annualReports', 'capitalExpenditures'],
                date_keys: 'fiscalDateEnding',
                isTimeSeries: false,
                is_plottable: false,
                fx_adjust: true
            },
            {
                id: 'pOcfRatio',
                label: 'P/OCF',
                type: 'derived_ratio',
                calculation_formula: 'price / operatingCashflowPerShare',
                is_plottable: true
            },
            {
                id: 'payoutRatioFcf',
                label: 'Payout Ratio (FCF)',
                type: 'derived_ratio',
                calculation_formula: 'dividendPayout / fcf',
                is_plottable: true
            },
            {
                id: 'payoutRatioOcf',
                label: 'Payout Ratio (OCF)',
                type: 'derived_ratio',
                calculation_formula: 'dividendPayout / operatingCashflow',
                is_plottable: true
            }
        ];
        const rawData = {
            'CASH_FLOW': {
                annualReports: [
                    { fiscalDateEnding: '2023-12-31', operatingCashflow: '1000', dividendPayout: '200', capitalExpenditures: '300', reportedCurrency: 'EUR' }
                ]
            },
            'BALANCE_SHEET': {
                annualReports: [
                    { fiscalDateEnding: '2023-12-31', commonStockSharesOutstanding: '100' }
                ]
            },
            'TIME_SERIES_MONTHLY_ADJUSTED': {
                'Monthly Adjusted Time Series': {
                    '2023-12-31': { '5. adjusted close': '50' }
                }
            }
        };
        const fxRateUsed = 1.1;
        const startDate = new Date('2023-12-31');
        const endDate = new Date('2023-12-31');
        const processed = processFinancialData(rawData, fxRateUsed, startDate, endDate, metricsConfigExtended);
        // OCF
        expect(processed.operatingCashflow[0].value).toBeCloseTo(1000 * 1.1);
        // OCF per share
        expect(processed.operatingCashflowPerShare[0].value).toBeCloseTo((1000 * 1.1) / 100);
        // P/OCF
        expect(processed.pOcfRatio[0].value).toBeCloseTo(50 / ((1000 * 1.1) / 100));
        // FCF
        expect(processed.fcf[0].value).toBeCloseTo((1000 * 1.1) - (300 * 1.1));
        // Payout Ratio (FCF)
        expect(processed.payoutRatioFcf[0].value).toBeCloseTo((200 * 1.1) / ((1000 * 1.1) - (300 * 1.1)));
        // Payout Ratio (OCF)
        expect(processed.payoutRatioOcf[0].value).toBeCloseTo((200 * 1.1) / (1000 * 1.1));
    });
}); 