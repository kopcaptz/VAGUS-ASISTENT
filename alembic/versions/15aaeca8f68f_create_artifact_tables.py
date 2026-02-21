"""create_artifact_tables

Revision ID: 15aaeca8f68f
Revises: 
Create Date: 2026-02-21 15:08:33.396631

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '15aaeca8f68f'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: artifacts and artifact_relationships for ArtifactKnowledgeBase."""
    op.create_table(
        "artifacts",
        sa.Column("artifact_id", sa.Text(), primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("plan_id", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("content_json", sa.Text(), nullable=False),
        sa.Column("artifact_type", sa.Text()),
        sa.Column("agent_type", sa.Text()),
        sa.Column("session_id", sa.Text()),
        sa.Column("source", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Column("ttl_seconds", sa.Integer()),
    )
    op.create_index("idx_artifacts_tenant", "artifacts", ["tenant_id"])

    op.create_table(
        "artifact_relationships",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("tenant_id", sa.Text(), nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("rel_type", sa.Text(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.UniqueConstraint("source_id", "target_id", "tenant_id", name="uq_artifact_rel"),
    )
    op.create_index("idx_relationships_tenant", "artifact_relationships", ["tenant_id"])


def downgrade() -> None:
    """Downgrade schema: drop artifact tables."""
    op.drop_index("idx_relationships_tenant", "artifact_relationships")
    op.drop_table("artifact_relationships")
    op.drop_index("idx_artifacts_tenant", "artifacts")
    op.drop_table("artifacts")
