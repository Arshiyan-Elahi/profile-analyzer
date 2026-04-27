# Profile Detection HF Test

This is a small local demo that sends SOP text to the Hugging Face Inference API using the `Qwen/Qwen2.5-7B-Instruct` model to test AI-based Client Profile Detection.

## Setup Instructions

1. Ensure you have Python installed.
2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Open the `.env` file and replace `your_token_here` with your actual Hugging Face API token.

## Running the App

1. Run the Streamlit application:
   ```bash
   streamlit run app.py
   ```
2. Open the provided local URL in your browser.
3. You can either paste your own SOP text or use the provided `sample_sop.txt`.
4. Click "Analyze SOP" to see the extracted profile in JSON format.
