import os
import sys

# Ensure imports work whether run from root or python dir
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

try:
    from batch_processor import BatchProcessor
except ImportError:
    # Try importing assuming we are in the parent package context
    from python.batch_processor import BatchProcessor

if __name__ == "__main__":
    # Local config
    os.environ["DATABASE_URL"] = "postgresql://user:password@localhost:5432/policy_db" 
    os.environ["QDRANT_URL"] = "http://localhost:6333"
    
    # Path to CSV - default to the one in python dir
    csv_file = os.path.join(current_dir, "List1.csv")
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    
    print(f"Running batch processor locally with CSV: {csv_file}")
    
    try:
        processor = BatchProcessor()
        result = processor.process_batch(csv_file, batch_size=5)
        import json
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Run failed: {e}")
