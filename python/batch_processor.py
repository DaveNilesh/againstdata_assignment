import pandas as pd
import time
import os
import io
import psycopg2
from psycopg2.extras import RealDictCursor

try:
    from .models import ProcessingRequest
    from .discovery import Discovery
    from .scraper import Scraper
    from .vector_store import VectorStore
    from .extractor import Extractor
except ImportError:
    from models import ProcessingRequest
    from discovery import Discovery
    from scraper import Scraper
    from vector_store import VectorStore
    from extractor import Extractor

class BatchProcessor:
    def __init__(self):
        # Initialize components once
        try:
            self.discovery = Discovery()
            self.scraper = Scraper()
            self.vector_store = VectorStore()
            self.extractor = Extractor()
        except Exception as e:
            print(f"Error initializing components in BatchProcessor: {e}")
            raise e

    def get_db_connection(self):
        return psycopg2.connect(os.getenv("DATABASE_URL"))

    def import_csv_to_db(self, csv_path: str):
        """
        Step 1: Read CSV and insert into DB with status 'pending'
        """
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        imported_count = 0
        try:
            # Handle path variants
            if not os.path.exists(csv_path):
                # Try relative to current file if running locally
                current_dir = os.path.dirname(os.path.abspath(__file__))
                alt_path = os.path.join(current_dir, csv_path)
                if os.path.exists(alt_path):
                    csv_path = alt_path
                # Check for just filename
                elif os.path.exists(os.path.basename(csv_path)):
                     csv_path = os.path.basename(csv_path)
            
            # Read CSV
            df = pd.read_csv(csv_path)

            for i, row in df.iterrows():
                domain = row.get('domain')
                company_id = str(row.get('id', ''))
                name = row.get('name', '')
                
                if not company_id and 'id' not in row:
                    company_id = f"auto_{int(time.time())}_{i}"

                if not domain or pd.isna(domain):
                    continue

                # Insert with pending status
                # If already exists and NOT completed/failed, ensure it's pending? 
                # Or just ignore if exists? Let's ignore if exists to avoid resetting state inadvertently,
                # unless status is null.
                cursor.execute("""
                    INSERT INTO companies (id, name, domain, status) 
                    VALUES (%s, %s, %s, 'pending') 
                    ON CONFLICT (id) DO NOTHING
                """, (company_id, name, domain))
                # For this assignment, "DO NOTHING" is safer than overwriting status which might be 'completed'
                
                imported_count += 1
            
            conn.commit()
            return {
                "status": "completed",
                "message": f"Imported {imported_count} companies from CSV",
                "imported_count": imported_count
            }

        except Exception as e:
            conn.rollback()
            return {
                "status": "failed",
                "message": f"Error importing CSV: {str(e)}",
                "imported_count": imported_count
            }
        finally:
            cursor.close()
            conn.close()

    def process_pending_companies(self, limit: int = 5):
        """
        Step 2: Read 'pending' companies from DB and process them
        """
        start_time = time.time()
        conn = self.get_db_connection()
        # Use RealDictCursor to get column names
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        try:
            # Fetch pending records with locking to prevent race conditions if multiple workers ran
            cursor.execute("SELECT id, name, domain FROM companies WHERE status = 'pending' LIMIT %s FOR UPDATE SKIP LOCKED", (limit,))
            rows = cursor.fetchall()
            
            if not rows:
                return {
                    "status": "completed", 
                    "message": "No pending companies found",
                    "total_processed": 0,
                    "details": []
                }

            results = []
            successful_count = 0
            failed_count = 0

            for row in rows:
                company_id = row['id']
                domain = row['domain']
                name = row['name']
                
                item_result = {
                    "id": company_id,
                    "domain": domain,
                    "status": "processing",
                    "error": None
                }
                
                # Switch processing status immediately or just process?
                # Since we have the lock, we can process.
                
                try:
                    # Pass the EXISTING connection/cursor to avoid deadlock and ensuring atomicity
                    # Actually _process_single_domain uses normal cursor, we have RealDictCursor.
                    # Mix is fine, or we create a standard cursor from the same connection.
                    std_cursor = conn.cursor()
                    
                    self._process_single_domain(company_id, name, domain, item_result, conn, std_cursor)
                    
                    # Update status to completed
                    std_cursor.execute("UPDATE companies SET status = 'completed', processed_at = NOW() WHERE id = %s", (company_id,))
                    std_cursor.close() # Close inner cursor
                    
                    # Commit transaction for this item (or batch? batch is better for performance but item is safer for partial progress)
                    # Let's commit per item so we release locks and progress is saved even if next item crashes
                    conn.commit()
                    
                    item_result['status'] = 'completed'
                    successful_count += 1
                    
                except Exception as e:
                    conn.rollback() # Rollback ANY partial changes for this item
                    print(f"Error processing {domain}: {e}")
                    
                    # New transaction to record failure
                    try:
                         fail_cursor = conn.cursor()
                         fail_cursor.execute("UPDATE companies SET status = 'failed', error_message = %s WHERE id = %s", (str(e), company_id))
                         conn.commit()
                         fail_cursor.close()
                    except:
                        pass

                    item_result['status'] = 'failed'
                    item_result['error'] = str(e)
                    failed_count += 1
                
                results.append(item_result)

            return {
                "status": "completed",
                "message": f"Processed {len(rows)} companies",
                "total_processed": len(rows),
                "successful": successful_count,
                "failed": failed_count,
                "processing_time_seconds": round(time.time() - start_time, 2),
                "details": results
            }

        finally:
            cursor.close()
            conn.close()

    def _process_single_domain(self, company_id, name, domain, result_tracker, conn=None, cursor=None):
        should_close_conn = False
        if conn is None:
            conn = self.get_db_connection()
            should_close_conn = True
        
        if cursor is None:
            cursor = conn.cursor()
            should_close_cursor = True
        else:
            should_close_cursor = False
        
        try:
             # If called independently (not from batch loop), ensure company exists
            if should_close_conn:
                cursor.execute("INSERT INTO companies (id, name, domain) VALUES (%s, %s, %s) ON CONFLICT (id) DO NOTHING",
                            (company_id, name, domain))
                conn.commit()

            # 1. Discovery
            links = self.discovery.find_policy_links(domain)
            result_tracker['privacy_url'] = links.get('privacy')
            result_tracker['terms_url'] = links.get('terms')
            
            # Save links
            for p_type, url in links.items():
                if url:
                    cursor.execute("INSERT INTO policy_pages (company_id, page_type, url) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                                (company_id, p_type, url))
            
            # If we own connection, commit intermediate steps? No, keep it atomic preferably.
            # But scraper is slow, so maybe not hold DB lock for scraping if possible?
            # Creating vectors doesn't need DB lock.
            # But inserting into policy_pages does.
            
            # 2. Scrape & Vectorize (Long running, non-DB)
            all_text_chunks = []
            for p_type, url in links.items():
                if url:
                    text = self.scraper.fetch_page(url)
                    if text:
                        clean_text = self.scraper.clean_text(text)
                        chunks = self.scraper.chunk_text(clean_text)
                        all_text_chunks.extend(chunks)
                        
                        metadatas = [{"domain": domain, "type": p_type, "url": url, "text": chunk} for chunk in chunks]
                        self.vector_store.add_texts(chunks, metadatas)
            
            # 3. Extract Scopes
            scopes_found_count = 0
            if all_text_chunks:
                scopes = self.extractor.extract_scopes(all_text_chunks)
                scopes_found_count = sum(1 for k, v in scopes.items() if v is True)
                
                cursor.execute("""
                    INSERT INTO policy_scopes (company_id, scope_registration, scope_legal, scope_customization, scope_marketing, scope_security)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (company_id) DO UPDATE SET
                    scope_registration = EXCLUDED.scope_registration,
                    scope_legal = EXCLUDED.scope_legal,
                    scope_customization = EXCLUDED.scope_customization,
                    scope_marketing = EXCLUDED.scope_marketing,
                    scope_security = EXCLUDED.scope_security
                """, (company_id, scopes.get('scope_registration'), scopes.get('scope_legal'), 
                    scopes.get('scope_customization'), scopes.get('scope_marketing'), scopes.get('scope_security')))
            
            result_tracker['scopes_found'] = scopes_found_count

            # 4. Enrich
            emails_found_count = 0
            if all_text_chunks:
                enrichment = self.extractor.enrich_company_data(all_text_chunks, None)
                if enrichment:
                    if enrichment.get('generic_email'): emails_found_count += 1
                    if enrichment.get('contact_email'): emails_found_count += 1
                    if enrichment.get('privacy_email'): emails_found_count += 1

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
                        enrichment.get('country'), company_id))
            
            result_tracker['emails_found'] = emails_found_count
            
            # Log completion
            cursor.execute("INSERT INTO processing_log (company_id, step, status, message) VALUES (%s, 'batch_complete', 'completed', 'Finished batch processing step')",
                           (company_id,))
            
            if should_close_conn:
                conn.commit()

        finally:
            if should_close_cursor:
                cursor.close()
            if should_close_conn:
                conn.close()
