"""
SQLAlchemy ORM 模型基类和示例模型
"""

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import String, Integer, BigInteger, Text, DateTime, func, SmallInteger
from datetime import datetime
from typing import Optional


class Base(DeclarativeBase):
    """
    所有 ORM 模型的基类

    使用 SQLAlchemy 2.x 的声明式映射风格
    """
    pass


class PDFDocument(Base):
    """
    PDF 文档元数据表 (示例模型)

    用于存储 PDF 文档的基本信息和处理状态
    """
    __tablename__ = "pdf_documents"

    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")

    # 文档基本信息
    doc_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False, index=True, comment="文档唯一标识 (带时间戳)")
    task_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True, comment="任务ID (不带时间戳)")
    file_name: Mapped[str] = mapped_column(String(500), nullable=False, comment="文件名")
    file_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="文件路径")
    file_size: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, comment="文件大小 (字节)")

    # 处理状态
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True, comment="处理状态: pending/processing/completed/failed")

    # 统计信息
    total_pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="总页数")
    total_tables: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="表格数量")
    total_cells: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="单元格数量")

    # Milvus 信息
    milvus_collection: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="Milvus 集合名称")
    milvus_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="Milvus 中的记录数")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="处理完成时间")

    # 错误信息
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")

    def __repr__(self):
        return f"<PDFDocument(id={self.id}, doc_id='{self.doc_id}', status='{self.status}')>"


class ProcessingLog(Base):
    """
    处理日志表 (示例模型)

    用于记录 PDF 处理过程中的关键事件
    """
    __tablename__ = "processing_logs"

    # 主键
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="主键ID")

    # 关联信息
    doc_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True, comment="文档ID")

    # 日志信息
    level: Mapped[str] = mapped_column(String(20), nullable=False, default="info", index=True, comment="日志级别: debug/info/warning/error")
    stage: Mapped[str] = mapped_column(String(50), nullable=False, index=True, comment="处理阶段: extract/convert/vectorize/save")
    message: Mapped[str] = mapped_column(Text, nullable=False, comment="日志消息")
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="详细信息 (JSON)")

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), index=True, comment="创建时间")

    def __repr__(self):
        return f"<ProcessingLog(id={self.id}, doc_id='{self.doc_id}', level='{self.level}', stage='{self.stage}')>"


class ComplianceFileTask(Base):
    """
    合规审查任务表

    用于存储招标文件的合规审查任务信息
    """
    __tablename__ = "compliance_file_task1"

    # 主键
    id: Mapped[str] = mapped_column(String(20), primary_key=True, comment="主键")

    # 文件信息
    file_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="文件ID")
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="文件名称")
    final_file_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="最终文件id (对于需要转化文件格式的转化后文件id)")

    # 项目信息
    project_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="项目名称")
    project_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="项目编号")
    procurement_method: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="采购方式")
    project_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="项目类型")
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="项目概述")

    # 审查状态
    review_status: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="评审状态（1：审查中 2：审查结束 -1:审查失败 3:解析中）"
    )
    review_result: Mapped[Optional[int]] = mapped_column(
        SmallInteger,
        nullable=True,
        comment="评审结果 (0: 无风险 1： 有风险)"
    )

    # 租户信息
    app_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="租户ID")

    # 状态
    status: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, comment="状态")

    # 时间戳
    create_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        comment="创建时间"
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
        comment="更新时间"
    )

    # 用户信息
    create_user: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="创建用户")
    update_user: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, comment="更新用户")
    create_user_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="用户名称")

    def __repr__(self):
        return f"<ComplianceFileTask(id='{self.id}', file_name='{self.file_name}', review_status={self.review_status})>"