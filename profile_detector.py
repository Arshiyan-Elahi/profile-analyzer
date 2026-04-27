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

def _repair_json(json_str):
    """
    Attempts to repair truncated JSON by closing open braces/brackets/strings.
    """
    json_str = json_str.strip()
    if not json_str:
        return "{}"
        
    stack = []
    in_string = False
    escape = False
    last_val_idx = -1
    
    for i, char in enumerate(json_str):
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char in '{[':
                stack.append('}' if char == '{' else ']')
            elif char in '}]':
                if stack and stack[-1] == char:
                    stack.pop()
            if not char.isspace():
                last_val_idx = i
    
    if in_string:
        json_str += '"'
        
    if last_val_idx != -1 and json_str[last_val_idx] == ',':
        json_str = json_str[:last_val_idx] + json_str[last_val_idx+1:]

    while stack:
        json_str += stack.pop()
        
    return json_str

def _extract_json(content):
    """
    Extracts the first valid JSON object from a string, handling markdown fences and prefixes.
    """
    content = content.strip()
    
    # 1. Try regex for markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
    if json_match:
        content = json_match.group(1).strip()
    
    # 2. Find the first '{' and last '}'
    start_idx = content.find('{')
    end_idx = content.rfind('}')
    
    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
        content = content[start_idx:end_idx + 1]
    
    return content

def _post_process_result(data):
    """
    Deduplicates and limits list items in the JSON result.
    """
    if not isinstance(data, dict):
        return data
        
    list_fields = ['terminology', 'preferred_wording', 'forbidden_wording']
    for field in list_fields:
        if field in data and isinstance(data[field], list):
            # Deduplicate while preserving order
            seen = set()
            deduped = []
            for item in data[field]:
                if isinstance(item, str):
                    val = item.strip()
                    if val and val.lower() not in seen:
                        seen.add(val.lower())
                        deduped.append(val)
                else:
                    deduped.append(item)
            data[field] = deduped[:10]
            
    if 'profile_suggestions' in data and isinstance(data['profile_suggestions'], list):
        data['profile_suggestions'] = data['profile_suggestions'][:5]
        
    return data

def _call_hf_api(client, messages, max_tokens=1000, retry=True):
    try:
        response = client.chat_completion(
            model=MODEL_ID,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.1
        )
        
        raw_content = response.choices[0].message.content
        content = _extract_json(raw_content)
        
        try:
            result = json.loads(content)
            return _post_process_result(result)
        except json.JSONDecodeError:
            # Try basic repair first
            try:
                repaired_content = _repair_json(content)
                result = json.loads(repaired_content)
                return _post_process_result(result)
            except Exception:
                # If repair fails and retry is allowed, ask the model to fix it
                if retry:
                    repair_messages = [
                        {"role": "system", "content": "Your previous response was invalid JSON. Convert it into valid RAW JSON only. Do not add markdown fences or explanations."},
                        {"role": "user", "content": raw_content}
                    ]
                    return _call_hf_api(client, repair_messages, max_tokens=max_tokens, retry=False)
                raise
                
    except Exception as e:
        if retry:
             # One last attempt if it was a general connection error
             return _call_hf_api(client, messages, max_tokens=max_tokens, retry=False)
        raise RuntimeError(f"Hugging Face API request failed: {str(e)}")

def analyze_sop(sop_text, progress_callback=None):
    client = _get_hf_client()
    
    chunks = chunk_text(sop_text)
    total_chunks = len(chunks)
    
    if total_chunks == 1:
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
            raise RuntimeError(f"Failed to analyze chunk {i+1}: {str(e)}")

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
