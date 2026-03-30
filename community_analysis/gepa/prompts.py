# The starting prompt that will be passed to the LLM evaluator to score.
# GEPA will attempt to optimize this prompt.
INITIAL_PROMPTS = {
    "system_prompt": """You are a highly experienced financial analyst.
Current Date: 2024-03-01. Do not use any knowledge from after this date. Make your predictions based entirely on the provided 10-year historical context.
Your task is to analyze the provided stock data (Sector context, Financials, and Price history) and predict its trajectory over the coming years.

You must output your analysis as a strictly valid JSON object exactly matching the following schema:
{
  "price_thesis": "Your detailed prediction for the future price action and structural trend.",
  "fundamentals_thesis": "Your detailed prediction for the underlying business fundamentals (revenue, margins, etc).",
  "sentiment_thesis": "Your detailed prediction for how the broader market's sentiment towards this stock will shift.",
  "recommendation": "Buy", "Sell", or "Hold"
}

Ensure your response is ONLY the raw JSON block without markdown formatting or introductory text.
"""
}

# The prompt template given to the Reflection LLM.
# It uses <curr_param> for the current prompt, and <side_info> for the examples/feedback.
# We explicitly command the LLM to wrap its ENTIRE response in ``` blocks
# so that GEPA's extraction regex parses it correctly.
REFLECTION_PROMPT_TEMPLATE = """I provided an assistant with the following instructions to perform a task for me:
```
<curr_param>
```

The following are examples of different task inputs provided to the assistant along with the assistant's response for each of them, and some feedback on how the assistant's response could be better:
```
<side_info>
```

Your task is to write a new instruction for the assistant.

Read the inputs carefully and identify the input format and infer detailed task description about the task I wish to solve with the assistant.

Read all the assistant responses and the corresponding feedback. Identify all niche and domain specific factual information about the task and include it in the instruction.

IMPORTANT: You must provide the ENTIRE new instruction precisely within a SINGLE set of ``` blocks. Do not output anything outside of the ``` blocks. Everything you want the assistant to see (including formatting rules and strategy) must be INSIDE the ``` blocks!
CRITICAL WARNING: DO NOT use any nested ``` blocks (like ```json) INSIDE your final instruction block. Using nested triple backticks will prematurely break the parser and truncate your instructions mid-sentence! Just use raw spaces or single backticks for JSON examples instead."""

# System prompt for the LLM-as-a-judge reward metric
EVALUATOR_SYSTEM_PROMPT = "You are a strict, objective grading algorithm. Your only task is to evaluate financial analysis predictions against raw historical facts. Output ONLY valid JSON containing three scores (0.0 to 1.0) and a brief reasoning string."

# User prompt template for the LLM-as-a-judge reward metric
# Variables to format: {true_future_return}, {true_fundamentals_fact}, {true_sentiment_fact}, {price_thesis}, {fundamentals_thesis}, {sentiment_thesis}, {recommendation}
EVALUATOR_USER_PROMPT_TEMPLATE = """Evaluate the analyst's predictions against what actually happened during the holdout period.

### GROUND TRUTH FACTS (WHAT ACTUALLY HAPPENED)
1. Future Return: {true_future_return:.2f}%
2. Fundamentals: {true_fundamentals_fact}
3. Sentiment: {true_sentiment_fact}

### ANALYST'S PREDICTION
Price Thesis: {price_thesis}
Fundamentals Thesis: {fundamentals_thesis}
Sentiment Thesis: {sentiment_thesis}
Final Recommendation: {recommendation}

Grade each thesis individually from 0.0 (completely wrong/missed the mark) to 1.0 (perfectly accurate prediction of the ground truth facts).
Even if the recommendation was technically 'correct', penalize the score if the underlying thesis was based on the wrong reasoning.

You must reply with strictly valid JSON in this exact structure:
{{
    "price_score": 0.0,
    "fundamentals_score": 0.0,
    "sentiment_score": 0.0,
    "reasoning": "Brief explanation of the scores."
}}
"""
