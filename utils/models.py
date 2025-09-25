import hashlib
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
    sub_allowed_sites = Column(JSONB)

    allow_thumbnail = Column(Boolean, default=True, nullable=False)
    allow_watermark = Column(Boolean, default=True, nullable=False)

    stats_site_usage = Column(JSONB)

    # Relationships
    thumbnails = relationship(
        "Thumbnail",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="Thumbnail.id",
    )
    watermark = relationship("WatermarkSetting", back_populates="user", uselist=False)


class Thumbnail(Base):
    __tablename__ = "thumbnails"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('public.users.id'), nullable=False)
    file_id = Column(String, nullable=False)
    user = relationship("User", back_populates="thumbnails")


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


class UrlCache(Base):
    """ Caches information about a specific video URL and format. """
    __tablename__ = "url_cache" # Renamed from video_cache
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    video_url = Column(String, index=True, nullable=True)
    format_id = Column(String, nullable=True)
    message_id = Column(BigInteger, nullable=True)


class PublicArchive(Base):
    """ Stores a record of a downloaded video to prevent duplicates. """
    __tablename__ = "public_archive"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    url_hash = Column(String, unique=True, index=True, nullable=False)
    message_id = Column(BigInteger, nullable=False)
    channel_id = Column(BigInteger, nullable=False)

    @staticmethod
    def create_hash(url: str) -> str:
        """Creates a SHA256 hash of a given URL."""
        return hashlib.sha256(url.encode('utf-8')).hexdigest()


class BotText(Base):
    __tablename__ = "bot_texts"
    __table_args__ = {"schema": "public"}
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)