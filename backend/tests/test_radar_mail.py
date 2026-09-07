"""论文雷达邮件与远端 CLI 测试。"""

from paper_graph.radar_mail import render_radar_email


def test_render_radar_email_contains_click_url_and_escaped_content():
    html = render_radar_email([
        {
            "title": "A <paper>",
            "authors": ["Author"],
            "abstract": "Summary",
            "score": 0.8,
            "click_url": "https://radar.example/r/1",
        }
    ])
    assert "A &lt;paper&gt;" in html
    assert "https://radar.example/r/1" in html
    assert "标记已读" in html
