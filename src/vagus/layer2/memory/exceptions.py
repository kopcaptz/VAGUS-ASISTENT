"""Специфичные исключения для layer2.memory."""


class ArtifactKBError(Exception):
    """Базовое исключение ArtifactKnowledgeBase."""
    pass


class ArtifactNotFoundError(ArtifactKBError):
    """Артефакт не найден (или недоступен для tenant)."""

    def __init__(self, artifact_id: str):
        super().__init__(f"Artifact not found: {artifact_id}")
        self.artifact_id = artifact_id


class DuplicateRelationshipError(ArtifactKBError):
    """Связь между артефактами уже существует."""

    def __init__(self, source_id: str, target_id: str):
        super().__init__(f"Relationship already exists: {source_id} -> {target_id}")
        self.source_id = source_id
        self.target_id = target_id


class TenantViolationError(ArtifactKBError):
    """Операция нарушает изоляцию tenant."""

    def __init__(self, message: str = "Tenant violation"):
        super().__init__(message)
