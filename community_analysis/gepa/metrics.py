import json
import re

async def stock_reward_metric(prediction: dict, true_future_return: float, true_fundamentals_fact: str, true_sentiment_fact: str) -> tuple[float, str]:
    """
    Async reward loop for the GEPA optimizer using LLM-as-a-judge. 
    Evaluates the predicted JSON thesis against the ground truth facts from the holdout period.
    Returns a tuple of (equally_weighted_average_score, reasoning).
    """
    import prompts

    if not isinstance(prediction, dict) or "recommendation" not in prediction:
        return 0.0, "Prediction was not valid JSON or was missing the 'recommendation' key."

    eval_sys_prompt = prompts.EVALUATOR_SYSTEM_PROMPT
    
    eval_user_prompt = prompts.EVALUATOR_USER_PROMPT_TEMPLATE.format(
        true_future_return=true_future_return,
        true_fundamentals_fact=true_fundamentals_fact,
        true_sentiment_fact=true_sentiment_fact,
        price_thesis=prediction.get('price_thesis', 'N/A'),
        fundamentals_thesis=prediction.get('fundamentals_thesis', 'N/A'),
        sentiment_thesis=prediction.get('sentiment_thesis', 'N/A'),
        recommendation=prediction.get('recommendation', 'N/A')
    )
    
    try:
        from google import genai
        from google.genai import types
        
        client = genai.Client()
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[eval_sys_prompt, eval_user_prompt],
            config=types.GenerateContentConfig(
                temperature=0.0,
                response_mime_type="application/json"
            )
        )
        
        output_text = response.text
        
        # Extract JSON
        match = re.search(r'\{.*\}', output_text, re.DOTALL)
        if match:
            scores_json = json.loads(match.group(0))
        else:
            scores_json = json.loads(output_text)
            
        p_score = float(scores_json.get("price_score", 0.0))
        f_score = float(scores_json.get("fundamentals_score", 0.0))
        s_score = float(scores_json.get("sentiment_score", 0.0))
        reasoning = scores_json.get("reasoning", "No reasoning provided.")
        
        # Calculate Equally Weighted Average
        final_score = (p_score + f_score + s_score) / 3.0
        
        return final_score, f"Price: {p_score}, Fund: {f_score}, Sent: {s_score}. {reasoning}"
        
    except Exception as e:
        return 0.0, f"Error calculating metric via LLM Judge: {e}"
