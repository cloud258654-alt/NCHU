import sys

try:
    from openai import OpenAI
    print("OpenAI SDK imported successfully.")
except ImportError:
    print("Error: The 'openai' package is required. Run 'pip install openai' first.")
    sys.exit(1)

def main():
    # Point the client to the LiteLLM proxy running locally
    client = OpenAI(
        api_key="sk-litellm-master-key-1234",  # Matches master_key in litellm_config.yaml
        base_url="http://localhost:4000"       # Matches port in docker-compose.yml
    )

    print("Sending mock sentiment analysis request to LiteLLM proxy...")
    try:
        response = client.chat.completions.create(
            model="gemini-2.5-flash",  # Directs LiteLLM to use Gemini model
            messages=[
                {
                    "role": "system", 
                    "content": "You are a sentiment analyzer. Reply with Positive, Negative, or Neutral."
                },
                {
                    "role": "user", 
                    "content": "The food tasted average, but the queue was way too long and hot."
                }
            ],
            temperature=0.0
        )
        
        sentiment = response.choices[0].message.content.strip()
        print("\n=== LiteLLM Response ===")
        print(f"Sentiment: {sentiment}")
        print("========================")
        
    except Exception as e:
        print(f"\nFailed to connect or retrieve response from LiteLLM proxy: {e}")
        print("Please make sure the docker container is running ('docker compose up -d') and GEMINI_API_KEY is configured.")

if __name__ == "__main__":
    main()
