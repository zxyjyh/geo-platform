"""知识库混合检索：向量余弦 + BM25 关键词，RRF 融合。只查现行且已处理完的文档。"""
from dataclasses import dataclass
from datetime import date

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collector import setting
from app.kb.embed import Embedder
from app.kb.text import bm25_scores, rrf, tokenize
from app.models import KbChunk, KbDoc


@dataclass
class Hit:
    chunk_id: int
    doc_id: int
    doc_title: str
    effective_date: date
    page_no: int
    half: str
    text: str
    score: float
    semantic_rank: int | None  # 从 1 开始；没进该路前 candidates 名时为 None
    keyword_rank: int | None
    similarity: float  # 原始余弦相似度


def search(session: Session, query: str, embedder: Embedder, limit: int = 5, candidates: int = 50) -> list[Hit]:
    query = query.strip()
    if not query:
        return []
    qvec = np.asarray(embedder.embed(query), dtype=np.float32)
    rows = session.execute(
        select(KbChunk, KbDoc.title, KbDoc.effective_date)
        .join(KbDoc, KbDoc.id == KbChunk.doc_id)
        .where(KbDoc.status == "active", KbDoc.process_status == "ready")
        .order_by(KbChunk.id)
    ).all()
    # 换过模型的旧切片维度对不上，不参与（语义、关键词两路都不参与）
    rows = [r for r in rows if r[0].dim == len(qvec)]
    if not rows:
        return []

    matrix = np.stack([np.frombuffer(c.embedding, dtype="<f4") for c, _, _ in rows])
    norms = np.linalg.norm(matrix, axis=1) * (np.linalg.norm(qvec) or 1.0)
    sims = matrix @ qvec / np.where(norms == 0, 1.0, norms)

    # 相关度下限：低于阈值的切片不参与检索结果
    min_sim = float(setting(session, "kb_min_similarity", "0.3"))
    above_threshold = {i for i in range(len(rows)) if sims[i] >= min_sim}

    semantic = [int(i) for i in np.argsort(-sims, kind="stable") if int(i) in above_threshold][:candidates]

    kw = bm25_scores(tokenize(query), [c.tokens.split() for c, _, _ in rows])
    keyword = [i for i in sorted(range(len(rows)), key=lambda i: (-kw[i], i))
               if kw[i] > 0 and i in above_threshold][:candidates]

    sem_rank = {i: r for r, i in enumerate(semantic, start=1)}
    kw_rank = {i: r for r, i in enumerate(keyword, start=1)}
    hits = []
    for idx, score in rrf([semantic, keyword])[:limit]:
        c, title, eff = rows[idx]
        hits.append(Hit(c.id, c.doc_id, title, eff, c.page_no, c.half, c.text, score,
                        sem_rank.get(idx), kw_rank.get(idx), float(sims[idx])))
    return hits
