import jieba
import logging
import re
import hashlib
from collections import OrderedDict
from threading import Lock
from typing import Dict,List,Any

from langchain_community.utils.math import cosine_similarity

from its_multi_agent.backend.knowledge.utils.markdown_utils import MarkDownUtils
from its_multi_agent.backend.knowledge.repositories.lexical_index_repository import LexicalIndexRepository
from its_multi_agent.backend.knowledge.repositories.vector_store_repository import VectorStoreRepository
from its_multi_agent.backend.knowledge.services.ingestion.parent_child_splitter import ParentChildSplitter
from its_multi_agent.backend.knowledge.services.cross_encoder_reranker import CrossEncoderReranker
from its_multi_agent.backend.knowledge.config.settings import settings
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from typing import List
from langchain_core.documents import Document



class RetrievalService:
    """
    负责检索的类（检索器）
    RAG:（小块：越小越好【小（无线小）】）文本嵌入模型  （完整信息：越大越大【不能无限大】）文本语言模型====准 原文档（大）--->1.小块（子） 2.稍微大一点的块（整个文档）【父】---留一个保留关系：穿针引线思想（父文档召回）
    """

    def __init__(self):
        self.vector_store = VectorStoreRepository()
        self.lexical_index = LexicalIndexRepository()
        self.document_splitter = ParentChildSplitter().child_splitter
        self.cross_encoder_reranker = CrossEncoderReranker()
        self._embedding_cache = OrderedDict()
        self._embedding_cache_lock = Lock()

    def rough_ranking(self, user_query, mds_metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
         对标题进行粗排
         基于jieba进行标题的分词匹配
        Args:
            user_query: 用户的问题
            mds_metadata: 所有md的元数据（标题【title】，路径【path】）

        Returns:
            List[Dict[str,Any]]:所有md的元数据 （标题【title】，路径【path】，标题粗排得分【rough_score】）
        """

        # 1. 用户输入问题是否存在
        if not user_query:
            return []
        ROUGHIN_WORD_WEIGHT = 0.7

        # 2.遍历mds_metadata(所有md的元数据)
        for md_metadata in mds_metadata:
            # 2.1 获取md标题
            md_metadata_title = md_metadata['title']

            # 2.2 判断标题是否存在
            if not md_metadata_title or not md_metadata_title.strip():
                continue
            # 2.3 进行分词&&算得分
            # 2.3.1 优先用字符切:set:交、并、差:jarcard算法=A N B/A U B
            user_query_char = set(user_query)
            md_metadata_title_char = set(md_metadata_title)
            unique_char = user_query_char | md_metadata_title_char
            char_score = len(user_query_char & md_metadata_title_char) / len(unique_char) if len(unique_char) > 0 else 0

            # 2.3.2 在用jieba词项切(影响因素大一些)
            user_query_word = set(jieba.lcut(user_query))
            md_metadata_title_word = set(jieba.lcut(md_metadata_title))
            unique_word = user_query_word | md_metadata_title_word
            word_score = len(user_query_word & md_metadata_title_word) / len(unique_word) if len(unique_word) > 0 else 0

            # 2.3.3 计算粗排分数：字符级+词性项级(侧重)
            roughing_score = word_score * ROUGHIN_WORD_WEIGHT + char_score * (1 - ROUGHIN_WORD_WEIGHT)

            md_metadata['roughing_score'] = float(roughing_score)

        # 3.根据标题的元数据（roughing_score）排序并且留下前50个
        return sorted(mds_metadata, key=lambda x: x['roughing_score'], reverse=True)[:50]

    def fine_ranking(self, user_query: str, rough_mds_metadata: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
         对标题进行精排
         基于嵌入模型相似性以及cosine_similarity()
        Args:
            user_query: 用户当前问题
            rough_mds_metadata: 粗排后的md元数据

        Returns:
            List[Dict[str, Any]]: 带精排分数的元数据
        """

        # 1. 判粗排元数据
        if not rough_mds_metadata:
            return []

        # 两个二维矩阵（X[样本数] Y[样本质量]） K(X, Y) = <X, Y> / (||X||*||Y||)

        # 2. 对问题向量化
        query_embedding = self._cached_embed_document(user_query)

        # 3. 获取粗排后的标题
        roughing_title = [md_metadata['title'] for md_metadata in rough_mds_metadata]

        # 4. 标题的向量值
        roughing_title_embeddings = self.vector_store.embed_documents(roughing_title)

        # 5. 计算问题和粗排标题的相似度（余弦相似分数）分数值越大 代表问题和标题越相似
        # flatten()--->一维数组[0.1,0.4,0.01,0.6...]
        # X:1  Y:[1,2,3,4,5]   similarity=[0.1,0.4,0.01,0.6,0.3]【-1,0】
        similarity = cosine_similarity([query_embedding], roughing_title_embeddings).flatten()

        # 6. 遍历粗排元数据
        ROUGH_HEIGHT = 0.3
        SIM_HEIGHT = 0.7
        for index, md_metadata in enumerate(rough_mds_metadata):

            # a. 获取精排分数(归一)
            sim = similarity[index]
            if sim < 0:
                sim = 0
            # b. 获取粗排
            roughing_score = md_metadata['roughing_score']

            # c. 加权求最终精排分数
            final_score = roughing_score * ROUGH_HEIGHT + sim * SIM_HEIGHT

            # d. 存放到md_metadata 元数据中
            md_metadata['sim_score'] = sim
            md_metadata['final_score'] = final_score

        # 7. 排序
        sim_mds_metadata = sorted(rough_mds_metadata, key=lambda x: x['final_score'], reverse=True)[:5]

        # 8. 返回
        return sim_mds_metadata

    def retrieval(
        self,
        user_question: str,
        search_queries: List[str] | None = None,
        knowledge_space: str = "default",
        domain: str = "general",
    ) -> List[Document]:
        """
         核心检索方法（检索器的入口）
        Args:
            user_question: 用户输入的问题

        Returns:
           List[Document]: 返回指定Top-N个相似性文档列表
        """

        queries = search_queries or [user_question]
        based_vector_candidates = []
        for query in queries:
            scoped_query = self._scoped_query(query, knowledge_space, domain)
            based_vector_candidates.extend(
                self._search_based_vector(
                    scoped_query,
                    matched_query=query,
                    knowledge_space=knowledge_space,
                    domain=domain,
                )
            )

        bm25_candidates = []
        if settings.BM25_RETRIEVAL_ENABLED:
            for query in queries:
                for document in self.lexical_index.search(
                    query,
                    knowledge_space,
                    domain,
                    settings.BM25_TOP_K,
                ):
                    document.metadata["matched_query"] = query
                    document.metadata["matched_queries"] = [query]
                    document.metadata["bm25_ranks"] = [document.metadata["bm25_rank"]]
                    bm25_candidates.append(document)

        # 2. 第二路检索(基于jieba的分词匹配的检索)
        based_title_candidates = (
            self._search_based_title(user_question)
            if settings.LEGACY_TITLE_RETRIEVAL_ENABLED
            else []
        )

        # 3. 合并两路检索的文档列表
        total_candidates = based_vector_candidates + bm25_candidates + based_title_candidates

        # 4. 对合并后的文档列表去重
        unique_candidates = self._deduplicate(total_candidates)

        # 5. 重新打分排序
        ranked_documents = self._reranking(
            unique_candidates,
            user_question,
            query_count=len(queries),
            limit=settings.RERANK_CANDIDATE_K,
        )
        ranked_documents = self._diversify(
            ranked_documents,
            limit=settings.RERANK_CANDIDATE_K,
            max_per_document=2,
        )

        # 6.返回指定Top-N个文档列表
        return self.cross_encoder_reranker.rerank(
            user_question,
            ranked_documents,
            settings.FINAL_TOP_K,
        )

    @staticmethod
    def _diversify(documents: List[Document], limit: int, max_per_document: int = 2) -> List[Document]:
        """Keep high scoring evidence while preventing one document from monopolizing results."""
        if limit <= 0 or max_per_document <= 0:
            return []
        selected = []
        counts = {}
        deferred = []
        for document in documents:
            metadata = document.metadata
            source_key = str(
                metadata.get("document_hash")
                or metadata.get("source_name")
                or metadata.get("path")
                or metadata.get("title")
                or "unknown"
            )
            if counts.get(source_key, 0) < max_per_document:
                selected.append(document)
                counts[source_key] = counts.get(source_key, 0) + 1
                if len(selected) >= limit:
                    break
            else:
                deferred.append(document)
        if len(selected) < limit:
            selected.extend(deferred[:limit - len(selected)])
        return selected

    def _search_based_vector(
        self,
        user_question: str,
        matched_query: str = "",
        knowledge_space: str = "default",
        domain: str = "general",
    ) -> List[Document]:
        """
        第一路检索
        基于语义相似度检索

        Args:
            user_question: 用户输入的问题

        Returns:
            List[Document]： Top-N个相似的文档列表

        """
        # 1.返回带分数的文档列表
        documents_with_score = self.vector_store.search_similarity_with_score(
            user_question,
            settings.VECTOR_CHILD_TOP_K,
            knowledge_space,
            domain,
        )

        # 2.TODO(不用距离得分)
        based_vector_candidates = []
        seen_parents = set()
        for rank, (document, score) in enumerate(documents_with_score, start=1):
            metadata = dict(document.metadata)
            parent_id = metadata.get("parent_id")
            parent_content = metadata.pop("parent_content", "")
            if parent_id and parent_content:
                if parent_id in seen_parents:
                    continue
                seen_parents.add(parent_id)
                metadata.update({
                    "chunk_type": "parent",
                    "matched_child": document.page_content,
                    "matched_query": matched_query or user_question,
                    "matched_queries": [matched_query or user_question],
                    "retrieval_rank": rank,
                    "retrieval_ranks": [rank],
                    "vector_score": float(score),
                })
                based_vector_candidates.append(Document(
                    page_content=parent_content,
                    metadata=metadata,
                ))
            else:
                document.metadata["matched_query"] = matched_query or user_question
                document.metadata["matched_queries"] = [matched_query or user_question]
                document.metadata["retrieval_rank"] = rank
                document.metadata["retrieval_ranks"] = [rank]
                based_vector_candidates.append(document)
        return based_vector_candidates

    @staticmethod
    def _scoped_query(query: str, knowledge_space: str, domain: str) -> str:
        context = []
        if knowledge_space != "default":
            context.append(f"知识空间:{knowledge_space}")
        if domain != "general":
            context.append(f"知识领域:{domain}")
        context.append(query)
        return "\n".join(context)

    def _search_based_title(self, user_query: str) -> List[Document]:
        """
         第二路检索
         基于标题的关键词匹配检索
        Args:
            user_query: 用户输入的问题

        Returns:
            List[Document]: Top-N个相似的文档列表

        """

        # 1. 获取指定目录下的文件的标题
        mds_metadata = MarkDownUtils.collect_md_metadata(settings.CRAWL_OUTPUT_DIR)

        # 2. 进行标题匹配
        # 2.1 关键词匹配（jieba）--->（比较对象：用户输入的问题 vs crawl目录下的文件标题）
        # 2.2 标题的语义匹配（比较对象：用户的输入问题  vs md目录下的 ）
        rough_mds_metadata = self.rough_ranking(user_query, mds_metadata)
        fine_mds_metadata = self.fine_ranking(user_query, rough_mds_metadata)

        # 3. 处理文档（根据标题读取标题对于的文档内容---Document(page_content,metadata={})）

        based_title_candidates = []
        for fine_md_metadata in fine_mds_metadata:
            try:
                # 3.1 打开文件
                with open(fine_md_metadata['path'], "r", encoding="utf-8") as f:
                    content = f.read().strip()
                # 3.2 判断content内容长度
                # a.短md知识
                if len(content) < 3000:
                    # 不切分
                    doc = Document(page_content=content, metadata={
                        "path": fine_md_metadata['path'],
                        "title": fine_md_metadata['title'],
                    })
                    based_title_candidates.append(doc)
                # b. 长md知识 切分
                else:
                    doc_chunks = self._deal_long_title_content(content, fine_md_metadata, user_query)
                    based_title_candidates.extend(doc_chunks)  # doc_chunks 列表中元素打散了
            except Exception as e:

                logger.error(f"打开文件失败:{e}")
                return []
        # 4. 返回指定文档列表

        return based_title_candidates

    def _deduplicate(self, total_candidates: List[Document]) -> List[Document]:
        """
         对合并后的文档列表去重
         使用来源位置和完整内容区分证据，合并同一父块的检索通道。
        Args:
            total_candidates: 合并的文档列表

        Returns:
            List[Document]：唯一的文档列表
        """

        if not total_candidates:
            return []

        # 2. 定义set集合
        seen = {}
        unique_candidates = []

        # 3. 遍历合并后的每一个文档列表
        for document in total_candidates:
            # 去重（）
            clean_content = re.sub(r'^文档来源:.*?(?=(\n|#))', '', document.page_content, flags=re.DOTALL).strip()#【加上】
            metadata = document.metadata
            provenance = tuple(str(metadata.get(field, "")) for field in (
                "knowledge_space", "domain", "document_hash", "source_name", "path",
            ))
            key = (provenance, "parent", str(metadata["parent_id"])) if metadata.get("parent_id") else (
                provenance, "content", str(metadata.get("title", "")),
                str(metadata.get("page", "")), str(metadata.get("sheet", "")),
                hashlib.sha256(clean_content.encode("utf-8")).hexdigest(),
            )
            if key not in seen:
                seen[key] = document
                unique_candidates.append(document)
                continue

            existing = seen[key]
            matched_queries = list(existing.metadata.get("matched_queries", []))
            for query in document.metadata.get("matched_queries", []):
                if query not in matched_queries:
                    matched_queries.append(query)
            existing.metadata["matched_queries"] = matched_queries
            existing.metadata["retrieval_rank"] = min(
                existing.metadata.get("retrieval_rank", settings.VECTOR_CHILD_TOP_K),
                document.metadata.get("retrieval_rank", settings.VECTOR_CHILD_TOP_K),
            )
            existing.metadata["retrieval_ranks"] = (
                list(existing.metadata.get("retrieval_ranks", []))
                + list(document.metadata.get("retrieval_ranks", []))
            )
            existing.metadata["bm25_ranks"] = (
                list(existing.metadata.get("bm25_ranks", []))
                + list(document.metadata.get("bm25_ranks", []))
            )

        # 4. 返回唯一的
        return unique_candidates

    def _reranking(
        self,
        unique_candidates: List[Document],
        user_question: str,
        query_count: int = 1,
        limit: int | None = None,
    ) -> List[Document]:
        """
         重新计算打分&&排序
         第二路长文档已经进行了cosine_similarity()的计算（无需在次打分）
         对第一路的文档和第二路的短文档进行重新计算

        Args:
            unique_candidates: 唯一的候选文档列表
            user_question: 用户输入的问题

        Returns:
            List[Document]: 最终指定Top-N的文档列表

        """

        # 1. 判断去重合并之后文档列表是否有文档对象
        if not unique_candidates:
            return []

        need_embedding_docs = []
        need_embedding_candidates_indices = []
        score_doc = []

        # 2. 遍历去重并合并之后的文档列表(Document,score)
        for candidate_index, unique_candidate in enumerate(unique_candidates):
            # 如何去判断 第二路长文档 or  第一路的文档和第二路?
            # 2.1 第二路的长文档
            if "chunk_index" in unique_candidate.metadata and "similarity" in unique_candidate.metadata:
                score_doc.append((unique_candidate, float(unique_candidate.metadata['similarity'])))
            # 2.2 第一路和第二路的短文档
            else:
                need_embedding_docs.append(unique_candidate)
                need_embedding_candidates_indices.append(candidate_index)

        # 3.处理需要重新计算分数的文档
        if need_embedding_docs:
            # 3.1 计算用户问题的向量
            query_embedding = self._cached_embed_document(user_question)

            # 3.2 获取到需要向量的文档内容
            embedding_docs_content = ["文档来源:" + doc.metadata.get('title', '') + doc.page_content for doc in
                                      need_embedding_docs]
            # 3.3 计算需要向量的文档内容
            doc_embeddings = self._cached_embed_documents(embedding_docs_content)

            # 3.4 计算相似得分
            similarity = cosine_similarity([query_embedding], doc_embeddings).flatten()

            # 3.5 封装到带得分的文档列表
            for idx, candidate_index in enumerate(need_embedding_candidates_indices):
                score_doc.append((unique_candidates[candidate_index], similarity[idx]))

        # 4. 排序
        fused_docs = []
        for document, semantic_score in score_doc:
            semantic_score = max(0.0, min(1.0, float(semantic_score)))
            lexical_score = self._lexical_score(user_question, document.page_content)
            matched_queries = document.metadata.get("matched_queries", [])
            coverage_score = min(1.0, len(matched_queries) / max(1, query_count))
            rrf_score = self._rrf_score(document)
            if settings.HYBRID_RERANK_ENABLED:
                final_score = (
                    semantic_score * settings.RERANK_SEMANTIC_WEIGHT
                    + lexical_score * settings.RERANK_LEXICAL_WEIGHT
                    + coverage_score * settings.RERANK_QUERY_COVERAGE_WEIGHT
                    + rrf_score * settings.RERANK_RRF_WEIGHT
                )
            else:
                final_score = semantic_score
            document.metadata.update({
                "semantic_score": semantic_score,
                "lexical_score": lexical_score,
                "query_coverage_score": coverage_score,
                "rrf_score": rrf_score,
                "rerank_score": float(final_score),
            })
            if final_score >= settings.RERANK_SCORE_THRESHOLD:
                fused_docs.append((document, final_score))

        sorted_docs = sorted(fused_docs, key=lambda x: x[1], reverse=True)

        # 5. 返回Top-N
        top_documents = []
        for document, score in sorted_docs[:limit or settings.FINAL_TOP_K]:
            top_documents.append(document)
        return top_documents

    def _cached_embed_document(self, text: str):
        self._ensure_embedding_cache()
        key = ("query", text)
        with self._embedding_cache_lock:
            if key in self._embedding_cache:
                value = self._embedding_cache.pop(key)
                self._embedding_cache[key] = value
                return value
        value = self.vector_store.embed_document(text)
        self._remember_embedding(key, value)
        return value

    def _cached_embed_documents(self, texts: List[str]):
        self._ensure_embedding_cache()
        values = [None] * len(texts)
        missing = []
        missing_positions = []
        with self._embedding_cache_lock:
            for index, text in enumerate(texts):
                key = ("document", text)
                if key in self._embedding_cache:
                    values[index] = self._embedding_cache.pop(key)
                    self._embedding_cache[key] = values[index]
                else:
                    missing.append(text)
                    missing_positions.append(index)
        if missing:
            embedded = self.vector_store.embed_documents(missing)
            for index, text, value in zip(missing_positions, missing, embedded):
                values[index] = value
                self._remember_embedding(("document", text), value)
        return values

    def _remember_embedding(self, key, value) -> None:
        self._ensure_embedding_cache()
        with self._embedding_cache_lock:
            self._embedding_cache[key] = value
            while len(self._embedding_cache) > settings.EMBEDDING_CACHE_SIZE:
                self._embedding_cache.popitem(last=False)

    def _ensure_embedding_cache(self) -> None:
        # Some focused unit tests construct the service with __new__ to avoid
        # external Milvus initialization.
        if not hasattr(self, "_embedding_cache"):
            self._embedding_cache = OrderedDict()
            self._embedding_cache_lock = Lock()

    @staticmethod
    def _rrf_score(document: Document) -> float:
        vector_ranks = list(document.metadata.get("retrieval_ranks", []))
        bm25_ranks = list(document.metadata.get("bm25_ranks", []))
        if not vector_ranks and not bm25_ranks:
            return 0.0

        channel_scores = []
        if vector_ranks:
            channel_scores.append(max(
                1.0 / (settings.RRF_K + max(1, int(rank)))
                for rank in vector_ranks
            ))
        if bm25_ranks:
            channel_scores.append(max(
                1.0 / (settings.RRF_K + max(1, int(rank)))
                for rank in bm25_ranks
            ))
        best_single_channel = 1.0 / (settings.RRF_K + 1)
        channel_count = 2 if settings.BM25_RETRIEVAL_ENABLED else 1
        return min(1.0, sum(channel_scores) / (best_single_channel * channel_count))

    @staticmethod
    def _lexical_score(query: str, content: str) -> float:
        def tokens(text: str):
            return {
                token.lower()
                for token in jieba.lcut(text)
                if token.strip() and re.search(r"[\w\u4e00-\u9fff]", token)
            }

        query_tokens = tokens(query)
        if not query_tokens:
            return 0.0
        content_tokens = tokens(content)
        token_recall = len(query_tokens & content_tokens) / len(query_tokens)

        identifiers = {
            item.lower()
            for item in re.findall(r"[A-Za-z]+[-_.]?\d+[A-Za-z0-9_.-]*|\d{3,}", query)
        }
        identifier_score = (
            sum(
                bool(re.search(
                    rf"(?<![A-Za-z0-9]){re.escape(identifier)}(?![A-Za-z0-9])",
                    content.lower(),
                ))
                for identifier in identifiers
            ) / len(identifiers)
            if identifiers
            else token_recall
        )
        return float(token_recall * 0.55 + identifier_score * 0.45)

    def _deal_long_title_content(self, content: str, fine_md_metadata: Dict[str, Any], user_query: str) -> List[
        Document]:
        """
         处理标题对应的长文本
         切分-->文档块--->算文档块和问题的相似度
        Args:
            content: 长文本
            fine_md_metadata: 长文本对应的元数据
            user_query: 用户的问题

        Returns:
            List[Document]: 和问题相似的文档块（chunk）
        """

        # 1. 对长文本切分(换成适合)
        chunks = self.document_splitter.split_text(content)

        # 2. 获取对应的标题
        doc_chunks_title = fine_md_metadata['title']

        # 3. 标题注入到文档块中（第二次结构和第一次的拼接一定要一样）TODO
        doc_chunks_inject_title = [f"文档来源:{doc_chunks_title}" + doc_chunk for doc_chunk in chunks]

        # 4. 对问题向量
        query_embedding = self._cached_embed_document(user_query)

        # 5. 对切分后的文档块向量化
        doc_chunk_embeddings = self._cached_embed_documents(doc_chunks_inject_title)

        # 6. 计算相似性:doc_chunks_similarity[0.8,0.6,0.7,0.1,0.9]
        doc_chunks_similarity = cosine_similarity([query_embedding], doc_chunk_embeddings).flatten()

        # 7. 获取3个相似性分数值高的三个索引 argsort->[3,1,2,0,4]->[2,0,4]--->[4,0,2]
        top_doc_chunks_indices = doc_chunks_similarity.argsort()[-3:][::-1]

        # 8. 构建最终文档对象列表(为每一个切分后的块)
        docs = []
        for i, chunk_idx in enumerate(top_doc_chunks_indices):
            doc = Document(
                page_content=doc_chunks_inject_title[chunk_idx],  # 带上
                metadata={
                    "path": fine_md_metadata['path'],
                    "title": fine_md_metadata['title'],
                    "chunk_index": int(chunk_idx),
                    "similarity": float(doc_chunks_similarity[chunk_idx])
                }
            )
            docs.append(doc)

        return   docs


if __name__ == '__main__':
    retrival_service = RetrievalService()

    # rough_ranking_result = retrival_service.rough_ranking("我的电脑开机之后没有任何的反应"）
    # for roughing_result in rough_ranking_result[:10]:
    #     print(f"粗排---{roughing_result}")
    #
    # sim_ranking_result = retrival_service.fine_ranking("我的电脑开机之后没有任何的反应", rough_ranking_result[:10])
    #
    # for sim_result in sim_ranking_result:
    #     print(f"精排---{sim_result}")

    # result = retrival_service.retrieval("我的电脑开机之后没有任何的反应")
    # result = retrival_service.retrieval("如何安装联想的一件影音")
    # result = retrival_service.retrieval("联想手机K900常见问题汇总有哪些")
    # result = retrival_service.retrieval("如何使用U盘安装Windows 7操作系统.")
    # result = retrival_service.retrieval("开机屏幕黑屏或蓝屏报错,无法正常进入系统怎么办")
    # result = retrival_service.retrieval("我的电脑经常死机该如何解决")
    result = retrival_service.retrieval("手机、平板上的画面能无线传输到电视上播放吗") # 80-90%

    for r in result:
        print(r)
