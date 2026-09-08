"""论文雷达邮件内容与 SMTP 发送。"""

from __future__ import annotations

import html
import os
import smtplib
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr


def _join_values(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if str(item).strip())
    return str(value or "")


def render_radar_email(items: list[dict], *, title: str = "CiteMap 论文雷达") -> str:
    blocks = []
    for item in items:
        link = html.escape(str(item.get("click_url") or item.get("arxiv_url") or "#"), quote=True)
        original_title = html.escape(str(item.get("title") or "无标题"))
        chinese_title = html.escape(str(item.get("title_zh") or ""))
        paper_title = chinese_title or original_title
        original_title_block = f'<div style="color:#666;font-size:13px;margin-top:4px">{original_title}</div>' if chinese_title else ""
        authors = html.escape(", ".join(item.get("authors") or []))
        tldr = html.escape(str(item.get("tldr") or "暂无 TLDR"))
        summary = html.escape(str(item.get("ai_summary") or item.get("abstract_zh") or "暂无中文 AI 摘要"))
        affiliations = html.escape(_join_values(item.get("affiliations")) or "未从论文首页识别")
        corresponding_authors = html.escape(_join_values(item.get("corresponding_authors")) or "未明确标注")
        contribution = html.escape(str(item.get("core_contribution") or ""))
        contribution_block = f'<p style="font-size:14px;line-height:1.6"><strong>核心贡献：</strong>{contribution}</p>' if contribution else ""
        score = item.get("score")
        score_text = f"{float(score):.3f}" if score is not None else "未知"
        blocks.append(
            f"""
            <article style=\"border:1px solid #ddd;border-radius:8px;padding:16px;margin:12px 0;font-family:Arial,sans-serif\">
              <h2 style=\"font-size:18px;margin:0 0 8px\"><a href=\"{link}\">{paper_title}</a></h2>
              {original_title_block}
              <div style=\"color:#666;font-size:13px\">{authors}</div>
              <div style=\"color:#666;font-size:13px;margin-top:6px\"><strong>机构：</strong>{affiliations}</div>
              <div style=\"color:#666;font-size:13px;margin-top:4px\"><strong>通讯作者：</strong>{corresponding_authors}</div>
              <div style=\"color:#555;font-size:13px;margin-top:8px\">匹配分数：{score_text}</div>
              <p style=\"font-size:14px;line-height:1.6\"><strong>TLDR：</strong>{tldr}</p>
              <p style=\"font-size:14px;line-height:1.6\"><strong>AI 摘要：</strong>{summary}</p>
              {contribution_block}
              <a href=\"{link}\">查看论文并标记已读</a>
            </article>
            """
        )
    content = "".join(blocks) or "<p>今天没有新的论文推荐。</p>"
    return f"<html><body><h1>{html.escape(title)}</h1>{content}</body></html>"


def send_radar_email(items: list[dict], *, subject: str = "CiteMap 论文雷达", title: str | None = None) -> None:
    sender = os.environ.get("RADAR_EMAIL_SENDER", "").strip()
    receiver = os.environ.get("RADAR_EMAIL_RECEIVER", "").strip()
    password = os.environ.get("RADAR_EMAIL_PASSWORD", "").strip()
    host = os.environ.get("RADAR_SMTP_HOST", "").strip()
    port = int(os.environ.get("RADAR_SMTP_PORT", "465"))
    if not all((sender, receiver, password, host)):
        raise RuntimeError("未配置完整的 RADAR_EMAIL_SENDER / RADAR_EMAIL_RECEIVER / RADAR_EMAIL_PASSWORD / RADAR_SMTP_HOST")

    msg = MIMEText(render_radar_email(items, title=title or "CiteMap 论文雷达"), "html", "utf-8")
    name, address = parseaddr(sender)
    msg["From"] = formataddr((Header(name or "CiteMap Radar", "utf-8").encode(), address))
    msg["To"] = receiver
    msg["Subject"] = Header(subject, "utf-8").encode()
    try:
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(sender, password)
            server.sendmail(sender, [receiver], msg.as_string())
    except Exception as ssl_error:
        try:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls()
                server.login(sender, password)
                server.sendmail(sender, [receiver], msg.as_string())
        except Exception as error:
            raise RuntimeError(f"雷达邮件发送失败: SSL={ssl_error}; STARTTLS={error}") from error
