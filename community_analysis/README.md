# Fink: A WYSIWYG Personal Finance Due Diligence Tool

Fink is a web-based tool for financial due diligence. It allows users to plot historical stock prices and various financial metrics for a given stock ticker, using data from the Alpha Vantage API.

## Features

*   **Interactive Charts:** Visualize financial data using Chart.js, with support for dual Y-axes.
*   **Multiple Metrics:** Plot key financial indicators such as:
    *   Adjusted Close Price
    *   PE (Price-to-Earnings) Ratio
    *   PS (Price-to-Sales) Ratio
    *   Shares Outstanding
    *   TTM (Trailing Twelve Months) Dividends
*   **Customizable Timeframe:** View data for the last 1, 5, 10, or 20 years, or all available historical data.
*   **Human-Readable Formatting:** Axes and tooltips display large numbers and currency in an easy-to-read format (e.g., "1.2B" for billions, "$2.50" for currency).
*   **API Caching:** Implements a client-side LRU cache to minimize API calls to Alpha Vantage and improve performance on repeated requests.
*   **Execution Log:** A "papertrail" log shows the steps the application is taking to fetch and process data, making it easier to debug.

## How to Use

1.  Open `index.html` in a modern web browser.
2.  Enter a valid stock ticker symbol (e.g., `IBM`, `AAPL`).
3.  Enter your personal [Alpha Vantage API Key](https://www.alphavantage.co/support/#api-key).
4.  Select the desired timeframe from the dropdown menu.
5.  Use the checkboxes and radio buttons to select which metrics to plot on the chart.
6.  Click the "Plot Data" button. The chart will update dynamically.

## Running Locally

Because modern browsers have security restrictions that prevent loading JavaScript modules directly from the local filesystem (`file://`), you need to run a simple local web server to use this application.

1.  **Install `http-server`:** If you don't have it, install it globally via npm:
    ```bash
    npm install -g http-server
    ```
2.  **Start the server:** Navigate to the project's root directory (`/Users/ajitapte/fink`) in your terminal and run the following command:
    ```bash
    http-server -p 8081 .
    ```
3.  **Access the application:** Open your web browser and go to `http://localhost:8081`.

## Project Structure

The project is organized into three main files:

*   `index.html`: The main HTML file containing the structure of the web application.
*   `styles.css`: Contains all the custom CSS and styling for the application.
*   `script.js`: The core JavaScript file that handles:
    *   User input and UI interactions.
    *   Fetching and caching data from the Alpha Vantage API.
    *   Processing and transforming raw financial data into plottable metrics.
    *   Rendering and updating the chart with Chart.js.

## Tech Stack

*   HTML5
*   CSS3 with [Tailwind CSS](https://tailwindcss.com/)
*   Vanilla JavaScript (ES6+)
*   [Chart.js](https://www.chartjs.org/) for charting
*   [Alpha Vantage API](https://www.alphavantage.co/) for financial data 