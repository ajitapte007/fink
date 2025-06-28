// fetchUtils.js
// Utilities for fetching data and caching from Alpha Vantage

// LRU Cache for Alpha Vantage API calls
const alphaVantageCache = new Map();
const CACHE_MAX_SIZE = 100;

/**
 * Adds an item to the LRU cache.
 * @param {string} key The cache key (e.g., API URL).
 * @param {object} value The data to cache.
 */
export function addToCache(key, value) {
    if (alphaVantageCache.has(key)) {
        alphaVantageCache.delete(key);
    }
    if (alphaVantageCache.size >= CACHE_MAX_SIZE) {
        const oldestKey = alphaVantageCache.keys().next().value;
        alphaVantageCache.delete(oldestKey);
    }
    alphaVantageCache.set(key, value);
}

/**
 * Retrieves an item from the LRU cache. Marks the item as most recently used.
 * @param {string} key The cache key.
 * @returns {object|undefined} The cached data, or undefined if not found.
 */
export function getFromCache(key) {
    if (alphaVantageCache.has(key)) {
        const value = alphaVantageCache.get(key);
        alphaVantageCache.delete(key);
        alphaVantageCache.set(key, value);
        return value;
    }
    return undefined;
}

/**
 * Fetches all required raw data and FX rates for a ticker (with cache logic).
 * @param {string} ticker
 * @param {string} alphaVantageApiKey
 * @param {number} startYearAgo
 * @param {number} endYearAgo
 * @param {Array} metricsConfig
 * @returns {Promise<{rawData: object, fxRateUsed: number}>}
 */
export async function fetchFinancialData(ticker, alphaVantageApiKey, startYearAgo, endYearAgo, metricsConfig) {
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

    // Only consider these endpoints for currency detection
    const currencyEndpoints = ['CASH_FLOW', 'INCOME_STATEMENT', 'BALANCE_SHEET'];
    let localCurrency = 'USD';
    for (const func of currencyEndpoints) {
        const raw = fetchedRawData[func];
        if (!raw) continue;
        let detected = 'USD';
        if (raw && Array.isArray(raw["annualReports"]) && raw["annualReports"][0] && raw["annualReports"][0]["reportedCurrency"]) {
            detected = raw["annualReports"][0]["reportedCurrency"];
        } else if (raw && raw["reportedCurrency"]) {
            detected = raw["reportedCurrency"];
        }
        if (detected && detected !== 'USD') {
            localCurrency = detected;
            break;
        }
    }
    // Fetch FX rate series if needed
    let fxRateUsed = 1.0;
    if (localCurrency !== 'USD') {
        const fxUrl = `https://www.alphavantage.co/query?function=FX_MONTHLY&from_symbol=${localCurrency}&to_symbol=USD&apikey=${alphaVantageApiKey}`;
        let fxData;
        const cachedFX = getFromCache(fxUrl);
        if (cachedFX) {
            fxData = cachedFX;
        } else {
            fxData = await fetch(fxUrl).then(r => r.json());
            addToCache(fxUrl, fxData);
        }
        let mostRecentFX = 1.0;
        if (fxData && fxData["Time Series FX (Monthly)"]) {
            const entries = Object.entries(fxData["Time Series FX (Monthly)"]);
            if (entries.length > 0) {
                // Pick the most recent (first) FX rate
                mostRecentFX = parseFloat(entries[0][1]["4. close"]);
            }
        }
        // Use this single FX rate for all conversions
        fxRateUsed = mostRecentFX;
    }

    return { rawData: fetchedRawData, fxRateUsed };
} 