#!/opt/venv/bin/python3
import re
import sys
import os
import logging
import argparse
import yaml
import requests

# 配置日志 - 确保qBittorrent能捕获
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - qbit_classifier - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/config/qbit_classifier.log'),  # 保存到qBittorrent配置目录
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def load_config(config_path):
    """加载YAML配置文件"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error(f"配置文件 {config_path} 不存在")
        sys.exit(1)
    except yaml.YAMLError as e:
        logger.error(f"配置文件解析错误: {str(e)}")
        sys.exit(1)

def create_directories(config):
    """创建必要的目录并检查权限"""
    base_dir = config['paths']['base_dir']
    dirs = {
        # 关键修改：把 'movies' 改成 'movie'，和 classify_torrent 返回的 category 一致
        'movie': os.path.join(base_dir, config['paths']['movies_dir']),  
        'tv': os.path.join(base_dir, config['paths']['tv_dir']),
        'other': os.path.join(base_dir, config['paths']['other_dir'])
    }
    
    for dir_type, dir_path in dirs.items():
        try:
            os.makedirs(dir_path, exist_ok=True)
            # 设置目录权限为775，确保读写权限
            os.chmod(dir_path, 0o775)
            logger.debug(f"目录已准备: {dir_path} (权限: {oct(os.stat(dir_path).st_mode)[-3:]})")
        except OSError as e:
            logger.error(f"创建目录 {dir_path} 失败: {str(e)}")
            sys.exit(1)
    
    return dirs

def login_qbittorrent(config):
    """登录qBittorrent并获取认证Cookie"""
    host = config['qbittorrent']['host']
    port = config['qbittorrent']['port']
    username = config['qbittorrent']['username']
    password = config['qbittorrent']['password']
    
    url = f"http://{host}:{port}/api/v2/auth/login"
    headers = {
        "User-Agent": "qbit-classifier/1.0",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    session = requests.Session()
    try:
        # 获取CSRF令牌
        session.get(url, headers=headers, timeout=10)
        csrf_token = session.cookies.get("XSRF-TOKEN", "")
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
        
        # 执行登录
        response = session.post(
            url,
            data={"username": username, "password": password},
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200 and response.text == "Ok.":
            logger.info("登录qBittorrent成功")
            return session.cookies
        else:
            logger.error(f"登录失败: 状态码={response.status_code}, 响应={response.text}")
            sys.exit(1)
            
    except requests.exceptions.RequestException as e:
        logger.error(f"登录请求异常: {str(e)}")
        sys.exit(1)

def set_torrent_properties(cookies, config, torrent_hash, target_path, category):
    """设置种子的存储路径、分类标签和自动管理属性"""
    host = config['qbittorrent']['host']
    port = config['qbittorrent']['port']
    base_url = f"http://{host}:{port}/api/v2/torrents"
    
    headers = {
        "User-Agent": "qbit-classifier/1.0",
        "X-CSRF-Token": cookies.get("XSRF-TOKEN", ""),
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    # 1. 设置存储路径
    path_response = requests.post(
        f"{base_url}/setLocation",
        data={"hashes": torrent_hash, "location": target_path},
        cookies=cookies,
        headers=headers,
        timeout=10
    )
    
    if path_response.status_code != 200:
        logger.error(f"设置存储路径失败，状态码: {path_response.status_code}")
        return False
    
    # 2. 设置分类标签（用于自动管理）
    category_response = requests.post(
        f"{base_url}/setCategory",
        data={"hashes": torrent_hash, "category": category},
        cookies=cookies,
        headers=headers,
        timeout=10
    )
    
    if category_response.status_code != 200:
        logger.error(f"设置分类标签失败，状态码: {category_response.status_code}")
        return False
    
    # 3. 启用自动管理（确保种子遵循分类设置）
    auto_manage_response = requests.post(
        f"{base_url}/setAutoManagement",
        data={"hashes": torrent_hash, "enable": "true"},
        cookies=cookies,
        headers=headers,
        timeout=10
    )
    
    if auto_manage_response.status_code != 200:
        logger.error(f"启用自动管理失败，状态码: {auto_manage_response.status_code}")
        return False
    
    return True

def classify_torrent(name, config):
    """根据英文命名规则分类种子"""
    name_lower = name.lower()
    rules = config['classification_rules']
    
    # 优先检查电视剧规则
    for pattern in rules['tv']:
        if re.search(pattern, name_lower):
            logger.debug(f"匹配电视剧模式: {pattern} 在 {name} 中")
            return "tv"
    
    # 然后检查电影规则
    for pattern in rules['movie']:
        if re.search(pattern, name_lower):
            logger.debug(f"匹配电影模式: {pattern} 在 {name} 中")
            return "movie"
    
    # 其他类型
    return "other"

def main():
    logger.info("===== 种子分类处理开始 =====")
    
    # 解析必要的命令行参数
    parser = argparse.ArgumentParser(description='qBittorrent英文种子自动分类工具')
    parser.add_argument('hash', help='种子哈希值')
    parser.add_argument('name', help='种子名称')
    parser.add_argument('path', help='当前存储路径')
    parser.add_argument('-c', '--config', help='配置文件路径', default='/scripts/config.yaml')
    args = parser.parse_args()
    
    # 提取参数
    torrent_hash = args.hash
    torrent_name = args.name
    current_path = args.path
    config_path = args.config
    
    logger.info(f"处理种子: {torrent_name} (哈希: {torrent_hash[:8]}...)")
    logger.info(f"当前路径: {current_path}")
    
    # 加载配置
    config = load_config(config_path)
    
    # 创建目录
    dirs = create_directories(config)
    
    # 确定分类
    category = classify_torrent(torrent_name, config)
    category_label = config['categories'][category]
    target_path = dirs[category]
    
    logger.info(f"分类结果: {category_label}, 目标路径: {target_path}")
    
    # 检查是否已在目标位置
    if os.path.abspath(current_path) == os.path.abspath(target_path):
        logger.info("种子已在目标目录，无需调整")
        sys.exit(0)
    
    # 登录并设置种子属性
    cookies = login_qbittorrent(config)
    success = set_torrent_properties(cookies, config, torrent_hash, target_path, category_label)
    
    # 输出结果
    if success:
        logger.info(f"种子成功分类为 [{category_label}] 并启用自动管理")
        sys.exit(0)
    else:
        logger.error("种子分类或属性设置失败")
        sys.exit(1)

if __name__ == "__main__":
    main()
