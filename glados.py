import requests
from curl_cffi import requests as cffi_requests
import datetime
import random
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 配置参数（请替换为你的实际信息）
PUSHPLUS_TOKEN = ""  # 从PushPlus官网获取
PROXY_CONFIG = None  # 海外服务器无需代理

# 账号配置（只保留你需要的账号，删除示例账号）
ACCOUNTS = [
    
     {
         "email": "",
         "cookie": "koa:xxxx"
     }
    # 如需添加多个账号，按格式继续添加
    
]

def translate_message(raw_message):
    """将API返回的英文消息转换为中文提示"""
    if raw_message == "Please Try Tomorrow":
        return "签到失败，请明天再试 🤖"
    elif "Checkin! Got" in raw_message:
        points = raw_message.split("Got ")[1].split(" Points")[0]
        return f"签到成功，获得{points}积分 🎉"
    elif raw_message == "Checkin Repeats! Please Try Tomorrow":
        return "重复签到，请明天再试 🔁"
    elif "please checkin via" in raw_message:
        return "签到失败，服务器要求在 glados.cloud 签到，请检查脚本更新或 Cookie ⚠️"
    else:
        return f"未知的签到结果: {raw_message} ❓"

def sanitize_header_value(value):
    """确保请求头内容仅包含Latin-1可编码字符，避免编码错误"""
    if isinstance(value, str):
        try:
            value.encode('latin-1')
            return value
        except UnicodeEncodeError:
            return value.encode('latin-1', 'replace').decode('latin-1')
    return value

def generate_headers(cookie):
    """生成随机User-Agent的请求头，并清理编码问题"""
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Safari/605.1.15",
        "Mozilla/5.0 (Linux; Android 13; SM-S901B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1 Edg/144.0.0.0"
    ]
    
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Content-Type": "application/json;charset=UTF-8",
        "Cookie": cookie,
        "Origin": "https://glados.cloud",
        "Sec-Ch-Ua": '"Not-A.Brand";v="99", "Chromium";v="124"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "User-Agent": random.choice(user_agents)
    }
    
    return {k: sanitize_header_value(v) for k, v in headers.items()}

def format_days(days_str):
    """格式化剩余天数显示（去除多余小数位）"""
    days = float(days_str)
    if days.is_integer():
        return str(int(days))
    return f"{days:.8f}".rstrip('0').rstrip('.')

def format_decimal(value_str, keep=8):
    """通用数字字符串格式化（去除多余小数位）"""
    try:
        value = float(value_str)
        if value.is_integer():
            return str(int(value))
        return f"{value:.{keep}f}".rstrip('0').rstrip('.')
    except Exception:
        return value_str

def send_notification(sign_messages, status_messages, token):
    """通过PushPlus推送签到结果到微信"""
    if not token:
        print("未配置PushPlus Token，跳过推送")
        return
    
    url = "https://www.pushplus.plus/send"
    beijing_time = datetime.datetime.now(datetime.UTC).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
    current_time = beijing_time.strftime("%Y-%m-%d %H:%M")
    
    # 构建推送内容
    sign_text = "🔔 签到结果:\n" + "\n".join(sign_messages)
    status_text = "\n⏳ 账号状态:\n" + "\n".join(status_messages)
    content = f"🕒 执行时间: {current_time}\n\n{sign_text}\n{status_text}\n\n✅ 任务完成"

    # 定义要发送的数据（修正笔误：将data改为正确的变量名）
    push_data = {
        "token": token,
        "title": "GLaDOS自动签到通知",
        "content": content,
        "template": "txt"
    }

    try:
        # 这里将之前错误的`data`改为`push_data`
        response = requests.post(url, json=push_data, timeout=30)
        response.raise_for_status()
        result = response.json()
        if result.get("code") == 200:
            print("PushPlus推送成功")
        else:
            print(f"推送失败: {result.get('msg', '未知错误')}")
    except requests.RequestException as e:
        print(f"推送请求失败: {str(e)}")

def create_retry_session(retries=3, backoff_factor=1):
    """创建带重试机制的会话（使用curl_cffi模拟浏览器）"""
    # curl_cffi 的 Session 默认不支持 requests.adapters 的 mount 方式
    # 但它内置了模拟浏览器功能，impersonate="chrome" 即可
    session = cffi_requests.Session(impersonate="chrome124")
    return session

def fetch_points(cookie, proxy):
    """查询账户积分总数与当日变动"""
    url = "https://glados.cloud/api/user/points"
    headers = generate_headers(cookie)
    session = create_retry_session()
    try:
        response = session.get(
            url,
            headers=headers,
            proxies=proxy,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        code = data.get("code", -1)
        if code != 0:
            return {"ok": False, "message": f"积分查询失败: code={code} ❌"}
        total_points = format_decimal(data.get("points", "0"))
        history = data.get("history", [])
        beijing_time = datetime.datetime.now(datetime.UTC).astimezone(datetime.timezone(datetime.timedelta(hours=8)))
        today_str = beijing_time.strftime("%Y-%m-%d")
        today_change = None
        for item in history:
            business = item.get("business", "")
            if business.endswith(today_str):
                today_change = format_decimal(item.get("change", "0"), keep=8)
                break
        msg = f"积分 {total_points}"
        if today_change is not None:
            msg += f"，今日 +{today_change}"
        return {"ok": True, "message": msg, "points": total_points, "today_change": today_change}
    except Exception as e:
        # curl_cffi 的异常可能与 requests 不同，捕获通用 Exception
        response = getattr(e, 'response', None)
        response_text = response.text[:200] if response is not None else '无响应'
        return {"ok": False, "message": f"积分请求失败: {str(e)}，响应片段: {response_text} ❌"}

def check_account_status(email, cookie, proxy):
    """查询账号剩余可用天数"""
    url = "https://glados.cloud/api/user/status"
    headers = generate_headers(cookie)
    session = create_retry_session()
    
    try:
        response = session.get(
            url,
            headers=headers,
            proxies=proxy,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        left_days = format_days(data['data']['leftDays'])
        return f"{email}: 剩余 {left_days} 天 🗓️"
    except Exception as e:
        response = getattr(e, 'response', None)
        response_text = response.text[:200] if response is not None else '无响应'
        return f"{email}: 状态查询失败 - {str(e)}，响应片段: {response_text} ❌"

def sign(email, cookie, proxy):
    """执行账号签到操作"""
    # 签到接口强制要求使用 glados.cloud
    url = "https://glados.cloud/api/user/checkin"
    # 针对签到接口，Origin 必须匹配新域名
    headers = generate_headers(cookie)
    headers["Origin"] = "https://glados.cloud"
    
    data = {"token": "glados.cloud"}
    session = create_retry_session()
    
    try:
        response = session.post(
            url,
            headers=headers,
            json=data,
            proxies=proxy,
            timeout=30
        )
        response.raise_for_status()
        response_data = response.json()
        raw_message = response_data.get("message", "无返回信息")
        return translate_message(raw_message)
    except Exception as e:
        response = getattr(e, 'response', None)
        status_code = response.status_code if response is not None else 'Unknown'
        response_text = response.text[:200] if response is not None else '无响应'
        return f"签到请求失败: 状态码 {status_code}, {str(e)}，响应片段: {response_text} ❌"

def multi_account_sign():
    """处理多个账号的签到流程"""
    if not ACCOUNTS:
        print("未配置任何账号，请检查ACCOUNTS列表")
        return
    
    sign_messages = []
    status_messages = []
    points_messages = []

    for idx, account in enumerate(ACCOUNTS, 1):
        email = account.get("email", f"账号{idx}")
        cookie = account.get("cookie", "")

        if not cookie:
            sign_messages.append(f"{email}: 未配置Cookie，跳过签到 ❌")
            status_messages.append(f"{email}: 无Cookie，无法查询状态 ❌")
            points_messages.append(f"{email}: 无Cookie，无法查询积分 ❌")
            continue

        print(f"\n开始处理账号: {email}")
        sign_result = sign(email, cookie, PROXY_CONFIG)
        sign_messages.append(f"{email}: {sign_result}")

        status_result = check_account_status(email, cookie, PROXY_CONFIG)
        status_messages.append(status_result)

        points_result = fetch_points(cookie, PROXY_CONFIG)
        points_messages.append(f"{email}: {points_result['message']}")

        time.sleep(random.randint(3, 8))

    # 将积分信息追加到状态区块一并展示
    merged_status = status_messages + [f"{msg}" for msg in points_messages]
    send_notification(sign_messages, merged_status, PUSHPLUS_TOKEN)

if __name__ == "__main__":
    print("===== GLaDOS自动签到脚本启动 =====")
    multi_account_sign()
    print("===== 脚本执行结束 =====")
