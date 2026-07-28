import os
import re
import math
import json
import io
import concurrent.futures
import requests

class SimpleTFIDF:
    """A lightweight, pure-Python TF-IDF indexer for retrieving relevant PDF pages."""
    def __init__(self):
        self.documents = []  # list of dicts: {id, text, source, page}
        self.vocab = set()
        self.idf = {}
        self.doc_tfs = []  # list of term frequency dicts for each document
        self.stopwords = {
            'a', 'about', 'above', 'after', 'again', 'against', 'all', 'am', 'an', 'and', 'any', 'are', 'arent',
            'as', 'at', 'be', 'because', 'been', 'before', 'being', 'below', 'between', 'both', 'but', 'by', 'cant',
            'cannot', 'could', 'couldnt', 'did', 'didnt', 'do', 'does', 'doesnt', 'doing', 'dont', 'down', 'during',
            'each', 'few', 'for', 'from', 'further', 'had', 'hadnt', 'has', 'hasnt', 'have', 'havent', 'having',
            'he', 'hed', 'hell', 'hes', 'her', 'here', 'heres', 'hers', 'herself', 'him', 'himself', 'his', 'how',
            'hows', 'i', 'id', 'ill', 'im', 'ive', 'if', 'in', 'into', 'is', 'isnt', 'it', 'its', 'itself', 'lets',
            'me', 'more', 'most', 'mustnt', 'my', 'myself', 'no', 'nor', 'not', 'of', 'off', 'on', 'once', 'only',
            'or', 'other', 'ought', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'same', 'shant', 'she', 'shed',
            'shell', 'shes', 'should', 'shouldnt', 'so', 'some', 'such', 'than', 'that', 'thats', 'the', 'their',
            'theirs', 'them', 'themselves', 'then', 'there', 'theres', 'these', 'they', 'theyd', 'theyll', 'theyre',
            'theyve', 'this', 'those', 'through', 'to', 'too', 'under', 'until', 'up', 'very', 'was', 'wasnt',
            'we', 'wed', 'well', 'were', 'weve', 'werent', 'what', 'whats', 'when', 'whens', 'where', 'wheres',
            'which', 'while', 'who', 'whos', 'whom', 'why', 'whys', 'with', 'wont', 'would', 'wouldnt', 'you',
            'youd', 'youll', 'youre', 'youve', 'your', 'yours', 'yourself', 'yourselves'
        }

    def _tokenize(self, text):
        # Lowercase and extract alphanumeric words
        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if w not in self.stopwords and len(w) > 1]

    def add_document(self, doc_id, text, source, page):
        tokens = self._tokenize(text)
        if not tokens:
            return
        
        tf = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
            self.vocab.add(token)
            
        # Normalize TF by document length
        length = len(tokens)
        normalized_tf = {k: v / length for k, v in tf.items()}
        
        self.documents.append({
            'id': doc_id,
            'text': text,
            'source': source,
            'page': page
        })
        self.doc_tfs.append(normalized_tf)

    def calculate_idf(self):
        n_docs = len(self.documents)
        if n_docs == 0:
            return
        
        # Count document frequency
        df = {}
        for tf in self.doc_tfs:
            for term in tf:
                df[term] = df.get(term, 0) + 1
                
        # Calculate IDF
        self.idf = {}
        for term, freq in df.items():
            self.idf[term] = math.log(1 + (n_docs / freq))

    def search(self, query, top_k=5):
        query_tokens = self._tokenize(query)
        if not query_tokens or not self.documents:
            return []
            
        scores = []
        for idx, doc in enumerate(self.documents):
            score = 0.0
            doc_tf = self.doc_tfs[idx]
            for token in query_tokens:
                if token in doc_tf:
                    # TF-IDF score contribution
                    score += doc_tf[token] * self.idf.get(token, 0.0)
            
            # Simple keyword match boosting
            matches = sum(1 for token in query_tokens if token in doc_tf)
            match_ratio = matches / len(query_tokens)
            score += match_ratio * 0.5  # boost score for high coverage of terms
            
            if score > 0:
                scores.append((idx, score))
                
        # Sort by score descending
        scores.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for doc_idx, score in scores[:top_k]:
            doc = self.documents[doc_idx]
            results.append({
                'id': doc['id'],
                'text': doc['text'],
                'source': doc['source'],
                'page': doc['page'],
                'score': score
            })
        return results

class RAGEngine:
    def __init__(self, pdf_dir):
        self.pdf_dir = pdf_dir
        self.retriever = SimpleTFIDF()
        self.indexed = False
        self.metadata = {}

    def serialize(self):
        """Return a JSON-safe dict of the TF-IDF index + metadata.

        Shared by both on-disk persistence (save_index) and the durable
        session store (KV), so there is a single source of truth for the
        wire format.
        """
        return {
            "documents": self.retriever.documents,
            "doc_tfs": self.retriever.doc_tfs,
            "idf": self.retriever.idf,
            "vocab": list(self.retriever.vocab),
            "metadata": self.metadata,
        }

    def hydrate(self, payload):
        """Rebuild the in-memory index from a serialize() payload."""
        self.retriever.documents = payload["documents"]
        self.retriever.doc_tfs = payload["doc_tfs"]
        self.retriever.idf = payload["idf"]
        self.retriever.vocab = set(payload.get("vocab", []))
        self.metadata = payload.get("metadata", {})
        self.indexed = len(self.retriever.documents) > 0
        return self.indexed

    def save_index(self, path):
        """Serialize the TF-IDF index + metadata to a JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.serialize(), f)

    def load_index(self, path):
        """Hydrate the TF-IDF index from a pre-built JSON file (fast cold start)."""
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return self.hydrate(payload)

    def extract_and_index(self):
        """Extract text from the two specified PDFs and build the TF-IDF index."""
        import pdfplumber  # lazy: only needed at build time, not in serverless runtime
        if not os.path.exists(self.pdf_dir):
            raise FileNotFoundError(f"PDF directory {self.pdf_dir} does not exist.")

        pdf_files = [f for f in os.listdir(self.pdf_dir) if f.endswith('.pdf')]
        doc_count = 0
        total_pages = 0
        
        for pdf_file in pdf_files:
            pdf_path = os.path.join(self.pdf_dir, pdf_file)
            print(f"Indexing {pdf_file}...")
            
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    pages_in_pdf = len(pdf.pages)
                    total_pages += pages_in_pdf
                    doc_count += 1
                    
                    for page_idx, page in enumerate(pdf.pages):
                        text = page.extract_text()
                        if text:
                            # 1-based page index
                            page_num = page_idx + 1
                            doc_id = f"{pdf_file}_p{page_num}"
                            self.retriever.add_document(doc_id, text, pdf_file, page_num)
                            
                self.metadata[pdf_file] = {
                    'pages': pages_in_pdf,
                    'size': os.path.getsize(pdf_path)
                }
            except Exception as e:
                print(f"Error processing {pdf_file}: {e}")
                
        self.retriever.calculate_idf()
        self.indexed = len(self.retriever.documents) > 0
        print(f"Indexing complete! Indexed {len(self.retriever.documents)} pages across {doc_count} files.")
        return self.indexed

    def index_pdf_stream(self, filename, file_obj):
        """Extract text from an uploaded PDF stream into this engine."""
        import pdfplumber

        filename = os.path.basename(filename)
        page_count = 0
        indexed_pages = 0
        size = 0

        raw = file_obj.read()
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        size = len(raw)

        with pdfplumber.open(io.BytesIO(raw)) as pdf:
            page_count = len(pdf.pages)
            for page_idx, page in enumerate(pdf.pages):
                text = page.extract_text()
                if text:
                    page_num = page_idx + 1
                    doc_id = f"{filename}_p{page_num}"
                    self.retriever.add_document(doc_id, text, filename, page_num)
                    indexed_pages += 1

        if indexed_pages == 0:
            raise ValueError(f"No extractable text found in {filename}.")

        self.metadata[filename] = {
            'pages': page_count,
            'size': size
        }
        self.retriever.calculate_idf()
        self.indexed = len(self.retriever.documents) > 0
        return self.metadata[filename]
    def expand_query(self, user_query, api_key):
        """Pre-Retrieval: Query Expansion using Gemini."""
        if not api_key:
            return [user_query]
            
        prompt = f"""Given the user's question, expand it into three search-friendly queries. Generate exact keyword matches, synonyms, and variations related to the core topic. Return the results as a clean, comma-separated list.
User Question: "{user_query}"
"""
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            data = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            response = requests.post(url, headers=headers, json=data, timeout=10)
            if response.status_code == 200:
                res_json = response.json()
                text = res_json['candidates'][0]['content']['parts'][0]['text']
                # Split by comma and clean up
                expanded = [q.strip() for q in text.split(',') if q.strip()]
                # Ensure the original query is in the list
                queries = [user_query]
                for q in expanded:
                    # Clean punctuation
                    q_clean = re.sub(r'^[0-9\.\-\*\s]+', '', q) # remove lists like 1. or *
                    if q_clean and q_clean.lower() != user_query.lower():
                        queries.append(q_clean)
                return list(dict.fromkeys(queries))[:4] # limit to original + 3 expansions
        except Exception as e:
            print(f"Query expansion failed: {e}")
            
        return [user_query]

    def filter_and_rerank(self, user_query, candidates, api_key):
        """Post-Retrieval: Filtering and Reranking using Relevance Detection Prompt."""
        if not api_key or not candidates:
            return candidates

        filtered = []
        
        # System relevance filter helper function
        def evaluate_relevance(candidate):
            context = candidate['text']
            prompt = f"""System: You are an expert data filter. Evaluate the retrieved context pieces. If the context is completely unrelated to the user's question, reply with exactly: "I cannot find the answer in the provided context."
User Question: "{user_query}"
Retrieved Context: "{context}"
"""
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
                headers = {"Content-Type": "application/json"}
                data = {
                    "contents": [{"parts": [{"text": prompt}]}]
                }
                response = requests.post(url, headers=headers, json=data, timeout=8)
                if response.status_code == 200:
                    res_json = response.json()
                    res_text = res_json['candidates'][0]['content']['parts'][0]['text'].strip()
                    # Check if response matches the failure string
                    if "cannot find the answer" in res_text.lower():
                        return None
                    return candidate
            except Exception as e:
                print(f"Relevance filter error for {candidate['id']}: {e}")
            return candidate  # fallback: keep in case of api error

        # Run filtering in parallel to save time
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(evaluate_relevance, candidates))
            filtered = [r for r in results if r is not None]
            
        return filtered

    def query(self, user_query, api_key, model="gemini-2.5-flash", mode="classic", top_k=5, use_filter=True, use_expansion=True, extra_retrievers=None):
        """Run the full RAG pipeline."""
        if not self.indexed:
            self.extract_and_index()
            
        if not self.indexed:
            return {"error": "No documents indexed."}
            
        # 1. Pre-Retrieval: Query Expansion
        expanded_queries = [user_query]
        if use_expansion and api_key:
            expanded_queries = self.expand_query(user_query, api_key)
            
        print(f"Queries for retrieval: {expanded_queries}")

        # 2. Retrieval: Multi-Query Search and fusion across base + session indexes
        all_candidates = []
        seen_ids = set()
        retrievers = [self.retriever]
        if extra_retrievers:
            retrievers.extend(extra_retrievers)

        for q in expanded_queries:
            for retriever in retrievers:
                results = retriever.search(q, top_k=top_k)
                for r in results:
                    candidate_key = f"{r['source']}::{r['id']}"
                    if candidate_key not in seen_ids:
                        seen_ids.add(candidate_key)
                        all_candidates.append(r)

        all_candidates.sort(key=lambda x: x['score'], reverse=True)
        candidates = all_candidates[:top_k]
        
        # 3. Post-Retrieval: Filtering & Reranking
        active_candidates = candidates
        if use_filter and api_key and len(candidates) > 0:
            active_candidates = self.filter_and_rerank(user_query, candidates, api_key)
            
        # If all candidates got filtered out, fallback to original candidates to prevent empty context
        if not active_candidates and candidates:
            active_candidates = candidates[:3]

        # Prepare context
        context_pieces = []
        for c in active_candidates:
            context_pieces.append(f"Source: {c['source']}, Page: {c['page']}\nContent: {c['text']}\n---")
        context_str = "\n".join(context_pieces)

        # 4. Generation: Select RAG Prompt based on Mode
        if not api_key:
            return {
                "answer": "RAG Backend retrieved relevant context, but no Gemini API key is configured. Please enter your API key in the settings panel to generate a finalized answer.",
                "context": active_candidates,
                "queries": expanded_queries,
                "api_key_required": True
            }

        prompt = ""
        system_instruction = ""
        
        if mode == "classic":
            # Strict Grounding & Citation Prompt
            system_instruction = "You are a helpful AI assistant. You must answer the user's question using ONLY the provided retrieved context. Do not use your pre-trained knowledge."
            prompt = f"""{system_instruction}

If the answer cannot be found in the context, say exactly: "I am sorry, but I do not have enough information to answer that question based on the provided documents."

Rules for formatting:
1. Every major claim must be cited directly using the exact source name provided in the context.
2. Format citations as [Source Name, Page X].
3. Maintain a highly professional and factual tone.

User Question: "{user_query}"
Retrieved Context: "{context_str}"
Response:"""

        elif mode == "auditor":
            # Grounding for Multi-PDF Analysis (Auditor)
            system_instruction = "You are an elite corporate auditor executing strict document analysis."
            prompt = f"""{system_instruction}
You are provided with several confidential PDF documents attached directly to your context.

CRITICAL RULES:
1. Grounding: Answer the user's inquiry using ONLY the data explicitly provided within the uploaded documents. Do not assume, extrapolate, or use outside training data.
2. Missing Information: If the answer cannot be found or verified across the documents, state exactly: "CRITICAL: The provided documents do not contain sufficient data to answer this query."
3. Citations: You must trace every claim, metric, or conclusion back to its specific source document. Append the filename and page number in brackets, for example: [Q2_Report.pdf, Page 14].

User Query: "{user_query}"
Retrieved Context: "{context_str}"
Answer:"""

        elif mode == "cot":
            # Advanced Reasoning & Chain of Thought
            system_instruction = "You are an expert analyst. Think step-by-step through the retrieved context to answer the user's question. First, identify the key pieces of evidence. Second, logically deduce the answer. Third, synthesize the response."
            prompt = f"""{system_instruction}

User Question: "{user_query}"
Context: "{context_str}"
Thought Process: Let's think step by step to ensure the final answer is complete"""

        # Call Gemini model
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            
            # Setup generation configs
            data = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.1 if mode != "cot" else 0.4,
                    "maxOutputTokens": 2048
                }
            }
            
            # Add system instruction as parameter if supported/needed, otherwise we keep it in prompt
            response = requests.post(url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                res_json = response.json()
                answer_text = res_json['candidates'][0]['content']['parts'][0]['text']
                
                thought_process = ""
                # Parse thought process if Chain of Thought mode
                if mode == "cot":
                    # Prefix the thought process we forced in prompt
                    full_text = "Let's think step by step to ensure the final answer is complete" + answer_text
                    
                    # Split into thought process and final response if synthesized clearly
                    split_markers = ["synthesis:", "therefore,", "final answer:", "response:", "answer:"]
                    split_idx = -1
                    matched_marker = ""
                    
                    for marker in split_markers:
                        idx = full_text.lower().rfind(marker)
                        if idx > split_idx:
                            split_idx = idx
                            matched_marker = marker
                            
                    if split_idx != -1:
                        thought_process = full_text[:split_idx].strip()
                        answer_text = full_text[split_idx + len(matched_marker):].strip()
                    else:
                        thought_process = full_text
                        
                return {
                    "answer": answer_text,
                    "thought_process": thought_process,
                    "context": active_candidates,
                    "queries": expanded_queries,
                    "model": model,
                    "mode": mode
                }
            else:
                error_msg = f"API Error (Status {response.status_code}): {response.text}"
                print(error_msg)
                return {"error": error_msg}
                
        except Exception as e:
            error_msg = f"Request to Gemini failed: {str(e)}"
            print(error_msg)
            return {"error": error_msg}

