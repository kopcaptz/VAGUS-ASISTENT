"""
Система памяти: Episodic + Semantic + Procedural + ArtifactKnowledgeBase +
ConversationSummarizer + CoherenceMonitor + MemoryManager.
"""

from .artifact_base import ArtifactKnowledgeBaseProtocol
from .artifact_kb import ArtifactKnowledgeBase
from .artifact_kb_pg import ArtifactKnowledgeBasePG
from .coherence import CoherenceMonitor
from .consolidation_handler import MemoryConsolidationHandler
from .exceptions import (
    ArtifactKBError,
    ArtifactNotFoundError,
    DuplicateRelationshipError,
    TenantViolationError,
)
from .episodic import EpisodicMemory
from .manager import MemoryManager
from .procedural import ProceduralMemory, intent_to_summary
from .schemas import ArtifactRecord, ArtifactSearchResult, MemoryEntry
from .semantic import SemanticMemory, sync_episodic_to_semantic
from .summarizer import ConversationSummarizer
from .synaptic_handler import SynapticTrainingHandler

__all__: list[str] = [
    "ArtifactKnowledgeBasePG",
    "ArtifactKBError",
    "ArtifactKnowledgeBase",
    "ArtifactKnowledgeBaseProtocol",
    "ArtifactNotFoundError",
    "ArtifactRecord",
    "ArtifactSearchResult",
    "CoherenceMonitor",
    "DuplicateRelationshipError",
    "ConversationSummarizer",
    "EpisodicMemory",
    "MemoryConsolidationHandler",
    "MemoryEntry",
    "MemoryManager",
    "ProceduralMemory",
    "SemanticMemory",
    "SynapticTrainingHandler",
    "TenantViolationError",
    "intent_to_summary",
    "sync_episodic_to_semantic",
    "create_artifact_kb_from_config",
]


def create_artifact_kb_from_config(
    layer2_config: dict | None,
) -> ArtifactKnowledgeBase | ArtifactKnowledgeBasePG:
    """
    Создаёт ArtifactKnowledgeBase или ArtifactKnowledgeBasePG из layer2.knowledge_base.
    backend: "sqlite" | "postgres"
    """
    kb_cfg = (layer2_config or {}).get("knowledge_base") or {}
    if not isinstance(kb_cfg, dict):
        return ArtifactKnowledgeBase(db_path=":memory:")
    backend = str(kb_cfg.get("backend", "sqlite")).strip().lower()
    if backend == "postgres":
        url = kb_cfg.get("postgres_url") or "postgresql+asyncpg://vagus:vagus_password@localhost:5432/vagus_db"
        return ArtifactKnowledgeBasePG(postgres_url=url)
    sqlite_path = kb_cfg.get("sqlite_path", "data/artifact_kb.db")
    return ArtifactKnowledgeBase(db_path=sqlite_path)
