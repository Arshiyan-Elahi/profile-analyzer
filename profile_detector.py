import os
import json
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from prompts import SYSTEM_PROMPT

load_dotenv()

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

def analyze_sop(sop_text):
    hf_token = os.getenv("HF_TOKEN")
    
    # Fallback for Streamlit Cloud deployment
    if not hf_token or hf_token == "your_token_here" or hf_token == "your_hugging_face_token_here":
        try:
            import streamlit as st
            hf_token = st.secrets.get("HF_TOKEN")
        except Exception:
            pass

    if not hf_token or hf_token == "your_token_here" or hf_token == "your_hugging_face_token_here":
        raise ValueError("Valid HF_TOKEN not found. Please set it in .env locally or in Streamlit Secrets if deployed.")

    client = InferenceClient(token=hf_token)
    
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Analyze the following SOP text and return the JSON profile:\n\n{sop_text}"}
    ]
    
    try:
        response = client.chat_completion(
            model=MODEL_ID,
            messages=messages,
            max_tokens=1000,
            temperature=0.2
        )
        
        content = response.choices[0].message.content
        
        # Try to parse the content as JSON
        try:
            # Sometimes models wrap JSON in markdown code blocks
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            parsed_json = json.loads(content)
            return parsed_json
        except json.JSONDecodeError:
            raise ValueError(f"Model returned invalid JSON: {content}")
            
    except Exception as e:
        raise RuntimeError(f"Hugging Face API request failed: {str(e)}")
