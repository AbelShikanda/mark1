from datetime import datetime
from typing import Dict, Any

class AnalyticsModule:
    def __init__(self, db):
        self.db = db

    def record_post(self, date: Optional[str] = None) -> None:
        date = date or datetime.utcnow().strftime("%Y-%m-%d")
        conn = self.db.get_conn()
        row = conn.execute("SELECT * FROM analytics WHERE date = ?", (date,)).fetchone()
        if row:
            conn.execute(
                "UPDATE analytics SET posts_sent = posts_sent + 1 WHERE date = ?", (date,)
            )
        else:
            conn.execute(
                "INSERT INTO analytics (date, posts_sent, groups_reached) VALUES (?, 1, 0)",
                (date,),
            )
        conn.commit()
        conn.close()

    def summary(self) -> Dict[str, Any]:
        conn = self.db.get_conn()
        total = conn.execute("SELECT COALESCE(SUM(posts_sent),0) FROM analytics").fetchone()[0]
        rows = conn.execute("SELECT * FROM analytics ORDER BY date DESC LIMIT 7").fetchall()
        conn.close()
        return {
            "total_posts": total,
            "recent": [dict(r) for r in rows],
        }
