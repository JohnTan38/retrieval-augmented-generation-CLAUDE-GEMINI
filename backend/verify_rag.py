import os
import sys

# Add backend directory to path
sys.path.append(os.path.dirname(__file__))

from rag_engine import RAGEngine

def test_rag():
    print("=== Singapore Social Services RAG Engine Test ===")
    
    # Path to PDFs
    pdf_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "public", "assets"))
    print(f"PDF Directory: {pdf_dir}")
    
    if not os.path.exists(pdf_dir):
        print(f"ERROR: PDF directory does not exist at {pdf_dir}!")
        return
        
    # Initialize engine
    rag = RAGEngine(pdf_dir)
    
    # Index documents
    print("\nRunning PDF Text Extraction and Indexing...")
    success = rag.extract_and_index()
    if not success:
        print("ERROR: Indexing failed!")
        return
        
    print(f"\nIndexing Succeeded!")
    print(f"Total chunks indexed: {len(rag.retriever.documents)}")
    print("\nDocument metadata:")
    for file, meta in rag.metadata.items():
        print(f"  - {file}: {meta['pages']} pages, {meta['size'] / 1024:.1f} KB")
        
    # Run test search
    test_queries = [
        "communal dining",
        "befriending and buddying eligibility",
        "CASHEW model pillars"
    ]
    
    for q in test_queries:
        print(f"\n--- Testing retrieval for query: '{q}' ---")
        results = rag.retriever.search(q, top_k=3)
        if not results:
            print("  No matches found.")
            continue
            
        for i, r in enumerate(results):
            snippet = r['text'][:150].replace('\n', ' ')
            # Clean snippet for windows console print compatibility
            snippet_safe = snippet.encode('ascii', errors='replace').decode('ascii')
            print(f"  [{i+1}] Source: {r['source']}, Page: {r['page']}, Score: {r['score']:.4f}")
            print(f"      Snippet: {snippet_safe}...")
            
    print("\n=== RAG Local Retrieval Test Passed! ===")

if __name__ == "__main__":
    test_rag()
