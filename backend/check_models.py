#!/usr/bin/env python
import os
from dotenv import load_dotenv
import google.genai as genai

# Load environment variables
load_dotenv()

# Initialize client
api_key = os.getenv('GOOGLE_GEMINI_API_KEY')
if not api_key:
    print("ERROR: API key not found!")
    exit(1)

print(f"API Key exists: {api_key[:20]}...")

client = genai.Client(api_key=api_key)

# List all models
print("\n=== All Available Models ===")
models = client.models.list()
for model in models:
    print(f"- {model.name}")
    if hasattr(model, 'supported_generation_methods'):
        print(f"  Methods: {model.supported_generation_methods}")

# Filter for image models
print("\n=== Image/Imagen Models ===")
for model in models:
    if 'imagen' in model.name.lower() or 'image' in model.name.lower():
        print(f"✓ {model.name}")
        if hasattr(model, 'supported_generation_methods'):
            print(f"  Methods: {model.supported_generation_methods}")
