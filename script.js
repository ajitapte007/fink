import { processFinancialData, getNestedValue, calculateTTM, interpolateData, findValidDate, roundDateToEndOfMonth, calculateDerivedMetric, formatLargeNumber } from './processUtils.js';
import { prepareChartData } from './chartUtils.js';
import { fetchFinancialData, addToCache, getFromCache } from './fetchUtils.js';
import { getCashflowSankeyChartUrl, renderQuickChartImage, renderPlotlySankeyChart, renderPlotlySankeyChartMultiLevel } from './chartUtils.js';

// DOM Elements for new UI
const tickerInputTop = document.getElementById('tickerInputTop');
const alphaVantageApiKeyTop = document.getElementById('alphaVantageApiKeyTop');
const loadBtn = document.getElementById('loadBtn');
const tabButtons = document.querySelectorAll('.tab');
const tabContents = document.querySelectorAll('.tab-content');
// Add these for slider and label
const leftSlider = document.getElementById('leftSlider');
const rightSlider = document.getElementById('rightSlider');
const sliderTrack = document.querySelector('.slider-track');
const yearRangeLabel = document.getElementById('year-range-label');
const messageDisplay = document.getElementById('message');
const togglePriceCheckbox = document.getElementById('togglePrice');
const ratioSelectRadios = document.querySelectorAll('input[name="ratioSelect"]');
const priceChartCanvas = document.getElementById('priceChart');

// Remove/ignore old left panel ticker/api key logic
// const tickerInput = document.getElementById('tickerInput');
// const alphaVantageApiKeyInput = document.getElementById('alphaVantageApiKey');

// Track which tabs have loaded data for the current ticker/key
let loadedTabs = { raw: false, recipes: false };
let lastTicker = '';
let lastApiKey = '';

function resetLoadedTabs() {
    loadedTabs = { raw: false, recipes: false };
}

function getCurrentTicker() {
    return tickerInputTop.value.trim().toUpperCase();
}
function getCurrentApiKey() {
    return alphaVantageApiKeyTop.value.trim();
}

function showTab(tab) {
    tabButtons.forEach(btn => btn.classList.remove('active'));
    tabContents.forEach(content => content.style.display = 'none');
    document.querySelector('.tab[data-tab="' + tab + '"]').classList.add('active');
    document.getElementById('tab-' + tab).style.display = 'block';
}

// Debug panel utility
export function debugLog(msg) {
    const debugPanel = document.getElementById('debugPanel');
    if (!debugPanel) return;
    debugPanel.style.display = 'block';
    const p = document.createElement('div');
    p.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    debugPanel.appendChild(p);
    debugPanel.scrollTop = debugPanel.scrollHeight;
}
window.debugLog = debugLog;

// Debug panel utility for Recipes tab
function debugLogRecipes(msg) {
    const debugPanel = document.getElementById('recipesDebugPanel');
    if (!debugPanel) return;
    debugPanel.style.display = 'block';
    const p = document.createElement('div');
    p.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
    debugPanel.appendChild(p);
    debugPanel.scrollTop = debugPanel.scrollHeight;
}

function fetchTabData(tab) {
    debugLog(`fetchTabData called for tab: ${tab}`);
    const ticker = getCurrentTicker();
    const apiKey = getCurrentApiKey();
    debugLog(`Ticker: ${ticker}, API Key: ${apiKey ? '[provided]' : '[missing]'}`);
    if (!ticker || !apiKey) return;
    if (tab === 'raw' && !loadedTabs.raw) {
        debugLog('Calling plotData for raw tab...');
        plotData(ticker, apiKey);
        loadedTabs.raw = true;
    } else if (tab === 'recipes' && !loadedTabs.recipes) {
        debugLog('Recipes tab selected (no-op for now).');
        loadedTabs.recipes = true;
    }
}

// Ensure tab click logic works after DOM is loaded
window.addEventListener('DOMContentLoaded', () => {
    const tabButtons = document.querySelectorAll('.tab');
    const tabContents = document.querySelectorAll('.tab-content');
    function showTab(tab) {
        tabButtons.forEach(btn => btn.classList.remove('active'));
        tabContents.forEach(content => content.style.display = 'none');
        document.querySelector('.tab[data-tab="' + tab + '"]').classList.add('active');
        document.getElementById('tab-' + tab).style.display = 'block';
    }
    for (const btn of tabButtons) {
        btn.addEventListener('click', function() {
            const tab = this.dataset.tab;
            showTab(tab);
            if (getCurrentTicker() && getCurrentApiKey()) {
                fetchTabData(tab);
                // If switching to recipes tab, rerun recipe logic
                if (tab === 'recipes') {
                    handleRecipeChange();
                }
            }
        });
    }
    // Open Tab 1 by default
    showTab('raw');

    // DOM element references
    const leftSlider = document.getElementById('leftSlider');
    const rightSlider = document.getElementById('rightSlider');
    const sliderTrack = document.querySelector('.slider-track');
    const yearRangeLabel = document.getElementById('year-range-label');

    // Slider label update logic
    function updateSliderAppearance() {
        const min = parseInt(leftSlider.min);
        const max = parseInt(leftSlider.max);
        let leftValue = parseInt(leftSlider.value);
        let rightValue = parseInt(rightSlider.value);
        if (leftValue > rightValue) {
            [leftValue, rightValue] = [rightValue, leftValue];
            leftSlider.value = leftValue;
            rightSlider.value = rightValue;
        }
        const leftPercent = ((leftValue - min) / (max - min)) * 100;
        const rightPercent = ((rightValue - min) / (max - min)) * 100;
        sliderTrack.style.background = `linear-gradient(to right, #e2e8f0 ${leftPercent}%, #3b82f6 ${leftPercent}%, #3b82f6 ${rightPercent}%, #e2e8f0 ${rightPercent}%)`;
        const currentYear = new Date().getFullYear();
        const startYear = currentYear - (20 - leftValue);
        const endYear = currentYear - (20 - rightValue);
        yearRangeLabel.textContent = `Start: ${startYear} | End: ${endYear}`;
    }
    leftSlider.addEventListener('input', updateSliderAppearance);
    rightSlider.addEventListener('input', updateSliderAppearance);
    updateSliderAppearance();

    // Recipes tab logic
    const recipeRadios = document.querySelectorAll('input[name="recipeSelect"]');
    recipeRadios.forEach(radio => {
        radio.addEventListener('change', handleRecipeChange);
    });
    // Initial render
    handleRecipeChange();

    async function handleRecipeChange() {
        const selected = document.querySelector('input[name="recipeSelect"]:checked');
        debugLogRecipes(`Recipe selected: ${selected?.value}`);
        if (!selected) return;
        if (selected.value === 'cashflowOverview') {
            await renderCashflowOverviewRecipe();
        }
        // Future: handle other recipes
    }

    async function renderCashflowOverviewRecipe() {
        const ticker = getCurrentTicker();
        const apiKey = getCurrentApiKey();
        debugLogRecipes(`Ticker: ${ticker}, API Key: ${apiKey ? '[provided]' : '[missing]'}`);
        if (!ticker || !apiKey) {
            renderQuickChartImage('recipesSankeyChart', '');
            debugLogRecipes('Missing ticker or API key.');
            return;
        }
        // Fetch latest CASHFLOW and INCOME_STATEMENT data
        const metricsConfig = [
            { metric: 'totalRevenue', source_function: 'INCOME_STATEMENT' },
            { metric: 'costOfRevenue', source_function: 'INCOME_STATEMENT' },
            { metric: 'sellingGeneralAndAdministrative', source_function: 'INCOME_STATEMENT' },
            { metric: 'researchAndDevelopment', source_function: 'INCOME_STATEMENT' },
            { metric: 'operatingExpenses', source_function: 'INCOME_STATEMENT' },
            { metric: 'capitalExpenditures', source_function: 'CASH_FLOW' },
            { metric: 'dividendPayout', source_function: 'CASH_FLOW' }
        ];
        debugLogRecipes('Fetching financial data...');
        try {
            const { rawData, fxRateUsed } = await fetchFinancialData(
                ticker,
                apiKey,
                0, // startYearAgo (latest)
                0, // endYearAgo (latest)
                metricsConfig
            );
            debugLogRecipes('Full rawData: ' + JSON.stringify(rawData, null, 2));
            debugLogRecipes('Data fetched. Preparing chart...');
            // Get latest values from correct function and path, and adjust for FX
            const totalRevenue = Number(rawData['INCOME_STATEMENT']?.annualReports?.[0]?.totalRevenue ?? 0) * fxRateUsed;
            const operatingExpenses = Number(rawData['INCOME_STATEMENT']?.annualReports?.[0]?.operatingExpenses ?? 0) * fxRateUsed;
            const capitalExpenditures = Number(rawData['CASH_FLOW']?.annualReports?.[0]?.capitalExpenditures ?? 0) * fxRateUsed;
            const sga = Number(rawData['INCOME_STATEMENT']?.annualReports?.[0]?.sellingGeneralAndAdministrative ?? 0) * fxRateUsed;
            const rnd = Number(rawData['INCOME_STATEMENT']?.annualReports?.[0]?.researchAndDevelopment ?? 0) * fxRateUsed;
            // First level: totalRevenue -> operatingExpenses, capitalExpenditures, operatingCashflow
            const operatingCashflow = Number(rawData['CASH_FLOW']?.annualReports?.[0]?.operatingCashflow ?? 0) * fxRateUsed;
            // Second level: operatingExpenses -> SG&A, R&D, Other
            const other2 = operatingExpenses - sga - rnd;
            // Build nodes and links for Plotly multi-level Sankey, with formatted values
            const nodes = [
                `Total Revenue ($${formatLargeNumber(totalRevenue)})`,           // 0
                `Operating Expenses ($${formatLargeNumber(operatingExpenses)})`, // 1
                `Capital Expenditures ($${formatLargeNumber(capitalExpenditures)})`, // 2
                `Operating Cashflow ($${formatLargeNumber(operatingCashflow)})`, // 3
                `SG&A ($${formatLargeNumber(sga)})`,                             // 4
                `R&D ($${formatLargeNumber(rnd)})`,                              // 5
                `Other OpEx ($${formatLargeNumber(other2)})`                     // 6
            ];
            const links = [
                // totalRevenue splits
                { source: 0, target: 1, value: operatingExpenses },
                { source: 0, target: 2, value: capitalExpenditures },
                { source: 0, target: 3, value: operatingCashflow },
                // operatingExpenses splits
                { source: 1, target: 4, value: sga },
                { source: 1, target: 5, value: rnd },
                { source: 1, target: 6, value: other2 }
            ];
            debugLogRecipes(`Sankey nodes: ${JSON.stringify(nodes)}`);
            debugLogRecipes(`Sankey links: ${JSON.stringify(links)}`);
            renderPlotlySankeyChartMultiLevel('recipesSankeyChart', nodes, links);
        } catch (err) {
            renderQuickChartImage('recipesSankeyChart', '');
            debugLogRecipes(`Error: ${err.message}`);
        }
    }

    // Also re-run recipe logic if ticker or API key changes and recipes tab is active
    tickerInputTop.addEventListener('input', () => {
        if (document.querySelector('.tab.active').dataset.tab === 'recipes') {
            handleRecipeChange();
        }
    });
    alphaVantageApiKeyTop.addEventListener('input', () => {
        if (document.querySelector('.tab.active').dataset.tab === 'recipes') {
            handleRecipeChange();
        }
    });
});

// Load button triggers fetch for the currently active tab
loadBtn.addEventListener('click', function() {
    // If ticker or API key changed, reset loadedTabs
    if (getCurrentTicker() !== lastTicker || getCurrentApiKey() !== lastApiKey) {
        resetLoadedTabs();
        lastTicker = getCurrentTicker();
        lastApiKey = getCurrentApiKey();
    }
    const activeTab = document.querySelector('.tab.active').dataset.tab;
    fetchTabData(activeTab);
});

// Update plotData to accept ticker/apiKey as arguments
async function plotData(ticker, apiKey) {
    debugLog('Entered plotData');
    showLoadingSpinner();
    displayMessage('Fetching and processing data... Please wait.', 'info');

    // Use arguments, not DOM elements
    // Convert slider position to "years ago"
    const startYearAgo = 20 - parseInt(leftSlider.value);
    const endYearAgo = 20 - parseInt(rightSlider.value);
    debugLog(`Slider years: startYearAgo=${startYearAgo}, endYearAgo=${endYearAgo}`);

    if (!ticker || !apiKey) {
        debugLog('Missing ticker or API key');
        displayMessage('Ticker and Alpha Vantage API Key are required.', 'error');
        hideLoadingSpinner();
        return;
    }

    try {
        const now = new Date();
        const startDate = new Date(new Date().setFullYear(now.getFullYear() - startYearAgo));
        const endDate = new Date(new Date().setFullYear(now.getFullYear() - endYearAgo));
        debugLog(`Fetching data for ${ticker} from ${startDate.toISOString()} to ${endDate.toISOString()}`);
        const { rawData, fxRateUsed } = await fetchFinancialData(ticker, apiKey, startDate, endDate, metricsConfig);
        debugLog('fetchFinancialData returned');
        const processedMetrics = processFinancialData(rawData, fxRateUsed, startDate, endDate, metricsConfig);
        debugLog('processFinancialData returned');
        const chartData = prepareChartData(processedMetrics, getSelectedMetricsForPlotting(), metricsConfig);
        debugLog('prepareChartData returned');
        if (chartData) {
            createOrUpdateChart(chartData);
            lastFetchedChartData = { ...chartData, processedMetrics }; // Cache both chart data and processed metrics
            displayMessage('Chart updated successfully.', 'success');
            debugLog('Chart created/updated');
        } else {
            debugLog('No chartData to plot');
        }
    } catch (error) {
        debugLog('Error in plotData: ' + error.message);
        console.error("An error occurred during plotting:", error);
        displayMessage(`An error occurred: ${error.message}`, 'error');
    } finally {
        hideLoadingSpinner();
        debugLog('Spinner hidden');
    }
}

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
 * Shows the loading spinner.
 */
function showLoadingSpinner() {
    loadingSpinner.style.display = 'block';
}

/**
 * Hides the loading spinner.
 */
function hideLoadingSpinner() {
    loadingSpinner.style.display = 'none';
}

/**
 * Initializes the Alpha Vantage API knowledge base from metricsConfig.
 */
async function initializeAlphaVantageDataKnowledgeBase() {
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
}

// Function to replot based on UI changes without re-fetching
function replotFromCache() {
    if (lastFetchedChartData) {
        // Use cached processedMetrics if available, otherwise fallback to empty object
        const processedMetrics = lastFetchedChartData.processedMetrics || {};
        const selectedMetrics = getSelectedMetricsForPlotting() || [];
        const { datasets, commonLabels } = prepareChartData(processedMetrics, selectedMetrics, metricsConfig);
        createOrUpdateChart({ ...lastFetchedChartData, datasets, commonLabels });
    }
}

// Event Listeners
if (typeof window !== 'undefined') {
    window.addEventListener('DOMContentLoaded', () => {
        initializeAlphaVantageDataKnowledgeBase();
        // Removed: fetchButton.addEventListener('click', plotData);

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