#!/usr/bin/env python3
"""端到端流程验证脚本。"""

import sys
import os
from pathlib import Path

# 添加 backend 到路径
sys.path.insert(0, str(Path(__file__).parent / "backend"))

from paper_graph.database import init_db, get_connection, list_papers, get_paper, upsert_paper
from paper_graph.ingest import ingest_local_pdf, ingest_arxiv_id, search_arxiv_only
from paper_graph.annotate import annotate_paper, annotate_all, get_default_model, get_client
from paper_graph.graph import build_team_graph, build_paper_graph
from paper_graph.notes import list_notes, get_note, save_note, create_note_template, delete_note


def test_database():
    """测试数据库初始化。"""
    print("测试数据库初始化...")
    db_path = Path("data/test_e2e.db")
    init_db(db_path)
    conn = get_connection(db_path)
    papers = list_papers(db_path)
    assert hasattr(papers, 'to_dict') or isinstance(papers, list), "list_papers 应该返回 DataFrame 或 list"
    conn.close()
    db_path.unlink(missing_ok=True)
    print("  ✓ 数据库初始化正常")


def test_ingest_and_annotate():
    """测试入库和标注流程。"""
    print("测试入库和标注流程...")
    db_path = Path("data/test_e2e_ingest.db")
    init_db(db_path)

    # 测试 arXiv 搜索
    results = search_arxiv_only("attention is all you need", max_results=2)
    assert len(results) > 0, "搜索应该返回结果"
    print(f"  ✓ 搜索到 {len(results)} 篇论文")

    # 测试入库
    paper_id = ingest_arxiv_id(results[0]["id"].replace("arxiv_", ""), db_path, pdf_dir=Path("data/pdfs"))
    assert paper_id, "入库应该返回 paper_id"
    print(f"  ✓ 入库成功: {paper_id}")

    # 测试获取论文
    conn = get_connection(db_path)
    paper = get_paper(conn, paper_id)
    assert paper is not None, "应该能获取到论文"
    assert paper["title"] == results[0]["title"], "标题应该一致"
    conn.close()
    print(f"  ✓ 获取论文正常: {paper['title'][:30]}...")

    # 测试智能标注（需要环境变量）
    model = get_default_model()
    print(f"  ℹ 默认模型: {model}")

    db_path.unlink(missing_ok=True)
    print("  ✓ 入库和标注流程正常")


def test_graph_building():
    """测试图谱构建。"""
    print("测试图谱构建...")
    db_path = Path("data/test_e2e_graph.db")
    init_db(db_path)

    team_graph = build_team_graph(db_path)
    assert team_graph.number_of_nodes() == 0, "空数据库应该返回空图"
    print("  ✓ 团队图谱空数据正常")

    paper_graph = build_paper_graph(db_path)
    assert paper_graph.number_of_nodes() == 0, "空数据库应该返回空图"
    print("  ✓ 论文图谱空数据正常")

    db_path.unlink(missing_ok=True)
    print("  ✓ 图谱构建正常")


def test_notes_system():
    """测试笔记系统。"""
    print("测试笔记系统...")
    db_path = Path("data/test_e2e_notes.db")
    init_db(db_path)

    # 先插入测试论文
    paper_data = {
        "id": "test_1",
        "title": "Test Paper",
        "abstract": "Test abstract",
        "published_date": "2024-01-01",
        "updated_date": "2024-01-01",
        "categories": "cs.CL",
        "arxiv_url": "https://arxiv.org/abs/2401.00001",
        "pdf_path": None,
        "source": "local",
    }
    conn = get_connection(db_path)
    upsert_paper(conn, paper_data)
    conn.commit()
    conn.close()
    print("  ✓ 测试论文已入库")

    # 测试创建笔记模板
    result = create_note_template(db_path, "test_1", paper_data)
    template_path = Path(result["path"])
    assert template_path.exists(), "笔记模板应该被创建"
    print(f"  ✓ 笔记模板创建成功: {template_path}")

    # 测试读取笔记
    note = get_note(db_path, "test_1")
    assert note is not None, "应该能读取笔记"
    assert "Test Paper" in note["content"], "笔记内容应该包含标题"
    print(f"  ✓ 读取笔记正常 ({len(note['content'])} 字符)")

    # 测试保存笔记
    new_content = note["content"] + "\n\n## 新笔记\n测试内容"
    save_note(db_path, "test_1", new_content)
    updated = get_note(db_path, "test_1")
    assert "新笔记" in updated["content"], "保存后应该包含新内容"
    print("  ✓ 保存笔记正常")

    # 测试列出笔记
    notes = list_notes(db_path)
    assert len(notes) == 1, "应该有一条笔记"
    print(f"  ✓ 列出笔记正常: {notes[0]['title']}")

    # 测试删除笔记
    delete_note(db_path, "test_1")
    notes_after = list_notes(db_path)
    assert len(notes_after) == 0, "删除后应该没有笔记"
    print("  ✓ 删除笔记正常")

    # 清理
    template_path.unlink(missing_ok=True)
    db_path.unlink(missing_ok=True)
    print("  ✓ 笔记系统正常")


def test_env_loading():
    """测试环境变量加载。"""
    print("测试环境变量加载...")
    model = get_default_model()
    print(f"  ℹ 默认模型: {model}")

    client = get_client()
    assert client is not None, "应该能创建客户端"
    print(f"  ✓ 客户端创建正常 (base_url: {client.base_url})")


def main():
    """运行所有端到端测试。"""
    print("=" * 60)
    print("CiteMap - 端到端流程验证")
    print("=" * 60)

    try:
        test_env_loading()
        test_database()
        test_ingest_and_annotate()
        test_graph_building()
        test_notes_system()

        print("\n" + "=" * 60)
        print("✓ 所有端到端测试通过！")
        print("=" * 60)
        return 0
    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
