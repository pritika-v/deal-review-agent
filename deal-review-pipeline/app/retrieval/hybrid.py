from __future__ import annotations
import os, re, math
from typing import Iterable
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer, CrossEncoder
import chromadb
from app.models.schemas import DocumentChunk, Evidence

class HybridRetriever:
    def __init__(self, chunks: list[DocumentChunk], collection_name: str, persist_path: str='data/chroma'):
        self.chunks=chunks
        self.texts=[c.text for c in chunks]
        self.bm25=BM25Okapi([re.findall(r'\w+', t.lower()) for t in self.texts])
        self.embedder=SentenceTransformer(os.getenv('EMBEDDING_MODEL','sentence-transformers/all-MiniLM-L6-v2'))
        self.reranker=CrossEncoder(os.getenv('RERANKER_MODEL','cross-encoder/ms-marco-MiniLM-L-6-v2'))
        self.client=chromadb.PersistentClient(path=persist_path)
        self.collection=self.client.get_or_create_collection(collection_name, metadata={'hnsw:space':'cosine'})
        embeddings=self.embedder.encode(self.texts, normalize_embeddings=True).tolist()
        self.collection.upsert(ids=[c.chunk_id for c in chunks], documents=self.texts,
                               embeddings=embeddings, metadatas=[{'document_id':c.document_id,'page':c.page,'section':c.section or '','clause':c.clause or ''} for c in chunks])

    def retrieve(self, query: str, top_k: int=5) -> list[Evidence]:
        q_tokens=re.findall(r'\w+', query.lower())
        bm_scores=self.bm25.get_scores(q_tokens)
        bm_ids=sorted(range(len(self.chunks)), key=lambda i: float(bm_scores[i]), reverse=True)[:8]
        qemb=self.embedder.encode([query], normalize_embeddings=True).tolist()[0]
        dense=self.collection.query(query_embeddings=[qemb], n_results=min(8,len(self.chunks)))
        dense_ids=[x for x in (dense.get('ids') or [[]])[0]]
        by_id={c.chunk_id:i for i,c in enumerate(self.chunks)}
        candidate_indices=[]
        for i in bm_ids:
            if i not in candidate_indices: candidate_indices.append(i)
        for cid in dense_ids:
            if cid in by_id and by_id[cid] not in candidate_indices: candidate_indices.append(by_id[cid])
        if not candidate_indices: return []
        pairs=[(query,self.chunks[i].text) for i in candidate_indices]
        scores=self.reranker.predict(pairs)
        ranked=sorted(zip(candidate_indices,scores), key=lambda x:float(x[1]), reverse=True)[:top_k]
        return [Evidence(document_id=self.chunks[i].document_id,chunk_id=self.chunks[i].chunk_id,text=self.chunks[i].text,
                          page=self.chunks[i].page,section=self.chunks[i].section,clause=self.chunks[i].clause,
                          score=float(s),source='BM25+dense+CrossEncoder') for i,s in ranked]
