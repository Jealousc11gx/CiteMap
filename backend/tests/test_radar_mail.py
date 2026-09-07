"""论文雷达邮件与远端 CLI 测试。"""

from paper_graph.radar_mail import render_radar_email


def test_render_radar_email_contains_click_url_and_escaped_content():
    html = render_radar_email([
        {
            "title": "A <paper>",
            "title_zh": "中文标题",
            "authors": ["Author"],
            "abstract": "Summary",
            "ai_summary": "中文 AI 摘要",
            "affiliations": ["Example University"],
            "corresponding_authors": ["Author"],
            "score": 0.8,
            "click_url": "https://radar.example/r/1",
        }
    ])
    assert "A &lt;paper&gt;" in html
    assert "中文标题" in html
    assert "中文 AI 摘要" in html
    assert "Example University" in html
    assert "通讯作者" in html
    assert "https://radar.example/r/1" in html
    assert "标记已读" in html


def test_render_radar_email_does_not_label_english_abstract_as_ai_summary():
    html = render_radar_email([{"title": "Paper", "authors": [], "abstract": "English abstract"}])
    assert "暂无中文 AI 摘要" in html
    assert "English abstract" not in html
