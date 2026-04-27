import os
import json
import re
from dotenv import load_dotenv
from huggingface_hub import InferenceClient
from prompts import SYSTEM_PROMPT, CHUNK_SYSTEM_PROMPT, MERGE_SYSTEM_PROMPT

load_dotenv()

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

def chunk_text(text, chunk_size=7000):
    """
    Splits text into chunks of roughly chunk_size characters.
    Tries to split at paragraph/section boundaries (double newlines).
    """
    if len(text) <= chunk_size:
        return [text]
    
    chunks = []
    # Split by double newlines first (paragraphs/sections)
    paragraphs = re.split(r'\n\s*\n', text)
    
    current_chunk = ""
    for para in paragraphs:
        if len(current_chunk) + len(para) + 2 <= chunk_size:
            current_chunk += (para + "\n\n")
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            # If a single paragraph is larger than chunk_size, split it by single newlines
            if len(para) > chunk_size:
                lines = para.split('\n')
                sub_chunk = ""
                for line in lines:
                    if len(sub_chunk) + len(line) + 1 <= chunk_size:
                        sub_chunk += (line + "\n")
                    else:
                        if sub_chunk:
                            chunks.append(sub_chunk.strip())
                        sub_chunk = line + "\n"
                current_chunk = sub_chunk
            else:
                current_chunk = para + "\n\n"
                
    if current_chunk:
        chunks.append(current_chunk.strip())
        
    return chunks

def _get_hf_client():
    hf_token = os.getenv("HF_TOKEN")
    
    # Fallback for Streamlit Cloud deployment
    if not hf_token or hf_token in ["your_token_here", "your_hugging_face_token_here", ""]:
        try:
            import streamlit as st
            hf_token = st.secrets.get("HF_TOKEN")
        except Exception:
            pass

    if not hf_token or hf_token in ["your_token_here", "your_hugging_face_token_here", ""]:
        raise ValueError("Valid HF_TOKEN not found. Please set it in .env locally or in Streamlit Secrets if deployed.")

    return InferenceClient(token=hf_token)

def _call_hf_api(client, messages, max_tokens=1000):
    try:
        response = client.chat_completion(
            model=MODEL_ID,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2
        )
        
        content = response.choices[0].message.content
        
        # Try to parse the content as JSON
        # Sometimes models wrap JSON in markdown code blocks
        json_match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        else:
            # Fallback for just ``` blocks
            json_match = re.search(r'```\s*(.*?)\s*```', content, re.DOTALL)
            if json_match:
                content = json_match.group(1)
            else:
                content = content.strip()
                
        return json.loads(content)
    except json.JSONDecodeError as e:
        raise ValueError(f"Model returned invalid JSON. Error: {str(e)}\nContent: {content}")
    except Exception as e:
        raise RuntimeError(f"Hugging Face API request failed: {str(e)}")

def analyze_sop(sop_text, progress_callback=None):
    client = _get_hf_client()
    
    # Split text into chunks
    chunks = chunk_text(sop_text)
    total_chunks = len(chunks)
    
    if total_chunks == 1:
        # Single request if small enough
        if progress_callback:
            progress_callback("Analyzing document...", 0)
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze the following SOP text and return the JSON profile:\n\n{chunks[0]}"}
        ]
        result = _call_hf_api(client, messages)
        if progress_callback:
            progress_callback("Analysis complete!", 100)
        return result

    # Multiple chunks: Analyze each
    chunk_results = []
    for i, chunk in enumerate(chunks):
        if progress_callback:
            progress_callback(f"Analyzing chunk {i+1} of {total_chunks}...", int((i / (total_chunks + 1)) * 100))
        
        messages = [
            {"role": "system", "content": CHUNK_SYSTEM_PROMPT},
            {"role": "user", "content": f"Analyze this chunk (Part {i+1} of {total_chunks}) of the SOP:\n\n{chunk}"}
        ]
        
        try:
            chunk_result = _call_hf_api(client, messages)
            chunk_results.append(chunk_result)
        except Exception as e:
            # Add context to the error but don't stop if we have some results? 
            # Actually, better to fail fast or log it. The user asked for clear error handling.
            raise RuntimeError(f"Failed to analyze chunk {i+1}: {str(e)}")

    # Final Merge
    if progress_callback:
        progress_callback("Merging results...", 90)
        
    merge_payload = json.dumps(chunk_results, indent=2)
    messages = [
        {"role": "system", "content": MERGE_SYSTEM_PROMPT},
        {"role": "user", "content": f"Merge these partial results into one final JSON profile:\n\n{merge_payload}"}
    ]
    
    final_result = _call_hf_api(client, messages, max_tokens=1000) 
    
    if progress_callback:
        progress_callback("Analysis complete!", 100)
        
    return final_result
