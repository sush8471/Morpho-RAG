import os
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
llm_model = os.getenv("LLM_MODEL", "gemini-3.8-flash")
fallback_model = os.getenv("FALLBACK_LLM_MODEL", "gemini-3.5-flash-lite")
embedding_model = os.getenv("EMBEDDING_MODEL", "gemini-embedding-001")

if not api_key:
    raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY not found in environment.")

client = genai.Client(api_key=api_key)

# 1. Generation test with primary & fallback support
print(f"1. Testing text generation with primary model: '{llm_model}'...")
try:
    response = client.models.generate_content(
        model=llm_model,
        contents="Say 'Morpho RAG is running with Gemini 3.8!'",
    )
    print(f"   Success ({llm_model}):", response.text.strip())
except Exception as e:
    print(f"   Primary model '{llm_model}' unavailable ({e}), trying fallback '{fallback_model}'...")
    response = client.models.generate_content(
        model=fallback_model,
        contents="Say 'Morpho RAG fallback active!'",
    )
    print(f"   Success ({fallback_model}):", response.text.strip())

# 2. Embedding test
print(f"\n2. Testing embeddings with: '{embedding_model}'...")
embed_response = client.models.embed_content(
    model=embedding_model,
    contents="Retrieval Augmented Generation with Qdrant and Gemini",
)
vector = embed_response.embeddings[0].values
print(f"   Success: Generated embedding vector of dimension {len(vector)}")

print("\nModel pipeline configured and verified successfully!")
