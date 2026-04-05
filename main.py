from flask import Flask, request
import requests
import json
import os

app = Flask(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
TELEGRAM_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
USERS_FILE = os.getenv("USERS_FILE", "users.json")

# Загружаем соответствие логинов Jira ↔ chat_id Telegram
try:
    with open(USERS_FILE) as f:
        TELEGRAM_USERS = json.load(f)
except Exception as e:
    print(f"⚠️ Не удалось загрузить {USERS_FILE}: {e}")
    TELEGRAM_USERS = {}


def send_telegram(chat_id: int, text: str):
    """Отправка сообщения в Telegram"""
    try:
        requests.post(
            TELEGRAM_URL,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=5
        )
    except Exception as e:
        print(f"❌ Ошибка отправки Telegram: {e}")


def get_chat_id(user: dict):
    """Определяем chat_id по имени Jira"""
    if not user:
        return None
    username = user.get("name")
    return TELEGRAM_USERS.get(username)


@app.route("/jira-to-telegram", methods=["POST"])
def jira_to_telegram():
    # --- query-параметры (инициатор действия) ---
    initiator_id = request.args.get("user_id")
    initiator_key = request.args.get("user_key")

    data = request.json or {}
    webhook_event = data.get("webhookEvent", "")
    issue_event_type_name = data.get("issue_event_type_name","")
    print(data)

    issue = data.get("issue", {})
    key = issue.get("key", "")
    fields = issue.get("fields", {})

    summary = fields.get("summary", "(без названия)")
    status = (fields.get("status") or {}).get("name", "")
    assignee = fields.get("assignee", {}) or {}
    reporter = fields.get("reporter", {}) or {}

    # Определяем chat_id получателей
    assignee_name = assignee.get("name")
    reporter_name = reporter.get("name")

    # Исключаем инициатора, чтобы не уведомлять его самого
    recipients = []
    if assignee_name and assignee_name != initiator_id:
        chat_id = TELEGRAM_USERS.get(assignee_name)
        if chat_id:
            recipients.append(chat_id)
    if reporter_name and reporter_name not in [initiator_id, assignee_name]:
        chat_id = TELEGRAM_USERS.get(reporter_name)
        if chat_id:
            recipients.append(chat_id)

    if not recipients:
        print(f"⚠️ Нет получателей для события {webhook_event} ({key})")
        return "No recipients", 200

    issue_url = f"https://team.3cup.ru/jira/browse/{key}"

    # --- Комментарии ---
    comment = data.get("comment", {})
    comment_author = (comment.get("author") or {}).get("displayName", "")
    comment_body = comment.get("body", "")

    # --- Формирование текста уведомления ---
    text = None

    if webhook_event == "jira:issue_created":
        text = (
            f"🆕 <b>Создана задача</b>\n"
            f"<b>{key}</b>: {summary}\n"
            f"Назначена: <b>{assignee.get('displayName') or 'не указано'}</b>\n"
            f"Автор: {reporter.get('displayName')}\n"
            f"{issue_url}"
        )

    if webhook_event == "jira:issue_updated":
        changelog = data.get("changelog", {})
        items = changelog.get("items", [])
        status_change = next((i for i in items if i.get("field") == "status"), None)

        if status_change:
            from_status = status_change.get("fromString", "")
            to_status = status_change.get("toString", "")
            text = (
                f"🔄 <b>Изменён статус задачи</b>\n"
                f"<b>{key}</b>: {summary}\n"
                f"📌 {from_status} → <b>{to_status}</b>\n"
                f"{issue_url}"
            )

        elif issue_event_type_name == "issue_updated":
            text = (
               f"📝 <b>Обновлена задача</b>\n"
               f"<b>{key}</b>: {summary}\n"
               f"Автор: {reporter.get('displayName')}"
           )


        elif issue_event_type_name == "issue_deleted":
            text = (
               f"❌ <b>Удалена задача</b>\n"
               f"<b>{key}</b>: {summary}\n"
               f"Автор: {reporter.get('displayName')}"
           )

        elif issue_event_type_name  == "issue_commented":
            text = (
               f"💬 <b>Новый комментарий</b> в задаче <b>{key}</b>: {summary}\n"
               f"От: {comment_author}\n"
               f"{comment_body[:4000]}\n\n"
               f"{issue_url}"
           )

        elif issue_event_type_name == "issue_comment_edited":
           text = (
               f"✏️ <b>Комментарий обновлён</b> в задаче <b>{key}</b>: {summary}\n"
               f"Автор: {comment_author}\n"
               f"{comment_body[:4000]}\n\n"
               f"{issue_url}"
           )

        elif issue_event_type_name == "issue_comment_deleted":
           text = (
               f"🗑 <b>Комментарий удалён</b> в задаче <b>{key}</b>: {summary}\n"
               f"Автор: {comment_author}\n"
               f"{comment_body[:4000]}\n\n"
               f"{issue_url}"
           )

        else:
           print(f"⚠️ Неизвестный тип события: {webhook_event} {issue_event_type_name}")
           return "Ignored", 200

    # --- Рассылка ---
    if text:
        for chat_id in recipients:
            send_telegram(chat_id, text)
        print(f"📤 Отправлено {len(recipients)} уведомлений по {key}")
    else:
        print(f"⚠️ Нет текста для события {webhook_event}")

    return "OK", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

