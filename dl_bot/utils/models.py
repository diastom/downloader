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

from .db_session import Base

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True) # Telegram User ID
    username = Column(String)
    is_admin = Column(Boolean, default=False)

    # Subscription details
    sub_is_active = Column(Boolean, default=False)
    sub_expiry_date = Column(DateTime, nullable=True)
    sub_download_limit = Column(Integer, default=-1) # -1 for unlimited

    # JSONB for flexible data structures
    sub_allowed_sites = Column(JSONB) # e.g., {"toonily.com": true, ...}
    stats_site_usage = Column(JSONB) # e.g., {"toonily.com": 10, ...}

    personal_archive_id = Column(BigInteger, nullable=True)

    # Relationships
    thumbnail = relationship("Thumbnail", back_populates="user", uselist=False, cascade="all, delete-orphan")
    watermark = relationship("WatermarkSetting", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Thumbnail(Base):
    __tablename__ = "thumbnails"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    file_id = Column(String, nullable=False)

    user = relationship("User", back_populates="thumbnail")

class WatermarkSetting(Base):
    __tablename__ = "watermark_settings"

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)

    enabled = Column(Boolean, default=False)
    text = Column(String, default="@YourBot")
    position = Column(String, default="top_left")
    size = Column(Integer, default=32)
    color = Column(String, default="white")
    stroke = Column(Integer, default=2)

    user = relationship("User", back_populates="watermark")

class VideoCache(Base):
    __tablename__ = "video_cache"

    id = Column(Integer, primary_key=True)
    video_url = Column(String, index=True)
    format_id = Column(String)
    message_id = Column(BigInteger)

class BotText(Base):
    __tablename__ = "bot_texts"

    key = Column(String, primary_key=True, index=True) # e.g., "help_text"
    value = Column(String, nullable=False)
