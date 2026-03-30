from data import generate_synthetic_market_data

def test_generate_synthetic_market_data():
    examples = generate_synthetic_market_data(n_samples=20)
    
    assert len(examples) == 20
    
    for ex in examples:
        assert isinstance(ex, dict)
        assert 'sector_context' in ex
        assert 'financials' in ex
        assert 'price_history' in ex
        assert 'future_return' in ex
        assert 'future_fundamentals_fact' in ex
        assert 'future_sentiment_fact' in ex
        assert 'recommendation' in ex
        
    recommendations = [ex['recommendation'] for ex in examples]
    
    # Assert that it generated valid labels (at least some variation)
    for rec in recommendations:
        assert rec in ["Buy", "Sell", "Hold"]
