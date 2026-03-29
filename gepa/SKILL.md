---
name: Optimize Financial Analysis Prompt using GEPA
description: Guide for agents and humans to synthesize financial training data and run prompt optimization using Google's GEPA framework.
---

# Generative Evaluation and Prompting Algorithm (GEPA) Pipeline

This directory contains scripts to generate a synthetic financial dataset and use it to iteratively optimize an LLM's system prompt to better predict stock movements.

## 🚨 Prerequisites
The `gepa` library **strictly requires Python 3.10 or higher**. If the system default is Python 3.9, the dependency resolution will fail. 

It is highly recommended to use the `uv` package manager to create and run within a dedicated virtual environment with the correct python version:
```bash
uv venv --python 3.10
uv pip install -r requirements.txt
```

## Step 1: Generate the Training Dataset
The dataset generation pipeline pulls actual historical data from Yahoo Finance and generates heavily fuzzed numerical array back-projections so that the LLM cannot perfectly memorize specific symbols or dates. It also injects qualitative historical sentiment and sector context paragraphs.

To regenerate the `stock_data.json` (130 records) and `holdout_data.json` (20 records):
```bash
uv run python3 data.py
```
*Note: This script uses the `yfinance` module and may take a few minutes as it pulls metadata for ~150 specific S&P 500 tickers.*

## Step 2: Run GEPA Optimization
The optimization loop trains the initial prompt defined in `prompts.py` using Gemini. 

To run the optimizer, you must ensure you have an active API key exported:
```bash
export GEMINI_API_KEY="your-google-api-key"
uv run python3 optimizer.py
```

The script will:
1. Load `stock_data.json` for GEPA's internal train and validation split.
2. Run the loop for multiple reflective iterations, proposing mutated prompts and computing reward scores using `metrics.py`.
3. Output the best performing system prompt.
4. Automatically evaluate the remaining unseen items in `holdout_data.json` on both the initial base prompt and the winning optimized prompt.
