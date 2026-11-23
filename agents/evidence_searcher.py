import re
import unicodedata
from typing import Dict, List, Set

from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings
from rank_bm25 import BM25Okapi

from config.constants import RRF_K, SEARCH_TOP_K
from config.settings import settings
from utils.logging import logger

from .ranker import FIRST_KINDS, Ranker


class EvidenceSearcher:
    """Hybrid search over tickets and pages: keywords find exact words, embeddings find the same idea in other words."""

    def __init__(self, items: List[Dict]):
        # 1) The texts to search: the evidence items, one per ticket or page that counts for someone
        self.item_ids = [item["id"] for item in items]

        # 2) For each type of question, the items worth finding: the ones that count for someone in that type.
        #    For "help" and "did", it is every item. For "decided", it is only the minutes that record a decision
        ranker = Ranker()
        self.ids_by_type = {
            question_type: {item["id"] for item in items if ranker.pieces_that_count(item["pieces"], question_type)}
            for question_type in FIRST_KINDS
        }

        # 3) Keyword search (BM25): scores a text by the words it shares with the query. Rare words count more
        self.bm25 = BM25Okapi([self._tokenize(item["text"]) for item in items])

        # 4) Vector search: OpenAI turns each text into a list of numbers (an embedding), kept in memory
        documents = [Document(page_content=item["text"], metadata={"id": item["id"]}) for item in items]
        try:
            embeddings = OpenAIEmbeddings(model=settings.OPENAI_EMBEDDING_MODEL, api_key=settings.OPENAI_API_KEY)
            self.vector_store = InMemoryVectorStore(embedding=embeddings)
            self.vector_store.add_documents(documents, ids=self.item_ids)
        except Exception as e:
            logger.error(f"Could not build the search index: {e}")
            raise
        logger.info(f"Search index ready: {len(items)} tickets and pages")

    def search(self, question: str, search_words: List[str], question_type: str, retry: bool = False) -> List[str]:
        """Return the ids of the tickets and pages that match the question, best first."""
        # 1) Only the tickets and pages that count for this type of question are worth finding
        if question_type not in self.ids_by_type:
            raise ValueError(f"Unknown question type: {question_type}")
        allowed_ids = self.ids_by_type[question_type]

        # 2) Each search gets what it handles best. The keyword search gets the topic words only, because words like
        #    "who" and "help" match unrelated texts. Without topic words, it gets the whole question
        words = " ".join(search_words)
        keyword_ids = self._keyword_search(words or question, allowed_ids)
        #    The vector search compares meanings, so it gets the whole question. On a retry, it gets the new words
        #    instead: the same question would only bring back the same texts
        vector_ids = self._vector_search(words if retry and words else question, allowed_ids)

        # 3) One list: a text found by both searches comes first
        found_ids = self._merge([keyword_ids, vector_ids])
        logger.info(
            f"Search{' again' if retry else ''}: {len(found_ids)} found among the {len(allowed_ids)} tickets and "
            f"pages that count for a \"{question_type}\" question "
            f"({len(keyword_ids)} by keywords, {len(vector_ids)} by meaning)"
        )
        return found_ids

    def _keyword_search(self, query: str, allowed_ids: Set[str]) -> List[str]:
        """The best matches by shared words. A text that shares no word with the query is never returned."""
        scores = self.bm25.get_scores(self._tokenize(query))
        # Best score first. Two texts with the same score keep the order of the data, so nothing is random
        order = sorted(range(len(self.item_ids)), key=lambda index: (-scores[index], index))
        matches = [self.item_ids[index] for index in order if scores[index] > 0 and self.item_ids[index] in allowed_ids]
        return matches[:SEARCH_TOP_K]

    def _vector_search(self, query: str, allowed_ids: Set[str]) -> List[str]:
        """The best matches by meaning: the texts whose embedding is the closest to the query's embedding."""
        try:
            documents = self.vector_store.similarity_search(
                query,
                k=SEARCH_TOP_K,
                # The store calls this for each text, and only compares the ones that pass
                filter=lambda document: document.metadata["id"] in allowed_ids,
            )
        except Exception as e:
            logger.error(f"The vector search failed: {e}")
            raise RuntimeError("The vector search failed") from e
        return [document.metadata["id"] for document in documents]

    def _merge(self, rankings: List[List[str]]) -> List[str]:
        """Reciprocal Rank Fusion: each list gives an item 1 / (60 + its rank) points, and the points add up."""
        points: Dict[str, float] = {}
        for ranking in rankings:
            for rank, item_id in enumerate(ranking, start=1):
                points[item_id] = points.get(item_id, 0.0) + 1 / (RRF_K + rank)
        # Most points first: an item found by both searches comes before an item found by one. Then by id
        return sorted(points, key=lambda item_id: (-points[item_id], item_id))

    def _tokenize(self, text: str) -> List[str]:
        """Cut a text into lower-case words without accents, so "Réclamation" matches "reclamation"."""
        decomposed = unicodedata.normalize("NFKD", text.lower())
        plain = "".join(letter for letter in decomposed if not unicodedata.combining(letter))
        return re.findall(r"[a-z0-9]+", plain)
