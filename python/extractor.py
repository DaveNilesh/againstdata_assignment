from langchain_community.chat_models import ChatOllama
from langchain_huggingface import ChatHuggingFace, HuggingFaceEndpoint
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

try:
    from .models import CompanyData
except ImportError:
    from models import CompanyData
import json
import os
import time

class Extractor:
    def __init__(self):
        hf_token = os.getenv("HUGGINGFACEHUB_API_TOKEN")
        
        if hf_token:
            print("INFO: Initializing Hugging Face Inference API (HuggingFaceH4/zephyr-7b-beta)")
            try:
                endpoint = HuggingFaceEndpoint(
                    repo_id="HuggingFaceH4/zephyr-7b-beta",
                    task="text-generation",
                    max_new_tokens=512,
                    do_sample=False,
                    repetition_penalty=1.03,
                    huggingfacehub_api_token=hf_token
                )
                self.llm = ChatHuggingFace(llm=endpoint)
            except Exception as e:
                print(f"ERROR: Failed to initialize Hugging Face: {e}. Falling back to Ollama.")
                hf_token = None # Fallback trigger
        
        if not hf_token:
             # Assumes Ollama is running and accessible. 
             # In docker-compose, might need OLLAMA_URL env var if not localhost.
             print("INFO: Initializing Local Ollama (qwen3-vl:4b)")
             base_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
             self.llm = ChatOllama(model="qwen3-vl:4b", temperature=0, base_url=base_url)

    def _invoke_with_retry(self, chain, input_data, max_retries=3, delay=20):
        for attempt in range(max_retries):
            try:
                return chain.invoke(input_data)
            except Exception as e:
                error_str = str(e)
                if "model_pending_deploy" in error_str or "503" in error_str:
                    print(f"WARNING: Model is warming up (Attempt {attempt+1}/{max_retries}). Waiting {delay}s...")
                    time.sleep(delay)
                else:
                    raise e
        raise Exception("Max retries exceeded for model inference")

    def extract_scopes(self, chunks: list[str]) -> dict:
        # Simplistic approach: Concatenate top chunks and ask LLM
        # For production: Map-Reduce or refinement loop
        context = "\n\n".join(chunks[:5]) # Limit context window
        
        prompt = ChatPromptTemplate.from_template("""
        You are a legal expert. Analyze the following policy text excerpts and determine if the following scopes apply (True/False).
        
        Scopes:
        - Registration: Appears to start collecting data upon user registration.
        - Legal: Data collected for legal compliance.
        - Customization: Data used to customize user experience.
        - Marketing: Data used for marketing purposes.
        - Security: Data used for security purposes.

        Policy Text:
        {context}

        Return ONLY a JSON object with keys: scope_registration, scope_legal, scope_customization, scope_marketing, scope_security.
        Values must be booleans.
        """)
        
        chain = prompt | self.llm | JsonOutputParser()
        
        try:
            return self._invoke_with_retry(chain, {"context": context})
        except Exception as e:
            print(f"Extraction error: {e}")
            # Fallback
            return {
                "scope_registration": False,
                "scope_legal": False,
                "scope_customization": False,
                "scope_marketing": False,
                "scope_security": False
            }

    def enrich_company_data(self, chunks: list[str], current_data: CompanyData) -> dict:
        context = "\n\n".join(chunks[:5])
        
        prompt = ChatPromptTemplate.from_template("""
        Extract the following information from the policy text if present:
        - generic_email
        - contact_email
        - privacy_email
        - delete_link (URL for account deletion)
        - country (Jurisdiction or address country)

        Policy Text:
        {context}

        Return a JSON object with these keys. If not found, use null.
        """)
        
        chain = prompt | self.llm | JsonOutputParser()
        
        try:
            enrichment = self._invoke_with_retry(chain, {"context": context})
            # Merge with existing data if new data is found
            # This logic can be refined
            return enrichment
        except Exception as e:
            print(f"Enrichment error: {e}")
            return {}
