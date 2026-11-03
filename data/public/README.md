# 真实公开企业数据集

本目录存放平台用于生产验收的两套真实企业数据。两份数据均来自 UCI Machine Learning Repository，已做 UTF-8 逗号分隔格式归一，并只追加少量可解释的派生列；原始取值未改写。

## 1. UCI Bank Marketing（银行电话营销活动）

- 文件：`uci_bank_marketing.csv`
- 规模：45,211 行 × 19 列
- 机构：一家葡萄牙银行业机构（数据已匿名化）
- 时间：2008 年 5 月—2010 年 11 月的电话营销活动（原始数据不提供逐行年份）
- 来源：UCI Machine Learning Repository, ID 222
  - 数据集页：https://archive.ics.uci.edu/dataset/222/bank+marketing
  - DOI：https://doi.org/10.24432/C5K306
  - 原始文件：`bank.zip` 中的 `bank-full.csv`（分号分隔）
- 字段：客户属性（age、job、marital、education、credit_default、balance、housing、loan）、联系信息（contact、day、month、duration、campaign_contacts、days_since_previous_contact、previous_contacts、previous_outcome）、活动结果（subscribed）
- 格式归一：分号改为逗号；`default`→`credit_default`、`pdays`→`days_since_previous_contact`、`previous`→`previous_contacts`、`poutcome`→`previous_outcome`、`campaign`→`campaign_contacts`、`y`→`subscribed`
- 派生列：`month_num`（1–12，便于按月排序）、`subscribed_flag`（yes=1 / no=0，便于计算订阅率）
- 典型用途：5 月与 6 月订阅转化对比、渠道/职业/婚姻/教育分组转化率、通话时长与转化关系

## 2. UCI Online Shoppers Purchasing Intention（在线商店访客购买意向）

- 文件：`uci_online_shoppers.csv`
- 规模：12,330 行 × 21 列
- 机构：一家在线商店（每条会话对应一名匿名访客，覆盖 1 年）
- 来源：UCI Machine Learning Repository, ID 468
  - 数据集页：https://archive.ics.uci.edu/dataset/468/online+shoppers+purchasing+intention+dataset
  - DOI：https://doi.org/10.24432/C5F88Q
  - 原始文件：`online_shoppers_intention.csv`
- 字段：页面浏览与停留（administrative、informational、product_related 及对应 duration）、Google Analytics 指标（bounce_rates、exit_rates、page_values）、访问背景（special_day、month、operating_systems、browser、region、traffic_type、visitor_type、weekend）、购买结果（purchase，布尔值）
- 格式归一：列名统一为小写下划线；`Month`→`month`、`Weekend`→`weekend` 等；`Revenue`→`purchase`，避免被误读为金额字段
- 派生列：`month_num`（1–12）、`weekend_flag`（TRUE=1 / FALSE=0）、`purchased_flag`（购买=1 / 未购买=0）
- 典型用途：月度购买转化率、流量类型/访客类型/周末效应分析、跳出率与转化关系

## 引用与许可

两份数据均为 UCI 公开数据集，使用时应保留数据集页与 DOI 引用。具体许可条款以各自数据集页面为准。

- Moro, S., Cortez, P., & Rita, P. (2014). A Data-Driven Approach to Predict the Success of Bank Telemarketing. *Decision Support Systems*. UCI ID 222.
- Sakar, C., & Kastro, Y. (2018). Online Shoppers Purchasing Intention Dataset. UCI ID 468.

## 平台导入

平台通过「数据资产 → 上传 CSV」接入，上传后自动完成 Schema 检查；确认遮蔽字段后即可用于智能问数和证据链分析。当前生产工作空间已登记：

- `UCI 银行营销活动（真实企业数据）`
- `UCI 在线商店访客购买意向（真实企业数据）`

两套数据均不含姓名、手机号、证件号等直接身份信息；银行数据的客户属性为匿名分组，在线商店数据为匿名会话。
