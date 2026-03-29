import os
from data import generate_synthetic_market_data
from modules import StockAnalystAdapter
import gepa
import prompts

def main():
    import json
    print("Loading datasets...")
    with open("stock_data.json", "r") as f:
        dataset = json.load(f)
    
    with open("holdout_data.json", "r") as f:
        holdout_data = json.load(f)
    
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
        max_metric_calls=500,
        reflection_minibatch_size=5
    )

    print("\n=== OPTIMIZATION COMPLETE ===\n")
    print("Initial Instructions:")
    print(prompts.INITIAL_PROMPTS["system_prompt"])
    print("\nOptimized Instructions:")
    print(optimizer.best_candidate["system_prompt"])
    print("\nBest Validation Score:", optimizer.val_aggregate_scores[optimizer.best_idx])
    
    print("\n--- Testing on Holdout Set (Base vs Optimized) ---")
    
    print(f"Evaluating {len(holdout_data)} holdout samples on Base Prompt...")
    base_eval = adapter.evaluate(holdout_data, prompts.INITIAL_PROMPTS)
    
    print(f"\nEvaluating {len(holdout_data)} holdout samples on Optimized Prompt...")
    opt_eval = adapter.evaluate(holdout_data, optimizer.best_candidate)
    
    # Simple accuracy comparison
    base_correct = 0
    opt_correct = 0
    
    for i, data in enumerate(holdout_data):
        target = data.get("recommendation", "Hold")
        
        base_pred = base_eval.outputs[i].get("extracted_recommendation", "Unknown") if base_eval.outputs[i] else "Unknown"
        opt_pred = opt_eval.outputs[i].get("extracted_recommendation", "Unknown") if opt_eval.outputs[i] else "Unknown"
        
        if base_pred == target: base_correct += 1
        if opt_pred == target: opt_correct += 1
        
    print(f"\nHoldout Set Evaluation Complete:")
    print(f"Base Prompt Accuracy:      {base_correct}/{len(holdout_data)} ({(base_correct/len(holdout_data))*100:.1f}%)")
    print(f"Optimized Prompt Accuracy: {opt_correct}/{len(holdout_data)} ({(opt_correct/len(holdout_data))*100:.1f}%)")

if __name__ == "__main__":
    main()
