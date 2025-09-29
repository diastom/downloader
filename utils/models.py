import hashlib
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Subscription details
    sub_is_active = Column(Boolean, default=False)
    sub_expiry_date = Column(DateTime, nullable=True)
    sub_download_limit = Column(Integer, default=-1)
    sub_encode_limit = Column(Integer, default=-1)
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
    watermarks = relationship(
        "WatermarkSetting",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="WatermarkSetting.id",
    )
    download_records = relationship(
        "DownloadRecord",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="DownloadRecord.id",
    )
    task_usage = relationship(
        "TaskUsage",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="TaskUsage.id",
    )
    purchases = relationship(
        "PurchaseTransaction",
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="PurchaseTransaction.id",
    )


class SubscriptionPlan(Base):
    __tablename__ = "subscription_plans"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    duration_days = Column(Integer, nullable=False)
    download_limit_per_day = Column(Integer, nullable=False, default=-1)
    encode_limit_per_day = Column(Integer, nullable=False, default=-1)
    download_limit = Column(Integer, nullable=False, default=-1)
    encode_limit = Column(Integer, nullable=False, default=-1)
    allowed_sites = Column(JSONB, default=list, nullable=False)
    allow_thumbnail = Column(Boolean, default=False, nullable=False)
    allow_watermark = Column(Boolean, default=False, nullable=False)
    price_toman = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    purchases = relationship(
        "PurchaseTransaction",
        back_populates="plan",
        cascade="all, delete-orphan",
        order_by="PurchaseTransaction.id",
    )


class WalletSetting(Base):
    __tablename__ = "wallet_settings"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    currency_code = Column(String, unique=True, nullable=False)
    address = Column(String, nullable=False)
    explorer_hint = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PurchaseTransaction(Base):
    __tablename__ = "purchase_transactions"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("public.users.id"), nullable=False, index=True)
    plan_id = Column(Integer, ForeignKey("public.subscription_plans.id"), nullable=False, index=True)
    currency_code = Column(String, nullable=False)
    expected_amount = Column(Numeric(24, 8), nullable=False)
    expected_toman = Column(Integer, nullable=False)
    wallet_address = Column(String, nullable=False)
    status = Column(String, default="pending", nullable=False, index=True)
    transaction_hash = Column(String, nullable=True)
    payment_link = Column(String, nullable=True)
    actual_amount = Column(Numeric(24, 8), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    verified_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="purchases")
    plan = relationship("SubscriptionPlan", back_populates="purchases")


class Thumbnail(Base):
    __tablename__ = "thumbnails"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey('public.users.id'), nullable=False)
    file_id = Column(String, nullable=False)
    display_name = Column(String, nullable=True)
    user = relationship("User", back_populates="thumbnails")


class WatermarkSetting(Base):
    __tablename__ = "watermark_settings"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("public.users.id"), nullable=False, index=True)
    display_name = Column(String, nullable=True)
    enabled = Column(Boolean, default=True)
    text = Column(String, default="@YourBot")
    position = Column(String, default="top_left")
    size = Column(Integer, default=32)
    color = Column(String, default="white")
    stroke = Column(Integer, default=2)
    user = relationship("User", back_populates="watermarks")


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


class DownloadRecord(Base):
    __tablename__ = "download_records"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("public.users.id"), nullable=False)
    domain = Column(String, nullable=False)
    bytes_downloaded = Column(BigInteger, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="download_records")


class TaskUsage(Base):
    __tablename__ = "task_usage"
    __table_args__ = {"schema": "public"}

    id = Column(Integer, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("public.users.id"), nullable=False, index=True)
    task_type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = relationship("User", back_populates="task_usage")
