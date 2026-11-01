"""step 5: position annotations, outlet_position.detalle

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-01 00:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSON = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')


def upgrade() -> None:
    op.add_column('outlet_position', sa.Column('detalle', JSON, nullable=True))
    op.create_table(
        'position_annotation',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('article_id', sa.Integer(), sa.ForeignKey('article.id'), nullable=False),
        sa.Column('event_id', sa.Integer(), sa.ForeignKey('event.id'), nullable=True),
        sa.Column('cleavage_id', sa.Integer(), sa.ForeignKey('cleavage.id'), nullable=False),
        sa.Column('codificador', sa.String(length=120), nullable=False),
        sa.Column('prompt_version', sa.String(length=40), nullable=False),
        sa.Column('valor', sa.Integer(), nullable=True),
        sa.Column('run_id', sa.Integer(), sa.ForeignKey('agent_run.id'), nullable=True),
        sa.Column('creado_en', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('article_id', 'cleavage_id', 'codificador', 'prompt_version'),
        sa.CheckConstraint('valor IS NULL OR (valor >= -2 AND valor <= 2)', name='ck_pa_valor'),
    )
    op.create_index('ix_position_annotation_cleavage', 'position_annotation', ['cleavage_id', 'codificador'])


def downgrade() -> None:
    op.drop_index('ix_position_annotation_cleavage', table_name='position_annotation')
    op.drop_table('position_annotation')
    op.drop_column('outlet_position', 'detalle')
