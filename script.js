// DOM Elements
const tickerInput = document.getElementById('tickerInput');
const alphaVantageApiKeyInput = document.getElementById('alphaVantageApiKey');
const timeframeSelect = document.getElementById('timeframeSelect');
const leftSlider = document.getElementById('leftSlider');
const rightSlider = document.getElementById('rightSlider');
const yearRangeLabel = document.getElementById('year-range-label');
const sliderTrack = document.querySelector('.slider-track');
const fetchButton = document.getElementById('fetchButton');
const messageDisplay = document.getElementById('message');
const priceChartCanvas = document.getElementById('priceChart');
const papertrailLog = document.getElementById('papertrailLog');
const loadingSpinner = document.getElementById('loadingSpinner');
const togglePriceCheckbox = document.getElementById('togglePrice');
const selectPERatioRadio = document.getElementById('selectPERatio');
const selectPSRatioRadio = document.getElementById('selectPSRatio');
const selectSharesOutstandingRadio = document.getElementById('selectSharesOutstanding');
const selectDividendsRadio = document.getElementById('selectDividends');
const ratioSelectRadios = document.querySelectorAll('input[name="ratioSelect"]');


let myChart; // Variable to hold the Chart.js instance
let lastFetchedChartData = null; // Store last fetched and processed data
let globalProcessedMetrics = {}; // Holds all processed metric data for a given request

// LRU Cache for Alpha Vantage API calls
const alphaVantageCache = new Map();
const CACHE_MAX_SIZE = 100;

// Global knowledge base for Alpha Vantage API structure
let alphaVantageAPIKnowledgeBase = {};

/**
 * Definition of all supported financial metrics and their properties.
 * This modular configuration makes it easy to add or modify metrics.
 *
 * @property {string} id - Unique internal identifier for the metric.
 * @property {string} label - Display name in the UI and chart legend.
 * @property {string} type - Category of the metric:
 * - 'raw_time_series': Directly fetched time series (e.g., daily/monthly prices).
 * - 'raw_fundamental': Directly fetched fundamental data (e.g., annual reports, quarterly earnings).
 * - 'derived_ttm': Trailing Twelve Months calculation based on another raw metric.
 * - 'derived_ratio': Ratio calculated from other raw or derived metrics.
 * @property {string} [source_function] - Alpha Vantage API function to call.
 * @property {Array<string>} [source_path] - JSON path within API response to extract data.
 * @property {string|Array<string>} [date_keys] - Key(s) to find the date within the source data item.
 * @property {string} [calculation_formula] - Formula for derived metrics, using other metric IDs.
 * @property {string} [calculation_basis] - For TTM, the ID of the raw metric it's based on.
 * @property {string} [color] - Line color on the chart (CSS color string).
 * @property {string} [axis] - Which Y-axis to plot on ('y-price' for left, 'y-ratio' for right).
 * @property {string} [ui_radio_id] - HTML ID of the radio button for this metric (if part of a group).
 * @property {boolean} is_plottable - Whether this metric should be plotted on the chart.
 * @property {boolean} [isTimeSeries] - Indicates if the source data is a time series (dates as keys).
 */
export const metricsConfig = [
    {
        id: 'price',
        label: 'Adjusted Close Price',
        type: 'raw_time_series',
        source_function: 'TIME_SERIES_MONTHLY_ADJUSTED',
        source_path: ['Monthly Adjusted Time Series', '5. adjusted close'],
        date_keys: null, // Dates are object keys
        color: 'rgb(75, 192, 192)',
        axis: 'y-price',
        is_plottable: true,
        isTimeSeries: true // Explicitly set to true
    },
    {
        id: 'quarterlyEPS',
        label: 'Reported EPS (Quarterly)',
        type: 'raw_fundamental',
        source_function: 'EARNINGS',
        source_path: ['quarterlyEarnings', 'reportedEPS'],
        date_keys: 'fiscalDateEnding',
        is_plottable: false, // Not plotted directly, used for TTM
        isTimeSeries: false // Explicitly set to false
    },
    {
        id: 'ttmEps',
        label: 'TTM EPS',
        type: 'derived_ttm',
        calculation_basis: 'quarterlyEPS', // Based on quarterlyEPS
        color: 'rgb(100, 100, 255)', // Not directly plotted, internal calculation
        axis: null,
        is_plottable: false
    },
    {
        id: 'annualRevenue',
        label: 'Total Revenue (Annual)',
        type: 'raw_fundamental',
        source_function: 'INCOME_STATEMENT',
        source_path: ['annualReports', 'totalRevenue'],
        date_keys: 'fiscalDateEnding',
        is_plottable: false, // Not plotted directly, used for PS Ratio
        isTimeSeries: false // Explicitly set to false
    },
    {
        id: 'commonSharesOutstanding',
        label: 'Shares Outstanding',
        type: 'raw_fundamental', // This is raw data, not derived
        source_function: 'BALANCE_SHEET',
        source_path: ['annualReports', 'commonStockSharesOutstanding'],
        date_keys: 'fiscalDateEnding',
        color: 'rgb(0, 123, 255)',
        axis: 'y-ratio',
        ui_radio_id: 'selectSharesOutstanding',
        is_plottable: true, // Directly plottable
        isTimeSeries: false // Explicitly set to false
    },
    {
        id: 'dividends',
        label: 'Dividend Amount (Raw)',
        type: 'raw_time_series', // Or raw_event_series
        source_function: 'DIVIDENDS',
        source_path: ['data', 'amount'],
        date_keys: 'ex_dividend_date',
        is_plottable: false, // Not plotted directly, used for TTM Dividends
        isTimeSeries: false // FIX: Dividend data is an array of objects, not a time series object
    },
    {
        id: 'ttmDividends',
        label: 'TTM Dividends',
        type: 'derived_ttm',
        calculation_basis: 'dividends', // Based on raw dividends
        color: 'rgb(255, 159, 64)',
        axis: 'y-ratio',
        ui_radio_id: 'selectDividends',
        is_plottable: true
    },
    {
        id: 'peRatio',
        label: 'PE Ratio',
        type: 'derived_ratio',
        calculation_formula: 'price / ttmEps', // Using IDs from this config
        color: 'rgb(255, 99, 132)',
        axis: 'y-ratio',
        ui_radio_id: 'selectPERatio',
        is_plottable: true
    },
    {
        id: 'psRatio',
        label: 'PS Ratio',
        type: 'derived_ratio',
        calculation_formula: 'price / rps', // Using IDs from this config
        color: 'rgb(54, 162, 235)',
        axis: 'y-ratio',
        ui_radio_id: 'selectPSRatio',
        is_plottable: true
    },
    {
        id: 'rps', // Revenue Per Share - an intermediate derived metric for PS Ratio
        label: 'Revenue Per Share',
        type: 'derived_custom', // Custom derived, not necessarily TTM or ratio itself
        calculation_formula: 'annualRevenue / commonSharesOutstanding',
        is_plottable: false
    },
    {
        id: 'revenues',
        label: 'Revenues',
        type: 'raw_fundamental',
        source_function: 'INCOME_STATEMENT',
        source_path: ['annualReports', 'totalRevenue'],
        date_keys: 'fiscalDateEnding',
        color: 'rgb(153, 102, 255)',
        axis: 'y-ratio',
        ui_radio_id: 'selectRevenues',
        is_plottable: true,
        isTimeSeries: false
    },
    {
        id: 'netIncome',
        label: 'Net Income',
        type: 'raw_fundamental',
        source_function: 'INCOME_STATEMENT',
        source_path: ['annualReports', 'netIncome'],
        date_keys: 'fiscalDateEnding',
        color: 'rgb(255, 205, 86)',
        axis: 'y-ratio',
        ui_radio_id: 'selectNetIncome',
        is_plottable: true,
        isTimeSeries: false
    },
    {
        id: 'annualEPS',
        label: 'EPS (Annual)',
        type: 'raw_fundamental',
        source_function: 'EARNINGS',
        source_path: ['annualEarnings', 'reportedEPS'],
        date_keys: 'fiscalDateEnding',
        color: 'rgb(75, 192, 192)',
        axis: 'y-ratio',
        ui_radio_id: 'selectEPS',
        is_plottable: true,
        isTimeSeries: false
    },
    {
        id: 'capitalExpenditures',
        label: 'Capital Expenditures',
        type: 'raw_fundamental',
        source_function: 'CASH_FLOW',
        source_path: ['annualReports', 'capitalExpenditures'],
        date_keys: 'fiscalDateEnding',
        color: 'rgb(255, 99, 132)',
        axis: 'y-ratio',
        ui_radio_id: 'selectCapex',
        is_plottable: true,
        isTimeSeries: false
    },
    {
        id: 'operatingCashflow',
        label: 'Operating Cashflow',
        type: 'raw_fundamental',
        source_function: 'CASH_FLOW',
        source_path: ['annualReports', 'operatingCashflow'],
        date_keys: 'fiscalDateEnding',
        is_plottable: false, // For calculation only
        isTimeSeries: false
    },
    {
        id: 'fcf',
        label: 'Free Cash Flow',
        type: 'derived_custom',
        calculation_formula: 'operatingCashflow - capitalExpenditures',
        color: 'rgb(54, 162, 235)',
        axis: 'y-ratio',
        ui_radio_id: 'selectFCF',
        is_plottable: true
    }
];


/**
 * Adds an item to the LRU cache.
 * @param {string} key The cache key (e.g., API URL).
 * @param {object} value The data to cache.
 */
function addToCache(key, value) {
    if (alphaVantageCache.has(key)) {
        alphaVantageCache.delete(key);
    }
    if (alphaVantageCache.size >= CACHE_MAX_SIZE) {
        const oldestKey = alphaVantageCache.keys().next().value;
        alphaVantageCache.delete(oldestKey);
        appendToPapertrail(`Cache full. Evicted oldest entry: ${oldestKey}`);
    }
    alphaVantageCache.set(key, value);
    appendToPapertrail(`Added to cache: ${key}`);
}

/**
 * Retrieves an item from the LRU cache. Marks the item as most recently used.
 * @param {string} key The cache key.
 * @returns {object|undefined} The cached data, or undefined if not found.
 */
function getFromCache(key) {
    if (alphaVantageCache.has(key)) {
        const value = alphaVantageCache.get(key);
        alphaVantageCache.delete(key);
        alphaVantageCache.set(key, value);
        appendToPapertrail(`Served from cache: ${key}`);
        return value;
    }
    return undefined;
}

/**
 * Displays a message to the user with a specific type (success, error, info).
 * @param {string} msg The message to display.
 * @param {'success'|'error'|'info'} type The type of message.
 */
function displayMessage(msg, type) {
    messageDisplay.textContent = msg;
    messageDisplay.className = `message w-full ${type}`;
    messageDisplay.classList.remove('hidden');
}

/**
 * Appends a message to the papertrail log.
 * @param {string} msg The message to log.
 */
function appendToPapertrail(msg) {
    papertrailLog.classList.remove('hidden');
    const p = document.createElement('p');
    p.textContent = `• ${msg}`;
    papertrailLog.appendChild(p);
    papertrailLog.scrollTop = papertrailLog.scrollHeight;
}

/**
 * Clears the papertrail log.
 */
function clearPapertrail() {
    papertrailLog.classList.add('hidden');
    papertrailLog.innerHTML = '<h3 class="text-lg font-semibold text-gray-700 mb-2">Execution Papertrail:</h3>';
}

/**
 * Shows the loading spinner.
 */
function showLoadingSpinner() {
    loadingSpinner.style.display = 'block';
    fetchButton.disabled = true;
}

/**
 * Hides the loading spinner.
 */
function hideLoadingSpinner() {
    loadingSpinner.style.display = 'none';
    fetchButton.disabled = false;
}

/**
 * Safely gets a nested value from an object using a path array.
 * @param {object} obj The object to traverse.
 * @param {string[]} path The array of keys/indices representing the path.
 * @returns {any|undefined} The value at the specified path, or undefined if not found.
 */
export function getNestedValue(obj, path) {
    return path.reduce((acc, key) => (acc && acc.hasOwnProperty(key)) ? acc[key] : undefined, obj);
}

/**
 * Finds a valid date string from an item, checking multiple potential date keys.
 * @param {object} item An object from which to extract a date.
 * @param {string|string[]} potentialDateKeys A string or array of strings representing potential date keys.
 * @returns {string|null} The first valid date string found, or null.
 */
function findValidDate(item, potentialDateKeys) {
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
 * @param {string} dateString A date string in YYYY-MM-DD format.
 * @returns {string} The date rounded to the end of the month in YYYY-MM-DD format.
 */
export function roundDateToEndOfMonth(dateString) {
    // Appending 'T00:00:00Z' ensures the date is parsed as UTC midnight
    const date = new Date(dateString + 'T00:00:00Z');
    if (isNaN(date.getTime())) {
        return null; // Handle invalid date strings
    }
    // Go to the first day of the next month in UTC
    date.setUTCMonth(date.getUTCMonth() + 1, 1);
    // Go back one day (in milliseconds) to get the last day of the previous month
    date.setTime(date.getTime() - 86400000); // 86400000ms = 1 day
    
    return date.toISOString().slice(0, 10); // Format YYYY-MM-DD
}

/**
 * Initializes the Alpha Vantage API knowledge base from metricsConfig.
 */
async function initializeAlphaVantageDataKnowledgeBase() {
    appendToPapertrail('Initializing Alpha Vantage API knowledge base from metrics configuration...');
    alphaVantageAPIKnowledgeBase = {}; // Reset to ensure fresh init

    metricsConfig.forEach(metric => {
        // Use a unique key combining function and a relevant part of the path
        // For raw metrics, store their definition for later extraction
        if (metric.type.startsWith('raw_')) {
            const key = JSON.stringify(metric.source_path); // Use stringified path as key
            alphaVantageAPIKnowledgeBase[key] = {
                function: metric.source_function,
                fullPath: metric.source_path,
                display: metric.label,
                isTimeSeries: metric.isTimeSeries, // Directly use from metricConfig
                dateExtractionKey: metric.date_keys
            };
        }
        // Derived metrics don't need to be in alphaVantageAPIKnowledgeBase as they are calculated locally
    });
    appendToPapertrail(`Alpha Vantage knowledge base initialized with ${Object.keys(alphaVantageAPIKnowledgeBase).length} raw metrics.`);
}

/**
 * Calculates a derived metric (like PE Ratio or PS Ratio) based on a formula and constituent data.
 * @param {string} formula The formula string (e.g., "price / ttmEps"). Uses metric IDs as variables.
 * @param {object} processedData - Object containing all processed (and potentially TTM) data keyed by metric ID.
 * @param {string[]} commonDates - Sorted array of dates to align on for calculation.
 * @returns {{values: number[], dates: string[]}} Calculated derived metric values and corresponding dates.
 */
function calculateDerivedMetric(formula, processedData, commonDates) {
    appendToPapertrail(`Calculating derived metric using formula: ${formula}`);
    const derivedValues = [];
    const derivedLabels = [];

    // Replace metric IDs in the formula with their actual data values for each date
    // Example: "price / ttmEps" becomes "processedData['price'][date] / processedData['ttmEps'][date]"
    const variablesInFormula = formula.match(/[a-zA-Z0-9_]+/g); // Basic regex to extract potential variable names

    const dataReferences = {}; // Map variable name (metric ID) to its data object
    variablesInFormula.forEach(varName => {
        if (processedData[varName]) { // Check if the variable (metric ID) exists in processedData
            dataReferences[varName] = processedData[varName];
        } else {
            appendToPapertrail(`Warning: Data for variable '${varName}' in formula '${formula}' is missing. Calculation might be incomplete.`);
            dataReferences[varName] = {}; // Provide empty object to avoid errors
        }
    });

    // Iterate through commonDates to calculate for each point
    for (const date of commonDates) {
        let currentCalculatedValue = null;
        let allConstituentsPresent = true;
        let executableFormula = formula;

        // Substitute actual values for variables in the formula for this specific date
        for (const varName in dataReferences) {
            const value = dataReferences[varName][date]; // Get value for this date
            if (value === undefined || value === null || isNaN(value)) {
                allConstituentsPresent = false;
                break;
            }
            executableFormula = executableFormula.replace(new RegExp(varName, 'g'), `(${value})`);
        }

        if (allConstituentsPresent) {
            try {
                // Check for division by zero before evaluating
                if (executableFormula.includes('/')) {
                    const parts = executableFormula.split('/');
                    if (parts.length === 2) {
                        let divisorValue;
                        try {
                            divisorValue = eval(parts[1]); // Safely evaluate divisor
                        } catch (e) {
                            appendToPapertrail(`Error evaluating divisor part "${parts[1]}" for date ${date}: ${e.message}`);
                            allConstituentsPresent = false; // Mark as not calculable
                        }

                        if (allConstituentsPresent && (divisorValue === 0 || isNaN(divisorValue) || !isFinite(divisorValue))) {
                            appendToPapertrail(`Warning: Division by zero, invalid, or non-finite divisor (${divisorValue}) for date ${date} in formula: ${executableFormula}.`);
                            allConstituentsPresent = false;
                        }
                    }
                }

                if (allConstituentsPresent) {
                    const result = eval(executableFormula); // Evaluate the complete numerical formula string
                    if (!isNaN(result) && isFinite(result)) {
                        currentCalculatedValue = result;
                    } else {
                        appendToPapertrail(`Warning: Formula evaluation for derived metric resulted in non-finite value for date ${date}: ${executableFormula}`);
                    }
                }
            } catch (e) {
                appendToPapertrail(`Error evaluating formula for derived metric on date ${date}: ${e.message}. Formula: ${executableFormula}`);
            }
        }
        derivedValues.push(currentCalculatedValue);
        derivedLabels.push(date);
    }
    appendToPapertrail(`Derived metric calculated for ${derivedValues.filter(v => v !== null).length} points.`);
    return { values: derivedValues, dates: derivedLabels };
}


// Helper function to escape regex special characters for use in new RegExp
function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); // $& means the matched substring
}

/**
 * Fetches and processes financial data based on metricsConfig.
 * @param {string} ticker The stock ticker symbol.
 * @param {string} alphaVantageApiKey Your Alpha Vantage API key.
 * @param {number} startYearAgo - How many years ago the data should start.
 * @param {number} endYearAgo - How many years ago the data should end.
 * @returns {Promise<object>}
 */
async function fetchAndProcessFinancialData(ticker, alphaVantageApiKey, startYearAgo, endYearAgo) {
    globalProcessedMetrics = {}; // Reset on each run
    appendToPapertrail('Step 1: Fetching all required Alpha Vantage data...');
    const fetchedRawData = {};
    const alphaVantageCalls = [];

    const functionsToFetch = new Set(metricsConfig.map(m => m.source_function).filter(Boolean));

    for (const func of Array.from(functionsToFetch)) {
        let url = `https://www.alphavantage.co/query?function=${func}&symbol=${ticker}&apikey=${alphaVantageApiKey}`;
        if (func === 'TIME_SERIES_MONTHLY_ADJUSTED') {
            url += `&outputsize=full`;
        }

        const cachedData = getFromCache(url);
        if (cachedData) {
            fetchedRawData[func] = cachedData;
        } else {
            alphaVantageCalls.push(
                fetch(url)
                    .then(response => response.json())
                    .then(data => {
                        if (data["Error Message"] || data["Note"]) {
                            throw new Error(data["Error Message"] || data["Note"] || `API error for ${func}.`);
                        }
                        fetchedRawData[func] = data;
                        addToCache(url, data);
                    })
                    .catch(error => {
                        fetchedRawData[func] = { error: `Failed to fetch ${func}: ${error.message}` };
                    })
            );
        }
    }
    await Promise.all(alphaVantageCalls);

    appendToPapertrail('Step 2: Extracting and filtering raw metrics...');
    const extractedRawMetrics = {};
    const now = new Date();
    const startDate = new Date(new Date().setFullYear(now.getFullYear() - startYearAgo));
    const endDate = new Date(new Date().setFullYear(now.getFullYear() - endYearAgo));

    for (const metricConfig of metricsConfig.filter(m => m.type.startsWith('raw_'))) {
        const rawData = fetchedRawData[metricConfig.source_function];
        if (!rawData || rawData.error) continue;

        let dataContainer = getNestedValue(rawData, [metricConfig.source_path[0]]);
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
                        if (!isNaN(value)) processedEntries.push({ date: dateStr, value });
                    }
                }
            });
            extractedRawMetrics[metricConfig.id] = processedEntries;
        }
    }

    appendToPapertrail('Step 3: Processing derived metrics...');
    const processedMetrics = { ...extractedRawMetrics };

    // TTM Metrics
    metricsConfig.filter(m => m.type === 'derived_ttm').forEach(mc => {
        processedMetrics[mc.id] = calculateTTM(processedMetrics[mc.calculation_basis]);
    });

    // Custom Derived Metrics (RPS, FCF)
    const calculateCustomMetric = (metricId, formula, operation) => {
        const metricConf = metricsConfig.find(m => m.id === metricId);
        if (!metricConf) return;
        
        const [id1, id2] = formula.split(operation === 'subtract' ? ' - ' : ' / ');
        const data1 = processedMetrics[id1.trim()];
        const data2 = processedMetrics[id2.trim()];
        
        if (data1 && data2) {
            const result = {};
            const map1 = new Map(data1.map(item => [new Date(item.date).getFullYear(), item.value]));
            const map2 = new Map(data2.map(item => [new Date(item.date).getFullYear(), item.value]));

            for (const [year, val1] of map1.entries()) {
                const val2 = map2.get(year);
                if (typeof val2 !== 'undefined') {
                    const originalDate = data1.find(item => new Date(item.date).getFullYear() === year).date;
                    if (operation === 'subtract') {
                        result[originalDate] = val1 - val2;
                    } else if (val2 !== 0) {
                        result[originalDate] = val1 / val2;
                    }
                }
            }
            processedMetrics[metricId] = result;
        }
    };

    calculateCustomMetric('rps', 'annualRevenue / commonSharesOutstanding', 'divide');
    calculateCustomMetric('fcf', 'operatingCashflow - capitalExpenditures', 'subtract');

    // Interpolation
    const priceDates = Object.keys(processedMetrics['price'] || {}).sort();
    if (priceDates.length === 0) throw new Error('No price data available for timeframe.');

    const interpolatedMetrics = {};
    const metricsToInterpolate = new Set(metricsConfig.filter(m => m.is_plottable || ['ttmEps', 'rps', 'fcf'].includes(m.id)).map(m => m.id));
    
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
            return (num != null && den != null && den !== 0) ? { date, value: num / den } : { date, value: null };
        });
        interpolatedMetrics[mc.id] = ratioResult;
    });

    appendToPapertrail('Step 4: Preparing final data for charting...');
    globalProcessedMetrics = interpolatedMetrics;
    const { datasets, commonLabels } = prepareChartData(getSelectedMetricsForPlotting());

    return {
        datasets,
        commonLabels,
        chartTitle: `${ticker.toUpperCase()} Financial Analysis`,
        xAxisLabel: 'Date',
        yAxisLabels: { 'y-price': 'Price (USD)', 'y-ratio': 'Ratio / Value' }
    };
}


/**
 * Calculates Trailing Twelve Months (TTM) for a given quarterly or event-based dataset.
 * This is now simplified to sum the last 4 reported data points.
 * @param {Array<object>} data - An array of objects, e.g., [{date: 'YYYY-MM-DD', value: 123.45}].
 * @returns {Array<object>} A new array with TTM values.
 */
export function calculateTTM(data) {
    if (!data || data.length < 4) {
        return [];
    }

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
 * Interpolates financial data (like annual or quarterly) to a monthly frequency.
 * Uses forward-fill logic.
 * @param {Array<object>} sourceData - Data to interpolate, e.g., [{date: 'YYYY-MM-DD', value: 100}].
 * @param {string[]} targetDates - Array of monthly date strings (YYYY-MM-DD) to align to.
 * @returns {Array<object>} Interpolated data, e.g., [{date: 'YYYY-MM-DD', value: 100}].
 */
export function interpolateData(sourceData, targetDates) {
    if (!sourceData || !targetDates || sourceData.length === 0 || targetDates.length === 0) {
        return targetDates ? targetDates.map(date => ({ date, value: null })) : [];
    }

    const sortedSource = [...sourceData].sort((a, b) => new Date(a.date) - new Date(b.date));
    const interpolated = [];
    
    let sourceIndex = 0;
    let lastValue = null;

    for (const targetDate of targetDates) {
        // Find the most recent source data point that is on or before the target date.
        // The source data point must have a date less than or equal to the target date.
        while (sourceIndex < sortedSource.length && new Date(sortedSource[sourceIndex].date) <= new Date(targetDate)) {
            lastValue = sortedSource[sourceIndex].value;
            sourceIndex++;
        }
        interpolated.push({ date: targetDate, value: lastValue });
    }

    return interpolated;
}

/**
 * Gets the list of metric IDs that should be plotted based on UI controls.
 * @returns {string[]} An array of metric IDs.
 */
function getSelectedMetricsForPlotting() {
    const selected = [];
    if (togglePriceCheckbox.checked) {
        selected.push('price');
    }

    const selectedRadio = document.querySelector('input[name="ratioSelect"]:checked');
    if (selectedRadio) {
        const metricId = selectedRadio.value;
        const metric = metricsConfig.find(m => m.id === metricId || m.ui_radio_id === selectedRadio.id);
        if (metric) {
            selected.push(metric.id);
        } else {
            // Fallback for new metrics that might not have a direct ui_radio_id link yet
            switch (metricId) {
                case 'REVENUES': selected.push('revenues'); break;
                case 'NET_INCOME': selected.push('netIncome'); break;
                case 'EPS': selected.push('annualEPS'); break;
                case 'CAPEX': selected.push('capitalExpenditures'); break;
                case 'FCF': selected.push('fcf'); break;
                case 'SO': selected.push('commonSharesOutstanding'); break;
                case 'DIVIDENDS': selected.push('ttmDividends'); break;
                case 'PE': selected.push('peRatio'); break;
                case 'PS': selected.push('psRatio'); break;
            }
        }
    }

    return selected;
}

/**
 * Prepares chart datasets from the global processed data based on UI selections.
 * @param {string[]} selectedMetrics - Array of metric IDs to plot.
 * @returns {{datasets: object[], commonLabels: string[]}>}
 */
function prepareChartData(selectedMetrics) {
    if (!globalProcessedMetrics) return { datasets: [], commonLabels: [] };

    appendToPapertrail(`Preparing chart for: ${selectedMetrics.join(', ')}`);
    const datasetsForChart = [];
    // Price is still an object, so this is our source of truth for labels
    const commonLabels = Object.keys(globalProcessedMetrics['price'] || {}).sort();

    for (const metricId of selectedMetrics) {
        const metricConfig = metricsConfig.find(m => m.id === metricId);
        const data = globalProcessedMetrics[metricId];
        if (!metricConfig || !data) {
            appendToPapertrail(`Warning: No data for ${metricId}. Skipping.`);
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
        appendToPapertrail(`Prepared dataset for ${metricConfig.label}.`);
    }
    return { datasets: datasetsForChart, commonLabels };
}

/**
 * Creates or updates the Chart.js chart.
 * @param {object} chartData - Data from fetchAndProcessFinancialData or prepareChartData.
 */
function createOrUpdateChart(chartData) {
    const { datasets, commonLabels, chartTitle, xAxisLabel, yAxisLabels } = chartData;
    if (myChart) myChart.destroy();

    const yAxes = {};

    // Configure Price (Left) Axis
    if (datasets.some(d => d.yAxisID === 'y-price')) {
        yAxes['y-price'] = { 
            type: 'linear', 
            position: 'left', 
            title: { display: true, text: yAxisLabels['y-price'] }, 
            grid: { drawOnChartArea: true },
            ticks: {
                callback: function(value) {
                    if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
                    if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
                    return value.toLocaleString();
                }
            }
        };
    }

    // Configure Ratio/Value (Right) Axis
    if (datasets.some(d => d.yAxisID === 'y-ratio')) {
        const selectedRadio = document.querySelector('input[name="ratioSelect"]:checked');
        let yRatioTitle = yAxisLabels['y-ratio']; // Default title
        if (selectedRadio) {
            const metric = metricsConfig.find(m => m.ui_radio_id === selectedRadio.id);
            if (metric) yRatioTitle = metric.label;
        }

        yAxes['y-ratio'] = { 
            type: 'linear', 
            position: 'right', 
            title: { display: true, text: yRatioTitle }, 
            grid: { drawOnChartArea: false },
            ticks: {
                callback: function(value) {
                    if (!selectedRadio) return value.toFixed(2);
                    
                    const metric = metricsConfig.find(m => m.ui_radio_id === selectedRadio.id);
                    if (!metric) return value.toFixed(2);

                    switch (metric.id) {
                        case 'commonSharesOutstanding':
                            if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
                            if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
                            return value.toLocaleString();
                        case 'ttmDividends':
                            return `$${value.toFixed(2)}`;
                        case 'annualEPS':
                             return value.toFixed(2);
                        case 'revenues':
                        case 'netIncome':
                        case 'capitalExpenditures':
                        case 'fcf':
                            if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
                            if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
                            return value.toLocaleString();
                        default: // Ratios
                            return value.toFixed(2);
                    }
                }
            }
        };
    }

    myChart = new Chart(priceChartCanvas, {
        type: 'line',
        data: { labels: commonLabels, datasets: datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                title: { display: true, text: chartTitle, font: { size: 18 } },
                legend: { position: 'top' },
                tooltip: { 
                    mode: 'index', 
                    intersect: false,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) label += ': ';
                            let value = context.parsed.y;
                            if (value === null) return `${label}N/A`;
                            
                            switch (context.dataset.label) {
                                case 'Shares Outstanding':
                                    if (Math.abs(value) >= 1e9) return `${label}${(value / 1e9).toFixed(2)}B`;
                                    if (Math.abs(value) >= 1e6) return `${label}${(value / 1e6).toFixed(2)}M`;
                                    return `${label}${value.toLocaleString()}`;
                                case 'TTM Dividends':
                                    return `${label}$${value.toFixed(4)}`; // More precision for dividends in tooltip
                                case 'PE Ratio':
                                case 'PS Ratio':
                                    return `${label}${value.toFixed(2)}`;
                                case 'Adjusted Close Price':
                                    return `${label}$${value.toFixed(2)}`;
                                case 'EPS (Annual)':
                                    return `${label}${value.toFixed(2)}`;
                                case 'Revenues':
                                case 'Net Income':
                                case 'Capital Expenditures':
                                case 'Free Cash Flow':
                                    if (Math.abs(value) >= 1e9) return `${label}${(value / 1e9).toFixed(2)}B`;
                                    if (Math.abs(value) >= 1e6) return `${label}${(value / 1e6).toFixed(2)}M`;
                                    return `${label}${value.toLocaleString()}`;
                                default:
                                    return `${label}${value.toLocaleString()}`;
                            }
                        }
                    }
                }
            },
            scales: { x: { title: { display: true, text: xAxisLabel } }, ...yAxes },
            interaction: { mode: 'index', intersect: false },
            elements: { point: { radius: 2, hoverRadius: 5 } }
        }
    });
    appendToPapertrail('Chart created or updated successfully.');
}

// Main function to orchestrate fetching and plotting
async function plotData() {
    clearPapertrail();
    showLoadingSpinner();
    displayMessage('Fetching and processing data... Please wait.', 'info');

    const ticker = tickerInput.value.trim().toUpperCase();
    const alphaVantageApiKey = alphaVantageApiKeyInput.value.trim();
    
    // Convert slider position to "years ago"
    const startYearAgo = 20 - parseInt(leftSlider.value);
    const endYearAgo = 20 - parseInt(rightSlider.value);

    if (!ticker || !alphaVantageApiKey) {
        displayMessage('Ticker and Alpha Vantage API Key are required.', 'error');
        hideLoadingSpinner();
        return;
    }

    try {
        const chartData = await fetchAndProcessFinancialData(ticker, alphaVantageApiKey, startYearAgo, endYearAgo);
        if (chartData) {
            createOrUpdateChart(chartData);
            lastFetchedChartData = chartData; // Cache the successful chart data
            displayMessage('Chart updated successfully.', 'success');
        }
    } catch (error) {
        console.error("An error occurred during plotting:", error);
        displayMessage(`An error occurred: ${error.message}`, 'error');
        appendToPapertrail(`Fatal error during plotData: ${error.stack}`);
    } finally {
        hideLoadingSpinner();
    }
}

// Function to replot based on UI changes without re-fetching
function replotFromCache() {
    if (lastFetchedChartData) {
        const { datasets, commonLabels } = prepareChartData(getSelectedMetricsForPlotting());
        createOrUpdateChart({ ...lastFetchedChartData, datasets, commonLabels });
        appendToPapertrail('Re-plotted metrics from cached data.');
    }
}

// Event Listeners
if (typeof window !== 'undefined') {
    window.addEventListener('DOMContentLoaded', () => {
        initializeAlphaVantageDataKnowledgeBase();
        fetchButton.addEventListener('click', plotData);

        // Add listeners to UI controls to replot from cache
        togglePriceCheckbox.addEventListener('change', replotFromCache);
        ratioSelectRadios.forEach(radio => {
            radio.addEventListener('change', replotFromCache);
        });

        // We don't need a listener for timeframeSelect to replot from cache,
        // as changing the timeframe requires a new data fetch.

        // Add event listeners to slider controls
        function updateSliderAppearance() {
            const min = parseInt(leftSlider.min);
            const max = parseInt(leftSlider.max);
            let leftValue = parseInt(leftSlider.value);
            let rightValue = parseInt(rightSlider.value);

            // Ensure left slider doesn't cross the right one
            if (leftValue > rightValue) {
                [leftValue, rightValue] = [rightValue, leftValue];
                leftSlider.value = leftValue;
                rightSlider.value = rightValue;
            }
            
            const leftPercent = ((leftValue - min) / (max - min)) * 100;
            const rightPercent = ((rightValue - min) / (max - min)) * 100;

            sliderTrack.style.background = `linear-gradient(to right, #e2e8f0 ${leftPercent}%, #3b82f6 ${leftPercent}%, #3b82f6 ${rightPercent}%, #e2e8f0 ${rightPercent}%)`;
            
            const currentYear = new Date().getFullYear();
            // Convert slider position to year
            const startYear = currentYear - (20 - leftValue);
            const endYear = currentYear - (20 - rightValue);

            yearRangeLabel.textContent = `Start: ${startYear} | End: ${endYear}`;
        }

        leftSlider.addEventListener('input', updateSliderAppearance);
        rightSlider.addEventListener('input', updateSliderAppearance);

        // Initial call to set slider appearance
        document.addEventListener('DOMContentLoaded', updateSliderAppearance);
    });
} 