import unittest

from langchain_core.documents import Document

from its_multi_agent.backend.knowledge.repositories.vector_store_repository import (
    VectorStoreRepository,
)


class FakeVectorDatabase:
    def __init__(self, fail_on_add=None, search_results=None):
        self.fail_on_add = fail_on_add
        self.search_results = search_results or []
        self.add_calls = []
        self.delete_calls = []
        self.search_calls = []

    def add_documents(self, documents, ids):
        self.add_calls.append((documents, ids))
        if len(self.add_calls) == self.fail_on_add:
            raise RuntimeError("simulated Milvus failure")
        return ids

    def delete(self, ids=None, expr=None):
        self.delete_calls.append(list(ids) if ids is not None else expr)

    def similarity_search_with_score(self, query, top_k):
        self.search_calls.append((query, top_k))
        return self.search_results[:top_k]


class FakeEmbedding:
    def embed_query(self, text):
        return [float(len(text))]

    def embed_documents(self, texts):
        return [[float(len(text))] for text in texts]


class VectorStoreRepositoryTest(unittest.TestCase):
    def _documents(self):
        return [
            Document(
                page_content=f"child-{index}",
                metadata={
                    "document_hash": "hash-a",
                    "parent_id": "parent-a",
                    "child_index": index,
                },
            )
            for index in range(3)
        ]

    def test_uses_stable_ids_for_batched_writes(self):
        database = FakeVectorDatabase()
        repository = VectorStoreRepository(vector_database=database)
        documents = self._documents()

        self.assertEqual(repository.add_documents(documents, batch_size=2), 3)
        inserted_ids = [item for _, ids in database.add_calls for item in ids]
        self.assertEqual(inserted_ids, database.delete_calls[0])
        self.assertEqual(inserted_ids, [item.metadata["vector_id"] for item in documents])

        second_documents = self._documents()
        second_ids = [
            repository._document_id(document, index)
            for index, document in enumerate(second_documents)
        ]
        self.assertEqual(inserted_ids, second_ids)

    def test_deletes_all_ids_when_a_batch_fails(self):
        database = FakeVectorDatabase(fail_on_add=2)
        repository = VectorStoreRepository(vector_database=database)

        with self.assertRaisesRegex(RuntimeError, "simulated Milvus failure"):
            repository.add_documents(self._documents(), batch_size=2)

        self.assertEqual(len(database.delete_calls), 2)
        self.assertEqual(database.delete_calls[0], database.delete_calls[1])

    def test_embedding_methods_use_the_expected_client_contract(self):
        repository = VectorStoreRepository(
            embedding=FakeEmbedding(),
            vector_database=FakeVectorDatabase(),
        )

        self.assertEqual(repository.embed_document("query"), [5.0])
        self.assertEqual(repository.embed_documents(["a", "abcd"]), [[1.0], [4.0]])

    def test_scope_collection_names_are_stable_and_isolated(self):
        first = VectorStoreRepository.scope_collection_name("hr", "policy")
        second = VectorStoreRepository.scope_collection_name("hr", "policy")
        other = VectorStoreRepository.scope_collection_name("legal", "contract")

        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertEqual(
            VectorStoreRepository.scope_collection_name("default", "general"),
            "its_knowledge",
        )

    def test_search_rejects_documents_from_another_scope(self):
        matching = Document(
            page_content="知识空间:hr\n知识领域:policy\n报销制度",
            metadata={"parent_id": "hr-1"},
        )
        other = Document(
            page_content="知识空间:legal\n知识领域:contract\n采购合同",
            metadata={"parent_id": "legal-1"},
        )
        database = FakeVectorDatabase(search_results=[(other, 0.1), (matching, 0.2)])
        repository = VectorStoreRepository(vector_database=database)

        results = repository.search_similarity_with_score("报销", 1, "hr", "policy")

        self.assertEqual([document.metadata["parent_id"] for document, _ in results], ["hr-1"])

    def test_unscoped_legacy_documents_only_match_default_scope(self):
        legacy = Document(page_content="旧版知识文档", metadata={})

        self.assertTrue(VectorStoreRepository.document_matches_scope(legacy, "default", "general"))
        self.assertFalse(VectorStoreRepository.document_matches_scope(legacy, "hr", "policy"))

    def test_deletes_document_vectors_by_registry_hash(self):
        database = FakeVectorDatabase()
        repository = VectorStoreRepository(vector_database=database)

        repository.delete_document("hash-a")

        self.assertEqual(database.delete_calls, ['document_hash == "hash-a"'])


if __name__ == "__main__":
    unittest.main()
