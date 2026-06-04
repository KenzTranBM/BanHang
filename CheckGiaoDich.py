# check_sepay_transactions.py

import requests

API_KEY = "YHM5YCOKB4PNKRLEMK79TDHPQCRSNRPRZE2X7OIE9NXAXLMH8DWTI8X4B6POAO2J"

url = "https://my.sepay.vn/userapi/transactions/list"

headers = {
    "Authorization": f"Bearer {API_KEY}",
}

params = {
    "limit": 10,
}

response = requests.get(url, headers=headers, params=params, timeout=15)
data = response.json()

print(data)

if data.get("status") == 200:
    transactions = data.get("transactions", [])

    for tx in transactions:
        print("-" * 40)
        print("ID:", tx.get("id"))
        print("Ngày:", tx.get("transaction_date"))
        print("Ngân hàng:", tx.get("bank_brand_name"))
        print("STK:", tx.get("account_number"))
        print("Tiền vào:", tx.get("amount_in"))
        print("Tiền ra:", tx.get("amount_out"))
        print("Nội dung:", tx.get("transaction_content"))
else:
    print("Lỗi:", data.get("error"))