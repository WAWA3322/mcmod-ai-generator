import requests
import zipfile
import io
import sqlite3
import time
import re

# 配置：如需更高搜索限额，可填入 GitHub token（非必须）
GITHUB_TOKEN = ""  # 留空也可以，但会限速
HEADERS = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}

DB_PATH = "mcmod_data.db"

def create_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS training_data (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mc_version TEXT,
        mod_loader TEXT,
        category TEXT,
        prompt TEXT,
        code TEXT,
        file_path TEXT,
        repo_name TEXT
    )''')
    conn.commit()
    return conn

def search_github(query, max_pages=2):
    repos = []
    for page in range(1, max_pages+1):
        url = f"https://api.github.com/search/repositories?q={query}&per_page=50&page={page}"
        resp = requests.get(url, headers=HEADERS).json()
        repos.extend(resp.get("items", []))
        time.sleep(2)  # 避免限速
    return repos

def download_zip(repo_full_name):
    url = f"https://api.github.com/repos/{repo_full_name}/zipball/main"
    try:
        resp = requests.get(url, headers=HEADERS)
        return zipfile.ZipFile(io.BytesIO(resp.content))
    except:
        return None

def classify_java(code, file_path):
    """自动判断这个Java文件属于什么类别"""
    code_lower = code.lower()
    path_lower = file_path.lower()
    if 'extends sworditem' in code_lower or 'extends bowitem' in code_lower:
        return 'weapon'
    elif 'extends armoritem' in code_lower:
        return 'armor'
    elif 'extends pickaxeitem' in code_lower or 'extends axeitem' in code_lower:
        return 'tool'
    elif 'extends block ' in code_lower or 'extends baseblock' in code_lower:
        return 'block'
    elif 'extends mob' in code_lower or 'extends livingentity' in code_lower:
        return 'entity'
    elif 'enchantment' in path_lower:
        return 'enchantment'
    elif 'worldgen' in path_lower or 'feature' in path_lower:
        return 'worldgen'
    else:
        return 'other'

def extract_mc_version(file_path, readme_text=""):
    """从路径或readme尝试提取MC版本"""
    # 简单策略: 看路径中是否包含版本号
    match = re.search(r'(1\.\d+\.\d+|1\.\d+)', file_path)
    return match.group(1) if match else "unknown"

def extract_mod_loader(code):
    """从代码判断 Forge 还是 Fabric"""
    if 'net.minecraftforge' in code:
        return 'Forge'
    elif 'net.fabricmc' in code:
        return 'Fabric'
    else:
        return 'Unknown'

def generate_prompt(category, class_name, code):
    """从代码自动生成一句中文描述作为训练prompt"""
    abilities = []
    code_lower = code.lower()
    if 'lightning' in code_lower: abilities.append('召唤闪电')
    if 'fire' in code_lower: abilities.append('火焰')
    if 'explosion' in code_lower: abilities.append('爆炸')
    if 'teleport' in code_lower: abilities.append('传送')
    ability_str = "，可以" + "、".join(abilities) if abilities else ""
    return f"创建一个{category}：{class_name}{ability_str}"

def collect_all_data():
    conn = create_db()
    queries = [
        ("forge 1.20.1 sword extension:java", "1.20.1", "Forge"),
        ("forge 1.19.2 item extension:java", "1.19.2", "Forge"),
        ("fabric 1.20.1 tool extension:java", "1.20.1", "Fabric"),
        ("fabric 1.19.2 armor extension:java", "1.19.2", "Fabric"),
    ]
    for query, default_version, default_loader in queries:
        print(f"Searching: {query}")
        repos = search_github(query, max_pages=1)
        for repo in repos:
            repo_name = repo["full_name"]
            print(f"  Processing {repo_name}...")
            zipf = download_zip(repo_name)
            if not zipf:
                continue
            for file_info in zipf.filelist:
                if not file_info.filename.endswith('.java'):
                    continue
                code = zipf.read(file_info.filename).decode('utf-8', errors='ignore')
                category = classify_java(code, file_info.filename)
                mc_version = extract_mc_version(file_info.filename) or default_version
                loader = extract_mod_loader(code) or default_loader
                class_name = file_info.filename.split('/')[-1].replace('.java','')
                prompt = generate_prompt(category, class_name, code)
                conn.execute('''INSERT INTO training_data 
                    (mc_version, mod_loader, category, prompt, code, file_path, repo_name)
                    VALUES (?,?,?,?,?,?,?)''',
                    (mc_version, loader, category, prompt, code, file_info.filename, repo_name))
            conn.commit()
            print(f"    Done.")
    conn.close()
    print(f"✅ 数据库已保存到 {DB_PATH}")

if __name__ == "__main__":
    collect_all_data()
