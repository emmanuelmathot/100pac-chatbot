"""Index vectoriel local du rapport (Chroma + embeddings ``mistral-embed``).

Construit hors-ligne (``scripts/build-index``) : le rapport est découpé en
fragments, encodé en embeddings Mistral, et persisté dans un store Chroma local.
À l'exécution, l'agent ne fait que des recherches top-k qui renvoient des
passages courts **avec leur source** (section + page) — les données ne transitent
pas en masse par le LLM.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_mistralai import MistralAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import SecretStr

from chatbot import paths
from chatbot.rag.extract import extract_pages
from chatbot.rag.figures import Figure, extract_figures
from chatbot.settings import get_settings

COLLECTION = "rapport_pac"
FIGURES_COLLECTION = "rapport_figures"
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200


@dataclass(frozen=True)
class Passage:
    """Un passage retrouvé, avec sa source pour citation."""

    text: str
    page: int
    section: str


def _embeddings() -> MistralAIEmbeddings:
    settings = get_settings()
    return MistralAIEmbeddings(
        model="mistral-embed",
        mistral_api_key=SecretStr(settings.mistral_api_key),
    )


def _documents() -> list[Document]:
    """Découpe le rapport en fragments porteurs de métadonnées (page, section)."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP
    )
    docs: list[Document] = []
    for page in extract_pages():
        for chunk in splitter.split_text(page.text):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={"page": page.page, "section": page.section},
                )
            )
    return docs


def build_index(batch_size: int = 64) -> int:
    """(Re)construit l'index vectoriel persistant. Retourne le nb de fragments."""
    if paths.CHROMA_DIR.exists():
        shutil.rmtree(paths.CHROMA_DIR)
    paths.CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    docs = _documents()
    store = Chroma(
        collection_name=COLLECTION,
        embedding_function=_embeddings(),
        persist_directory=str(paths.CHROMA_DIR),
    )
    # Ajout par lots pour rester sous les limites de débit de l'API d'embeddings.
    for i in range(0, len(docs), batch_size):
        store.add_documents(docs[i : i + batch_size])
        print(f"  indexé {min(i + batch_size, len(docs))}/{len(docs)} fragments")

    # Index dédié des légendes de figures/tableaux (pour le tool show_report_figure).
    figures = extract_figures()
    fig_store = Chroma(
        collection_name=FIGURES_COLLECTION,
        embedding_function=_embeddings(),
        persist_directory=str(paths.CHROMA_DIR),
    )
    fig_docs = [
        Document(
            page_content=f.caption,
            metadata={"kind": f.kind, "number": f.number, "page": f.page},
        )
        for f in figures
    ]
    for i in range(0, len(fig_docs), batch_size):
        fig_store.add_documents(fig_docs[i : i + batch_size])
    print(f"  indexé {len(fig_docs)} légendes de figures")
    return len(docs)


def get_store() -> Chroma:
    """Ouvre l'index persistant (lève si absent)."""
    if not paths.CHROMA_DIR.exists():
        raise FileNotFoundError(
            f"Index vectoriel absent ({paths.CHROMA_DIR}). "
            "Lancez `scripts/build-index` pour le générer."
        )
    return Chroma(
        collection_name=COLLECTION,
        embedding_function=_embeddings(),
        persist_directory=str(paths.CHROMA_DIR),
    )


def search(query: str, k: int = 4) -> list[Passage]:
    """Recherche sémantique : renvoie les ``k`` passages les plus proches + source."""
    results = get_store().similarity_search(query, k=k)
    return [
        Passage(
            text=d.page_content,
            page=int(d.metadata.get("page", 0)),
            section=str(d.metadata.get("section", "")),
        )
        for d in results
    ]


def search_figures(query: str, k: int = 1) -> list[Figure]:
    """Recherche les figures/tableaux dont la légende correspond le mieux à la requête."""
    store = Chroma(
        collection_name=FIGURES_COLLECTION,
        embedding_function=_embeddings(),
        persist_directory=str(paths.CHROMA_DIR),
    )
    results = store.similarity_search(query, k=k)
    return [
        Figure(
            kind=str(d.metadata.get("kind", "Figure")),
            number=int(d.metadata.get("number", 0)),
            caption=d.page_content,
            page=int(d.metadata.get("page", 0)),
        )
        for d in results
    ]


if __name__ == "__main__":
    n = build_index()
    print(f"\n✓ Index construit : {n} fragments dans {paths.CHROMA_DIR}")
