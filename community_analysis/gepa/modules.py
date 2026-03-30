import os
from typing import Any, Sequence, Mapping
from gepa.core.adapter import GEPAAdapter, EvaluationBatch
from metrics import stock_reward_metric

# We define DataInst=dict, Trajectory=dict, RolloutOutput=dict
class StockAnalystAdapter(GEPAAdapter[dict, dict, dict]):
    def __init__(self, model_name="gemini/gemini-2.5-flash"):
        self.model_name = model_name
        self._llm_configured = bool(os.environ.get("GEMINI_API_KEY"))

    async def _call_llm(self, sys_prompt: str, user_prompt: str) -> str:
        # Mock for local dev without a real key
        if not self._llm_configured:
            return "Based on mock evaluation, recommendation: Hold"
            
        try:
            from google import genai
            from google.genai import types
            import asyncio
            
            client = genai.Client()
            response = await client.aio.models.generate_content(
                model=self.model_name.replace("gemini/", ""), # Remove litellm prefix if present
                contents=[
                    sys_prompt,
                    user_prompt
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=4096,
                    temperature=0.0,
                    response_mime_type="application/json"
                )
            )
            return response.text
        except Exception as e:
            return f"Error generating response: {e}"

    def evaluate(self, batch: list[dict], candidate: dict[str, str], capture_traces: bool = False):
        import asyncio
        from tqdm.asyncio import tqdm
        system_prompt = candidate.get("system_prompt", "You are a financial analyst.")
        import re
        import json
        
        outputs = [None] * len(batch)
        scores = [0.0] * len(batch)
        trajectories = [None] * len(batch) if capture_traces else None
        
        async def process_item(idx, data):
            user_prompt = (
                f"Sector Context: {data['sector_context']}\n"
                f"Financials: {data['financials']}\n"
                f"Price History: {data['price_history']}\n"
            )
            
            # 1. Execute LLM
            llm_response = await self._call_llm(system_prompt, user_prompt)
            
            # 2. Extract JSON (Robustly)
            predicted_json = {}
            try:
                match = re.search(r'\{.*\}', llm_response, re.DOTALL)
                if match:
                    predicted_json = json.loads(match.group(0))
                else:
                    predicted_json = json.loads(llm_response)
            except Exception as e:
                pass
                
            rec = predicted_json.get("recommendation", "Hold")
                
            # 3. Calculate Reward using multi-factor LLM-as-a-judge (Make this async too eventually, but wrapper handles it)
            # We must import the async version or run it in a thread pool if it's sync
            from metrics import stock_reward_metric
            score, feedback = await stock_reward_metric(
                prediction=predicted_json,
                true_future_return=data['future_return'],
                true_fundamentals_fact=data.get('future_fundamentals_fact', ''),
                true_sentiment_fact=data.get('future_sentiment_fact', '')
            )
            
            outputs[idx] = {"llm_response": llm_response, "extracted_recommendation": rec}
            scores[idx] = score
            
            if capture_traces:
                trajectories[idx] = {
                    "inputs": {"sector": data['sector_context'], "financials": data['financials'], "price": data['price_history']},
                    "generated": llm_response,
                    "extracted": predicted_json,
                    "correct_action": data['recommendation'],
                    "feedback": feedback
                }

        async def run_batch():
            tasks = [process_item(i, d) for i, d in enumerate(batch)]
            _ = await tqdm.gather(*tasks, desc=f"Evaluating Batch ({len(batch)} items)")

        asyncio.run(run_batch())
        
        return EvaluationBatch(
            outputs=outputs,
            scores=scores,
            trajectories=trajectories
        )

    def make_reflective_dataset(self, candidate: dict[str, str], eval_batch: EvaluationBatch[dict, dict], components_to_update: list[str]) -> Mapping[str, Sequence[Mapping[str, Any]]]:
        if "system_prompt" not in components_to_update:
            return {}
            
        dataset = []
        for traj in eval_batch.trajectories:
            record = {
                "Inputs": traj["inputs"],
                "Generated Outputs": traj["generated"],
                "Feedback": traj["feedback"]
            }
            dataset.append(record)
            
        return {"system_prompt": dataset}
