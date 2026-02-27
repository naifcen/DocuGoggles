# src/file_search/search/meili_search_client.py

from meilisearch import Client
from typing import List, Dict, Optional


class MeiliSearchClient:
    def __init__(self, host: str = "http://127.0.0.1:7700", api_key: Optional[str] = "masterKey"):
        self.client = Client(host, api_key)
        self.index_name = "documents"

        # Check if index exists more reliably
        try:
            self.index = self.client.get_index(self.index_name)
            # print(f"Using existing Meilisearch index: {self.index_name}")
        except Exception as e: # Meilisearch typically raises an error if index not found
            # print(f"Index '{self.index_name}' not found ({e}), attempting to create...")
            try:
                # Pass primaryKey within an options dictionary
                self.client.create_index(uid=self.index_name, options={'primaryKey': 'id'})
                print(f"Created new Meilisearch index: {self.index_name}")
                self.index = self.client.index(self.index_name)
            except Exception as create_error:
                print(f"Failed to create index '{self.index_name}': {create_error}")
                raise  # Re-raise if creation fails

    def index_documents(self, documents: List[Dict]):
        """Index documents into Meilisearch."""
        if not documents:
            print("No documents to index.")
            return
        try:
            result = self.index.add_documents(documents)
            print(f"Successfully indexed {len(documents)} documents.")
            return result
        except Exception as e:
            print(f"Indexing error: {e}")
            return None

    def search(self, query: str, filters: Optional[str] = None) -> List[Dict]:
        """Search the Meilisearch index."""
        try:
            params = {"q": query}
            if filters:
                params["filter"] = filters
            results = self.index.search(**params)
            return results.get("hits", [])
        except Exception as e:
            print(f"Search failed: {e}")
            return []
