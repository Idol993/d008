# 财产/人寿保险核保理赔系统 - 版本发布与合规回滚自动化管理系统

## 系统概述

本系统是专为保险行业设计的版本发布与合规回滚自动化管理平台，覆盖核保、理赔、合规、法务等全流程，满足银保监监管要求。

## 核心功能模块

### 1. 发布申请与前置条件检查
- 支持按版本、险种、保单类型提交发布申请
- 自动检查4项前置条件：
  - 核保规则准确率
  - 理赔对账一致性
  - 监管条款适配
  - 客户信息安全校验

### 2. 风险级别判断与合规审批
- 三种风险级别：
  - 常规规则迭代 (routine)
  - 紧急理赔故障 (urgent_claim)
  - 监管条款更新 (regulatory_update)
- 自动生成对应审批流程
- 支持核保、理赔、合规、法务四方审批

### 3. 险种灰度策略推送
- 支持车险、寿险、重疾险三类险种
- 按险种分阶段灰度推送
- 灰度间隔根据风险级别动态调整

### 4. 实时监控与自动回滚
- 每3分钟监控4项核心指标：
  - 核保通过率
  - 理赔处理延迟
  - 赔付异常率
  - 信息泄露风险
- 超过阈值自动触发合规回滚
- 自动恢复上一监管认可稳定版本
- 回滚后自动重启核生理赔监控

### 5. 回滚报告与通知
- 生成回滚报告，包含：
  - 保单影响范围
  - 理赔异常原因
  - 监管条款说明
- 通知核保、理赔、客服、合规干系人

### 6. 手动回滚演练
- 创建保险业务回滚演练
- 自动生成演练计划
- 执行保单校验
- 归档监管备查

### 7. 每周统计报表
- 每周一自动统计：
  - 系统发布成功率
  - 回滚次数
  - 理赔处理时长
- 生成合规趋势图表 PDF
- 生成保险运营 Excel 报表

### 8. 历史记录查询与导出
- 按发布时间、险种、保单类型、版本号组合查询
- 支持批量导出（CSV/Excel格式）

### 9. 银保监审计日志
- 所有操作完整记录
- 可直接用于监管检查
- 支持导出审计日志

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 初始化数据库

```bash
python main.py --init-db
```

### 运行演示

```bash
python main.py --demo
```

### 启动系统服务

```bash
python main.py --start
```

## 目录结构

```
.
├── config.py              # 系统配置文件
├── models.py              # 数据模型定义
├── audit_logger.py        # 审计日志模块
├── release_manager.py     # 发布管理模块
├── approval_manager.py    # 审批流程模块
├── grayscale_manager.py   # 灰度发布模块
├── monitor_rollback.py    # 监控与回滚模块
├── report_notification.py # 报告与通知模块
├── rollback_drill.py      # 回滚演练模块
├── weekly_report.py       # 周报生成模块
├── history_export.py      # 历史查询与导出模块
├── main.py                # 主入口程序
├── requirements.txt       # 依赖列表
├── data/                  # 数据目录
├── logs/                  # 日志目录
└── reports/               # 报表目录
```

## 配置说明

主要配置项位于 `config.py`：

- `THRESHOLDS`: 各项监控指标阈值
- `INSURANCE_TYPES`: 支持的险种类型
- `RISK_LEVELS`: 风险级别定义
- `GRAYSCALE_STRATEGY`: 灰度推送策略
- `APPROVERS`: 各角色审批人
- `STAKEHOLDERS`: 干系人通知列表
- `MONITOR_INTERVAL_MINUTES`: 监控间隔（分钟）
- `WEEKLY_REPORT_DAY`: 周报生成日（0=周一）

## 数据库表结构

1. `release_requests` - 发布申请表
2. `approval_records` - 审批记录表
3. `precheck_records` - 前置检查记录表
4. `grayscale_records` - 灰度发布记录表
5. `monitor_records` - 监控记录表
6. `rollback_records` - 回滚记录表
7. `rollback_drills` - 回滚演练表
8. `weekly_reports` - 周报表
9. `audit_logs` - 审计日志表
10. `stable_versions` - 稳定版本表

## 监管合规

本系统所有操作均记录审计日志，满足：
- 《保险法》相关要求
- 银保监会核保理赔管理办法
- 个人信息保护法
- 金融消费者权益保护实施办法
