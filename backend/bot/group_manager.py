from typing import List, Dict, Any
from config import config as cfg

class GroupManager:
    def __init__(self, db):
        self.db = db

    def list_groups(self) -> List[Dict[str, Any]]:
        conn = self.db.get_conn()
        rows = conn.execute("SELECT * FROM groups ORDER BY id DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def add_group(self, name: str, url: Optional[str] = None, category: Optional[str] = None) -> int:
        conn = self.db.get_conn()
        cur = conn.execute(
            "INSERT INTO groups (name, url, category) VALUES (?, ?, ?)",
            (name, url, category),
        )
        gid = cur.lastrowid
        conn.commit()
        conn.close()
        return gid

    def remove_group(self, gid: int) -> None:
        conn = self.db.get_conn()
        conn.execute("DELETE FROM groups WHERE id = ?", (gid,))
        conn.commit()
        conn.close()
