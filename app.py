## Adapted from streamlit tutorial. Refrence link below:
# https://docs.streamlit.io/develop/tutorials/chat-and-llm-apps/build-conversational-apps)

import streamlit as st
import os
import base64
import tempfile
import uuid
import time
import gc
import nest_asyncio 
nest_asyncio.apply()

from src.utils import convert_pdf_to_markdown
from src.chunk_embed import chunk_markdown, EmbedData, save_embeddings, load_embeddings
from src.index import QdrantVDB
from src.retriever import Retriever
from src.rag_engine import RAG
from llama_index.core import Settings

if "id" not in st.session_state:
    st.session_state.id = uuid.uuid4()
    st.session_state.file_cache = {}

session_id = st.session_state.id


def reset_chat():
    st.session_state.messages = []
    st.session_state.context = None
    gc.collect()

# Function to display the uploaded PDF in the app
def display_pdf(file):
    st.markdown("### 📄 PDF Preview")
    base64_pdf = base64.b64encode(file.read()).decode("utf-8")
    pdf_display = f"""<iframe src="data:application/pdf;base64,{base64_pdf}" width="500" height="100%" type="application/pdf"
                        style="height:100vh; width:100%"
                    >
                    </iframe>"""
    st.markdown(pdf_display, unsafe_allow_html=True)


# Sidebar: Upload Document
with st.sidebar:
    st.markdown("<h1 style='text-align: center;'>🤖  Multimodal RAG - Query your document</h1>", unsafe_allow_html=True)
    st.header("Upload your PDF")
    uploaded_file = st.file_uploader("", type="pdf")
    

    if uploaded_file:
        file_key = f"{session_id}-{uploaded_file.name}"
        if file_key not in st.session_state.file_cache:
            status_placeholder = st.empty()
            status_placeholder.info("📥 File uploaded successfully")
        
            time.sleep(2.5)  # Delay before switching message
        

            with tempfile.TemporaryDirectory() as temp_dir:
                file_path = os.path.join(temp_dir, uploaded_file.name)
                print(f"Temporary file path: {file_path}")
                # Save uploaded file to temp dir
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getvalue())

                status_placeholder.info("Identifying document layout...")
                progress_bar = st.progress(10)


                # Convert to markdown
                markdown_text = convert_pdf_to_markdown(file_path)
                st.session_state.markdown_text = markdown_text

                status_placeholder.info("Generating embeddings...")
                progress_bar.progress(50)
                
                chunks = chunk_markdown(markdown_text)
                st.session_state.chunks = chunks

                embeddata = EmbedData(batch_size=8)
                embeddata.embed(chunks)
                save_embeddings(embeddata, "embeddings_attention.pkl")

                st.session_state.embeddata = embeddata

                status_placeholder.info("Indexing the document...")
                progress_bar.progress(80)

                database = QdrantVDB(collection_name="MultiMod_collection", vector_dim=len(embeddata.embeddings[0]), batch_size=7)
                database.create_collection()
                database.ingest_data(embeddata)

                st.session_state.database= database

                # After vector DB and embeddata have been defined...
                retriever = Retriever(database, embeddata=embeddata)
                rag = RAG(retriever)
                st.session_state.rag = rag
                status_placeholder = st.empty()
                st.success("Ready to Chat...")
                progress_bar.progress(100)
                st.session_state.file_cache[file_key] = True
                
        else:
            st.success("Ready to Chat...")  
        display_pdf(uploaded_file)

            

col1, col2 = st.columns([6, 1])

with col2:
    st.button("Clear ↺", on_click=reset_chat)

# Initialize chat history
if "messages" not in st.session_state:
    reset_chat()


# Show message history (preserved across reruns)
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Accept user query
if prompt := st.chat_input("Ask a question..."):

    # Store and display user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Generate RAG-based response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
    
        with st.spinner("Thinking..."):
        
            rag = st.session_state.get("rag")
            response_text = rag.query(prompt)
            message_placeholder.markdown(response_text)
            

    # Store assistant response
    st.session_state.messages.append({"role": "assistant", "content": response_text})


