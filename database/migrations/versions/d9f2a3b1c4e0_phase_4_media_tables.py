"""Phase 4: media_records and visual_observations tables

Revision ID: d9f2a3b1c4e0
Revises: c48a7391b05e
Create Date: 2026-11-24

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'd9f2a3b1c4e0'
down_revision = 'c48a7391b05e'
branch_labels = None
depends_on = None


def upgrade():
    # media_records
    op.create_table(
        'media_records',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('media_id', sa.String(100), nullable=False, unique=True),
        sa.Column('farmer_id', sa.Integer(), sa.ForeignKey('farmers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('session_id', sa.Integer(), sa.ForeignKey('conversation_sessions.id', ondelete='SET NULL'), nullable=True),
        sa.Column('media_type', sa.String(20), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('file_path', sa.String(255), nullable=True),
        sa.Column('file_size_bytes', sa.Integer(), default=0, nullable=False),
        sa.Column('source_url', sa.String(500), nullable=True),
        sa.Column('caption_text', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), default='PENDING', nullable=False),
        sa.Column('retry_count', sa.Integer(), default=0, nullable=False),
        sa.Column('max_retries', sa.Integer(), default=3, nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('transcription_text', sa.Text(), nullable=True),
        sa.Column('detected_language', sa.String(20), nullable=True),
        sa.Column('transcription_confidence', sa.Float(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('extracted_frame_count', sa.Integer(), default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_media_records_media_id', 'media_records', ['media_id'])
    op.create_index('ix_media_records_farmer_id', 'media_records', ['farmer_id'])
    op.create_index('ix_media_records_status', 'media_records', ['status'])

    # visual_observations
    op.create_table(
        'visual_observations',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('observation_id', sa.String(100), nullable=False, unique=True),
        sa.Column('media_record_id', sa.Integer(), sa.ForeignKey('media_records.id', ondelete='CASCADE'), nullable=False),
        sa.Column('frame_timestamp_sec', sa.Float(), nullable=True),
        sa.Column('frame_index', sa.Integer(), default=0, nullable=False),
        sa.Column('identified_crop', sa.String(100), nullable=True),
        sa.Column('leaf_discoloration', sa.Boolean(), default=False, nullable=False),
        sa.Column('yellowing', sa.Boolean(), default=False, nullable=False),
        sa.Column('spots_lesions', sa.Boolean(), default=False, nullable=False),
        sa.Column('wilting', sa.Boolean(), default=False, nullable=False),
        sa.Column('visible_pest_damage', sa.Boolean(), default=False, nullable=False),
        sa.Column('physical_damage', sa.Boolean(), default=False, nullable=False),
        sa.Column('general_condition', sa.String(100), default='NORMAL', nullable=False),
        sa.Column('observed_symptoms_json', sa.Text(), nullable=True),
        sa.Column('image_quality', sa.String(50), default='GOOD', nullable=False),
        sa.Column('confidence', sa.Float(), default=0.0, nullable=False),
        sa.Column('uncertainty_notes', sa.Text(), nullable=True),
        sa.Column('additional_info_required', sa.Text(), nullable=True),
        sa.Column('recommended_action', sa.String(100), default='ANSWER', nullable=False),
        sa.Column('possible_diagnoses_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_visual_obs_observation_id', 'visual_observations', ['observation_id'])
    op.create_index('ix_visual_obs_media_record_id', 'visual_observations', ['media_record_id'])


def downgrade():
    op.drop_table('visual_observations')
    op.drop_table('media_records')
