// DOM Elements
const tickerInput = document.getElementById('tickerInput');
const alphaVantageApiKeyInput = document.getElementById('alphaVantageApiKey');
const timeframeSelect = document.getElementById('timeframeSelect');
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
 * @param {string} selectedTimeframe '1', '5', '10', '20', or 'all' for years.
 * @returns {Promise<{datasets: Object, commonLabels: string[], chartTitle: string, xAxisLabel: string, yAxisLabels: string[]}>}
 */
async function fetchAndProcessFinancialData(ticker, alphaVantageApiKey, selectedTimeframe) {
    globalProcessedMetrics = {}; // Reset on each run
    appendToPapertrail('Step 1: Fetching all required Alpha Vantage data based on metrics configuration...');
    const fetchedRawData = {}; // Stores raw API responses keyed by function name
    const alphaVantageCalls = [];

    // Determine unique functions to fetch based on metricsConfig
    const functionsToFetch = new Set(metricsConfig.map(m => m.source_function).filter(Boolean));

    for (const func of Array.from(functionsToFetch)) {
        let url = `https://www.alphavantage.co/query?function=${func}&symbol=${ticker}&apikey=${alphaVantageApiKey}`;
        if (func === 'TIME_SERIES_MONTHLY_ADJUSTED') {
            url += `&outputsize=full`; // Ensure full data for time series
        }

        const cachedData = getFromCache(url);
        if (cachedData) {
            fetchedRawData[func] = cachedData;
            appendToPapertrail(`Cache hit for ${func} (URL: ${url}).`);
        } else {
            appendToPapertrail(`Cache miss for ${func}. Fetching from Alpha Vantage (URL: ${url}).`);
            alphaVantageCalls.push(
                fetch(url)
                    .then(response => {
                        if (!response.ok) {
                            throw new Error(`HTTP error! status: ${response.status} for ${func}`);
                        }
                        return response.json();
                    })
                    .then(data => {
                        if (data["Error Message"] || data["Note"]) {
                            throw new Error(data["Error Message"] || data["Note"] || `Alpha Vantage API returned an error for ${func}.`);
                        }
                        fetchedRawData[func] = data;
                        addToCache(url, data);
                        appendToPapertrail(`Successfully fetched and cached raw data for ${func}.`);
                    })
                    .catch(error => {
                        console.error(`Error fetching raw ${func} data from Alpha Vantage:`, error);
                        appendToPapertrail(`Error fetching raw data for ${func}: ${error.message}`);
                        fetchedRawData[func] = { error: `Failed to fetch data for ${func}: ${error.message}` };
                    })
            );
        }
    }
    await Promise.all(alphaVantageCalls);
    appendToPapertrail('Finished fetching all raw data from Alpha Vantage.');


    // --- Extract Raw Metrics (without timeframe filtering yet) ---
    appendToPapertrail('Step 2.1: Extracting raw metrics from fetched data (before timeframe filtering)...');
    const extractedRawMetrics = {}; // Stores raw values for each metric ID, e.g., { 'price': { '2023-01-31': 150, ... } }

    for (const metricConfig of metricsConfig.filter(m => m.type.startsWith('raw_'))) {
        const rawDataForFunction = fetchedRawData[metricConfig.source_function];

        // appendToPapertrail(`Debug: Raw data for function ${metricConfig.source_function} (ID: ${metricConfig.id}): ${JSON.stringify(rawDataForFunction).substring(0, 200)}...`);

        if (!rawDataForFunction || rawDataForFunction.error) {
            appendToPapertrail(`Warning: Skipping extraction for ${metricConfig.label} due to missing or errored raw data from ${metricConfig.source_function}.`);
            extractedRawMetrics[metricConfig.id] = {}; // Ensure empty object if data is missing
            continue;
        }

        let dataContainer = getNestedValue(rawDataForFunction, [metricConfig.source_path[0]]);

        // appendToPapertrail(`Debug: Data container for ${metricConfig.label} (path: ${metricConfig.source_path[0]}): ${JSON.stringify(dataContainer).substring(0, 200)}...`);

        if (!dataContainer) {
            appendToPapertrail(`Warning: Data container not found for ${metricConfig.label} (Path: ${metricConfig.source_path[0]}). Raw data: ${JSON.stringify(rawDataForFunction).substring(0, 100)}...`);
            extractedRawMetrics[metricConfig.id] = {};
            continue;
        }

        const tempExtracted = {};
        if (metricConfig.isTimeSeries) {
            const containerKeys = Object.keys(dataContainer).sort((a, b) => new Date(a) - new Date(b));
            for (const dateStr of containerKeys) {
                const value = parseFloat(getNestedValue(dataContainer[dateStr], metricConfig.source_path.slice(1)));
                if (!isNaN(value)) tempExtracted[dateStr] = value;
            }
        } else {
            const entries = Array.isArray(dataContainer) ? dataContainer : [];
            entries.forEach(item => {
                const dateStr = findValidDate(item, metricConfig.date_keys);
                if (dateStr) {
                    const value = parseFloat(getNestedValue(item, metricConfig.source_path.slice(1)));
                    if (!isNaN(value)) {
                        tempExtracted[dateStr] = value;
                    } else {
                        appendToPapertrail(`Skipping invalid value for ${metricConfig.label} on date ${dateStr}. Raw value: ${getNestedValue(item, metricConfig.source_path.slice(1))}`);
                    }
                }
            });
        }
        extractedRawMetrics[metricConfig.id] = tempExtracted;
        appendToPapertrail(`Extracted raw ${metricConfig.label} data: ${Object.keys(tempExtracted).length} points.`);
    }

    // --- Apply Timeframe Filtering to ALL extracted raw data ---
    appendToPapertrail(`Step 2.2: Applying timeframe filter for the last ${selectedTimeframe} year(s) to all extracted raw metrics...`);
    const filteredRawMetrics = {};
    let filterDate = new Date(0); // This is the start of the timeframe filter

    if (selectedTimeframe !== 'all') {
        const yearsAgo = parseInt(selectedTimeframe);
        filterDate = new Date();
        filterDate.setFullYear(filterDate.getFullYear() - yearsAgo);
    }

    for (const metricId in extractedRawMetrics) {
        const data = extractedRawMetrics[metricId];
        const filteredData = {};
        for (const dateStr in data) {
            if (new Date(dateStr) >= filterDate) {
                filteredData[dateStr] = data[dateStr];
            }
        }
        filteredRawMetrics[metricId] = filteredData;
        appendToPapertrail(`Filtered ${metricId}: ${Object.keys(data).length} -> ${Object.keys(filteredData).length} points.`);
    }


    // --- Process Derived Metrics ---
    appendToPapertrail('Step 3: Processing derived metrics (TTM, ratios, etc.)...');
    const processedMetrics = { ...filteredRawMetrics }; // Start with filtered raw metrics

    // Calculate all TTM metrics first
    for (const metricConfig of metricsConfig.filter(m => m.type === 'derived_ttm')) {
        const basisMetricId = metricConfig.calculation_basis;
        const sourceData = processedMetrics[basisMetricId]; // Use already filtered data
        if (!sourceData) {
            appendToPapertrail(`Warning: Cannot calculate TTM for ${metricConfig.label}; source data '${basisMetricId}' not found.`);
            continue;
        }

        const ttmResult = calculateTTM(sourceData, metricConfig.id === 'ttmDividends');
        processedMetrics[metricConfig.id] = ttmResult;
        appendToPapertrail(`Calculated TTM for ${metricConfig.label}: ${Object.keys(ttmResult).length} points.`);
    }
    
    // Calculate custom derived metrics (like 'rps') before they are needed by ratios
    for (const metricConfig of metricsConfig.filter(m => m.type === 'derived_custom')) {
        const formula = metricConfig.calculation_formula;
        // For custom derivations, we need to find a way to align dates.
        // Let's assume for rps, we align annual revenue with annual shares outstanding.
        // This part can get complex. A simple approach: align by year.
        const [numeratorId, denominatorId] = formula.split(' / ');
        const numeratorData = processedMetrics[numeratorId];
        const denominatorData = processedMetrics[denominatorId];

        if (!numeratorData || !denominatorData) {
            appendToPapertrail(`Warning: Missing data for custom derived metric ${metricConfig.label}. Numerator: ${numeratorId}, Denominator: ${denominatorId}`);
            continue;
        }

        const result = {};
        const numeratorDates = Object.keys(numeratorData).sort();
        const denominatorDates = Object.keys(denominatorData).sort();

        // This is a simplified alignment logic. It may need to be more robust.
        // It aligns based on matching years, taking the latest data for each year if multiple exist.
        const denominatorMap = denominatorDates.reduce((acc, date) => {
            const year = new Date(date).getFullYear();
            acc[year] = denominatorData[date];
            return acc;
        }, {});

        for(const date of numeratorDates) {
            const year = new Date(date).getFullYear();
            if (denominatorMap[year] && denominatorMap[year] !== 0) {
                result[date] = numeratorData[date] / denominatorMap[year];
            }
        }

        processedMetrics[metricConfig.id] = result;
        appendToPapertrail(`Calculated custom derived metric ${metricConfig.label}: ${Object.keys(result).length} points.`);
    }

    // Now calculate all ratio metrics
    // We need a common set of dates to perform ratio calculations.
    // Price data is monthly, so other data should be aligned to it.
    const priceDates = Object.keys(processedMetrics['price'] || {}).sort();
    if (priceDates.length === 0) {
        appendToPapertrail('Error: No price data available. Cannot calculate ratios.');
        displayMessage('No price data available for the selected timeframe. Ratios cannot be calculated.', 'error');
    }

    // Interpolate all necessary metric data to align with price dates
    const interpolatedMetrics = {};
    for (const metricId in processedMetrics) {
        // We only need to interpolate data that will be used in ratios or plotted directly.
        // Let's interpolate everything except price itself for simplicity here.
        if (metricId !== 'price' && processedMetrics[metricId]) {
            interpolatedMetrics[metricId] = interpolateData(processedMetrics[metricId], priceDates);
        } else {
            interpolatedMetrics[metricId] = processedMetrics[metricId]; // Keep price data as is
        }
    }
    appendToPapertrail('Interpolated necessary metrics to align with monthly price dates.');


    // Recalculate ratios using the new interpolated data
    for (const metricConfig of metricsConfig.filter(m => m.type === 'derived_ratio')) {
        const [numeratorId, denominatorId] = metricConfig.calculation_formula.split(' / ').map(s => s.trim());
        const numeratorData = interpolatedMetrics[numeratorId], denominatorData = interpolatedMetrics[denominatorId];
        if (!numeratorData || !denominatorData) continue;
        const ratioResult = {};
        for (const date of priceDates) {
            const num = numeratorData[date], den = denominatorData[date];
            if (num !== undefined && den !== undefined && den !== 0 && isFinite(num) && isFinite(den)) {
                ratioResult[date] = num / den;
            }
        }
        interpolatedMetrics[metricConfig.id] = ratioResult; // FIX: store in interpolatedMetrics
        appendToPapertrail(`Calculated ratio ${metricConfig.label}: ${Object.keys(ratioResult).length} points.`);
    }


    // --- Final Data Preparation for Charting ---
    appendToPapertrail('Step 4: Preparing final data for charting...');
    globalProcessedMetrics = interpolatedMetrics; // FIX: Store fully interpolated data
    const { datasets, commonLabels } = prepareChartData(getSelectedMetricsForPlotting());

    const chartTitle = `${ticker.toUpperCase()} Financial Analysis`;
    const xAxisLabel = 'Date';
    const yAxisLabels = { 'y-price': 'Price (USD)', 'y-ratio': 'Ratio / Value' };


    return {
        datasets,
        commonLabels,
        chartTitle: chartTitle,
        xAxisLabel: xAxisLabel,
        yAxisLabels: yAxisLabels
    };
}


/**
 * Calculates Trailing Twelve Months (TTM) for a given quarterly or event-based dataset.
 * @param {object} data - An object where keys are date strings (YYYY-MM-DD) and values are numbers.
 * @param {boolean} isDividend - True if calculating TTM for dividends (sum of last 4 quarters).
 * @returns {object} A new object with TTM values, keyed by date.
 */
export function calculateTTM(data, isDividend = false) {
    const sortedDates = Object.keys(data).sort((a, b) => new Date(a) - new Date(b));
    const ttmData = {};

    if (sortedDates.length < 1) {
        return ttmData;
    }
    
    if (isDividend) {
        // For dividends, we sum up amounts over the last 12 months for each date point.
        // This requires aligning with a monthly series later, so we will do a simple TTM calc here.
        const monthlySums = {}; // Aggregate dividends by month
        for (const dateStr of sortedDates) {
            const date = new Date(dateStr);
            const year = date.getFullYear();
            const month = date.getMonth();
            const monthKey = `${year}-${String(month + 1).padStart(2, '0')}`;
            monthlySums[monthKey] = (monthlySums[monthKey] || 0) + data[dateStr];
        }

        const sortedMonths = Object.keys(monthlySums).sort();
        for (let i = 0; i < sortedMonths.length; i++) {
            let ttmSum = 0;
            const currentMonthDate = new Date(sortedMonths[i] + '-01');
            const twelveMonthsAgo = new Date(currentMonthDate);
            twelveMonthsAgo.setMonth(twelveMonthsAgo.getMonth() - 11);

            // Sum up all months in the TTM window
            for (let j = 0; j <= i; j++) {
                 const monthToConsider = new Date(sortedMonths[j] + '-01');
                 if (monthToConsider >= twelveMonthsAgo && monthToConsider <= currentMonthDate) {
                     ttmSum += monthlySums[sortedMonths[j]];
                 }
            }
            // Use the end of the month for the date key
            const lastDayOfMonth = new Date(currentMonthDate.getFullYear(), currentMonthDate.getMonth() + 1, 0);
            ttmData[lastDayOfMonth.toISOString().slice(0, 10)] = ttmSum;
        }

    } else { // For quarterly data like EPS
        if (sortedDates.length < 4) {
            // Not enough data for a full TTM calculation
            return ttmData;
        }
        for (let i = 3; i < sortedDates.length; i++) {
            const currentQuarterDate = sortedDates[i];
            const q1 = data[sortedDates[i]];
            const q2 = data[sortedDates[i - 1]];
            const q3 = data[sortedDates[i - 2]];
            const q4 = data[sortedDates[i - 3]];
            const ttmSum = q1 + q2 + q3 + q4;
            ttmData[currentQuarterDate] = ttmSum;
        }
    }
    return ttmData;
}


/**
 * Interpolates financial data (like annual or quarterly) to a monthly frequency.
 * Uses forward-fill logic.
 * @param {object} sourceData - Data to interpolate, keyed by date.
 * @param {string[]} targetDates - Array of monthly date strings (YYYY-MM-DD) to align to.
 * @returns {object} Interpolated data keyed by the target dates.
 */
export function interpolateData(sourceData, targetDates) {
    const interpolated = {};
    const sourceDates = Object.keys(sourceData).sort();

    if (sourceDates.length === 0) {
        return interpolated;
    }

    let lastValue = null;
    let sourceIndex = 0;

    for (const targetDate of targetDates) {
        // Find the most recent source data point that is on or before the target date
        while (sourceIndex < sourceDates.length && new Date(sourceDates[sourceIndex]) <= new Date(targetDate)) {
            lastValue = sourceData[sourceDates[sourceIndex]];
            sourceIndex++;
        }
        
        if (lastValue !== null) {
            interpolated[targetDate] = lastValue;
        }
    }
    
    // After finding the first value, the loop continues from where it left off.
    // To ensure the first few months get a value if the first data point is later,
    // we do a backward pass. This is a bit of a simplification.
    // A better approach is to ensure the first `lastValue` is found correctly.
    if (Object.keys(interpolated).length > 0) {
        let firstAvailableValue = null;
        for (const date of targetDates) {
            if (interpolated[date] !== undefined) {
                firstAvailableValue = interpolated[date];
                break;
            }
        }
        if (firstAvailableValue !== null) {
            for (const date of targetDates) {
                if (interpolated[date] === undefined) {
                    interpolated[date] = firstAvailableValue;
                } else {
                    break; // Stop once we hit the already filled values
                }
            }
        }
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
        // Find the metric in metricsConfig that corresponds to this radio button
        const metric = metricsConfig.find(m => m.ui_radio_id === selectedRadio.id);
        if (metric) {
            selected.push(metric.id);
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
    const commonLabels = Object.keys(globalProcessedMetrics['price'] || {}).sort();

    for (const metricId of selectedMetrics) {
        const metricConfig = metricsConfig.find(m => m.id === metricId);
        const data = globalProcessedMetrics[metricId];
        if (!metricConfig || !data) {
            appendToPapertrail(`Warning: No data for ${metricId}. Skipping.`);
            continue;
        }
        const alignedData = commonLabels.map(label => data[label] !== undefined ? data[label] : null);
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
    const timeframe = timeframeSelect.value;

    if (!ticker || !alphaVantageApiKey) {
        displayMessage('Ticker and Alpha Vantage API Key are required.', 'error');
        hideLoadingSpinner();
        return;
    }

    try {
        const chartData = await fetchAndProcessFinancialData(ticker, alphaVantageApiKey, timeframe);
        lastFetchedChartData = chartData; // Cache the processed data

        if (chartData.datasets.length === 0) {
            displayMessage('No data available to plot for the selected metrics and timeframe. Check papertrail for details.', 'error');
            // Destroy any old chart if no data is available now
            if (myChart) {
                myChart.destroy();
            }
        } else {
            createOrUpdateChart(chartData);
            displayMessage('Data plotted successfully.', 'success');
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
    if (!lastFetchedChartData) {
        appendToPapertrail("No cached data to replot. Please fetch data first.");
        return;
    }
    
    appendToPapertrail("Re-plotting from cached data based on new UI selections...");

    // Get the newly selected metrics
    const selectedMetrics = getSelectedMetricsForPlotting();
    const originalDatasets = lastFetchedChartData.datasets;
    
    // We need to re-create the datasets from the original `processedMetrics` data
    // because `lastFetchedChartData.datasets` only contains the previously selected datasets.
    // This is a bug in the original design. For now, we will work with what we have,
    // which means we can only show/hide what was originally fetched and processed.
    // A better implementation would be to store `processedMetrics` globally.

    // Let's filter the originally prepared datasets based on the new selection.
    // This requires us to know which dataset corresponds to which metric ID.
    // We can add the ID to the dataset object when creating it.
    
    // --- Let's correct this by re-creating the datasets from scratch if we have the full processed data ---
    // The current `lastFetchedChartData` only has the *final* datasets, not the full pool of processed data.
    // This is a key bug. Let's assume for now we just trigger a full re-fetch and process.
    // This is inefficient but will work until we refactor the data flow.
    appendToPapertrail("Limitation: Re-plotting from cache is not fully implemented. Triggering a new plot...");
    plotData();


    // The code below would be the ideal implementation if `processedMetrics` were stored.
    /*
    const datasetsForChart = [];
    const allProcessedData = lastFetchedChartData.allProcessedData; // Assuming we store this

    for (const metricId of selectedMetrics) {
        const metricConfig = metricsConfig.find(m => m.id === metricId);
        const data = allProcessedData[metricId];
        // ... build dataset as in fetchAndProcessFinancialData ...
    }

    const newChartData = { ...lastFetchedChartData, datasets: datasetsForChart };
    createOrUpdateChart(newChartData);
    displayMessage('Chart updated from cache.', 'success');
    */
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
    });
} 