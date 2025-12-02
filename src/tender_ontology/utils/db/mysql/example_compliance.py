"""
合规审查服务使用示例

演示如何使用 ComplianceService 处理 PDF 文件并创建审查任务
"""

from mysql_util import MySQLUtil
from compliance_service import ComplianceService


def main():
    """
    完整的使用流程示例
    """
    print("="*80)
    print("合规审查服务使用示例")
    print("="*80)

    # ========== 1. 初始化数据库连接 ==========
    print("\n[步骤 1] 初始化 MySQL 连接...")

    # TODO: 替换为你的数据库连接信息
    mysql = MySQLUtil(
        host="localhost",      # 数据库主机
        port=3306,             # 数据库端口
        user="root",           # 数据库用户名
        password="your_password",  # 数据库密码
        database="compliance_db",  # 数据库名称
        charset="utf8mb4",
        echo=False  # 设为 True 可以打印 SQL 语句
    )

    # 创建表 (如果表不存在)
    # mysql.create_tables(drop_existing=False)

    # ========== 2. 初始化服务 ==========
    print("\n[步骤 2] 初始化合规审查服务...")
    service = ComplianceService(mysql)

    # ========== 3. 接收 PDF 并创建任务 ==========
    print("\n[步骤 3] 接收 PDF 文件并创建审查任务...")

    # TODO: 替换为实际的 PDF 文件路径
    pdf_path = r"E:\programFile\AIProgram\docxServer\pdf\task\test\test.pdf"

    try:
        task = service.create_task_from_pdf(
            pdf_path=pdf_path,
            file_id=None,  # 自动生成
            project_name="政府网站群集约化平台升级改造项目",
            project_code="PRJ-2025-001",
            procurement_method="公开招标",
            project_type="信息化建设",
            overview="对鄂尔多斯市政府网站进行集约化平台升级改造，提升用户体验和服务能力",
            app_id="tenant_001",
            create_user="user_001",
            create_user_name="张三"
        )

        print(f"\n✓ 任务创建成功!")
        print(f"  任务ID: {task.id}")
        print(f"  文件ID: {task.file_id}")
        print(f"  文件名: {task.file_name}")
        print(f"  项目名称: {task.project_name}")
        print(f"  评审状态: {task.review_status} (3=解析中)")

    except FileNotFoundError as e:
        print(f"\n✗ 错误: {e}")
        print("  请修改 pdf_path 为实际的 PDF 文件路径")
        return

    # ========== 4. 查询任务 ==========
    print("\n[步骤 4] 查询任务详情...")
    found_task = service.get_task(task.id)
    if found_task:
        print(f"✓ 查询成功:")
        print(f"  任务ID: {found_task.id}")
        print(f"  文件名: {found_task.file_name}")
        print(f"  项目名称: {found_task.project_name}")
        print(f"  项目编号: {found_task.project_code}")
        print(f"  采购方式: {found_task.procurement_method}")
        print(f"  项目类型: {found_task.project_type}")
        print(f"  评审状态: {found_task.review_status}")
        print(f"  创建时间: {found_task.create_time}")

    # ========== 5. 模拟处理流程 ==========
    print("\n[步骤 5] 模拟任务处理流程...")

    # 5.1 解析完成，开始审查
    print("\n  5.1 解析完成，更新状态为'审查中'...")
    service.update_task_status(
        task.id,
        review_status=1,  # 1: 审查中
        update_user="user_001"
    )

    # 5.2 审查完成，发现风险
    print("\n  5.2 审查完成，更新状态为'审查结束，有风险'...")
    service.update_task_status(
        task.id,
        review_status=2,  # 2: 审查结束
        review_result=1,  # 1: 有风险
        update_user="user_001"
    )

    # 5.3 再次查询任务
    print("\n  5.3 查询更新后的任务状态...")
    updated_task = service.get_task(task.id)
    print(f"  评审状态: {updated_task.review_status} (2=审查结束)")
    print(f"  评审结果: {updated_task.review_result} (1=有风险)")
    print(f"  更新时间: {updated_task.update_time}")

    # ========== 6. 查询任务列表 ==========
    print("\n[步骤 6] 查询不同状态的任务列表...")

    # 查询解析中的任务
    parsing_tasks = service.get_tasks_by_status(review_status=3)
    print(f"\n  解析中的任务: {len(parsing_tasks)} 个")

    # 查询审查中的任务
    reviewing_tasks = service.get_tasks_by_status(review_status=1)
    print(f"  审查中的任务: {len(reviewing_tasks)} 个")

    # 查询审查结束的任务
    completed_tasks = service.get_tasks_by_status(review_status=2)
    print(f"  审查结束的任务: {len(completed_tasks)} 个")
    for t in completed_tasks[:5]:  # 只显示前5个
        print(f"    - {t.file_name} (结果: {t.review_result})")

    # 查询指定租户的任务
    tenant_tasks = service.get_tasks_by_app_id(app_id="tenant_001")
    print(f"\n  租户 tenant_001 的任务: {len(tenant_tasks)} 个")

    # ========== 7. 统计信息 ==========
    print("\n[步骤 7] 统计信息...")
    from models import ComplianceFileTask

    total = mysql.count(ComplianceFileTask)
    parsing = service.count_tasks_by_status(review_status=3)
    reviewing = service.count_tasks_by_status(review_status=1)
    completed = service.count_tasks_by_status(review_status=2)
    failed = service.count_tasks_by_status(review_status=-1)
    no_risk = mysql.count(ComplianceFileTask, review_result=0)
    has_risk = mysql.count(ComplianceFileTask, review_result=1)

    print(f"\n  总任务数: {total}")
    print(f"  解析中: {parsing}")
    print(f"  审查中: {reviewing}")
    print(f"  审查结束: {completed}")
    print(f"  审查失败: {failed}")
    print(f"\n  无风险: {no_risk}")
    print(f"  有风险: {has_risk}")

    # ========== 8. 关闭连接 ==========
    print("\n[步骤 8] 关闭数据库连接...")
    mysql.close()

    print("\n" + "="*80)
    print("示例执行完成!")
    print("="*80)


if __name__ == "__main__":
    main()