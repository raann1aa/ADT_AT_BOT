"""Phase 3 schema: conversation messages, transactional outbox, and field history

Revision ID: c48a7391b05e
Revises: fd75e8e4759e
Create Date: 2026-11-24 12:18:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c48a7391b05e'
down_revision: Union[str, Sequence[str], None] = 'fd75e8e4759e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema for Phase 3 entities."""
    # 1. conversation_messages table
    op.create_table(
        'conversation_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('sender_role', sa.String(length=50), nullable=False),
        sa.Column('message_text', sa.Text(), nullable=False),
        sa.Column('intent', sa.String(length=100), nullable=True),
        sa.Column('entities', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['session_id'], ['conversation_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('conversation_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_conversation_messages_session_id'), ['session_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_conversation_messages_intent'), ['intent'], unique=False)

    # 2. outbox_messages table
    op.create_table(
        'outbox_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('outbox_id', sa.String(length=100), nullable=False),
        sa.Column('recipient_phone', sa.String(length=20), nullable=False),
        sa.Column('message_text', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('dispatched_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('outbox_messages', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_outbox_messages_outbox_id'), ['outbox_id'], unique=True)
        batch_op.create_index(batch_op.f('ix_outbox_messages_recipient_phone'), ['recipient_phone'], unique=False)
        batch_op.create_index(batch_op.f('ix_outbox_messages_status'), ['status'], unique=False)
        batch_op.create_index(batch_op.f('ix_outbox_messages_idempotency_key'), ['idempotency_key'], unique=False)

    # 3. field_history table
    op.create_table(
        'field_history',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=False),
        sa.Column('field_name', sa.String(length=100), nullable=False),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),
        sa.Column('changed_by', sa.String(length=100), nullable=False, server_default='SYSTEM'),
        sa.Column('change_source', sa.String(length=100), nullable=False, server_default='WHATSAPP_CHAT'),
        sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('field_history', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_field_history_entity_type'), ['entity_type'], unique=False)
        batch_op.create_index(batch_op.f('ix_field_history_entity_id'), ['entity_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_field_history_field_name'), ['field_name'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('field_history')
    op.drop_table('outbox_messages')
    op.drop_table('conversation_messages')
