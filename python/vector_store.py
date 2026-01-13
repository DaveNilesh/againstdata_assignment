import requests
import os
from qdrant_client import QdrantClient
from qdrant_client.http import models as rest
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    from langchain_community.embeddings import HuggingFaceEmbeddings

class VectorStore:
    def __init__(self):
        self.qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        self.client = QdrantClient(url=self.qdrant_url)
        self.collection_name = "policy_chunks"
        self.embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            self.client.get_collection(self.collection_name)
        except Exception:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=rest.VectorParams(
                    size=384,  # Dimension for all-MiniLM-L6-v2
                    distance=rest.Distance.COSINE,
                ),
            )

    def add_texts(self, texts: list[str], metadatas: list[dict]):
        embeddings = self.embeddings.embed_documents(texts)
        points = [
            rest.PointStruct(
                id=i,  # Ideally generate UUIDs
                vector=embedding,
                payload=metadata
            )
            for i, (embedding, metadata) in enumerate(zip(embeddings, metadatas))
        ]
        # In a real app, use UUIDs for IDs to avoid collisions on subsequent runs
        import uuid
        for p in points:
            p.id = str(uuid.uuid4())
            
        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )


    def search(self, query: str, limit: int = 5, filter_dict: dict = None):
        query_vector = self.embeddings.embed_query(query)
        
        # Raw HTTP search to avoid client version issues
        url = f"{self.qdrant_url}/collections/{self.collection_name}/points/search"
        
        payload = {
            "vector": query_vector,
            "limit": limit,
            "with_payload": True
        }
        
        if filter_dict:
             conditions = [
                {"key": k, "match": {"value": v}} 
                for k, v in filter_dict.items()
            ]
             payload["filter"] = {"must": conditions}

        try:
            resp = requests.post(url, json=payload)
            resp.raise_for_status()
            result = resp.json().get('result', [])
            
            # Wrap in object to match main.py expectation (h.payload['...'])
            class Hit:
                def __init__(self, data):
                    self.payload = data.get('payload', {})
                    self.score = data.get('score')
                    self.id = data.get('id')
            
            return [Hit(r) for r in result]
            
        except Exception as e:
            print(f"Error searching Qdrant: {e}")
            return []
