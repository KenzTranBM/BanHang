# app.py
import json
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from flask import Response
import requests
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from openai import OpenAI

app = Flask(__name__)
app.secret_key = "change-this-secret-key"

BANK_CODE = "VPB"
ACCOUNT_NO = "459980431"
ACCOUNT_NAME = "TRAN HUY HOANG"

PAYMENT_TIMEOUT_SECONDS = 300
SEPAY_TRANSACTIONS_URL = "https://my.sepay.vn/userapi/transactions/list"
ORDER_FILE = "order.txt"
PUBLIC_ORDER_STATUS_URL = "http://103.189.203.6:5000/api/order-status"
IS_PUBLIC_SERVER = False

def get_public_order_status():
    if IS_PUBLIC_SERVER:
        return {
            "active_order": False,
            "order_text": "",
        }

    try:
        response = requests.get(PUBLIC_ORDER_STATUS_URL, timeout=2)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as error:
        print("Không gọi được public order-status:", error)
        return {
            "active_order": False,
            "order_text": "",
        }

@app.route("/api/sync-order-status")
def api_sync_order_status():
    public_status = get_public_order_status()

    if public_status.get("active_order"):
        session["remote_order_text"] = public_status.get("order_text", "")
        session.modified = True

        return jsonify({
            "active_order": True,
            "redirect_url": url_for("success", remote=1),
        })

    return jsonify({
        "active_order": False,
    })
def local_order_file_has_active_order():
    order_path = Path(ORDER_FILE)
    if not order_path.exists():
        return False

    return bool(order_path.read_text(encoding="utf-8").strip())


def public_order_file_has_active_order():
    if IS_PUBLIC_SERVER:
        return False

    try:
        response = requests.get(PUBLIC_ORDER_STATUS_URL, timeout=2)
        response.raise_for_status()
        data = response.json()
        return bool(data.get("active_order"))
    except requests.RequestException:
        return False


def order_file_has_active_order():
    if local_order_file_has_active_order():
        return True

    if public_order_file_has_active_order():
        return True

    return False
def order_file_has_active_order():
    order_path = Path(ORDER_FILE)
    if not order_path.exists():
        return False

    return bool(order_path.read_text(encoding="utf-8").strip())


def clear_order_file():
    Path(ORDER_FILE).write_text("", encoding="utf-8")
DRINKS = [
    {
        "id": 1,
        "key": "ca_phe_den",
        "name": "Cà phê đen",
        "price": 20000,
        "image": "images/ca_phe_den.png",
    },
    {
        "id": 2,
        "key": "ca_phe_sua",
        "name": "Cà phê sữa",
        "price": 25000,
        "image": "images/ca_phe_sua.png",
    },
    {
        "id": 3,
        "key": "bac_xiu",
        "name": "Bạc xỉu",
        "price": 30000,
        "image": "images/bac_xiu.png",
    },
    {
        "id": 4,
        "key": "milo",
        "name": "Milo",
        "price": 40000,
        "image": "images/milo.png",
    },
]

SIZE_EXTRA_PRICE = {"M": 0, "L": 5000}


def read_key(file_name):
    key_path = Path(file_name)
    if not key_path.exists():
        raise FileNotFoundError(f"Không tìm thấy file {file_name}")

    value = key_path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"File {file_name} đang trống")

    return value


openai_client = OpenAI(api_key=read_key("keychatgpt.txt"))


def format_currency(amount):
    return f"{amount:,.0f} đ".replace(",", ".")


app.jinja_env.filters["currency"] = format_currency


def save_paid_order_to_file(order):
    lines = [
        "=" * 40,
        f"ID khách: {order['customer_id']}",
        f"Thời gian: {order['created_at']}",
        f"Thanh toán lúc: {order.get('paid_at', '')}",
        "Danh sách món:",
    ]

    for item in order["items"]:
        ice_text = "Có đá" if item["ice"] == "yes" else "Không đá"
        lines.append(
            f"- {item['drink']['name']} | Size {item['size']} | "
            f"{ice_text} | SL: {item['quantity']} | "
            f"Tạm tính: {format_currency(item['subtotal'])}"
        )

    lines.extend([
        f"Tổng tiền: {format_currency(order['total'])}",
        "=" * 40,
        "",
    ])

    with open(ORDER_FILE, "a", encoding="utf-8") as file:
        file.write("\n".join(lines))


def get_today_key():
    return datetime.now().strftime("%Y%m%d")


def get_next_customer_id():
    today_key = get_today_key()

    if session.get("order_date") != today_key:
        session["order_date"] = today_key
        session["customer_order_number"] = 0

    session["customer_order_number"] += 1
    session.modified = True
    return session["customer_order_number"]


def get_cart():
    cart = session.get("cart", {})
    normalized_cart = {}

    for key, value in cart.items():
        if isinstance(value, dict):
            normalized_cart[key] = value
            continue

        drink_id = int(key)
        new_key = f"{drink_id}_M_yes"
        normalized_cart[new_key] = {
            "drink_id": drink_id,
            "size": "M",
            "ice": "yes",
            "quantity": int(value),
        }

    session["cart"] = normalized_cart
    session.modified = True
    return normalized_cart


def save_cart(cart):
    session["cart"] = cart
    session.modified = True


def find_drink(drink_id):
    return next((drink for drink in DRINKS if drink["id"] == drink_id), None)


def find_drink_by_key(drink_key):
    return next((drink for drink in DRINKS if drink["key"] == drink_key), None)


def get_drink_name(drink_key):
    drink = find_drink_by_key(drink_key)
    return drink["name"] if drink else "món đó"


def get_size_text(size):
    return "lớn" if size == "L" else "nhỏ"


def get_ice_text(ice):
    return "có đá" if ice == "yes" else "không đá"


def build_cart_items():
    cart = get_cart()
    items = []
    total = 0

    for cart_key, item_data in cart.items():
        drink = find_drink(item_data["drink_id"])
        if not drink:
            continue

        size = item_data["size"]
        ice = item_data["ice"]
        quantity = item_data["quantity"]
        price = drink["price"] + SIZE_EXTRA_PRICE.get(size, 0)
        subtotal = price * quantity
        total += subtotal

        items.append({
            "cart_key": cart_key,
            "drink": drink,
            "size": size,
            "ice": ice,
            "price": price,
            "quantity": quantity,
            "subtotal": subtotal,
        })

    return items, total


def add_item_to_cart(drink_id, size, ice, quantity):
    if size not in SIZE_EXTRA_PRICE:
        size = "M"

    if ice not in ["yes", "no"]:
        ice = "yes"

    quantity = max(int(quantity), 1)
    cart_key = f"{drink_id}_{size}_{ice}"
    cart = get_cart()

    if cart_key not in cart:
        cart[cart_key] = {
            "drink_id": drink_id,
            "size": size,
            "ice": ice,
            "quantity": quantity,
        }
    else:
        cart[cart_key]["quantity"] += quantity

    save_cart(cart)


def create_vietqr_url(amount, content):
    query = urlencode({
        "amount": amount,
        "addInfo": content,
        "accountName": ACCOUNT_NAME,
    })

    return f"https://img.vietqr.io/image/{BANK_CODE}-{ACCOUNT_NO}-compact2.png?{query}"


def get_sepay_transactions():
    headers = {"Authorization": f"Bearer {read_key('keysepay.txt')}"}
    response = requests.get(
        SEPAY_TRANSACTIONS_URL,
        headers=headers,
        params={"limit": 20},
        timeout=15,
    )
    response.raise_for_status()

    data = response.json()
    if data.get("status") != 200:
        return []

    return data.get("transactions", [])


def has_payment_expired(order):
    expires_at = datetime.fromisoformat(order["payment_expires_at"])
    return datetime.now() > expires_at


def has_paid_successfully(order):
    expected_content = order["payment_content"]
    expected_amount = int(order["total"])

    for tx in get_sepay_transactions():
        amount_in = int(float(tx.get("amount_in") or 0))
        content = tx.get("transaction_content") or ""

        if amount_in >= expected_amount and expected_content in content:
            order["status"] = "paid"
            order["paid_transaction_id"] = tx.get("id")
            order["paid_at"] = tx.get("transaction_date")
            return True

    return False


def normalize_ai_item(item):
    drink = find_drink_by_key(item.get("drink_key"))
    if not drink:
        return None

    size = item.get("size")
    ice = item.get("ice")
    quantity = item.get("quantity", 1)

    if size is not None:
        size = str(size).upper()

    if size not in ["M", "L"]:
        size = None

    if ice not in ["yes", "no"]:
        ice = None

    try:
        quantity = int(quantity)
    except (TypeError, ValueError):
        quantity = 1

    return {
        "drink_id": drink["id"],
        "drink_key": drink["key"],
        "drink_name": drink["name"],
        "size": size,
        "ice": ice,
        "quantity": max(quantity, 1),
    }


def normalize_ai_items(items):
    normalized = []

    for item in items:
        normalized_item = normalize_ai_item(item)
        if normalized_item:
            normalized.append(normalized_item)

    return normalized


def normalize_spoken_text(text):
    replacements = {
        "đáng": "đá",
        "đã": "đá",
        "ko": "không",
        "khong": "không",
        "khỏi": "không",
    }
    normalized_text = (text or "").lower()

    for source, target in replacements.items():
        normalized_text = normalized_text.replace(source, target)

    return normalized_text


def extract_spoken_slots(user_text):
    normalized_text = normalize_spoken_text(user_text)

    drink_key = None
    if any(keyword in normalized_text for keyword in ["cà phê đen", "cafe đen", "ly đen"]):
        drink_key = "ca_phe_den"
    elif any(keyword in normalized_text for keyword in ["cà phê sữa", "cafe sữa", "cà phê sửa", "nâu"]):
        drink_key = "ca_phe_sua"
    elif any(keyword in normalized_text for keyword in ["bạc xỉu", "bạc xíu", "bạc sỉu"]):
        drink_key = "bac_xiu"
    elif any(keyword in normalized_text for keyword in ["milo", "mát cha", "macha", "trà xanh"]):
        drink_key = "milo"

    size = None
    if any(keyword in normalized_text for keyword in ["ly lớn", "size lớn", "lớn", "to"]):
        size = "L"
    elif any(keyword in normalized_text for keyword in ["ly nhỏ", "size nhỏ", "nhỏ", "vừa"]):
        size = "M"

    ice = None
    if any(keyword in normalized_text for keyword in ["không đá", "đừng cho đá", "đừng bỏ đá"]):
        ice = "no"
    elif any(keyword in normalized_text for keyword in ["có đá", "cho đá", "thêm đá", "bỏ đá"]):
        ice = "yes"

    quantity = 1
    if any(keyword in normalized_text for keyword in ["hai ly", "2 ly", "hai cốc", "2 cốc"]):
        quantity = 2
    elif any(keyword in normalized_text for keyword in ["ba ly", "3 ly", "ba cốc", "3 cốc"]):
        quantity = 3

    is_update = any(
        keyword in normalized_text
        for keyword in ["đổi", "sửa", "thay", "ly đó", "món đó", "cái đó", "không có đá"]
    )

    return {
        "drink_key": drink_key,
        "size": size,
        "ice": ice,
        "quantity": quantity,
        "is_update": is_update,
    }


def merge_item_slots(base_item, spoken_slots):
    merged_item = dict(base_item or {})

    for key in ["drink_key", "size", "ice"]:
        if spoken_slots.get(key):
            merged_item[key] = spoken_slots[key]

    if spoken_slots.get("quantity"):
        merged_item["quantity"] = spoken_slots["quantity"]

    return normalize_ai_item(merged_item)


def get_last_cart_key():
    cart = get_cart()

    if not cart:
        return None

    return next(reversed(cart))


def get_cart_item_by_key(cart_key):
    cart = get_cart()
    item = cart.get(cart_key)

    if not item:
        return None

    drink = find_drink(item["drink_id"])
    if not drink:
        return None

    return {
        "drink_id": drink["id"],
        "drink_key": drink["key"],
        "drink_name": drink["name"],
        "size": item["size"],
        "ice": item["ice"],
        "quantity": item["quantity"],
    }


def update_cart_item(cart_key, updated_item):
    cart = get_cart()
    old_item = cart.get(cart_key)
    drink = find_drink_by_key(updated_item.get("drink_key"))

    if not old_item or not drink or not is_complete_item(updated_item):
        return None

    quantity = max(int(updated_item.get("quantity") or old_item.get("quantity") or 1), 1)
    cart.pop(cart_key, None)

    new_key = f"{drink['id']}_{updated_item['size']}_{updated_item['ice']}"
    if new_key in cart:
        cart[new_key]["quantity"] += quantity
    else:
        cart[new_key] = {
            "drink_id": drink["id"],
            "size": updated_item["size"],
            "ice": updated_item["ice"],
            "quantity": quantity,
        }

    save_cart(cart)

    return {
        "drink_id": drink["id"],
        "drink_key": drink["key"],
        "drink_name": drink["name"],
        "size": updated_item["size"],
        "ice": updated_item["ice"],
        "quantity": quantity,
    }


def build_updated_reply(item):
    drink_name = get_drink_name(item["drink_key"])
    size_text = get_size_text(item["size"])
    ice_text = get_ice_text(item["ice"])
    return f"Dạ mình đã sửa thành {drink_name} {size_text} {ice_text} rồi ạ."


def sanitize_voice_result_with_user_text(result, user_text):
    spoken_slots = extract_spoken_slots(user_text)
    pending_item = get_voice_pending_item()

    if spoken_slots["is_update"] and get_cart():
        last_cart_key = get_last_cart_key()
        last_item = get_cart_item_by_key(last_cart_key)
        updated_item = merge_item_slots(last_item, spoken_slots)

        if updated_item:
            result["intent"] = "update"
            result["target_cart_key"] = last_cart_key
            result["pending_item"] = updated_item
            result["items"] = []
            return result

    if pending_item:
        merged_item = merge_item_slots(pending_item, spoken_slots)
        if merged_item:
            result["pending_item"] = merged_item
            result["items"] = []
            result["intent"] = "add" if is_complete_item(merged_item) else "ask"
            return result

    if spoken_slots["drink_key"]:
        candidate_item = merge_item_slots({}, spoken_slots)
        if candidate_item:
            result["pending_item"] = candidate_item
            result["items"] = []
            result["intent"] = "add" if is_complete_item(candidate_item) else "ask"
            return result

    return result


def get_voice_messages():
    return session.get("voice_messages", [])


def get_voice_pending_item():
    pending_item = session.get("voice_pending_item")
    if not isinstance(pending_item, dict):
        return None

    normalized_item = normalize_ai_item(pending_item)
    if not normalized_item:
        return None

    return {
        "drink_key": normalized_item["drink_key"],
        "quantity": normalized_item["quantity"],
        "size": normalized_item["size"],
        "ice": normalized_item["ice"],
    }


def save_voice_pending_item(pending_item):
    normalized_item = normalize_ai_item(pending_item or {})
    if not normalized_item:
        session["voice_pending_item"] = None
        session.modified = True
        return

    session["voice_pending_item"] = {
        "drink_key": normalized_item["drink_key"],
        "quantity": normalized_item["quantity"],
        "size": normalized_item["size"],
        "ice": normalized_item["ice"],
    }
    session.modified = True


def clear_voice_context():
    session["voice_messages"] = []
    session["voice_pending_item"] = None
    session.modified = True


def build_current_cart_for_ai():
    items, _ = build_cart_items()
    return [
        {
            "name": item["drink"]["name"],
            "size": item["size"],
            "ice": item["ice"],
            "quantity": item["quantity"],
        }
        for item in items
    ]


def is_complete_item(item):
    return bool(
        item
        and item.get("drink_key")
        and item.get("size") in ["M", "L"]
        and item.get("ice") in ["yes", "no"]
    )


def build_missing_info_reply(pending_item):
    drink_name = get_drink_name(pending_item.get("drink_key"))

    missing_size = pending_item.get("size") not in ["M", "L"]
    missing_ice = pending_item.get("ice") not in ["yes", "no"]

    if missing_size and missing_ice:
        return f"Bạn muốn {drink_name} ly nhỏ hay ly lớn, có đá hay không đá?"

    if missing_size:
        return f"Dạ {get_ice_text(pending_item['ice'])} rồi ạ, bạn muốn ly nhỏ hay ly lớn?"

    if missing_ice:
        return f"Dạ ly {get_size_text(pending_item['size'])} rồi ạ, bạn muốn có đá hay không đá?"

    return ""


def add_complete_voice_item(item):
    drink = find_drink_by_key(item["drink_key"])
    if not drink:
        return None

    add_item_to_cart(
        drink_id=drink["id"],
        size=item["size"],
        ice=item["ice"],
        quantity=item.get("quantity", 1),
    )
    return {
        "drink_id": drink["id"],
        "drink_key": drink["key"],
        "drink_name": drink["name"],
        "size": item["size"],
        "ice": item["ice"],
        "quantity": item.get("quantity", 1),
    }


def build_added_reply(item):
    quantity = item.get("quantity", 1)
    drink_name = get_drink_name(item["drink_key"])
    size_text = get_size_text(item["size"])
    ice_text = get_ice_text(item["ice"])
    return (
        f"Dạ đã thêm {quantity} ly {drink_name} {size_text} {ice_text}. "
        "Bạn muốn gọi thêm gì nữa không?"
    )


def build_voice_prompt(user_text, voice_messages, pending_item, current_cart):
    return f"""
Bạn là AI nhân viên order nước bằng tiếng Việt cho quán cafe vỉa hè.

Bạn phải hiểu tiếng Việt đời thường, nói sai, nói thiếu, nói lẫn do nhận diện giọng nói.
Không được máy móc đòi khách nói đúng từng chữ.

MENU:
- ca_phe_den: Cà phê đen, 20000
- ca_phe_sua: Cà phê sữa, 25000
- bac_xiu: Bạc xỉu, 30000
- milo: milo, 40000

SIZE:
- M = Ly nhỏ
- L = Ly lớn, cộng 5000

ĐÁ:
- yes = có đá
- no = không đá

GIỎ HÀNG HIỆN TẠI:
{json.dumps(current_cart, ensure_ascii=False)}

MÓN ĐANG HỎI DỞ:
{json.dumps(pending_item, ensure_ascii=False)}

LỊCH SỬ HỘI THOẠI:
{json.dumps(voice_messages, ensure_ascii=False)}

KHÁCH VỪA NÓI:
{user_text}

QUY TẮC QUAN TRỌNG:
1. Phải ưu tiên cập nhật MÓN ĐANG HỎI DỞ trước khi tạo món mới.
2. Nếu MÓN ĐANG HỎI DỞ đã có món, khách chỉ nói "ly lớn", "ly nhỏ", "có đá", "không đá" thì đó là thông tin bổ sung cho món đang hỏi dở.
3. Không hỏi lại thông tin đã có trong MÓN ĐANG HỎI DỞ.
4. Tuyệt đối không tự mặc định size M hoặc có đá. Chỉ add khi khách đã nói rõ đủ drink_key, size và ice.
5. Nếu khách nói "cà phê" chung chung thì hỏi lại "cà phê đen hay cà phê sữa", không tự chọn.
6. Nếu khách nói "có đáng", "có đã" thì hiểu là "có đá".
7. Nếu khách nói "bỏ đá" mà không có chữ "không/khỏi/đừng" thì hiểu là có đá.
8. Nếu khách nói "không đá", "khỏi đá", "đừng cho đá" thì hiểu là không đá.
9. Khi thiếu thông tin, intent = ask, items = [], pending_item giữ thông tin đã biết.
10. Khi đủ thông tin, intent = add, items chứa đúng 1 món vừa hoàn tất, pending_item = null.
11. Nếu khách nói sửa/đổi/thay món vừa gọi, ví dụ "ly đó không đá", "đổi ly đó thành ly lớn", intent = update, không add món mới.
12. Nếu khách chốt đơn/thanh toán và giỏ hàng có món, intent = confirm.
13. Nếu khách hủy/làm lại/xóa hết, intent = clear.
14. Reply ngắn, tự nhiên, giống nhân viên bán nước.

TỪ KHÓA:
- Cà phê đen: "cà phê đen", "cafe đen", "đen", "ly đen"
- Cà phê sữa: "cà phê sữa", "cafe sữa", "cà phê sửa", "nâu", "sữa"
- Bạc xỉu: "bạc xỉu", "bạc xíu", "bạc sỉu"
- milo: "milo", "mát cha", "macha", "trà xanh"
- Size M: "nhỏ", "ly nhỏ", "size nhỏ", "m", "em", "vừa"
- Size L: "lớn", "ly lớn", "size lớn", "l", "eo", "to"
- Có đá: "có đá", "có đáng", "có đã", "đá", "cho đá", "thêm đá", "bỏ đá"
- Không đá: "không đá", "ko đá", "khỏi đá", "đừng cho đá", "đừng bỏ đá"

TRẢ VỀ JSON HỢP LỆ:
{{
  "reply": "câu trả lời ngắn cho khách",
  "intent": "ask|add|update|confirm|clear|unknown",
  "pending_item": {{
    "drink_key": "ca_phe_den|ca_phe_sua|bac_xiu|milo",
    "quantity": 1,
    "size": "M|L|null",
    "ice": "yes|no|null"
  }},
  "items": [
    {{
      "drink_key": "ca_phe_den|ca_phe_sua|bac_xiu|milo",
      "quantity": 1,
      "size": "M|L",
      "ice": "yes|no"
    }}
  ]
}}

CHỈ TRẢ VỀ JSON.
KHÔNG MARKDOWN.
KHÔNG GIẢI THÍCH NGOÀI JSON.
"""


def parse_voice_order_with_ai(user_text):
    voice_messages = get_voice_messages()
    pending_item = get_voice_pending_item()
    current_cart = build_current_cart_for_ai()
    prompt = build_voice_prompt(user_text, voice_messages, pending_item, current_cart)

    response = openai_client.responses.create(
        model="gpt-4.1-nano",
        input=prompt,
    )

    try:
        result = json.loads(response.output_text)
    except json.JSONDecodeError:
        return {
            "reply": "Mình chưa nghe rõ, bạn nói lại giúp mình nhé.",
            "intent": "unknown",
            "pending_item": pending_item,
            "items": [],
        }

    if not isinstance(result, dict):
        return {
            "reply": "Mình chưa nghe rõ, bạn nói lại giúp mình nhé.",
            "intent": "unknown",
            "pending_item": pending_item,
            "items": [],
        }

    intent = result.get("intent", "unknown")
    if intent not in ["ask", "add", "update", "confirm", "clear", "unknown"]:
        intent = "unknown"

    return {
        "reply": result.get("reply") or "Mình chưa nghe rõ, bạn nói lại giúp mình nhé.",
        "intent": intent,
        "pending_item": result.get("pending_item"),
        "items": result.get("items", []),
    }


def handle_voice_result(result):
    intent = result["intent"]
    pending_item = get_voice_pending_item()

    if intent == "clear":
        session.pop("cart", None)
        clear_voice_context()
        result["reply"] = "Dạ mình đã xóa đơn, bạn muốn gọi món gì mới?"
        result["items"] = []
        return result

    if intent == "confirm":
        save_voice_pending_item(pending_item)
        result["items"] = []
        return result

    if intent == "update":
        target_cart_key = result.get("target_cart_key") or get_last_cart_key()
        candidate_item = normalize_ai_item(result.get("pending_item") or {})

        if target_cart_key and is_complete_item(candidate_item):
            updated_item = update_cart_item(target_cart_key, candidate_item)
            if updated_item:
                session["voice_pending_item"] = None
                result["items"] = [updated_item]
                result["reply"] = build_updated_reply(updated_item)
                return result

        result["intent"] = "ask"
        intent = "ask"

    if intent == "add":
        normalized_items = normalize_ai_items(result.get("items", []))

        if normalized_items:
            added_item = normalized_items[0]
            add_complete_voice_item(added_item)
            session["voice_pending_item"] = None
            result["items"] = [added_item]
            result["reply"] = build_added_reply(added_item)
            return result

        candidate_item = normalize_ai_item(result.get("pending_item") or {})
        if is_complete_item(candidate_item):
            added_item = add_complete_voice_item(candidate_item)
            session["voice_pending_item"] = None
            result["items"] = [added_item]
            result["reply"] = build_added_reply(added_item)
            return result

        intent = "ask"
        result["intent"] = "ask"

    if intent == "ask":
        candidate_item = normalize_ai_item(result.get("pending_item") or {})

        if candidate_item:
            save_voice_pending_item(candidate_item)

            if is_complete_item(candidate_item):
                added_item = add_complete_voice_item(candidate_item)
                session["voice_pending_item"] = None
                result["intent"] = "add"
                result["items"] = [added_item]
                result["reply"] = build_added_reply(added_item)
                return result

            result["items"] = []
            result["reply"] = build_missing_info_reply(candidate_item) or result["reply"]
            return result

    save_voice_pending_item(pending_item)
    result["items"] = []
    return result


def append_voice_message(user_text, assistant_reply):
    voice_messages = get_voice_messages()
    voice_messages.append({"role": "user", "content": user_text})
    voice_messages.append({"role": "assistant", "content": assistant_reply})
    session["voice_messages"] = voice_messages[-20:]
    session.modified = True


@app.route("/")
def index():
    if order_file_has_active_order():
        return redirect(url_for("success"))

    items, total = build_cart_items()
    return render_template("index.html", drinks=DRINKS, items=items, total=total)


@app.route("/add-to-cart/<int:drink_id>", methods=["POST"])
def add_to_cart(drink_id):
    if not find_drink(drink_id):
        return redirect(url_for("index"))

    add_item_to_cart(
        drink_id=drink_id,
        size=request.form.get("size", "M"),
        ice=request.form.get("ice", "yes"),
        quantity=1,
    )
    return redirect(url_for("index"))



@app.route("/api/transcribe", methods=["POST"])
def transcribe_audio():
    if "audio" not in request.files:
        return jsonify({"error": "Không có file audio"}), 400

    audio_file = request.files["audio"]
    suffix = Path(audio_file.filename or "voice.webm").suffix or ".webm"

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp_file:
        audio_path = temp_file.name
        audio_file.save(audio_path)

    try:
        with open(audio_path, "rb") as file:
            transcript = openai_client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=file,
                language="vi",
            )

        text = (transcript.text or "").strip()
        return jsonify({"text": text})

    except Exception as error:
        print("Lỗi transcribe audio:", error)
        return jsonify({"error": "Không nhận diện được giọng nói"}), 500

    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


@app.route("/api/voice-start", methods=["POST"])
def voice_start():
    if "voice_messages" not in session:
        session["voice_messages"] = []

    if "voice_pending_item" not in session:
        session["voice_pending_item"] = None

    session.modified = True

    return jsonify({
        "reply": "Xin chào, bạn muốn uống món gì? Quán có cà phê đen, cà phê sữa, bạc xỉu và milo.",
    })


@app.route("/api/voice-order", methods=["POST"])
def voice_order():
    data = request.get_json(silent=True) or {}
    user_text = data.get("text", "").strip()

    if not user_text:
        return jsonify({
            "reply": "Mình chưa nghe rõ, bạn nói lại giúp mình nhé.",
            "intent": "unknown",
            "items": [],
            "cart_html": render_template("_cart_content.html", items=build_cart_items()[0], total=build_cart_items()[1]),
            "checkout_url": url_for("checkout"),
        })

    result = parse_voice_order_with_ai(user_text)
    result = sanitize_voice_result_with_user_text(result, user_text)
    result = handle_voice_result(result)

    append_voice_message(user_text, result["reply"])

    items, total = build_cart_items()
    result["cart_html"] = render_template("_cart_content.html", items=items, total=total)
    result["checkout_url"] = url_for("checkout")

    return jsonify(result)


@app.route("/update-cart/<cart_key>", methods=["POST"])
def update_cart(cart_key):
    quantity = int(request.form.get("quantity", 0))
    cart = get_cart()

    if cart_key in cart:
        if quantity <= 0:
            cart.pop(cart_key)
        else:
            cart[cart_key]["quantity"] = quantity

    save_cart(cart)
    return redirect(url_for("index"))


@app.route("/remove-from-cart/<cart_key>", methods=["POST"])
def remove_from_cart(cart_key):
    cart = get_cart()
    cart.pop(cart_key, None)
    save_cart(cart)
    return redirect(url_for("index"))


@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    items, total = build_cart_items()

    if not items:
        return redirect(url_for("index"))

    customer_id = get_next_customer_id()
    payment_content = f"ID{customer_id}"
    expires_at = datetime.now() + timedelta(seconds=PAYMENT_TIMEOUT_SECONDS)

    session["pending_order"] = {
        "customer_id": customer_id,
        "items": items,
        "total": total,
        "created_at": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "payment_content": payment_content,
        "qr_url": create_vietqr_url(total, payment_content),
        "status": "pending",
        "payment_expires_at": expires_at.isoformat(),
    }
    session.pop("cart", None)
    clear_voice_context()

    return redirect(url_for("payment"))


@app.route("/payment")
def payment():
    order = session.get("pending_order")

    if not order:
        return redirect(url_for("index"))

    if has_payment_expired(order):
        session.pop("pending_order", None)
        return redirect(url_for("index"))

    expires_at = datetime.fromisoformat(order["payment_expires_at"])
    remaining_seconds = max(0, int((expires_at - datetime.now()).total_seconds()))

    return render_template("payment.html", order=order, remaining_seconds=remaining_seconds)


@app.route("/check-payment")
def check_payment():
    order = session.get("pending_order")

    if not order:
        return jsonify({"paid": False, "expired": True, "message": "Giao dịch đã kết thúc"})

    if has_payment_expired(order):
        session.pop("pending_order", None)
        session.modified = True
        return jsonify({"paid": False, "expired": True, "message": "Mã QR đã hết hiệu lực"})

    try:
        if has_paid_successfully(order):
            save_paid_order_to_file(order)

            session["last_order"] = order
            session.pop("pending_order", None)
            clear_voice_context()
            session.modified = True

            return jsonify({
                "paid": True,
                "expired": False,
                "message": "Đã nhận tiền thành công",
            })
    except Exception as error:
        return jsonify({"paid": False, "expired": False, "message": str(error)})

    return jsonify({"paid": False, "expired": False, "message": "Đang chờ nhận tiền..."})


@app.route("/cancel-payment", methods=["POST"])
def cancel_payment():
    session.pop("pending_order", None)
    session.modified = True
    return redirect(url_for("index"))


@app.route("/success")
def success():
    remote_order_text = session.get("remote_order_text")

    if request.args.get("remote") == "1" and remote_order_text:

        remote_order = parse_remote_order_text(
            remote_order_text
        )

        return render_template(
            "success.html",
            order=None,

            remote_order_text=remote_order_text,
            remote_order_id=remote_order["customer_id"],
            remote_order_time=remote_order["created_at"],
            remote_order_items=remote_order["items"],
            remote_order_total=remote_order["total"],
        )

    order = session.get("last_order")

    if not order:
        return redirect(url_for("index"))

    return render_template(
        "success.html",
        order=order,
        remote_order_text=None,
    )

@app.route("/complete-order", methods=["POST"])
def complete_order():
    clear_order_file()
    session.pop("last_order", None)
    session.pop("cart", None)
    clear_voice_context()
    session.modified = True
    return redirect(url_for("index"))

@app.route("/complete-remote-order", methods=["POST"])
def complete_remote_order():
    try:
        response = requests.post(
            "http://103.189.203.6:5000/api/complete-public-order",
            timeout=3,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        print("Không thể hoàn thành order public:", error)

    session.pop("remote_order_text", None)
    session.modified = True

    return redirect(url_for("index"))
import re
def parse_remote_order_text(order_text):
    result = {
        "customer_id": "",
        "created_at": "",
        "items": [],
        "total": "",
    }

    id_match = re.search(r"ID khách:\s*(\d+)", order_text)
    if id_match:
        result["customer_id"] = id_match.group(1)

    time_match = re.search(r"Thời gian:\s*(.+)", order_text)
    if time_match:
        result["created_at"] = time_match.group(1).strip()

    total_match = re.search(r"Tổng tiền:\s*(.+)", order_text)
    if total_match:
        result["total"] = total_match.group(1).strip()

    item_pattern = re.compile(
        r"-\s*(.*?)\s*\|\s*Size\s*(M|L)\s*\|\s*(Có đá|Không đá)\s*\|\s*SL:\s*(\d+)\s*\|\s*Tạm tính:\s*(.+)"
    )

    for match in item_pattern.finditer(order_text):
        result["items"].append({
            "name": match.group(1).strip(),
            "size": "Nhỏ" if match.group(2) == "M" else "Lớn",
            "ice": match.group(3).strip(),
            "quantity": match.group(4).strip(),
            "subtotal": match.group(5).strip(),
        })

    return result

@app.route("/api/tts", methods=["POST"])
def api_tts():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"error": "Missing text"}), 400

    try:
        speech = client.audio.speech.create(
            model="gpt-4o-mini-tts",
            voice="alloy",
            input=text,
            response_format="mp3",
        )

        return Response(
            speech.content,
            mimetype="audio/mpeg",
        )

    except Exception as error:
        return jsonify({"error": str(error)}), 500

if __name__ == "__main__":
    app.run(debug=True)
