import streamlit as st
import json
from profile_detector import analyze_sop

st.set_page_config(page_title="SOP Profile Detection", layout="wide")

st.title("SOP Client Profile Detection Test")
st.write("This demo uses Qwen/Qwen2.5-7B-Instruct via the Hugging Face Inference API.")

st.sidebar.header("Options")
input_method = st.sidebar.radio("Input Method", ["Paste Text", "Upload Files"])

sop_text = ""

if input_method == "Paste Text":
    sop_text = st.text_area("Paste SOP Text Here:", height=300)
else:
    uploaded_files = st.sidebar.file_uploader("Upload SOP files", type=["txt", "pdf", "docx", "doc"], accept_multiple_files=True)
    if uploaded_files:
        selected_file_name = st.selectbox("Select file to view/analyze:", [f.name for f in uploaded_files])
        for f in uploaded_files:
            if f.name == selected_file_name:
                if f.name.endswith(".txt"):
                    sop_text = f.read().decode("utf-8")
                elif f.name.endswith(".pdf"):
                    import PyPDF2
                    pdf_reader = PyPDF2.PdfReader(f)
                    sop_text = "\n".join([page.extract_text() or "" for page in pdf_reader.pages])
                elif f.name.endswith(".docx") or f.name.endswith(".doc"):
                    try:
                        import docx
                        doc = docx.Document(f)
                        sop_text = "\n".join([para.text for para in doc.paragraphs])
                    except Exception as e:
                        st.error(f"Could not read Word document. Older .doc files may need to be converted to .docx first.\nError: {e}")
                        sop_text = ""
                st.text_area("File Content Preview:", value=sop_text, height=300, disabled=True)
                break
    else:
        st.info("Please upload one or more files from the sidebar.")

if st.button("Analyze SOP"):
    if not sop_text.strip():
        st.warning("Please provide SOP text to analyze.")
    else:
        status_container = st.status("Initializing analysis...", expanded=True)
        
        def update_progress(text, percentage):
            status_container.update(label=text)
            # We can also add a progress bar inside the status if we want
        
        try:
            result = analyze_sop(sop_text, progress_callback=update_progress)
            status_container.update(label="Analysis Complete!", state="complete", expanded=False)
            st.success("Analysis Complete!")
            
            # Display readable summary if available
            if "summary" in result and result["summary"]:
                st.subheader("Executive Summary")
                st.info(result["summary"])
            
            st.subheader("Detected Profile (Structured JSON)")
            st.json(result)
        except Exception as e:
            status_container.update(label="Analysis Failed", state="error")
            st.error(f"Error during analysis: {e}")
