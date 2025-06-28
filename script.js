import { processFinancialData, getNestedValue, calculateTTM, interpolateData, findValidDate, roundDateToEndOfMonth, calculateDerivedMetric } from './processUtils.js';
import { prepareChartData } from './chartUtils.js';
import { fetchFinancialData, addToCache, getFromCache } from './fetchUtils.js';

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
 * @property {boolean} fx_adjust - Whether this metric should be FX adjusted.
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
        isTimeSeries: true, // Explicitly set to true
        fx_adjust: false // Price is always in USD
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
        type: 'raw_fundamental',
        source_function: 'BALANCE_SHEET',
        source_path: ['annualReports', 'commonStockSharesOutstanding'],
        date_keys: 'fiscalDateEnding',
        color: 'rgb(0, 123, 255)',
        axis: 'y-ratio',
        ui_radio_id: 'selectSharesOutstanding',
        is_plottable: true,
        isTimeSeries: false,
        fx_adjust: false // Shares should not be FX adjusted
    },
    {
        id: 'dividendPayout',
        label: 'Dividend Payout',
        type: 'raw_fundamental',
        source_function: 'CASH_FLOW',
        source_path: ['annualReports', 'dividendPayout'],
        date_keys: 'fiscalDateEnding',
        is_plottable: false,
        isTimeSeries: false
    },
    {
        id: 'ttmDividends',
        label: 'TTM Dividends',
        type: 'derived_custom',
        calculation_formula: 'dividendPayout / commonSharesOutstanding',
        color: 'rgb(255, 159, 64)',
        axis: 'y-ratio',
        ui_radio_id: 'selectDividends',
        is_plottable: true
    },
    {
        id: 'dividendYieldTTM',
        label: 'Dividend Yield (TTM)',
        type: 'derived_ratio',
        calculation_formula: 'ttmDividends / price',
        color: 'rgb(40, 167, 69)',
        axis: 'y-ratio',
        ui_radio_id: 'selectDividendYield',
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
        id: 'pFcfRatio',
        label: 'P/FCF Ratio',
        type: 'derived_ratio',
        calculation_formula: 'price / fcfPerShare',
        color: 'rgb(111, 66, 193)',
        axis: 'y-ratio',
        ui_radio_id: 'selectPFCFRatio',
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
    },
    {
        id: 'fcfPerShare',
        label: 'FCF Per Share',
        type: 'derived_custom',
        calculation_formula: 'fcf / commonSharesOutstanding',
        is_plottable: false
    }
];


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
    if (typeof papertrailLog === 'undefined' || !papertrailLog || typeof document === 'undefined') {
        // In test or non-browser environment, do nothing (or optionally: console.log(msg));
        return;
    }
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
                case 'PFCF': selected.push('pFcfRatio'); break;
                case 'DIVYIELD': selected.push('dividendYieldTTM'); break;
            }
        }
    }

    return selected;
}

/**
 * Creates or updates the Chart.js chart.
 * @param {object} chartData - Data from fetchAndProcessFinancialData or prepareChartData.
 */
function createOrUpdateChart(chartData) {
    // Provide defaults for chartData fields if missing
    const {
        datasets = [],
        commonLabels = [],
        chartTitle = 'Financial Analysis',
        xAxisLabel = 'Date',
        yAxisLabels = { 'y-price': 'Price (USD)', 'y-ratio': 'Ratio / Value' }
    } = chartData || {};
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
                        case 'dividendYieldTTM':
                            return `${(value * 100).toFixed(2)}%`;
                        case 'revenues':
                        case 'netIncome':
                        case 'capitalExpenditures':
                        case 'fcf':
                            if (Math.abs(value) >= 1e9) return `${(value / 1e9).toFixed(1)}B`;
                            if (Math.abs(value) >= 1e6) return `${(value / 1e6).toFixed(1)}M`;
                            return value.toLocaleString();
                        case 'PE Ratio':
                        case 'PS Ratio':
                            return value.toFixed(2);
                        case 'P/FCF Ratio':
                            return value.toFixed(2);
                        case 'Dividend Yield (TTM)':
                            return `${(value * 100).toFixed(2)}%`;
                        case 'Adjusted Close Price':
                            return `${value.toFixed(2)}`;
                        default:
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
                            let originalLabel = context.dataset.label || '';
                            let value = context.parsed.y;
                            
                            const yAxisID = context.dataset.yAxisID;
                            let displayLabel = originalLabel;
                            if (yAxisID === 'y-price') {
                                displayLabel += ' (left)';
                            } else if (yAxisID === 'y-ratio') {
                                displayLabel += ' (right)';
                            }

                            if (value === null) return `${displayLabel}: N/A`;
                            
                            // Use originalLabel for the switch, and displayLabel for the output
                            switch (originalLabel) {
                                case 'Shares Outstanding':
                                    if (Math.abs(value) >= 1e9) return `${displayLabel}: ${(value / 1e9).toFixed(2)}B`;
                                    if (Math.abs(value) >= 1e6) return `${displayLabel}: ${(value / 1e6).toFixed(2)}M`;
                                    return `${displayLabel}: ${value.toLocaleString()}`;
                                case 'TTM Dividends':
                                    return `${displayLabel}: $${value.toFixed(4)}`; // More precision for dividends in tooltip
                                case 'PE Ratio':
                                case 'PS Ratio':
                                    return `${displayLabel}: ${value.toFixed(2)}`;
                                case 'P/FCF Ratio':
                                    return `${displayLabel}: ${value.toFixed(2)}`;
                                case 'Dividend Yield (TTM)':
                                    return `${displayLabel}: ${(value * 100).toFixed(2)}%`;
                                case 'Adjusted Close Price':
                                    return `${displayLabel}: $${value.toFixed(2)}`;
                                case 'EPS (Annual)':
                                    return `${displayLabel}: ${value.toFixed(2)}`;
                                case 'Revenues':
                                case 'Net Income':
                                case 'Capital Expenditures':
                                case 'Free Cash Flow':
                                    if (Math.abs(value) >= 1e9) return `${displayLabel}: ${(value / 1e9).toFixed(2)}B`;
                                    if (Math.abs(value) >= 1e6) return `${displayLabel}: ${(value / 1e6).toFixed(2)}M`;
                                    return `${displayLabel}: ${value.toLocaleString()}`;
                                default:
                                    return `${displayLabel}: ${value.toLocaleString()}`;
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
        const now = new Date();
        const startDate = new Date(new Date().setFullYear(now.getFullYear() - startYearAgo));
        const endDate = new Date(new Date().setFullYear(now.getFullYear() - endYearAgo));
        const { rawData, fxRateUsed } = await fetchFinancialData(ticker, alphaVantageApiKey, startDate, endDate, metricsConfig);
        const processedMetrics = processFinancialData(rawData, fxRateUsed, startDate, endDate, metricsConfig);
        const chartData = prepareChartData(processedMetrics, getSelectedMetricsForPlotting(), metricsConfig);
        if (chartData) {
            createOrUpdateChart(chartData);
            lastFetchedChartData = { ...chartData, processedMetrics }; // Cache both chart data and processed metrics
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
        // Use cached processedMetrics if available, otherwise fallback to empty object
        const processedMetrics = lastFetchedChartData.processedMetrics || {};
        const selectedMetrics = getSelectedMetricsForPlotting() || [];
        const { datasets, commonLabels } = prepareChartData(processedMetrics, selectedMetrics, metricsConfig);
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