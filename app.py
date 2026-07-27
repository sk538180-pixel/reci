from flask import Flask, render_template, request, render_template_string
from supabase import create_client, Client
import qrcode
import base64
from io import BytesIO
import uuid
import json
import random
import string
import requests
import re

app = Flask(__name__)
app.secret_key = 'recipt_secure_app_secret_key'

# Supabase Credentials
SUPABASE_URL = "https://qtzmgxvjibivdgodcfwz.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF0em1neHZqaWJpdmRnb2RjZnd6Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc0NTYyMzYsImV4cCI6MjA5MzAzMjIzNn0.o9US11mFFINPL80qO8x-5ns3sZgnoMlrYEt1v_-jXD8"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_or_create_valid_user_id(user_id):
    if user_id and user_id != -1:
        try:
            res = supabase.table('users').select('id').eq('id', user_id).execute()
            if res.data:
                return res.data[0]['id']
        except Exception:
            pass
    try:
        admin_res = supabase.table('users').select('id').eq('email', 'admin@recipt.app').execute()
        if admin_res.data:
            return admin_res.data[0]['id']
        ins = supabase.table('users').insert({'email': 'admin@recipt.app', 'name': 'Master Admin', 'wallet_balance': 999999}).execute()
        if ins.data:
            return ins.data[0]['id']
    except Exception:
        pass
    return None

# Root route: 100% Stealth "Domain Offline" page for any web browser visitor
@app.route('/')
def index():
    return render_template('offline.html')

# Block any legacy web login/submit attempts
@app.route('/login', methods=['GET', 'POST'])
@app.route('/admin', methods=['GET', 'POST'])
@app.route('/submit', methods=['GET', 'POST'])
def block_web():
    return render_template('offline.html'), 404

# ================= KOTLIN ANDROID MOBILE APP REST APIs =================

@app.route('/api/verify_key', methods=['POST'])
def api_verify_key():
    data = request.json or {}
    key_code = data.get('key_code', '').strip()
    device_id = data.get('device_id', '').strip()
    
    if not key_code:
        return {"status": "error", "message": "License Key is required"}, 400
    if not device_id:
        return {"status": "error", "message": "Device ID missing"}, 400
        
    try:
        # Master Admin Key
        if key_code == "ADMIN-MASTER-4035":
            admin_user_id = get_or_create_valid_user_id(-1) or -1
            return {
                "status": "success",
                "is_admin": True,
                "wallet_balance": 999999,
                "user_id": admin_user_id,
                "key_code": key_code,
                "message": "Admin Login Successful"
            }

        res = supabase.table('license_keys').select('*').eq('key_code', key_code).execute()
        if not res.data:
            return {"status": "error", "message": "Invalid License Key!"}, 401
            
        key_data = res.data[0]
        if key_data.get('status') == 'Blocked':
            return {"status": "error", "message": "This key has been blocked by Admin!"}, 403
            
        bound_device = key_data.get('device_id')
        if not bound_device:
            # Bind device hardware ID on first activation
            supabase.table('license_keys').update({'device_id': device_id, 'status': 'Active'}).eq('id', key_data['id']).execute()
        elif bound_device != device_id:
            return {"status": "error", "message": "Key is registered on another device! Contact Admin to reset."}, 403
            
        email = key_data.get('user_email') or f"user_{key_data['id']}@recipt.app"
        user_res = supabase.table('users').select('*').eq('email', email).execute()
        if user_res.data:
            user = user_res.data[0]
        else:
            initial_balance = key_data.get('initial_balance', 500)
            insert_user = supabase.table('users').insert({'email': email, 'name': key_data.get('user_note') or 'User', 'wallet_balance': initial_balance}).execute()
            user = insert_user.data[0]
            
        return {
            "status": "success",
            "is_admin": False,
            "wallet_balance": user.get('wallet_balance', 0),
            "user_id": user['id'],
            "email": user['email'],
            "key_code": key_code,
            "message": "Login Successful"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/user/info', methods=['GET', 'POST'])
def api_user_info():
    user_id = request.args.get('user_id') or (request.json.get('user_id') if request.json else None)
    if not user_id:
        return {"status": "error", "message": "User ID required"}, 400
    try:
        user_res = supabase.table('users').select('*').eq('id', user_id).execute()
        if user_res.data:
            user = user_res.data[0]
            return {
                "status": "success",
                "user_id": user['id'],
                "email": user['email'],
                "wallet_balance": user.get('wallet_balance', 0)
            }
        return {"status": "error", "message": "User not found"}, 404
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

def extract_fields_from_html(html):
    data = {}
    if not html:
        return data
    try:
        m = re.search(r'जिला :- <b>(.*?)</b>', html)
        if m: data['District'] = m.group(1).strip()
        m = re.search(r'अंचल :- <b>(.*?)</b>', html)
        if m: data['Anchal'] = m.group(1).strip()
        m = re.search(r'हल्का :- <b>(.*?)</b>', html)
        if m: data['Halka'] = m.group(1).strip()
        m = re.search(r'मौजा :- <b>(.*?)</b>', html)
        if m: data['Mauja'] = m.group(1).strip()
        m = re.search(r'मौजा/थाना संख्या :- <b>(.*?)</b>', html)
        if m: data['Thana'] = m.group(1).strip()
        m = re.search(r'जमाबंदी रेयत का नाम :- <b>(.*?)</b>', html)
        if m: data['Name'] = m.group(1).strip()
        m = re.search(r'अभिभावक का नाम :- <b>(.*?)</b>', html)
        if m: data['Name2'] = m.group(1).strip()
        m = re.search(r'पता :- <b>(.*?)</b>', html)
        if m: data['Pata'] = m.group(1).strip()
        m = re.search(r'जमाबन्दी संख्या :- <b>(.*?)</b>', html)
        if m: data['JamabandiNo'] = m.group(1).strip()
        m = re.search(r'भाग वर्तमान :- <b>(.*?)</b>', html)
        if m: data['BhagVartaman'] = m.group(1).strip()
        m = re.search(r'पृष्ठ संख्या :- <b>(.*?)</b>', html)
        if m: data['PrishthSankhya'] = m.group(1).strip()
        m = re.search(r'तिथि-\s*<b>(.*?)</b>', html)
        if m: data['Date'] = m.group(1).strip()
    except Exception as e:
        pass
    return data

# Fetch single receipt details for Editing
@app.route('/api/receipt/get', methods=['GET'])
def api_receipt_get():
    receipt_id = request.args.get('id')
    if not receipt_id:
        return {"status": "error", "message": "Receipt ID required"}, 400
    try:
        res = supabase.table('receipts').select('*').eq('id', receipt_id).execute()
        if res.data:
            receipt = res.data[0]
            if receipt.get('form_data') and isinstance(receipt['form_data'], str):
                try:
                    import json
                    receipt['form_data'] = json.loads(receipt['form_data'])
                except:
                    pass
            
            extracted = extract_fields_from_html(receipt.get('html_content', ''))
            if not receipt.get('form_data') or not isinstance(receipt['form_data'], dict):
                receipt['form_data'] = extracted
            else:
                for k, v in extracted.items():
                    if not receipt['form_data'].get(k) and v:
                        receipt['form_data'][k] = v

            return {"status": "success", "receipt": receipt}
        return {"status": "error", "message": "Receipt not found"}, 404
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

# Create Receipt (Mode 1: Form Data Se, Mode 2: Direct HTML / Purani Raseed Link Se)
@app.route('/api/receipt/create', methods=['POST'])
def api_receipt_create():
    data = request.json or {}
    user_id = data.get('user_id')
    is_admin = data.get('is_admin', False)
    
    if not user_id and not is_admin:
        return {"status": "error", "message": "User not authenticated"}, 401

    target_user_id = get_or_create_valid_user_id(user_id)

    if not is_admin and target_user_id:
        user_res = supabase.table('users').select('wallet_balance').eq('id', target_user_id).execute()
        if user_res.data:
            balance = user_res.data[0].get('wallet_balance', 0)
            if balance < 250:
                return {"status": "error", "message": "Insufficient Balance! Required ₹250."}, 400
            
            # Deduct ₹250
            new_bal = balance - 250
            supabase.table('users').update({'wallet_balance': new_bal}).eq('id', target_user_id).execute()

    custom_url = data.get('custom_url', '').strip()
    if not custom_url:
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
        custom_url = f"citizen/payment_receipt.aspxd=hfhfhf5755gj535424fydscukkcg{random_suffix}"

    host_url = request.host_url.rstrip('/')
    full_url = f"{host_url}/{custom_url}"
    
    # Generate Base64 QR Code
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(full_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

    mode = data.get('mode', 'form')
    old_receipt_url = data.get('old_receipt_url', '').strip()
    raw_html = data.get('raw_html', '').strip()

    if mode == 'direct_html' or old_receipt_url or raw_html:
        if old_receipt_url:
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                r = requests.get(old_receipt_url, headers=headers, timeout=15)
                html_fetched = r.text
            except Exception as e:
                return {"status": "error", "message": f"Failed to fetch Purani Raseed Link: {str(e)}"}, 400
        else:
            html_fetched = raw_html

        # Fix logo image paths so logo ALWAYS loads on live site
        html_fetched = html_fetched.replace('../img/logo2_new1.png', '/static/download.png')
        html_fetched = html_fetched.replace('img/logo2_new1.png', '/static/download.png')
        html_fetched = re.sub(r'src=["\'][^"\']*logo2_new1[^"\']*["\']', 'src="/static/download.png"', html_fetched)

        # Optional field replacements in HTML
        new_name = data.get('name', '').strip()
        new_name2 = data.get('name2', '').strip()
        new_halka = data.get('halka', '').strip()
        new_mauja = data.get('mauja', '').strip()
        new_thana = data.get('thana', '').strip()

        if new_name:
            html_fetched = re.sub(r'(जमाबंदी रेयत का नाम :- <b>).*?(</b>)', f'\\1{new_name}\\2', html_fetched)
            html_fetched = re.sub(r'(id="lblReiyatName"[^>]*>)[^<]*', f'\\1{new_name}', html_fetched)
        if new_name2:
            html_fetched = re.sub(r'(अभिभावक का नाम :- <b>).*?(</b>)', f'\\1{new_name2}\\2', html_fetched)
            html_fetched = re.sub(r'(id="lblGuardianName"[^>]*>)[^<]*', f'\\1{new_name2}', html_fetched)
        if new_halka:
            html_fetched = re.sub(r'(हल्का :- <b>).*?(</b>)', f'\\1{new_halka}\\2', html_fetched)
            html_fetched = re.sub(r'(id="lblHalkaName"[^>]*>)[^<]*', f'\\1{new_halka}', html_fetched)
        if new_mauja:
            html_fetched = re.sub(r'(मौजा :- <b>).*?(</b>)', f'\\1{new_mauja}\\2', html_fetched)
            html_fetched = re.sub(r'(id="lblMaujaName"[^>]*>)[^<]*', f'\\1{new_mauja}', html_fetched)
        if new_thana:
            html_fetched = re.sub(r'(मौजा/थाना संख्या :- <b>).*?(</b>)', f'\\1{new_thana}\\2', html_fetched)

        html_rendered = html_fetched
        extracted_fields = extract_fields_from_html(html_rendered)
        formatted_data = {
            "mode": "direct_html",
            "old_receipt_url": old_receipt_url,
            "qr_base64": qr_base64
        }
        formatted_data.update(extracted_fields)
        if new_name: formatted_data["Name"] = new_name
        if new_name2: formatted_data["Name2"] = new_name2
        if new_halka: formatted_data["Halka"] = new_halka
        if new_mauja: formatted_data["Mauja"] = new_mauja
        if new_thana: formatted_data["Thana"] = new_thana
    else:
        formatted_data = {
            "mode": "form",
            "District": data.get('district', 'वैशाली'),
            "Anchal": data.get('anchal', 'हाजीपुर'),
            "Halka": data.get('halka', 'हल्का-01'),
            "Mauja": data.get('mauja', 'मौजा-01'),
            "Name": data.get('name', ''),
            "Name2": data.get('name2', ''),
            "Pata": data.get('pata', ''),
            "Thana": data.get('thana', '101'),
            "Khata": data.get('khata', '12'),
            "Khesra": data.get('khesra', '345'),
            "JamabandiNo": data.get('jamabandi_no', '67'),
            "BhagVartaman": data.get('bhag_vartaman', '1'),
            "PrishthSankhya": data.get('prishth_sankhya', '23'),
            "Date": data.get('date', ''),
            "qr_base64": qr_base64
        }
        html_rendered = render_template('receipt_template.html', data=formatted_data)

    try:
        ins_payload = {
            'url_path': custom_url,
            'html_content': html_rendered,
            'form_data': formatted_data
        }
        if target_user_id:
            ins_payload['user_id'] = target_user_id

        supabase.table('receipts').insert(ins_payload).execute()

        return {
            "status": "success",
            "url_path": custom_url,
            "full_url": full_url,
            "message": "Receipt Created Successfully!"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

# Update Existing Receipt
@app.route('/api/receipt/update', methods=['POST'])
def api_receipt_update():
    data = request.json or {}
    receipt_id = data.get('receipt_id')
    if not receipt_id:
        return {"status": "error", "message": "Receipt ID required"}, 400
        
    try:
        res = supabase.table('receipts').select('*').eq('id', receipt_id).execute()
        if not res.data:
            return {"status": "error", "message": "Receipt not found"}, 404
            
        existing_receipt = res.data[0]
        custom_url = existing_receipt['url_path']
        host_url = request.host_url.rstrip('/')
        full_url = f"{host_url}/{custom_url}"

        # Generate Base64 QR Code
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(full_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        qr_base64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

        mode = data.get('mode', 'form')
        old_receipt_url = data.get('old_receipt_url', '').strip()
        raw_html = data.get('raw_html', '').strip()

        if mode == 'direct_html' or old_receipt_url or raw_html:
            if old_receipt_url:
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
                    r = requests.get(old_receipt_url, headers=headers, timeout=15)
                    html_fetched = r.text
                except Exception as e:
                    return {"status": "error", "message": f"Failed to fetch Purani Raseed Link: {str(e)}"}, 400
            else:
                html_fetched = raw_html

            # Fix logo image paths so logo ALWAYS loads on live site
            html_fetched = html_fetched.replace('../img/logo2_new1.png', '/static/download.png')
            html_fetched = html_fetched.replace('img/logo2_new1.png', '/static/download.png')
            html_fetched = re.sub(r'src=["\'][^"\']*logo2_new1[^"\']*["\']', 'src="/static/download.png"', html_fetched)

            new_name = data.get('name', '').strip()
            new_name2 = data.get('name2', '').strip()
            new_halka = data.get('halka', '').strip()
            new_mauja = data.get('mauja', '').strip()
            new_thana = data.get('thana', '').strip()

            if new_name:
                html_fetched = re.sub(r'(जमाबंदी रेयत का नाम :- <b>).*?(</b>)', f'\\1{new_name}\\2', html_fetched)
                html_fetched = re.sub(r'(id="lblReiyatName"[^>]*>)[^<]*', f'\\1{new_name}', html_fetched)
            if new_name2:
                html_fetched = re.sub(r'(अभिभावक का नाम :- <b>).*?(</b>)', f'\\1{new_name2}\\2', html_fetched)
                html_fetched = re.sub(r'(id="lblGuardianName"[^>]*>)[^<]*', f'\\1{new_name2}', html_fetched)
            if new_halka:
                html_fetched = re.sub(r'(हल्का :- <b>).*?(</b>)', f'\\1{new_halka}\\2', html_fetched)
                html_fetched = re.sub(r'(id="lblHalkaName"[^>]*>)[^<]*', f'\\1{new_halka}', html_fetched)
            if new_mauja:
                html_fetched = re.sub(r'(मौजा :- <b>).*?(</b>)', f'\\1{new_mauja}\\2', html_fetched)
                html_fetched = re.sub(r'(id="lblMaujaName"[^>]*>)[^<]*', f'\\1{new_mauja}', html_fetched)
            if new_thana:
                html_fetched = re.sub(r'(मौजा/थाना संख्या :- <b>).*?(</b>)', f'\\1{new_thana}\\2', html_fetched)

            html_rendered = html_fetched
            extracted_fields = extract_fields_from_html(html_rendered)
            formatted_data = {
                "mode": "direct_html",
                "old_receipt_url": old_receipt_url,
                "qr_base64": qr_base64
            }
            formatted_data.update(extracted_fields)
            if new_name: formatted_data["Name"] = new_name
            if new_name2: formatted_data["Name2"] = new_name2
            if new_halka: formatted_data["Halka"] = new_halka
            if new_mauja: formatted_data["Mauja"] = new_mauja
            if new_thana: formatted_data["Thana"] = new_thana
        else:
            formatted_data = {
                "mode": "form",
                "District": data.get('district', 'वैशाली'),
                "Anchal": data.get('anchal', 'हाजीपुर'),
                "Halka": data.get('halka', 'हल्का-01'),
                "Mauja": data.get('mauja', 'मौजा-01'),
                "Name": data.get('name', ''),
                "Name2": data.get('name2', ''),
                "Pata": data.get('pata', ''),
                "Thana": data.get('thana', '101'),
                "Khata": data.get('khata', '12'),
                "Khesra": data.get('khesra', '345'),
                "JamabandiNo": data.get('jamabandi_no', '67'),
                "BhagVartaman": data.get('bhag_vartaman', '1'),
                "PrishthSankhya": data.get('prishth_sankhya', '23'),
                "Date": data.get('date', ''),
                "qr_base64": qr_base64
            }
            html_rendered = render_template('receipt_template.html', data=formatted_data)

        supabase.table('receipts').update({
            'html_content': html_rendered,
            'form_data': formatted_data
        }).eq('id', receipt_id).execute()

        return {
            "status": "success",
            "receipt_id": receipt_id,
            "url_path": custom_url,
            "full_url": full_url,
            "message": "Receipt Updated Successfully!"
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

# Delete Existing Receipt
@app.route('/api/receipt/delete', methods=['POST'])
def api_receipt_delete():
    data = request.json or {}
    receipt_id = data.get('receipt_id')
    if not receipt_id:
        return {"status": "error", "message": "Receipt ID required"}, 400
    try:
        supabase.table('receipts').delete().eq('id', receipt_id).execute()
        return {"status": "success", "message": "Receipt Deleted Successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

@app.route('/api/receipts/list', methods=['GET'])
def api_receipts_list():
    user_id = request.args.get('user_id')
    try:
        if user_id and str(user_id) != "1":
            res = supabase.table('receipts').select('id, url_path, form_data, created_at').eq('user_id', user_id).order('id', desc=True).execute()
        else:
            res = supabase.table('receipts').select('id, url_path, form_data, created_at').order('id', desc=True).execute()
            
        receipts = []
        host_url = request.host_url.rstrip('/')
        for row in (res.data or []):
            name = "Receipt"
            if row.get('form_data') and isinstance(row['form_data'], dict):
                name = row['form_data'].get('Name') or name
            receipts.append({
                "id": row['id'],
                "url_path": row['url_path'],
                "full_url": f"{host_url}/{row['url_path']}",
                "display_name": name,
                "created_at": row.get('created_at', '')
            })
        return {"status": "success", "receipts": receipts}
    except Exception as e:
        return {"status": "success", "receipts": []}

# ================= ADMIN KEYS MANAGEMENT APIs =================

@app.route('/api/admin/keys/generate', methods=['POST'])
def api_admin_keys_generate():
    secret = request.args.get('secret') or (request.json.get('secret') if request.json else None)
    if secret != "super_admin_secret_123":
        return {"status": "error", "message": "Unauthorized"}, 401
        
    data = request.json or {}
    count = int(data.get('count', 1))
    initial_balance = int(data.get('initial_balance', 500))
    note = data.get('note', 'Generated via Admin App')
    
    generated_keys = []
    for _ in range(count):
        code = "RECIPT-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4)) + "-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        try:
            ins = supabase.table('license_keys').insert({
                'key_code': code,
                'status': 'Unused',
                'initial_balance': initial_balance,
                'user_note': note
            }).execute()
            if ins.data:
                generated_keys.append(ins.data[0])
        except Exception:
            pass
            
    return {"status": "success", "keys": generated_keys}

@app.route('/api/admin/keys/list', methods=['GET', 'POST'])
def api_admin_keys_list():
    secret = request.args.get('secret') or (request.json.get('secret') if request.json else None)
    if secret != "super_admin_secret_123":
        return {"status": "error", "message": "Unauthorized"}, 401
        
    try:
        res = supabase.table('license_keys').select('*').order('id', desc=True).execute()
        return {"status": "success", "keys": res.data or []}
    except Exception as e:
        return {"status": "success", "keys": []}

@app.route('/api/admin/keys/reset_device', methods=['POST'])
def api_admin_keys_reset_device():
    secret = request.args.get('secret') or (request.json.get('secret') if request.json else None)
    if secret != "super_admin_secret_123":
        return {"status": "error", "message": "Unauthorized"}, 401
        
    data = request.json or {}
    key_id = data.get('key_id')
    if not key_id:
        return {"status": "error", "message": "Key ID required"}, 400
        
    try:
        supabase.table('license_keys').update({'device_id': None, 'status': 'Unused'}).eq('id', key_id).execute()
        return {"status": "success", "message": "Device reset successfully!"}
    except Exception as e:
        return {"status": "error", "message": str(e)}, 500

# Public Receipt Viewer for QR codes / direct links
@app.route('/<path:url_path>')
def view_page(url_path):
    try:
        response = supabase.table('receipts').select('html_content').eq('url_path', url_path).execute()
        if response.data:
            html = response.data[0]['html_content']
            # Dynamically fix logo paths for ALL receipts (old & new)
            html = html.replace('../img/logo2_new1.png', '/static/download.png')
            html = html.replace('img/logo2_new1.png', '/static/download.png')
            html = re.sub(r'src=["\'][^"\']*logo2_new1[^"\']*["\']', 'src="/static/download.png"', html)
            return render_template_string(html)
        return render_template('offline.html'), 404
    except Exception:
        return render_template('offline.html'), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
