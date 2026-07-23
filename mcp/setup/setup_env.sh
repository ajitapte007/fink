#!/bin/bash
set -e
echo "🔑 Checking environment configuration..."
cd "$(dirname "$0")/../.."

if [ ! -f ".env" ]; then
    echo "⚠️ .env file not found. Creating from .env.example..."
    cp .env.example .env
fi

source .env

if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" == "your_openai_api_key_here" ]; then
    read -p "🔑 Enter your OpenAI API Key (or press Enter to skip): " user_openai
    if [ -n "$user_openai" ]; then
        # Replace value in-place inside .env
        sed -i '' "s|OPENAI_API_KEY=.*|OPENAI_API_KEY=$user_openai|g" .env
        echo "✅ OpenAI API Key saved to .env"
    fi
fi

if [ -z "$ALPHAVANTAGE_API_KEY" ] || [ "$ALPHAVANTAGE_API_KEY" == "your_alphavantage_api_key_here" ]; then
    read -p "🔑 Enter your Alpha Vantage API Key (or press Enter to skip): " user_av
    if [ -n "$user_av" ]; then
        # Replace value in-place inside .env
        sed -i '' "s|ALPHAVANTAGE_API_KEY=.*|ALPHAVANTAGE_API_KEY=$user_av|g" .env
        echo "✅ Alpha Vantage API Key saved to .env"
    fi
fi
