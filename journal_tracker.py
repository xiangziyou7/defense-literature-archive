#!/usr/bin/env python3
"""
兵器领域文献全自动监控系统
监控13个核心期刊，两大研究方向：引信系统可靠性、智能侵彻
"""

import sys
import os
import json
import time
import argparse
import subprocess
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

# 路径配置
SCRIPT_DIR = Path(__file__).parent.absolute()
WORKSPACE_DIR = SCRIPT_DIR.parent.parent
PAPERS_DIR = WORKSPACE_DIR / "papers" / "journal-tracker"
REPORTS_DIR = SCRIPT_DIR / "reports"
ARCHIVE_DIR = SCRIPT_DIR / "archive"
DATA_DIR = SCRIPT_DIR / "data"

# 配置文件
JOURNALS_FILE = SCRIPT_DIR / "journals.json"
KEYWORDS_FILE = SCRIPT_DIR / "keywords.json"
SEEN_FILE = SCRIPT_DIR / "seen_papers.json"

# 百度学术 API
BAIDU_API_KEY = os.environ.get(
    "BAIDU_API_KEY", 
    "bce-v3/ALTAKSP-uhAi4YRqgaSohyBPz7xW6/4aab978b08a7b8c6018bf822d74e0d61b63b688e"
)
BAIDU_API_URL = "https://qianfan.baidubce.com/v2/tools/baidu_scholar/search"

# GitHub 配置
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "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")
GITHUB_REPO = os.environ.get("GITHUB_REPO", "xiangziyou7/defense-literature-archive")


def load_json(filepath: Path) -> dict:
    """加载 JSON 文件"""
    if not filepath.exists():
        return {}
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_json(filepath: Path, data: dict):
    """保存 JSON 文件"""
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def search_baidu_scholar(query: str, page: int = 0, enable_abstract: bool = True) -> dict:
    """搜索百度学术"""
    try:
        headers = {
            "Authorization": f"Bearer {BAIDU_API_KEY}",
            "X-Appbuilder-From": "openclaw"
        }
        params = {
            "wd": query,
            "pageNum": page,
            "enable_abstract": str(enable_abstract).lower()
        }
        
        resp = requests.get(BAIDU_API_URL, headers=headers, params=params, timeout=30)
        result = resp.json()
        
        if result.get("code") == "0":
            count = len(result.get("data", []))
            print(f"    API 返回 {count} 条结果", flush=True)
        else:
            print(f"    API 错误: {result.get('message', 'unknown')}", flush=True)
        
        return result
    except Exception as e:
        print(f"[ERROR] 百度学术搜索失败: {e}", flush=True)
        return {"error": str(e)}


def classify_paper(title: str, abstract: str, keywords_config: dict) -> Tuple[float, str, str, List[str]]:
    """
    分类文献到两大方向及子类别
    返回: (相关性分数, 主方向, 子类别, 匹配关键词列表)
    """
    text = f"{title} {abstract}".lower()
    matched_keywords = []
    
    exclude_keywords = keywords_config.get("exclude_keywords", [])
    for excl in exclude_keywords:
        if excl.lower() in text:
            return 0.0, "排除", "", []
    
    best_score = 0.0
    best_direction = ""
    best_subcategory = ""
    
    core_directions = keywords_config.get("core_directions", {})
    
    for direction_id, direction_config in core_directions.items():
        direction_name = direction_config.get("name", direction_id)
        subcategories = direction_config.get("subcategories", {})
        
        for subcat_id, subcat_config in subcategories.items():
            subcat_name = subcat_config.get("name", subcat_id)
            keywords = subcat_config.get("keywords", [])
            
            subcat_score = 0.0
            subcat_matched = []
            
            for kw in keywords:
                if kw.lower() in text:
                    # 中英文关键词权重
                    weight = 1.5 if any('\u4e00' <= c <= '\u9fff' for c in kw) else 1.0
                    subcat_score += weight
                    subcat_matched.append(kw)
            
            if subcat_score > best_score:
                best_score = subcat_score
                best_direction = direction_name
                best_subcategory = subcat_name
                matched_keywords = subcat_matched
    
    # 标准化分数
    if best_score > 0:
        best_score = min(best_score / 3.0, 1.0)
    
    return best_score, best_direction, best_subcategory, matched_keywords


# 时间过滤配置
MAX_PAPER_AGE_YEARS = 3


def is_paper_recent(year_str: str) -> bool:
    """检查论文发表年份是否在近3年内"""
    if not year_str:
        return True  # 没有年份信息则保留
    
    try:
        year = int(year_str)
        current_year = datetime.now().year
        return year >= (current_year - MAX_PAPER_AGE_YEARS)
    except:
        return True  # 解析失败则保留
    """检查文献是否已处理"""
    return doi in seen_data.get("papers", {})


def mark_paper_seen(doi: str, paper_info: dict, seen_data: dict):
    """标记文献为已处理"""
    seen_data["papers"][doi] = paper_info
    seen_data["last_scan"] = datetime.now().isoformat()
    
    if "stats" not in seen_data:
        seen_data["stats"] = {"total_scanned": 0, "total_relevant": 0, "total_downloaded": 0}
    
    seen_data["stats"]["total_scanned"] += 1
    if paper_info.get("relevance", 0) >= 0.25:
        seen_data["stats"]["total_relevant"] += 1
    if paper_info.get("downloaded", False):
        seen_data["stats"]["total_downloaded"] += 1


def download_paper(doi: str, title: str) -> bool:
    """下载论文 PDF"""
    PAPERS_DIR.mkdir(parents=True, exist_ok=True)
    
    download_script = WORKSPACE_DIR / "skills" / "paper-tools" / "paper_download.py"
    if not download_script.exists():
        print(f"[WARN] 下载脚本不存在: {download_script}")
        return False
    
    try:
        result = subprocess.run(
            ["python3", str(download_script), doi, title],
            capture_output=True,
            text=True,
            timeout=120
        )
        return result.returncode == 0
    except Exception as e:
        print(f"[ERROR] 下载失败: {e}")
        return False


def scan_journal(journal: dict, keywords_config: dict, seen_data: dict, config: dict) -> List[dict]:
    """扫描单个期刊"""
    journal_name = journal["name"]
    search_terms = journal.get("search_terms", [journal_name])
    papers_per_journal = config.get("papers_per_journal", 30)
    
    print(f"\n{'='*60}")
    print(f"扫描期刊: {journal_name}")
    print(f"{'='*60}")
    
    new_papers = []
    
    for term in search_terms:
        print(f"\n搜索: {term}")
        
        result = search_baidu_scholar(term, page=0, enable_abstract=True)
        
        if "error" in result:
            print(f"[ERROR] 搜索失败: {result['error']}")
            continue
        
        papers = result.get("data", [])
        if not papers:
            print("未找到文献")
            continue
        
        print(f"找到 {len(papers)} 篇文献")
        
        for paper in papers[:papers_per_journal]:
            title = paper.get("title", "").replace("<em>", "").replace("</em>", "")
            doi = paper.get("doi", "") or paper.get("DOI", "") or paper.get("url", "")
            abstract = paper.get("abstract", "")
            year = paper.get("year", "")
            
            if not doi:
                continue
            
            # 时间过滤：仅保留近3年文献
            if not is_paper_recent(year):
                print(f"  [跳过] {title[:50]}... (发表年份: {year}, 超过{MAX_PAPER_AGE_YEARS}年)")
                continue
            
            if is_paper_seen(doi, seen_data):
                continue
            
            # 分类
            relevance, direction, subcategory, matched_kw = classify_paper(title, abstract, keywords_config)
            threshold = keywords_config.get("relevance_threshold", 0.25)
            
            if relevance < threshold:
                print(f"  [跳过] {title[:50]}... (相关性: {relevance:.2f})")
                mark_paper_seen(doi, {
                    "title": title,
                    "journal": journal_name,
                    "relevance": relevance,
                    "direction": direction,
                    "downloaded": False,
                    "seen_at": datetime.now().isoformat()
                }, seen_data)
                continue
            
            print(f"  [✓] {title[:50]}...")
            print(f"       方向: {direction} | 子类: {subcategory}")
            print(f"       相关性: {relevance:.2f} | 关键词: {', '.join(matched_kw[:3])}")
            
            paper_info = {
                "title": title,
                "doi": doi,
                "abstract": abstract,
                "journal": journal_name,
                "relevance": relevance,
                "direction": direction,
                "subcategory": subcategory,
                "matched_keywords": matched_kw,
                "authors": paper.get("authors", []),
                "year": paper.get("year", ""),
                "source": paper.get("source", ""),
                "url": paper.get("url", ""),
                "seen_at": datetime.now().isoformat()
            }
            
            new_papers.append(paper_info)
    
    return new_papers


def scan_all_journals():
    """扫描所有期刊"""
    print("\n" + "="*60)
    print("兵器领域文献全自动监控系统 - 开始扫描")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    journals_config = load_json(JOURNALS_FILE)
    keywords_config = load_json(KEYWORDS_FILE)
    seen_data = load_json(SEEN_FILE)
    
    if not journals_config or not keywords_config:
        print("[ERROR] 配置文件加载失败")
        return
    
    journals = journals_config.get("journals", [])
    scan_config = journals_config.get("scan_config", {})
    
    if "stats" not in seen_data:
        seen_data["stats"] = {"total_scanned": 0, "total_relevant": 0, "total_downloaded": 0}
    
    all_new_papers = []
    journals_sorted = sorted(journals, key=lambda x: x.get("priority", 999))
    
    for journal in journals_sorted:
        try:
            new_papers = scan_journal(journal, keywords_config, seen_data, scan_config)
            all_new_papers.extend(new_papers)
            time.sleep(2)
        except Exception as e:
            print(f"[ERROR] 扫描期刊 {journal['name']} 失败: {e}")
            continue
    
    # 自动下载 OA 文献
    if scan_config.get("download_oa", True) and all_new_papers:
        print(f"\n{'='*60}")
        print(f"下载高相关性文献 (共 {len(all_new_papers)} 篇)")
        print("="*60)
        
        for paper in all_new_papers:
            if paper["relevance"] >= 0.4:
                print(f"\n下载: {paper['title'][:50]}...")
                downloaded = download_paper(paper["doi"], paper["title"])
                paper["downloaded"] = downloaded
            else:
                paper["downloaded"] = False
            
            mark_paper_seen(paper["doi"], paper, seen_data)
    
    save_json(SEEN_FILE, seen_data)
    
    # 保存当日数据
    if all_new_papers:
        save_daily_data(all_new_papers)
    
    # 输出摘要
    print(f"\n{'='*60}")
    print("扫描完成")
    print("="*60)
    print(f"总扫描文献: {seen_data['stats']['total_scanned']}")
    print(f"高相关文献: {seen_data['stats']['total_relevant']}")
    print(f"成功下载: {seen_data['stats']['total_downloaded']}")
    print(f"本次发现: {len(all_new_papers)} 篇新文献")
    
    # 分类统计
    if all_new_papers:
        print(f"\n分类统计:")
        direction_counts = {}
        for p in all_new_papers:
            d = p.get("direction", "未分类")
            direction_counts[d] = direction_counts.get(d, 0) + 1
        for d, c in sorted(direction_counts.items(), key=lambda x: -x[1]):
            print(f"  - {d}: {c} 篇")
    
    return all_new_papers


def save_daily_data(papers: List[dict]):
    """保存当日数据"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    data_file = DATA_DIR / f"{today}.json"
    
    # 按方向和子类别组织
    organized = {
        "date": today,
        "total": len(papers),
        "directions": {}
    }
    
    for paper in papers:
        direction = paper.get("direction", "未分类")
        subcategory = paper.get("subcategory", "其他")
        
        if direction not in organized["directions"]:
            organized["directions"][direction] = {}
        if subcategory not in organized["directions"][direction]:
            organized["directions"][direction][subcategory] = []
        
        organized["directions"][direction][subcategory].append(paper)
    
    organized["statistics"] = {
        "by_direction": {d: sum(len(s) for s in subs.values()) for d, subs in organized["directions"].items()},
        "by_journal": {},
        "by_subcategory": {}
    }
    
    for paper in papers:
        j = paper.get("journal", "未知")
        organized["statistics"]["by_journal"][j] = organized["statistics"]["by_journal"].get(j, 0) + 1
        
        s = paper.get("subcategory", "其他")
        organized["statistics"]["by_subcategory"][s] = organized["statistics"]["by_subcategory"].get(s, 0) + 1
    
    save_json(data_file, organized)
    print(f"\n[INFO] 数据已保存: {data_file}")
    
    # 追加到归档
    archive_file = ARCHIVE_DIR / "all_papers.json"
    archive = load_json(archive_file)
    if not archive:
        archive = {"papers": []}
    archive["papers"].extend(papers)
    archive["last_updated"] = datetime.now().isoformat()
    save_json(archive_file, archive)


def generate_daily_report():
    """生成每日结构化日报"""
    print("\n" + "="*60)
    print("生成每日日报")
    print("="*60)
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    
    today = datetime.now().strftime("%Y-%m-%d")
    data_file = DATA_DIR / f"{today}.json"
    
    if not data_file.exists():
        print("[WARN] 当日无数据，跳过日报生成")
        return
    
    data = load_json(data_file)
    
    report_lines = [
        f"# 兵器领域文献日报",
        f"",
        f"**日期**: {today}",
        f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"",
        "---",
        "",
        "## 📊 今日统计",
        "",
        f"- **文献总量**: {data.get('total', 0)} 篇",
        ""
    ]
    
    # 期刊分布
    by_journal = data.get("statistics", {}).get("by_journal", {})
    if by_journal:
        report_lines.append("### 期刊分布")
        report_lines.append("")
        report_lines.append("| 期刊 | 数量 |")
        report_lines.append("|------|------|")
        for j, c in sorted(by_journal.items(), key=lambda x: -x[1]):
            report_lines.append(f"| {j} | {c} |")
        report_lines.append("")
    
    # 方向统计
    by_direction = data.get("statistics", {}).get("by_direction", {})
    if by_direction:
        report_lines.append("### 方向统计")
        report_lines.append("")
        for d, c in sorted(by_direction.items(), key=lambda x: -x[1]):
            report_lines.append(f"- **{d}**: {c} 篇")
        report_lines.append("")
    
    # 子类别统计
    by_subcategory = data.get("statistics", {}).get("by_subcategory", {})
    if by_subcategory:
        report_lines.append("### 子类别统计")
        report_lines.append("")
        for s, c in sorted(by_subcategory.items(), key=lambda x: -x[1])[:10]:
            report_lines.append(f"- {s}: {c} 篇")
        report_lines.append("")
    
    # 核心文献摘要
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## 📝 核心文献摘要")
    report_lines.append("")
    
    directions = data.get("directions", {})
    
    for direction_name in ["引信系统可靠性", "智能侵彻"]:
        if direction_name in directions:
            report_lines.append(f"### {direction_name}")
            report_lines.append("")
            
            for subcat, papers in directions[direction_name].items():
                report_lines.append(f"#### {subcat}")
                report_lines.append("")
                
                for paper in papers[:3]:  # 每个子类最多3篇
                    report_lines.append(f"**{paper['title']}**")
                    report_lines.append(f"")
                    report_lines.append(f"- **期刊**: {paper['journal']}")
                    report_lines.append(f"- **DOI**: [{paper['doi']}](https://doi.org/{paper['doi']})")
                    report_lines.append(f"- **相关性**: {paper['relevance']:.2f}")
                    if paper.get('abstract'):
                        abstract_short = paper['abstract'][:200] + "..." if len(paper['abstract']) > 200 else paper['abstract']
                        report_lines.append(f"- **摘要**: {abstract_short}")
                    report_lines.append("")
            
            report_lines.append("")
    
    # 领域热点
    report_lines.append("---")
    report_lines.append("")
    report_lines.append("## 🔥 领域热点")
    report_lines.append("")
    
    # 找出高相关性文献
    all_papers = []
    for d, subs in directions.items():
        for s, papers in subs.items():
            all_papers.extend(papers)
    
    top_papers = sorted(all_papers, key=lambda x: x.get("relevance", 0), reverse=True)[:5]
    
    for i, paper in enumerate(top_papers, 1):
        report_lines.append(f"{i}. **{paper['title']}**")
        report_lines.append(f"   - {paper['direction']} / {paper['subcategory']}")
        report_lines.append(f"   - 相关性: {paper['relevance']:.2f}")
        report_lines.append("")
    
    # 保存报告
    report_file = REPORTS_DIR / f"{today}.md"
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("\n".join(report_lines))
    
    print(f"[OK] 日报已生成: {report_file}")
    
    return report_file


def sync_to_github():
    """同步到 GitHub Pages 私有仓库"""
    print("\n" + "="*60)
    print("同步到 GitHub")
    print("="*60)
    
    archive_dir = ARCHIVE_DIR
    
    if not (archive_dir / "all_papers.json").exists():
        print("[WARN] 无数据需要同步")
        return
    
    # 创建同步目录结构
    sync_dir = SCRIPT_DIR / "sync_temp"
    sync_dir.mkdir(parents=True, exist_ok=True)
    
    # 复制数据文件
    import shutil
    
    data_sync = sync_dir / "data"
    data_sync.mkdir(parents=True, exist_ok=True)
    
    if DATA_DIR.exists():
        for f in DATA_DIR.glob("*.json"):
            shutil.copy(f, data_sync / f.name)
    
    reports_sync = sync_dir / "reports"
    reports_sync.mkdir(parents=True, exist_ok=True)
    
    if REPORTS_DIR.exists():
        for f in REPORTS_DIR.glob("*.md"):
            shutil.copy(f, reports_sync / f.name)
    
    if (archive_dir / "all_papers.json").exists():
        shutil.copy(archive_dir / "all_papers.json", sync_dir / "all_papers.json")
    
    # Git 操作
    try:
        os.chdir(sync_dir)
        
        # 初始化 git
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "openclaw@local"], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "OpenClaw"], check=True, capture_output=True)
        
        # 添加远程仓库
        remote_url = f"https://{GITHUB_TOKEN}@github.com/{GITHUB_REPO}.git"
        subprocess.run(["git", "remote", "add", "origin", remote_url], capture_output=True)
        
        # 拉取最新
        subprocess.run(["git", "pull", "origin", "main", "--allow-unrelated-histories"], capture_output=True)
        
        # 添加并提交
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Auto sync: {datetime.now().strftime('%Y-%m-%d %H:%M')}"], capture_output=True)
        
        # 推送
        result = subprocess.run(["git", "push", "-u", "origin", "main", "--force"], capture_output=True)
        
        if result.returncode == 0:
            print("[OK] 同步成功")
        else:
            print(f"[WARN] 同步可能失败: {result.stderr.decode()}")
        
    except Exception as e:
        print(f"[ERROR] 同步失败: {e}")
    finally:
        os.chdir(SCRIPT_DIR)


def generate_search_page():
    """生成静态检索页面"""
    print("\n" + "="*60)
    print("生成检索页面")
    print("="*60)
    
    archive_file = ARCHIVE_DIR / "all_papers.json"
    if not archive_file.exists():
        print("[WARN] 无数据，跳过检索页面生成")
        return
    
    archive = load_json(archive_file)
    papers = archive.get("papers", [])
    
    # 生成 HTML 检索页面
    papers_json = json.dumps(papers, ensure_ascii=False)
    total_papers = len(papers)
    last_updated = archive.get('last_updated', '未知')
    
    html = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>兵器领域文献检索系统</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; background: #f5f5f5; }
        h1 { color: #333; }
        .search-box { background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .search-box input, .search-box select { padding: 10px; margin: 5px; border: 1px solid #ddd; border-radius: 4px; }
        .search-box input[type="text"] { width: 300px; }
        .stats { background: #e3f2fd; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
        .paper-list { background: white; border-radius: 8px; overflow: hidden; }
        .paper-item { padding: 15px; border-bottom: 1px solid #eee; }
        .paper-item:hover { background: #f9f9f9; }
        .paper-title { font-weight: bold; color: #1976d2; }
        .paper-meta { font-size: 0.9em; color: #666; margin-top: 5px; }
        .tag { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 0.8em; margin-right: 5px; }
        .tag-direction { background: #e8f5e9; color: #2e7d32; }
        .tag-subcategory { background: #fff3e0; color: #e65100; }
    </style>
</head>
<body>
    <h1>🔍 兵器领域文献检索系统</h1>
    <div class="stats"><strong>文献总数:</strong> ''' + str(total_papers) + ''' 篇 | <strong>最后更新:</strong> ''' + last_updated + '''</div>
    <div class="search-box">
        <input type="text" id="searchInput" placeholder="输入关键词搜索...">
        <select id="directionFilter">
            <option value="">全部方向</option>
            <option value="引信系统可靠性">引信系统可靠性</option>
            <option value="智能侵彻">智能侵彻</option>
        </select>
        <select id="journalFilter"><option value="">全部期刊</option></select>
        <button onclick="search()">搜索</button>
    </div>
    <div class="paper-list" id="paperList"></div>
    <script>
        const papers = ''' + papers_json + ''';
        const journals = [...new Set(papers.map(p => p.journal))];
        const journalFilter = document.getElementById('journalFilter');
        journals.forEach(j => { const opt = document.createElement('option'); opt.value = j; opt.textContent = j; journalFilter.appendChild(opt); });
        function search() {
            const keyword = document.getElementById('searchInput').value.toLowerCase();
            const direction = document.getElementById('directionFilter').value;
            const journal = document.getElementById('journalFilter').value;
            let filtered = papers.filter(p => {
                const matchKeyword = !keyword || p.title.toLowerCase().includes(keyword) || (p.abstract && p.abstract.toLowerCase().includes(keyword));
                const matchDirection = !direction || p.direction === direction;
                const matchJournal = !journal || p.journal === journal;
                return matchKeyword && matchDirection && matchJournal;
            });
            renderPapers(filtered);
        }
        function renderPapers(papers) {
            const list = document.getElementById('paperList');
            list.innerHTML = papers.slice(0, 100).map(p => '<div class="paper-item"><div class="paper-title">' + p.title + '</div><div class="paper-meta"><span class="tag tag-direction">' + (p.direction || '未分类') + '</span> <span class="tag tag-subcategory">' + (p.subcategory || '其他') + '</span> | ' + p.journal + ' | 相关性: ' + (p.relevance || 0).toFixed(2) + '</div><div class="paper-meta">DOI: <a href="https://doi.org/' + p.doi + '" target="_blank">' + p.doi + '</a></div></div>').join('');
        }
        renderPapers(papers);
    </script>
</body>
</html>'''
    
    search_page = SCRIPT_DIR / "search" / "index.html"
    search_page.parent.mkdir(parents=True, exist_ok=True)
    
    with open(search_page, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"[OK] 检索页面已生成: {search_page}")


def show_status():
    """显示系统状态"""
    print("\n" + "="*60)
    print("兵器领域文献监控系统 - 系统状态")
    print("="*60)
    
    journals_config = load_json(JOURNALS_FILE)
    seen_data = load_json(SEEN_FILE)
    keywords_config = load_json(KEYWORDS_FILE)
    
    journals = journals_config.get("journals", [])
    print(f"\n监控期刊: {len(journals)} 个")
    for j in journals:
        print(f"  - {j['name']}")
    
    scan_config = journals_config.get("scan_config", {})
    print(f"\n扫描间隔: 每 {scan_config.get('interval_hours', 6)} 小时")
    
    stats = seen_data.get("stats", {})
    print(f"\n统计信息:")
    print(f"  总扫描: {stats.get('total_scanned', 0)} 篇")
    print(f"  高相关: {stats.get('total_relevant', 0)} 篇")
    print(f"  已下载: {stats.get('total_downloaded', 0)} 篇")
    
    # 方向信息
    directions = keywords_config.get("core_directions", {})
    print(f"\n研究方向:")
    for d_id, d_config in directions.items():
        subcats = d_config.get("subcategories", {})
        print(f"  - {d_config['name']}: {len(subcats)} 个子类别")


def main():
    parser = argparse.ArgumentParser(description="兵器领域文献全自动监控系统")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    subparsers.add_parser("scan", help="扫描所有期刊")
    subparsers.add_parser("status", help="显示系统状态")
    subparsers.add_parser("report", help="生成每日日报")
    subparsers.add_parser("sync", help="同步到GitHub")
    subparsers.add_parser("search", help="生成检索页面")
    
    # 全流程
    subparsers.add_parser("run", help="完整运行流程(扫描+报告+同步)")
    
    args = parser.parse_args()
    
    if args.command == "scan":
        scan_all_journals()
    elif args.command == "status":
        show_status()
    elif args.command == "report":
        generate_daily_report()
    elif args.command == "sync":
        sync_to_github()
    elif args.command == "search":
        generate_search_page()
    elif args.command == "run":
        scan_all_journals()
        generate_daily_report()
        generate_search_page()
        sync_to_github()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
