// processUtils.js
// Utilities for processing and transforming financial data

/**
 * Safely gets a nested value from an object using a path array.
 */
export function getNestedValue(obj, path) {
    return path.reduce((acc, key) => (acc && acc.hasOwnProperty(key)) ? acc[key] : undefined, obj);
}

/**
 * Finds a valid date string from an item, checking multiple potential date keys.
 */
export function findValidDate(item, potentialDateKeys) {
    const keys = Array.isArray(potentialDateKeys) ? potentialDateKeys : [potentialDateKeys];
    for (const key of keys) {
        if (item.hasOwnProperty(key) && typeof item[key] === 'string') {
            const dateStr = item[key].trim();
            if (dateStr && dateStr !== 'None') {
                const dateObj = new Date(dateStr);
                if (dateObj.toString() !== 'Invalid Date') {
                    return dateStr;
                }
            }
        }
    }
    return null;
}

/**
 * Rounds a date to the end of its month (YYYY-MM-DD format).
 */
export function roundDateToEndOfMonth(dateString) {
    const date = new Date(dateString + 'T00:00:00Z');
    if (isNaN(date.getTime())) {
        return null;
    }
    date.setUTCMonth(date.getUTCMonth() + 1, 1);
    date.setTime(date.getTime() - 86400000);
    return date.toISOString().slice(0, 10);
}

/**
 * Calculates Trailing Twelve Months (TTM) for a given quarterly or event-based dataset.
 */
export function calculateTTM(data) {
    if (!Array.isArray(data) || data.length < 4) return [];
    const sortedData = [...data].sort((a, b) => new Date(a.date) - new Date(b.date));
    const ttmData = [];
    for (let i = 3; i < sortedData.length; i++) {
        const currentEntry = sortedData[i];
        const p1 = sortedData[i].value;
        const p2 = sortedData[i - 1].value;
        const p3 = sortedData[i - 2].value;
        const p4 = sortedData[i - 3].value;
        const ttmSum = p1 + p2 + p3 + p4;
        ttmData.push({ date: currentEntry.date, value: ttmSum });
    }
    return ttmData;
}

/**
 * Interpolates (forward-fills) annual data to a set of target dates.
 */
export function interpolateData(sourceData, targetDates) {
    if (!Array.isArray(sourceData) || !Array.isArray(targetDates)) return [];
    const sortedSource = [...sourceData].sort((a, b) => new Date(a.date) - new Date(b.date));
    const interpolated = [];
    let sourceIndex = 0;
    let lastValue = null;
    for (const targetDate of targetDates) {
        while (sourceIndex < sortedSource.length && new Date(sortedSource[sourceIndex].date) <= new Date(targetDate)) {
            lastValue = sortedSource[sourceIndex].value;
            sourceIndex++;
        }
        if (lastValue === null || new Date(targetDate) < new Date(sortedSource[0].date)) {
            interpolated.push({ date: targetDate, value: null });
        } else {
            interpolated.push({ date: targetDate, value: lastValue });
        }
    }
    return interpolated;
}

/**
 * Calculates a derived metric (like PE Ratio or PS Ratio) based on a formula and constituent data.
 */
export function calculateDerivedMetric(formula, processedData, commonDates) {
    const derivedValues = [];
    const derivedLabels = [];
    const variablesInFormula = formula.match(/[a-zA-Z0-9_]+/g);
    const dataReferences = {};
    variablesInFormula.forEach(varName => {
        if (processedData[varName]) {
            dataReferences[varName] = processedData[varName];
        } else {
            dataReferences[varName] = {};
        }
    });
    for (const date of commonDates) {
        let currentCalculatedValue = null;
        let allConstituentsPresent = true;
        let executableFormula = formula;
        for (const varName in dataReferences) {
            const value = dataReferences[varName][date];
            if (value === undefined || value === null || isNaN(value)) {
                allConstituentsPresent = false;
                break;
            }
            executableFormula = executableFormula.replace(new RegExp(varName, 'g'), `(${value})`);
        }
        if (allConstituentsPresent) {
            try {
                if (executableFormula.includes('/')) {
                    const parts = executableFormula.split('/');
                    if (parts.length === 2) {
                        let divisorValue;
                        try {
                            divisorValue = eval(parts[1]);
                        } catch (e) {
                            allConstituentsPresent = false;
                        }
                        if (allConstituentsPresent && (divisorValue === 0 || isNaN(divisorValue) || !isFinite(divisorValue))) {
                            allConstituentsPresent = false;
                        }
                    }
                }
                if (allConstituentsPresent) {
                    const result = eval(executableFormula);
                    if (!isNaN(result) && isFinite(result)) {
                        currentCalculatedValue = result;
                    }
                }
            } catch (e) {}
        }
        derivedValues.push(currentCalculatedValue);
        derivedLabels.push(date);
    }
    return { values: derivedValues, dates: derivedLabels };
}

/**
 * Processes raw financial data, applies FX conversion, and prepares for charting.
 */
export function processFinancialData(rawData, fxRateUsed, startDate, endDate, metricsConfig, latestYahooData) {
    // Removed appendToPapertrail for modular utility
    // 1. Extract and convert raw metrics
    const extractedRawMetrics = {};

    for (const metricConfig of metricsConfig.filter(m => m.type.startsWith('raw_'))) {
        const endpoint = metricConfig.source_function;
        const isPrice = endpoint === 'TIME_SERIES_MONTHLY_ADJUSTED';
        const fxToUse = (metricConfig.fx_adjust === false) ? 1.0 : (isPrice ? 1.0 : fxRateUsed);
        const raw = rawData[endpoint];
        if (!raw || raw.error) continue;

        let dataContainer = getNestedValue(raw, [metricConfig.source_path[0]]);
        if (!dataContainer) continue;

        const tempExtracted = {};
        if (metricConfig.isTimeSeries) {
            Object.keys(dataContainer).forEach(dateStr => {
                const itemDate = new Date(dateStr);
                if (itemDate >= startDate && itemDate <= endDate) {
                    const value = parseFloat(getNestedValue(dataContainer[dateStr], metricConfig.source_path.slice(1)));
                    if (!isNaN(value)) tempExtracted[dateStr] = value;
                }
            });
            extractedRawMetrics[metricConfig.id] = tempExtracted;
        } else {
            const processedEntries = [];
            (Array.isArray(dataContainer) ? dataContainer : []).forEach(item => {
                const dateStr = findValidDate(item, metricConfig.date_keys);
                if (dateStr) {
                    const itemDate = new Date(dateStr);
                    if (itemDate >= startDate && itemDate <= endDate) {
                        const value = parseFloat(getNestedValue(item, metricConfig.source_path.slice(1)));
                        if (!isNaN(value)) {
                            const converted = value * fxToUse;
                            processedEntries.push({ date: dateStr, value: converted });
                        }
                    }
                }
            });
            extractedRawMetrics[metricConfig.id] = processedEntries;
        }
    }

    const processedMetrics = { ...extractedRawMetrics };

    if (latestYahooData && latestYahooData.price) {
        const latestPrice = latestYahooData.price;
        const latestTime = latestYahooData.regularMarketTime;
        const latestDate = latestTime 
            ? new Date(latestTime * 1000).toISOString().slice(0, 10) 
            : new Date().toISOString().slice(0, 10);
        if (!processedMetrics['price']) {
            processedMetrics['price'] = {};
        }
        processedMetrics['price'][latestDate] = latestPrice;
    }

    // TTM Metrics
    metricsConfig.filter(m => m.type === 'derived_ttm').forEach(mc => {
        processedMetrics[mc.id] = calculateTTM(processedMetrics[mc.calculation_basis]);
    });

    // Generic calculation for all derived_custom metrics
    metricsConfig.filter(m => m.type === 'derived_custom').forEach(mc => {
        const formula = mc.calculation_formula;
        // Only support simple binary operations for now
        let operation = null;
        if (formula.includes(' - ')) operation = 'subtract';
        else if (formula.includes(' / ')) operation = 'divide';
        else return;
        const [id1, id2] = formula.split(operation === 'subtract' ? ' - ' : ' / ');
        const data1 = processedMetrics[id1.trim()];
        const data2 = processedMetrics[id2.trim()];
        if (data1 && data2) {
            const result = {};
            const toMap = (data) => new Map(
                Array.isArray(data)
                    ? data.map(item => [new Date(item.date).getFullYear(), item.value])
                    : Object.entries(data).map(([date, value]) => [new Date(date).getFullYear(), value])
            );
            const map1 = toMap(data1);
            const map2 = toMap(data2);
            for (const [year, val1] of map1.entries()) {
                const val2 = map2.get(year);
                if (typeof val2 !== 'undefined') {
                    const originalDateSource = Array.isArray(data1) ? data1 : (Array.isArray(data2) ? data2 : null);
                    let originalDate;
                    if (originalDateSource) {
                        originalDate = originalDateSource.find(item => new Date(item.date).getFullYear() === year).date;
                    } else {
                        originalDate = Object.keys(data1).find(date => new Date(date).getFullYear() === year);
                    }
                    if (originalDate) {
                        if (operation === 'subtract') {
                            result[originalDate] = val1 - val2;
                        } else if (operation === 'divide' && val2 !== 0) {
                            result[originalDate] = val1 / val2;
                        }
                    }
                }
            }
            processedMetrics[mc.id] = result;
        }
    });

    // Interpolation
    const priceDates = Object.keys(processedMetrics['price'] || {}).sort();
    if (priceDates.length === 0) throw new Error('No price data available for timeframe.');

    const interpolatedMetrics = {};
    const metricsToInterpolate = new Set(metricsConfig.filter(m => m.is_plottable || [
        'ttmEps', 'rps', 'fcf', 'fcfPerShare', 'operatingCashflowPerShare',
        'payoutRatioFcf', 'payoutRatioOcf', 'commonSharesOutstanding',
        'longTermDebt', 'shortTermDebt', 'cashAndCashEquivalents', 'cashAndShortTermInvestments',
        'ebitda', 'netIncome', 'totalAssets', 'totalShareholderEquity'
    ].includes(m.id)).map(m => m.id));
    
    for (const metricId in processedMetrics) {
        if (!metricsToInterpolate.has(metricId) || metricId === 'price') {
            interpolatedMetrics[metricId] = processedMetrics[metricId];
            continue;
        }
        const dataAsArray = Array.isArray(processedMetrics[metricId]) ? processedMetrics[metricId] : Object.entries(processedMetrics[metricId]).map(([date, value]) => ({ date, value }));
        interpolatedMetrics[metricId] = interpolateData(dataAsArray, priceDates);
    }
    
    // Ratios
    metricsConfig.filter(m => m.type === 'derived_ratio').forEach(mc => {
        const [numId, denId] = mc.calculation_formula.split(' / ').map(s => s.trim());
        const numData = interpolatedMetrics[numId];
        const denData = interpolatedMetrics[denId];
        if (!numData || !denData) return;
        
        const numMap = new Map(Array.isArray(numData) ? numData.map(i => [i.date, i.value]) : Object.entries(numData));
        const denMap = new Map(Array.isArray(denData) ? denData.map(i => [i.date, i.value]) : Object.entries(denData));
        
        const ratioResult = priceDates.map(date => {
            const num = numMap.get(date);
            const den = denMap.get(date);
            let val = (num != null && den != null && den !== 0) ? num / den : null;
            if (val !== null && (mc.id === 'roa' || mc.id === 'roe')) {
                val = val * 100;
            }
            return { date, value: val };
        });
        interpolatedMetrics[mc.id] = ratioResult;
    });

    // Custom aggregate calculations (marketCap, enterpriseValue, evEbitda)
    const priceMap = new Map(priceDates.map(d => [d, interpolatedMetrics['price']?.[d] ?? null]));
    const sharesMap = new Map(priceDates.map(d => [d, interpolatedMetrics['commonSharesOutstanding']?.find(pt => pt.date === d)?.value ?? null]));
    const debtMap = new Map(priceDates.map(d => {
        const lt = interpolatedMetrics['longTermDebt']?.find(pt => pt.date === d)?.value ?? null;
        const st = interpolatedMetrics['shortTermDebt']?.find(pt => pt.date === d)?.value ?? null;
        if (lt === null && st === null) return [d, null];
        return [d, (lt || 0) + (st || 0)];
    }));
    const cashMap = new Map(priceDates.map(d => {
        const cashEquiv = interpolatedMetrics['cashAndCashEquivalents']?.find(pt => pt.date === d)?.value ?? null;
        const cashShort = interpolatedMetrics['cashAndShortTermInvestments']?.find(pt => pt.date === d)?.value ?? null;
        if (cashEquiv === null && cashShort === null) return [d, null];
        return [d, cashEquiv || cashShort || 0];
    }));
    const ebitdaMap = new Map(priceDates.map(d => [d, interpolatedMetrics['ebitda']?.find(pt => pt.date === d)?.value ?? null]));

    interpolatedMetrics['marketCap'] = priceDates.map(date => {
        const price = priceMap.get(date);
        const shares = sharesMap.get(date);
        return (price !== null && shares !== null) ? { date, value: price * shares } : { date, value: null };
    });

    interpolatedMetrics['enterpriseValue'] = priceDates.map(date => {
        const mcap = interpolatedMetrics['marketCap'].find(pt => pt.date === date)?.value ?? null;
        const debt = debtMap.get(date) ?? 0;
        const cash = cashMap.get(date) ?? 0;
        return (mcap !== null) ? { date, value: mcap + debt - cash } : { date, value: null };
    });

    interpolatedMetrics['evEbitda'] = priceDates.map(date => {
        const ev = interpolatedMetrics['enterpriseValue'].find(pt => pt.date === date)?.value ?? null;
        const ebitda = ebitdaMap.get(date);
        return (ev !== null && ebitda !== null && ebitda !== 0) ? { date, value: ev / ebitda } : { date, value: null };
    });

    return interpolatedMetrics;
}

/**
 * Formats a number as billions (B) or millions (M) with 2 decimal places.
 * @param {number} value
 * @returns {string}
 */
export function formatLargeNumber(value) {
    if (value === null || value === undefined || isNaN(value)) return '';
    const absValue = Math.abs(value);
    if (absValue >= 1e9) {
        return (value / 1e9).toFixed(2) + 'B';
    } else if (absValue >= 1e6) {
        return (value / 1e6).toFixed(2) + 'M';
    } else {
        return value.toLocaleString();
    }
}

/**
 * Converts a time series to percentage of its first non-null value.
 * Returns array of {date, value} where value is (current/start)*100 or null if not computable.
 */
export function toPercentOfStartValue(timeSeries) {
    if (!Array.isArray(timeSeries) || timeSeries.length === 0) return [];
    // Find first non-null, non-NaN, non-zero value
    let startIdx = 0;
    while (startIdx < timeSeries.length && (timeSeries[startIdx].value === null || isNaN(timeSeries[startIdx].value))) {
        startIdx++;
    }
    if (startIdx === timeSeries.length) return timeSeries.map(pt => ({...pt, value: null}));
    const startValue = timeSeries[startIdx].value;
    if (startValue === 0 || startValue === null || isNaN(startValue)) {
        // Avoid division by zero or nonsense
        return timeSeries.map(pt => ({...pt, value: null}));
    }
    return timeSeries.map(pt => {
        if (pt.value === null || isNaN(pt.value)) return {...pt, value: null};
        return {...pt, value: (pt.value / startValue) * 100};
    });
} 