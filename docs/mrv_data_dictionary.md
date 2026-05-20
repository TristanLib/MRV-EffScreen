# THETIS-MRV 数据字典与字段审计

更新日期：2026-05-20

## 数据来源

主数据来自 THETIS-MRV public emission reports。官方入口为：

- EMSA THETIS-MRV: https://emsa.europa.eu/thetis-mrv.html
- THETIS-MRV public portal: https://mrv.emsa.europa.eu/#public/emission-report

本项目已定位到公开门户使用的可复现接口：

- 可下载文件清单：`https://mrv.emsa.europa.eu/api/public-emission-report/downloadable-files`
- 报告期清单：`https://mrv.emsa.europa.eu/api/public-emission-report/reporting-periods`
- 门户配置：`https://mrv.emsa.europa.eu/api/public-emission-report/configuration`
- 年度 Excel 下载：`https://mrv.emsa.europa.eu/api/public-emission-report/reporting-period-document/binary/{reportingPeriod}/{version}`

下载脚本：`src/data/download_mrv_public_reports.sh`

## 原始文件清单

完整清单见 `reports/tables/mrv_workbook_inventory.csv`。当前已下载 2018-2024 共 7 个年度文件，2024 文件包含 Full ERs 与 Partial ERs 两个 sheet。

| 年度 | 版本 | sheet | 样本行数 | 字段数 | 生成日期 |
|---:|---:|---|---:|---:|---|
| 2018 | 275 | 2018 | 12260 | 62 | 29-03-2026 05:12:54 |
| 2019 | 227 | 2019 | 12420 | 62 | 28-05-2025 05:08:28 |
| 2020 | 208 | 2020 | 12115 | 62 | 04-02-2026 05:10:47 |
| 2021 | 217 | 2021 | 12483 | 62 | 17-03-2026 05:11:44 |
| 2022 | 241 | 2022 | 13474 | 62 | 06-02-2026 05:24:31 |
| 2023 | 89 | 2023 | 12828 | 62 | 15-04-2026 05:08:22 |
| 2024 | 217 | 2024 Full ERs | 14139 | 113 | 19-05-2026 05:21:40 |
| 2024 | 217 | 2024 Partial ERs | 1026 | 113 | 19-05-2026 05:21:40 |

当前总行数为 90745。若只使用 2018-2023 全年度兼容字段，总行数为 75580。若加入 2024 Full ERs，总行数为 89719。2024 Partial ERs 不建议进入主实验，因为其 `Reporting Period` 是非完整年度区间。

## 字段组

2018-2023 共有 6 个字段组：

1. `Ship`：船舶身份、船型、报告期、技术能效、注册港、母港、冰级。
2. `DoC`：Document of Compliance 签发和到期日期。
3. `Verifier`：核查机构信息。
4. `Monitoring methods`：A、B、C、D 等监测方法标记。
5. `Annual monitoring results`：年度燃油、CO2、航段排放、海上时间、能效强度指标。
6. `Voluntary reporting`：冰区航行、laden voyage、额外解释和货物平均密度等自愿报告字段。

2024 在此基础上有重要变化：

1. 新增 `Company` 字段组，包括公司 IMO number 和公司名称。
2. `Verifier Number` 不再出现在 2024 公共表中。
3. `Annual monitoring results` 扩展到 90 个字段，新增 CH4、N2O、CO2eq、ETS 相关字段、cargo heating、dynamic positioning 等字段。
4. 2024 字段名从部分 `Annual average ...` 改为更直接的 `... per distance` / `... per transport work`，需要在清洗阶段做字段别名映射。

## 关键字段

| 标准字段名 | 原始字段 | 用途 | 第一周判断 |
|---|---|---|---|
| `ship__imo_number` | Ship / IMO Number | 主键之一 | 完整，可用 |
| `ship__name` | Ship / Name | 展示、案例分析 | 完整，但不作为模型特征 |
| `ship__ship_type` | Ship / Ship type | 分船型建模、分层标签 | 完整，核心字段 |
| `ship__reporting_period` | Ship / Reporting Period | 年度切分 | 完整；2024 Partial ERs 为区间字符串 |
| `ship__technical_efficiency` | Ship / Technical efficiency | 技术能效特征 | 2018 缺失约 12.5%，之后基本完整；需解析 EEDI/EEXI/EIV 与数值 |
| `ship__port_of_registry` | Ship / Port of Registry | 静态/行政特征 | 缺失约 3%-14%，可作为低优先级特征 |
| `ship__home_port` | Ship / Home Port | 静态/行政特征 | 缺失约 74%-82%，不建议主模型使用 |
| `ship__ice_class` | Ship / Ice Class | 冰区能力特征 | 缺失约 83%-84%，只适合二值化为 has_ice_class |
| `annual_monitoring_results__total_fuel_consumption` | Total fuel consumption | 运营/排放强相关字段 | 完整；若标签由排放强度构造，可能泄漏 |
| `annual_monitoring_results__total_co2_emissions` | Total CO2 emissions | 排放总量 | 完整；若预测能效等级，通常应从严格特征集中排除 |
| `annual_monitoring_results__annual_average_co2_emissions_per_distance` | Annual average CO2 emissions per distance | 通用能效标签候选 | 2018-2023 完整；2024 需要映射到 `co2_emissions_per_distance` |
| `annual_monitoring_results__annual_average_co2_emissions_per_transport_work_*` | CO2 per transport work | 船型相关能效标签候选 | 多数可用，但需按船型选择合适口径 |
| `annual_monitoring_results__total_co2eq_emissions` | Total CO2eq emissions | 2024 扩展字段 | 仅 2024 有，不进入 2018-2023 主实验 |

完整字段级缺失率、样例值和类型统计见 `reports/tables/mrv_schema_audit.csv`。

## 船型分布

完整统计见 `reports/tables/mrv_ship_type_counts.csv`。样本最多的船型为：

| 船型 | 行数 |
|---|---:|
| Bulk carrier | 27761 |
| Oil tanker | 13858 |
| Container ship | 13500 |
| Chemical tanker | 9881 |
| General cargo ship | 8855 |
| Vehicle carrier | 3238 |
| Ro-pax ship | 2839 |
| Gas carrier | 2473 |
| LNG carrier | 2184 |
| Ro-ro ship | 1724 |

第一版建模建议至少对 Bulk carrier、Oil tanker、Container ship、Chemical tanker、General cargo ship 做分船型结果。样本极少的 Combination carrier、Passenger ship (Cruise Passenger ship)、Other ship types (Offshore) 不宜单独建模。

## 标签候选

### 主标签：船型内 CO2 per distance 三分类

字段：

- 2018-2023：`Annual average CO2 emissions per distance [kg CO2 / n mile]`
- 2024：`CO2 emissions per distance [kg CO2 / n mile]`

构造方式：

1. 在 `ship_type + reporting_year` 内计算三分位数。
2. 低三分位为 `efficient`，中三分位为 `medium`，高三分位为 `inefficient`。
3. 仅在同船型、同年度内比较，避免跨船型尺度差异。

优点：全船型可用、缺失率低、适合快速跑通基线。缺点：只按距离标准化，不如 transport work 贴近实际运输效率。

### 稳健性标签：船型相关 transport work 强度三分类

候选字段：

- Mass: `CO2 emissions per transport work (mass)`
- DWT: `CO2 emissions per transport work (dwt)`
- Pax: `CO2 emissions per transport work (pax)`
- Freight: `CO2 emissions per transport work (freight)`

建议用法：

- Bulk carrier、Oil tanker、Chemical tanker、General cargo ship：优先测试 mass 或 dwt。
- Passenger / Ro-pax：优先测试 pax。
- Ro-ro / Vehicle carrier：优先测试 freight。

第一版不要把所有船型强行套同一个 transport work 指标，否则解释成本会升高。

### 异常检测标签

第一版不做人工真值标签，采用无监督和残差排序：

1. Isolation Forest：在船型内使用运营和强度字段识别 top-k 异常。
2. LOF：作为局部密度对照。
3. 回归残差：用非目标字段预测 CO2 per distance 或 total CO2，取残差 top-k 做案例分析。

异常结果只能表述为“异常筛查候选”，不能表述为合规违规或虚假申报。

## 泄漏字段清单

如果主标签使用 CO2 per distance 或 CO2 per transport work，以下字段不能进入严格特征集：

1. 目标字段本身及同族强度字段：所有 `CO2 emissions per distance`、`CO2 emissions per transport work`、`CO2eq emissions per distance`、`CO2eq emissions per transport work`。
2. 直接排放总量：`Total CO2 emissions`、各航段 CO2 emissions、2024 的 `Total CO2eq emissions`、CH4、N2O 相关排放字段。
3. 高度同源燃油字段：`Total fuel consumption`、fuel consumption per distance、fuel consumption per transport work。
4. 由目标直接派生的 on laden 指标。

建议实验分三套特征：

1. `strict_static`：船型、年份、技术能效、注册港、冰级、监测方法，不含燃油和排放。
2. `operational_no_emission`：在 static 基础上加入海上时间、through ice、报告覆盖相关字段，但仍不含燃油/排放强度。
3. `consistency_screening`：用于异常检测，可加入燃油、排放总量和强度字段，但论文中明确它是数据一致性/异常筛查，不是预测式能效分类。

## 第一版实验范围建议

主实验：

1. 使用 2018-2023 数据建立兼容字段基线。
2. 训练集：2018-2021，验证集：2022，测试集：2023。
3. 另做随机分层切分作为对照。
4. 使用 Full ERs 的 2024 作为外部年度测试或扩展实验，不把 Partial ERs 放入主结果。

原因：

- 2018-2023 schema 稳定，适合快速发论文。
- 2024 新增 GHG/ETS 字段，政策口径变化明显，直接混入会增加解释负担。
- Partial ERs 不是完整年度，适合单独作为鲁棒性/异常样本讨论，不适合作为主模型训练数据。

## 第二周已确认

1. 字段别名映射已在 `src/data/build_mrv_modeling_base.py` 中实现，统一了 2018-2023 与 2024 的 time at sea、CO2 per distance、transport work 等字段。
2. `Technical efficiency` 已解析为：
   - `technical_efficiency_type`
   - `technical_efficiency_value`
   - `technical_efficiency_is_not_applicable`
3. 主标签确定为 `ship_type + reporting_year` 内的 `co2_per_distance_kg_nm` 三分类。
4. 2018-2023 作为主实验；2024 Full ERs 标记为 `external_2024`；2024 Partial ERs 标记为 `excluded_partial_2024`。
5. 缺失处理策略与特征集定义已写入 `docs/mrv_feature_sets.md`。

第二周生成的主要数据集：

- `data/interim/mrv_unified_public_reports.csv`
- `data/processed/mrv_modeling_base.csv`

第二周生成的主要质量报告：

- `reports/tables/mrv_processed_missingness.csv`
- `reports/tables/mrv_processed_summary.csv`
- `reports/tables/mrv_label_distribution.csv`
- `reports/tables/mrv_year_scope_counts.csv`
