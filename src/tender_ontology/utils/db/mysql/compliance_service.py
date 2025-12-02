"""
合规审查服务类

负责接收 PDF 文件并创建合规审查任务
"""

from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
import uuid
import os

from .mysql_util import MySQLUtil
from .models import ComplianceFileTask


class ComplianceService:
    """
    合规审查服务类

    功能:
    1. 接收 PDF 文件
    2. 在数据库中创建审查任务记录
    3. 更新任务状态
    """

    def __init__(self, mysql_util: MySQLUtil):
        """
        初始化服务

        Args:
            mysql_util: MySQL 工具类实例
        """
        self.mysql = mysql_util

    def generate_task_id(self) -> str:
        """
        生成任务ID (20位字符串)

        Returns:
            任务ID (格式: 时间戳 + 随机数)
        """
        timestamp = datetime.now().strftime("%y%m%d%H%M%S")  # 12位
        random_part = str(uuid.uuid4().int)[:8]  # 8位随机数
        return timestamp + random_part

    def create_task_from_pdf(
        self,
        pdf_path: Optional[str] = None,
        file_id: Optional[str] = None,
        project_name: Optional[str] = None,
        project_code: Optional[str] = None,
        procurement_method: Optional[str] = None,
        project_type: Optional[str] = None,
        overview: Optional[str] = None,
        app_id: Optional[str] = None,
        create_user: Optional[str] = None,
        create_user_name: Optional[str] = None
    ) -> ComplianceFileTask:
        """
        接收 PDF 文件并创建审查任务

        Args:
            pdf_path: PDF 文件路径（可选，如果为None则稍后更新）
            file_id: 文件ID (可选, 如不提供则自动生成)
            project_name: 项目名称
            project_code: 项目编号
            procurement_method: 采购方式
            project_type: 项目类型
            overview: 项目概述
            app_id: 租户ID
            create_user: 创建用户ID
            create_user_name: 创建用户名称

        Returns:
            创建的任务对象

        Raises:
            Exception: 数据库插入失败

        示例:
            service = ComplianceService(mysql_util)
            task = service.create_task_from_pdf(
                pdf_path="/path/to/file.pdf",
                project_name="政府采购项目",
                app_id="tenant_001",
                create_user="user_001",
                create_user_name="张三"
            )
            print(f"任务创建成功, ID: {task.id}")
        """
        # 1. 验证 PDF 文件存在（如果提供了路径）
        file_name = None
        if pdf_path:
            pdf_file = Path(pdf_path)
            if not pdf_file.exists():
                raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
            # 3. 获取文件名
            file_name = pdf_file.name

        # 2. 生成任务ID和文件ID
        task_id = self.generate_task_id()
        if not file_id:
            file_id = self.generate_task_id()

        # 4. 创建任务对象
        task = ComplianceFileTask(
            id=task_id,
            file_id=file_id,
            file_name=file_name,
            project_name=project_name,
            project_code=project_code,
            procurement_method=procurement_method,
            project_type=project_type,
            overview=overview,
            review_status=3,  # 3: 解析中
            review_result=None,
            app_id=app_id,
            status=1,
            create_user=create_user,
            create_user_name=create_user_name
        )

        # 5. 插入数据库
        saved_task = self.mysql.insert_one(task)

        print(f"[合规审查] [OK] 任务创建成功: {saved_task.id}")
        print(f"[合规审查]   文件: {file_name}")
        print(f"[合规审查]   项目: {project_name or '未指定'}")
        print(f"[合规审查]   状态: 解析中")

        return saved_task

    def update_task_status(
        self,
        task_id: str,
        review_status: Optional[int] = None,
        review_result: Optional[int] = None,
        final_file_id: Optional[str] = None,
        update_user: Optional[str] = None,
        **kwargs
    ) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务ID
            review_status: 评审状态 (1:审查中 2:审查结束 -1:审查失败 3:解析中)
            review_result: 评审结果 (0:无风险 1:有风险)
            final_file_id: 最终文件ID
            update_user: 更新用户ID
            **kwargs: 其他要更新的字段

        Returns:
            是否更新成功

        示例:
            # 更新为审查中
            service.update_task_status(task_id, review_status=1)

            # 更新为审查结束,有风险
            service.update_task_status(task_id, review_status=2, review_result=1)

            # 更新为解析失败
            service.update_task_status(task_id, review_status=-1)
        """
        update_fields = {}

        if review_status is not None:
            update_fields['review_status'] = review_status

        if review_result is not None:
            update_fields['review_result'] = review_result

        if final_file_id is not None:
            update_fields['final_file_id'] = final_file_id

        if update_user is not None:
            update_fields['update_user'] = update_user

        # 合并其他字段
        update_fields.update(kwargs)

        if not update_fields:
            print(f"[合规审查] [WARN] 没有需要更新的字段")
            return False

        # 更新数据库
        success = self.mysql.update_by_id(ComplianceFileTask, task_id, **update_fields)

        if success:
            print(f"[合规审查] [OK] 任务 {task_id} 状态更新成功")
        else:
            print(f"[合规审查] [FAIL] 任务 {task_id} 不存在或更新失败")

        return success

    def get_task(self, task_id: str) -> Optional[ComplianceFileTask]:
        """
        根据任务ID查询任务

        Args:
            task_id: 任务ID

        Returns:
            任务对象或 None
        """
        return self.mysql.get_by_id(ComplianceFileTask, task_id)

    def get_tasks_by_status(self, review_status: int, limit: int = 100) -> list:
        """
        根据评审状态查询任务列表

        Args:
            review_status: 评审状态
            limit: 限制返回数量

        Returns:
            任务列表

        示例:
            # 查询所有解析中的任务
            parsing_tasks = service.get_tasks_by_status(review_status=3)
        """
        tasks = self.mysql.filter_by(ComplianceFileTask, review_status=review_status)
        return tasks[:limit]

    def get_tasks_by_app_id(self, app_id: str, limit: int = 100) -> list:
        """
        根据租户ID查询任务列表

        Args:
            app_id: 租户ID
            limit: 限制返回数量

        Returns:
            任务列表
        """
        tasks = self.mysql.filter_by(ComplianceFileTask, app_id=app_id)
        return tasks[:limit]

    def count_tasks_by_status(self, review_status: int) -> int:
        """
        统计指定状态的任务数量

        Args:
            review_status: 评审状态

        Returns:
            任务数量
        """
        return self.mysql.count(ComplianceFileTask, review_status=review_status)


# 使用示例
def example():
    """
    使用示例
    """
    # 1. 初始化 MySQL 连接
    mysql = MySQLUtil(
        host="localhost",
        port=3306,
        user="root",
        password="your_password",
        database="compliance_db",
        charset="utf8mb4"
    )

    # 2. 初始化服务
    service = ComplianceService(mysql)

    # 3. 接收 PDF 并创建任务
    print("\n=== 创建任务 ===")
    task = service.create_task_from_pdf(
        pdf_path="/path/to/招标文件.pdf",
        project_name="政府网站群集约化平台升级改造项目",
        project_code="PRJ-2025-001",
        procurement_method="公开招标",
        project_type="信息化建设",
        overview="对政府网站进行集约化平台升级改造",
        app_id="tenant_001",
        create_user="user_001",
        create_user_name="张三"
    )

    # 4. 查询任务
    print("\n=== 查询任务 ===")
    found_task = service.get_task(task.id)
    print(f"任务ID: {found_task.id}")
    print(f"文件名: {found_task.file_name}")
    print(f"项目名称: {found_task.project_name}")
    print(f"评审状态: {found_task.review_status}")

    # 5. 更新任务状态 (模拟解析完成,开始审查)
    print("\n=== 更新状态: 解析完成,开始审查 ===")
    service.update_task_status(
        task.id,
        review_status=1,  # 审查中
        update_user="user_001"
    )

    # 6. 更新任务状态 (模拟审查完成,有风险)
    print("\n=== 更新状态: 审查完成,有风险 ===")
    service.update_task_status(
        task.id,
        review_status=2,  # 审查结束
        review_result=1,  # 有风险
        update_user="user_001"
    )

    # 7. 查询所有解析中的任务
    print("\n=== 查询所有解析中的任务 ===")
    parsing_tasks = service.get_tasks_by_status(review_status=3)
    print(f"解析中的任务数: {len(parsing_tasks)}")

    # 8. 统计
    print("\n=== 统计 ===")
    total = mysql.count(ComplianceFileTask)
    parsing = service.count_tasks_by_status(review_status=3)
    reviewing = service.count_tasks_by_status(review_status=1)
    completed = service.count_tasks_by_status(review_status=2)
    failed = service.count_tasks_by_status(review_status=-1)

    print(f"总任务数: {total}")
    print(f"解析中: {parsing}")
    print(f"审查中: {reviewing}")
    print(f"审查结束: {completed}")
    print(f"审查失败: {failed}")

    # 9. 关闭连接
    mysql.close()


if __name__ == "__main__":
    example()