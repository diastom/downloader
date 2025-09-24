from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    BigInteger,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from utils.db_session import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = {"schema": "public"}

    id = Column(BigInteger, primary_key=True)
    username = Column(String)
    is_admin = Column(Boolean, default=False)

    # Subscription details
    sub_is_active = Column(Boolean, default=False)
    sub_expiry_date = Column(DateTime, nullable=True)
    sub_download_limit = Column(Integer, default=-1)

    # --- START OF CORRECTION ---
    # Kept the original column for site access
    sub_allowed_sites = Column(JSONB) 
    
    # Added new, separate boolean flags for feature access
    allow_thumbnail = Column(Boolean, default=True, nullable=False)
    allow_watermark = Column(Boolean, default=True, nullable=False)
    # --- END OF CORRECTION ---

    stats_site_usage = Column(JSONB)
    personal_archive_id = Column(BigInteger, nullable=True)

    # Relationships
    thumbnail = relationship("Thumbnail", back_populates="user", uselist=False)
    watermark = relationship("WatermarkSetting", back_populates="user", uselist=False)


class Thumbnail(Base):
    __tablename__ = "thumbnails"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('public.users.id'), nullable=False)
    file_id = Column(String, nullable=False)
    user = relationship("User", back_populates="thumbnail")


class WatermarkSetting(Base):
    __tablename__ = "watermark_settings"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("public.users.id"), unique=True, nullable=False)
    enabled = Column(Boolean, default=False)
    text = Column(String, default="@YourBot")
    position = Column(String, default="top_left")
    size = Column(Integer, default=32)
    color = Column(String, default="white")
    stroke = Column(Integer, default=2)
    user = relationship("User", back_populates="watermark")


class VideoCache(Base):
    __tablename__ = "video_cache"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    video_url = Column(String, index=True, nullable=True)
    format_id = Column(String, nullable=True)
    message_id = Column(BigInteger, nullable=True)


class BotText(Base):
    __tablename__ = "bot_texts"
    __table_args__ = {"schema": "public"}
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)

