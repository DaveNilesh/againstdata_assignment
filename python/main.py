from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import RealDictCursor
import os
from models import ProcessingRequest, ProcessingResponse
from discovery import Discovery
from scraper import Scraper
from vector_store import VectorStore
from extractor import Extractor


app = FastAPI()

# Database connection
def get_db_connection():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    return conn

# Initialize components
discovery = Discovery()
scraper = Scraper()
vector_store = VectorStore()
extractor = Extractor() # This might be heavy to init

# NOTE: process_domain_task below is legacy (for single domain /api/process-domain).
# The new BatchProcessor has its own internal logic.
# We can keep this for backward compatibility or individual testing.

def process_domain_task(request: ProcessingRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print(f"Processing {request.domain}")
        # Log start
        cursor.execute("INSERT INTO processing_log (company_id, step, status, message) VALUES (%s, %s, %s, %s)", 
                       (request.id, 'start', 'running', 'Started processing'))
        conn.commit()

        # 1. Discovery
        links = discovery.find_policy_links(request.domain)
        cursor.execute("INSERT INTO processing_log (company_id, step, status, message) VALUES (%s, %s, %s, %s)",
                       (request.id, 'discovery', 'completed', f"Found: {links}"))
        
        # Save links
        for p_type, url in links.items():
            if url:
                cursor.execute("INSERT INTO policy_pages (company_id, page_type, url) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                               (request.id, p_type, url))
        conn.commit()

        # 2. Scrape & Vectorize
        all_text_chunks = []
        for p_type, url in links.items():
            if url:
                text = scraper.fetch_page(url)
                clean_text = scraper.clean_text(text)
                chunks = scraper.chunk_text(clean_text)
                all_text_chunks.extend(chunks)
                
                # Store vectors
                metadatas = [{"domain": request.domain, "type": p_type, "url": url, "text": chunk} for chunk in chunks]
                vector_store.add_texts(chunks, metadatas)
        
        if not all_text_chunks:
             cursor.execute("INSERT INTO processing_log (company_id, step, status, message) VALUES (%s, %s, %s, %s)",
                       (request.id, 'scraping', 'failed', 'No content found'))
             conn.commit()
             return

        # 3. Extract Scopes
        scopes = extractor.extract_scopes(all_text_chunks)
        cursor.execute("""
            INSERT INTO policy_scopes (company_id, scope_registration, scope_legal, scope_customization, scope_marketing, scope_security)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (company_id) DO UPDATE SET
            scope_registration = EXCLUDED.scope_registration,
            scope_legal = EXCLUDED.scope_legal,
            scope_customization = EXCLUDED.scope_customization,
            scope_marketing = EXCLUDED.scope_marketing,
            scope_security = EXCLUDED.scope_security
        """, (request.id, scopes.get('scope_registration'), scopes.get('scope_legal'), 
              scopes.get('scope_customization'), scopes.get('scope_marketing'), scopes.get('scope_security')))
        
        # 4. Enrich Data
        enrichment = extractor.enrich_company_data(all_text_chunks, None)
        # Update companies table (simplified)
        if enrichment:
             cursor.execute("""
                UPDATE companies SET
                generic_email = COALESCE(%s, generic_email),
                contact_email = COALESCE(%s, contact_email),
                privacy_email = COALESCE(%s, privacy_email),
                delete_link = COALESCE(%s, delete_link),
                country = COALESCE(%s, country)
                WHERE id = %s
             """, (enrichment.get('generic_email'), enrichment.get('contact_email'), 
                   enrichment.get('privacy_email'), enrichment.get('delete_link'), 
                   enrichment.get('country'), request.id))

        cursor.execute("INSERT INTO processing_log (company_id, step, status, message) VALUES (%s, %s, %s, %s)",
                       (request.id, 'complete', 'completed', 'Finished processing'))
        conn.commit()

    except Exception as e:
        print(f"Error: {e}")
        cursor.execute("INSERT INTO processing_log (company_id, step, status, message) VALUES (%s, %s, %s, %s)",
                       (request.id, 'error', 'failed', str(e)))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

@app.post("/api/process-domain")
async def process_domain(request: ProcessingRequest, background_tasks: BackgroundTasks):
    # Ensure company exists in DB (or create if not)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO companies (id, name, domain) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                (request.id, request.name, request.domain))
    conn.commit()
    cur.close()
    conn.close()

    background_tasks.add_task(process_domain_task, request)
    return {"status": "accepted", "message": f"Processing started for {request.domain}"}

class ChatRequest(BaseModel):
    query: str

@app.post("/api/chat")
def chat(req: ChatRequest):
    # RAG Logic
    # 1. Search Vector Store
    hits = vector_store.search(req.query, limit=3)
    context = "\n\n".join([h.payload['text'] for h in hits])
    sources = [{"domain": h.payload['domain'], "url": h.payload['url'], "type": h.payload['type']} for h in hits]
    
    # 2. Ask LLM
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser
    
    prompt = ChatPromptTemplate.from_template("""
    Answer the user's question based on the following policy excerpts.
    If the answer is not in the text, say you don't know.
    
    Context:
    {context}
    
    Question: {question}
    """)
    
    chain = prompt | extractor.llm | StrOutputParser()
    try:
        answer = chain.invoke({"context": context, "question": req.query})
        return {"answer": answer, "sources": sources}
    except Exception as e:
        return {"answer": "Sorry, I encountered an error.", "error": str(e)}

class ImportRequest(BaseModel):
    csv_path: str

class PendingProcessRequest(BaseModel):
    limit: int = 5

@app.post("/api/import-csv")
def import_csv(req: ImportRequest):
    from batch_processor import BatchProcessor
    processor = BatchProcessor()
    return processor.import_csv_to_db(req.csv_path)

@app.post("/api/process-pending")
def process_pending(req: PendingProcessRequest):
    from batch_processor import BatchProcessor
    processor = BatchProcessor()
    return processor.process_pending_companies(req.limit)

# Kept for backward compatibility if needed, but implementation redirects to new logic or similar
@app.post("/api/batch-process")
def batch_process_legacy(req: ImportRequest):
    # This was originally doing both. Now strict separation is requested.
    # We can make it do both sequentially for backward compat?
    # Or just deprecate. Let's make it do Import + Process(5) for simple test
    from batch_processor import BatchProcessor
    processor = BatchProcessor()
    import_res = processor.import_csv_to_db(req.csv_path)
    if import_res['status'] != 'completed':
        return import_res
    
    # Process some
    process_res = processor.process_pending_companies(limit=5)
    return {
        "import_summary": import_res,
        "process_summary": process_res
    }


@app.get("/health")
def health():
    return {"status": "ok"}
