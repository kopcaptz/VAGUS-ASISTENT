"""create_lessons_table

Revision ID: 20260223_121829
Revises: 15aaeca8f68f
Create Date: 2026-02-23 12:18:29.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260223_121829'
down_revision: Union[str, Sequence[str], None] = '15aaeca8f68f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: create lessons table."""
    op.create_table(
        'lessons',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('tenant_id', sa.Text(), nullable=False),
        sa.Column('original_prompt_hash', sa.Text(), nullable=False),
        sa.Column('agent_type', sa.Text(), nullable=False),
        sa.Column('issues', sa.Text(), nullable=False),
        sa.Column('suggestions', sa.Text(), nullable=False),
        sa.Column('refined_prompt', sa.Text(), nullable=False),
        sa.Column('score_before', sa.Float(), nullable=False),
        sa.Column('score_after', sa.Float(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), server_default=sa.func.now()),
        sa.Index('idx_lessons_tenant_agent_hash', 'tenant_id', 'agent_type', 'original_prompt_hash'),
        sa.Index('idx_lessons_tenant_created', 'tenant_id', 'created_at'),
    )


def downgrade() -> None:
    """Downgrade schema: drop lessons table."""
    op.drop_table('lessons')
