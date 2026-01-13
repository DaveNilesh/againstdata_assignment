import csv
import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from pydantic import BaseModel

# Imports adapted for running as a script in the same directory
try:
    from models import ProcessingRequest
    from discovery import Discovery
    from scraper import Scraper
    from vector_store import VectorStore
    from extractor import Extractor
except ImportError:
    # Fallback if running from parent directory or different context
    from .models import ProcessingRequest
    from .discovery import Discovery
    from .scraper import Scraper
    from .vector_store import VectorStore
    from .extractor import Extractor

# Configuration
CSV_FILE = "List1.csv"
BATCH_SIZE = 5

def get_db_connection():
    return psycopg2.connect(os.getenv("DATABASE_URL"))

print("Initializing components...")
discovery = Discovery()
scraper = Scraper()
vector_store = VectorStore()
# Extractor might be heavy (LLM init), so we init it once
extractor = Extractor()
print("Components initialized.")

def process_row(row_data):
    """
    Replicates the logic from main.py's process_domain_task
    """
    # Create request object similar to API
    # CSV headers: id,name,generic_email, etc...
    # We mainly need id, name, domain
    
    company_id = row_data.get('id')
    name = row_data.get('name')
    domain = row_data.get('domain')
    
    if not domain:
        print(f"Skipping row {row_data}: No domain provided")
        return

    request = ProcessingRequest(id=company_id, name=name, domain=domain)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        print(f"Processing {request.domain}...")
        
        # Ensure company exists
        cursor.execute("INSERT INTO companies (id, name, domain) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                     (request.id, request.name, request.domain))
        conn.commit()

        # Log start
        cursor.execute("INSERT INTO processing_log (company_id, step, status, message) VALUES (%s, %s, %s, %s)", 
                       (request.id, 'start', 'running', 'Started processing from script'))
        conn.commit()

        # 1. Discovery
        links = discovery.find_policy_links(request.domain)
        cursor.execute("INSERT INTO processing_log (company_id, step, status, message) VALUES (%s, %s, %s, %s)",
                       (request.id, 'discovery', 'completed', f"Found: {links}"))
        
        for p_type, url in links.items():
            if url:
                cursor.execute("INSERT INTO policy_pages (company_id, page_type, url) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                               (request.id, p_type, url))
        conn.commit()

        # 2. Scrape & Vectorize
        all_text_chunks = []
        for p_type, url in links.items():
            if url:
                try:
                    text = scraper.fetch_page(url)
                    clean_text = scraper.clean_text(text)
                    chunks = scraper.chunk_text(clean_text)
                    all_text_chunks.extend(chunks)
                    
                    metadatas = [{"domain": request.domain, "type": p_type, "url": url, "text": chunk} for chunk in chunks]
                    vector_store.add_texts(chunks, metadatas)
                except Exception as e:
                    print(f"  Error scraping {url}: {e}")

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
        print(f"Finished {request.domain}")

    except Exception as e:
        print(f"Error processing {request.domain}: {e}")
        cursor.execute("INSERT INTO processing_log (company_id, step, status, message) VALUES (%s, %s, %s, %s)",
                       (request.id, 'error', 'failed', str(e)))
        conn.commit()
    finally:
        cursor.close()
        conn.close()

def main():
    if not os.path.exists(CSV_FILE):
        print(f"Error: {CSV_FILE} not found in current directory.")
        return

    print("Reading CSV...")
    with open(CSV_FILE, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        print(f"Found {len(rows)} rows.")
        
        for i, row in enumerate(rows):
            process_row(row)
            # Basic rate limiting
            if (i + 1) % BATCH_SIZE == 0:
                print("Batch pause (2s)...")
                time.sleep(2)

if __name__ == "__main__":
    main()
