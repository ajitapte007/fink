import os
from data import generate_synthetic_market_data
from modules import StockAnalystAdapter
import gepa
import prompts

def main():
    print("Generating dataset...")
    # Generating a slightly larger dataset
    dataset = generate_synthetic_market_data(60)
    
    from collections import defaultdict
    import random
    
    regime_groups = defaultdict(list)
    for d in dataset:
        regime_groups[d.get("regime_label", "Unknown")].append(d)
        
    train_data = []
    val_data = []
    
    for regime, items in regime_groups.items():
        # Shuffle internally to mix tickers
        random.shuffle(items)
        # Allocate up to 4 samples per regime to the validation holdout
        val_samples = items[:4]
        train_samples = items[4:]
        
        val_data.extend(val_samples)
        train_data.extend(train_samples)
        
    print(f"Stratified Split complete. Train data size: {len(train_data)}, Validation size: {len(val_data)}")
    adapter = StockAnalystAdapter(model_name="gemini/gemini-2.5-flash")
    
    api_key_set = bool(os.environ.get("GEMINI_API_KEY"))
    if not api_key_set:
        print("WARNING: GEMINI_API_KEY not found in environment. Running with local mocked strings just to verify structure.")
        
    print("\n--- Running GEPA Optimization ---")

    def gemini_reflection_lm(prompt, **kwargs):
        if not api_key_set:
            return "```\nYou are an improved, mocked analyst prompt. Output JSON.\n```"
            
        print("\n[DEBUG] Requesting reflection from Gemini (native SDK)...")
        # GEPA passes either a string or a list of message dicts.
        if isinstance(prompt, list):
            # Extract just the text from the GEPA message format
            # GEPA formatting is typically [{"role": "user", "content": "..."}]
            prompt_text = "\n".join([m.get("content", "") for m in prompt if isinstance(m, dict)])
        else:
            prompt_text = str(prompt)
            
        try:
            from google import genai
            client = genai.Client()
            response = client.models.generate_content(
                model="gemini-2.5-pro",
                contents=prompt_text,
                config=genai.types.GenerateContentConfig(
                    max_output_tokens=4096,
                    temperature=0.7
                )
            )
            raw = response.text
            print(f"[DEBUG] Gemini proposed raw text ({len(raw)} chars).")
            return raw
        except Exception as e:
            print(f"[DEBUG] Error contacting Gemini: {e}")
            return "```\nError proposing prompt\n```"

    optimizer = gepa.optimize(
        seed_candidate=prompts.INITIAL_PROMPTS,
        trainset=train_data,
        valset=val_data,
        adapter=adapter,
        reflection_lm=gemini_reflection_lm,
        reflection_prompt_template=prompts.REFLECTION_PROMPT_TEMPLATE,
        max_metric_calls=150,
        reflection_minibatch_size=5
    )

    print("\n=== OPTIMIZATION COMPLETE ===\n")
    print("Initial Instructions:")
    print(prompts.INITIAL_PROMPTS["system_prompt"])
    print("\nOptimized Instructions:")
    print(optimizer.best_candidate["system_prompt"])
    print("\nBest Validation Score:", optimizer.val_aggregate_scores[optimizer.best_idx])
    
    print("\n--- Testing on a Bubble Example ---")
    bubble_data = {
        'sector_context': "Meme Stocks, retail euphoria",
        'financials': "P/E ratio: 150.0, Declining margins: -20.0%, Revenue growth decelerating",
        'price_history': "Up 300% in 1 year, massive volatility, MACD highly divergent",
        'recommendation': "Sell",
        'future_return': -60.0,
        'future_fundamentals_fact': "Growth completely rapidly evaporated. Margins compressed heavily under brutal competition and inventory glut.",
        'future_sentiment_fact': "The narrative completely broke. Euphoria instantly rotated into panic, causing massive multiple contraction and institutional dumping."
    }
    
    print("Running Base Prompt...")
    base_eval = adapter.evaluate([bubble_data], prompts.INITIAL_PROMPTS)
    # Extract prediction from JSON dict instead of string
    try:
        base_pred = base_eval.outputs[0]["extracted_recommendation"]
        print("Base Prediction (Raw JSON Data):", base_eval.outputs[0])
    except Exception as e:
        print("Base Prediction Failed:", e)
    
    print("\nRunning Optimized Prompt...")
    opt_eval = adapter.evaluate([bubble_data], optimizer.best_candidate)
    try:
        opt_pred = opt_eval.outputs[0]["extracted_recommendation"]
        print("Optimized Prediction (Raw JSON Data):", opt_eval.outputs[0])
    except Exception as e:
        print("Optimized Prediction Failed:", e)

if __name__ == "__main__":
    main()
