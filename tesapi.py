import requests
import json

# ============ 配置区 ============
API_KEY = "sk-e8Q3vFw6DLxdUMc0ZJsxy8Bbd4foFapUNSje1bUxlNaOz0Uw"
API_URL = "https://api.moonshot.cn/v1/chat/completions"

# ============ 测试 Kimi k2.6 ============
def test_kimi():
    print("🚀 测试 Kimi k2.6 模型 (OpenAI 格式)\n")
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    # ✅ 修复：temperature 改为 1
    payload = {
        "model": "kimi-k2.6",
        "messages": [
            {"role": "user", "content": "说'OK'就表示你活着"}
        ],
        "max_tokens": 50,
        "temperature": 1.0,  # ← 改成 1.0
    }
    
    print(f"📤 请求体: {json.dumps(payload, ensure_ascii=False)}")
    print()
    
    try:
        response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
        
        print(f"📊 HTTP 状态码: {response.status_code}")
        print()
        
        if response.status_code == 200:
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"✅ 成功！回复：{content}")
            print(f"\n完整返回: {json.dumps(data, indent=2, ensure_ascii=False)}")
        else:
            print(f"❌ 失败")
            print(f"响应内容: {response.text[:500]}")
            
    except Exception as e:
        print(f"❌ 异常: {e}")

# ============ 测试多个模型，找出哪些可用 ============
def test_models():
    """测试不同的模型名和 temperature 组合"""
    
    # 不同模型可能对 temperature 有不同要求
    test_cases = [
        {"model": "kimi-k2.6", "temperature": 1.0},
        {"model": "kimi-k2.6", "temperature": 0.7},  # 已知会失败，留着看错误信息
        {"model": "moonshot-v1-8k", "temperature": 0.7},
        {"model": "moonshot-v1-32k", "temperature": 0.7},
    ]
    
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    
    print("🚀 批量测试模型...\n")
    
    for case in test_cases:
        print(f"{'='*50}")
        print(f"📡 模型: {case['model']}, temperature: {case['temperature']}")
        print('='*50)
        
        payload = {
            "model": case["model"],
            "messages": [{"role": "user", "content": "说'OK'"}],
            "max_tokens": 20,
            "temperature": case["temperature"]
        }
        
        try:
            response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
            print(f"状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"✅ 可用！回复: {content}")
            else:
                error = response.json().get("error", {}).get("message", response.text[:100])
                print(f"❌ 不可用: {error}")
        except Exception as e:
            print(f"❌ 异常: {e}")
        
        print()

# ============ 主程序 ============
if __name__ == "__main__":
    print("="*50)
    print("🔑 API Key:", API_KEY[:12] + "..." + API_KEY[-6:])
    print("📍 API 地址:", API_URL)
    print("="*50)
    print()
    
    # 先单独测 Kimi
    test_kimi()
    
    print("\n" + "="*50)
    print("是否继续批量测试其他模型？")
    print("="*50)
    
    # 取消注释下面这行可以批量测试
    # test_models()