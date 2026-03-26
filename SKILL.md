---
name: journal-tracker
description: 兵器领域期刊长期监控系统。定时扫描10个核心期刊，自动下载OA文献，智能去重和相关性过滤。
---

# 兵器领域前沿追踪系统

## 功能

- **多期刊监控**: 兵工学报、Defense Technology、IEEE Trans. AI 等10个核心期刊
- **定时扫描**: 每6小时自动检查新文献
- **智能过滤**: 自动去重 + 相关性判断（AI/侵彻力学/可靠性工程三大方向）
- **自动下载**: OA文献自动下载，机构文献支持手动导入

## 期刊列表

1. 兵工学报
2. 兵器装备工程学报
3. IEEE Transactions on Reliability
4. Journal of Defense Modeling and Simulation
5. 火炮发射与控制学报
6. IEEE Transactions on Artificial Intelligence
7. Defense Technology
8. Reliability Engineering & System Safety
9. 弹道学报

## 核心关键词（三大方向）

### AI/大模型
人工智能, 深度学习, 机器学习, 大模型, LLM, neural network, deep learning, artificial intelligence

### 侵彻力学
侵彻, 穿甲, 破甲, 终点弹道, 动力学, penetration, terminal ballistics, armor

### 可靠性工程
可靠性, 失效分析, 寿命预测, 故障诊断, reliability, failure analysis, prognostics

## 使用方法

### 手动扫描
```bash
python journal_tracker.py scan
```

### 查看状态
```bash
python journal_tracker.py status
```

### 添加手动文献
```bash
python journal_tracker.py add <DOI> --title "论文标题"
```

### 导出报告
```bash
python journal_tracker.py report
```

## 文件结构

```
journal-tracker/
├── SKILL.md           # 本说明文档
├── journal_tracker.py # 主程序
├── journals.json      # 期刊配置
├── keywords.json      # 关键词配置
├── seen_papers.json   # 已处理文献记录（去重）
└── reports/           # 生成的报告
```

## Cron 配置

系统使用 OpenClaw cron 每6小时自动扫描：

```
0 */6 * * * → journal-tracker scan
```

## 输出

- 新文献通知 → 发送到配置的通知渠道
- PDF 文件 → `/root/.openclaw/workspace/papers/journal-tracker/`
- 报告 → `reports/YYYY-MM-DD.md`
