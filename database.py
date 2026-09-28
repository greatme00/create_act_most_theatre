"""Работа с базой данных SQLite."""

import sqlite3
import logging
from contextlib import closing
from datetime import datetime
from pathlib import Path

from config import SUPER_ADMIN_IDS


# ---------- Тексты по умолчанию для акта ----------
# Плейсхолдеры: {full_name}, {sign_name}, {contract_number}, {period},
#               {month}, {year}, {gender_ending}, {ndfl_amount}, {insurance_amount}
# ---------- Тексты по умолчанию для акта ----------
# Ключи с префиксами:
#   common.*         — общие блоки (одинаковые для всех)
#   self_employed.*  — только для самозанятых
#   gph.*            — только для ГПХ
#
# Плейсхолдеры: {full_name}, {sign_name}, {contract_number}, {period},
#               {month}, {year}, {gender_ending},
#               {ndfl_amount}, {insurance_amount}

DEFAULT_ACT_TEXTS = {
    # ---------- Общие ----------
    "common.header_city": "г. Москва",
    "common.preamble_theater": (
        "Государственное бюджетное учреждение культуры города Москвы "
        "«Государственный академический театр имени Моссовета» "
        "(ГБУК г. Москвы «Театр им. Моссовета»)"
    ),
    "common.preamble_position": (
        ", именуемое в дальнейшем «Заказчик», в лице директора "
        "Черепнева Алексея Анатольевича, действующего на основании Устава, "
        "с одной стороны, и "
    ),
    "common.preamble_footer": (
        ", именуем{gender_ending} в дальнейшем «Исполнитель», с другой стороны, "
        "совместно именуемые «Стороны», составили настоящий Акт (далее — Акт) "
        "о нижеследующем:"
    ),
    "common.contract_text": (
        "В соответствии с условиями Договора № {contract_number} "
        "(далее — Договор) Исполнителем оказаны услуги, а Заказчиком "
        "приняты услуги по исполнению роли/ей в составе организуемых "
        "Заказчиком театрально-зрелищных мероприятий (спектаклей)."
    ),
    "common.contract_text_empty": (
        "В соответствии с условиями Договора № ____ от __________ "
        "(далее — Договор) Исполнителем оказаны услуги, а Заказчиком "
        "приняты услуги по исполнению роли/ей в составе организуемых "
        "Заказчиком театрально-зрелищных мероприятий (спектаклей)."
    ),
    "common.period_text": "За период {period} фактически оказаны услуги в следующем объеме:",
    "common.service_show": "исполнение роли при проведении публичных показов спектакля",
    "common.service_rehearsal": "участие в репетиции спектакля",
    "common.rehearsal_theater": (
        "Репертуарные спектакли структурного подразделения — "
        "Студия «МОСТ»"
    ),
    "common.obligations": (
        "Обязательства по договору выполнены Исполнителем в установленные "
        "сроки. Заказчик не имеет претензий к объему и качеству оказанных "
        "услуг."
    ),
    "common.total_label": (
        "Сумма вознаграждения, подлежащая уплате Исполнителю, "
        "за услуги, принятые по настоящему акту, составляет "
    ),
    "common.payment_terms": (
        "Расчет по Договору производится путем перечисления Заказчиком "
        "денежных средств на банковский счет Исполнителя согласно "
        "реквизитам, указанным в Договоре, в течение 7 (Семи) рабочих дней "
        "со дня подписания Сторонами настоящего Акта."
    ),
    "common.copies_text": (
        "Настоящий Акт составлен в 2 (двух) экземплярах, имеющих равную "
        "юридическую силу, по одному экземпляру для каждой из Сторон и "
        "является неотъемлемой частью Договора."
    ),
    "common.signature_customer_title": "Заказчик:",
    "common.signature_customer_position": "Директор",
    "common.signature_customer_name": "______________ /А.А. Черепнев/",
    "common.signature_performer_title": "Исполнитель:",
    "common.signature_performer_name": "______________ /{sign_name}/",

    # ---------- Самозанятый ----------
    "self_employed.preamble_performer_label_m": "самозанятый {full_name}",
    "self_employed.preamble_performer_label_f": "самозанятая {full_name}",
    "self_employed.signature_performer_label_m": "самозанятый {full_name}",
    "self_employed.signature_performer_label_f": "самозанятая {full_name}",

    # ---------- ГПХ ----------
    "gph.preamble_performer_label_m": "{full_name}",
    "gph.preamble_performer_label_f": "{full_name}",
    "gph.signature_performer_label_m": "",
    "gph.signature_performer_label_f": "",
    "gph.tax_ndfl": (
        "в том числе налог на доходы физических лиц 13% — "
        "в размере {ndfl_amount} рублей."
    ),
    "gph.insurance_fees": (
        "Указанное в настоящем пункте вознаграждение является объектом "
        "обложения страховых взносов в размере единого тарифа 30%, "
        "что составляет {insurance_amount} рублей 00 копеек."
    ),
    "gph.insurance_responsibility": (
        "Обязанности по исчислению и уплате в бюджет суммы страховых "
        "взносов лежат на Заказчике."
    ),
}


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    _VALID_STATUSES = ("self_employed", "gph")
    _VALID_GENDERS = ("m", "f")
    _ALLOWED_TABLES = {"shows": "shows", "rehearsals": "rehearsals"}

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path,
            timeout=30.0,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS shows (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    title TEXT NOT NULL, category TEXT,
                    price INTEGER, day TEXT NOT NULL, show_time TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS rehearsals (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    title TEXT NOT NULL, price INTEGER NOT NULL DEFAULT 750,
                    units INTEGER NOT NULL DEFAULT 1,
                    day TEXT NOT NULL, time_start TEXT, time_end TEXT);
                CREATE INDEX IF NOT EXISTS shows_by_user_day ON shows(user_id, day);
                CREATE INDEX IF NOT EXISTS rehearsals_by_user_day ON rehearsals(user_id, day);
                CREATE TABLE IF NOT EXISTS reminder_log (
                    event_type TEXT NOT NULL, event_id INTEGER NOT NULL,
                    reminder_day TEXT NOT NULL,
                    PRIMARY KEY (event_type, event_id, reminder_day));
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    contract_number TEXT);
                CREATE TABLE IF NOT EXISTS user_prices (
                    user_id INTEGER NOT NULL, category TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    PRIMARY KEY (user_id, category));
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    added_by INTEGER,
                    added_at TEXT);
                CREATE TABLE IF NOT EXISTS act_texts (
                    key TEXT PRIMARY KEY,
                    text TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    quotes_subscribed INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS bot_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS user_activity (
                    id INTEGER PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    created_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS user_activity_by_user
                    ON user_activity(user_id, created_at);
            """)

            # ---------- МИГРАЦИЯ: удаляем колонку role из shows ----------
            show_columns = {row["name"] for row in db.execute("PRAGMA table_info(shows)")}
            if "role" in show_columns:
                logging.info("Миграция: удаляю колонку role из shows")
                db.executescript("""
                    CREATE TABLE shows_new (
                        id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                        title TEXT NOT NULL, category TEXT,
                        price INTEGER, day TEXT NOT NULL, show_time TEXT NOT NULL);
                    INSERT INTO shows_new (id, user_id, title, category, price, day, show_time)
                        SELECT id, user_id, title, category, price, day, show_time FROM shows;
                    DROP TABLE shows;
                    ALTER TABLE shows_new RENAME TO shows;
                    CREATE INDEX IF NOT EXISTS shows_by_user_day ON shows(user_id, day);
                """)
                logging.info("Миграция: колонка role удалена")

            # ---------- Миграция rehearsals: units ----------
            columns = {row["name"] for row in db.execute("PRAGMA table_info(rehearsals)")}
            if "units" not in columns:
                db.execute("ALTER TABLE rehearsals ADD COLUMN units INTEGER NOT NULL DEFAULT 1")

            # ---------- Миграция users: status и gender ----------
            user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
            if "status" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'self_employed'")
            if "gender" not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN gender TEXT DEFAULT 'm'")

    # ---------- Тексты акта ----------

    def get_act_text(self, key: str) -> str:
        """Возвращает текст по ключу. Если нет в БД — дефолт из DEFAULT_ACT_TEXTS."""
        with closing(self.connect()) as db:
            row = db.execute("SELECT text FROM act_texts WHERE key = ?", (key,)).fetchone()
        if row is not None:
            return row["text"]
        return DEFAULT_ACT_TEXTS.get(key, "")

    def set_act_text(self, key: str, text: str) -> None:
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO act_texts(key, text) VALUES (?, ?)",
                (key, text),
            )

    def reset_act_text(self, key: str) -> None:
        """Удаляет кастомный текст — вернётся дефолт."""
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM act_texts WHERE key = ?", (key,))

    def get_all_act_texts(self) -> dict[str, str]:
        """Возвращает все тексты: дефолт + переопределения из БД."""
        result = dict(DEFAULT_ACT_TEXTS)
        with closing(self.connect()) as db:
            for row in db.execute("SELECT key, text FROM act_texts"):
                result[row["key"]] = row["text"]
        return result

    # ----- профиль -----

    def profile(self, user_id: int) -> sqlite3.Row | None:
        with closing(self.connect()) as db:
            return db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()


    def save_profile(
        self,
        user_id: int,
        full_name: str,
        contract_number: str | None,
        status: str = "self_employed",
        gender: str = "m",
    ) -> None:
        if status not in self._VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        if gender not in self._VALID_GENDERS:
            raise ValueError(f"Invalid gender: {gender}")
        with closing(self.connect()) as db, db:
            db.execute(
                """INSERT OR REPLACE INTO users
                   (user_id, full_name, contract_number, status, gender)
                   VALUES (?, ?, ?, ?, ?)""",
                (user_id, full_name, contract_number, status, gender),
            )

    # ----- цены -----

    def prices(self, user_id: int) -> dict[str, int]:
        from config import DEFAULT_PRICES
        result = dict(DEFAULT_PRICES)
        with closing(self.connect()) as db:
            for row in db.execute("SELECT category, price FROM user_prices WHERE user_id = ?", (user_id,)):
                result[row["category"]] = row["price"]
        return result

    def save_price(self, user_id: int, category: str, price: int) -> None:
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO user_prices(user_id, category, price) VALUES (?, ?, ?)",
                (user_id, category, price),
            )

    # ----- показы -----

    def add_show(self, user_id: int, data: dict[str, str]) -> None:
        price = self.prices(user_id)[data["category"]]
        with closing(self.connect()) as db, db:
            db.execute(
                """INSERT INTO shows (user_id, title, category, price, day, show_time)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (user_id, data["title"], data["category"],
                 price, data["day"], data.get("time", "")),
            )

    def has_same_show(self, user_id: int, title: str, day: str) -> bool:
        with closing(self.connect()) as db:
            return db.execute(
                "SELECT 1 FROM shows WHERE user_id = ? AND title = ? AND day = ?",
                (user_id, title, day),
            ).fetchone() is not None

    # ----- репетиции -----

    def add_rehearsal(self, user_id: int, data: dict[str, str | None]) -> None:
        from utils import rehearsal_units
        units = rehearsal_units(data["start"], data["end"])
        price = self.prices(user_id).get("Репетиция", 750)
        with closing(self.connect()) as db, db:
            db.execute(
                """INSERT INTO rehearsals (user_id, title, units, day, time_start, time_end, price)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, data["title"], units, data["day"], data["start"], data["end"], price),
            )

    # ----- выборки -----


    def month_rows(self, table: str, user_id: int, month: str) -> list[sqlite3.Row]:
        if table not in self._ALLOWED_TABLES:
            raise ValueError(f"Unknown table: {table}")
        safe_table = self._ALLOWED_TABLES[table]
        with closing(self.connect()) as db:
            return db.execute(
                f"SELECT * FROM {safe_table} WHERE user_id = ? AND day LIKE ? ORDER BY day, id",
                (user_id, f"{month}-%"),
            ).fetchall()

    def events_for_day(self, day: str) -> list[sqlite3.Row]:
        with closing(self.connect()) as db:
            return db.execute("""
                SELECT 'show' AS type, id, user_id, title, show_time AS time FROM shows WHERE day = ?
                UNION ALL
                SELECT 'rehearsal' AS type, id, user_id, title, time_start AS time FROM rehearsals WHERE day = ?
            """, (day, day)).fetchall()

    def reminder_was_sent(self, event_type: str, event_id: int, reminder_day: str) -> bool:
        with closing(self.connect()) as db:
            return db.execute(
                "SELECT 1 FROM reminder_log WHERE event_type = ? AND event_id = ? AND reminder_day = ?",
                (event_type, event_id, reminder_day),
            ).fetchone() is not None

    def mark_reminder_sent(self, event_type: str, event_id: int, reminder_day: str) -> None:
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT OR IGNORE INTO reminder_log(event_type, event_id, reminder_day) VALUES (?, ?, ?)",
                (event_type, event_id, reminder_day),
            )

    def delete(self, table: str, record_id: int, user_id: int) -> bool:
        if table not in self._ALLOWED_TABLES:
            return False
        safe_table = self._ALLOWED_TABLES[table]
        with closing(self.connect()) as db, db:
            return db.execute(
                f"DELETE FROM {safe_table} WHERE id = ? AND user_id = ?",
                (record_id, user_id),
            ).rowcount > 0
    # ----- админские методы -----

    def list_users(self) -> list[sqlite3.Row]:
        with closing(self.connect()) as db:
            return db.execute("""
                SELECT u.user_id, u.full_name, u.contract_number,
                       (SELECT COUNT(*) FROM shows s WHERE s.user_id = u.user_id) AS shows_count,
                       (SELECT COUNT(*) FROM rehearsals r WHERE r.user_id = u.user_id) AS rehearsals_count
                FROM users u
                ORDER BY u.user_id
            """).fetchall()

    def get_user(self, user_id: int) -> sqlite3.Row | None:
        with closing(self.connect()) as db:
            return db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

    def delete_user(self, user_id: int) -> bool:
        with closing(self.connect()) as db, db:
            db.execute("DELETE FROM reminder_log WHERE event_id IN (SELECT id FROM shows WHERE user_id = ?)", (user_id,))
            db.execute("DELETE FROM reminder_log WHERE event_id IN (SELECT id FROM rehearsals WHERE user_id = ?)", (user_id,))
            db.execute("DELETE FROM shows WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM rehearsals WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM user_prices WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM user_settings WHERE user_id = ?", (user_id,))
            db.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            cur = db.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
            return cur.rowcount > 0

    def set_user_name(self, user_id: int, full_name: str) -> bool:
        with closing(self.connect()) as db, db:
            return db.execute(
                "UPDATE users SET full_name = ? WHERE user_id = ?",
                (full_name, user_id),
            ).rowcount > 0

    def set_user_contract(self, user_id: int, contract: str) -> bool:
        with closing(self.connect()) as db, db:
            return db.execute(
                "UPDATE users SET contract_number = ? WHERE user_id = ?",
                (contract, user_id),
            ).rowcount > 0

    def set_user_status(self, user_id: int, status: str) -> bool:
        if status not in self._VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        with closing(self.connect()) as db, db:
            return db.execute(
                "UPDATE users SET status = ? WHERE user_id = ?",
                (status, user_id),
            ).rowcount > 0

    def set_user_gender(self, user_id: int, gender: str) -> bool:
        if gender not in self._VALID_GENDERS:
            raise ValueError(f"Invalid gender: {gender}")
        with closing(self.connect()) as db, db:
            return db.execute(
                "UPDATE users SET gender = ? WHERE user_id = ?",
                (gender, user_id),
            ).rowcount > 0

    def user_stats(self, user_id: int) -> dict[str, int]:
        with closing(self.connect()) as db:
            shows = db.execute("SELECT COUNT(*) AS c FROM shows WHERE user_id = ?", (user_id,)).fetchone()["c"]
            rehearsals = db.execute("SELECT COUNT(*) AS c FROM rehearsals WHERE user_id = ?", (user_id,)).fetchone()["c"]
        return {"shows": shows, "rehearsals": rehearsals}

    # ----- админы -----

    def list_admins(self) -> list[sqlite3.Row]:
        with closing(self.connect()) as db:
            return db.execute(
                "SELECT user_id, added_by, added_at FROM admins ORDER BY added_at"
            ).fetchall()

    def add_admin(self, user_id: int, added_by: int) -> bool:
        with closing(self.connect()) as db, db:
            try:
                db.execute(
                    "INSERT INTO admins(user_id, added_by, added_at) VALUES (?, ?, ?)",
                    (user_id, added_by, datetime.now().isoformat(timespec="seconds")),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def remove_admin(self, user_id: int) -> bool:
        with closing(self.connect()) as db, db:
            return db.execute(
                "DELETE FROM admins WHERE user_id = ?", (user_id,)
            ).rowcount > 0

    def is_admin_db(self, user_id: int) -> bool:
        if user_id in SUPER_ADMIN_IDS:
            return True
        with closing(self.connect()) as db:
            return db.execute(
                "SELECT 1 FROM admins WHERE user_id = ?", (user_id,)
            ).fetchone() is not None

    def all_user_ids(self) -> list[int]:
        with closing(self.connect()) as db:
            rows = db.execute("SELECT user_id FROM users").fetchall()
        return [row["user_id"] for row in rows]

        # ----- активность пользователей -----

    def log_activity(self, user_id: int, action: str) -> None:
        with closing(self.connect()) as db, db:
            db.execute(
                "INSERT INTO user_activity(user_id, action, created_at) VALUES (?, ?, ?)",
                (user_id, action, datetime.now().isoformat(timespec="seconds")),
            )

    def last_activity(self, user_id: int) -> str | None:
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT created_at FROM user_activity WHERE user_id = ? ORDER BY created_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
        return row["created_at"] if row else None

    def activity_stats(self, user_id: int, days: int = 7) -> dict[str, int]:
        from datetime import timedelta
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with closing(self.connect()) as db:
            rows = db.execute(
                """SELECT action, COUNT(*) AS cnt
                   FROM user_activity
                   WHERE user_id = ? AND created_at >= ?
                   GROUP BY action""",
                (user_id, since),
            ).fetchall()
        return {row["action"]: row["cnt"] for row in rows}

    def activity_total(self, user_id: int, days: int = 7) -> int:
        from datetime import timedelta
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT COUNT(*) AS c FROM user_activity WHERE user_id = ? AND created_at >= ?",
                (user_id, since),
            ).fetchone()
        return row["c"] if row else 0

    def cleanup_old_activity(self, keep_days: int = 28) -> int:
        """Удаляет записи активности старше keep_days. Возвращает число удалённых."""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat(timespec="seconds")
        with closing(self.connect()) as db, db:
            cur = db.execute("DELETE FROM user_activity WHERE created_at < ?", (cutoff,))
            return cur.rowcount

    def list_activity_all_users(self, days: int = 7) -> list[sqlite3.Row]:
        from datetime import timedelta
        since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
        with closing(self.connect()) as db:
            return db.execute("""
                SELECT u.user_id, u.full_name,
                       (SELECT MAX(a.created_at) FROM user_activity a
                        WHERE a.user_id = u.user_id) AS last_seen,
                       (SELECT COUNT(*) FROM user_activity a
                        WHERE a.user_id = u.user_id AND a.created_at >= ?) AS cnt
                FROM users u
                ORDER BY last_seen DESC
            """, (since,)).fetchall()

        # ----- настройки пользователя -----

    def is_quotes_subscribed(self, user_id: int) -> bool:
        """По умолчанию — подписан."""
        with closing(self.connect()) as db:
            row = db.execute(
                "SELECT quotes_subscribed FROM user_settings WHERE user_id = ?",
                (user_id,),
            ).fetchone()
        if row is None:
            return True
        return bool(row["quotes_subscribed"])

    def set_quotes_subscribed(self, user_id: int, value: bool) -> None:
        with closing(self.connect()) as db, db:
            db.execute(
                """INSERT INTO user_settings(user_id, quotes_subscribed)
                   VALUES (?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET quotes_subscribed = excluded.quotes_subscribed""",
                (user_id, 1 if value else 0),
            )

    def subscribed_user_ids(self) -> list[int]:
        """ID всех, кто подписан на цитаты."""
        with closing(self.connect()) as db:
            rows = db.execute("""
                SELECT u.user_id FROM users u
                LEFT JOIN user_settings s ON s.user_id = u.user_id
                WHERE COALESCE(s.quotes_subscribed, 1) = 1
            """).fetchall()
        return [row["user_id"] for row in rows]