"""Работа с базой данных SQLite."""

import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

from config import SUPER_ADMIN_IDS


# ---------- Тексты по умолчанию для акта ----------
# Плейсхолдеры: {full_name}, {sign_name}, {contract_number}, {period},
#               {month}, {year}, {gender_ending}, {ndfl_amount}, {insurance_amount}
DEFAULT_ACT_TEXTS = {
    "header_city": "г. Москва",
    "preamble_theater": (
        "Государственное бюджетное учреждение культуры города Москвы "
        "«Государственный академический театр имени Моссовета» "
        "(ГБУК г. Москвы «Театр им. Моссовета»)"
    ),
    "preamble_position": (
        ", именуемое в дальнейшем «Заказчик», в лице директора "
        "Черепнева Алексея Анатольевича, действующего на основании Устава, "
        "с одной стороны, и "
    ),
    # Самозанятый
    "preamble_performer_label_self_employed_m": "самозанятый {full_name}",
    "preamble_performer_label_self_employed_f": "самозанятая {full_name}",
    # ГПХ
    "preamble_performer_label_gph_m": "{full_name}",
    "preamble_performer_label_gph_f": "{full_name}",
    # Общий footer с плейсхолдером {gender_ending}
    "preamble_footer": (
        ", именуем{gender_ending} в дальнейшем «Исполнитель», с другой стороны, "
        "совместно именуемые «Стороны», составили настоящий Акт (далее — Акт) "
        "о нижеследующем:"
    ),
    "contract_text": (
        "В соответствии с условиями Договора № {contract_number} "
        "(далее — Договор) Исполнителем оказаны услуги, а Заказчиком "
        "приняты услуги по исполнению роли/ей в составе организуемых "
        "Заказчиком театрально-зрелищных мероприятий (спектаклей)."
    ),
    "contract_text_empty": (
        "В соответствии с условиями Договора № ____ от __________ "
        "(далее — Договор) Исполнителем оказаны услуги, а Заказчиком "
        "приняты услуги по исполнению роли/ей в составе организуемых "
        "Заказчиком театрально-зрелищных мероприятий (спектаклей)."
    ),
    "period_text": "За период {period} фактически оказаны услуги в следующем объеме:",
    "service_show": "исполнение роли при проведении публичных показов спектакля",
    "service_rehearsal": "участие в репетиции спектакля",
    "rehearsal_theater": (
        "Репертуарные спектакли структурного подразделения — "
        "Студия «МОСТ»"
    ),
    "obligations": (
        "Обязательства по договору выполнены Исполнителем в установленные "
        "сроки. Заказчик не имеет претензий к объему и качеству оказанных "
        "услуг."
    ),
    "total_label": (
        "Сумма вознаграждения, подлежащая уплате Исполнителю, "
        "за услуги, принятые по настоящему акту, составляет "
    ),
    "tax_ndfl": (
        "в том числе налог на доходы физических лиц 13% — "
        "в размере {ndfl_amount} рублей."
    ),
    "insurance_fees": (
        "Указанное в настоящем пункте вознаграждение является объектом "
        "обложения страховых взносов в размере единого тарифа 30%, "
        "что составляет {insurance_amount} рублей 00 копеек."
    ),
    "insurance_responsibility": (
        "Обязанности по исчислению и уплате в бюджет суммы страховых "
        "взносов лежат на Заказчике."
    ),
    "payment_terms": (
        "Расчет по Договору производится путем перечисления Заказчиком "
        "денежных средств на банковский счет Исполнителя согласно "
        "реквизитам, указанным в Договоре, в течение 7 (Семи) рабочих дней "
        "со дня подписания Сторонами настоящего Акта."
    ),
    "copies_text": (
        "Настоящий Акт составлен в 2 (двух) экземплярах, имеющих равную "
        "юридическую силу, по одному экземпляру для каждой из Сторон и "
        "является неотъемлемой частью Договора."
    ),
    "signature_customer_title": "Заказчик:",
    "signature_customer_position": "Директор",
    "signature_customer_name": "______________ /А.А. Черепнев/",
    "signature_performer_title": "Исполнитель:",
    "signature_performer_label": "самозанятое лицо {full_name}",
    "signature_performer_name": "______________ /{sign_name}/",
    "signature_date": "«____» ______________ {year} г.",
    "signature_mp": "М.П.",
}


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as db, db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS shows (
                    id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL,
                    title TEXT NOT NULL, role TEXT NOT NULL, category TEXT,
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
            """)

            # Миграция rehearsals: units
            columns = {row["name"] for row in db.execute("PRAGMA table_info(rehearsals)")}
            if "units" not in columns:
                db.execute("ALTER TABLE rehearsals ADD COLUMN units INTEGER NOT NULL DEFAULT 1")

            # Миграция users: status и gender
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
                """INSERT INTO shows (user_id, title, role, category, price, day, show_time)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_id, data["title"], data["category"], data["category"],
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
        if table not in {"shows", "rehearsals"}:
            raise ValueError("Unknown table")
        with closing(self.connect()) as db:
            return db.execute(
                f"SELECT * FROM {table} WHERE user_id = ? AND day LIKE ? ORDER BY day, id",
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
        if table not in {"shows", "rehearsals"}:
            return False
        with closing(self.connect()) as db, db:
            return db.execute(
                f"DELETE FROM {table} WHERE id = ? AND user_id = ?",
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
        with closing(self.connect()) as db, db:
            return db.execute(
                "UPDATE users SET status = ? WHERE user_id = ?",
                (status, user_id),
            ).rowcount > 0

    def set_user_gender(self, user_id: int, gender: str) -> bool:
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