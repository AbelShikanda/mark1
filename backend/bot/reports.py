"""Generate, store and export market snapshots.

Reports are aggregate-only: raw messages are never embedded, so the raw-row
retention sweep can delete them without touching saved reports.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from db_logic import get_conn, log
from bot import settings as app_settings
from bot.classifier import top_keywords, parse_topics


def _cutoff_days(days: int) -> str:
    return (datetime.now() - timedelta(days=max(1, int(days)))).strftime("%Y-%m-%d %H:%M:%S")


def _iso_week(dt: Optional[datetime] = None) -> str:
    dt = dt or datetime.now()
    return dt.strftime("%Y-W%V")


def _rows(conn, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def markdown_of(report: Dict[str, Any]) -> str:
    return report.get("summary_md") or ""


def csv_of(report: Dict[str, Any]) -> str:
    body = report.get("body") or {}
    summary = body.get("summary") or {}
    rows = [("section", "key", "value")]
    rows.append(("scope", "campaign_id", body.get("scope_campaign_id") if body.get("scope_campaign_id") is not None else "all"))
    rows += [("summary", k, v) for k, v in summary.items()]
    rows += [("intent", k, v) for k, v in (body.get("intents") or {}).items()]
    rows += [("sentiment", k, v) for k, v in (body.get("sentiments") or {}).items()]
    rows += [("top_keyword", k, v) for k, v in (body.get("top_keywords") or [])]
    rows += [("top_question_keyword", k, v) for k, v in (body.get("top_questions") or [])]
    rows += [("best_hour", str(h), v) for h, v in sorted((body.get("best_hour_replies") or {}).items())]
    rows += [("best_weekday", k, v) for k, v in (body.get("best_weekday_replies") or {}).items()]
    for stat in body.get("group_stats") or []:
        rows.append(("group", stat.get("name"), f"{stat.get('replies', 0)}/{stat.get('posts', 0)}"))
    for stat in (body.get("product_stats") or {}).values():
        rows.append(("product", stat.get("name"), f"{stat.get('replies', 0)}/{stat.get('posts', 0)}"))

    def esc(value) -> str:
        text = str(value if value is not None else "")
        if any(ch in text for ch in [',', '"', '\n']):
            text = '"' + text.replace('"', '""') + '"'
        return text

    return "\n".join(",".join(esc(item) for item in row) for row in rows)


def pdf_of(report: Dict[str, Any]) -> bytes:
    from xhtml2pdf import pisa
    import io

    body = report.get("body") or {}
    summary = body.get("summary") or {}
    title = report.get("title") or "Market report"
    period = body.get("period") or {}

    def kv_table(pairs):
        return "".join(
            f"<tr><td style='padding:4px 8px;border:1px solid #ddd'>{k}</td>"
            f"<td style='padding:4px 8px;border:1px solid #ddd;text-align:right'>{v}</td></tr>"
            for k, v in pairs
        )

    summary_rows = kv_table([(k.replace("_", " "), v) for k, v in summary.items()])
    intent_rows = kv_table(sorted((body.get("intents") or {}).items(), key=lambda kv: -kv[1]))
    sentiment_rows = kv_table(sorted((body.get("sentiments") or {}).items(), key=lambda kv: -kv[1]))
    keyword_rows = "".join(
        f"<tr><td style='padding:4px 8px;border:1px solid #ddd'>{k}</td>"
        f"<td style='padding:4px 8px;border:1px solid #ddd;text-align:right'>{v}</td></tr>"
        for k, v in (body.get("top_keywords") or [])
    )

    def bar_rows(pairs):
        if not pairs:
            return "<p>No data.</p>"
        max_val = max(v for _, v in pairs) or 1
        out = []
        for key, value in pairs:
            width = int(280 * value / max_val)
            out.append(
                f"<div style='margin:2px 0'><span style='display:inline-block;width:150px'>{key}</span>"
                f"<span style='display:inline-block;background:#4f46e5;height:10px;width:{width}px'></span>"
                f"<span style='margin-left:6px'>{value}</span></div>"
            )
        return "".join(out)

    intent_chart = bar_rows(sorted((body.get("intents") or {}).items(), key=lambda kv: -kv[1]))
    hour_chart = bar_rows(sorted((body.get("best_hour_replies") or {}).items()))

    html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>{title}</title></head>
<body style="font-family: Helvetica, Arial, sans-serif; color:#111; font-size:11px">
<h1 style="font-size:20px">{title}</h1>
<p>Period: {period.get('from', '?')[:10]} to {period.get('to', '?')[:10]} · Generated: {report.get('generated_at', '?')}</p>
<h2>Summary</h2>
<table style="border-collapse:collapse">{summary_rows}</table>
<h2>Intents</h2>
<table style="border-collapse:collapse">{intent_rows}</table>
{intent_chart}
<h2>Sentiments</h2>
<table style="border-collapse:collapse">{sentiment_rows}</table>
<h2>Top keywords</h2>
<table style="border-collapse:collapse">{keyword_rows}</table>
<h2>Replies by hour of day</h2>
{hour_chart}
<p style="color:#666; font-size:9px; margin-top:24px">Aggregates only. Raw messages are never embedded in a report.</p>
</body></html>"""

    buffer = io.BytesIO()
    result = pisa.CreatePDF(html, dest=buffer)
    if result.err:
        raise RuntimeError("PDF rendering failed")
    return buffer.getvalue()


def aggregate(from_ts: str, to_ts: str, campaign_id: Optional[int] = None) -> Dict[str, Any]:
    conn = get_conn()
    post_where = "WHERE cp.status = 'sent' AND cp.posted_at >= ? AND cp.posted_at < ?"
    params: List[Any] = [from_ts, to_ts]
    if campaign_id is not None:
        post_where += " AND cp.campaign_id = ?"
        params.append(int(campaign_id))
    posts = _rows(
        conn,
        "SELECT cp.id, cp.campaign_id, cp.target_id, cp.target_name, cp.posted_at, cp.status, "
        "       cp.product_id, c.name AS campaign_name, p.name AS product_name, "
        "       COALESCE(c.capture_replies, 0) AS capture_boost "
        "FROM campaign_posts cp LEFT JOIN campaigns c ON c.id = cp.campaign_id "
        "LEFT JOIN products p ON p.id = cp.product_id "
        + post_where,
        tuple(params),
    )
    msg_params: List[Any] = [from_ts, to_ts]
    if campaign_id is not None:
        msg_where = (
            "WHERE m.captured_at >= ? AND m.captured_at < ? "
            "AND (m.campaign_post_id IN (SELECT id FROM campaign_posts WHERE campaign_id = ?))"
        )
        msg_params.append(int(campaign_id))
    else:
        msg_where = "WHERE m.captured_at >= ? AND m.captured_at < ?"
    messages = _rows(
        conn,
        "SELECT m.id, m.group_id, m.campaign_post_id, m.sender, m.text, m.captured_at, "
        "       m.intent, m.sentiment, m.topics, m.spam_flag "
        "FROM group_messages m " + msg_where,
        tuple(msg_params),
    )
    groups = {row["id"]: row for row in _rows(conn, "SELECT id, name FROM groups")}
    products = {row["id"]: row for row in _rows(conn, "SELECT id, name FROM products")}
    conn.close()

    post_counts: Dict[str, Any] = {}
    reply_counts: Dict[int, int] = {}
    posts_with_capture = sum(1 for p in posts if p.get("capture_boost"))
    for message in messages:
        pid = message.get("campaign_post_id")
        if pid is not None:
            reply_counts[pid] = reply_counts.get(pid, 0) + 1

    group_stats: Dict[int, Dict[str, Any]] = {}
    for post in posts:
        gid = int(post["target_id"]) if post.get("target_id") is not None else None
        if gid is None:
            continue
        stat = group_stats.setdefault(gid, {"id": gid, "name": groups.get(gid, {}).get("name", f"group {gid}"), "posts": 0, "replies": 0})
        stat["posts"] += 1
        stat["replies"] += reply_counts.get(post["id"], 0)

    product_stats: Dict[int, Dict[str, Any]] = {}
    for post in posts:
        pid = post.get("product_id")
        if pid is None:
            continue
        pid = int(pid)
        stat = product_stats.setdefault(
            pid,
            {
                "id": pid,
                "name": post.get("product_name") or products.get(pid, {}).get("name") or f"product {pid}",
                "posts": 0,
                "replies": 0,
            },
        )
        stat["posts"] += 1
        stat["replies"] += reply_counts.get(post["id"], 0)

    intent_counts: Dict[str, int] = {}
    sentiment_counts: Dict[str, int] = {}
    spam_count = 0
    texts: List[str] = []
    question_texts: List[str] = []
    for message in messages:
        intent = message.get("intent") or "unclassified"
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        sentiment = message.get("sentiment") or "neutral"
        sentiment_counts[sentiment] = sentiment_counts.get(sentiment, 0) + 1
        spam_count += 1 if message.get("spam_flag") else 0
        text = message.get("text") or ""
        texts.append(text)
        if "?" in text:
            question_texts.append(text)

    # Best time by hour of day (most replies after posts).
    by_hour: Dict[int, int] = {}
    by_weekday: Dict[str, int] = {}
    for post in posts:
        try:
            stamp = datetime.strptime(str(post["posted_at"]), "%Y-%m-%d %H:%M:%S")
        except Exception:
            continue
        by_hour[stamp.hour] = by_hour.get(stamp.hour, 0) + reply_counts.get(post["id"], 0)
        weekday = stamp.strftime("%A")
        by_weekday[weekday] = by_weekday.get(weekday, 0) + reply_counts.get(post["id"], 0)

    def best_key(d: Dict[Any, int]):
        if not d:
            return None
        return max(d.items(), key=lambda item: item[1])[0]

    top_questions = top_keywords(question_texts, limit=25)
    total_replies = len(messages)
    if total_replies == 0:
        best_hour = None
        best_weekday = None
    else:
        best_hour = best_key(by_hour)
        best_weekday = best_key(by_weekday)
    summary = {
        "posts_sent": len(posts),
        "posts_with_capture": posts_with_capture,
        "replies_captured": len(messages),
        "messages_per_post": round(len(messages) / len(posts), 2) if posts else 0.0,
        "groups_reached": len({p["target_id"] for p in posts if p.get("target_id") is not None}),
        "spam_flagged": spam_count,
        "unclassified": sum(1 for m in messages if (m.get("intent") or "unclassified") == "unclassified"),
    }
    return {
        "period": {"from": from_ts, "to": to_ts},
        "scope_campaign_id": campaign_id,
        "summary": summary,
        "intents": intent_counts,
        "sentiments": sentiment_counts,
        "top_keywords": top_keywords(texts, limit=25),
        "top_questions": top_questions,
        "group_stats": sorted(group_stats.values(), key=lambda g: (-g["replies"], -g["posts"])),
        "best_hour": best_hour,
        "best_weekday": best_weekday,
        "best_hour_replies": by_hour,
        "best_weekday_replies": by_weekday,
        "product_stats": product_stats,
        "spam": {"flagged": spam_count},
    }


def build_summary_md(aggregate_body: Dict[str, Any]) -> str:
    body = aggregate_body
    lines = [
        f"# Market report ({body['period']['from'][:10]} → {body['period']['to'][:10]})",
        "",
        f"- Posts sent: **{body['summary']['posts_sent']}** (with capture: **{body['summary'].get('posts_with_capture', 0)}**)",
        f"- Replies captured: **{body['summary']['replies_captured']}**",
        f"- Messages per post: **{body['summary']['messages_per_post']}**",
        f"- Groups reached: **{body['summary']['groups_reached']}**",
        f"- Spam flagged: **{body['summary']['spam_flagged']}**",
        f"- Unclassified: **{body['summary']['unclassified']}**",
        f"- Best hour: **{body['best_hour'] if body['best_hour'] is not None else 'not enough data'}"
        + (f" · best weekday: **{body['best_weekday']}**" if body['best_weekday'] else ""),
        "",
        "## Intent distribution",
    ]
    for intent, count in sorted(body["intents"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {intent}: {count}")
    lines += ["", "## Sentiments"]
    for sentiment, count in sorted(body["sentiments"].items(), key=lambda kv: -kv[1]):
        lines.append(f"- {sentiment}: {count}")
    lines += ["", "## Top keywords"]
    for word, count in body["top_keywords"]:
        lines.append(f"- {word}: {count}")
    lines += ["", "## Top question keywords"]
    for word, count in body["top_questions"]:
        lines.append(f"- {word}: {count}")
    product_lines = ["", "## Products (by replies)"]
    prods = sorted(body["product_stats"].values(), key=lambda p: (-p["replies"], -p["posts"]))[:15]
    for stat in prods or [{"name": "—", "posts": 0, "replies": 0}]:
        product_lines.append(f"- {stat['name']} — {stat['replies']} replies / {stat['posts']} posts")
    lines += product_lines
    group_lines = ["", "## Groups (by replies)"]
    for stat in body["group_stats"][:15]:
        group_lines.append(f"- {stat['name']} — {stat['replies']} replies / {stat['posts']} posts")
    lines += group_lines
    return "\n".join(lines)


def create_report(title: str, days: int = 7, trigger: str = "manual", campaign_id: Optional[int] = None) -> Dict[str, Any]:
    to_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    from_ts = _cutoff_days(days)
    if campaign_id is not None:
        conn = get_conn()
        row = conn.execute("SELECT name FROM campaigns WHERE id = ?", (int(campaign_id),)).fetchone()
        conn.close()
        campaign_name = row["name"] if row else f"campaign {campaign_id}"
        title = title or f"{campaign_name} — last {days} days"
    body = aggregate(from_ts, to_ts, campaign_id)
    summary_md = build_summary_md(body)
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO market_reports (title, period_start, period_end, body_json, summary_md, trigger) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (title or f"Market report {to_ts[:10]}", from_ts, to_ts, json.dumps(body), summary_md, trigger),
    )
    report_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return get_report(report_id)


def list_reports(limit: int = 50) -> List[Dict[str, Any]]:
    conn = get_conn()
    rows = _rows(
        conn,
        "SELECT id, title, period_start, period_end, generated_at, trigger FROM market_reports ORDER BY id DESC LIMIT ?",
        (max(1, int(limit)),),
    )
    conn.close()
    return rows


def get_report(report_id: int) -> Optional[Dict[str, Any]]:
    conn = get_conn()
    row = conn.execute(
        "SELECT id, title, period_start, period_end, generated_at, body_json, summary_md, trigger "
        "FROM market_reports WHERE id = ?",
        (int(report_id),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    data = dict(row)
    try:
        data["body"] = json.loads(data.pop("body_json"))
    except Exception:
        data["body"] = {}
        data.pop("body_json", None)
    return data


def delete_report(report_id: int) -> bool:
    conn = get_conn()
    deleted = conn.execute("DELETE FROM market_reports WHERE id = ?", (int(report_id),)).rowcount
    conn.commit()
    conn.close()
    return bool(deleted)


def maybe_generate_weekly() -> Optional[Dict[str, Any]]:
    if not app_settings.get_bool("market_report_auto_weekly", False):
        return None
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_meta WHERE key = 'market_last_weekly'").fetchone()
    current_week = _iso_week()
    if row and row["value"] == current_week:
        conn.close()
        return None
    conn.close()

    # Only generate when there is something to report.
    conn = get_conn()
    count_row = conn.execute(
        "SELECT COUNT(*) AS c FROM group_messages WHERE captured_at >= ?", (_cutoff_days(7),)
    ).fetchone()
    conn.close()
    if not count_row or count_row["c"] == 0:
        conn = get_conn()
        conn.execute(
            "INSERT INTO app_meta (key, value) VALUES ('market_last_weekly', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (current_week,),
        )
        conn.commit()
        conn.close()
        return None

    report = create_report(f"Weekly market report {current_week}", days=7, trigger="weekly")
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES ('market_last_weekly', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (current_week,),
    )
    conn.commit()
    conn.close()
    log("info", f"auto-generated weekly market report ({current_week})", "reports")
    return report
