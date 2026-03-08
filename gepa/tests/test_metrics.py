import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import json

@pytest.mark.asyncio
async def test_stock_reward_metric_valid_json():
    from metrics import stock_reward_metric
    prediction = {
        "price_thesis": "Stock goes up",
        "fundamentals_thesis": "Revenue grows",
        "sentiment_thesis": "People love it",
        "recommendation": "Buy"
    }
    
    with patch('google.genai.Client') as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance
        
        # Mock LLM response giving varying scores
        mock_response = MagicMock()
        mock_response.text = json.dumps({
            "price_score": 1.0,
            "fundamentals_score": 0.5,
            "sentiment_score": 0.0,
            "reasoning": "Mixed accuracy."
        })
        mock_instance.aio.models.generate_content = AsyncMock(return_value=mock_response)
        
        score, feedback = await stock_reward_metric(
            prediction=prediction,
            true_future_return=25.0,
            true_fundamentals_fact="Rapid growth",
            true_sentiment_fact="Panic selling"
        )
        
        assert score == pytest.approx(0.5)
        assert "Price: 1.0" in feedback
        assert "Mixed accuracy" in feedback

@pytest.mark.asyncio
async def test_stock_reward_metric_invalid_prediction():
    from metrics import stock_reward_metric
    score, feedback = await stock_reward_metric("Buy", 25.0, "Fact", "Fact")
    assert score == 0.0
    assert "Prediction was not valid JSON" in feedback
    
    score, feedback = await stock_reward_metric({"price_thesis": "Up"}, 25.0, "Fact", "Fact")
    assert score == 0.0
    assert "missing the 'recommendation' key" in feedback
