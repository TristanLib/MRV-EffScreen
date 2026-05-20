# MRV 特征集定义

更新日期：2026-05-20

本文档定义第三周建模时使用的特征集，目的是避免标签泄漏，并把“能效分类”和“异常/一致性筛查”两类任务分开。

## 目标字段

主分类目标：

- `efficiency_label_distance`
- `efficiency_label_distance_code`

目标由 `ship_type + reporting_year` 内的 `co2_per_distance_kg_nm` 三分位构造：

- `efficient` = 船型-年度组内低三分位。
- `medium` = 中三分位。
- `inefficient` = 高三分位。

第三周分类实验必须过滤：

- `is_main_experiment == true`
- `efficiency_label_distance != ""`

时间切分：

- `train`: 2018-2021
- `validation`: 2022
- `test`: 2023
- `external_2024`: 2024 Full ERs，仅作扩展年度测试

## 禁用字段

以下字段不能作为能效分类模型特征：

- `efficiency_label_distance`
- `efficiency_label_distance_code`
- `distance_efficiency_group_n`
- `distance_efficiency_rank_pct`
- `co2_per_distance_kg_nm`
- `co2_per_distance_on_laden_kg_nm`
- `co2_per_transport_work_mass_g_tnm`
- `co2_per_transport_work_volume_g_m3nm`
- `co2_per_transport_work_dwt_g_dwtnm`
- `co2_per_transport_work_pax_g_paxnm`
- `co2_per_transport_work_freight_g_tnm`
- `total_co2_emissions_mt`
- `co2_between_ms_ports_mt`
- `co2_departed_ms_ports_mt`
- `co2_to_ms_ports_mt`
- `co2_at_berth_mt`
- `co2_within_ports_mt`
- `co2_on_laden_mt`
- `co2_passenger_transport_mt`
- `co2_freight_transport_mt`
- `total_fuel_consumption_mt`
- `fuel_consumption_on_laden_mt`
- `fuel_per_distance_kg_nm`
- `fuel_per_distance_on_laden_kg_nm`
- `fuel_per_transport_work_mass_g_tnm`
- `fuel_per_transport_work_volume_g_m3nm`
- `fuel_per_transport_work_dwt_g_dwtnm`
- `fuel_per_transport_work_pax_g_paxnm`
- `fuel_per_transport_work_freight_g_tnm`

原因：这些字段与目标字段同源或高度同源，会把分类问题变成公式反推。

## 特征集 A：strict_static

用途：主论文中最干净的分类基线。

字段：

- `reporting_year`
- `ship_type`
- `technical_efficiency_type`
- `technical_efficiency_value`
- `technical_efficiency_is_not_applicable`
- `port_of_registry`
- `has_home_port`
- `has_ice_class`
- `monitoring_method_a`
- `monitoring_method_b`
- `monitoring_method_c`

说明：

- 不使用 IMO number 和 ship name，避免模型记忆船舶身份。
- 不使用任何 fuel / CO2 / transport work 字段。
- `monitoring_method_d_1` 和 `monitoring_method_d_2` 缺失率过高，默认不进第一版。

## 特征集 B：operational_no_emission

用途：检验加入非排放运营字段是否提升分类性能。

字段：

- 特征集 A 全部字段
- `time_spent_at_sea_hours`
- `distance_through_ice_nm`
- `time_spent_at_sea_through_ice_hours`

说明：

- `time_spent_at_sea_hours` 完整，可作为运营强度代理。
- 冰区相关字段缺失高，建议二值化或加 missing indicator。
- 仍然不加入燃油、排放总量和排放强度字段。

## 特征集 C：consistency_screening

用途：异常检测、数据一致性筛查、案例分析。不要用于主分类结论。

字段：

- 特征集 A/B 字段
- `total_fuel_consumption_mt`
- `fuel_per_distance_kg_nm`
- `total_co2_emissions_mt`
- `co2_per_distance_kg_nm`
- `time_spent_at_sea_hours`
- transport work 系列字段，按船型选择

说明：

- 这套字段可以用于 Isolation Forest、LOF、回归残差。
- 论文中必须写明它用于异常候选筛查，不用于证明预测能力。

## 缺失处理建议

分类任务：

- 类别字段：缺失填充为 `Unknown`。
- 布尔字段：保持 `true` / `false`。
- 数值字段：只用训练集内中位数做 imputation；分船型模型可用船型内训练集中位数。
- 高缺失字段：先不进主模型，必要时转为是否存在的二值特征。

异常检测：

- 可先限制在字段完整的主流船型，减少缺失填充造成的异常伪影。
- 异常结果只做 top-k 案例分析，不宣称违规。
